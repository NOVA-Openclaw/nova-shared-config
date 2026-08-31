#!/usr/bin/env bash
# shared-config/deploy.sh — deploy the shared model-catalog scripts to /opt.
#
# Self-contained deploy step: invoked by the repo-root agent-install.sh with a
# single call, so the deploy logic lives with the scripts it deploys rather than
# inside the installer. Runnable standalone too.
#
# DEPLOY DIRECTION: this repo is AUTHORITATIVE. /opt/agents/shared-config is the
# DEPLOYED ARTIFACT, not the source. Do not hand-edit /opt/agents/shared-config/*.py
# — edit here, PR, redeploy. See shared-config/README.md.
#
# PERMISSIONS: git tracks neither owner/group nor fine-grained mode. These scripts
# maintain models-providers.json which carries LIVE API KEYS, so they must deploy
# non-world-readable (750 root:agents), NOT the repo's default file mode. That
# ownership/mode is enforced HERE, never assumed from the repo file mode.
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST_DIR="/opt/agents/shared-config"
SCRIPTS=("refresh-model-catalog.py" "build-fallback-chains.py")

if [ "$(id -u)" -ne 0 ]; then
    echo "  shared-config deploy needs root (to set root:agents 750); skipping (re-run with sudo to deploy)"
    exit 0
fi

install -d -o root -g agents -m 2775 "$DEST_DIR"
for f in "${SCRIPTS[@]}"; do
    if [ -f "$SRC_DIR/$f" ]; then
        # 750 root:agents — owner+group exec, NOT world-readable (next to a live-key registry).
        install -o root -g agents -m 0750 "$SRC_DIR/$f" "$DEST_DIR/$f"
        echo "  deployed $f -> $DEST_DIR/$f (750 root:agents)"
    else
        echo "  WARNING: $f not present in repo shared-config/; skipped"
    fi
done

# Never create/overwrite models-providers.json — it carries live API keys and is a
# deployed-runtime artifact maintained by refresh-model-catalog.py, not a repo file.
# If it exists, preserve its 640 root:agents perms.
if [ -f "$DEST_DIR/models-providers.json" ]; then
    chown root:agents "$DEST_DIR/models-providers.json"
    chmod 0640 "$DEST_DIR/models-providers.json"
    echo "  preserved models-providers.json perms (640 root:agents) — not overwritten"
fi
