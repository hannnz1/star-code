# MUSE M1 Permission Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** U03 的 default/acceptEdits/plan 在 API、CLI/TUI/Web、恢复和子任务中使用同一持久化策略。

**Architecture:** SQLite schema 9 保存 permission_mode、policy_version、legacy_policy；新任务默认 default，旧任务以 acceptEdits/plan 冻结旧有效行为并标为 legacy。独立权限 helper 计算审批和动作摘要，数据库执行边界再次验证；模式变更仅对停止的任务组生效，子任务只收紧。

**Tech Stack:** Pydantic、SQLite/SQLAlchemy、FastAPI、React/TypeScript、Textual、pytest。

**Spec:** U03；保留既有路径、任务租约和动作幂等契约，不恢复 bypass。

## Task 1 — 持久化与执行边界

Files: `contracts.py`、`storage/database.py`、`permissions/task_policy.py`、`tasks/repository.py`、`tasks/delegation.py`、`tasks/conversation.py`、`tools/registry.py`。

- [x] 写真实 write/execute 三模式、矛盾请求、旧数据库迁移、重启和子任务策略测试；运行观察失败。
- [x] 新默认 default、read_only 隐式映射 plan、显式冲突拒绝；历史任务保留旧策略和 legacy 标志。
- [x] 分发和 begin_call 都验证策略；计划模式不能经 Hook/Skill/委派写入，用户记忆维持独立 execute 审批。
- [x] 审批摘要绑定工作区、参数、模式、版本；legacy v1 旧摘要仅作为已冻结历史策略兼容，策略更新后不再沿用。

## Task 2 — 用户模式变更

Files: repository/API/public contracts/terminal/frontend。

- [x] 测试模式变更、过期、拒绝重试和陈旧 digest 不能执行。
- [x] revision 校验；有运行中后代不允许更改；停止任务组可收紧，子任务不自动放宽。
- [x] 未消费审批失效，保留历史审批快照；重置 PREPARED digest，不重放已执行工具。

## Task 3 — 全入口与回归

- [x] CLI --mode、terminal/TUI /mode、Web 创建选择/任务策略显示均传递同一 permission_mode。
- [x] 重新生成 API TypeScript 类型、构建 Web；真实浏览器记录写入审批展示。
- [x] 旧测试中刻意接受编辑的场景显式选择 acceptEdits，新默认通过专用测试证明；不为测试偷改产品默认。
- [x] 相关回归、Ruff、迁移/回滚说明、最终完整回归和独立审查，结果写开发日志。
