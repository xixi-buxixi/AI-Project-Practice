---
name: project-governance
description: Manage AI workflow, stage gates (grill-me, goal-me), project governance levels (lite, standard, enterprise), hook validation, and traceability.
risk: safe
source: workspace
---

# Project Governance and Build Process

This skill coordinates the project build process, AI workflow, stage gates, governance levels, and hook verification. It uses **Progressive Disclosure** to keep the context size small while ensuring the AI complies with project governance rules.

## Core Rules Reference Guide (Progressive Disclosure)

When executing tasks in this project, do not load all documentation at once. Identify the current stage or task type, and read the specific detailed document from the `references/` directory only when needed:

1. **AI Guide & Stage Gates (`grill-me`, `goal-me`)**
   - **When to read**: When initiating a new project/phase, resolving workflow disputes, or clarifying requirements/goals.
   - **File**: [AI指导.md](file:///c:/Users/15070/Desktop/Project Build Process/.agents/skills/project-governance/references/AI指导.md)
   - **Key Actions**: Perform "Grill Gate" to clarify requirements and "Goal Gate" to lock milestones.

2. **Requirements Phase (需求设计阶段)**
   - **When to read**: When writing, modifying, or reviewing product requirements documents (PRD) or feature specs.
   - **File**: [需求文档设计流程.md](file:///c:/Users/15070/Desktop/Project Build Process/.agents/skills/project-governance/references/需求文档设计流程.md)

3. **Interface Phase (接口设计阶段)**
   - **When to read**: When defining, updating, or reviewing REST/GraphQL API specifications, contracts, or backend interfaces.
   - **File**: [接口文档设计流程.md](file:///c:/Users/15070/Desktop/Project Build Process/.agents/skills/project-governance/references/接口文档设计流程.md)

4. **Project Initialization Phase (项目初始化结构)**
   - **When to read**: When setting up a new project directory structure, configuring base directories, or governing directory architecture.
   - **File**: [最优项目初始化结构.md](file:///c:/Users/15070/Desktop/Project Build Process/.agents/skills/project-governance/references/最优项目初始化结构.md)

5. **CI/CD & Git Hooks Integration**
   - **When to read**: When configuring or debugging Git hooks, pre-commit validations, preflight checks, or CI environment configurations.
   - **File**: [ci-git-hooks.md](file:///c:/Users/15070/Desktop/Project Build Process/.agents/skills/project-governance/references/ci-git-hooks.md)

6. **Full Workflow & Governance Dispute Resolution**
   - **When to read**: When encountering governance level mismatches, audit failures, or deep build flow questions.
   - **File**: [AI项目构建流程.md](file:///c:/Users/15070/Desktop/Project Build Process/.agents/skills/project-governance/references/AI项目构建流程.md)

---

## Workspace Governance Levels

Refer to [AI_RULES_SUMMARY.md](file:///c:/Users/15070/Desktop/Project Build Process/AI_RULES_SUMMARY.md) and `.governance.yaml` for governance configurations.
- **lite**: Minimum requirements boundary, smoke test, manual final approval.
- **standard**: Config-driven paths, security scan, syntax/test checks, read-only review.
- **enterprise**: Structured tracing, governance hash signing, audit score, red-blue review, strict safety gates.

## Validation & Verification Hooks

Run verification commands prior to finishing a stage:
- **Security Check**: `python hooks/hookctl.py security`
- **Preflight Check**: `python hooks/hookctl.py preflight --module all --level standard`
- **Finalize Check**: `python hooks/hookctl.py finalize --module all --level lite`
- **Traceability Matrix**: `python hooks/hookctl.py trace`
