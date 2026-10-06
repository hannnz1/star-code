# 后续任务建议：实现与验收

最新交付以 [任务看板最新对齐报告](task-board-final-alignment-2026-10-05.md) 为准；本文件保留此前批次的历史记录。

2026-10-05。本轮继续对齐 [Replit 官方后续任务体验](https://docs.replit.com/features/agent/follow-up-tasks)：用户可以检查建议，再安排后续工作。MUSE 当前实现商家范围的证据规则，不宣称等同于模型分析任意项目后的推荐。

## 已完成

1. `GET /api/commerce/projects/{project_id}/plans/{plan_id}/follow-ups`：读取实际计划状态、错误码和代码合并审查，只读生成建议。建站成功提供新品准备及体验改进；新品成功提供体验检查；失败/受阻且有错误码提供诊断草稿；封存代码冲突提供冲突修复草稿。
2. `POST .../follow-ups/accept`：明确点击后才保存草稿。原子校验来源计划、项目和代码基线的证据摘要，版本过期返回 409；相同请求 ID 重试返回已有草稿，换内容复用 ID 拒绝。不启动模型任务，不批准或发布。
3. 草稿保存 `source_plan_id`、`source_plan_revision` 和 `suggestion_id`，刷新后保留来源。后续编辑、归档和启动复用已有草稿流程。来源是历史关联，并不是执行依赖；未实现跨计划排队。
4. 工作台详情新增「根据成果安排下一步」，展示建议内容、证据和版本，保存后打开草稿编辑。保留原 Coding Agent 和三角色队列。
5. 取消申请立即隐藏建议；旧项目资料的计划不提供新建议。代码冲突草稿保留原成果，基于当前代码起点重新准备，仍需审查双方差异及重新验证；不会自动解决冲突。

核心源码：`src/muse/commerce/follow_ups.py`、`task_drafts.py`、`models.py`、`api.py`；前端：`frontend/src/commerce/FollowUps.tsx`、`StoreTeam.tsx`。新增模型字段有默认值，旧草稿不需要数据库结构迁移。

## 测试证据

- 相关后端回归 **88 passed**（包含此前 84 项及新增 4 项），原始结果：[follow-ups-full-backend.xml](../../work/task-board-evidence-2026-10-05/follow-ups-full-backend.xml)。
- 桌面/手机浏览器 **7 passed**（包含此前 5 项及新增 2 项），原始结果：[follow-ups-browser.xml](../../work/task-board-evidence-2026-10-05/follow-ups-browser.xml)。
- 新增后端 `tests/muse/commerce/test_follow_ups.py`：只读建议、成功计划的两种建议、失败错误码、来源持久化、重复请求、陈旧摘要拒绝、项目变更拒绝、未知计划、取消申请及真实封存代码冲突。
- 新增浏览器 `test_follow_ups_browser.py`：1440/390 宽度；读取零 POST、保存仅一次 accept POST、未新增执行任务、刷新后草稿来源仍存在、无横向溢出、无 JavaScript 错误。成功状态使用受控测试夹具，不能证明真实发布成功。
- TypeScript、Vite 构建、OpenAPI 生成类型检查通过。本轮没有模型 API 费用，没有真实店铺写入。

![桌面建议](../../work/task-board-ui-2026-10-05/follow-ups-1440.png)

![手机建议](../../work/task-board-ui-2026-10-05/follow-ups-390.png)

在仓库根目录可重跑新增测试：

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/muse/commerce/test_follow_ups.py tests/muse/commerce/test_follow_ups_browser.py -q --basetemp=work/follow-ups-review-rerun
```

## 下一批对齐范围

1. 跨计划前置条件与等待队列、并发容量展示；来源关联不能当作这些功能已完成。
2. 看板建议分组、建议批量启动/取消、模型依据项目成果生成更多建议。当前草稿已有批量归档，建议本身还没有批量动作。
3. 可审查的冲突修复上下文包与修复结果验证，不能仅凭生成草稿宣称自动修复。
4. 一次性自动批准/本地应用的策略和验证，以及完整应用隔离与正式商家发布验收。
