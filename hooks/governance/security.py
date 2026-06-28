# -*- coding: utf-8 -*-

import json
import os
import re
import sys

from .config import find_project_root, get_module_paths, load_governance_config, run_cmd, shannon_entropy

def is_test_fixture_path(rel_path):
    norm = os.path.normpath(rel_path).replace("\\", "/").lower()
    parts = norm.split("/")
    return any(part in ["test", "tests", "__tests__", "fixtures", "fixture", "mock", "mocks"] for part in parts)

def should_ignore_secret_match(line, key, value, quote, rel_path, config):
    security = (config or {}).get("security", {})
    if security.get("allow_nosec", True) and ("# nosec" in line or "// nosec" in line):
        return True
    if security.get("allow_test_fixtures", True) and is_test_fixture_path(rel_path):
        return True

    normalized_value = (value or "").strip().strip("'\"")
    if not normalized_value:
        return True
    if normalized_value in ["''", '""']:
        return True

    lowered = normalized_value.lower()
    if any(term in lowered for term in security.get("placeholder_terms", [])):
        return True

    if not quote and re.match(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)+$", normalized_value):
        return True

    entropy_threshold = float(security.get("entropy_threshold", 3.5))
    return shannon_entropy(normalized_value) < entropy_threshold

def run_security_scan(project_root, module_name=None, config=None):
    if isinstance(module_name, dict) and config is None:
        config = module_name
        module_name = None
    config = config or load_governance_config(project_root)
    findings = []

    secret_pat = re.compile(
        r"(?<![A-Za-z0-9_])(api_key|apikey|secret_key|private_key|token|passwd|password|client_secret|access_key|secret_access_key|auth_token|jwt|api_secret|session_token|db_password|database_url|connection_string|bearer)(?![A-Za-z0-9_])\s*[:=]\s*(?:(['\"])([^'\"]{8,})\2|([A-Za-z0-9_\-\.\~\/\+=:]{10,}))",
        re.IGNORECASE
    )
    private_key_pat = re.compile(r"-----BEGIN\s+([A-Z0-9_\s]+)?PRIVATE\s+KEY-----")

    files_to_scan = []

    for filename in os.listdir(project_root):
        file_path = os.path.join(project_root, filename)
        if os.path.isfile(file_path) and (filename == ".env" or filename.startswith(".env.")):
            files_to_scan.append(file_path)

    if module_name:
        target_dirs = get_module_paths(project_root, module_name, config)
    else:
        target_dirs = [
            os.path.join(project_root, "src"),
            os.path.join(project_root, "examples"),
            project_root
        ]

    for target_dir in target_dirs:
        if not os.path.exists(target_dir):
            continue
        for root, dirs, files in os.walk(target_dir):
            excluded_dirs = set(config.get("security", {}).get("excluded_dirs", []))
            dirs[:] = [d for d in dirs if d not in excluded_dirs]

            for file in files:
                file_path = os.path.join(root, file)
                filename = os.path.basename(file_path)
                _, ext = os.path.splitext(filename)

                if ext.lower() in [".py", ".js", ".ts", ".go", ".rs", ".java", ".json", ".yaml", ".yml", ".md", ".txt", ".sh", ".properties", ".pem", ".key"] or \
                   filename == ".env" or \
                   filename.startswith(".env."):
                    if file_path not in files_to_scan:
                        files_to_scan.append(file_path)

    for file_path in files_to_scan:
        filename = os.path.basename(file_path)
        _, ext = os.path.splitext(filename)
        rel_path = os.path.relpath(file_path, project_root)

        is_ignored = False
        ret_ignore, _, _ = run_cmd(["git", "check-ignore", file_path], cwd=project_root)
        if ret_ignore == 0:
            is_ignored = True

        if not is_ignored:
            if filename == ".env" or (filename.startswith(".env.") and not any(ph in filename.lower() for ph in ["example", "sample", "template", "default"])):
                findings.append({
                    "file": rel_path,
                    "line": 1,
                    "type": "unignored_env",
                    "summary": f"敏感配置文件 {filename} 未在 .gitignore 中忽略，存在泄漏风险！"
                })
            elif ext.lower() in [".pem", ".key"]:
                findings.append({
                    "file": rel_path,
                    "line": 1,
                    "type": "unignored_private_key_file",
                    "summary": f"私钥/证书文件 {filename} 未在 .gitignore 中忽略，存在泄漏风险！"
                })

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for line_num, line in enumerate(f, 1):
                    m = secret_pat.search(line)
                    if m:
                        val = m.group(3) or m.group(4) or ""
                        quote = m.group(2)
                        key = m.group(1)
                        if not should_ignore_secret_match(line, key, val, quote, rel_path, config):
                            findings.append({
                                "file": rel_path,
                                "line": line_num,
                                "type": "hardcoded_secret",
                                "summary": f"发现疑似硬编码凭证：{key} = '{val[:3]}...{val[-3:] if len(val) > 6 else ''}'"
                            })
                    if private_key_pat.search(line):
                        findings.append({
                            "file": rel_path,
                            "line": line_num,
                            "type": "private_key_block",
                            "summary": "发现疑似硬编码私钥块 (Private Key Block)"
                        })
        except Exception:
            pass

    return findings

