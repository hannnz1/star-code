# 商家运行闭环剩余实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans，在当前工作目录继续内联执行；用户已授权完成完整首版，不按任务重复询问。最终全部实现结束后仅一次全分支 fresh review。

**Goal:** 接通既有准确代码、v5 预览来源、v4 商家审查/发布服务，使建站与新品两条流程在受信部署中真正运行。

**Architecture:** 原 Runtime/模型配置继续处理固定三角色。Linux provisioning 和验证是固定后端工作，不是模型工具或用户提交 passed 标志。运行数据库保存未知栅栏、验证作业和来源；WordPress/HMAC 秘密只在独立连接服务加载。预览与正式目标不共享数据库或卷。

**Tech Stack:** 既有 Python/FastAPI/SQLite/Playwright/httpx、Docker CLI、WordPress/WooCommerce、固定 PHP Connector、React。

**Spec:** ../specs/2026-09-30-muse-commerce-mvp-design.md；前续计划 2026-10-01-commerce-release-continuation.md；执行证据 docs/commerce/development-ledger.md。

## 全局边界

- WordPress + WooCommerce，一套固定 15 文件主题，店长/网站开发/商品内容三个角色。营销、分析不在首版，先完成 10 次真实商家任务再决定。
- 每批 1–20 件简单实体商品，最多五张 PNG/JPEG/WebP；每图 10 MiB、项目 100 张/100 MiB；审批最长 30 分钟，重复不续期。
- 不复制客户/订单数据库，不覆盖商家非自有资源，不把 unknown 当作失败重发。预览只允许 staging、禁止真实扣款/邮件/索引；正式 writes 要真实验证和商家明确批准。
- 当前没有真实 Linux/Docker 环境。可继续实现离线合同，但不得改 verified=false 或把模拟探针计作真实通过。本轮没有 Commerce 付费模型预算，不执行付费 API 验收。
- 原 Coding/记忆/MCP/多 Agent 模型配置不变；不提交或推送 Git，不同步桌面旧项目。

## 必须关注的输入与故障

1. Linux CLI 超时可能已创建容器：固定 job identity、inspect/只读恢复，不二次建立同一环境；清理只删除自己登记的容器/卷。
2. buyer checkout POST 回复丢失可能已创建订单：发送前持久 UNKNOWN；恢复不能创建第二单。测试证据不含地址、邮件、cookie、order key。
3. 新品预览需完整页面，但正式图仍只是新品；不能改变原封存代码、source hash 或把 staging grant 当商家批准。
4. 商家确认候选文案时旧任务仍可能运行：同事务创建新资料来源、使旧计划/批准失效并取消旧队伍，不给旧任务续权。
5. 第二站恢复不具备旧站资源 ID、凭据或许可：使用新连接/快照/源意图、重新验证与批准。

## A：参考环境自动准备与固定安全设置

创建 `src/muse/commerce/reference_environment.py`，扩展 `scripts/commerce/bootstrap.py`；创建固定 staging safety/bootstrap PHP 资源。使用现有 environment.validate_lock、Docker CLI 有界读取和私有 CLI config，不接受模型 Shell/URL/宿主挂载。

Consumes: 受信服务路径、固定锁定 manifest、project/job identity、已校验离线 Woo 资源和 Connector/主题资源。

Produces: 与 job 绑定的新 staging EnvironmentRef/私有连接、容器/卷身份与探针证据；失败/未知状态不返回“ready”。

- [ ] 先写缺 daemon、未验证 digest、已有/外部卷、宿主 namespace/socket、资源 hash 错误、超时/取消和 staging safety 未生效测试，观察 RED。
- [ ] 在服务私有目录生成固定 Compose/密码/记录；只用 digest 镜像、独立内网/卷、loopback web，无下载或任意安装。
- [ ] 固定 CLI/PHP 初始安装仅处理新空环境；Woo/Connector 文件精确验证，账号最小权限，屏蔽邮件、真实网关、索引和外部服务请求，检查实际设置。
- [ ] inspect 和实际 readback 后生成连接；留持久任务身份，未知启动只查询，清理不触及现有商家站或其它 job。
- [ ] 相关合同回归；真实 Linux 测试无环境时仍 NOT_RUN。

## B：可信购买/页面验证与持久作业

创建 `src/muse/commerce/buyer_probe.py`、`trusted_verifier.py`、`verification_jobs.py`。复用 staging_source/journal/publisher、verify_staging_facts、capture_staging_preview、PreviewRepository。扩展 request_review/固定服务 API/UI 作业进度，不暴露验证报告上传。

Consumes: 当前成功的三角色成果和准确代码、独立 staging 来源/已核对完整效果日志、正式目标只读快照与原始 absence proofs。

