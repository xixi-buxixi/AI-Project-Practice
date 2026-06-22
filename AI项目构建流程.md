# AI 项目构建流程通用规范 (合并版)

本规范定义了一套基于项目规模与风险的分级治理流程，旨在通过“文档 + 契约 + Hook + 审查闭环”的方式，将人类愿景高效收敛为 AI 可执行的代码与文档契约。

> **主规范声明**：本文件是项目构建流程的唯一主入口。`需求文档设计流程.md` 与 `接口文档设计流程.md` 是阶段细化规范；`最优项目初始化结构.md` 是初始化结构备忘。

> **统一入口声明**：新项目或新阶段开始时，AI 必须先读取 `AI指导.md`。支持斜杠命令的工具优先使用 `/grill-me`、`/grill-me-doc` 与 `/goal`；不支持时必须使用 `AI指导.md` 中的兼容提示词模拟同等流程。

---

## 1. 核心设计原则

1.  **项目分级治理**：拒绝一刀切。根据项目规模、风险和周期，划分为 **Lite (轻量级)**、**Standard (标准级)** 与 **Enterprise (企业级)** 三个执行级别。
2.  **上下文隔离 (Context Isolation)**：子 Agent 的工作空间被限制在各自模块的 `src/<module_name>/` 目录下，只读取局部上下文，防止全局大文档导致 Token 爆满和思维混乱（Scheme B 高内聚布局）。
3.  **Token 防爆校验机制 (Token Saving Guardrails)**：总览协调者 (OrchestratorAgent) 默认通过本地自动化 Hook 脚本（零 Token）或审查 Agent 的结构化报告判定结果。遇到 P0/P1、跨模块冲突、疑难失败、安全问题或审查报告证据不足时，可以定向阅读相关源码片段，避免“完全不读代码”导致总控失明。
4.  **有状态执行者与无状态审查者 (Stateful Executors & Stateless Reviewers)**：
    *   **执行子 Agent**：在任务通过最终审查前保持存活，保留本地编译和会话上下文，提升连续修复效率。
    *   **审查子 Agent**：采用“即用即建、用完即毁”的无状态模式，专注于客观审计，防止历史会话干扰审查判定。
5.  **安全清理而非盲删 (Safe Cleanup)**：后置 Hook 只允许清理白名单临时产物，例如 `.agent-temp/`、`tmp/ai-*`、`*.debug.log`、`*.scratch.*`。其他未追踪文件必须进入报告或隔离目录，严禁直接删除，避免误删用户刚创建的有效文件。
6.  **扩展点前置治理 (Extensibility First)**：在需求和契约阶段主动识别平台、渠道、供应商、内容类型、支付方式、导入导出格式、AI 工具、业务策略等变化维度，并为每个扩展点选择 E0-E4 强度。代码构建阶段必须按强度选择枚举、策略、工厂、适配器、插件、注册表、规则引擎或事件机制，禁止把持续增长的业务差异堆成 `if/else` 或 `switch/case`。
7.  **Grill Gate 与 Goal Gate**：任何阶段开始前必须先通过 Grill Gate 澄清模糊项，再通过 Goal Gate 锁定当前阶段目标、完成条件和阻塞条件。支持 `/grill-me`、`/grill-me-doc`、`/goal` 的工具应直接使用；不支持时使用 `AI指导.md` 中的兼容提示词。

---

## 2. 项目规模分级与满意度对齐

项目启动前，必须根据以下矩阵进行流程裁剪裁决，确定执行级别和任务满意度默认基线：

### 2.1 分级判定矩阵

| 级别 | 适用项目 | 建议周期 | 风险特征 | 默认满意度基线 |
| :--- | :--- | :--- | :--- | :--- |
| **Lite** | 单页应用、小工具、自动化脚本、个人原型、一次性数据处理 | 小于 1 周 | 低风险、单人维护、无外部用户影响、模块数 $\le 5$ | **Average** (一般 - 轻量验证) |
| **Standard** | 小系统、微服务、单端 Web/App、内部工具、轻量商业 MVP | 1 到 4 周 | 中等风险、有清晰模块边界、有基本多角色协作 | **Qualified** (合格 - 自动化首检) |
| **Enterprise** | 多团队项目、金融/安全核心模块、长期维护系统、复杂 AI Agent 平台 | 大于 4 周 | 高风险、强合规审计、多团队跨角色深度协作 | **Great** (优秀 - 红蓝审计通道) |

### 2.2 升级触发条件
*   **Lite $\rightarrow$ Standard**：Lite 执行中出现模块数超过 5 个、需求反复变更、物理契约复杂或审查问题持续存在。
*   **Standard $\rightarrow$ Enterprise**：Standard 项目连续 3 轮审查仍存在 P0/P1 问题，或项目中期引入了金融、安全、隐私等高危属性。

