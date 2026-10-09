# Deploying on Railway

The Railway project is the organizers' one (invite as Editor). One service, built from the
root `Dockerfile`, plus the PostgreSQL plugin. Region stays EU West.

## One-time setup (dashboard or CLI)

1. In the project, add **PostgreSQL** (Database → Add PostgreSQL).
2. Add a service from the GitHub repo `Canonik/brambilla-crm`, branch `main`. Railway reads
   `railway.json` (Dockerfile builder, `/health` healthcheck).
3. Service → Variables:
   - `DATABASE_URL` = `${{Postgres.DATABASE_URL}}` (reference to the plugin)
   - `CRM_TOKEN` = the token from the platform's Deploy page
   - `OPENROUTER_API_KEY` = the model key from the Deploy page
   - `PUBLIC_BASE_URL` = `https://<service-domain>` (optional, export links)
4. Settings → Networking → Generate domain. Register that https address on the platform.

## CLI equivalent

```
railway login            # opens the browser once
railway link             # pick the organizers' project and the service
railway add --database postgres
railway variables --set CRM_TOKEN=... --set OPENROUTER_API_KEY=... --set 'DATABASE_URL=${{Postgres.DATABASE_URL}}'
railway up               # builds from the local tree; or let the GitHub integration deploy main
railway domain
```

## After every deploy

```
BASE_URL=https://<domain> CRM_TOKEN=<token> EXPORT_URL=<public url of export.zip> \
  .venv/bin/pytest -q tests/acceptance -k "form_check or conformity"
```
Then the platform's form check. The migration must be measured on Railway: run
`tests/acceptance/test_migration.py` with `EXPORT_URL` pointing at a public copy of the
export (a GitHub release asset of this repo works, it is a public repo).
