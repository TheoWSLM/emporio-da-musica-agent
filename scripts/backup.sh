#!/usr/bin/env bash
# Dumps the runtime data (conversations, messages, tickets) — the catalog and policies are rebuilt by
# the ingestion. Output goes to a staging directory, not a real backup destination.
set -euo pipefail
cd "$(dirname "$0")/.."
BACKUP_DIR="${BACKUP_DIR:-/opt/backups/emporio_musica}"
mkdir -p "$BACKUP_DIR"
file="$BACKUP_DIR/runtime-$(date +%Y%m%d-%H%M%S).sql.gz"
docker compose exec -T postgres pg_dump -U emporio -d emporio --data-only \
  -t conversations -t messages -t support_tickets | gzip > "$file"
echo "wrote $file"
