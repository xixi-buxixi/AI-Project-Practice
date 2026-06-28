# -*- coding: utf-8 -*-

import copy
import json
import math
import os
import re
import subprocess
import sys

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

def _run_cmd(cmd, cwd=None):
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


def run_cmd(cmd, cwd=None):
    hookctl_module = sys.modules.get("hookctl")
    override = getattr(hookctl_module, "run_cmd", None) if hookctl_module else None
    if override is not None and override is not run_cmd:
        return override(cmd, cwd)
    return _run_cmd(cmd, cwd)

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

def get_module_paths(project_root, module_name=None, config=None):
    module_config = get_module_config(config, module_name)
    configured_paths = module_config.get("paths") or []
    if configured_paths:
        return [resolve_config_path(project_root, p) for p in configured_paths]
    return [get_module_dir(project_root, module_name)]

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
