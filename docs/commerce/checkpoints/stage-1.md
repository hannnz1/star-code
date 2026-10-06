# Commerce 开发检查点：准备功能与离线主题

日期：2026-09-30。结论：**PARTIAL；真实平台 BLOCKED；完整 MVP 未完成、未验收。** 此报告不把分阶段演示或 mock 结果算作正式建站/新品上线成功。

## 源码与环境

- 开发位置：`outputs/muse-next`，分支 `muse-integration`；原桌面 StarCode checkout 未改动、未推送 GitHub。
- 基线提交：`4aec15ae79648f1e398b29e975177b73ca532fb6`。本轮变更未提交；该基线 ID 不代表包含本批功能的完整提交。
- 当前 389 个源码/配置/测试/spec 文件的清单：`work/commerce/checkpoints/stage-1/source-manifest.json`。
- 清单 files 数组 canonical JSON 的 SHA-256：`4eba1a05d5b1a7305cd0abb4b6db4ad35fb086916663f52d88de5d5d0318be43`。它用于定位未提交代码，不替代发布代码提交/批准。
- 日志、截图、当前前端构建和版本锁哈希：`work/commerce/checkpoints/stage-1/evidence-manifest.json`。只记录本轮明确证据；没有包含凭据、订单或客户资料。
- WordPress/WooCommerce 候选版本在 `deploy/commerce/versions.lock.json`；`verified=false`，镜像 digest 未冻结。Docker CLI 存在但 daemon 不可连接、缺 PHP CLI；用户确认目前没有独立环境。未启动或部署店铺。
- 沿用 StarCode 原模型配置；本轮模型调用 0、费用 0、店铺写入 0。未以历史 SWE/MCP/长会话成绩替代此次 Commerce 验收。

## 实现与未实现

| 任务 | 本轮状态 | 可核对的能力和缺口 |
|---|---|---|
| P0 环境冻结 | PARTIAL / BLOCKED | 未验证版本锁拒绝部署；staging/live-test 配置名和数据库卷分开。标志尚未证明禁邮件/支付/索引实际生效 |
| P1 契约、迁移 | OFFLINE_CHECKS_PASS / 未提交 | schema 11 原子迁移及 v10 备份、保留任务/记忆/批准；项目/计划/事件 API、乐观 revision、去重、项目范围及脱敏错误 |
| P2 只读 Connector | PARTIAL / BLOCKED | 独立 Python 服务、Linux secret 文件检查、固定目标、HTTPS/重定向/根超时/最多 2 次只读重试、类型快照与 fingerprint；固定只读 PHP 插件。真实 WP/PHP 和 MUSE 项目连接/刷新 API 未完成 |
| P3 固定写操作/回执 | NOT_IMPLEMENTED | 未开放写路由、operation ledger 或主题部署 |
| P4 三角色编排 | NOT_IMPLEMENTED | 没有 Commerce 根任务/角色子任务；不显示模拟团队进度 |
| P5 主题/建站 | PARTIAL | 七页 blueprint/导航/缺失设置持久化、修改后 STALE；自有区块主题、确定性 ZIP、哈希、不可变 PHP/路径/静态内容检查。未有 staging/预览/真实 block schema/购买验证 |
| P6 Coding Bridge | NOT_IMPLEMENTED | 原独立 coding 入口保留；Commerce 限定改码、受限 Linux 执行与目标验证未接入 |
| P7 批准/发布恢复 | NOT_IMPLEMENTED | 没有商家业务批准或发布；30 分钟版本绑定、写超时对账、部分成功和取消恢复仍未实现 |
| P8 新品 | PARTIAL | 严格 CSV 1–20 件、Decimal、SKU 去重/公式拒绝、货币/库存校验；持久草稿、重复请求去重、revision 保护。图片真实解码有测试，上传/成果存储未接；店铺已有 SKU 未检查，上新未完成 |
| P9 商家 UI | PARTIAL | 品牌/工作区向导、七页结构准备、CSV 错误纠正和草稿列表；390/1440px 浏览器及原任务入口验证。没有发布/团队/预览/差异审查页面 |
| P10 导出与验收 | NOT_IMPLEMENTED | 未做第二环境恢复、6 个真实模型案例及人工验收 |

P5 renderer 增加必需 code_revision 参数，避免伪造来源版本；此阶段没有生成可发布包。主题资源的 wheel inclusion 已配置，但新 wheel 构建和干净安装未验证。

## 检查命令与实际结果

以下命令在本 Python checkout 执行。完整日志保留首次失败与修复后结果，不覆盖或删除。

