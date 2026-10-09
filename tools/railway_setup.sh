#!/bin/sh
# One-time Railway setup from the CLI, run by the coordinator after `railway login`.
# Secrets come from ~/.brambilla-secrets.env (outside the repo):
#   CRM_TOKEN=...
#   OPENROUTER_API_KEY=...
set -eu
RAILWAY=${RAILWAY:-$HOME/.local/bin/railway}
test -f "$HOME/.brambilla-secrets.env" || { echo "missing ~/.brambilla-secrets.env"; exit 1; }
. "$HOME/.brambilla-secrets.env"
cd "$(dirname "$0")/.."
"$RAILWAY" whoami
# link interactively the first time (project and service are chosen in the prompt)
"$RAILWAY" status || "$RAILWAY" link
"$RAILWAY" variables --set "CRM_TOKEN=$CRM_TOKEN" --set "OPENROUTER_API_KEY=$OPENROUTER_API_KEY" --set 'DATABASE_URL=${{Postgres.DATABASE_URL}}' --skip-deploys
"$RAILWAY" up --detach
"$RAILWAY" domain
