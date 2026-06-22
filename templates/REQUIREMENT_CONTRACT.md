# REQUIREMENT_CONTRACT

> **定位**：需求阶段薄契约。只记录冻结需求资产的读取顺序、冻结版本、进入接口/构建阶段的准入条件和阻塞条件；不复制 PRD 正文。

## 1. 需求冻结资产清单 (Frozen Assets)

| 资产路径 | 冻结版本 (Git Commit/Tag) | 冻结时间 | 哈希校验 (SHA-256) |
|---|---|---|---|
| `docs/requirements/overview.md` | | | |
| `docs/requirements/constitution.md` | | | |
| `docs/requirements/glossary.md` | | | |
| `docs/requirements/out-of-scope.md` | | | |

## 2. 接口设计准入条件 (Interface Gate)

- [ ] 1. 核心需求文档（PRD、术语表、核心底线、不做的范围）已确认无 TBD 或待确认模糊项。
- [ ] 2. 核心业务流程及状态机转换在需求文档中定义完整。
- [ ] 3. 需求变更记录中无未裁决的 P0/P1 问题。

## 3. 代码构建准入条件 (Build Gate)

- [ ] 1. 逻辑接口定义完成，物理接口契约（如 HTTP API / CLI 参数 / 消息事件）已冻结。
- [ ] 2. `MODULE_MAP.md` 中所有模块分工、边界与依赖已固化，且各扩展点强度（E0-E4）定义清晰。
- [ ] 3. 根目录导航 `agent.md` 与主任务看板 `tasks.md` 已就绪。

## 4. 阻塞条件与临时挂起规则 (Blocking Conditions)

在以下情况发生时，AI Agent 必须停止执行，拉起 Grill-Me 模式或请求人工裁决：
* 发现实现中的代码结构与 `docs/contracts/` 存在不可调和的逻辑冲突。
* 需求发生未冻结变更，或超出 `docs/requirements/out-of-scope.md` 划定的边界。
* 对未定义的术语或第三方交互协议存在二义性理解。
