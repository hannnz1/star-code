# MUSE 升级开发状态 — 2026-09-28

依据 SPEC-MUSE-UPGRADE-001。当前完成本轮功能开发和离线自动验证；正式平台/模型指标/人工验收待完成。原所选 StarCode 模型与密钥未修改，本轮收费 API 调用 0，GitHub 发布目标为 `hannnz1/star-code` 的 `muse-python-rc8` 分支，上传结果以 Git 提交和远程核对回执为准。

## 功能与 AC 对照

| 需求 | 开发和自动证据 | 尚需真实/人工证据 |
|---|---|---|
| U01 / AC01–03 worktree | 短根/深路径/中文空格、审批冻结、重启、保留父改动、集成/失败完成门槛；durable_worktrees、worktree_lifecycle、agent_completion | 所有路径组合实际模型协作配对 |
| U02 / AC01–02 thinking | 三协议 payload、支持声明/关闭/拒绝、签名/encrypted 回放、Worker 重启、摘要 delta/completed、无摘要、不完整流；14 thinking_protocol 测试 | AC03 当前所选服务预算内冒烟 |
| U03 / AC01–03 权限 | default/acceptEdits/plan、schema10旧策略、审批模式/版本/workspace绑定、未消费批准失效、后代收紧、全部入口；permission_modes、frontend、compat_entrypoints | 正式30会话弹窗配对 |
| U04 / AC01–02 提取 | 默认关闭、成功用户根来源、快照去重、独立租约、Token/请求预算、候选/冲突/敏感校验；关闭队列不发新请求；memory_maintenance、review_regressions | AC03 60片段双人工标注及实际模型质量 |
| U05 / AC01–03 整理 | 24h/5会话门槛、项目唯一在途作业、版本/原证据、冲突确认、撤回后新投影排除；memory_maintenance | 实际长期使用质量审核 |
| U06 / AC01–02 召回 | 作用域/版本、本地排序、同provider语义ID校验及fallback、100候选/10注入、配额截断/未选原因；memory_maintenance | AC03 同义问法/语义与字面对照质量 |
| U07 / AC01–03 文件 | 分页/行号、字面/正则/大小写、数量/时间/取消、脱敏/offload；file_paging_search、workspace_tools | 独立环境真实链接门槛 |
| U08 / AC01 协调者 | 根直接/包装执行拒绝，委派/受审集成；父工作区 verification 的实际命令回执、拒绝其他worktree测试；upgrade_interfaces、review_regressions | AC02–03 双任务真实模型/冲突/统一验证与加速配对 |
| U09 / AC01–03 来源 | 显式用户目录、嵌套/local顺序和去重、越界拒绝、内置保留、项目覆盖/来源显示、API及独立Worker创建快照、停止reload版本；trusted_resources、review_regressions、durable_roles | Windows真实symlink/junction仍需环境 |
| U10 / AC01–02 Skill | /run-skill和安全别名、原文参数、固定模型/源哈希、审批及fork；任务与Skill checkpoint原子INSERT；upgrade_interfaces、durable_skills、review_regressions | 人工快捷交互复核 |
| U11 / AC01–03 trace | JSON/JSONL脱敏、直接父链、follow-up区分、单调工具耗时、计划ID/哈希、both预先拒绝；upgrade_interfaces、review_regressions | 真实协作逐例审计 |
| U12 / AC02 沙箱 | bwrap/Seatbelt统一argv、off/required冻结、缺后端/策略不支持失败关闭、Windowsunsupported；os_sandbox | AC01/03真实Linux/macOS探针BLOCKED；平台probe已准备，本机SKIP |
| U13 / AC01–02 回归 | 公开API/CLI/TUI/Web和编码/研究/资料/后台、MCP/Hooks/团队/历史回归；完整套件1075通过 | AC03独立干净Windows/真实链接和用户验收 |
| U14 / AC01–03 benchmark | 原计划/证据索引和新增60片段manifest准备；数字未预填 | 全部正式指标及人工最后审核，见验收清单 |

“自动通过”仅表示对应模拟/本机契约，不把组合测试升级为每组真实模型端到端成绩。

## 最终自动证据

- 第一轮完整：1066 passed / 2 skipped / 3 warnings，128.84s，`work/upgrade-final/full1.log`；其中1个警告为pytest缓存目录权限。
- 独立审查6个问题全部先复现：6 failed，`work/upgrade-final/review-red.log`；修复6 passed，审查员独立复测同样6 passed。新增真实父工作区验证后7 passed。
- 相关worktree/roles/skills/完成回归44 passed，`work/upgrade-final/review-related.log`。
- 最终完整：**1075 passed / 2 skipped / 2依赖弃用警告，123.26s，无失败**，`work/upgrade-final/full2.log`。跳过为本机文件符号链接权限、旧外部consolidation API未配置凭据。
- 随后额外Linux/macOS真实平台probe本机1 skipped（不是通过）；产品行为未再改变，仅保留原文件换行和加入平台测试。
- Ruff与Web TypeScript/Vite生产构建通过，API类型重新生成，git diff --check通过。
- Schema<10自动SQLite备份/integrity/audit；迁移/恢复/权限29项通过。原记忆ID/作用域与legacy/manual来源保留。

## 交付

- 使用/兼容/配置/回退：`muse-upgrade-release-notes-2026-09-28.md`。
- 人工及平台最终清单：`muse-upgrade-human-acceptance-2026-09-28.md`。
- 60片段预标注夹具：`../benchmarks/fixtures/muse-memory-upgrade/`，双人工审核后冻结，当前指标null、API状态NOT_RUN。
- 历史M0证据保留：完整1018 passed / 2 skipped，`work/upgrade-m0/full3.log`；深路径审批重新实例化Worker10 passed，`approval-final.log`。

限制：没有独立干净Windows、Linux/macOS主机或用户人工指标结果，不能标为Java完全替代版正式验收；网络允许列表当前明确不支持而拒绝，费用未知不记为0，不宣称本机已验证OS隔离。不恢复bypass、旧逐字段NDJSON、tmux、联合both回退。Git 提交使用已认证 GitHub 账户的公开 noreply 身份，不修改全局 Git 身份。

## GitHub 上传前复验

- 完整测试：**1075 passed / 3 skipped / 2 依赖弃用警告，124.64s，零失败**（`work/upgrade-final/publish-full-retry.log`）。
- Ruff、TypeScript/Vite 构建通过。跳过项为 Windows 文件符号链接权限、未配置凭据的外部 consolidation API 和 Linux/macOS 专用沙箱探针。
- 上传不调用收费 API；本地配置、状态库、运行日志和虚拟环境不纳入提交。
