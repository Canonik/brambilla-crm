#!/bin/sh
# Read-only production checks. Needs CRM_TOKEN in the environment; never resets or migrates.
# Usage: CRM_TOKEN=... sh tools/prod_readonly_check.sh [base_url]
set -u
BASE=${1:-https://faithful-emotion-production-1fe1.up.railway.app}
AUTH="Authorization: Bearer ${CRM_TOKEN:?set CRM_TOKEN}"
get() { # label path
  code=$(curl -sS -m 15 -o /tmp/prc_body -w '%{http_code}' -H "$AUTH" "$BASE$2")
  printf '%-44s HTTP %s  %s\n' "$1" "$code" "$(head -c 160 /tmp/prc_body | tr '\n' ' ')"
}
post() { # label path json
  code=$(curl -sS -m 15 -o /tmp/prc_body -w '%{http_code}' -H "$AUTH" -H 'Content-Type: application/json' -X POST -d "$3" "$BASE$2")
  printf '%-44s HTTP %s  %s\n' "$1" "$code" "$(head -c 160 /tmp/prc_body | tr '\n' ' ')"
}
echo "== $BASE  $(date +%H:%M:%S)"
code=$(curl -sS -m 15 -o /tmp/prc_body -w '%{http_code}' "$BASE/health"); printf '%-44s HTTP %s  %s\n' "health (no token)" "$code" "$(cat /tmp/prc_body)"
code=$(curl -sS -m 15 -o /dev/null -w '%{http_code}' -H 'Authorization: Bearer wrong' "$BASE/crm/v3/objects/contacts"); printf '%-44s HTTP %s\n' "wrong token -> 401" "$code"
get "stats" "/__stats"
get "contacts legacy list" "/crm/v3/objects/contacts?limit=1"
get "contacts dated list" "/crm/objects/2026-09/contacts?limit=1"
get "companies dated list" "/crm/objects/2026-09/companies?limit=1&properties=name,fatturato_2025,classe_cliente,partita_iva"
post "companies search total" "/crm/v3/objects/companies/search" '{"limit":1}'
post "contacts search total" "/crm/v3/objects/contacts/search" '{"limit":1}'
post "deals search total" "/crm/v3/objects/deals/search" '{"limit":1}'
post "tickets search total" "/crm/v3/objects/tickets/search" '{"limit":1}'
get "pipelines deals legacy" "/crm/v3/pipelines/deals"
get "pipelines deals dated" "/crm/pipelines/2026-09/deals"
get "pipelines tickets legacy" "/crm/v3/pipelines/tickets"
get "dormant list legacy" "/crm/v3/lists/object-type-id/0-2/name/Clienti%20dormienti"
get "dormant list dated" "/crm/lists/2026-09/object-type-id/0-2/name/Clienti%20dormienti"
get "owners legacy" "/crm/v3/owners?limit=1"
get "properties companies partita_iva" "/crm/v3/properties/companies/partita_iva"
get "properties dated id_legacy deals" "/crm/properties/2026-09/deals/id_legacy"
get "assoc labels contacts companies v4" "/crm/v4/associations/contacts/companies/labels"
get "assoc labels dated" "/crm/associations/2026-09/contacts/companies/labels"
get "openapi" "/__openapi.json"
for p in / /companies /deals /dormant /tickets /assistant; do
  code=$(curl -sS -m 15 -o /tmp/prc_body -w '%{http_code} %{content_type} %{size_download}B' "$BASE$p"); printf '%-44s %s\n' "ui $p" "$code"
done
# 20 parallel single-record reads, p95 (needs a company id)
cid=$(curl -sS -m 15 -H "$AUTH" "$BASE/crm/v3/objects/companies?limit=1" | python3 -c 'import sys,json; r=json.load(sys.stdin).get("results",[]); print(r[0]["id"] if r else "")')
if [ -n "$cid" ]; then
  for i in $(seq 1 40); do curl -sS -m 15 -o /dev/null -w '%{time_total}\n' -H "$AUTH" "$BASE/crm/v3/objects/companies/$cid" & done | sort -n > /tmp/prc_times; wait
  n=$(wc -l < /tmp/prc_times); p95=$(sed -n "$(( (n*95+99)/100 ))p" /tmp/prc_times); printf '%-44s n=%s p95=%ss max=%ss\n' "40 parallel company reads" "$n" "$p95" "$(tail -1 /tmp/prc_times)"
fi
