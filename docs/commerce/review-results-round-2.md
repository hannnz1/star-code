# 第二批独立审查与处置

审查者：独立上下文 gpt-6-astra，按 executing-plans/requesting-code-review 技能审查 [本批范围](review-package-round-2.md)，未修改文件。原 verdict 为 request changes，无 Critical，五项 Important，未另列 Minor。此文件记录作者的一次修复，不声称重新取得 reviewer 的通过结论。

| Important | 处置与实际范围 |
|---|---|
| 业务落库后 complete_call 前中断导致 UNKNOWN | 提案/委派/审查在同事务存 managed_call_receipt，绑定 task/call/plan/step/参数/审批 digest；租约恢复只对固定 SQLite 管理工具核对回执。无回执说明该事务未提交；外部工具和损坏回执继续 UNKNOWN，绝不自动重试 WordPress 写入 |
| 原 reload 丢失冻结角色 | 对 Commerce 任务明确拒绝 reload，保留角色哈希快照；普通 Coding reload 保持原逻辑 |
| 支持的长商品事实无法读取 | 三角色增加原任务专属 read_offload，12,000 字符分页、哈希与任务归属检查；长 CSV 原始描述完整恢复，跨任务读取拒绝 |
| 已知缺政策/设置仍排队收费 | 保存 NEEDS_INPUT / FACTS_INCOMPLETE，不建模型根任务或预算，列明缺字段；已确认事实后需新计划，不强行生成政策或设置 |
| 鉴权/权限错误丢失 | 主适配器只读取最大 16 KiB 的错误 envelope 并保留固定 allowlist code；远端正文/密钥丢弃；通过真实 Connector ASGI + 外部 HTTP fixture 验证 |

针对性回归也覆盖：已提交/未提交的两种 crash 窗口、委派去重、错误回执不再消耗修正次数、损坏证据/任意 external 继续 UNKNOWN、原审批后继续同一次调用、故障恢复保留根预算、早停根任务不能伪造团队完成、重复状态同步不改版本。

原始测试记录不覆盖：`work/commerce2-review-red.log`、`commerce2-review-green.log`、`commerce2-review-final.log`、`commerce2-review-no-task-red.log`、`commerce2-root-completion-red.log`、`commerce2-advance-idempotence-red.log`。初版 reload 用例误用了 keyword-only 签名，长描述测试漏了 json import，已修正并如实保留失败日志。最后四组相关测试 `work/commerce2-review-final2.log` 为 **44 passed**。

## Declined-to-judge 的裁决

以下均保留为后续未验收项，不能因为当前离线测试通过而放行：

- 前一批主题/P0/P1/P5/P8 的完整审查：保留原记录，本次只检查依赖接口。
- 真实 WP/PHP/effective template/global styles/镜像 digest：缺真实环境，BLOCKED/NOT_RUN。
- P3/P7 远端写回执、未知结果、批准过期、冲突/部分成功/订单库存保护：未实现完整内核，不能部署发布。
- P6 Linux 身份、网络、凭据/Docker socket 探针、隔离代码桥及预览/ZIP目标边界：未实测，禁止 Commerce Shell/写文件。
- SKU 实站对账、图片上传、购买流程：未完成，CSV 文件检查不能替代。
- 付费三角色完整执行、六个真实案例、费用和人工商家批准：NOT_RUN，本轮费用 0。
- P10 导出/第二环境迁移、干净 wheel 安装、完整 MVP：未完成，保留构建环境限制。
- 浏览器/全量复测：由主实施者执行并在新检查点记录实际结果，不采用 reviewer 口头通过或旧日志代替。

当前只可继续独立离线开发，不能标作完整建站、上新或生产验收通过。