### 2.3 任务满意度 (Satisfaction Level) 与验证深度映射
开发任务的校验流水线深度可根据下表动态切换（支持任务级重写）：

*   **档位 1：一般 (Average / Prototype)**：轻量验证通道。子 Agent 汇报后，总 Agent 执行 `hooks/finalize.py --lint` 和至少一个 smoke test（如启动、帮助命令、核心函数最小调用或页面加载检查）。若通过，标记为“已完成 (Done)”，不实例化审查 Agent。
*   **档位 2：合格 (Qualified / MVP)**：自动化首检通道。子 Agent 汇报后，总 Agent 在本地命令行执行 `hooks/finalize.py --test` 编译并运行核心单元测试，只读取测试日志总结（零 Token 源码阅读），通过则标记为“已完成 (Done)”。
*   **档位 3：优秀 (Great / Production)**：独立红蓝审计通道。通过首检后，总 Agent 实例化无状态的**审查子 Agent (ReviewAgent)**，注入验收清单和待审目录。审查子 Agent 运行深度边界测试并生成结构化审查报告，总 Agent 只读取报告做出通过/打回判定。

### 2.4 扩展强度与构建模式映射

扩展强度由需求阶段初判，接口阶段固化为契约，构建阶段按下表落地。AI 不得跳过强度选择直接编码。

| 强度 | 构建模式 | 适用约束 | 验证要求 |
|---|---|---|---|
| E0 无需抽象 | 直接实现 | 明确只有一个实现且不会扩展 | Decision Log 记录不抽象原因 |
| E1 轻量枚举 | 枚举/配置表/简单映射 | 成员少、变化低、差异不影响流程 | 枚举边界测试，禁止散落魔法字符串 |
| E2 策略/适配器 | Strategy、Adapter、Factory Method、Provider Interface | 成员会增加，差异影响校验、流程、外部调用或错误处理 | 新增一个成员只新增策略/适配器与注册项，核心流程测试不改写 |
| E3 插件化/注册表 | Registry、Plugin Contract、Abstract Factory、Capability Declaration | 第三方或后续团队独立接入，成员持续增长 | 注册表 Schema、能力声明、插件启停和兼容性测试 |
| E4 规则引擎/工作流 | Rule Engine、Workflow、Policy Pipeline、Event-driven Architecture | 规则组合复杂、频繁调整、需要审计或非开发配置 | 规则冲突、优先级、回滚、审计和灰度测试 |

反分支堆积规则：

- 同一变化维度出现第 2 个实现时，必须评估 E1 是否升级到 E2。
- 同一变化维度出现第 3 个实现时，默认禁止继续新增并列 `if/else` 或 `switch/case`；例外必须写入 `docs/decisions/decisions-and-pending-log.md`。
- 允许在策略选择入口保留短小分派逻辑，但业务差异必须下沉到独立策略、适配器、插件或规则对象。
- ReviewAgent 必须把“新增平台/渠道/供应商时需要修改核心流程”视为 P1 扩展性缺陷。

### 2.5 裁剪落地原则
*   **Lite**：只保留 `REQUIREMENTS.md`、`task.md`、最小契约章节、轻量 Hook 和 smoke test。禁止引入多 Agent 审查、追踪矩阵和复杂目录。
*   **Standard**：默认只启用三类角色：需求/契约生成者、实现者、只读审查者。`RegressionAgent` 和 `Auditor` 可按风险启用，但不作为默认必选。
*   **Enterprise**：启用完整角色、结构化追踪、审计评分、红蓝循环、变更签署和安全扫描。高风险项目不能通过删除文档来降级，只能通过自动化降低人工维护成本。
*   裁剪只能减少文档数量和审查角色，不能取消需求边界、异常路径、安全检查、可运行验证和人工最终裁决。

---

## 3. 目录与文件结构规范

项目目录结构与文档的细粒度，取决于所选的执行级别。Standard 和 Enterprise 级别采用 **Scheme B 高内聚布局**，实现规则与代码同版本控制。

### 3.1 Lite 级文件结构 (扁平结构)
```text
project-root/
├── REQUIREMENTS.md           # 合并项目目标、边界限制、Out of Scope、设计及验收标准
├── README.md
├── task.md                   # 扁平 TODO 任务看板
├── .env.example
├── .gitignore
└── hooks/
    └── lite_hook.py          # 极简前置与后置 Linter 校验脚本
```

