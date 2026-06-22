#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import re
import hashlib
import subprocess
import shutil
import fnmatch
import argparse

# Whitelist patterns for automatic deletion during cleanup
CLEANUP_WHITELIST = [
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "__pycache__",
    "*.log",
    ".pytest_cache",
    ".agent-temp",
    "tmp/ai-*",
    "*.scratch.*"
]

def load_cycles_json(state_dir):
    cycles_path = os.path.join(state_dir, "cycles.json")
    if not os.path.exists(cycles_path):
        os.makedirs(state_dir, exist_ok=True)
        default_data = {
            "attempt_count": 0,
            "invalid_build_cycle_count": 0,
            "infra_failure_count": 0,
            "modules": {}
        }
        with open(cycles_path, "w", encoding="utf-8") as f:
            json.dump(default_data, f, indent=2, ensure_ascii=False)
        return default_data

    try:
        with open(cycles_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "attempt_count": 0,
            "invalid_build_cycle_count": 0,
            "infra_failure_count": 0,
            "modules": {}
        }

def save_cycles_json(state_dir, data):
    cycles_path = os.path.join(state_dir, "cycles.json")
    os.makedirs(state_dir, exist_ok=True)
    with open(cycles_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_state_dir(project_root):
    return os.path.join(project_root, ".agent", "state")

def get_quarantine_dir(project_root):
    return os.path.join(project_root, ".agent", "quarantine")

def run_cmd(cmd, cwd=None):
    try:
        res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=cwd)
        # Check for command not found error signatures to classify as infra failure
        if res.returncode != 0:
            err = res.stderr.lower()
            if "not recognized" in err or "command not found" in err or "no such file" in err:
                return 2, res.stdout, res.stderr
            return 1, res.stdout, res.stderr
        return 0, res.stdout, res.stderr
    except FileNotFoundError as e:
        return 2, "", str(e)
    except Exception as e:
        return 2, "", str(e)

def find_project_root(start_path):
    curr = os.path.abspath(start_path)
    while True:
        if os.path.exists(os.path.join(curr, "AI_AGENT_CONTRACT.md")) or \
           os.path.exists(os.path.join(curr, "agent.md")) or \
           os.path.exists(os.path.join(curr, "REQUIREMENTS.md")) or \
           os.path.exists(os.path.join(curr, ".git")):
            return curr
        parent = os.path.dirname(curr)
        if parent == curr:
            return os.path.abspath(start_path)
        curr = parent

def detect_language(project_root, module_name=None):
    target_dir = os.path.join(project_root, "src", module_name) if module_name else os.path.join(project_root, "src")
    if not os.path.exists(target_dir):
        # Fallback for Lite example
        target_dir = os.path.join(project_root, "examples", module_name) if module_name else project_root
        if not os.path.exists(target_dir):
            target_dir = project_root

    # Search in target_dir parent directories
    curr = target_dir
    while True:
        if os.path.exists(os.path.join(curr, "package.json")): return "node"
        if os.path.exists(os.path.join(curr, "Cargo.toml")): return "rust"
        if os.path.exists(os.path.join(curr, "go.mod")): return "go"
        if os.path.exists(os.path.join(curr, "pom.xml")) or os.path.exists(os.path.join(curr, "build.gradle")): return "java"
        if os.path.exists(os.path.join(curr, "requirements.txt")) or os.path.exists(os.path.join(curr, "pyproject.toml")): return "python"
        if curr == project_root: break
        curr = os.path.dirname(curr)

    # Search files recursively inside target_dir
    for root, _, files in os.walk(target_dir):
        if any(h in root for h in [".git", ".agent", "node_modules", "venv", ".venv", "__pycache__"]):
            continue
        if "package.json" in files: return "node"
        if "Cargo.toml" in files: return "rust"
        if "go.mod" in files: return "go"
        if "pom.xml" in files or "build.gradle" in files: return "java"
        if "requirements.txt" in files or "pyproject.toml" in files: return "python"
        if any(f.endswith(".py") for f in files): return "python"
        if any(f.endswith(".js") or f.endswith(".ts") for f in files): return "node"
        if any(f.endswith(".go") for f in files): return "go"
        if any(f.endswith(".rs") for f in files): return "rust"

    return "python" # Default fallback

