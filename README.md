# AI-Project-Practice

> A configuration-driven governance toolchain for AI-assisted software development. It enforces quality gates (syntax, tests, security), path boundaries, and traceability through pre/post hooks — with three tunable strictness levels.

## What It Does

The core engine ([hooks/hookctl.py](hooks/hookctl.py)) provides four governance commands that wrap any project's build loop:

| Command | Purpose |
|---|---|
| `preflight` | Gate before work: verify environment, guideline docs, path boundaries, governance integrity |
| `finalize` | Gate after work: clean temp files, quarantine artifacts, run syntax/lint/tests |
| `security` | Static scan for hardcoded secrets, private keys, and unignored `.env` files |
| `trace` | Generate the requirement→code→test traceability matrix and sign the governance hash |

It auto-detects and validates **Python, Node, Go, Rust, and Java** via pluggable language adapters.

## Governance Levels

Set `project_level` in [.governance.yaml](.governance.yaml), or override per-run with `--level`:

| Level | Path boundary | Syntax/Test | Security scan | Traceability | Integrity hash |
|---|---|---|---|---|---|
| `lite` | ✗ | ✓ | ✓ | ✗ | ✗ |
| `standard` (default) | ✓ | ✓ | ✓ | ✗ | ✗ |
| `enterprise` | ✓ | ✓ | ✓ (stricter) | ✓ | ✓ |

## Quick Start

```bash
# 1. Install the only runtime dependency
pip install -r requirements.txt

# 2. Run the governance commands from your project root
python hooks/hookctl.py security
python hooks/hookctl.py preflight --module all --level standard
python hooks/hookctl.py finalize  --module all --level lite
python hooks/hookctl.py trace

# 3. (Optional) Install a git pre-commit hook that runs preflight + finalize
python hooks/hookctl.py install-git-hook
```

## Repository Layout

```
hooks/            Governance engine (hookctl.py) + thin entrypoints
templates/        Document templates (PRD, MODULE_MAP, contracts, tasks)
examples/         lite_project — a runnable Lite-level demo
tests/            unittest suite for the engine
.agents/          AI workflow skill + reference docs (progressive disclosure)
.governance.yaml  Project-level governance config (level, modules, commands)
AI_RULES_SUMMARY.md  Default entry point for the AI agent each turn
```

## Configuration

All behavior is driven by [.governance.yaml](.governance.yaml) — modules, paths, languages, and per-language lint/test commands. Adding a new tech stack or custom runner means editing config, not the engine. See [AI_RULES_SUMMARY.md](AI_RULES_SUMMARY.md) for the full intake rules.

## Testing

```bash
cd tests && python -m unittest test_hookctl -v
```

## Requirements

- Python 3.9+
- PyYAML (declared in [requirements.txt](requirements.txt))
- Git (the cleanup, path-boundary, and security gates shell out to `git`)
