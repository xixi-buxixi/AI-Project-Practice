# -*- coding: utf-8 -*-

import hashlib
import json
import os
import re
import sys

from .cleanup import check_path_allowed
from .config import (
    find_project_root, first_existing_path, get_allowed_paths, get_module_config,
    get_modules_to_run, get_state_dir, load_cycles_json, load_governance_config,
    resolve_config_path, resolve_level, should_verify_integrity,
)
from .security import check_runtime_environment

def get_governance_paths(project_root, config=None):
    config = config or load_governance_config(project_root)
    paths = config.get("paths", {})
    const_path = first_existing_path(project_root, [
        paths.get("constitution"),
        "docs/requirements/constitution.md",
        "constitution.md",
    ])
    trace_path = first_existing_path(project_root, [
        paths.get("traceability_source"),
        "docs/traceability/traceability-source.json",
        "traceability-source.json",
        paths.get("traceability_source_yaml"),
        "docs/traceability/traceability-source.yaml",
        "docs/requirements/traceability-source.yaml",
        "traceability-source.yaml",
    ])
    map_path = first_existing_path(project_root, [
        paths.get("module_map"),
        "MODULE_MAP.md",
        "templates/MODULE_MAP.md",
    ])
    return const_path, trace_path, map_path

def calculate_governance_hash(project_root, config=None):
    const_path, trace_path, map_path = get_governance_paths(project_root, config)

    hash_content = b""
    for path in [const_path, trace_path, map_path]:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            if path == const_path:
                lines = content.splitlines()
                filtered_lines = [l for l in lines if not re.search(r"^\s*sha256_hash\s*:", l)]
                content = "\n".join(filtered_lines)
            hash_content += content.encode("utf-8") + b"\n"

    return hashlib.sha256(hash_content).hexdigest()

def verify_governance_integrity(project_root, config=None):
    const_path, _, _ = get_governance_paths(project_root, config)

    if not os.path.exists(const_path):
        return True, "No constitution.md found, skipping integrity check"

    actual_hash = calculate_governance_hash(project_root, config)
    expected_hash = None
    try:
        with open(const_path, "r", encoding="utf-8") as f:
            for line in f:
                m = re.match(r"^\s*sha256_hash\s*:\s*\"([a-fA-F0-9]{64})\"", line)
                if m:
                    expected_hash = m.group(1)
                    break
    except Exception as e:
        return False, f"Failed to read constitution.md: {str(e)}"

    if not expected_hash:
        return False, "constitution.md lacks a valid sha256_hash. Run 'trace' to sign it."

    if actual_hash != expected_hash:
        return False, f"Governance integrity check failed! Actual: {actual_hash[:8]}, Expected: {expected_hash[:8]}. Run 'trace' to sign it."

    return True, "Governance integrity verified"

def update_constitution_hash(file_path, project_root, config=None):
    if not os.path.exists(file_path):
        return None

    gov_hash = calculate_governance_hash(project_root, config)

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.splitlines()
    hash_line_idx = -1
    for i, line in enumerate(lines):
        if re.search(r"^\s*sha256_hash\s*:", line):
            hash_line_idx = i
            break

    if hash_line_idx != -1:
        m = re.match(r"^(\s*)sha256_hash\s*:", lines[hash_line_idx])
        indent = m.group(1) if m else "  "
        lines[hash_line_idx] = f'{indent}sha256_hash: "{gov_hash}"'
    else:
        lines.append(f'sha256_hash: "{gov_hash}"')

    with open(file_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")

    return gov_hash

def cmd_preflight(args):
    module_name = args.module
    project_root = find_project_root(os.getcwd())
    config = load_governance_config(project_root, getattr(args, "config", None))
    level = resolve_level(args, config)
    state_dir = get_state_dir(project_root)
    cycles_data = load_cycles_json(state_dir)

    checks = []
    status = "pass"
    exit_code = 0

    # 1. Verify Governance Integrity (Enterprise only)
    if should_verify_integrity(level):
        ok, msg = verify_governance_integrity(project_root, config)
        if not ok:
            checks.append({
                "name": "integrity",
                "status": "fail",
                "severity": "P0",
                "summary": "发现治理配置文件完整性校验失败（防篡改触发）！",
                "evidence": [msg]
            })
            status = "blocked"
            exit_code = 3
        else:
            checks.append({
                "name": "integrity",
                "status": "pass",
                "severity": "P3",
                "summary": msg,
                "evidence": []
            })

    if exit_code == 0:
        # Check runtime environment alignment
        env_ok, env_msg = check_runtime_environment(project_root)
        if not env_ok:
            checks.append({
                "name": "env",
                "status": "fail",
                "severity": "P1",
                "summary": "运行环境与项目配置不匹配！",
                "evidence": [env_msg]
            })
            status = "blocked"
            exit_code = 3

    if exit_code == 0:
        modules_to_check = get_modules_to_run(module_name, config, cycles_data)

        # Check guideline document
        for m_name in modules_to_check:
            if not m_name:
                continue
            agents_md_path = os.path.join(project_root, "src", m_name, "agents.md")
            if level == "lite":
                agents_md_path = os.path.join(project_root, "examples", m_name, "REQUIREMENTS.md")
                if not os.path.exists(agents_md_path):
                    agents_md_path = os.path.join(project_root, "REQUIREMENTS.md")

            module_config = get_module_config(config, m_name)
            if module_config.get("agent_contract"):
                agents_md_path = resolve_config_path(project_root, module_config.get("agent_contract"))

            if not os.path.exists(agents_md_path):
                checks.append({
                    "name": "lint",
                    "status": "fail",
                    "severity": "P1",
                    "summary": f"缺少指引规范文件: {os.path.basename(agents_md_path)} 不存在",
                    "evidence": [agents_md_path]
                })
                status = "fail"
                exit_code = 2
            else:
                checks.append({
                    "name": "lint",
                    "status": "pass",
                    "severity": "P3",
                    "summary": f"模块 {m_name} 指引规范已就绪",
                    "evidence": [agents_md_path]
                })

        # Check allowed paths
        allowed_paths = get_allowed_paths(project_root, module_name, config, cycles_data)

        if allowed_paths and exit_code == 0:
            ok, violations = check_path_allowed(project_root, None if module_name == "all" else module_name, allowed_paths)
            if not ok:
                checks.append({
                    "name": "contract",
                    "status": "fail",
                    "severity": "P0",
                    "summary": "发现超出允许修改路径的文件变更",
                    "evidence": violations
                })
                status = "blocked"
                exit_code = 3

    report = {
        "status": status,
        "module": module_name,
        "checks": checks,
        "counters": {
            "attempt_count": cycles_data.get("attempt_count", 0),
            "invalid_build_cycle_count": cycles_data.get("invalid_build_cycle_count", 0),
            "infra_failure_count": cycles_data.get("infra_failure_count", 0)
        },
        "artifacts": {
            "deleted": [],
            "quarantined": [],
            "reports": []
        }
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(exit_code)
