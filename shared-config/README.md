# shared-config

Operational scripts that maintain the shared model catalog used across the NOVA
peer ecosystem. Deployed to `/opt/agents/shared-config/` by `agent-install.sh`.

## Authority & drift direction (read this first)

**This repo is authoritative. `/opt/agents/shared-config/` is the deployed
artifact, not the source.**

- Edit scripts **here**, open a PR, merge, then redeploy via `agent-install.sh`
  (`git pull` + installer — the same path that provisions the rest of `/opt`).
- **Do NOT hand-edit `/opt/agents/shared-config/*.py`.** A live-`/opt` edit
  silently forks the source of truth from this repo. The relationship was
  historically inverted (the script lived only in `/opt`, untracked); bringing it
  under version control here fixes that, but only if `/opt` is henceforth treated
  as output.

## Scripts

- **`refresh-model-catalog.py`** — refreshes `/opt/agents/shared-config/models-providers.json`
  from live provider catalogs (OpenRouter public + keyed provider-direct
  `/models` endpoints). Deterministic writer per `GLOBAL/CRON_DESIGN`. Validate-
  then-distribute gate; per-provider count verification.
- **`build-fallback-chains.py`** — constructs `fallback_models` chains per
  `FALLBACK_CHAIN_POLICY`.

## Secrets

- These scripts read provider API keys from the **environment** (`<PROVIDER>_API_KEY`),
  never from embedded literals. Keep it that way — no baked credentials in repo.
- **`models-providers.json` is NOT a repo file.** It carries live `apiKey` values
  and is a deployed-runtime artifact maintained by `refresh-model-catalog.py`.
  The installer never creates or overwrites it and preserves its `640 root:agents`
  permissions. If a repo copy is ever needed for reference, it must be a
  **redacted schema example**, never the live file. See `GLOBAL/SECRETS_HYGIENE`.

## Permissions on deploy

`git` tracks neither owner/group nor fine-grained mode, and these scripts sit
next to a live-key registry, so the installer enforces deploy perms explicitly:

- `refresh-model-catalog.py`, `build-fallback-chains.py` → **`750 root:agents`**
  (owner+group exec, **not** world-readable).
- `models-providers.json` (if present) → **`640 root:agents`**, never overwritten.

Verify post-deploy that live perms match: `stat -c '%A %U:%G' /opt/agents/shared-config/*`.
