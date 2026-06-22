# Module Task State: <module_name>

> **定位**：模块动态看板。存放在 `src/<module_name>/tasks.md`，执行子 Agent 必须在此更新局部工作总结与自测验证命令。

## 1. 当前任务状态 (Current)
- **Task ID**: TASK-XXXX
- **Goal**: [当前模块开发的核心功能说明]
- **Target Level**: Great | Qualified | Average
- **Status**: todo | in_progress | blocked | done
- **Last Updated**: YYYY-MM-DD HH:MM:SS

## 2. 局部完成总结 (Done Summary)
*   [修改或增加的具体函数/类/路由说明]
*   [变更的文件路径清单]

## 3. 阻塞项与需要的输入 (Blocked)
*   **Blocker**: [描述为什么阻塞]
*   **Needed Input**: [需要向总 Agent 或人工索取什么反馈]

## 4. 技术决策 (Technical Decisions)
*   [开发过程中针对本模块做出的技术选型、设计折衷]

## 5. 验证与日志状态 (Verification)
- **Command**: [例如：pytest src/<module_name>/tests/]
- **Result**: pass | fail | not_run
- **Log Summary**:
  ```text
  [黏贴测试通过的控制台摘要日志]
  ```
