"""Full migration and 20-client HTTP reads in a disposable local PostgreSQL schema.

Required: SCORE_DATABASE_URL (loopback only), SCORE_SERVER_ROOT (Core server/).
Only sends reset when --reset is requested, to its own private schema. Copies source to a private temporary directory so a
concurrent Core edit cannot change the code used for the optional restart check.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import http.server
import json
import math
import os
from pathlib import Path
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import uuid


def main():
    import httpx
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    from psycopg.rows import dict_row

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--clients", type=int, default=20)
    parser.add_argument("--reads-per-client", type=int, default=10)
    parser.add_argument("--restart", action="store_true")
    parser.add_argument("--reset", action="store_true", help="Verify reset in this run's disposable schema")
    args = parser.parse_args()
    assert args.clients > 0 and args.reads_per_client > 0
    dsn = os.environ["SCORE_DATABASE_URL"]
    assert conninfo_to_dict(dsn).get("host") in {"127.0.0.1", "localhost", "::1"}, "Loopback PostgreSQL required"
    source = Path(os.environ["SCORE_SERVER_ROOT"]).resolve()
    assert (source / "app/schema.sql").is_file()
    archive = args.export.resolve()
    assert archive.is_file()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    schema = "score_volume_" + uuid.uuid4().hex
    isolated_dsn = make_conninfo(dsn, options=f"-c search_path={schema}")
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=source, text=True, capture_output=True)
    report = {
        "backend_root": str(source), "schema": schema,
        "transport": "real loopback HTTP / uvicorn subprocess / local PostgreSQL",
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "source_commit": revision.stdout.strip() if revision.returncode == 0 else None,
        "candidate_baseline_commit": os.environ.get("SCORE_BASELINE_COMMIT"),
        "tracked_backend_clean": subprocess.run(["git", "diff", "--quiet", "HEAD", "--", "app"], cwd=source).returncode == 0 if revision.returncode == 0 else None,
        "source_sha256": {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source.joinpath("app").rglob("*") if p.is_file() and p.suffix in {".py", ".sql"}},
    }
    report_path = args.output.resolve()
    log_path = report_path.with_suffix(".log")
    runtime = tempfile.TemporaryDirectory(prefix="score-volume-runtime-")
    snapshot = Path(runtime.name) / "server"
    shutil.copytree(source, snapshot, ignore=shutil.ignore_patterns(".venv", "__pycache__", "*.pyc", "tests"))
    admin = psycopg.connect(dsn, autocommit=True, row_factory=dict_row)
    report["postgres"] = admin.execute("SELECT version() AS version").fetchone()["version"]
    admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    proc = None
    export_server = None
    server_log = log_path.open("w")
    env = dict(os.environ)
    env.update(DATABASE_URL=isolated_dsn, CRM_TOKEN="score-local-only", OPENROUTER_API_KEY="", DB_POOL_MIN="2", DB_POOL_MAX="24")
    headers = {"Authorization": "Bearer score-local-only"}

    class ArchiveHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(archive.stat().st_size))
            self.end_headers()
            with archive.open("rb") as fh:
                shutil.copyfileobj(fh, self.wfile)

        def log_message(self, *unused):
            pass

    def start_server():
        nonlocal proc
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        port = listener.getsockname()[1]
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", str(snapshot), "--fd", str(listener.fileno()), "--no-access-log", "--log-level", "warning"],
            env=env, stdout=server_log, stderr=subprocess.STDOUT, pass_fds=(listener.fileno(),),
        )
        listener.close()
        url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            assert proc.poll() is None, f"uvicorn exited: see {log_path}"
            try:
                response = httpx.get(url + "/health", timeout=1, trust_env=False)
                if response.status_code == 200:
                    return url
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        raise RuntimeError("Local uvicorn did not become ready")

    def stop_server():
        nonlocal proc
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        proc = None

    def process_memory():
        if proc is None:
            return {}
        result = {}
        for line in Path(f"/proc/{proc.pid}/status").read_text().splitlines():
            key, _, value = line.partition(":")
            if key in {"VmRSS", "VmHWM", "VmSize", "VmPeak"}:
                result[key + "_KiB"] = int(value.strip().split()[0])
        return result

    def snapshot_state():
        with psycopg.connect(isolated_dsn, row_factory=dict_row) as conn:
            assert conn.execute("SELECT current_schema() AS name").fetchone()["name"] == schema
            counts = {r["object_type"]: r["n"] for r in conn.execute("SELECT object_type,count(*) AS n FROM objects GROUP BY object_type")}
            vat = conn.execute("SELECT definition FROM properties WHERE object_type='companies' AND name='partita_iva'").fetchone()
            return {
                "counts": counts,
                "id_legacy_property_definitions": conn.execute("SELECT count(*) AS n FROM properties WHERE name='id_legacy'").fetchone()["n"],
                "partita_iva": vat["definition"] if vat else None,
                "pipelines": [r["definition"]["label"] for r in conn.execute("SELECT definition FROM pipelines ORDER BY object_type,id")],
                "lists": [r["definition"].get("name") for r in conn.execute("SELECT definition FROM lists ORDER BY list_id")],
            }

    try:
        export_server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), ArchiveHandler)
        threading.Thread(target=export_server.serve_forever, daemon=True).start()
        base_url = start_server()
        with psycopg.connect(isolated_dsn, row_factory=dict_row) as conn:
            assert conn.execute("SELECT current_schema() AS name").fetchone()["name"] == schema
            assert conn.execute("SELECT count(*) AS n FROM objects").fetchone()["n"] == 0
        print(f"Migrating {archive.stat().st_size} bytes into private schema {schema}", flush=True)
        start = time.perf_counter()
        response = httpx.post(base_url + "/__migrate", headers=headers, json={"export_url": f"http://127.0.0.1:{export_server.server_port}/archive?sample=1"}, timeout=300, trust_env=False)
        report["migration"] = {"http_status": response.status_code, "seconds_http_total": round(time.perf_counter() - start, 4), "response_bytes": len(response.content)}
        if response.status_code != 204:
            report["migration"]["error"] = response.text[:2000]
            raise RuntimeError(f"Migration failed: {response.status_code}")
        with psycopg.connect(isolated_dsn, row_factory=dict_row) as conn:
            report["migration"]["metadata"] = conn.execute("SELECT value FROM meta WHERE key='migration'").fetchone()["value"]
            report["associations"] = conn.execute("SELECT count(*) AS n FROM associations").fetchone()["n"]
            report["dormant_members"] = conn.execute("SELECT count(*) AS n FROM list_memberships").fetchone()["n"]
            # Deterministic spread across the entire imported ID range.
            limits = conn.execute("SELECT min(id) AS lo,max(id) AS hi FROM objects").fetchone()
            samples = []
            count = args.clients * args.reads_per_client
            for i in range(count):
                candidate_id = limits["lo"] + i * (limits["hi"] - limits["lo"]) // max(1, count - 1)
                row = conn.execute("SELECT id,object_type FROM objects WHERE id >= %s ORDER BY id LIMIT 1", (candidate_id,)).fetchone()
                samples.append((row["object_type"], str(row["id"])))
        report["before_restart"] = snapshot_state()
        report["migration_process_memory"] = process_memory()
        print(f"Migration HTTP {report['migration']['seconds_http_total']:.3f}s; reading {len(samples)} records with {args.clients} clients", flush=True)
        barrier = threading.Barrier(args.clients)

        def read_worker(worker_id):
            rows = []
            with httpx.Client(base_url=base_url, headers=headers, timeout=10, trust_env=False) as client:
                barrier.wait(timeout=15)
                for object_type, record_id in samples[worker_id::args.clients]:
                    started = time.perf_counter()
                    try:
                        r = client.get(f"/crm/v3/objects/{object_type}/{record_id}")
                        elapsed = time.perf_counter() - started
                        correct = r.status_code == 200 and r.json().get("id") == record_id
                        rows.append({"seconds": elapsed, "status": r.status_code, "correct_id": correct})
                    except Exception as exc:
                        rows.append({"seconds": time.perf_counter() - started, "status": None, "error": type(exc).__name__, "correct_id": False})
            return rows

        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=args.clients) as executor:
            results = [row for batch in executor.map(read_worker, range(args.clients)) for row in batch]
        durations = sorted(r["seconds"] for r in results)
        report["reads"] = {
            "clients": args.clients, "requests": len(results), "seconds_wall": round(time.perf_counter() - start, 4),
            "p50_ms": round(statistics.median(durations) * 1000, 3),
            "p95_ms": round(durations[math.ceil(0.95 * len(durations)) - 1] * 1000, 3),
            "max_ms": round(max(durations) * 1000, 3),
            "correct_responses": sum(r["correct_id"] for r in results),
            "status_counts": {str(status): sum(r["status"] == status for r in results) for status in sorted(set(r["status"] for r in results), key=str)},
            "over_one_second": sum(r["seconds"] >= 1 for r in results),
            "object_types_sampled": sorted({ot for ot, _ in samples}),
        }
        print(f"Read result: {json.dumps(report['reads'])}", flush=True)
        report["after_reads_process_memory"] = process_memory()
        if args.restart:
            stop_server()
            base_url = start_server()
            report["after_restart"] = snapshot_state()
            report["after_restart_process_memory"] = process_memory()
            before, after = report["before_restart"], report["after_restart"]
            report["restart"] = {
                "records_preserved": before["counts"] == after["counts"],
                "id_legacy_definitions_preserved": before["id_legacy_property_definitions"] == after["id_legacy_property_definitions"],
                "partita_iva_preserved": before["partita_iva"] == after["partita_iva"],
                "pipelines_preserved": before["pipelines"] == after["pipelines"],
                "lists_preserved": before["lists"] == after["lists"],
            }
            print(f"Restart result: {json.dumps(report['restart'])}", flush=True)
            assert all(report["restart"].values()), "Restart did not preserve CRM state"
        if args.reset:
            started = time.perf_counter()
            response = httpx.post(base_url + "/__reset", headers=headers, timeout=10, trust_env=False)
            report["reset"] = {"http_status": response.status_code, "response_bytes": len(response.content),
                               "seconds": round(time.perf_counter() - started, 4)}
            assert response.status_code == 204 and not response.content
            after = snapshot_state()
            report["after_reset"] = after
            assert after["counts"] == {}
            assert after["id_legacy_property_definitions"] == 0 and after["partita_iva"] is None
            assert sorted(after["pipelines"]) == ["Sales Pipeline", "Support Pipeline"]
            assert after["lists"] == []
            with psycopg.connect(isolated_dsn, row_factory=dict_row) as conn:
                report["reset"]["remaining_associations"] = conn.execute("SELECT count(*) AS n FROM associations").fetchone()["n"]
                report["reset"]["remaining_memberships"] = conn.execute("SELECT count(*) AS n FROM list_memberships").fetchone()["n"]
            assert report["reset"]["remaining_associations"] == report["reset"]["remaining_memberships"] == 0
            print(f"Reset result: {json.dumps(report['reset'])}", flush=True)
    except BaseException as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        stop_server()
        if export_server is not None:
            export_server.shutdown()
            export_server.server_close()
        server_log.close()
        try:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
            report["own_schema_removed"] = True
        finally:
            admin.close()
            runtime.cleanup()
            report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        print(f"Report: {report_path}", flush=True)


if __name__ == "__main__":
    main()