def check_runtime_environment(project_root):
    agent_path = os.path.join(project_root, "agent.md")
    if not os.path.exists(agent_path):
        agent_path = os.path.join(project_root, "templates", "agent.md")
        if not os.path.exists(agent_path):
            return True, "No agent.md found, skipping environment check."

    try:
        with open(agent_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception as e:
        return True, f"Failed to read agent.md: {str(e)}"

    type_match = re.search(r"环境类型\s*\(Type\)\s*:\s*([^\r\n\*\-\[\]]+)", content, re.IGNORECASE)
    name_match = re.search(r"名称/版本\s*\(Name/Version\)\s*:\s*([^\r\n\*\-\[\]]+)", content, re.IGNORECASE)
    prefix_match = re.search(r"解释器/执行命令前缀\s*\(Path/Prefix\)\s*:\s*`?([^\r\n`]+)`?", content, re.IGNORECASE)

    if not type_match:
        return True, "No environment type declared in agent.md, skipping environment check."

    env_type = type_match.group(1).strip()
    env_name = name_match.group(1).strip() if name_match else ""
    env_prefix = prefix_match.group(1).strip() if prefix_match else ""

    # Check if the parsed environment type contains template placeholders
    if "/" in env_type or "[" in env_type or "例如" in env_type or env_type.lower() in ["global", "none", "默认"]:
        return True, "Global or unconfigured template environment."

    if env_type.lower() == "conda":
        current_env = os.environ.get("CONDA_DEFAULT_ENV", "")
        python_exe = sys.executable.lower()
        is_in_correct_conda = False
        if env_name:
            if current_env == env_name:
                is_in_correct_conda = True
            elif f"envs/{env_name.lower()}" in python_exe.replace("\\", "/") or f"envs\\{env_name.lower()}" in python_exe:
                is_in_correct_conda = True

        if not is_in_correct_conda:
            return False, f"配置的 Conda 环境为 '{env_name}'，但当前激活的环境为 '{current_env}' (Python: {sys.executable})。请通过 '{env_prefix or 'conda activate ' + env_name}' 运行或激活环境。"

    elif env_type.lower() in ["venv", "virtualenv", "poetry"]:
        is_venv = (sys.prefix != sys.base_prefix)
        if not is_venv:
            python_exe = sys.executable.lower()
            if not any(x in python_exe for x in [".venv", "venv", "virtualenvs", "poetry"]):
                return False, f"项目配置了 '{env_type}' 虚拟环境，但当前正运行在全局环境 ({sys.executable})。请激活虚拟环境或使用前缀：'{env_prefix}'。"

    elif env_type.lower() in ["nvm", "node"]:
        if env_name:
            ret, stdout, stderr = run_cmd("node -v")
            if ret != 0:
                return False, f"未检测到 Node.js 环境。配置要求：Node '{env_name}'。"
            current_version = stdout.strip()
            clean_expected = env_name.lower().replace("node", "").replace("v", "").strip()
            clean_current = current_version.lower().replace("v", "").strip()
            if not clean_current.startswith(clean_expected):
                return False, f"配置要求的 Node 版本为 '{env_name}'，但当前 Node 版本为 '{current_version}'。请通过 '{env_prefix or 'nvm use ' + clean_expected}' 切换环境。"

    elif env_type.lower() in ["rustup", "rust"]:
        if env_name:
            ret, stdout, stderr = run_cmd("rustc --version")
            if ret != 0:
                return False, f"未检测到 Rust 编译环境。配置要求：'{env_name}'。"
            current_version = stdout.strip()
            clean_expected = env_name.lower().replace("rust", "").strip()
            if clean_expected not in current_version.lower():
                return False, f"配置要求的 Rust 版本为 '{env_name}'，但当前版本为 '{current_version}'。请切换至对应的工具链。"

    return True, f"运行环境已验证匹配: {env_type} ({env_name})"

def cmd_security(args):
    module_name = args.module
    project_root = find_project_root(os.getcwd())
    config = load_governance_config(project_root, getattr(args, "config", None))

    checks = []
    status = "pass"
    exit_code = 0

    findings = run_security_scan(project_root, module_name, config)
    if findings:
        checks.append({
            "name": "security",
            "status": "fail",
            "severity": "P0",
            "summary": f"静态安全扫描发现 {len(findings)} 处硬编码凭证或私钥暴露风险！",
            "evidence": [f"{f['file']}:{f['line']} [{f['type']}] {f['summary']}" for f in findings]
        })
        status = "blocked"
        exit_code = 3
    else:
        checks.append({
            "name": "security",
            "status": "pass",
            "severity": "P3",
            "summary": "静态安全扫描通过，未发现敏感信息暴露",
            "evidence": []
        })

    report = {
        "status": status,
        "summary": "静态安全漏洞与敏感数据暴露扫描报告",
        "checks": checks
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(exit_code)
