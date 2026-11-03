# Operations runbook (home server)

The public demo runs on a home server next to other applications and is published through the
**Cloudflare tunnel connector that already runs there**. This app never starts its own connector: its
edge joins the existing ingress network and the tunnel gets one more public hostname.

## Layout

```
/opt/apps/emporio_musica/        # git clone of this repository (code at the root)
├── .env                         # chmod 600, server only — never committed
├── data/postgres/               # database volume
├── deploy/homeserver/           # this runbook, audit, compose override
└── scripts/                     # implantar.sh, smoke.py, backup.sh
```

## Server-only `.env` entries

Besides the variables of `.env.example`:

| Variable | Meaning |
|---|---|
| `POSTGRES_PASSWORD` | A real password (the deploy refuses the local default). |
| `INGRESS_NETWORK` | Name of the existing Docker network the tunnel connector is attached to. |
| `EDGE_PORT` | Local port for checks on `127.0.0.1` (pick one not used by the other apps). |
| `PUBLIC_URL` | Public hostname, smoke-tested after each deploy. |
| `NEIGHBOUR_HEALTH_URLS` | Comma-separated URLs of the other apps that must still answer 200 after the deploy. |
| `COMPOSE_PROFILES` | `quick-tunnel` to publish through a Cloudflare Quick Tunnel (random `trycloudflare.com` URL, no domain needed). |
| `RELEASE_ID` | Written by `scripts/implantar.sh` (commit of the deployed checkout). |

## First deploy

1. `git clone https://github.com/TheoWSLM/emporio-da-musica-agent.git /opt/apps/emporio_musica`
2. `cd /opt/apps/emporio_musica && install -m 600 /dev/null .env` and fill it in.
3. `scripts/implantar.sh` — validates `.env` (permissions, required keys, ingress network), tags the images
   with the commit (`RELEASE_ID`), starts `postgres → migrate → ingest → api → edge` with
   `docker compose -f compose.yaml -f deploy/homeserver/compose.server.yaml up -d --build --wait` and runs
   `scripts/smoke.py` locally, publicly and against the neighbour apps. It never restarts Docker, never
   prunes and never touches other containers.
4. Publish it, either way:
   - **With a domain:** in the Cloudflare Zero Trust dashboard, add a public hostname to the existing tunnel:
     `<hostname>` → `http://emporio-musica-caddy:80`. The connector is not restarted.
   - **Without a domain (current demo):** set `COMPOSE_PROFILES=quick-tunnel`; the `quick-tunnel` container
     prints a random `https://<words>.trycloudflare.com` URL (`docker compose -f compose.yaml -f
     deploy/homeserver/compose.server.yaml logs quick-tunnel | grep trycloudflare`). The URL changes if that
     container is recreated (e.g. after a host reboot).
5. `python3 scripts/smoke.py https://<hostname> --check-rate-limit 20` once, to confirm the 429.

## Operate

- Status: `docker compose ps` · logs: `docker compose logs -f api` (Caddy access logs carry no URI or headers).
- The healthchecks mark a stuck container as `unhealthy`; `restart: unless-stopped` handles crashes.

## Update / roll back

- Update: `git fetch --tags && git checkout <tag> && scripts/implantar.sh`.
- Roll back: check out the previous tag and run `scripts/implantar.sh` again (images are tagged per commit).
- The version delivered for the case is tagged `v1.0-submission`.

## Backup

`scripts/backup.sh` dumps the runtime tables (conversations, messages, tickets) to
`/opt/backups/emporio_musica/` — a staging area, not a real backup. Everything else is rebuilt by `ingest`.

## Decommission

`docker compose -f compose.yaml -f deploy/homeserver/compose.server.yaml down`, remove the public hostname
from the tunnel (the other routes stay untouched), revoke the demo API keys, delete `data/`.

## Why migrations run on every start

Other apps on the server run migrations as a manual step. Here `migrate` and `ingest` are idempotent and
there is a single API replica, so running them on each `up` is safe and keeps the evaluator's local
`make up` free of manual steps.
