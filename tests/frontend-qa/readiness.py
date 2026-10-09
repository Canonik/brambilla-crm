"""Read-only frontend integration preflight; no dependencies or CRM mutations."""
import argparse
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request

ROUTES = {
    'companies': '/companies', 'contacts': '/contacts', 'deals': '/deals',
    'tickets': '/tickets', 'lists': '/dormant', 'assistant': '/assistant',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frontend', type=Path, default=Path('frontend'))
    parser.add_argument('--base-url', help='Optional deployed origin; only public GETs are issued')
    args = parser.parse_args()
    failures = []
    for name in ('package.json', 'package-lock.json', 'index.html', 'src/main.tsx'):
        if not (args.frontend / name).is_file():
            failures.append(f'Missing frontend/{name}')
    if args.base_url:
        base = args.base_url.rstrip('/')
        def get(path):
            with urllib.request.urlopen(base + path, timeout=10) as response:
                return response.headers.get('Content-Type', ''), response.read().decode('utf-8')
        try:
            _, body = get('/health')
            health = json.loads(body)
            if health.get('status') != 'ok' or health.get('version') != '2026-09':
                failures.append('Health status/version mismatch')
            for module, route in ROUTES.items():
                if health.get('ui', {}).get(module) != route:
                    failures.append(f'Health route mismatch: {module}')
        except (OSError, ValueError) as exc:
            failures.append(f'Health request failed: {type(exc).__name__}')
        for route in ROUTES.values():
            try:
                mime, body = get(route)
                if 'text/html' not in mime or 'id="root"' not in body:
                    failures.append(f'{route}: expected React HTML shell')
                if 'UI build failed' in body:
                    failures.append(f'{route}: deployment serves build failure placeholder')
            except OSError as exc:
                failures.append(f'{route}: request failed: {type(exc).__name__}')
    print(json.dumps({'failures': failures, 'live_checked': bool(args.base_url),
                      'scope': 'Preflight only; does not prove rendering or CRM correctness'}, indent=2))
    return int(bool(failures))


if __name__ == '__main__':
    sys.exit(main())