Produces: 固定后端真实完成九类检查的 `trusted_merchant_verification`、与 v4 正式意图绑定的审查记录；任一缺失/失败保持 BLOCKED/VERIFYING 和诊断。

- [ ] RED：模型 passed=true/陈旧来源/缺 probe/缺订单/截图缺宽度/失效内容/取消/checkout unknown 不可生成批准。
- [ ] 后端通过 A 创建独立站、prepare_staging_source 与真实 Docker capture 授权 v5；逐步准备后独立 readback，不能复制 live DB。
- [ ] 7 类页面和 390/768/1440 截图、链接、SKU/价格/库存/图片、实际模板/设置/分类名验证；空商品建站使用明确标记的 disposable buyer probe，不改变商家商品事实。
- [ ] 合成买家通过固定 Store API cart/checkout + 浏览器验证，只有独立 staging 和离线网关。先持久发送栅栏；结果未知停止、只读核对；不自动创建替代订单或扣库存补偿。
- [ ] 验证成功后同事务重新核对项目/计划/代码/目标/取消，产出九类报告和 REVIEW_REQUIRED，调用 MerchantReleaseApprovalRepository.stage_review；模型无写该 artifact 的能力。
- [ ] 作业重启恢复与超时诊断，不重复模型调用/部署/商家写入；公开只看精简证据与状态。

## C：商品内容候选的商家确认

创建 `src/muse/commerce/content_proposals.py` 与前端候选审查；修改 orchestration.submit/API。只有 title/description 改写能进入待确认候选；SKU/价格/币种/库存/分类/图片/原 source_facts 不由模型悄悄修改。

Consumes: 固定内容角色当前 leased task、原始商家 ProductDraft、结构化候选与 call_id。

Produces: 持久 source/candidate 摘要和明确商家确认后新 ImportedProducts 来源；不直接发布、不续用旧代码/批准。

- [x] RED：模型自行确认、价格/库存篡改、项目/版本变化、重复提交、确认并发/取消、旧许可复用。
- [x] 保存冻结候选/原事实和待补说明；商家逐项看到改写，不以模型引用证明真实性。
- [x] 显式确认的同事务创建新批次/项目版本、使旧源计划失效并取消旧队伍；重试仅返回原确认回执，重新任务需新代码封存/验证。
- [x] 手机/桌面真实 UI 操作，错误明确；模型费用仍仅由用户启动原 Worker 后发生。

## D：发布整体进度、第二站恢复与打包

复用 ConnectorPublicationService 和工作台，完善显式整批发布、取消/过期/未知停止；复用 ProjectRestorer 新项目/新媒体/原主题来源。

- [ ] 成功/中断/未知结果批次 UI；一份商家批准对应完整冻结图，任何一步不确定就停，不自动重发。
- [ ] 在 A 的第二个独立站恢复导出资料，重新登记连接、准备源图、验证和批准；旧回执/资源 ID/凭据/许可不得迁入。
- [ ] 校验分类名与 ID、商家已有订单/编辑不受覆盖；保留冲突证据。
- [ ] 新 wheel/fresh venv 安装、pip check、Connector/主题/前端逐文件资源校验，原编程核心全量回归与 Ruff/类型/生产构建。
- [ ] 全部实现完成后一次全分支 fresh review，必要问题 RED→GREEN；新增失败或修复后才扩大/重复检查。
- [ ] AC01–AC09 最终证据矩阵区分代码合同、便携 CMS、真实 Linux、付费模型、人工；六个真实模型案例等待另行 API 预算，人工测试留给用户，不能预填 PASS。

## 执行顺序与当前状态

截至第 81 批：C 已完成；D 连续发布 UI 已实现；A 已实现资源准备、一次初始化、严格回读、只读恢复、拥有资源清理、独立服务/API/主程序调用和桌面/手机面板。B 的固定 Store API buyer sender、独立签名订单回读与金额核对已实现，并在一次性 Windows CMS 上测试通过；后台验证已有私有持久作业、固定阶段执行器和未知结果防重发合同。新增每作业独占参考站绑定，预览部署授权和截图保存识别私有目标而不修改商家项目版本；参考站阶段已接通受信服务，安装前增加取消/来源检查。尚未接通其余生产适配器和启动循环，仍缺完整浏览器/九项可信 verifier 与 request_review 整合，以及 D 第二站恢复/最终打包验收。第 50 批全量 1900 passed / 30 skipped / 4 warnings，949.65 秒，不覆盖后续批次。无真实 Linux daemon，A 整阶段不能标记验收完成。以上未选步骤仍未整阶段完成，不是新的产品范围扩张。


### 第 85–87 批增量

