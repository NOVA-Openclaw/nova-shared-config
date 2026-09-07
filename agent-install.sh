#!/bin/bash
# agent-install.sh - Installer for nova-shared-config
#
# Thin caller: the actual deploy logic lives in shared-config/deploy.sh, kept with
# the scripts it deploys. This installer just invokes it (and any future steps).
#
# DEPLOY DIRECTION: this repo is AUTHORITATIVE. /opt/agents/shared-config is the
# DEPLOYED ARTIFACT, not the source. Do not hand-edit /opt/agents/shared-config/*.py
# — edit here, PR, and redeploy via this installer. See shared-config/README.md.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "nova-shared-config installer"

DEPLOY="$SCRIPT_DIR/shared-config/deploy.sh"
if [ -f "$DEPLOY" ]; then
    bash "$DEPLOY"
else
    echo "  WARNING: shared-config/deploy.sh not found; nothing deployed"
fi

echo "done"
exit 0
