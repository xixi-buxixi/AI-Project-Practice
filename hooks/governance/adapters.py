# -*- coding: utf-8 -*-

import json
import os
import sys

from .cleanup import perform_cleanup
from .config import (
    LANGUAGE_ORDER, commands_to_list, first_existing_path, find_project_root,
    get_allowed_paths, get_configured_command, get_module_config, get_module_dir,
    get_module_paths, get_modules_to_run, get_state_dir, load_cycles_json,
    load_governance_config, parse_verification_cmd, resolve_level, run_cmd,
    save_cycles_json, should_verify_integrity, unique_preserve_order,
)
from .integrity import verify_governance_integrity

def detect_languages(project_root, module_name=None, config=None):
    config = config or load_governance_config(project_root)
    module_config = get_module_config(config, module_name)
    configured = module_config.get("languages") or module_config.get("language")
    if configured:
        if isinstance(configured, str):
            configured = [configured]
        return [str(lang).lower() for lang in configured]

    detected = []
    target_dirs = get_module_paths(project_root, module_name, config)

    def add_language(language):
        if language not in detected:
            detected.append(language)

    for target_dir in target_dirs:
        if not target_dir or not os.path.exists(target_dir):
            continue

        curr = target_dir
        while True:
            if os.path.exists(os.path.join(curr, "package.json")):
                add_language("node")
            if os.path.exists(os.path.join(curr, "Cargo.toml")):
                add_language("rust")
            if os.path.exists(os.path.join(curr, "go.mod")):
                add_language("go")
            if os.path.exists(os.path.join(curr, "pom.xml")) or os.path.exists(os.path.join(curr, "build.gradle")):
                add_language("java")
            if os.path.exists(os.path.join(curr, "requirements.txt")) or os.path.exists(os.path.join(curr, "pyproject.toml")):
                add_language("python")
            if curr == project_root:
                break
            parent = os.path.dirname(curr)
            if parent == curr:
                break
            curr = parent

        for root, dirs, files in os.walk(target_dir):
            dirs[:] = [d for d in dirs if d not in [".git", ".agent", "node_modules", "venv", ".venv", "__pycache__"]]
            if "package.json" in files:
                add_language("node")
            if "Cargo.toml" in files:
                add_language("rust")
            if "go.mod" in files:
                add_language("go")
            if "pom.xml" in files or "build.gradle" in files:
                add_language("java")
            if "requirements.txt" in files or "pyproject.toml" in files:
                add_language("python")
            if any(f.endswith(".py") for f in files):
                add_language("python")
            if any(f.endswith(".js") or f.endswith(".ts") for f in files):
                add_language("node")
            if any(f.endswith(".go") for f in files):
                add_language("go")
            if any(f.endswith(".rs") for f in files):
                add_language("rust")
            if any(f.endswith(".java") for f in files):
                add_language("java")

    if not detected:
        detected = ["python"]
    return [lang for lang in LANGUAGE_ORDER if lang in detected]

def detect_language(project_root, module_name=None):
    return detect_languages(project_root, module_name)[0]

class LanguageAdapter:
    language = None

    def __init__(self, project_root, module_name=None, config=None, level=None):
        self.project_root = project_root
        self.module_name = module_name
        self.config = config or load_governance_config(project_root)
        self.level = level or self.config.get("project_level", "standard")

    def check_syntax(self) -> list:
        return []

    def get_default_lint_command(self) -> str:
        return None

    def get_default_test_command(self) -> str:
        return None

    def get_configured_command(self, command_type):
        return get_configured_command(self.config, command_type, self.language, self.level, self.module_name)

class PythonAdapter(LanguageAdapter):
    language = "python"

    def check_syntax(self) -> list:
        configured = self.get_configured_command("syntax")
        if configured is not None:
            return run_check_commands(configured, "Python Syntax", get_module_dir(self.project_root, self.module_name, self.config))
        errors = []
        module_dir = get_module_dir(self.project_root, self.module_name, self.config)
        for root, _, files in os.walk(module_dir):
            if any(h in root for h in [".git", ".agent", "__pycache__", "venv", ".venv", "node_modules"]):
                continue
            for file in files:
                if file.endswith(".py"):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            source = f.read()
                        compile(source, file_path, "exec")
                    except SyntaxError as se:
                        errors.append({
                            "file": os.path.relpath(file_path, self.project_root),
                            "line": se.lineno or 1,
                            "error": str(se)
                        })
        return errors

    def get_default_lint_command(self) -> str:
        configured = self.get_configured_command("lint")
        return configured if configured is not None else None

    def get_default_test_command(self) -> str:
        configured = self.get_configured_command("test")
        return configured if configured is not None else "python -m unittest discover"

