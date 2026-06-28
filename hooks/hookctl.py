#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from governance.adapters import (
    GoAdapter,
    JavaAdapter,
    LanguageAdapter,
    NodeAdapter,
    PythonAdapter,
    RustAdapter,
    build_language_adapter,
    cmd_finalize,
    detect_language,
    detect_languages,
    get_language_adapter,
    get_language_adapters,
    run_check_commands,
)
from governance.cleanup import (
    check_path_allowed,
    cmd_install_git_hook,
    is_binary_file,
    is_hook_managed_state_path,
    parse_git_status_entries,
    perform_cleanup,
)
from governance.config import (
    CLEANUP_WHITELIST,
    DEFAULT_GOVERNANCE_CONFIG,
    LANGUAGE_ORDER,
    PROJECT_LEVELS,
    commands_to_list,
    deep_merge,
    extract_verification_command,
    find_project_root,
    first_existing_path,
    get_allowed_paths,
    get_configured_command,
    get_module_config,
    get_module_dir,
    get_module_paths,
    get_modules_to_run,
    get_quarantine_dir,
    get_state_dir,
    load_cycles_json,
    load_governance_config,
    parse_verification_cmd,
    read_structured_file,
    resolve_config_path,
    resolve_level,
    run_cmd,
    save_cycles_json,
    shannon_entropy,
    should_verify_integrity,
    strip_command_markup,
    unique_preserve_order,
)
from governance.integrity import (
    calculate_governance_hash,
    cmd_preflight,
    get_governance_paths,
    update_constitution_hash,
    verify_governance_integrity,
)
from governance.security import (
    check_runtime_environment,
    cmd_security,
    is_test_fixture_path,
    run_security_scan,
    should_ignore_secret_match,
)
from governance.traceability import (
    cmd_trace,
    generate_traceability_md,
    normalize_traceability_requirement,
    parse_traceability_source,
    parse_yaml_traceability,
)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Hook Control Tool (hookctl) for AI Project Build Process"
    )
    subparsers = parser.add_subparsers(dest="action", required=True, help="Action to perform")

    parser_pre = subparsers.add_parser("preflight", help="Run preflight checks before launching Agent")
    parser_pre.add_argument("--module", required=True, help="Module name to run checks on")
    parser_pre.add_argument("--lite", action="store_true", help="Lite mode")
    parser_pre.add_argument("--level", choices=sorted(PROJECT_LEVELS), help="Governance level")
    parser_pre.add_argument("--config", help="Path to governance config file")

    parser_fin = subparsers.add_parser("finalize", help="Run finalize checks and cleanup after Agent run")
    parser_fin.add_argument("--module", required=True, help="Module name to run checks on")
    parser_fin.add_argument("--lite", action="store_true", help="Lite mode")
    parser_fin.add_argument("--level", choices=sorted(PROJECT_LEVELS), help="Governance level")
    parser_fin.add_argument("--config", help="Path to governance config file")
    parser_fin.add_argument("--test-command", help="Override verification command for this finalize run")

    parser_tr = subparsers.add_parser("trace", help="Generate/update traceability matrix and update constitution hash")
    parser_tr.add_argument("--source", help="Path to traceability-source.json or traceability-source.yaml")
    parser_tr.add_argument("--config", help="Path to governance config file")

    parser_sec = subparsers.add_parser("security", help="Run static security scan for secrets")
    parser_sec.add_argument("--module", help="Limit scan to specific module")
    parser_sec.add_argument("--config", help="Path to governance config file")

    subparsers.add_parser("install-git-hook", help="Install local Git pre-commit hook")
    return parser


def main():
    args = build_parser().parse_args()
    commands = {
        "preflight": cmd_preflight,
        "finalize": cmd_finalize,
        "trace": cmd_trace,
        "security": cmd_security,
        "install-git-hook": cmd_install_git_hook,
    }
    commands[args.action](args)


if __name__ == "__main__":
    main()
