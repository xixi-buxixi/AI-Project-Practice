# -*- coding: utf-8 -*-

import fnmatch
import json
import os
import shutil
import sys

from .config import CLEANUP_WHITELIST, find_project_root, get_quarantine_dir, run_cmd

def is_hook_managed_state_path(path):
    norm_path = os.path.normpath(path).replace("\\", "/")
    return (
        norm_path == ".agent/state/cycles.json" or
        norm_path == ".agent/state/cycles.json.lock" or
        norm_path.endswith("/.agent/state/cycles.json") or
        norm_path.endswith("/.agent/state/cycles.json.lock")
    )

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