def check_path_allowed(project_root, module_name, allowed_paths):
    ret, out, _ = run_cmd("git status --porcelain", cwd=project_root)
    if ret != 0:
        return True, []

    modified_files = []
    for line in out.splitlines():
        if line.strip():
            parts = line.strip().split(None, 1)
            if len(parts) > 1:
                path = parts[1]
                if " -> " in path:
                    path = path.split(" -> ")[-1]
                modified_files.append(os.path.normpath(path))

    violations = []
    for f in modified_files:
        is_allowed = False
        for p in allowed_paths:
            norm_p = os.path.normpath(p)
            if f.startswith(norm_p):
                is_allowed = True
                break
        if not is_allowed:
            violations.append(f)

    return len(violations) == 0, violations

def parse_verification_cmd(project_root, module_name):
    # Try module tasks.md first
    tasks_path = os.path.join(project_root, "src", module_name, "tasks.md")
    if not os.path.exists(tasks_path):
        tasks_path = os.path.join(project_root, "examples", module_name, "task.md")
        if not os.path.exists(tasks_path):
            tasks_path = os.path.join(project_root, "task.md")

    if os.path.exists(tasks_path):
        try:
            with open(tasks_path, "r", encoding="utf-8") as f:
                content = f.read()
            m = re.search(r"-\s+Command:\s*(.+)", content, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        except Exception:
            pass
    return None

def perform_cleanup(project_root, module_name, allowed_paths=None):
    deleted_files = []
    quarantined_files = []
    reported_untracked = []

    ret, git_root_out, _ = run_cmd("git rev-parse --show-toplevel", cwd=project_root)
    if ret != 0:
        return deleted_files, quarantined_files, reported_untracked
        
    git_root = git_root_out.strip()

    ret, out, _ = run_cmd("git status --porcelain", cwd=project_root)
    if ret != 0:
        return deleted_files, quarantined_files, reported_untracked

    untracked_paths = []
    for line in out.splitlines():
        if line.startswith("??"):
            path = line[3:].strip()
            untracked_paths.append(path)

    quarantine_dir = get_quarantine_dir(project_root)

    paths_to_check = allowed_paths if allowed_paths else [
        os.path.join("src", module_name) if module_name else "src",
        os.path.join("examples", module_name) if module_name else "examples"
    ]
    
    abs_paths_to_check = []
    for p in paths_to_check:
        if os.path.isabs(p):
            abs_paths_to_check.append(os.path.normpath(p))
        else:
            abs_p = os.path.normpath(os.path.join(project_root, p))
            abs_paths_to_check.append(abs_p)

    for path in untracked_paths:
        abs_path = os.path.normpath(os.path.join(git_root, path))
        if not os.path.exists(abs_path):
            continue

        in_scope = False
        for p in abs_paths_to_check:
            if abs_path.startswith(p + os.sep) or abs_path == p:
                in_scope = True
                break
        
        rel_path = os.path.relpath(abs_path, project_root)

        if not in_scope:
            reported_untracked.append(rel_path)
            continue

        filename = os.path.basename(abs_path)
        is_whitelisted = False
        for pattern in CLEANUP_WHITELIST:
            if fnmatch.fnmatch(filename, pattern) or fnmatch.fnmatch(rel_path, pattern):
                is_whitelisted = True
                break

        if is_whitelisted:
            try:
                if os.path.isdir(abs_path):
                    shutil.rmtree(abs_path)
                else:
                    os.remove(abs_path)
                deleted_files.append(rel_path)
            except Exception:
                pass
        else:
            _, ext = os.path.splitext(filename)
            if ext.lower() in [".py", ".md", ".json", ".txt", ".js", ".ts", ".rs", ".go", ".java", ".c", ".h", ".cpp", ".yml", ".yaml"]:
                reported_untracked.append(rel_path)
                continue

            try:
                os.makedirs(quarantine_dir, exist_ok=True)
                dest = os.path.join(quarantine_dir, filename)
                base, ext = os.path.splitext(filename)
                counter = 1
                while os.path.exists(dest):
                    dest = os.path.join(quarantine_dir, f"{base}_{counter}{ext}")
                    counter += 1
                
                shutil.move(abs_path, dest)
                quarantined_files.append(rel_path)
            except Exception:
                pass

    return deleted_files, quarantined_files, reported_untracked

def check_syntax(project_root, module_name):
    errors = []
    module_dir = os.path.join(project_root, "src", module_name) if module_name else os.path.join(project_root, "src")
    if not os.path.exists(module_dir):
        module_dir = os.path.join(project_root, "examples", module_name) if module_name else project_root
        if not os.path.exists(module_dir):
            module_dir = project_root

    for root, _, files in os.walk(module_dir):
        if any(h in root for h in [".git", ".agent", "__pycache__", "venv", ".venv", "node_modules"]):
            continue
        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        source = f.read()
                    compile(source, file_path, "exec")
                except SyntaxError as se:
                    errors.append({
                        "file": os.path.relpath(file_path, project_root),
                        "line": se.lineno,
                        "error": str(se)
                    })
    return errors

def parse_yaml_traceability(file_path):
    if not os.path.exists(file_path):
        return []
    
    requirements = []
    current_req = None
    current_list_field = None
    
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            
            if stripped == "requirements:":
                continue
            
            if stripped.startswith("- id:"):
                if current_req:
                    requirements.append(current_req)
                req_id = stripped[5:].strip().strip('"').strip("'")
                current_req = {
                    "id": req_id,
                    "source": "",
                    "prd_section": "",
                    "module": "",
                    "logical_entity": "",
                    "acceptance_criteria": [],
                    "tests": []
                }
                current_list_field = None
                continue
                
            if current_req:
                if stripped.startswith("source:"):
                    current_req["source"] = stripped[7:].strip().strip('"').strip("'")
                    current_list_field = None
                elif stripped.startswith("prd_section:"):
                    current_req["prd_section"] = stripped[12:].strip().strip('"').strip("'")
                    current_list_field = None
                elif stripped.startswith("module:"):
                    current_req["module"] = stripped[7:].strip().strip('"').strip("'")
                    current_list_field = None
                elif stripped.startswith("logical_entity:"):
                    current_req["logical_entity"] = stripped[15:].strip().strip('"').strip("'")
                    current_list_field = None
                elif stripped == "acceptance_criteria:":
                    current_list_field = "acceptance_criteria"
                elif stripped == "tests:":
                    current_list_field = "tests"
                elif stripped.startswith("-") and current_list_field:
                    val = stripped[1:].strip().strip('"').strip("'")
                    current_req[current_list_field].append(val)
                    
    if current_req:
        requirements.append(current_req)
        
    return requirements

def generate_traceability_md(requirements):
    md = [
        "# Traceability Matrix",
        "",
        "> **定位**：由 `traceability-source.yaml` 自动生成的人类可读追踪矩阵。请勿手动修改本文件。",
        "",
        "| 需求ID | 原始输入 | PRD章节 | 模块 | 逻辑实体 | 验收条件 (AC) | 测试用例 |",
        "|:---|:---|:---|:---|:---|:---|:---|"
    ]
    for r in requirements:
        acs = ", ".join(r["acceptance_criteria"])
        tests = ", ".join(r["tests"])
        md.append(f"| {r['id']} | {r['source']} | {r['prd_section']} | {r['module']} | {r['logical_entity']} | {acs} | {tests} |")
    return "\n".join(md) + "\n"

def update_constitution_hash(file_path):
    if not os.path.exists(file_path):
        return None
        
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    lines = content.splitlines()
    hash_lines = []
    hash_line_idx = -1
    for i, line in enumerate(lines):
        if re.search(r"^\s*sha256_hash\s*:", line):
            hash_line_idx = i
        else:
            hash_lines.append(line)
            
    hash_content = "\n".join(hash_lines).encode("utf-8")
    file_hash = hashlib.sha256(hash_content).hexdigest()
    
    if hash_line_idx != -1:
        m = re.match(r"^(\s*)sha256_hash\s*:", lines[hash_line_idx])
        indent = m.group(1) if m else "  "
        lines[hash_line_idx] = f'{indent}sha256_hash: "{file_hash}"'
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
            
    return file_hash

def run_security_scan(project_root, module_name=None):
    findings = []
    # Match pattern: key/token/password = 'string' or key/token/password=string (unquoted)
    secret_pat = re.compile(
        r"(api_key|apikey|secret_key|private_key|token|passwd|password|client_secret)\s*[:=]\s*(['\"]?)([a-zA-Z0-9_\-\.\~]{10,})\2", 
        re.IGNORECASE
    )
    private_key_pat = re.compile(r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----")
    
    # 1. Collect files to scan
    files_to_scan = []
    
    # Always scan root files like .env*
    for f in os.listdir(project_root):
        f_path = os.path.join(project_root, f)
        if os.path.isfile(f_path):
            if f == ".env" or f.startswith(".env."):
                files_to_scan.append(f_path)
    
    # Scan module directory or entire src
    if module_name:
        target_dirs = [
            os.path.join(project_root, "src", module_name),
            os.path.join(project_root, "examples", module_name)
        ]
    else:
        target_dirs = [
            os.path.join(project_root, "src"),
            os.path.join(project_root, "examples"),
            project_root # also check root directory
        ]
        
    for target_dir in target_dirs:
        if not os.path.exists(target_dir):
            continue
        for root, dirs, files in os.walk(target_dir):
            # Prune ignored directories
            dirs[:] = [d for d in dirs if d not in [".git", ".agent", "__pycache__", "venv", ".venv", "node_modules"]]
            
            for file in files:
                file_path = os.path.join(root, file)
                filename = os.path.basename(file_path)
                _, ext = os.path.splitext(filename)
                
                # Check if it matches allowed extensions or .env*
                if ext.lower() in [".py", ".js", ".ts", ".go", ".rs", ".java", ".json", ".yaml", ".yml", ".md", ".txt", ".sh", ".properties"] or \
                   filename == ".env" or \
                   filename.startswith(".env."):
                    if file_path not in files_to_scan:
                        files_to_scan.append(file_path)
                        
    # 2. Run scan on collected files
    for file_path in files_to_scan:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for line_num, line in enumerate(f, 1):
                    # Check secrets
                    m = secret_pat.search(line)
                    if m:
                        val = m.group(3)
                        if not any(ph in val.lower() for ph in ["example", "placeholder", "your_", "todo", "my_", "test_", "mock", "auto_generated"]):
                            findings.append({
                                "file": os.path.relpath(file_path, project_root),
                                "line": line_num,
                                "type": "hardcoded_secret",
                                "summary": f"发现疑似硬编码凭证：{m.group(1)} = '{val[:3]}...{val[-3:] if len(val) > 6 else ''}'"
                            })
                    # Check private keys
                    if private_key_pat.search(line):
                        findings.append({
                            "file": os.path.relpath(file_path, project_root),
                            "line": line_num,
                            "type": "private_key",
                            "summary": "发现疑似硬编码私钥块 (Private Key Block)"
                        })
        except Exception:
            pass
            
    return findings

def get_default_lint_command(lang, project_root):
    if lang == "python": return None # custom syntax check
    if lang == "node": return "npm run lint"
    if lang == "rust": return "cargo clippy"
    if lang == "go": return "go vet ./..."
    return None

def get_default_test_command(lang, project_root):
    if lang == "python": return "python -m unittest discover"
    if lang == "node": return "npm test"
    if lang == "rust": return "cargo test"
    if lang == "go": return "go test ./..."
    if lang == "java":
        if os.path.exists(os.path.join(project_root, "pom.xml")): return "mvn test"
        return "gradle test"
    return None

def cmd_preflight(args):
    module_name = args.module
    is_lite = args.lite
    project_root = find_project_root(os.getcwd())
    state_dir = get_state_dir(project_root)
    cycles_data = load_cycles_json(state_dir)

    checks = []
    status = "pass"
    exit_code = 0

    agents_md_path = os.path.join(project_root, "src", module_name, "agents.md")
    if is_lite:
        agents_md_path = os.path.join(project_root, "examples", module_name, "REQUIREMENTS.md")
        if not os.path.exists(agents_md_path):
            agents_md_path = os.path.join(project_root, "REQUIREMENTS.md")

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
            "summary": "模块指引规范已就绪",
            "evidence": [agents_md_path]
        })

    module_lock = cycles_data.get("modules", {}).get(module_name, {})
    allowed_paths = module_lock.get("allowed_paths", [])
    if allowed_paths:
        ok, violations = check_path_allowed(project_root, module_name, allowed_paths)
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

