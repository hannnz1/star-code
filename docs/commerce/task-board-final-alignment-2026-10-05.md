# MUSE 商家任务看板：最新对齐交付与边界

日期：2026-10-05。目标参照 [Replit Task Board](https://docs.replit.com/features/agent/task-board) 与 [Follow-up tasks](https://docs.replit.com/features/agent/follow-up-tasks)。这是一份行为证据表，不是竞品全部产品能力等价声明。

续接更新：[状态对齐验收](task-board-status-alignment-2026-10-05.md) 已将待审查成果与受阻任务分开，并新增状态筛选和一致的下一步提示；本轮 15 项浏览器、20 项后端合同通过。实际 Linux 双副本及两店合成新品发布已经通过，见 [运行验收](runtime-acceptance-2026-10-05.md)。下文 Docker 不可连接等记录属于此前批次，不能作为当前状态。

2026-10-06 续接：真实完整建站链路和两例真实模型冲突修复已通过，见 [完整对齐续接](full-alignment-continuation-2026-10-06.md)。这补齐测试站运行和小样本模型证据，不代表生产或人工验收。

## 本轮新增

| 能力 | 代码与测试证据 | 实现范围 |
| --- | --- | --- |
| 批量保存建议 | `follow_ups.py::accept_batch`；`test_follow_ups.py::test_suggestion_batch_is_atomic_and_retry_does_not_duplicate_drafts` | 整批事务、摘要检查、请求重试。同一版本建议单项/批量保存不重复建立草稿。 |
| 建议分组与批量启动/取消 | `TaskBoard.tsx` 后续建议筛选、草稿复选框；`task_queue.py::batch` | 草稿可批量批准并启动、归档；已授权排队可取消。未保存的表单修改不计入批次。 |
| 跨计划依赖队列 | 草稿 `dependency_plan_ids`；`task_queue.py::_reason/promote`；`test_task_queue.py` | 只引用同项目现有计划，等待其业务 `SUCCEEDED`。失败/取消/失效不放行。Worker 才能推进，GET/刷新只读。来源关联与执行依赖分开。 |
| 容量和后台排队 | `commerce.max_active_plans`（默认 2）；`TaskRepository.claim_next`；`test_worker_claim_limit_keeps_existing_plan_children_running` | 按项目限制正在运行及等待处理的计划；同一计划子任务可继续。未准入的草稿不创建模型任务。直接创建的商家任务领取也受限制。不是收费套餐管理。 |
| 一次性批准草稿 | 卡片「一次性批准计划并启动」；带版本校验的 batch start | 明确同意当前已保存商家提纲后启动；不是批准模型未来任意改写的计划。 |
| 一次性本地自动应用 | `task_automation.py`、`LocalApplyAutomation.tsx`；`test_task_automation.py` | 绑定项目和起点，24 小时过期，冲突/基线变化/取消阻塞；可撤销 ARMED。封存后应用受限静态主题，不批准店铺发布。持久回执允许崩溃后核对，避免重复应用。草稿菜单可批准并设置一次性本地应用。 |
| 放弃/恢复代码成果 | `code_integration.py::disposition`；`test_code_disposition.py`；三尺寸浏览器测试 | 放弃不删除封存、不改计划版本、不改变发布权限；恢复后重新审查。原审查摘要立即失效。 |
| 成果状态可见 | `code-dispositions`、看板标注已应用/已放弃 | 显示本地代码处理状态；不会把尚未发布的商家计划伪装成业务成功。 |
| 当前模型的后续推荐 | `follow_up_models.py`、`test_follow_up_models.py` | 用户明确创建持久建议任务，每任务最多一次请求，无工具。发送品牌名称、语言、计划状态/错误码/角色成果哈希及已封存主题差异摘要（最多 8000 字符）；不发送凭据、订单或其他工作区文件。1–3 条结果通过类型校验才可进入草稿。显示请求数与用量，旧证据失效；中断不会自动重新扣费。 |
| 冲突修复执行上下文 | `conflict_context.py`、`read_conflict_file`、网站开发角色指令；`test_code_conflict_produces_version_bound_repair_draft` | 冻结 base/current/candidate，在当前基线修复、封存和验证。2026-10-06 两个真实模型用例通过：明确选择正确修复；歧义追问且不写入。小样本不代表任意冲突成功率。 |
| 响应式与加载 | 1440/900/390 Chromium；`main.tsx` 商家页面 lazy/Suspense | 桌面、平板、手机均做交互回归。商家模块按需加载，主脚本约 410 KB，商家独立块约 98 KB；构建不再报单块超过 500 KB。 |

## 验证与证据入口

### 独立审查后的修复

- **重启后的授权到期**：`APPLYING` 在创建新应用前也必须通过事务内到期检查；已提交的同请求回执可以在到期后恢复，避免重复应用。回归测试分别覆盖未提交拒绝和已提交恢复。
- **合并后主题超限**：两个分别有效的主题合并后仍需满足文件和包大小限制。验证失败返回 `VERIFICATION_FAILED`，当前自动应用进入 `BLOCKED`；后台继续处理其他任务，不因该错误退出。回归测试使用两段 300 KB CSS，并验证随后另一任务成功。

以上测试先复现失败，再修复通过；独立复核另行运行相关 19 项测试通过。

代码版本对应的本地回归包括原 Coding Agent、商家队列、自动应用、模型建议、主题编辑/封存、代码合并、状态备份和导出恢复。模型使用脚本 provider，真实发布状态使用受控夹具；这些测试不能证明真实模型质量或正式部署。

最新验证结果和 SHA-256 清单由下列一条命令生成，不调用付费模型 API，也不写真实店铺：

```powershell
& '.venv\Scripts\python.exe' scripts/commerce/verify_task_board.py
```

脚本在 `work/task-board-evidence/<UTC 时间>/` 保存原始后端/浏览器 JUnit、类型/构建/OpenAPI 日志、命令退出码及源码/截图 SHA-256。某阶段失败就停止，不能用失败日志作为通过证明。本轮修复后的原始结果入口：[验收清单](../../work/task-board-evidence/20261005T033811Z/summary.json)。

修复后交付脚本实跑：135 项后端回归、12 项浏览器回归通过，无失败、错误或跳过；TypeScript、前端构建和 OpenAPI 一致性检查均通过。旧批次结果保留在 [原证据报告](task-board-alignment-evidence-2026-10-05.md)，不能累计为额外测试覆盖。本轮付费 API 请求和真实店铺写入均为 0。

截图位于 `work/task-board-ui-2026-10-05/`，包括桌面/平板/手机看板、模型建议和自动应用结果。

![平板看板](../../work/task-board-ui-2026-10-05/task-board-900.png)

![桌面模型建议](../../work/task-board-ui-2026-10-05/model-follow-ups-1440.png)

![本地自动应用](../../work/task-board-ui-2026-10-05/auto-apply-1440.png)

## 仍不能称作全部对齐的部分

1. **完整应用环境副本**：固定 WordPress/WooCommerce 平台的独立数据库、固定插件和主题副本已通过真实 Linux 隔离和建站验证。任意应用运行服务、第三方插件和生产店铺完整数据复制尚未支持。
2. **Ready/Done 业务语义**：商家 `Done` 仍按业务成功、取消、失败、失效分列。本地代码应用是独立处理结果，有明确标注。Replit 的主项目代码应用语义不能直接替代店铺发布完成语义。
3. **真实模型评测**：三角色准备、建议生成及两例冲突修复已有真实模型小样本和费用账本；大样本稳定性及真实商家质量尚未验收，详见续接记录。
4. **自动解决语义冲突**：可自动合并不重叠行并生成冻结三方上下文的修复任务；明确选择的真实模型端到端用例通过。歧义需要询问，不能称任意冲突无人介入自动解决。
5. **竞品交互细节**：当前建议作为详情面板和看板草稿筛选，不复刻竞品推荐弹窗；批量取消使用可恢复归档。自动批准作用于已保存提纲，自动应用仅限本地静态主题。上述为已交付的商家适配范围，不能写成竞品任意项目/任意任务完全等价。

测试站的 Linux 隔离、建站、购买和发布读回已有实际证据；正式商家目标、用户人工体验及生产发布验收仍未执行。测试授权不能替代商家批准。