class NodeAdapter(LanguageAdapter):
    language = "node"

    def check_syntax(self) -> list:
        configured = self.get_configured_command("syntax")
        if configured is not None:
            return run_check_commands(configured, "Node Syntax", get_module_dir(self.project_root, self.module_name, self.config))
        errors = []
        module_dir = get_module_dir(self.project_root, self.module_name, self.config)

        js_files = []
        ts_files = []
        for root, _, files in os.walk(module_dir):
            if any(h in root for h in [".git", ".agent", "node_modules", "venv", ".venv"]):
                continue
            for file in files:
                file_path = os.path.join(root, file)
                if file.endswith(".js"):
                    js_files.append(file_path)
                elif file.endswith(".ts"):
                    ts_files.append(file_path)

        for js_file in js_files:
            ret, stdout, stderr = run_cmd(["node", "--check", js_file])
            if ret != 0:
                errors.append({
                    "file": os.path.relpath(js_file, self.project_root),
                    "line": 1,
                    "error": stderr.strip() or stdout.strip()
                })

        if ts_files:
            tsconfig = first_existing_path(self.project_root, [
                os.path.join(module_dir, "tsconfig.json"),
                os.path.join(self.project_root, "tsconfig.json"),
            ])
            if tsconfig and os.path.exists(tsconfig):
                tsc_cmd = ["npx", "tsc", "--noEmit", "-p", tsconfig]
                if os.name == "nt":
                    # npx resolves to npx.cmd on Windows; invoke via cmd /c so
                    # shell=False spawning can still locate the wrapper script.
                    tsc_cmd = ["cmd", "/c"] + tsc_cmd
                ret, stdout, stderr = run_cmd(tsc_cmd, cwd=self.project_root)
                if ret != 0 and ret != 2:
                    errors.append({
                        "file": "TypeScript Compilation",
                        "line": 1,
                        "error": stderr.strip() or stdout.strip()
                    })
        return errors

    def get_default_lint_command(self) -> str:
        configured = self.get_configured_command("lint")
        return configured if configured is not None else "npm run lint"

    def get_default_test_command(self) -> str:
        configured = self.get_configured_command("test")
        return configured if configured is not None else "npm test"

class GoAdapter(LanguageAdapter):
    language = "go"

    def check_syntax(self) -> list:
        configured = self.get_configured_command("syntax")
        module_dir = get_module_dir(self.project_root, self.module_name, self.config)
        return run_check_commands(configured if configured is not None else "go vet ./...", "Go Vet", module_dir)

    def get_default_lint_command(self) -> str:
        configured = self.get_configured_command("lint")
        return configured if configured is not None else "go vet ./..."

    def get_default_test_command(self) -> str:
        configured = self.get_configured_command("test")
        return configured if configured is not None else "go test ./..."

class RustAdapter(LanguageAdapter):
    language = "rust"

    def check_syntax(self) -> list:
        configured = self.get_configured_command("syntax")
        module_dir = get_module_dir(self.project_root, self.module_name, self.config)
        return run_check_commands(configured if configured is not None else "cargo check", "Cargo Check", module_dir)

    def get_default_lint_command(self) -> str:
        configured = self.get_configured_command("lint")
        return configured if configured is not None else "cargo clippy"

    def get_default_test_command(self) -> str:
        configured = self.get_configured_command("test")
        return configured if configured is not None else "cargo test"

class JavaAdapter(LanguageAdapter):
    language = "java"

    def check_syntax(self) -> list:
        module_dir = get_module_dir(self.project_root, self.module_name, self.config)
        configured = self.get_configured_command("syntax")
        if configured is not None:
            return run_check_commands(configured, "Java Syntax", module_dir)
        if self.level != "enterprise":
            return []
        if os.path.exists(os.path.join(module_dir, "pom.xml")) or os.path.exists(os.path.join(self.project_root, "pom.xml")):
            ret, stdout, stderr = run_cmd("mvn compile -DskipTests", cwd=module_dir)
            if ret != 0 and ret != 2:
                return [{
                    "file": "Maven Compile",
                    "line": 1,
                    "error": stderr.strip() or stdout.strip()
                }]
        elif os.path.exists(os.path.join(module_dir, "build.gradle")) or os.path.exists(os.path.join(self.project_root, "build.gradle")):
            ret, stdout, stderr = run_cmd("gradle compileJava", cwd=module_dir)
            if ret != 0 and ret != 2:
                return [{
                    "file": "Gradle Compile",
                    "line": 1,
                    "error": stderr.strip() or stdout.strip()
                }]
        return []

    def get_default_lint_command(self) -> str:
        configured = self.get_configured_command("lint")
        return configured if configured is not None else None

    def get_default_test_command(self) -> str:
        configured = self.get_configured_command("test")
        if configured is not None:
            return configured
        if os.path.exists(os.path.join(self.project_root, "pom.xml")):
            return "mvn test"
        return "gradle test"