### 3.2 Standard 级文件结构 (适度合并版 - Scheme B)
```text
project-root/
├── AI_AGENT_CONTRACT.md      # AI 协作契约与全局执行底线规则
├── REQUIREMENT_CONTRACT.md   # 需求阶段薄契约：冻结资产、准入条件和阻塞条件
├── agent.md                  # 项目稳定导航（全局上下文、模块边界、启动规则）
├── MODULE_MAP.md             # 模块路由表（连接需求、接口契约与负责 Agent）
├── README.md
├── tasks.md                  # 全局交付级任务看板（总 Agent 维护摘要，不承载高频临时状态）
├── .env.example
├── .gitignore
│
├── docs/                     # 静态与冻结文档资产（Standard 级别合并）
│   ├── requirements/
│   │   └── overview.md       # 合并 PRD、核心原则、简短术语表与边界限制
│   ├── architecture.md       # 合并模块划分、逻辑实体模型与事件流
│   ├── contracts/
│   │   └── overview.md       # 合并当前项目类型对应的物理接口或交互契约
│   ├── decisions/
│   │   └── decisions-and-pending-log.md # 记录架构决策、延期与 Pending 问题
│   └── reviews/              # 质量审查输出目录
│       └── review-round-xxx.md
│
├── hooks/                    # 强力自动化 Hook 目录
│   ├── preflight.py          # 前置检查脚本
│   └── finalize.py           # 后置清理校验脚本（检查语法、Linter、用完即删清理）
│
├── .agent/                   # 本地 Agent 状态目录，必须加入 .gitignore
│   ├── state/
│   │   └── cycles.json       # 轮次、失败分类与模块锁状态
│   └── quarantine/           # 未识别未追踪文件的隔离区，不自动删除
│
└── src/                      # 业务源码目录 (高内聚 Scheme B)
    └── <module_name>/
        ├── agents.md         # 模块静态规则（可修改路径、API边界、特定约束）
        ├── tasks.md          # 模块动态看板（执行子 Agent 更新总结与自测命令）
        └── ... (业务代码与局部单元测试)
```

### 3.3 Enterprise 级文件结构 (完整隔离版)
Enterprise 级别不合并核心治理文档，便于细粒度变更审计、哈希校验和多团队开发。

```text
project-root/
├── AI_AGENT_CONTRACT.md      
├── REQUIREMENT_CONTRACT.md
├── agent.md                  
├── MODULE_MAP.md             
├── README.md
├── tasks.md                  
├── .env.example
├── .gitignore
│
├── docs/                     
│   ├── requirements/         # 细粒度需求文档，严禁合并
│   │   ├── constitution.md   # 核心不可变原则、语义版本与冻结状态
│   │   ├── glossary.md       # 项目专业术语表
│   │   ├── overview.md       # 业务总览 PRD
│   │   ├── out-of-scope.md   # 明确不做的范围清单（供回归扫描）
│   │   └── modules/
│   │       └── <module-name>.md # 各模块独立 PRD（包含目标、边界与验收标准）
│   │
│   ├── interfaces/           # 逻辑接口文档目录
│   │   ├── logical-model.md  # 逻辑实体、核心属性及模块间数据责任
│   │   └── events.md         # 业务事件、状态机转换流与失败分支
│   │
│   ├── contracts/            # 物理接口或交互契约目录
│   │   ├── overview.md
│   │   ├── extensions/       # E2+ 扩展点契约，如平台/渠道/供应商/格式/工具
│   │   │   └── <extension-point>.md
│   │   └── modules/
│   │       └── <module-name>.md # 各模块具体物理契约（如 HTTP API / CLI 参数 / 插件事件）
│   │
│   ├── traceability/         # 双向追踪目录
│   │   ├── traceability-source.yaml # 需求-代码-测试追踪元数据
│   │   └── traceability.generated.md # 自动生成的追踪矩阵文件
│   │
│   ├── decisions/
│   │   ├── ADR-0001-initial-architecture.md # 架构决策记录
│   │   └── decisions-and-pending-log.md
│   └── reviews/
│       └── review-round-xxx.md
│
├── hooks/                    
│   ├── preflight.py          
│   ├── finalize.py           
│   └── security_scan.py      # 独立静态安全扫描 Hook
├── .agent/                   # 本地 Agent 状态目录，必须加入 .gitignore
│   ├── state/
│   │   └── cycles.json
│   └── quarantine/
│
└── src/                      # 业务源码目录 (高内聚 Scheme B)
    └── <module_name>/
        ├── agents.md
        ├── tasks.md
        ├── extensions/       # 本模块扩展实现：策略、适配器、插件、注册表
        │   ├── registry.*
        │   └── <member>.*
        └── ...
```

