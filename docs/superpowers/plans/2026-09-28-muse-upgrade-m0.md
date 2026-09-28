# MUSE Upgrade M0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 修复 Windows 深路径 worktree、保持审批目标稳定，拒绝未解决的协作失败。

**Architecture:** 继续使用真实 Git linked worktree。审批绑定绝对目标，Git 创建命令使用从父工作区计算的等价相对路径；根目录选择在任务中冻结。完成判定从真实回执归纳未解决的失败，而不相信模型最终文字。

**Tech Stack:** Python 3.12+、SQLite/SQLAlchemy、Git、pytest、现有 MUSE Worker。

**Spec:** `docs/superpowers/specs/2026-09-28-muse-mewcode-upgrade-design.md`，U01/U13。

## Global Constraints

- 沿用所选 StarCode 模型和凭据；此阶段仅离线验证。
- 保留父目录未提交内容、禁用仓库 hooks、不复制 ignored 文件。
- 审批绑定最终绝对路径和准确提交；配置变化不能改变已批准目标。
- 保留当前 feature branch 的已有工作，不重置、不自动推送。
- 后续 M1–M6 按总 Spec 分别编写实施计划；本计划不宣称完成其他需求。

## Review Focus

- 路径 UTF-8 字节数和 Windows 字符数不同：中文深路径不能绕开预检。
- managed_root 改变后重启：待批准任务必须继续使用原目标。
- 过期/伪造工作树路径：模型参数不能覆盖服务绑定的目标。
- 失败后重试成功：必须能消除已被同等成功操作替代的旧错误。
- 第一个子任务失败、第二个成功：不能因存在任意成功回执而掩盖未完成工作。

## Task 1: 创建路径与根目录快照

**Files:** `src/muse/config.py`、`src/muse/extensions/worktrees.py`、`tests/test_durable_worktrees.py`。

**Interfaces:** Settings 新增 `worktree_managed_root: Path | None`；配置读取 `worktrees.managed_root`。`DurableWorktrees.managed_root()` 返回冻结根目录；`creation_path(destination: Path) -> str` 返回等价 Git 参数或明确拒绝。

- [x] 写测试：当前深路径创建/恢复、空格中文、配置短根、根配置变更后审批目标保持、根位于私有状态目录拒绝、更深不支持路径预检不产生工作树。
- [x] 使用当前项目深度的 basetemp 运行 `tests/test_durable_worktrees.py`；先观察现有故障和新增契约失败。
- [x] 实现配置、来源安全校验、持久化根快照和相对参数；保留旧调用回执的绝对路径，避免配置变更移动旧树。
- [x] 运行 worktree 测试及 `tests/test_worktree_lifecycle.py`，预期全部通过，包括准确提交、集成和保留改动。
- [x] 完成记录；只在作者身份可用时提交本任务文件，不伪造作者或修改全局配置。

## Task 2: 完成判定

**Files:** `src/muse/agent/loop.py`、`tests/muse/unit/test_agent_completion.py`。

**Interfaces:** `AgentRunner._verified_result()` 消费持久化工具回执；同等 spawn 以准确基准、prompt、role 为身份；同一子任务 merge/integrate 为同一集成操作。

- [x] 写真实 Worker 测试：spawn_worktree 失败后模型说成功，任务必须 FAILED；另加失败同操作重试成功不误挡的回执例。
- [x] 运行测试并确认失败来自当前错误完成判定。
- [x] 在完成检查中阻止未解决的创建/集成失败和当前有效 worktree 子任务失败；提供明确错误证据。
- [x] 运行 agent completion、delegation、worktree 集，预期通过。
- [x] 将串行降级记录为用户创建明确串行后续任务；原失败任务不改写为成功。

## Task 3: 回归与交付

**Files:** `docs/python-runtime-operations.md`、`docs/muse-upgrade-development-ledger.md`。

**Interfaces:** 配置/审批/失败恢复说明；逐 AC 证据与剩余项。

- [x] 运行项目完整离线 `pytest`，将完整日志保存于 `work/upgrade-m0`；记录所有 skip/fail。
- [x] 对 Task 1/2 diff 作独立上下文审查，修复重要问题后重跑受影响测试。
- [x] 更新 U01 各 AC 状态和兼容说明；不得把 M0 成绩当成 U02–U14 已验收。
- [x] 继续 M1 的独立实施计划和开发。