def run_check_commands(command, label, cwd):
    errors = []
    for cmd in commands_to_list(command):
        ret, stdout, stderr = run_cmd(cmd, cwd=cwd)
        if ret != 0 and ret != 2:
            errors.append({
                "file": label,
                "line": 1,
                "error": stderr.strip() or stdout.strip()
            })
    return errors

def build_language_adapter(language, project_root, module_name=None, config=None, level=None):
    if language == "python":
        return PythonAdapter(project_root, module_name, config, level)
    if language == "node":
        return NodeAdapter(project_root, module_name, config, level)
    if language == "go":
        return GoAdapter(project_root, module_name, config, level)
    if language == "rust":
        return RustAdapter(project_root, module_name, config, level)
    if language == "java":
        return JavaAdapter(project_root, module_name, config, level)
    return PythonAdapter(project_root, module_name, config, level)

def get_language_adapters(project_root, module_name=None, config=None, level=None):
    config = config or load_governance_config(project_root)
    level = level or config.get("project_level", "standard")
    return [
        build_language_adapter(lang, project_root, module_name, config, level)
        for lang in detect_languages(project_root, module_name, config)
    ]

def get_language_adapter(project_root, module_name=None) -> LanguageAdapter:
    return get_language_adapters(project_root, module_name)[0]