已新增来源捕获、预览部署和购买三个固定生产适配器，使用原作业、专属参考站、v5 grant/效果日志和 SyntheticBuyer；回复丢失只读对账，不重新授权/部署/下单。首四个阶段可以在显式测试配置下顺序执行，但当前没有完整部署启动循环，也没有把六阶段/九项报告接到 request_review，B 整项仍未完成。

后续优先：浏览器/事实适配器及完整报告 → 后台启动与公开精简进度 → 中断后的明确续跑（不能自动重发未知操作） → 无商品/零库存的独立 disposable buyer fixture → Linux 实测/第二站/最终交付。购买后库存行为须在实际锁定 CMS 流程中核对，不用模拟成功替代端到端证据。


### 第 88 批增量

浏览器与事实固定生产适配器已实现，准确消费部署来源、回读真实平台数据并保存原浏览器的截图/诊断；事实阶段要求当前 snapshot 与浏览器核对来源一致。恢复须逐张复核 PNG，不重新运行浏览器。六阶段仍是私有模块整合，不代表后台循环、最终九项 producer 或商家审批已接通；需要最终报告安全合成与来源转入审查的同事务实现。

### 第 89 批增量

已增加私有 VerificationRuntime 固定六阶段轮询与中断记账，拒绝任意 handler 和混用来源。正式宿主启动配置和公开进度尚未接入；最终九项报告/审查同事务仍是下一项整合工作。RUNNING 恢复需宿主明确确认独占服务，不自动中断其它 worker；回执收齐不能直接生成批准。第 88 批整仓 2092 passed / 31 skipped / 1 failed；launcher 退出竞态独立重跑及 12 次重复通过，但未确认根因，不能将全套验收标为通过。

第 89 批后续通过确定性退出时序注入确认并修复 launcher 过早报错，新增仍存活不能忽略拒绝的反向检查；runtime/jobs/readback/launcher 最终 42 passed，109.28 秒。上段整仓结果是修复前历史证据；修复后没有新整仓 PASS 或真实 Linux 验收，详见 ledger。

### 第 90 批增量

固定 TrustedMerchantVerifier 已实现九项证据报告生成及原预览期限约束，读取正式目标当前快照/缺失证据并绑定 v4 意图；审批端再次核对 provenance、证据字节及期限，时钟回拨不能续权。报告生成本身保持 VERIFYING，不自动给商家批准。下一项为审查状态与审查记录的同事务转换；须保留私有预览来源在审查阶段的只读访问，不能为了展示截图开放新的预览写入。之后接入宿主启动和公开精简进度，再完成显式恢复及空商品测试购买。B 整项仍未完成，真实 Linux、真实模型和人工验收仍不预填 PASS。


### 第 91–93 批增量

报告、REVIEW_REQUIRED 与准确审查记录已同事务接通；后台服务、Linux 独占锁、CLI/ASGI 生命周期、受鉴权精简进度以及工作台入口已实现。中断结果仅明确只读核对；部分预览续跑只允许已核对且仍持原有效许可的未发送步骤。原编程能力和模型配置保留。相关合同与桌面/手机浏览器回归详见 ledger，不算实际 Linux 或全阶段验收。后续剩余重点：空商品/零库存的独立测试购买商品、真实购买库存行为、第二站完整恢复、最终安装/资源校验与全量编程核心回归；真实 Linux、付费模型、人工证据继续保持待验收。

### 第 94–97 批增量

无货/零库存的独立隐藏 fixture 已完整接入六阶段购买、浏览器和可信报告，并从正式发布商品中排除；签名测试订单库存保护已有一次性真实 Windows CMS 证据。第二项目恢复后的新连接、新封存、新验证、新报告、新批准合同完成；实际 Linux 第二站尚缺环境。最新 wheel 干净 venv 安装、依赖检查、33 个资源摘要通过；第 94 批全量 2132 passed / 31 skipped，最新第 98 批全量进行中。

工程剩余：最新全量结果确认和最终证据更新。产品验收剩余：真实锁定 Linux/Docker 上建站/新品及第二站/隔离故障验证、另行预算的六个真实模型案例、最后人工测试。边界记录见 docs/commerce/acceptance-evidence-2026-10-02.md；不能将合同和 Windows CMS 局部验证升级为全部 AC 通过。

第 98 批确认：新安装、资源校验、最新整仓分批覆盖、证据更新均已完成，2161 passed / 31 skipped，2192 用例无遗漏，各批 exit 0。单进程全量中断不计通过；首轮分批的审批状态偶发异常经完整批次及 10 次独立重复未复现，根因仍需追踪，不虚构修复。剩余环境与产品验收条件不变；已有工程测试不能替代缺少的真实 Linux 环境。人工测试仍留最后。
