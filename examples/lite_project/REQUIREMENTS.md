# Lite Project Requirements

> **定位**：Lite 级别的薄需求文档。包含具体功能范围与局部验收用例。

## 1. 核心需求范围
本示例项目用于演示 Lite 级 Hook 的自动化能力。
*   **功能 1**：计算斐波那契数列的前 N 项。
*   **功能 2**：支持命令行输入参数指定项数 N。

## 2. 验收用例 (Acceptance Criteria)
*   **AC-1**：运行 `python src/main.py --n 5` 应在 stdout 输出 `[0, 1, 1, 2, 3]`。
*   **AC-2**：当参数 N 小于等于 0 时，系统返回错误提示且退出码非零。
