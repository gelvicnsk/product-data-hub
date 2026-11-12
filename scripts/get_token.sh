#!/usr/bin/env bash
# Obtient un jeton d'accès Keycloak pour un utilisateur de démonstration.
#   TOKEN=$(scripts/get_token.sh alice)     # rôle reader
#   TOKEN=$(scripts/get_token.sh bob)       # rôle data_steward
#   curl -H "Authorization: Bearer $TOKEN" localhost:8001/products
# Les mots de passe viennent de .env (KC_DEMO_READER_PASSWORD, KC_DEMO_STEWARD_PASSWORD).
set -euo pipefail

cd "$(dirname "$0")/.."
set -a; source .env; set +a

user="${1:-alice}"
case "$user" in
  alice) password="$KC_DEMO_READER_PASSWORD" ;;
  bob)   password="$KC_DEMO_STEWARD_PASSWORD" ;;
  *) echo "utilisateur inconnu : $user (alice ou bob)" >&2; exit 2 ;;
esac

curl -sf "http://localhost:${KEYCLOAK_PORT:-8180}/realms/product-hub/protocol/openid-connect/token" \
  -d grant_type=password -d client_id=product-hub-cli \
  -d username="$user" --data-urlencode password="$password" \
  | python3 -c "import json, sys; print(json.load(sys.stdin)['access_token'])"