---

## 4. 核心文件与职责边界

### `AI_AGENT_CONTRACT.md` (原 `AGENTS.md`)
AI 编码工具必须严格遵守的全局底线：
*   **动作强制**：Agent 修改代码必须直接修改，禁止输出补丁（patch）文本或“请手动修改”的指示。
*   **只读审查**：审查子 Agent (ReviewAgent) 仅有只读权限，绝对不得修改任何文件或自动修复问题。
*   **前置对齐**：修改前必须阅读对应模块的 `agents.md`、需求和物理契约。若存在文档冲突，先更新文档，严禁盲目猜测实现。
*   **清理强制**：完成编码或审查前，必须运行后置 Hook。Hook 只允许删除白名单临时产物；未识别的未追踪文件必须报告或隔离，不能直接删除。
*   **配置隔离**：严禁将密钥、密码直接写入代码或提示词，敏感配置必须进入本地 `.env`，提交至仓库的只能是 `.env.example` 占位文件。

### `REQUIREMENT_CONTRACT.md`
需求阶段薄契约。只记录冻结需求资产的读取顺序、冻结版本、进入接口/构建阶段的准入条件和阻塞条件；不复制 PRD 正文，也不承载 AI 编码执行底线。

### `agent.md`
项目稳定导航。仅包含不易发生频繁变化的信息（不维护动态任务）：
*   项目目标和所处阶段。
*   静态模块清单和清晰边界。
*   核心文档的路径索引。
*   总览协调者 (OrchestratorAgent) 与模块 Agent 的协作启动方式。

### `MODULE_MAP.md`
连接需求与物理源码的路由表。包含：模块名称、负责 Agent、对应需求文档路径、对应物理契约路径、依赖模块、交付物以及验收标准。

---

## 5. Hook 机制与循环轮次管理

### 5.1 循环轮次计数器

为了防止环境配置、语法修正等基础问题耗尽业务开发的熔断轮次，标准与企业级流程采用**多维度计数器**：

*   `attempt_count`：只要 Agent 产生了代码变更并触发后置 Hook，无论编译/测试成功与否，均递增该值。
*   `invalid_build_cycle_count`（业务无效循环计数器）：当代码可以成功编译或启动，但业务单元测试不通过、物理契约校验失败或验收路径未走通时递增。**该计数器达到 5 次时触发模块熔断**，挂起任务并由总览协调者或人工介入。
*   `infra_failure_count`（环境/依赖失效计数器）：当依赖缺失、编译配置、Linter 格式或环境问题导致构建失败时递增。**该计数器达到 3 次时触发环境熔断**，必须暂停业务编码，优先修复依赖、运行环境或测试脚本。

*(注：Lite 级别不使用上述复杂的多计数器，统一使用单一 Cycle 计数器，上限为 5 轮。)*

### 5.2 前置与后置 Hook 职责
*   **前置 Hook (`hooks/preflight.py`)**：启动子 Agent 前执行。验证源码路径是否存在、静态规则 `agents.md` 是否就绪、本地依赖和运行环境是否正常。
*   **后置 Hook (`hooks/finalize.py`)**：子 Agent 编码结束或汇报前执行。
    1.  运行项目既定语法分析（Linter）与格式化工具。
    2.  清理白名单临时产物，并把未识别未追踪文件写入报告或移入 `.agent/quarantine/`。
    3.  检查模块 `tasks.md` 格式规范性，包括 `Done Summary` 及自测命令的完整性。

### 5.3 Hook 输入输出契约
所有 Hook 必须具有稳定、可机器读取的输出，不能只打印自然语言日志。

```json
{
  "status": "pass | fail | blocked",
  "module": "<module_name>",
  "checks": [
    {
      "name": "lint | test | contract | security | cleanup | task_state",
      "status": "pass | fail | skipped",
      "severity": "P0 | P1 | P2 | P3",
      "summary": "<短摘要>",
      "evidence": ["<文件路径或命令摘要>"]
    }
  ],
  "counters": {
    "attempt_count": 1,
    "invalid_build_cycle_count": 0,
    "infra_failure_count": 0
  },
  "artifacts": {
    "deleted": ["<仅限白名单临时文件>"],
    "quarantined": ["<未识别未追踪文件>"],
    "reports": ["<报告文件路径>"]
  }
}
```

退出码约定：

| 退出码 | 含义 | 后续动作 |
|---:|---|---|
| 0 | 所有阻塞检查通过 | 可进入下一步 |
| 1 | 业务或契约检查失败 | 递增 `invalid_build_cycle_count` |
| 2 | 环境、依赖、工具链或格式化失败 | 递增 `infra_failure_count` |
| 3 | 安全红线、权限越界或误删风险 | 立即阻塞并人工介入 |

