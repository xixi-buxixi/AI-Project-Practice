# Global Delivery Task Board (tasks.md)

> **定位**：全局交付级任务看板。仅由总 Agent (OrchestratorAgent) 维护交付级状态摘要，不承载高频尝试或临时细节。

## 1. 交付目标状态 (Milestones & Epics)

*   **当前里程碑**：[例如：MVP-1 核心闭环验证]
*   **整体状态**：进行中 (In Progress) / 阻塞 (Blocked) / 已完成 (Done)

| 任务ID (Task ID) | 模块 (Module) | 任务目标 (Goal) | 质量级别 (Level) | 状态 (Status) | 负责 Agent | 对应分支/PR |
|---|---|---|---|---|---|---|
| TASK-001 | auth | 实现用户注册与 JWT 登录，通过 Hook Linter | Qualified | done | ModuleAgent_Auth | `feat/auth-core` |
| TASK-002 | user | 实现用户资料查询与更新，通过 smoke test | Average | in_progress | ModuleAgent_User | `feat/user-profile` |

## 2. 阻塞与挂起项 (Global Blockers)

| 阻塞ID | 关联任务 | 阻塞描述 | 解决依赖输入 | 状态 |
|---|---|---|---|---|
| BLK-001 | TASK-002 | 第三方存储服务 API 限流，测试环境不稳定 | 需要提供 Mock 存储服务配置 | open |

## 3. 全局发布验证命令 (Global Smoke Test)
*   **命令**：`python hooks/finalize.py --global`
*   **最新执行结果**：pass
*   **上次执行时间**：YYYY-MM-DD HH:MM:SS
