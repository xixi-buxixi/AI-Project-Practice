# AI Rules Summary

> 默认入口：AI 在普通开发轮次优先读取本摘要和 `.governance.yaml`。只有进入需求、接口、初始化、审计或高风险变更阶段时，才按需读取对应长文档。

## Core Workflow

1. 先确认当前任务目标、完成标准、允许修改范围、验证命令，并核对并对齐 `agent.md` 中的运行环境。
2. 能通过仓库文件、配置或代码判断的问题，先读取再行动，不把可发现事实转交给用户。
3. 修改代码前检查现有实现、dirty diff 和相关模板，保持改动最小且集中。
4. 开发完成前运行可用验证命令，并报告实际命令与结果。
5. 不覆盖或回退用户已有改动；遇到无关 dirty 文件，只记录并绕开。

## Governance Levels

- `lite`：适合原型、小工具和一次性脚本。只要求最小需求边界、smoke test、安全检查和人工最终裁决。
- `standard`：默认级别。启用配置驱动的路径边界、基础安全扫描、语法/测试验证和只读审查；不默认启用阻断式治理哈希。
- `enterprise`：高风险或长期维护项目。启用结构化追踪、治理哈希签署、审计评分、红蓝审查和更严格安全门禁。

项目级默认值写在 `.governance.yaml`。命令行可用 `--level lite|standard|enterprise` 覆盖；旧的 `--lite` 等同于 `--level lite`。

## File Intake Rules

- 普通开发默认读取：`AI_RULES_SUMMARY.md`、`.governance.yaml`、相关模块文件、相关测试。
- 需求阶段按需读取：`需求文档设计流程.md`。
- 接口阶段按需读取：`接口文档设计流程.md`。
- 初始化或目录治理阶段按需读取：`最优项目初始化结构.md`。
- 全流程或治理争议时再读取：`AI指导.md`、`AI项目构建流程.md`。

## Safety And Hygiene

- 禁止在源码、测试、脚本、文档或日志中硬编码真实 secret、API key、token、密码、私钥和连接串。
- 真实凭证只能放入本地 `.env` 或等价的 ignored 配置；版本库只保留 `.env.example` 等非密钥示例。
- 安全扫描支持 `# nosec` / `// nosec` 标记明确误报，但不得用它隐藏真实凭证。
- 临时验证脚本、测试日志和生成 fixtures 用完即删；永久测试必须服务于项目行为回归。

## Traceability

- Lite/Standard 可用轻量 Markdown 需求 ID 和代码注释追踪，但不应为了普通业务迭代制造大量代码噪声。
- Enterprise 使用结构化追踪源，优先 `traceability-source.json`，兼容 `traceability-source.yaml`。
- 追踪矩阵由工具生成，不手改 `traceability.generated.md`。

## Hook Commands

- 安全扫描：`python hooks/hookctl.py security`
- 前置检查：`python hooks/hookctl.py preflight --module all --level standard`
- 后置检查：`python hooks/hookctl.py finalize --module all --level lite`
- 追踪生成：`python hooks/hookctl.py trace`

`hookctl.py` 读取 `.governance.yaml` 中的模块、路径、语言和命令配置；新增技术栈或改用自定义 lint/test runner 时，优先改配置，不改核心脚本。