### 5.4 状态文件与提交边界
*   高频运行状态、轮次计数、模块锁和临时报告默认写入 `.agent/state/`，该目录必须加入 `.gitignore`。
*   `tasks.md` 只记录交付级摘要、当前阻塞和最终验证命令，不承担每次尝试的完整日志。
*   长期有效的技术取舍进入 `docs/decisions/decisions-and-pending-log.md`，不要堆在 `tasks.md` 中。
*   需要提交的审查结论只保留结构化摘要；大体量原始日志默认不提交，除非 Human Owner 明确要求保留。

---

## 6. 需求双向追踪机制 (Traceability)

为了保证“所想即所得”，构建流程必须包含需求追踪。

*   **Lite / Standard 级（轻量级 Markdown 批注）**：
    *   在需求文档（如 `overview.md`）中使用 `REQ-xxx` 标识声明：
        ```markdown
        ## REQ-001: 用户能够通过手机号登录
        - 优先级: P1
        - 验收标准:
          - [ ] 输入合法手机号发送验证码
          - [ ] 输入正确验证码完成登录
        ```
    *   在对应实现代码或测试代码中加入注释声明：
        ```typescript
        // maps: REQ-001
        ```
    *   使用本地脚本定期扫描，自动生成需求追踪报告 (Traceability Report)，呈现哪些需求已被代码/测试覆盖，哪些依然缺失。
*   **Enterprise 级（YAML 结构化追踪）**：
    *   维护独立的 `/docs/traceability/traceability-source.yaml`，用 YAML 结构化维护 `需求 -> 逻辑模型 -> 物理契约 -> 源码文件 -> 测试文件` 的双向链条。
    *   通过工具自动构建出矩阵文件 `traceability.generated.md` 进行阻断式静态合规检查。

---

## 7. 推荐的标准/企业构建流程 (Standard & Enterprise)

Standard 级（默认）与 Enterprise 级项目必须遵循以下阶段执行：

### 阶段 0：项目意图确认
*   **目标**：明确项目一句话目标、核心使用者、最小可行性产品 (MVP) 范围及明确不做的边界（超出范围 - Out of Scope）。
*   **检查点**：是否可以用 3 到 5 条验收标准描述项目成功。判断项目类型（Web/API、CLI、移动端、插件、自动化脚本、数据处理、AI Agent、游戏等），不能默认所有项目都按 Web API 架构构建。
*   **扩展性检查点**：必须询问未来可能扩展的维度，并初步判断 E0-E4 强度。典型触发词包括“多平台”“多渠道”“以后加平台”“多供应商”“多格式”“多模型”“多支付”“多内容类型”“规则可配置”。如果用户需求中出现这些信号，AI 必须主动提出扩展模式选择，而不能默认以后继续加条件判断。
*   **Grill Gate**：阶段 0 不允许直接输出最终 PRD。AI 必须按 `AI指导.md` 进行一问一答式追问，直到项目类型、MVP、Out of Scope、扩展点和验收标准足够清晰。

### 阶段 1：确认预启动目录结构
*   按照所选的级别，初始化对应的目录结构（如 Scheme B 布局），此时不编写任何业务源码。
*   由总览协调者检查目录完整性。
*   **Goal Gate**：初始化前必须明确本轮目标是“创建结构和上下文”，而不是实现业务功能。

### 阶段 2：编写需求文档与架构设计
*   **Standard 级**：编写合并版的 `docs/requirements/overview.md` 与 `docs/architecture.md`。
*   **Enterprise 级**：
    1.  编写 `constitution.md`（核心不可变原则、MVP 边界、版本）。
    2.  增量维护 `glossary.md`（术语表）。
    3.  编写 `overview.md` 和各模块的 `modules/<module-name>.md`（明确不做什么）。
    4.  编写逻辑实体与事件流文档 `interfaces/logical-model.md` 与 `interfaces/events.md`，从逻辑层面闭环业务，严禁混入具体 HTTP 方法或数据库字段等物理细节。
*   **扩展性产出**：需求文档必须包含扩展点清单、扩展强度、推荐模式、新增成员允许修改和禁止修改的边界。架构文档必须说明扩展点归属模块、核心流程与扩展实现之间的边界。

### 阶段 3：生成物理接口或交互契约
*   根据项目交付形态（如 CLI 命令行参数、HTTP API、AI Agent 工具契约等），在 `docs/contracts/` 下输出物理契约。
*   反向核对物理契约是否完美承载了阶段 2 的状态机流转与异常错误路径。
*   对 E2 及以上扩展点，必须生成统一扩展契约，包含能力声明、选择规则、注册方式、错误映射、鉴权边界和新增成员流程。