def cmd_finalize(args):
    module_name = args.module
    is_lite = args.lite
    project_root = find_project_root(os.getcwd())
    state_dir = get_state_dir(project_root)
    cycles_data = load_cycles_json(state_dir)

    checks = []
    status = "pass"
    exit_code = 0

    # Retrieve allowed paths
    module_lock = cycles_data.get("modules", {}).get(module_name, {})
    allowed_paths = module_lock.get("allowed_paths", [])

    # 1. Clean up & Quarantine
    deleted, quarantined, reported = perform_cleanup(project_root, module_name, allowed_paths)
    checks.append({
        "name": "cleanup",
        "status": "pass",
        "severity": "P3",
        "summary": f"清理了 {len(deleted)} 个临时文件，隔离了 {len(quarantined)} 个未追踪文件",
        "evidence": [f"Deleted: {d}" for d in deleted] + [f"Quarantined: {q}" for q in quarantined]
    })

    if reported:
        checks.append({
            "name": "cleanup",
            "status": "pass",
            "severity": "P2",
            "summary": f"发现 {len(reported)} 个未追踪且未被隔离的文件（如源码或外部文件）",
            "evidence": [f"Untracked/Reported: {r}" for r in reported]
        })

    # Language Detection & Adapter Dispatch
    lang = detect_language(project_root, module_name)
    
    # 2. Lint / Syntax Check
    syntax_errors = []
    if lang == "python":
        syntax_errors = check_syntax(project_root, module_name)
        if syntax_errors:
            checks.append({
                "name": "lint",
                "status": "fail",
                "severity": "P1",
                "summary": "发现 Python 语法错误",
                "evidence": [f"{err['file']}:{err['line']}: {err['error']}" for err in syntax_errors]
            })
            status = "fail"
            exit_code = 2
    else:
        # Default linter cmd
        lint_cmd = get_default_lint_command(lang, project_root)
        if lint_cmd:
            ret, stdout, stderr = run_cmd(lint_cmd, cwd=project_root)
            if ret != 0:
                checks.append({
                    "name": "lint",
                    "status": "fail",
                    "severity": "P1",
                    "summary": f"Linter 校验失败 ({lint_cmd})",
                    "evidence": [stderr, stdout[:500]]
                })
                status = "fail"
                # If command was not found, exit code is 2 (infra), else 1
                exit_code = 2 if ret == 2 else 1
    
    if exit_code == 0:
        checks.append({
            "name": "lint",
            "status": "pass",
            "severity": "P3",
            "summary": f"语法与 Linter 扫描通过 (语言: {lang})",
            "evidence": []
        })

    # 3. Test / Verification
    test_cmd = parse_verification_cmd(project_root, module_name)
    if not test_cmd:
        test_cmd = get_default_test_command(lang, project_root)

    if test_cmd and exit_code == 0:
        checks.append({
            "name": "test",
            "status": "skipped",
            "severity": "P1",
            "summary": f"执行验证测试命令: {test_cmd}",
            "evidence": []
        })
        
        ret, stdout, stderr = run_cmd(test_cmd, cwd=project_root)
        if ret != 0:
            checks[-1]["status"] = "fail"
            checks[-1]["evidence"] = [f"Exit code: {ret}", stderr, stdout[:500]]
            status = "fail"
            exit_code = 2 if ret == 2 else 1
        else:
            checks[-1]["status"] = "pass"
            checks[-1]["evidence"] = [stdout[:500]]
    elif exit_code == 0:
        checks.append({
            "name": "test",
            "status": "skipped",
            "severity": "P3",
            "summary": "未找到适合的测试命令，已跳过测试",
            "evidence": []
        })

    # 4. Update Counters
    cycles_data["attempt_count"] = cycles_data.get("attempt_count", 0) + 1
    if "modules" not in cycles_data:
        cycles_data["modules"] = {}
    if module_name not in cycles_data["modules"]:
        cycles_data["modules"][module_name] = {
            "attempt_count": 0,
            "invalid_build_cycle_count": 0,
            "infra_failure_count": 0
        }
    
    m_data = cycles_data["modules"][module_name]
    m_data["attempt_count"] = m_data.get("attempt_count", 0) + 1

    if exit_code == 1:
        cycles_data["invalid_build_cycle_count"] = cycles_data.get("invalid_build_cycle_count", 0) + 1
        m_data["invalid_build_cycle_count"] = m_data.get("invalid_build_cycle_count", 0) + 1
    elif exit_code == 2:
        cycles_data["infra_failure_count"] = cycles_data.get("infra_failure_count", 0) + 1
        m_data["infra_failure_count"] = m_data.get("infra_failure_count", 0) + 1

    save_cycles_json(state_dir, cycles_data)

    report = {
        "status": status,
        "module": module_name,
        "checks": checks,
        "counters": {
            "attempt_count": m_data["attempt_count"],
            "invalid_build_cycle_count": m_data["invalid_build_cycle_count"],
            "infra_failure_count": m_data["infra_failure_count"]
        },
        "artifacts": {
            "deleted": deleted,
            "quarantined": quarantined,
            "reports": reported
        }
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(exit_code)

def cmd_trace(args):
    project_root = find_project_root(os.getcwd())
    checks = []
    status = "pass"
    exit_code = 0

    # 1. Update constitution.md Hash
    const_path = os.path.join(project_root, "docs", "requirements", "constitution.md")
    if not os.path.exists(const_path):
        const_path = os.path.join(project_root, "constitution.md")

    file_hash = None
    if os.path.exists(const_path):
        file_hash = update_constitution_hash(const_path)
        checks.append({
            "name": "trace",
            "status": "pass",
            "severity": "P3",
            "summary": "自动更新 constitution.md 冻结哈希成功",
            "evidence": [f"File: {const_path}", f"Calculated SHA-256: {file_hash}"]
        })
    else:
        checks.append({
            "name": "trace",
            "status": "skipped",
            "severity": "P3",
            "summary": "未找到 constitution.md，跳过 Hash 计算",
            "evidence": []
        })

    # 2. Read traceability-source.yaml and generate traceability.generated.md
    trace_source = args.source
    if not trace_source:
        trace_source = os.path.join(project_root, "docs", "traceability", "traceability-source.yaml")
        if not os.path.exists(trace_source):
            trace_source = os.path.join(project_root, "docs", "requirements", "traceability-source.yaml")
            if not os.path.exists(trace_source):
                trace_source = os.path.join(project_root, "traceability-source.yaml")

    if os.path.exists(trace_source):
        try:
            requirements = parse_yaml_traceability(trace_source)
            if requirements:
                md_content = generate_traceability_md(requirements)
                dest_dir = os.path.dirname(trace_source)
                dest_md = os.path.join(dest_dir, "traceability.generated.md")
                
                with open(dest_md, "w", encoding="utf-8") as f:
                    f.write(md_content)
                
                checks.append({
                    "name": "trace",
                    "status": "pass",
                    "severity": "P3",
                    "summary": f"解析 {len(requirements)} 个条目，并成功生成 {os.path.basename(dest_md)}",
                    "evidence": [f"Source: {trace_source}", f"Destination: {dest_md}"]
                })
            else:
                checks.append({
                    "name": "trace",
                    "status": "fail",
                    "severity": "P2",
                    "summary": "解析 traceability-source.yaml 未找到有效需求条目",
                    "evidence": [f"Source: {trace_source}"]
                })
                status = "fail"
                exit_code = 1
        except Exception as e:
            checks.append({
                "name": "trace",
                "status": "fail",
                "severity": "P1",
                "summary": f"解析/生成追踪矩阵时发生异常：{str(e)}",
                "evidence": [f"Source: {trace_source}"]
            })
            status = "fail"
            exit_code = 2
    else:
        checks.append({
            "name": "trace",
            "status": "skipped",
            "severity": "P3",
            "summary": "未找到 traceability-source.yaml，跳过追踪矩阵生成",
            "evidence": []
        })

    report = {
        "status": status,
        "summary": "双向追踪与元数据 Hash 校验报告",
        "checks": checks
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(exit_code)

def cmd_security(args):
    module_name = args.module
    project_root = find_project_root(os.getcwd())
    
    checks = []
    status = "pass"
    exit_code = 0

    findings = run_security_scan(project_root, module_name)
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

def main():
    parser = argparse.ArgumentParser(description="Hook Control Tool (hookctl) for AI Project Build Process")
    subparsers = parser.add_subparsers(dest="action", required=True, help="Action to perform")
    
    # Preflight subparser
    parser_pre = subparsers.add_parser("preflight", help="Run preflight checks before launching Agent")
    parser_pre.add_argument("--module", required=True, help="Module name to run checks on")
    parser_pre.add_argument("--lite", action="store_true", help="Lite mode")
    
    # Finalize subparser
    parser_fin = subparsers.add_parser("finalize", help="Run finalize checks and cleanup after Agent run")
    parser_fin.add_argument("--module", required=True, help="Module name to run checks on")
    parser_fin.add_argument("--lite", action="store_true", help="Lite mode")
    
    # Trace subparser
    parser_tr = subparsers.add_parser("trace", help="Generate/update traceability matrix and update constitution hash")
    parser_tr.add_argument("--source", help="Path to traceability-source.yaml")
    
    # Security subparser
    parser_sec = subparsers.add_parser("security", help="Run static security scan for secrets")
    parser_sec.add_argument("--module", help="Limit scan to specific module")
    
    args = parser.parse_args()

    if args.action == "preflight":
        cmd_preflight(args)
    elif args.action == "finalize":
        cmd_finalize(args)
    elif args.action == "trace":
        cmd_trace(args)
    elif args.action == "security":
        cmd_security(args)

if __name__ == "__main__":
    main()