def cmd_finalize(args):
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
            report = {
                "status": status,
                "module": module_name,
                "checks": checks,
                "counters": {
                    "attempt_count": cycles_data.get("attempt_count", 0),
                    "invalid_build_cycle_count": cycles_data.get("invalid_build_cycle_count", 0),
                    "infra_failure_count": cycles_data.get("infra_failure_count", 0)
                },
                "artifacts": {"deleted": [], "quarantined": [], "reports": []}
            }
            print(json.dumps(report, indent=2, ensure_ascii=False))
            sys.exit(exit_code)

    # Retrieve allowed paths
    allowed_paths = get_allowed_paths(project_root, module_name, config, cycles_data)

    # 2. Clean up & Quarantine
    deleted, quarantined, reported, cleanup_errors = perform_cleanup(
        project_root,
        None if module_name == "all" else module_name,
        allowed_paths,
        config.get("cleanup", {}).get("whitelist"),
    )
    checks.append({
        "name": "cleanup",
        "status": "pass",
        "severity": "P3",
        "summary": f"清理了 {len(deleted)} 个临时文件，隔离了 {len(quarantined)} 个未追踪文件",
        "evidence": [f"Deleted: {d}" for d in deleted] + [f"Quarantined: {q}" for q in quarantined]
    })

    if cleanup_errors:
        checks.append({
            "name": "cleanup",
            "status": "fail",
            "severity": "P2",
            "summary": f"清理/隔离过程中发生 {len(cleanup_errors)} 处错误（已降级为报告，未静默吞噬）",
            "evidence": cleanup_errors
        })
        if status == "pass":
            status = "fail"
        if exit_code == 0:
            exit_code = 1

    if reported:
        checks.append({
            "name": "cleanup",
            "status": "pass",
            "severity": "P2",
            "summary": f"发现 {len(reported)} 个未追踪且未被隔离的文件（如源码或外部文件）",
            "evidence": [f"Untracked/Reported: {r}" for r in reported]
        })

    modules_to_run = get_modules_to_run(module_name, config, cycles_data)

    for m_name in modules_to_run:
        lang_adapters = get_language_adapters(project_root, m_name, config, level)
        languages = [adapter.language for adapter in lang_adapters]

        # 3. Lint / Syntax Check
        syntax_errors = []
        for lang_adapter in lang_adapters:
            syntax_errors.extend(lang_adapter.check_syntax())
        if syntax_errors:
            checks.append({
                "name": "lint",
                "status": "fail",
                "severity": "P1",
                "summary": f"发现 {m_name or '默认'} 模块语法错误",
                "evidence": [f"{err['file']}:{err['line']}: {err['error']}" for err in syntax_errors]
            })
            status = "fail"
            exit_code = 2
        else:
            lint_cmds = []
            for lang_adapter in lang_adapters:
                lint_cmds.extend(commands_to_list(lang_adapter.get_default_lint_command()))
            lint_cmds = unique_preserve_order(lint_cmds)
            if lint_cmds:
                for lint_cmd in lint_cmds:
                    ret, stdout, stderr = run_cmd(lint_cmd, cwd=project_root)
                    if ret != 0:
                        checks.append({
                            "name": "lint",
                            "status": "fail",
                            "severity": "P1",
                            "summary": f"Linter 校验失败 ({m_name or '默认'} 模块: {lint_cmd})",
                            "evidence": [stderr, stdout[:500]]
                        })
                        status = "fail"
                        exit_code = 2 if ret == 2 else 1
                        break
                    else:
                        checks.append({
                            "name": "lint",
                            "status": "pass",
                            "severity": "P3",
                            "summary": f"Linter 校验通过 ({m_name or '默认'} 模块: {lint_cmd})",
                            "evidence": []
                        })
            else:
                checks.append({
                    "name": "lint",
                    "status": "pass",
                    "severity": "P3",
                    "summary": f"语法与 Linter 扫描通过 ({m_name or '默认'} 模块, 语言: {', '.join(languages)})",
                    "evidence": []
                })

        # 4. Test / Verification
        test_cmd = parse_verification_cmd(
            project_root,
            m_name,
            config,
            getattr(args, "test_command", None),
        )
        test_cmds = commands_to_list(test_cmd)
        if not test_cmds:
            for lang_adapter in lang_adapters:
                test_cmds.extend(commands_to_list(lang_adapter.get_default_test_command()))
            test_cmds = unique_preserve_order(test_cmds)

        if test_cmds and exit_code == 0:
            for test_cmd in test_cmds:
                check_item = {
                    "name": "test",
                    "status": "pass",
                    "severity": "P1",
                    "summary": f"执行验证测试命令 ({m_name or '默认'} 模块): {test_cmd}",
                    "evidence": []
                }
                checks.append(check_item)
                ret, stdout, stderr = run_cmd(test_cmd, cwd=project_root)
                if ret != 0:
                    check_item["status"] = "fail"
                    check_item["evidence"] = [f"Exit code: {ret}", stderr, stdout[:500]]
                    status = "fail"
                    exit_code = 2 if ret == 2 else 1
                    break
                else:
                    check_item["evidence"] = [stdout[:500]]
        elif exit_code == 0:
            checks.append({
                "name": "test",
                "status": "skipped",
                "severity": "P3",
                "summary": f"未找到 {m_name or '默认'} 模块适合的测试命令，已跳过测试",
                "evidence": []
            })

    # 5. Update Counters
    cycles_data["attempt_count"] = cycles_data.get("attempt_count", 0) + 1
    if "modules" not in cycles_data:
        cycles_data["modules"] = {}

    for m_name in modules_to_run:
        if not m_name:
            continue
        if m_name not in cycles_data["modules"]:
            cycles_data["modules"][m_name] = {
                "attempt_count": 0,
                "invalid_build_cycle_count": 0,
                "infra_failure_count": 0
            }
        m_data = cycles_data["modules"][m_name]
        m_data["attempt_count"] = m_data.get("attempt_count", 0) + 1

        if exit_code == 1:
            cycles_data["invalid_build_cycle_count"] = cycles_data.get("invalid_build_cycle_count", 0) + 1
            m_data["invalid_build_cycle_count"] = m_data.get("invalid_build_cycle_count", 0) + 1
        elif exit_code == 2:
            cycles_data["infra_failure_count"] = cycles_data.get("infra_failure_count", 0) + 1
            m_data["infra_failure_count"] = m_data.get("infra_failure_count", 0) + 1

    save_cycles_json(state_dir, cycles_data)

    primary_m_name = modules_to_run[0]
    m_counters = {
        "attempt_count": cycles_data["attempt_count"],
        "invalid_build_cycle_count": cycles_data["invalid_build_cycle_count"],
        "infra_failure_count": cycles_data["infra_failure_count"]
    }
    if primary_m_name and primary_m_name in cycles_data["modules"]:
        m_counters = cycles_data["modules"][primary_m_name]

    report = {
        "status": status,
        "module": module_name,
        "checks": checks,
        "counters": {
            "attempt_count": m_counters["attempt_count"],
            "invalid_build_cycle_count": m_counters["invalid_build_cycle_count"],
            "infra_failure_count": m_counters["infra_failure_count"]
        },
        "artifacts": {
            "deleted": deleted,
            "quarantined": quarantined,
            "reports": reported
        }
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(exit_code)