### 阶段 3.5：需求、逻辑接口与物理契约盲审 (Enterprise 必选 / Standard 高风险可启用)
在生成模块 Agent 提示词前，可由异构模型担任的审计员 (Auditor) 角色对文档进行盲审。Enterprise 级项目必须执行；Standard 级仅在安全、隐私、资金、合规、不可逆副作用或反复契约冲突时启用：
*   **打分维度**：`requirement_clarity_score`（清晰度）、`module_boundary_score`（模块边界）、`contract_consistency_score`（契约一致性）、`extensibility_design_score`（扩展性设计）、`business_closure_score`（业务闭环度）、`risk_control_score`（风险控制）。
*   **证据约束**：每个低于阈值的分数必须绑定 Gap List 证据，包括文件路径、章节、冲突描述和阻塞等级；没有证据的打分不得作为打回依据。
*   **回归检查 Agent (RegressionAgent) 扫描**：对照 `Out of Scope` 清单，采用相近语义矩阵，逐行扫描需求和契约文档，严防需求范围漂移。
*   **退出标准**：
    *   审计员未给出 P0/P1 文档缺陷，`business_closure_score` $\ge 8/10$。
    *   回归检查 Agent 扫描通过。
    *   盲审迭代最多 3 轮。若第 3 轮仍未通过，可通过决策日志 (Decisions Log) 将非 P0 问题挂起，并给出条件通过 (CONDITIONAL PASS)。

### 阶段 4：生成 Agent 提示词
*   总览协调者 (OrchestratorAgent) 读取当前最新的需求、架构和契约文档，生成/更新各模块 Agent 的配置与上下文，写入 `src/<module_name>/agents.md`。
*   每个涉及扩展点的模块 Agent 提示词必须写明：扩展点名称、强度、采用模式、注册位置、允许新增文件、禁止修改的核心流程，以及新增成员的验收命令。
*   模块 Agent 提示词必须包含本轮 Goal：目标、允许路径、完成条件、验证命令和阻塞条件。

### 阶段 5：初始化 Hook
*   配置前置 Hook（`preflight.py`）与后置 Hook（`finalize.py`），初始化 `cycles.json` 计数状态。

### 阶段 6：分阶段构建项目
*   **依赖驱动构建**：构建顺序由模块依赖决定，而非文件顺序。通用层级：
    1. 数据基础层（存储、CRUD） $\rightarrow$ 2. 核心业务层（领域服务） $\rightarrow$ 3. 物理契约适配层（HTTP API / CLI 入口） $\rightarrow$ 4. 前端交互层 $\rightarrow$ 5. 集成与配置层。
*   **并行开发约束**：
    1.  并行任务必须位于不同模块或不同允许路径集合。
    2.  每个模块在 `.agent/state/cycles.json` 中声明 `locked_by`、`task_id` 和 `allowed_paths`。
    3.  跨模块修改必须由总览协调者先更新 `MODULE_MAP.md`、相关契约和受影响模块的 `agents.md`。
    4.  如果两个 Agent 需要修改同一文件，必须串行执行，不允许用后完成者覆盖先完成者。
*   **模块构建循环**：
    1.  运行前置 Hook。
    2.  读取模块静态规则 `agents.md`、对应需求和物理契约。
    3.  根据扩展强度选择实现模式：E1 使用枚举/配置映射；E2 使用策略/适配器/工厂；E3 使用注册表/插件契约/能力声明；E4 使用规则管线/工作流/事件驱动。不得把同一扩展维度的差异直接堆入核心业务流程。
    4.  实现业务逻辑，编写局部单元测试。
    5.  运行后置 Hook（计数器递增，清理垃圾文件）。
    6.  若达到 5 轮熔断上限，自动挂起并请求总览协调者同步上下文或引入人工介入。

### 阶段 7：只读审查与修复循环
*   **Standard 级**：默认采用三角色闭环：需求/契约生成者、执行者、只读审查者。审查者只读审查代码、配置和测试覆盖度，输出标准化问题清单至 `docs/reviews/`，由执行者修复。仅当出现范围漂移、契约冲突或高风险变更时，才额外启用 `RegressionAgent` 或 `Auditor`。
*   **扩展性审查**：ReviewAgent 必须检查 E2 及以上扩展点是否按契约落地；如果新增扩展成员需要修改核心流程、核心状态机或多个无关模块，应标记为 P1。若发现同一扩展维度出现三处及以上并列条件判断且没有 Decision Log 例外，也应标记为 P1。
*   **Enterprise 级 (红蓝对抗模式)**：
    *   严格执行 3 轮红蓝审查-修复循环。
    *   **红蓝熔断规则**：若第 3 轮审查仍然被打回 (REJECT)，必须强制熔断，严禁 AI 相互拉扯。总览协调者重新对齐需求与边界，必要时引入人工架构评审裁决。

