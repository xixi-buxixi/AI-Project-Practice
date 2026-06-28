# 持续集成 (CI) 与 Git Hooks 集成指南

本指南介绍如何将 `hookctl.py` 静态治理工具集成到本地 Git Hooks 以及 CI 流程中，确保代码库的安全与一致性。

`hookctl.py` 默认读取仓库根目录的 `.governance.yaml`。可用 `--config <path>` 指定其他配置文件，并可用 `--level lite|standard|enterprise` 覆盖项目级治理档位；旧参数 `--lite` 仍然兼容，等同于 `--level lite`。

## 1. 本地 Git Pre-Commit Hook 集成

### 自动安装 (推荐)

您可以在仓库根目录下运行以下命令，自动在本地 `.git/hooks/pre-commit` 中安装校验钩子：

```bash
python hooks/hookctl.py install-git-hook
```

该命令会创建 pre-commit 脚本，在您每次执行 `git commit` 时，自动运行所有模块的 `preflight` 和 `finalize` 动作。如果有任何一票否决规则（如发现未加密 of `.env` 文件、明文密钥、超出修改范围等）触发，提交将会被自动拦截。

### 手动安装

若要手动配置 pre-commit 钩子，请在 `.git/hooks/pre-commit` 文件中写入以下内容，并确保其具有可执行权限：

```sh
#!/bin/sh
# 运行前置与后置治理校验

echo "========================================="
echo "🔍 Running Git Pre-Commit Governance Hooks..."
echo "========================================="

# 执行 preflight 校验所有模块
python hooks/hookctl.py preflight --module all --level standard
PREFLIGHT_RET=$?
if [ $PREFLIGHT_RET -ne 0 ]; then
    echo "❌ pre-commit 校验失败：Preflight 被阻断。"
    exit $PREFLIGHT_RET
fi

# 执行 finalize 校验所有模块
python hooks/hookctl.py finalize --module all --level standard
FINALIZE_RET=$?
if [ $FINALIZE_RET -ne 0 ]; then
    echo "❌ pre-commit 校验失败：Finalize 被阻断。"
    exit $FINALIZE_RET
fi

echo "✅ 所有治理 Hook 校验通过。"
exit 0
```

---

## 2. CI 流水线集成 (GitHub Actions / GitLab CI)

在云端构建与 CI 流水线中，建议将静态安全扫描与追踪矩阵完整性作为前置流水线门槛。

### 2.1 GitHub Actions 集成示例

在 `.github/workflows/governance-check.yml` 中配置以下工作流：

```yaml
name: Governance and Security Check

on:
  push:
    branches: [ main, dev ]
  pull_request:
    branches: [ main ]

jobs:
  check:
    runs-on: ubuntu-latest

    steps:
    - name: Checkout Code
      uses: actions/checkout@v3
      with:
        fetch-depth: 0 # 获取完整历史以供 git status 分析

    - name: Setup Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.10'

    - name: Run Static Security Scan
      run: |
        python hooks/hookctl.py security --config .governance.yaml

    - name: Run Integrity and Traceability Matrix Check
      run: |
        # Standard 默认跳过 Enterprise 级治理哈希；高风险项目可改为 --level enterprise
        python hooks/hookctl.py preflight --module all --level standard

    - name: Run Codebase Finalize and Tests
      run: |
        # 自动探测多语言环境，执行代码 linter 校验及默认测试套件
        python hooks/hookctl.py finalize --module all --level standard
```

### 2.2 GitLab CI 集成示例

在 `.gitlab-ci.yml` 中配置以下作业：

```yaml
stages:
  - check

governance_check:
  stage: check
  image: python:3.10-slim
  before_script:
    - apt-get update && apt-get install -y git
  script:
    # 1. 运行静态安全扫描，检查硬编码密钥及 unignored 敏感文件
    - python hooks/hookctl.py security --config .governance.yaml
    # 2. 运行完整性哈希校验
    - python hooks/hookctl.py preflight --module all --level standard
    # 3. 运行后置自动化编译/语法校验与单元测试
    - python hooks/hookctl.py finalize --module all --level standard
  only:
    - merge_requests
    - main
```

---

## 3. 防篡改哈希链更新流程

Enterprise 级项目如果由于需求变更需要修改 `constitution.md`、`traceability-source.json` / `traceability-source.yaml` 或 `MODULE_MAP.md`，直接提交会被 `preflight --level enterprise` 的防篡改哈希链校验阻断。Standard 级默认跳过该阻断，只保留基础边界、安全和验证。

**更新哈希链的标准流程如下**：
1. 开发者/Agent 编写或更新需求/契约配置文件。
2. 在提交代码前，在终端运行更新/签署命令：
   ```bash
   python hooks/hookctl.py trace
   ```
3. 该命令会按 `.governance.yaml` 中的路径重新计算核心文件联合防篡改哈希，并自动写回 `constitution.md` 中，同时重新输出追踪对照表 `traceability.generated.md`。追踪源优先使用 JSON，YAML 作为兼容格式保留。
4. 将更新后的 `constitution.md` 及其他改动一并执行 `git commit` 提交。
