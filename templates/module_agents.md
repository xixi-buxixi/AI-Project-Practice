# Module Static Rule: <module_name>

> **定位**：模块静态导航规则。存放在 `src/<module_name>/agents.md`，用于规定当前模块可修改文件范围、模块 API 边界、外部依赖与特定底线约束。

## 1. 模块边界与允许修改路径 (Allowed Paths)
*   **本模块绝对路径**：`src/<module_name>/`
*   **只允许修改的路径 (White List)**:
    1. `src/<module_name>/**/*.py` (或对应语言的源代码文件)
    2. `src/<module_name>/tests/` (模块局部单元测试)
*   **严禁修改的路径 (Black List)**:
    1. 根目录的公共配置文件。
    2. 其他业务模块下的 `src/<other_module_name>/`。

## 2. API 边界与依赖规范 (Dependencies)
*   **允许引入的本模块外部依赖**：
    * 仅限 [MODULE_MAP.md](../../MODULE_MAP.md) 声明的依赖模块。
*   **模块对外暴露方法**：
    * 任何其他模块想要调用本模块，必须通过 `src/<module_name>/exports.py` 或统一的对外 Facade 接口。

## 3. 本模块特定设计约束 (Constraints)
*   [例如：所有涉及到用户身份判断的操作必须经过 Auth 校验，且必须使用统一返回格式]
*   [例如：不能跳过 exports 直接读取底层 DB model]
