#!/usr/bin/env python3
"""
fallback-chain-audit.py — validate agents-table fallback_models chains
against UNIVERSAL/FALLBACK_CHAIN_POLICY (I)ruid ruling 2026-08-29).

Reads model ids ONLY from the shared registry
(/opt/agents/shared-config/models-providers.json). NEVER dump a raw
provider block — it contains live apiKey values.

--------------------------------------------------------------------------
CRITICAL VALIDATOR TRAP (demonstrated live 2026-09-01, graybeard self-audit)
--------------------------------------------------------------------------
A naive validator that strict-matches the raw registry `id` will flag EVERY
dotted direct-anthropic rung as broken and "correct" it into breakage.

  - Registry stores DIRECT anthropic ids HYPHENATED:  anthropic/claude-sonnet-4-6
  - Chains/wire/alias layer accept BOTH dotted and hyphenated for direct anthropic:
        anthropic/claude-sonnet-4.6  AND  anthropic/claude-sonnet-4-6  both resolve
  - OpenRouter anthropic MIRRORS are DOTTED:  openrouter/anthropic/claude-sonnet-4.6

On pass one this validator (in strict mode) produced 74 false positives across
27 active agents. The ACCEPT set below adds the dotted variant of every
hyphenated direct-anthropic id so the audit does not mass-rewrite correct chains.

Other traps encoded here:
  - chain[0] == primary (or its OR mirror, "exclude-primary" convention) is VALID.
  - Filter status='active' — peer rows (graybeard/newhart/victoria) carry NULL
    model config by design; do NOT groom them.
  - OR-only lead rung is legitimate when no direct partner exists in the registry
    (e.g. openrouter/moonshotai/kimi-k3 has no direct moonshot/kimi-k3).
  - ollama/* tails are unpaired by design and must sit at the chain end.
--------------------------------------------------------------------------

Usage:  python3 fallback-chain-audit.py [--db nova_memory] [--user graybeard]
Exit 0 = all active chains conform; exit 1 = problems found.
"""
import getpass
import os
import subprocess
import sys

REGISTRY = "/opt/agents/shared-config/models-providers.json"


def load_registry():
    out = subprocess.check_output(
        ["jq", "-r",
         'to_entries[] | .key as $p | (.value.models // [])[] | "\\($p)/\\(.id)"',
         REGISTRY], text=True)
    return set(l.strip() for l in out.splitlines() if l.strip())


def build_accept(reg):
    """Registry ids plus dotted variants of hyphenated direct-anthropic ids."""
    accept = set(reg)
    for m in list(reg):
        if m.startswith("anthropic/"):
            parts = m.split("-")
            # e.g. anthropic/claude-sonnet-4-6 -> ...-4.6
            if len(parts) >= 2 and parts[-1].isdigit() and parts[-2].isdigit():
                accept.add("-".join(parts[:-2]) + "-" + parts[-2] + "." + parts[-1])
    return accept


def load_rows(db, user):
    out = subprocess.check_output(
        ["psql", "-U", user, "-d", db, "-h", "localhost", "-At", "-F", "\t", "-c",
         "SELECT name, model, array_to_string(fallback_models, ',') FROM agents "
         "WHERE status='active' AND fallback_models IS NOT NULL "
         "AND array_length(fallback_models,1) > 0 ORDER BY name;"],
        text=True)
    rows = []
    for line in out.splitlines():
        if not line.strip():
            continue
        name, primary, csv = line.split("\t")
        chain = [c.strip() for c in csv.split(",") if c.strip()]
        rows.append((name, primary, chain))
    return rows


def is_or(m):
    return m.startswith("openrouter/")


def is_ollama(m):
    return m.startswith("ollama/")


def direct_partner_set(or_model):
    """Direct-provider candidate(s) for an OpenRouter mirror. Prefix quirks:
    openrouter/x-ai/ -> xai/ ; openrouter/moonshotai/ -> moonshot/ ;
    anthropic accepts BOTH dotted and hyphenated."""
    body = or_model[len("openrouter/"):]
    out = set()
    if body.startswith("anthropic/"):
        mdl = body.split("/", 1)[1]
        out.add("anthropic/" + mdl)                   # dotted
        out.add("anthropic/" + mdl.replace(".", "-"))  # hyphenated
    elif body.startswith("x-ai/"):
        out.add("xai/" + body.split("/", 1)[1])
    elif body.startswith("moonshotai/"):
        out.add("moonshot/" + body.split("/", 1)[1])
    else:
        out.add(body)  # google / deepseek share the prefix
    return out


def audit(rows, reg, accept):
    problems = []
    for name, primary, chain in rows:
        # Rule: every rung must be an accepted id
        for m in chain:
            if m not in accept:
                problems.append(f"{name}: rung not in registry (dotted+hyphenated anthropic accepted): {m}")

        # Pairing: OR rung preceded by its direct partner, unless legitimate lead
        for i, m in enumerate(chain):
            if is_ollama(m) or not is_or(m):
                continue
            dps = direct_partner_set(m)
            direct_exists = any(d in reg for d in dps)
            prev = chain[i - 1] if i > 0 else None
            paired = prev in dps if prev else False
            if direct_exists and not paired and i != 0:
                # i==0 with a direct partner existing = exclude-primary lead mirror (VALID)
                problems.append(f"{name}: OR rung {m} not preceded by direct partner (prev={prev})")

        # ollama tails must sit at the end
        for i, m in enumerate(chain):
            if is_ollama(m) and any(not is_ollama(x) for x in chain[i + 1:]):
                problems.append(f"{name}: ollama rung {m} not at tail")
    return problems


def main():
    # Default to the invoking identity so the script works for any agent with a
    # .pgpass, not just a hardcoded user. --user remains an explicit override.
    # (A hardcoded default user silently "works" only for the matching identity
    # and fails exit>=2 for everyone else — that masks connection errors as
    # chain defects under an alert-on-nonzero cron. See lesson on this.)
    db = "nova_memory"
    user = os.environ.get("PGUSER") or getpass.getuser()
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--db" and i + 1 < len(args):
            db = args[i + 1]
        if a == "--user" and i + 1 < len(args):
            user = args[i + 1]

    reg = load_registry()
    accept = build_accept(reg)
    rows = load_rows(db, user)
    problems = audit(rows, reg, accept)

    print(f"Registry: {len(reg)} ids | accept-set: {len(accept)} | agents audited: {len(rows)}")
    if problems:
        print("\n=== PROBLEMS ===")
        for p in problems:
            print(" -", p)
        sys.exit(1)
    print(f"\nNO PROBLEMS — all {len(rows)} active chains conform to all five rules.")
    sys.exit(0)


if __name__ == "__main__":
    main()
