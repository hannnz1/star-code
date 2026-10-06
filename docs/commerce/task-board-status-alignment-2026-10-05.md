# Task Board 状态与操作对齐

本轮按照用户确认的对齐方向，修正 Ready 列与阻塞状态混用的问题。参考已核对的 [Replit 官方 Task Board](https://docs.replit.com/references/agent/task-board)，保留商家发布需要独立审查的业务边界。

## 完成内容

| 看板位置 | 状态 | 用户看到的操作含义 |
|---|---|---|
| 草稿 | 未启动的持久计划 | 检查提纲、修改并明确启动 |
| 进行中 | 执行、验证、发布、排队 | 跟踪实际执行 |
| 进行中，需处理标记 | NEEDS_INPUT、BLOCKED、NEEDS_RECONCILIATION、PARTIAL | 分别补资料、检查阻塞、只读核对远端、核对部分发布；不把这些任务标为成果就绪 |
| 待审查 | REVIEW_REQUIRED、APPROVED | 审查成果，或对已批准成果明确执行发布 |
| 已结束 | SUCCEEDED、FAILED、CANCELLED、STALE，以及归档草稿 | 保留原有业务状态和历史；已结束不自动表示已发布 |

新增状态筛选：全部状态、需要处理、待审查/发布、执行/排队、已结束。筛选变化清空批量选择，避免对已隐藏的选择执行动作。任务详情复用卡片的下一步提示，店铺概览的待处理计数继续包含受阻任务和待审查任务。未改变后端执行状态、审批或发布授权。

## 实跑验证

- 新增浏览器状态回归：3 passed，1440/900/390；来源为真实数据库中保存的合成状态任务，不使用真实模型生成成果。
- 原有草稿、任务准备、代码审查/应用、建议及自动化浏览器回归：12 passed。
- 队列、草稿、历史、自动应用和成果处理后端合同：20 passed。
- TypeScript、Vite build、OpenAPI 类型一致性、Ruff、Git diff whitespace 检查通过。
- 本轮付费 API 请求为 0，真实商家站写入为 0。

三个新增测试在修改前因缺少正确 Ready 列失败；修改后通过。测试还检查打开卡片和状态筛选零写请求、任务数不变、无 JS 错误或横向溢出。已有浏览器回归出现两条 websockets 依赖弃用警告，无测试失败。

原始证据：`work/task-board-status-2026-10-05/browser.xml`、`existing-browser.xml`、`backend.xml`；截图 `board-1440.png`、`board-900.png`、`board-390.png`。重跑入口 `scripts/commerce/verify_task_board.py` 已纳入新增浏览器文件和截图哈希；本轮使用上述分组命令，没有声称整个入口重新实跑。

![桌面状态看板](../../work/task-board-status-2026-10-05/board-1440.png)

## 仍有差距

独立六阶段验证与商家审批、发布的完整业务闭环仍需端到端验收。运行副本和合成商品发布的实际 Linux 证据已补齐，见 [Linux 验收记录](runtime-acceptance-2026-10-05.md)，此前“Docker 不可连接”是历史状态。

重叠代码冲突的模型修复质量、模型后续建议质量仍缺新增真实效果样本。多人实时共享协作和任意应用运行环境复制未完成对齐；本轮不宣称全部 Replit 能力等价。
