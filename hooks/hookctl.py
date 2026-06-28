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
import math
import copy

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

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

PROJECT_LEVELS = {"lite", "standard", "enterprise"}
LANGUAGE_ORDER = ["node", "python", "java", "go", "rust"]

DEFAULT_GOVERNANCE_CONFIG = {
    "project_level": "standard",
    "paths": {
        "constitution": "docs/requirements/constitution.md",
        "traceability_source": "docs/traceability/traceability-source.json",
        "traceability_source_yaml": "docs/traceability/traceability-source.yaml",
        "module_map": "MODULE_MAP.md",
    },
    "modules": [],
    "commands": {
        "syntax": {},
        "lint": {},
        "test": None,
    },
    "cleanup": {
        "whitelist": CLEANUP_WHITELIST[:],
    },
    "security": {
        "entropy_threshold": 3.5,
        "allow_nosec": True,
        "allow_test_fixtures": True,
        "placeholder_terms": [
            "example",
            "placeholder",
            "your_",
            "todo",
            "my_",
            "test_",
            "mock",
            "dummy",
            "sample",
            "auto_generated",
        ],
        "excluded_dirs": [
            ".git",
            ".agent",
            "__pycache__",
            "venv",
            ".venv",
            "node_modules",
        ],
    },
}


def deep_merge(base, override):
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def read_structured_file(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    with open(file_path, "r", encoding="utf-8") as f:
        if ext == ".json":
            return json.load(f) or {}
        try:
            import yaml
        except ImportError as exc:
            raise RuntimeError(
                f"YAML parsing requires PyYAML. Use JSON instead or install PyYAML: {file_path}"
            ) from exc
        return yaml.safe_load(f) or {}


def load_governance_config(project_root, config_path=None):
    candidates = []
    if config_path:
        candidates.append(config_path)
    else:
        candidates.extend([
            os.path.join(project_root, ".governance.yaml"),
            os.path.join(project_root, ".governance.yml"),
            os.path.join(project_root, ".governance.json"),
        ])

    loaded = {}
    used_path = None
    for path in candidates:
        abs_path = path if os.path.isabs(path) else os.path.join(project_root, path)
        if os.path.exists(abs_path):
            loaded = read_structured_file(abs_path)
            used_path = abs_path
            break

    config = deep_merge(DEFAULT_GOVERNANCE_CONFIG, loaded)
    config["__config_path"] = used_path

    cleanup = config.setdefault("cleanup", {})
    whitelist = cleanup.get("whitelist") or []
    cleanup["whitelist"] = unique_preserve_order(CLEANUP_WHITELIST + list(whitelist))

    security = config.setdefault("security", {})
    security["placeholder_terms"] = list(security.get("placeholder_terms") or [])
    security["excluded_dirs"] = list(security.get("excluded_dirs") or [])
    return config


def unique_preserve_order(values):
    seen = set()
    result = []
    for value in values:
        if value is None:
            continue
        key = str(value).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def resolve_level(args=None, config=None):
    if args is not None and getattr(args, "lite", False):
        return "lite"
    level = getattr(args, "level", None) if args is not None else None
    if not level:
        level = (config or {}).get("project_level", "standard")
    level = str(level).lower()
    if level not in PROJECT_LEVELS:
        raise ValueError(f"Invalid governance level '{level}'. Expected one of: lite, standard, enterprise")
    return level


def should_verify_integrity(level):
    return level == "enterprise"


def resolve_config_path(project_root, path):
    if not path:
        return None
    return os.path.normpath(path if os.path.isabs(path) else os.path.join(project_root, path))


def first_existing_path(project_root, paths):
    fallback = None
    for path in paths:
        resolved = resolve_config_path(project_root, path)
        if not resolved:
            continue
        if fallback is None:
            fallback = resolved
        if os.path.exists(resolved):
            return resolved
    return fallback


def commands_to_list(command):
    if command is None or command is False:
        return []
    if isinstance(command, list):
        return [str(c).strip() for c in command if str(c).strip()]
    command = str(command).strip()
    return [command] if command else []


def strip_command_markup(value):
    value = (value or "").strip()
    value = value.strip("|").strip()
    if len(value) >= 2 and value[0] == "`" and value[-1] == "`":
        value = value[1:-1]
    return value.strip()


def shannon_entropy(value):
    if not value:
        return 0.0
    counts = {}
    for char in value:
        counts[char] = counts.get(char, 0) + 1
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())

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
    # A list cmd runs with shell=False so each element is a separate argv entry,
    # preventing shell injection from interpolated paths. A string cmd keeps
    # shell=True for backward compatibility with config-driven command strings.
    use_shell = not isinstance(cmd, (list, tuple))
    try:
        res = subprocess.run(
            cmd,
            shell=use_shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
        )
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

