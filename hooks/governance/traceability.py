# -*- coding: utf-8 -*-

import json
import os
import sys

from .config import find_project_root, load_governance_config, read_structured_file
from .integrity import get_governance_paths, update_constitution_hash

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
