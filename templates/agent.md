# Project Stable Navigation

> **定位**：项目稳定导航。只放置不易频繁变化的全局上下文、模块边界、启动规则，禁止维护动态任务看板。

## 1. 项目愿景与目标 (Project Vision & Goal)
*   **愿景**：[描述本项目的最终业务目标与核心价值]
*   **当前阶段**：需求设计 / 接口定义 / 结构初始化 / 模块构建 / 交付部署

## 2. 核心架构与技术栈 (Architecture & Stack)
*   **架构风格**：单体高内聚 (Scheme B) / 微服务 / Serverless / 插件化
*   **前端技术栈**：[例如：React + Vite + Vanilla CSS]
*   **后端技术栈**：[例如：Node.js + Express / Go + Gin]
*   **数据库/存储**：[例如：PostgreSQL / Redis]
*   **验证工具链**：[例如：pytest / npm test / cargo test]
*   **运行环境与依赖管理 (Runtime Environment)**:
    *   环境类型 (Type): Conda / venv / Poetry / NVM / SDKMAN / Global
    *   名称/版本 (Name/Version): [例如：my_conda_env / Node v18.16.0]
    *   解释器/执行命令前缀 (Path/Prefix): [例如：`conda run -n my_conda_env` / `nvm use 18 &&`]

## 3. 模块视图与边界 (Modules & Boundaries)
*   所有可用模块及物理归属详见 [MODULE_MAP.md](./MODULE_MAP.md)。
*   **核心安全红线**：
    1. 任何模块绝不允许把明文凭证（Token、API Key、密码）直接提交至代码或文档。
    2. 禁止未经授权跨模块修改非允许路径。

## 4. 关键文档索引 (Key Documents Index)
*   **需求薄契约**：[REQUIREMENT_CONTRACT.md](./REQUIREMENT_CONTRACT.md)
*   **需求资产总览 (PRD)**：[docs/requirements/overview.md](./docs/requirements/overview.md)
*   **接口/契约总览**：[docs/contracts/overview.md](./docs/contracts/overview.md)
*   **决策与延期日志**：[docs/decisions/decisions-and-pending-log.md](./docs/decisions/decisions-and-pending-log.md)
*   **测试与审计报告**：[docs/reviews/](./docs/reviews/)

## 5. Agent 启动规则与指令 (Agent Booting Rules)
*   **OrchestratorAgent**：流水线总控调度者，负责运行 Hook 并调度子 Agent，只读源码与 Review 报告。
*   **ModuleAgent**：负责执行具体模块代码构建，其上下文载入命令与静态约束详见各模块下的 `agents.md`。