def get_module_config(config, module_name):
    for module in (config or {}).get("modules", []) or []:
        if module.get("name") == module_name:
            return module
    return {}


def get_module_paths(project_root, module_name=None, config=None):
    module_config = get_module_config(config, module_name)
    configured_paths = module_config.get("paths") or []
    if configured_paths:
        return [resolve_config_path(project_root, p) for p in configured_paths]
    return [get_module_dir(project_root, module_name)]


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


def get_configured_command(config, command_type, language=None, level=None, module_name=None):
    module_config = get_module_config(config, module_name)
    module_commands = module_config.get("commands") or {}
    command = module_commands.get(command_type)
    if command is None:
        command = (config or {}).get("commands", {}).get(command_type)

    if command is None:
        return None
    if isinstance(command, str) or isinstance(command, list) or command is False:
        return command
    if not isinstance(command, dict):
        return None

    candidates = []
    if language:
        candidates.append(language)
    if level:
        candidates.append(level)
    candidates.extend(["default", "*"])

    for key in candidates:
        if key not in command:
            continue
        value = command[key]
        if isinstance(value, dict):
            if level and level in value:
                return value[level]
            if "default" in value:
                return value["default"]
            continue
        return value
    return None

def get_module_dir(project_root, module_name, config=None):
    if config:
        module_config = get_module_config(config, module_name)
        configured_paths = module_config.get("paths") or []
        if configured_paths:
            resolved = resolve_config_path(project_root, configured_paths[0])
            if resolved:
                return resolved
    module_dir = os.path.join(project_root, "src", module_name) if module_name else os.path.join(project_root, "src")
    if not os.path.exists(module_dir):
        module_dir = os.path.join(project_root, "examples", module_name) if module_name else project_root
        if not os.path.exists(module_dir):
            module_dir = project_root
    return module_dir

def is_hook_managed_state_path(path):
    norm_path = os.path.normpath(path).replace("\\", "/")
    return (
        norm_path == ".agent/state/cycles.json" or
        norm_path == ".agent/state/cycles.json.lock" or
        norm_path.endswith("/.agent/state/cycles.json") or
        norm_path.endswith("/.agent/state/cycles.json.lock")
    )

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


def check_path_allowed(project_root, module_name, allowed_paths):
    ret_root, git_root_out, _ = run_cmd("git rev-parse --show-toplevel", cwd=project_root)
    git_root = git_root_out.strip() if ret_root == 0 else project_root

    ret, out, _ = run_cmd("git status --porcelain -z", cwd=project_root)
    if ret != 0:
        return True, []

    abs_allowed_paths = []
    for p in allowed_paths:
        if os.path.isabs(p):
            abs_allowed_paths.append(os.path.normpath(p))
        else:
            abs_allowed_paths.append(os.path.normpath(os.path.join(git_root, p)))

    modified_files = [os.path.normpath(path) for _, path in parse_git_status_entries(out)]

    violations = []
    for f in modified_files:
        if is_hook_managed_state_path(f):
            continue

        abs_f = os.path.normpath(os.path.join(git_root, f))
        is_allowed = False
        for norm_p in abs_allowed_paths:
            if abs_f.startswith(norm_p + os.sep) or abs_f == norm_p:
                is_allowed = True
                break
        if not is_allowed:
            violations.append(f)

    return len(violations) == 0, violations


def parse_git_status_entries(output):
    entries = []
    if "\0" in output:
        parts = [part for part in output.split("\0") if part]
        i = 0
        while i < len(parts):
            record = parts[i]
            status = record[:2]
            path = record[3:] if len(record) > 3 and record[2] == " " else record[2:].strip()
            if status.strip().startswith(("R", "C")) and i + 1 < len(parts):
                path = parts[i + 1]
                i += 1
            if path:
                entries.append((status, path))
            i += 1
        return entries

    for line in output.splitlines():
        if not line.strip():
            continue
        status = line[:2]
        path = line[3:].strip() if len(line) > 3 else ""
        if " -> " in path:
            path = path.split(" -> ")[-1]
        if path:
            entries.append((status, path))
    return entries