### 阶段 7.5：全量集成与静态安全扫描 (安全底线)
进入功能验收前的硬门槛。总览协调者自动执行：
*   运行项目主集成测试命令。
*   执行 `security_scan.py` 或本地 Semgrep/GitLeaks，检测 `.env` 是否被忽略、`.env.example` 中是否存在真实密钥、代码中是否存在明文密码/访问令牌。
*   **一票否决**：任何发现明文密码、硬编码密钥的构建一律拒绝进入后续流程。

### 阶段 8：功能检查与交互检查 (交付形态相关)
*   根据项目交付形态进行验收：
    *   **Web UI**：检查表单校验、加载态、空状态、错误态、响应式及重连。
    *   **API 服务**：接口测试、鉴权与幂等性校验。
    *   **CLI 工具**：帮助命令、退出码、标准错误与管道输入校验。
    *   **AI Agent**：工具调用边界、记忆读写、越权防护及失败回退校验。

### 阶段 9：人工验收
*   人工检查 MVP 完成度、核心路径可用性、README 启动指南，确认无 P0/P1 问题，予以验收。

---

## 8. Lite 级轻量验证构建流程

针对 Lite 级项目，流程进行极限压缩，取消多 Agent 协作和复杂审查：

1.  **需求与边界确认**：编写扁平的 `REQUIREMENTS.md`，明确记下 MVP TODO 列表及 `Out of Scope`（超出范围限制）。
2.  **规划任务**：编写 `task.md`。
3.  **单 Agent 编码**：主 Agent 直接在该会话下进行代码编写，并配套编写基本自测命令。
4.  **运行 Hook 与 smoke test**：每次代码变更后运行 `lite_hook.py`，执行 Linter、白名单临时文件清理和最小可运行验证。Web 项目至少加载首页；CLI 至少运行 `--help` 与一个核心命令；脚本至少执行一条 dry-run 或样例输入。
5.  **AI 自检摘要**：在汇报完成前，主 Agent 必须在会话或 `task.md` 中输出如下格式的自检：
    ```markdown
    ## 自检 (Self Review)
    - 质量视角 (QA View): 是否满足 REQUIREMENTS.md 的验收指标？ [通过/失败 (PASS/FAIL)]
    - 运维视角 (SRE View): 启动、日志、配置是否正常？ [通过/失败 (PASS/FAIL)]
    - 安全视角 (Security View): 是否无明文密码与硬编码密钥？ [通过/失败 (PASS/FAIL)]
    - 待修复项 (Required Fixes): (如有，列出修复 TODO，修复后再重新自检)
      - [ ] ...
    ```
6.  **人工快速验收**：开发者运行自测命令，确认无误后合并交付。

---

## 9. 通用 Agent 提示词模板

### 9.1 总览协调者提示词模板 (OrchestratorAgent)
```markdown
# 总览协调者 (OrchestratorAgent)

你是当前项目的总览协调者。你的职责不是直接编写业务代码，而是维护项目结构、划分模块边界、保持文档一致性并维护 Agent 协作秩序。

## 必读文件
- 项目根入口 `/agent.md`
- 全局规则 `/AI_AGENT_CONTRACT.md`
- 需求薄契约 `/REQUIREMENT_CONTRACT.md`
- 模块表 `/MODULE_MAP.md`
- 静态文档 `/docs/requirements/`、`/docs/architecture.md`、`/docs/contracts/`
- 全局看板 `/tasks.md`

## 核心职责
1. 根据模块依赖关系，安排并控制模块构建子 Agent 的构建顺序。
2. 启动模块构建子 Agent 时，向其注入包含“允许修改路径、当前验收指标、满意度目标、扩展点强度和推荐模式”的激活指令。
3. 运行前置与后置 Hook 脚本，实时跟踪 cycles 状态。
4. 审查阶段读取审查子 Agent 输出的报告，指派修复任务。
5. 当报告证据不足、出现 P0/P1、跨模块冲突或安全问题时，允许定向阅读相关源码片段。
6. 维护扩展点清单，确保 E2 及以上扩展点有策略、适配器、插件、注册表或规则契约承载。
7. 发现同一扩展维度出现分支堆积时，必须暂停对应模块构建，要求先更新架构/契约或写入 Decision Log 例外。
8. 解决跨模块不一致及文档冲突。
9. 完成后更新全局 `/tasks.md` 及全局决策日志。
```

### 9.2 执行子 Agent 提示词模板 (ModuleAgent)
```markdown
# 执行子 Agent: <模块名称> (ModuleAgent)

你负责开发 `<module-name>` 模块的业务代码与局部单元测试。

## 必读文件
- 全局契约 `/AI_AGENT_CONTRACT.md`
- 需求薄契约 `/REQUIREMENT_CONTRACT.md`
- 模块路由 `/MODULE_MAP.md`
- 本模块静态规则 `/src/<module-name>/agents.md`
- 本模块动态看板 `/src/<module-name>/tasks.md`

## 核心职责
1. 只修改 `/src/<module-name>/agents.md` 允许的路径，严禁跨出本模块边界。
2. 严格遵守物理契约定义的请求/响应结构、退出码、事件和数据格式。
3. 严格遵守本模块扩展点的强度和模式：E2 使用策略/适配器/工厂，E3 使用注册表/插件/能力声明，E4 使用规则管线/工作流/事件驱动。
4. 新增平台、渠道、供应商、内容类型、支付方式、AI 工具或格式支持时，优先新增独立策略/适配器/插件和注册项，不得直接修改核心流程来追加并列条件判断。
5. 每一轮构建或测试后，必须运行后置 Hook。
6. 完成本轮次后，更新局部看板 `/src/<module-name>/tasks.md` 中的“已完成总结” (Done Summary) 和验证日志。
7. 如果 `invalid_build_cycle_count` 达到 5 轮或 `infra_failure_count` 达到 3 轮，必须停止修改，向总览协调者汇报当前状态。
```

### 9.3 只读审查子 Agent 提示词模板 (ReviewAgent)
```markdown
# 审查子 Agent (ReviewAgent)

你是当前项目的只读审查者。

## 严格限制
- 只能阅读文件、执行测试命令、检查控制台输出与日志。
- 严禁修改、创建、重命名或删除项目中的任何文件，禁止自动修复代码。

## 必读文件
- `/agent.md`、`/AI_AGENT_CONTRACT.md` 与 `/REQUIREMENT_CONTRACT.md`
- `/docs/requirements/` 与 `/docs/contracts/`
- 待审模块源码与局部单元测试

## 审查职责
1. 逐条检查当前模块的实际物理接口/命令是否符合 `docs/contracts/` 中的契约要求。
2. 校验测试用例是否覆盖了核心业务边界与异常失败路径。
3. 检查代码是否包含密钥泄露、未忽略 `.env` 等安全红线。
4. 将问题按严重等级（P0/P1/P2/P3）记录到 `/docs/reviews/review-round-xxx.md`，不提供抽象泛化的口头评价，必须给出具体的代码位置、期望行为 (Expected)、实际行为 (Actual) 和建议修复方向 (Suggested Fix)。
```

---

## 10. 迭代退出标准

一个项目或当前迭代可以认为进入“基本完善/可交付”状态，必须满足：

*   **文档一致性**：需求文档（合并版或细分版）、架构设计（包含逻辑实体/事件流）、物理契约与实际实现代码完全对齐。
*   **扩展性一致性**：PRD 中 E2 及以上扩展点已在契约和代码中落地为策略、适配器、插件、注册表、规则引擎或事件机制；新增扩展成员不需要修改核心业务流程。
*   **无分支堆积**：同一扩展维度没有三处及以上并列 `if/else` 或 `switch/case` 承载业务差异；如确需保留，必须有 Decision Log 例外和后续重构触发条件。
*   **无安全红线**：静态安全扫描 100% 通过，没有任何硬编码的真实密钥、明文测试密码或访问令牌，`.env` 已被 `.gitignore` 忽略。
*   **验收标准覆盖**：所有核心模块均已完成 `MODULE_MAP.md` 中的 MVP 验收标准。
*   **无遗留缺陷**：当前版本无 P0/P1 审查缺陷，P2 问题有明确延期排期并记入 `docs/decisions/decisions-and-pending-log.md`。
*   **熔断管控**：未发生审查死锁，或死锁熔断后已由人工重新裁决并稳定了上下文。
*   **验证通过**：全量集成测试命令通过，核心用户路径在对应交付形态下经过了端到端校验。
*   **审查证据完整**：所有 P0/P1/P2 问题均包含文件位置、期望行为、实际行为、修复方向和验证方式；评分低于阈值时必须有 Gap List 证据。
*   **自测与说明**：每个模块在 `/src/<module_name>/tasks.md` 中都有完整的自测日志总结，根目录 README.md 能够指导新人或新 Agent 一键配置并启动项目。
