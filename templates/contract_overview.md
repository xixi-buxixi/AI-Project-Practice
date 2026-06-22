# Physical Contract Overview (contract_overview.md)

> **定位**：物理契约总览文档。合并当前项目类型对应的全局契约描述、错误代码矩阵及通信协议标准。

## 1. 协议规范与全局约定 (Protocol Specification)
*   **通信协议**：HTTP/1.1 (JSON) / gRPC / WebSockets / Command Line Interface
*   **全局错误码矩阵 (Global Errors)**:

| 错误编码 (Code) | HTTP 状态码 | 业务定义 (Reason) | 推荐处理策略 (Mitigation) |
|---|---|---|---|
| `ERR_UNAUTHORIZED` | 401 | 未携带 Token 或 Token 过期 | 重新登录并刷新凭证 |
| `ERR_INVALID_PARAM` | 400 | 输入参数校验失败，格式不符 | 客户端校对表单后重试 |
| `ERR_INTERNAL` | 500 | 服务端运行异常或依赖数据库故障 | 重试或人工排查日志 |

## 2. 全局参数约束与 Schema (Global Schema)
*   **日期格式**：统一采用 ISO 8601 格式 `YYYY-MM-DDTHH:mm:ssZ`。
*   **认证标头**：`Authorization: Bearer <Token>`。

## 3. 细分模块物理契约路由
各模块的 API、命令行参数及内部物理契约详见 `docs/contracts/modules/`：
*   **Auth 模块契约**：[docs/contracts/modules/auth.md](./modules/auth.md)
*   **User 模块契约**：[docs/contracts/modules/user.md](./modules/user.md)