def get_modules_to_run(module_name, config, cycles_data):
    if module_name == "all":
        configured = [m.get("name") for m in config.get("modules", []) if m.get("name")]
        if configured:
            return configured
        modules = list(cycles_data.get("modules", {}).keys())
        return modules if modules else [None]
    return [module_name]


def get_allowed_paths(project_root, module_name, config, cycles_data):
    allowed_paths = []
    if module_name == "all":
        for module in config.get("modules", []) or []:
            allowed_paths.extend(module.get("paths") or [])
        for module in cycles_data.get("modules", {}).values():
            allowed_paths.extend(module.get("allowed_paths", []))
    else:
        module_config = get_module_config(config, module_name)
        allowed_paths.extend(module_config.get("paths") or [])
        module_lock = cycles_data.get("modules", {}).get(module_name, {})
        allowed_paths.extend(module_lock.get("allowed_paths", []))
    return unique_preserve_order(allowed_paths)

def extract_verification_command(content):
    patterns = [
        r"[-*]\s*(?:\*\*)?(?:Command|命令)(?:\*\*)?\s*[:：]\s*(.+)",
        r"(?:\*\*)?(?:Command|命令)(?:\*\*)?\s*[:：]\s*(.+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, content, re.IGNORECASE)
        if m:
            return strip_command_markup(m.group(1))

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [strip_command_markup(c) for c in stripped.strip("|").split("|")]
        if len(cells) >= 2 and cells[0].strip().lower() in ["command", "命令"]:
            return strip_command_markup(cells[1])
    return None


def parse_verification_cmd(project_root, module_name, config=None, override_cmd=None):
    if override_cmd:
        return strip_command_markup(override_cmd)
    config = config or load_governance_config(project_root)
    configured = get_configured_command(config, "test", None, config.get("project_level", "standard"), module_name)
    if configured is not None:
        commands = commands_to_list(configured)
        if commands:
            return commands[0]

    if not module_name:
        tasks_path = os.path.join(project_root, "task.md")
    else:
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
            command = extract_verification_command(content)
            if command:
                return command
        except Exception:
            pass
    return None

def is_binary_file(file_path):
    if os.path.isdir(file_path):
        return False
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(1024)
            return b"\x00" in chunk
    except Exception:
        return False

def perform_cleanup(project_root, module_name, allowed_paths=None, cleanup_whitelist=None):
    deleted_files = []
    quarantined_files = []
    reported_untracked = []
    cleanup_errors = []
    cleanup_whitelist = cleanup_whitelist or CLEANUP_WHITELIST

    ret, git_root_out, _ = run_cmd("git rev-parse --show-toplevel", cwd=project_root)
    if ret != 0:
        return deleted_files, quarantined_files, reported_untracked, cleanup_errors

    git_root = git_root_out.strip()

    ret, out, _ = run_cmd("git status --porcelain -z", cwd=project_root)
    if ret != 0:
        return deleted_files, quarantined_files, reported_untracked, cleanup_errors

    untracked_paths = []
    for status, path in parse_git_status_entries(out):
        if status == "??":
            untracked_paths.append(path)

    quarantine_dir = get_quarantine_dir(project_root)

    abs_paths_to_check = []
    if allowed_paths:
        for p in allowed_paths:
            if os.path.isabs(p):
                abs_paths_to_check.append(os.path.normpath(p))
            else:
                abs_p = os.path.normpath(os.path.join(git_root, p))
                abs_paths_to_check.append(abs_p)
    else:
        paths_to_check = [
            os.path.join("src", module_name) if module_name else "src",
            os.path.join("examples", module_name) if module_name else "examples"
        ]
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
        for pattern in cleanup_whitelist:
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
            except Exception as e:
                cleanup_errors.append(f"删除失败 {rel_path}: {e}")
                reported_untracked.append(rel_path)
        else:
            if os.path.isdir(abs_path):
                reported_untracked.append(rel_path)
                continue
                
            _, ext = os.path.splitext(filename)
            is_binary = is_binary_file(abs_path)
            quarantine_exts = [
                ".exe", ".dll", ".so", ".dylib", ".bin", ".o", ".obj", 
                ".zip", ".tar", ".gz", ".rar", ".db", ".sqlite", ".class", ".jar"
            ]
            
            should_quarantine = is_binary or ext.lower() in quarantine_exts

            if should_quarantine:
                try:
                    os.makedirs(quarantine_dir, exist_ok=True)
                    dest = os.path.join(quarantine_dir, filename)
                    base, ext_part = os.path.splitext(filename)
                    counter = 1
                    while os.path.exists(dest):
                        dest = os.path.join(quarantine_dir, f"{base}_{counter}{ext_part}")
                        counter += 1
                    
                    shutil.move(abs_path, dest)
                    quarantined_files.append(rel_path)
                except Exception as e:
                    cleanup_errors.append(f"隔离失败 {rel_path}: {e}")
                    reported_untracked.append(rel_path)
            else:
                reported_untracked.append(rel_path)

    return deleted_files, quarantined_files, reported_untracked, cleanup_errors



def normalize_traceability_requirement(item):
    item = item or {}
    requirement = {
        "id": str(item.get("id", "")),
        "source": str(item.get("source", "")),
        "prd_section": str(item.get("prd_section", "")),
        "module": str(item.get("module", "")),
        "logical_entity": str(item.get("logical_entity", "")),
        "acceptance_criteria": item.get("acceptance_criteria") or [],
        "tests": item.get("tests") or [],
    }
    if isinstance(requirement["acceptance_criteria"], str):
        requirement["acceptance_criteria"] = [requirement["acceptance_criteria"]]
    if isinstance(requirement["tests"], str):
        requirement["tests"] = [requirement["tests"]]
    requirement["acceptance_criteria"] = [str(v) for v in requirement["acceptance_criteria"]]
    requirement["tests"] = [str(v) for v in requirement["tests"]]
    return requirement


def parse_traceability_source(file_path):
    if not os.path.exists(file_path):
        return []

    data = read_structured_file(file_path)
    if isinstance(data, list):
        raw_requirements = data
    elif isinstance(data, dict):
        raw_requirements = data.get("requirements") or []
    else:
        raw_requirements = []
    return [normalize_traceability_requirement(item) for item in raw_requirements]


def parse_yaml_traceability(file_path):
    return parse_traceability_source(file_path)

def generate_traceability_md(requirements, gov_hash=None):
    md = [
        "# Traceability Matrix",
        "",
        "> **定位**：由 `traceability-source.yaml` 自动生成的人类可读追踪矩阵。请勿手动修改本文件。",
    ]
    if gov_hash:
        md.append(f"> **治理哈希 (Governance Hash)**: `{gov_hash}`")
    md.extend([
        "",
        "| 需求ID | 原始输入 | PRD章节 | 模块 | 逻辑实体 | 验收条件 (AC) | 测试用例 |",
        "|:---|:---|:---|:---|:---|:---|:---|"
    ])
    for r in requirements:
        acs = ", ".join(r["acceptance_criteria"])
        tests = ", ".join(r["tests"])
        md.append(f"| {r['id']} | {r['source']} | {r['prd_section']} | {r['module']} | {r['logical_entity']} | {acs} | {tests} |")
    return "\n".join(md) + "\n"

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

def cmd_trace(args):
    project_root = find_project_root(os.getcwd())
    config = load_governance_config(project_root, getattr(args, "config", None))
    checks = []
    status = "pass"
    exit_code = 0

    const_path, configured_trace_source, _ = get_governance_paths(project_root, config)

    file_hash = None
    if os.path.exists(const_path):
        file_hash = update_constitution_hash(const_path, project_root, config)
        checks.append({
            "name": "trace",
            "status": "pass",
            "severity": "P3",
            "summary": "自动更新 constitution.md 联合治理哈希成功",
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

    trace_source = args.source
    if not trace_source:
        trace_source = configured_trace_source

    if os.path.exists(trace_source):
        try:
            requirements = parse_traceability_source(trace_source)
            if requirements:
                md_content = generate_traceability_md(requirements, file_hash)
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
                    "summary": "解析追踪源未找到有效需求条目",
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
            "summary": "未找到追踪源，跳过追踪矩阵生成",
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

def cmd_install_git_hook(args):
    project_root = find_project_root(os.getcwd())
    git_dir = os.path.join(project_root, ".git")
    if not os.path.exists(git_dir):
        print(json.dumps({
            "status": "fail",
            "summary": "未找到 .git 目录，无法安装 Git Hook。请确保在 Git 仓库根目录中运行此命令。"
        }, indent=2, ensure_ascii=False))
        sys.exit(1)
        
    hooks_dir = os.path.join(git_dir, "hooks")
    os.makedirs(hooks_dir, exist_ok=True)
    
    pre_commit_path = os.path.join(hooks_dir, "pre-commit")
    
    script_content = """#!/bin/sh
# Automatically generated by hookctl.py Git Hook Installer
# Runs preflight and finalize checks before committing

echo "========================================="
echo "🔍 Running Git Pre-Commit Governance Hooks..."
echo "========================================="

# Run hookctl preflight and finalize
python hooks/hookctl.py preflight --module all
PREFLIGHT_RET=$?
if [ $PREFLIGHT_RET -ne 0 ]; then
    echo "❌ pre-commit check failed (Preflight blocked). Commit aborted."
    exit $PREFLIGHT_RET
fi

python hooks/hookctl.py finalize --module all
FINALIZE_RET=$?
if [ $FINALIZE_RET -ne 0 ]; then
    echo "❌ pre-commit check failed (Finalize blocked). Commit aborted."
    exit $FINALIZE_RET
fi

echo "✅ All governance hooks passed successfully."
exit 0
"""
    try:
        with open(pre_commit_path, "w", newline="\n", encoding="utf-8") as f:
            f.write(script_content)
        if os.name != 'nt':
            run_cmd(f'chmod +x "{pre_commit_path}"')
            
        report = {
            "status": "pass",
            "summary": "Git pre-commit hook 安装成功！",
            "checks": [
                {
                    "name": "install-git-hook",
                    "status": "pass",
                    "severity": "P3",
                    "summary": f"成功写入 pre-commit 钩子至 {os.path.relpath(pre_commit_path, project_root)}",
                    "evidence": [f"Path: {pre_commit_path}"]
                }
            ]
        }
        print(json.dumps(report, indent=2, ensure_ascii=False))
        sys.exit(0)
    except Exception as e:
        report = {
            "status": "fail",
            "summary": f"Git pre-commit hook 安装失败：{str(e)}",
            "checks": [
                {
                    "name": "install-git-hook",
                    "status": "fail",
                    "severity": "P1",
                    "summary": str(e),
                    "evidence": []
                }
            ]
        }
        print(json.dumps(report, indent=2, ensure_ascii=False))
        sys.exit(2)

def main():
    parser = argparse.ArgumentParser(description="Hook Control Tool (hookctl) for AI Project Build Process")
    subparsers = parser.add_subparsers(dest="action", required=True, help="Action to perform")
    
    # Preflight subparser
    parser_pre = subparsers.add_parser("preflight", help="Run preflight checks before launching Agent")
    parser_pre.add_argument("--module", required=True, help="Module name to run checks on")
    parser_pre.add_argument("--lite", action="store_true", help="Lite mode")
    parser_pre.add_argument("--level", choices=sorted(PROJECT_LEVELS), help="Governance level")
    parser_pre.add_argument("--config", help="Path to governance config file")
    
    # Finalize subparser
    parser_fin = subparsers.add_parser("finalize", help="Run finalize checks and cleanup after Agent run")
    parser_fin.add_argument("--module", required=True, help="Module name to run checks on")
    parser_fin.add_argument("--lite", action="store_true", help="Lite mode")
    parser_fin.add_argument("--level", choices=sorted(PROJECT_LEVELS), help="Governance level")
    parser_fin.add_argument("--config", help="Path to governance config file")
    parser_fin.add_argument("--test-command", help="Override verification command for this finalize run")
    
    # Trace subparser
    parser_tr = subparsers.add_parser("trace", help="Generate/update traceability matrix and update constitution hash")
    parser_tr.add_argument("--source", help="Path to traceability-source.json or traceability-source.yaml")
    parser_tr.add_argument("--config", help="Path to governance config file")
    
    # Security subparser
    parser_sec = subparsers.add_parser("security", help="Run static security scan for secrets")
    parser_sec.add_argument("--module", help="Limit scan to specific module")
    parser_sec.add_argument("--config", help="Path to governance config file")

    # Install git hook subparser
    parser_inst = subparsers.add_parser("install-git-hook", help="Install local Git pre-commit hook")
    
    args = parser.parse_args()

    if args.action == "preflight":
        cmd_preflight(args)
    elif args.action == "finalize":
        cmd_finalize(args)
    elif args.action == "trace":
        cmd_trace(args)
    elif args.action == "security":
        cmd_security(args)
    elif args.action == "install-git-hook":
        cmd_install_git_hook(args)

if __name__ == "__main__":
    main()
