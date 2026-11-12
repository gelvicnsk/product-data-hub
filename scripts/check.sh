#!/usr/bin/env bash
# Vérifie que les services du Product Data Hub répondent (docker-compose).
#   scripts/check.sh ; echo $?      -> 0 si tout va bien, 1 sinon
set -euo pipefail

cd "$(dirname "$0")/.."
[[ -f .env ]] && { set -a; source .env; set +a; }

ko=0
check() {   # nom, commande
  if eval "$2" >/dev/null 2>&1; then echo "OK   $1"; else echo "KO   $1" >&2; ko=1; fi
}

check "postgres"  "docker compose exec -T postgres pg_isready -U ${POSTGRES_USER:-hub_admin}"
check "faux CRM"  "curl -sf localhost:${MOCK_CRM_PORT:-8010}/health"
check "keycloak"  "curl -sf localhost:${KEYCLOAK_PORT:-8180}/realms/product-hub"
check "api"       "curl -sf localhost:${API_PORT:-8002}/health"
exit $ko