| 检查 | 预期 | 实际结果/证据 |
|---|---|---|
| 修改前全量 pytest | 记录基线，不预设通过 | 1074 passed、3 skipped、1 failed；`work/commerce-baseline.log`；原 launcher taskkill Access denied |
| 准备批次首次全量 pytest | 发现新/旧问题 | 1138 passed、3 skipped、2 failed；`work/commerce-full.log`；原 launcher + 记忆时间并列问题 |
| 三项审查复现 | 修复前失败 | `work/commerce-review-red.log`、`work/commerce-review-ui-red2.log` |
| 审查修复后 Commerce + 原前端 | 全通过 | 77 passed；`work/commerce-review-green.log`（该时点测试数量） |
| 冻结时钟/重复 ID/保留事实版本 + 原记忆 | 先失败再通过，保留原断言 | 新 3 项 RED→GREEN，相关 15 passed；最终全量也未再出现记忆失败 |
| 准备批次最终全量 pytest | 全通过 | 1152 passed、3 skipped、1 failed，344.53s；`work/commerce-final.log`；仍为原 launcher 权限失败 |
| 主题包首批测试 | 先失败再实现 | 13 failed（模块缺失）→13 passed；`work/commerce-theme-red.log`、`work/commerce-theme-green.log` |
| 主题/结构与额外主动内容探针 | 全通过 | 23 passed；`work/commerce-theme-integrity.log`；ZIP 越界/重复/符号链接、PHP/哈希篡改、脚本/外部资源拒绝 |
| 加入主题后的最终全量 pytest | 全通过 | **1172 passed、3 skipped、1 failed，145.55s**；`work/commerce-final-with-theme.log`；原 launcher 权限失败仍存在 |
| Commerce 收集数量 | 与全量新增量一致 | 98 tests collected；`work/commerce-collected.log`；上述全量中这 98 项均通过，不是 98 个真实业务验收案例 |
| Ruff：src/muse + tests/muse/commerce | 零错误 | All checks passed；不宣称全部遗留 mewcode/tests lint 通过（宽范围结果 `work/commerce-ruff.log` 仍有 540 项原问题） |
| OpenAPI 生成类型 --check | 字节一致 | 通过；类型生成器改为 UTF-8/LF、检查真实字节，CRLF 漂移复现已验证 |
| git diff --check | 无 whitespace 错误 | 通过；Git 的 LF/CRLF 工作副本提示不是测试通过声明 |
| npm.cmd --prefix frontend run build | 前端编译成功 | 成功；dist 文件记录在 evidence manifest；浏览器使用真实本地 API，未解除 CSP |
| uv lock --offline | 锁校验成功 | BLOCKED：uv.exe 执行拒绝；Pillow 已有锁定 package，仅补 root 依赖 metadata，干净 locked install 未验证 |
| hatchling.build.build_wheel | 当前 wheel 含主题/前端 | BLOCKED：venv 无 hatchling，也无 pip；没有使用旧 wheel 冒充本轮构建 |
| PHP lint、WP/Linux、staging/购买、真实模型、人工 | 正式环境验证 | NOT_RUN / BLOCKED；不得记 PASS |

最终全量实际命令（exit code 1）：

```powershell
.\.venv\Scripts\python.exe -u -m pytest -q -p no:cacheprovider --basetemp work/commerce-final-with-theme-tmp *> work/commerce-final-with-theme.log
```

失败用例：`tests/muse/integration/test_launcher.py::test_stop_script_matches_serialized_process_time[True-False]`，Stop-MUSE.ps1 调用 taskkill 返回 Access denied。修改前已存在；本轮保留原脚本和测试，未改为 SKIP 或模拟通过。

## 审查与原能力回归

独立审查与三项 Important 处置、14 项无法判定范围见 [review-results.md](../review-results.md)。没有重复评审覆盖失败记录。审查后的主题补充尚未独立审查。

浏览器验证真实项目保存/重载、CSV 错误纠正与持久化、A 项目响应晚返回时切 B 不串数据、页面无 Token、390px 无横向溢出，并能切回原页面创建 coding 任务（queued）；没有执行付费任务或把 queued 当作编程成功。全量覆盖原 API、迁移、预算、权限、委派、研究、资料、记忆和任务相关测试，但 Windows launcher 未通过。

截图：`work/commerce/checkpoints/stage-1/merchant-1440.png`、`merchant-390.png`；它们是 MUSE 准备 UI，不是店铺预览截图。

## 正式验收矩阵与下一阶段

| Spec 验收 | 本轮结论 |
|---|---|
| AC01 原能力 | 离线回归 PARTIAL：原 launcher 权限失败，真实模型未跑 |
| AC02 建站 | NOT_RUN：只有结构/主题离线实现，Commerce Coding Bridge/实际购买未接 |
| AC03 新品 | NOT_RUN：仅导入草稿，无上新 |
| AC04 上下文 | 离线 fingerprint PARTIAL；真实改价/改页、刷新快照和拒绝旧批准未接 |
| AC05 团队 | NOT_RUN：未创建业务子任务 |
| AC06 生产边界 | NOT_RUN：零写入是当前未开放发布的结果，不能证明 Linux 越权隔离 |
| AC07 故障恢复 | 离线输入/只读/归属探针 PARTIAL；真实写故障未跑 |
| AC08 可迁移 | NOT_RUN：未导出到第二环境恢复 |
| AC09 质量/取消/手工编辑 | 输入拒绝及事实缺口 PARTIAL；真实编辑冲突/审查/取消仍未实现 |

可以继续 P2 项目连接与 P4 编排的离线开发；不能将第一阶段整体放行。真实 Linux/WP 环境需先建立、锁定并验证，之后实现并验证 P3 写内核、P6 隔离、P7 审批/对账，才能连接现有准备功能成为两条实际业务流程。完整路径仍按原计划，不缩减正式验收门槛。

上手见 [quickstart.md](../quickstart.md)，所有偏离和裁决见 [development-ledger.md](../development-ledger.md)。
