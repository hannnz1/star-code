# Replit Task Board 功能对齐证据

最新交付以 [任务看板最新对齐报告](task-board-final-alignment-2026-10-05.md) 为准；本文件保留此前批次的历史记录。

核验日期：2026-10-05。对象：本目录 MUSE Python 商家工作台。结论：核心任务管理和受限静态主题整合已有可重复测试证据；不能宣称整个 Replit Agent 功能全部对齐。

后续更新：证据驱动建议与来源草稿已完成，最新回归为 88 项后端、7 项浏览器通过，详见 [后续建议验收](task-board-follow-ups-validation-2026-10-05.md)。下表与 84/5 结果保留上一批基线记录。

## 对照来源

已阅读 [Replit 官方 Task Board](https://docs.replit.com/features/agent/task-board)。其对照点包括草稿、执行队列、成果审查、应用结果、历史、搜索和任务菜单。运行环境隔离、自动应用及自动批准也是官方能力，必须单独核验，不能用四列页面截图证明。

## 逐项证据

下列源码路径和测试路径均相对于仓库根目录；测试函数可直接用 pytest 的 `文件::函数` 运行。

| 对照能力 | MUSE 实现证据 | 自动化证据 | 判定与边界 |
| --- | --- | --- | --- |
| 草稿持久化、编辑、明确启动 | `src/muse/commerce/task_drafts.py`、`frontend/src/commerce/StoreTeam.tsx` | `tests/muse/commerce/test_task_drafts.py::test_task_draft_lifecycle_is_durable_and_start_is_explicit`；`test_draft_start_rejects_stale_project_without_creating_task` | 已实现。固定商家流程提纲，不等同于任意需求的模型规划。 |
| 执行状态及角色依赖 | `src/muse/commerce/orchestration.py`、`frontend/src/commerce/TaskBoard.tsx`、`StoreTeam.tsx` | `test_commerce_workflow.py`、`test_workflow_api.py`；`test_team_browser.py::test_team_preparation_ui_queues_real_tasks_and_shows_connection_errors` | 三角色工作流已接通；跨计划依赖编排和容量提示仍缺。 |
| 成果、日志、逐文件差异及审查 | `frontend/src/commerce/ReviewSummary.tsx`、`ThemeCode.tsx` | `test_code_integration_browser.py::test_code_baseline_review_apply_and_file_diff_are_explicit`，1440/390 两种宽度 | 已实现只读审查和显式操作；浏览器测试使用受控成果，不证明真实模型生成质量。 |
| 应用结果到项目基线 | `src/muse/commerce/code_integration.py`、`frontend/src/commerce/CodeIntegration.tsx` | `test_code_integration.py::test_parallel_file_changes_merge_locally_with_stale_review_and_retry_protection` | 静态主题范围已实现。检查过期版本、摘要、取消状态及幂等请求；应用不等于正式发布。 |
| 多任务代码合并 | `merge_lines`、`merge_files` | `test_same_file_disjoint_changes_apply_and_survive_sealed_source`；8 个 `test_line_merge_preserves_disjoint_changes_and_rejects_ambiguity` 参数案例；`test_same_file_conflicts_and_stale_project_never_apply` | 不同文件和同文件不重叠行可合并。重叠修改/边界插入拒绝；尚无 Agent 自动冲突修复。 |
| 历史、批量归档/恢复 | `src/muse/commerce/board.py`、`TaskBoard.tsx` | `test_board_archives.py::test_archive_is_atomic_revision_bound_and_does_not_change_plans`；`test_active_unknown_duplicate_and_empty_archives_are_rejected`；看板浏览器生命周期测试 | 已实现。运行中的计划不能伪装成已完成；本地代码应用也不会伪造商家业务成功状态。 |
| 重命名及搜索/筛选 | `task_drafts.py`、`TaskBoard.tsx` | `test_task_drafts.py::test_plan_rename_changes_display_metadata_without_invalidating_plan`；`test_team_browser.py::test_merchant_board_draft_archive_restore_start_and_rename` | 搜索/筛选已实现；该浏览器测试证明重命名持久化和归档筛选，不据此声称所有搜索组合都已自动化覆盖。 |
| 桌面和移动布局 | `frontend/src/commerce/studio.css` | 两组 1440/390 浏览器参数测试，无横向溢出及 JS 错误；截图见下 | 桌面/手机已有运行证据；平板两列规则已写入，尚无本轮独立平板浏览器证据。 |
| 完整项目副本隔离 | 静态主题按计划独立草稿和封存包 | `test_code_bridge.py`、代码整合测试 | 部分对齐。未证明完整应用服务、数据库与 Linux/Docker 运行环境复制。 |
| 后续任务建议 | `follow_ups.py`、`FollowUps.tsx`，根据计划状态、错误码和代码冲突生成建议，接受后保存来源草稿 | `test_follow_ups.py`、`test_follow_ups_browser.py`，见新增验收报告 | 商家规则范围已实现；任意成果的模型推荐、建议分组与批量启动尚未对齐。 |
| 一次性自动批准/自动应用 | 当前仍是显式审查与应用 | 无对应测试 | 尚未对齐；真实店铺发布审批继续独立。 |

## 本轮实跑结果

- 后端相关回归：**84 passed，0 failures，0 errors**，28.93 秒。
- Chromium 浏览器：**5 passed，0 failures，0 errors**，24.47 秒。包含桌面/手机审查与本地应用、任务准备及草稿生命周期。
- TypeScript `tsc --noEmit`、Vite production build、`python -m muse.openapi_types --check` 和 `git diff --check` 均退出 0。
- 后端有一个重复 ZIP 条目的预期故障夹具警告；浏览器有两个依赖弃用警告。未发现测试失败。
- 此轮没有付费模型调用，没有真实店铺发布；不能替代商家模型质量 benchmark、购买流程或独立部署验收。

机器可读的原始结果：[`backend.xml`](../../work/task-board-evidence-2026-10-05/backend.xml)、[`browser.xml`](../../work/task-board-evidence-2026-10-05/browser.xml)。JUnit 保存具体测试名称、耗时与失败计数，便于复核，不能作为生产环境证明。

## 截图

截图由本地 Chromium 自动化实跑生成。它们证明可见布局和测试场景中的界面状态，不证明远端环境或模型能力。

![桌面四列任务看板](../../work/task-board-ui-2026-10-05/task-board-1440.png)

![手机任务看板](../../work/task-board-ui-2026-10-05/task-board-390.png)

![本地代码应用结果](../../work/task-board-ui-2026-10-05/code-integration-1440.png)

## 重跑命令

在仓库根目录运行 PowerShell：

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/muse/commerce/test_code_integration.py tests/muse/commerce/test_code_bridge.py tests/muse/commerce/test_board_archives.py tests/muse/commerce/test_task_drafts.py tests/muse/commerce/test_commerce_restore.py tests/muse/commerce/test_commerce_export.py tests/muse/commerce/test_commerce_workflow.py tests/muse/commerce/test_workflow_api.py tests/muse/commerce/test_commerce_migration.py tests/muse/commerce/test_generated_commerce_types.py tests/test_state_backup.py -q --basetemp=work/task-board-evidence-backend-rerun --junitxml=work/task-board-evidence-2026-10-05/backend-rerun.xml
& '.venv\Scripts\python.exe' -m pytest tests/muse/commerce/test_code_integration_browser.py tests/muse/commerce/test_team_browser.py -q --basetemp=work/task-board-evidence-browser-rerun --junitxml=work/task-board-evidence-2026-10-05/browser-rerun.xml
& '.venv\Scripts\python.exe' -m muse.openapi_types --check
Push-Location frontend
& 'C:\Program Files\nodejs\node.exe' node_modules/typescript/bin/tsc --noEmit
& 'C:\Program Files\nodejs\node.exe' node_modules/vite/bin/vite.js build
Pop-Location
```

需要现有 Python/前端依赖和 Chromium；每条命令独立检查退出码。重跑使用不同临时目录，不需要清理旧测试证据。

## 后续顺序

1. 动态后续建议与来源计划关联，跨计划依赖和并发容量展示。
2. 冲突修复草稿，保留冲突来源和审查绑定；不静默选择任一方。
3. 单独设计一次性自动批准/本地应用策略，不扩展为自动店铺发布。
4. 隔离环境的实际运行、真实建站与上新，以及平板/人工交互验收。没有环境时继续保留未验收状态。
