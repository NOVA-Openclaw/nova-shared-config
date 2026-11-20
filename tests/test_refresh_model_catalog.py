#!/usr/bin/env python3
"""Tests for shared-config/refresh-model-catalog.py key resolution behavior."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "shared-config" / "refresh-model-catalog.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("refresh_model_catalog", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_no_plaintext_or_env_only_patterns() -> None:
    """Static guard: no .secrets reads or bare os.environ.get API_KEY patterns."""
    text = SCRIPT_PATH.read_text()
    assert ".secrets" not in text
    assert "1password-master.gpg" not in text
    assert "op signin" not in text
    assert "os.environ.get" not in text, "use nova-op resolution instead of os.environ.get"
    assert "os.getenv" not in text


def test_provider_with_no_mapped_key_is_skipped(monkeypatch) -> None:
    """A provider whose candidate env vars are not in the map is skipped."""
    module = load_script_module()
    with tempfile.TemporaryDirectory() as tmp:
        item_map = Path(tmp) / "map.json"
        item_map.write_text("{}")
        monkeypatch.setenv("NOVA_OP_ITEM_MAP", str(item_map))
        monkeypatch.delenv("XAI_API_KEY", raising=False)

        ids, status = module.fetch_direct("xai", "https://example.com", module.DIRECT_PROVIDERS["xai"])
        assert status == "no_key"
        assert ids == []


def test_provider_with_mapped_key_is_resolved(monkeypatch) -> None:
    """A provider with a mapped key uses it to fetch."""
    module = load_script_module()
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        op_bin = home / ".local/bin/nova-op"
        op_bin.parent.mkdir(parents=True)
        op_bin.write_text(
            '#!/usr/bin/env bash\n'
            'if [[ "$1" == "item" && "$2" == "get" ]]; then echo "resolved-key"; exit 0; fi\n'
            'exit 1\n'
        )
        op_bin.chmod(0o755)

        item_map = home / ".openclaw/scripts/nova-op-item-map.json"
        item_map.parent.mkdir(parents=True)
        item_map.write_text(json.dumps({
            "XAI_API_KEY": {"vault": "v", "item": "i", "field": "API Key"}
        }))

        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("NOVA_OP", str(op_bin))
        monkeypatch.setenv("NOVA_OP_ITEM_MAP", str(item_map))
        monkeypatch.delenv("XAI_API_KEY", raising=False)

        captured: dict[str, str] = {}

        def fake_urlopen(req, timeout=None):
            captured["authorization"] = req.get_header("Authorization")
            class Resp:
                def read(self): return json.dumps({"data": [{"id": "x-ai/grok-test"}]}).encode()
                def __enter__(self): return self
                def __exit__(self, *args): return False
            return Resp()

        monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

        ids, status = module.fetch_direct("xai", "https://example.com", module.DIRECT_PROVIDERS["xai"])
        assert status == "ok"
        assert ids == ["x-ai/grok-test"]
        assert captured["authorization"] == "Bearer resolved-key"


def test_provider_with_failed_resolution_is_loud_error(monkeypatch) -> None:
    """A mapped key that fails to resolve produces an error status."""
    module = load_script_module()
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        op_bin = home / ".local/bin/nova-op"
        op_bin.parent.mkdir(parents=True)
        op_bin.write_text(
            '#!/usr/bin/env bash\necho "op error" >&2\nexit 1\n'
        )
        op_bin.chmod(0o755)

        item_map = home / ".openclaw/scripts/nova-op-item-map.json"
        item_map.parent.mkdir(parents=True)
        item_map.write_text(json.dumps({
            "XAI_API_KEY": {"vault": "v", "item": "i", "field": "API Key"}
        }))

        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("NOVA_OP", str(op_bin))
        monkeypatch.setenv("NOVA_OP_ITEM_MAP", str(item_map))
        monkeypatch.delenv("XAI_API_KEY", raising=False)

        ids, status = module.fetch_direct("xai", "https://example.com", module.DIRECT_PROVIDERS["xai"])
        assert status == "error"
        assert ids == []


def test_env_var_wins_without_calling_nova_op(monkeypatch) -> None:
    """An already-set env var is used directly, no nova-op call made."""
    module = load_script_module()
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        op_bin = home / ".local/bin/nova-op"
        op_bin.parent.mkdir(parents=True)
        # This op would fail if called; env wins, so it should not be called.
        op_bin.write_text('#!/usr/bin/env bash\nexit 1\n')
        op_bin.chmod(0o755)

        item_map = home / ".openclaw/scripts/nova-op-item-map.json"
        item_map.parent.mkdir(parents=True)
        item_map.write_text("{}")

        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("NOVA_OP", str(op_bin))
        monkeypatch.setenv("NOVA_OP_ITEM_MAP", str(item_map))
        monkeypatch.setenv("XAI_API_KEY", "env-key")

        captured: dict[str, str] = {}

        def fake_urlopen(req, timeout=None):
            captured["authorization"] = req.get_header("Authorization")
            class Resp:
                def read(self): return json.dumps({"data": []}).encode()
                def __enter__(self): return self
                def __exit__(self, *args): return False
            return Resp()

        monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

        ids, status = module.fetch_direct("xai", "https://example.com", module.DIRECT_PROVIDERS["xai"])
        assert status == "ok"
        assert captured["authorization"] == "Bearer env-key"


def test_custom_nova_op_binary_is_used(monkeypatch) -> None:
    """The helper must honour the NOVA_OP env var so a wrapper can be used."""
    module = load_script_module()
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        custom_op = home / "custom-nova-op"
        custom_op.write_text(
            '#!/usr/bin/env bash\n'
            'if [[ "$1" == "item" && "$2" == "get" ]]; then echo "custom-key"; exit 0; fi\n'
            'exit 1\n'
        )
        custom_op.chmod(0o755)

        # Default nova-op path must NOT be used; ensure it does not exist.
        default_op = home / ".local/bin/nova-op"
        default_op.parent.mkdir(parents=True)
        default_op.write_text('#!/usr/bin/env bash\necho "default-op-called" >&2\nexit 1\n')
        default_op.chmod(0o755)

        item_map = home / ".openclaw/scripts/nova-op-item-map.json"
        item_map.parent.mkdir(parents=True)
        item_map.write_text(json.dumps({
            "XAI_API_KEY": {"vault": "v", "item": "i", "field": "API Key"}
        }))

        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("NOVA_OP", str(custom_op))
        monkeypatch.setenv("NOVA_OP_ITEM_MAP", str(item_map))
        monkeypatch.delenv("XAI_API_KEY", raising=False)

        captured: dict[str, str] = {}

        def fake_urlopen(req, timeout=None):
            captured["authorization"] = req.get_header("Authorization")
            class Resp:
                def read(self): return json.dumps({"data": []}).encode()
                def __enter__(self): return self
                def __exit__(self, *args): return False
            return Resp()

        monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

        ids, status = module.fetch_direct("xai", "https://example.com", module.DIRECT_PROVIDERS["xai"])
        assert status == "ok"
        assert captured["authorization"] == "Bearer custom-key"


def test_vendored_helper_matches_pinned_hash() -> None:
    """Vendored nova_op_env.py must match the pinned hash in VENDORED.json."""
    import hashlib

    file_path = REPO_ROOT / "shared-config" / "lib" / "nova_op_env.py"
    meta_file = REPO_ROOT / "shared-config" / "lib" / "nova_op_env.py.VENDORED.json"
    assert file_path.exists()
    assert meta_file.exists(), f"missing {meta_file}"

    meta = json.loads(meta_file.read_text())
    actual_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
    assert meta["sha256"] == actual_hash, (
        f"nova_op_env.py hash mismatch: expected {meta['sha256']}, got {actual_hash}"
    )
    assert meta["source_repo"] == "NOVA-Openclaw/nova-workspace"
    assert meta["source_path"] == "scripts/lib/nova_op_env.py"
    assert "source_commit" in meta
    assert "revendor" in meta
