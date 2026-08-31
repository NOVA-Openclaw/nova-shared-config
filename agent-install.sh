#!/bin/bash
# agent-install.sh - Installer for nova-scripts
#
# Historically a stub for NOVA-INSTALL.sh compatibility. Now also deploys the
# shared-config operational scripts to /opt/agents/shared-config when run with
# sufficient privilege.
#
# DEPLOY DIRECTION (important): this repo is AUTHORITATIVE. /opt is the DEPLOYED
# ARTIFACT, not the source. Do not hand-edit /opt/agents/shared-config/*.py —
# edit here, PR, and redeploy via this installer. See shared-config/README.md.
#
# PERMISSIONS: git tracks neither owner/group nor fine-grained mode. The scripts
# maintain models-providers.json which carries LIVE API KEYS, so they must be
# deployed non-world-readable (750 root:agents), NOT the repo's default file mode.
# That ownership/mode is enforced HERE, in installer logic — never assumed from
# the repo file mode.
set -euo pipefail

echo "nova-scripts installer"

SHARED_SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/shared-config"
SHARED_DEST_DIR="/opt/agents/shared-config"
SHARED_SCRIPTS=("refresh-model-catalog.py" "build-fallback-chains.py")

deploy_shared_config() {
    # Only attempt if the source dir exists and we can write as root:agents.
    [ -d "$SHARED_SRC_DIR" ] || { echo "  no shared-config/ to deploy; skipping"; return 0; }

    if [ "$(id -u)" -ne 0 ]; then
        echo "  shared-config deploy needs root (to set root:agents 750); re-run with sudo to deploy those scripts"
        return 0
    fi

    install -d -o root -g agents -m 2775 "$SHARED_DEST_DIR"
    for f in "${SHARED_SCRIPTS[@]}"; do
        if [ -f "$SHARED_SRC_DIR/$f" ]; then
            # 750 root:agents — executable by owner+group, NOT world-readable
            # (these scripts sit next to a live-key registry).
            install -o root -g agents -m 0750 "$SHARED_SRC_DIR/$f" "$SHARED_DEST_DIR/$f"
            echo "  deployed $f -> $SHARED_DEST_DIR/$f (750 root:agents)"
        else
            echo "  WARNING: $f not present in repo shared-config/; skipped"
        fi
    done

    # Do NOT create or overwrite models-providers.json here — it carries live API
    # keys and is a deployed-runtime artifact maintained by refresh-model-catalog.py,
    # not a repo file. If it exists, leave its 640 root:agents perms intact.
    if [ -f "$SHARED_DEST_DIR/models-providers.json" ]; then
        chown root:agents "$SHARED_DEST_DIR/models-providers.json"
        chmod 0640 "$SHARED_DEST_DIR/models-providers.json"
        echo "  preserved models-providers.json perms (640 root:agents) — not overwritten"
    fi
}

deploy_shared_config

echo "done"
exit 0
