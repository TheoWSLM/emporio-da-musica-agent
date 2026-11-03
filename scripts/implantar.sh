#!/usr/bin/env bash
# Deploy / update on the home server. Run from the app directory (the git clone).
#   scripts/implantar.sh            # deploy the current checkout
#   git checkout v1.0-submission && scripts/implantar.sh
# Validates the configuration, builds tagged images, starts the stack (DB -> migrations -> ingestion
# -> API -> edge) and runs the smoke test. Never restarts Docker, never prunes, never touches other apps.
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE=(docker compose -f compose.yaml -f deploy/homeserver/compose.server.yaml)

[[ -f .env ]] || { echo "missing .env (create it with: install -m 600 /dev/null .env)"; exit 1; }
[[ "$(stat -c %a .env 2>/dev/null || stat -f %Lp .env)" == "600" ]] || { echo ".env must have permissions 600"; exit 1; }

value() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- | sed -e 's/[[:space:]]*#.*$//' -e 's/^"//' -e 's/"$//'; }
for key in OPENAI_API_KEY POSTGRES_PASSWORD INGRESS_NETWORK; do
  [[ -n "$(value "$key")" ]] || { echo "missing $key in .env"; exit 1; }
done
[[ "$(value POSTGRES_PASSWORD)" != "emporio" ]] || { echo "set a real POSTGRES_PASSWORD on the server"; exit 1; }
docker network inspect "$(value INGRESS_NETWORK)" >/dev/null || { echo "ingress network $(value INGRESS_NETWORK) not found"; exit 1; }

RELEASE_ID="$(git rev-parse --short HEAD)$(git diff --quiet || echo '-dirty')"
export RELEASE_ID
echo "$RELEASE_ID" > RELEASE
# Persist it in .env so any later `docker compose` command (logs, restart, profiles) uses the same images.
if grep -q '^RELEASE_ID=' .env; then sed -i.bak "s/^RELEASE_ID=.*/RELEASE_ID=${RELEASE_ID}/" .env && rm -f .env.bak; else echo "RELEASE_ID=${RELEASE_ID}" >> .env; fi
chmod 600 .env
echo "deploying release $RELEASE_ID"

mkdir -p data/postgres
"${COMPOSE[@]}" up -d --build --wait

EDGE_PORT="$(value EDGE_PORT)"; EDGE_PORT="${EDGE_PORT:-18082}"
NEIGHBOURS=()
for url in $(value NEIGHBOUR_HEALTH_URLS | tr ',' ' '); do NEIGHBOURS+=(--neighbour "$url"); done
python3 scripts/smoke.py "http://127.0.0.1:${EDGE_PORT}" "${NEIGHBOURS[@]}"
PUBLIC_URL="$(value PUBLIC_URL)"
[[ -z "$PUBLIC_URL" ]] || python3 scripts/smoke.py "$PUBLIC_URL" "${NEIGHBOURS[@]}"
echo "release $RELEASE_ID is up"
