# MODULE_MAP

> **定位**：模块路由表。连接需求、接口契约与负责 Agent，是架构边界的物理承载。

## 1. 模块边界与负责 Agent

| 模块名称 (Module) | 职责描述 (Description) | 需求路径 (Requirement Path) | 契约路径 (Contract Path) | 负责 Agent (Owner Agent) | 核心依赖模块 (Depends On) |
|---|---|---|---|---|---|
| `auth` | 统一身份认证与鉴权 | `docs/requirements/modules/auth.md` | `docs/contracts/modules/auth.md` | `ModuleAgent_Auth` | None |
| `user` | 用户信息与权限管理 | `docs/requirements/modules/user.md` | `docs/contracts/modules/user.md` | `ModuleAgent_User` | `auth` |

## 2. 扩展点映射表 (Extension Points Registry)

> **原则**：业务变动应通过扩展（E2-E4）新增策略/适配器/插件，严禁在核心逻辑中不断堆积 if-else/switch 分支。

| 扩展点 (Extension Point) | 强度 (Strength) | 推荐设计模式 (Pattern) | 注册表路径 (Registry Path) | 新增成员方式 (How to Add) | 绝对禁止修改的文件/目录 (Must Not Modify) |
|---|---|---|---|---|---|
| `payment_gateways` | E2 (策略) | Strategy / Factory | `src/payment/registry.py` | 在 `src/payment/strategies/` 下新增策略实现并注册 | `src/payment/payment_service.py` (核心状态流转) |
| `data_formats` | E3 (插件) | Plugin / Registry | `config/plugins.json` | 新增插件文件并在 JSON 配置文件中声明 | `src/core/parser_engine.py` (核心引擎) |

## 3. 双向溯源哈希约束 (Traceability Checksums)

每次发布模块前，后置 Hook 将验证以下哈希的有效性：
* `sha256_requirements_frozen`:
* `sha256_contracts_frozen`:
