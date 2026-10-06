# 商家完整发布闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans，在当前 checkout 原生执行；用户已明确要求持续完成原计划，不为内部任务切分重复询问是否继续。步骤用复选框记录，真实环境验收单列。

**Goal:** 完成原商家计划 P6–P10，打通建站、新品上线的代码准备、可信预览、商家审查和发布恢复。

**Architecture:** 保留当前 Runtime/固定角色与 Connector。新增不可变业务发布意图以及只从成功回执推导的资源引用；多步发布用独立 v2 许可，不改变 v1 批准指纹。可信后端产出验证报告，模型不能自行标记通过。

**Tech Stack:** 既有 Python/FastAPI/SQLite/httpx/Playwright、React、WordPress/WooCommerce、PHP 固定插件、Linux Docker。

**Spec:** ../specs/2026-09-30-muse-commerce-mvp-design.md；接口补充记录于 docs/commerce/development-ledger.md。

## Global Constraints

- 原模型配置、普通 Coding 入口与预算不变。不能将脚本模型测试称为真实模型验收。
- 7 类页面、每批最多 20 件简单实体商品、每件最多 5 张 PNG/JPEG/WebP 图片；每图 10 MiB。
- 审批最多 30 分钟；重复批准不续期；取消只阻止后续动作，在途结果必须对账。
- 静态主题固定 15 文件，不允许生成 PHP、JavaScript、插件或任意宿主路径。
- Windows 临时站的功能证据不能将 Linux 版本清单 verified 改为 true。
- 不复制全店数据库，不修改现有订单，不借接管非自有资源完成建站。

## Review Focus

1. 创建成功后商家修改内容：旧回执不可绑定新实体版本，后续发布应 STALE。
2. 跨项目或站点的同 ID 回执：核对完整连接作用域、操作摘要和目标绑定。
3. 一步成功、下一步未知：停止所有后续操作，重启只读对账，不能盲目重发。
4. 已批准意图被插入/改序/替换图片：摘要、依赖 DAG 和批准来源必须整体失效。
5. 导航改变有效 header：不能用读到的新 theme 指纹替代商家原批准；变化须属于可验证的前序效果。

## R1：成功创建回执与实体绑定

Files: create src/muse/commerce/release_resources.py; tests/muse/commerce/test_release_resources.py。

Consumes: WordPressConnection、已校验 ChangeOperation、OperationRecord、WordPressReader 严格资源证明、规范化 StoreSnapshot。

Produces: resolve_created_resource(connection, operation, receipt, proof, snapshot) -> CreatedResource，含实体 key/id/fingerprint 与创建操作/回执摘要。该函数不批准或签发许可。

- [x] 先写测试：页面与 SKU 成功绑定、未知/失败、旧无实体版本证明、跨项目/连接、错误摘要、手工修改、非自有实体拒绝。
- [x] 运行测试确认缺功能 RED。
- [x] 实现完全匹配的 terminal receipt + 当前 proof + snapshot owner 校验，禁止 fallback 或使用 bounded snapshot 推断不存在。
- [x] 合跑原资源证明/回执测试，并在临时站实际创建→读取→绑定→编辑后拒绝（16 项绑定测试与 WP 实测；完整发布未验收）。

## R2：不可变业务发布意图与 v2 执行许可

Files: create src/muse/commerce/release.py, release_approval.py; modify connector authorization.py、PHP protocol.php；test_release_intent.py/test_release_authorization.py。

Consumes: P6 准确代码包、冻结事实、商家目标、全部初始资源版本与 R1 资源绑定。

Produces: ReleaseIntent/ReleaseStep 固定动作 DAG，业务批准绑定整个意图；StepExecution 仅由可信 broker 按前序回执物化。v2 audience/version 与 v1 完全分开，不能让模型提交物化后的 ID 或重签旧批准。

- [ ] 测试 DAG 插入/改序/跨意图引用、源码/内容/目标/验证报告变化、过期撤销及未知前序阻断。
- [ ] 实现私有持久来源和批准。当前 project/plan 取消、STALE 或来源变化持续拒绝；受控执行状态变化不重写冻结来源。
- [ ] 只对可验证前序效果推导触及资源的新版本；其它初始依赖保持精确版本。主题/导航间接效果必须逐字段验证，不接受任意新快照。
- [ ] Python/PHP v2 跨语言契约、并发取消、崩溃窗口、拒绝旧 audience 回归。

## R3：隔离 staging 与可信验证报告

Files: create src/muse/commerce/verification.py、preview.py；完善 isolation.py、environment.py 和 deploy/commerce 固定部署；test_commerce_verification.py。

Consumes: 封存代码/媒体/意图、真实固定版本 Linux 环境、独立 staging 目标。

Produces: 绑定代码、业务摘要、目标和 snapshot 的 VerificationReport + PreviewRef；仅真实 OS/浏览器/事实/购买证据全部通过才可 REVIEW_REQUIRED。

- [ ] 测试缺 daemon/未验证镜像/宿主命名空间/密钥或 socket 可见/任意 URL 跳转全部拒绝。
- [ ] 执行真实 Linux 探针，创建独立 staging，验证 7 类页面、390/1440 布局、链接、SKU/价格/库存/图片及测试订单。
- [ ] 超时和失败保存诊断，passed=false，不能消费模型“测试通过”的文本。

## R4：远端图片与公开审查/发布界面

Files: create connector media.py/PHP includes/media.php、Commerce review/publish/reconcile API、frontend commerce Review/Preview/PublishProgress；对应 API、PHP、浏览器测试。

Consumes: R2/R3 批准和验证；已有 ProjectMedia 的净化字节及哈希。

Produces: 固定受签名媒体创建、SHA 绑定商品图片、商家可审查差异和显式批准；按回执显示部分成功/未知结果。

- [ ] 测试图片字节或引用变更、非法格式、跨项目媒体、文件系统崩溃、重复点击、取消及批准过期。
- [ ] 媒体第九类操作显式升级 allowlist；有持久未知栅栏，禁止走服务用户原生上传权限绕过批准。
- [ ] 连接建站和上新完整 DAG；操作恢复只读对账，不自动解除 UNKNOWN。
- [ ] 桌面/手机实际审查、批准、发布、恢复测试，并确认原 Coding 入口和订单不受影响。

## R5：移交、第二环境恢复与最终验收

Files: extend export.py，create restore.py；更新 quickstart、connector、验收报告和最终 checkpoint。

- [x] 实现同事务离线恢复、新项目/图片引用重建、准确主题来源索引/下载/继续开发、再次导出恢复；不导入旧许可。
- [ ] 从导出准确主题、净化图片和事实恢复到第二个独立测试站；新凭据单独配置，新版本重新验证和商家批准，不导入旧许可。
- [ ] 在另行明确 API 预算后运行原计划 6 个真实模型案例；记录实际费用/时长及失败，人工验收由用户完成。
- [ ] 运行根目录全量测试、Ruff、类型检查/生产构建、固定 WP 故障及平台验收；真实未运行项保留 NOT_RUN。
- [ ] 全部实现结束后一次 fresh whole-branch review，修复有证据的问题，再核对最终验收；不按每个内部任务重复派审查。

## 自检

R1/R2 对应 P3/P7 的资源与批准边界；R3 对应 P0/P5/P6；R4 对应 P7/P8/P9；R5 对应 P10。所有步骤都保留原全局限制。当前只有静态代码准备/图片本地上传/临时站固定操作通过；上述未勾选项不代表已完成。
