#!/usr/bin/env python3
# DO NOT EDIT — installed/managed by nova-workspace:scripts/lib/nova_op_env.py
# Last synced: 2026-11-20
# Local changes will be overwritten by the owning repo's installer.
# To re-vendor: see nova_op_env.py.VENDORED.json and update its sha256.
"""Load environment variables from the 1Password item map via nova-op.

Reads ~/.openclaw/scripts/nova-op-item-map.json and resolves each requested
variable via nova-op by item ID. Vault IDs come from the map, not from any
hardcoded per-script value.

Example:
    from lib.nova_op_env import nova_op_resolve, nova_op_load_env
    api_key = nova_op_resolve("OPENPROJECT_API_KEY")
    # or load several at once
    nova_op_load_env(["OPENPROJECT_API_KEY", "ELEVENLABS_API_KEY"])
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

DEFAULT_ITEM_MAP = Path.home() / ".openclaw" / "scripts" / "nova-op-item-map.json"
DEFAULT_NOVA_OP = Path.home() / ".local" / "bin" / "nova-op"


class NovaOpError(RuntimeError):
    """Resolution failed for a variable listed in the item map."""


class MissingFromMapError(RuntimeError):
    """Variable has no entry in the item map (expected for optional providers)."""


def _nova_op_path() -> str:
    return os.environ.get("NOVA_OP", str(DEFAULT_NOVA_OP))


def _item_map_path() -> Path:
    return Path(os.environ.get("NOVA_OP_ITEM_MAP", DEFAULT_ITEM_MAP))


def _load_map(config_path: Path | None = None) -> dict[str, Any]:
    path = config_path or _item_map_path()
    if not path.exists():
        raise MissingFromMapError(f"nova-op-env: item map not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def has_map_entry(var: str, config_path: Path | None = None) -> bool:
    """Return True if the variable has a complete entry in the item map."""
    try:
        config = _load_map(config_path)
    except MissingFromMapError:
        return False
    entry = config.get(var)
    if not isinstance(entry, dict):
        return False
    return bool(
        entry.get("item") and entry.get("field") and entry.get("vault")
    )


def nova_op_resolve(
    var: str,
    config_path: Path | None = None,
    nova_op: str | None = None,
) -> str:
    """Resolve a single environment variable via nova-op.

    Looks up the variable name in the item map, then calls
    ``nova-op item get <item> --vault <vault> --field <field> --reveal``.

    - If the variable is already set in the environment, that value wins.
    - If the variable has no entry in the item map, raises MissingFromMapError.
    - If the variable is mapped but nova-op fails, raises NovaOpError.

    Never returns an empty string.
    """
    existing = os.environ.get(var, "").strip()
    if existing:
        return existing

    config = _load_map(config_path)
    entry = config.get(var)
    if not isinstance(entry, dict):
        raise MissingFromMapError(f"nova-op-env: incomplete map entry for {var}")

    item = str(entry.get("item") or "").strip()
    field = str(entry.get("field") or "").strip()
    vault = str(entry.get("vault") or "").strip()

    if not item or not field or not vault:
        raise MissingFromMapError(f"nova-op-env: incomplete map entry for {var}")

    if item == "REPLACE_WITH_ITEM_ID" or vault == "REPLACE_WITH_VAULT_ID":
        raise NovaOpError(
            f"nova-op-env: {var} still contains placeholder values in the item map"
        )

    cmd = [
        nova_op or _nova_op_path(),
        "item",
        "get",
        item,
        "--vault",
        vault,
        "--field",
        field,
        "--reveal",
    ]
    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.CalledProcessError as exc:
        raise NovaOpError(
            f"nova-op-env: failed to resolve {var} (item={item} field={field} vault={vault}): "
            f"{exc.stderr.strip()}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise NovaOpError(
            f"nova-op-env: timed out resolving {var} (item={item} field={field} vault={vault})"
        ) from exc

    value = result.stdout.strip()
    if not value:
        raise NovaOpError(
            f"nova-op-env: resolved empty value for {var} (item={item} field={field} vault={vault})"
        )
    return value


def nova_op_load_env(
    vars: list[str],
    config_path: Path | None = None,
    nova_op: str | None = None,
) -> dict[str, str]:
    """Resolve and export multiple environment variables.

    Variables already set in the environment are left untouched, allowing
    callers to pre-inject values (e.g. from a parent plugin).

    Returns a mapping of variable names to resolved values. Raises
    RuntimeError if any resolution fails.
    """
    result: dict[str, str] = {}
    errors: list[str] = []
    for var in vars:
        existing = os.environ.get(var, "").strip()
        if existing:
            result[var] = existing
            continue
        try:
            value = nova_op_resolve(var, config_path, nova_op)
        except RuntimeError as exc:
            errors.append(str(exc))
            continue
        os.environ[var] = value
        result[var] = value

    if errors:
        raise RuntimeError("; ".join(errors))
    return result


def resolve_first_present(
    vars: list[str],
    config_path: Path | None = None,
    nova_op: str | None = None,
) -> tuple[str | None, list[str]]:
    """Resolve the first variable in the list that is mapped in the item map.

    Returns (value, list_of_attempted_vars).
    - If none of the variables is mapped, returns (None, attempted).
    - If a mapped variable fails to resolve, raises NovaOpError (loud failure).
    - Existing environment values win without calling nova-op.
    """
    attempted: list[str] = []
    for var in vars:
        if var in os.environ and os.environ[var].strip():
            return os.environ[var].strip(), attempted + [var]
        if has_map_entry(var, config_path):
            return nova_op_resolve(var, config_path, nova_op), attempted + [var]
        attempted.append(var)
    return None, attempted
