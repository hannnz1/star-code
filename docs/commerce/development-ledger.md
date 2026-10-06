# SDD ledger — plan: docs/superpowers/plans/2026-09-30-muse-commerce-mvp.md

## 2026-10-05：完整商家回归与真实本机 CMS 补测

新增验收脚本 `--scope merchant`，区分全部商家后端和浏览器文件，保留跳过原因并扩大源码/WordPress 插件 SHA-256 清单。参数、文件去重、语法和 Ruff 检查通过；本轮完整测试由直接 pytest 两批和 CMS 补测执行，没有声称整个新脚本模式已运行。

综合批次 1114 passed / 28 skipped（783.46 秒），11 个浏览器文件 30 passed（152.89 秒）。恢复原 loopback 一次性 CMS 后 26 passed / 2 failed（274.71 秒）；局部诊断复现一次，异常为 Snapshot unavailable，数据库只读核验恰有 200 页。保持产品上限，另建全新数据库重跑 28 passed（537.56 秒）。旧数据库保留，临时诊断修改撤回，原配置/凭据恢复，本轮 PHP 和 MariaDB 已关闭。

对全部 1161 个收集 ID 去重、核对并用对应 CMS 实测替换跳过项，最终 1161 passed、0 skipped、0 failed、0 errors，无遗漏。保留首轮失败及复现 XML，不累计重复用例。最终清单 `work/merchant-final-coverage-20261005.json`；验收说明 `docs/commerce/acceptance-evidence-2026-10-02.md`。

本轮未调用付费模型、未写真实商家站、未推送 GitHub。CMS 测试的宿主隔离/正式许可仍是夹具前提；Docker daemon 仍不可连接，版本锁 verified=false，完整 Linux、真实商家部署、模型效果和人工验收尚未通过。

## 2026-10-05：真实模型与 Linux 验收推进

用户授权商家模型验收新增费用上限 2 美元。原 gpt-5.4-mini 模型配置保持不变，累计 108 个真实 API 请求，所有请求有用量，按未缓存输入价格累计上界 0.380871 美元。诊断失败与修复复测费用计入同一账本。最新批次建站、新品、注入三例角色产物完整，均安全停在 VERIFICATION_UNAVAILABLE；政策缺失例无模型请求且停在 FACTS_INCOMPLETE。仅准备阶段通过，不代表商家发布通过。

修复准确步骤 ID 的上下文投影、商品数组提交说明、三角色结构化输出完成门禁、Docker CAP_ 与 EXPOSE null 检查格式、宿主标准 PATH；新增可选固定内部地址的回环预览代理。集中回归 101 项通过；新增最小环境合同 27 项通过；再次继续后普通沙箱复验 70 项通过，范围重叠不累加。

专用 WSL2 `MUSE-Commerce-Test-20261005` 已安装实际 Docker 29.1.3/Python 3.12。官方根文件系统校验成功，原损坏 Ubuntu 未修改，环境存储 E 盘。基础 Agent Linux 内核隔离及代码读写捕获实际通过。实际店铺运行副本到 bootstrap 仍失败，保留原始证据及部分测试资源；默认镜像部署锁继续 verified=false。完整 Linux 店铺、真实发布和人工验收仍未通过。

下一条 Linux 诊断命令在执行前被自动审批审核服务的 Codex 额度限制阻断，未执行；不绕过审核。普通沙箱本地检查和文档已继续。详细状态与恢复步骤见 `docs/commerce/runtime-acceptance-2026-10-05.md`。未推送 GitHub，未写真实商家站。

## 2026-10-05：Linux 双副本与实际沙箱商品发布通过

续接后审批服务恢复。修复 WordPress REST permalink、WooCommerce 合法 @/逗号路径，以及 Docker inspect 动态状态和挂载排序对清理的干扰。保留固定归属、挂载内容、配置稳定性和外部消费者检查。最新相关回归 52 passed，无跳过；Ruff 通过。

实际 run-15 双店 READY、安全与资产哈希读回、资源不相交、各自清理通过。run-17 两店各发布两个合成商品、四个唯一签名回执，重复请求回执一致，发布状态/价格/库存再读回一致，两店均 CLEANED。证据位于 work/linux-runtime-run15-evidence.json 和 work/linux-runtime-release-run17-evidence.json。run-01 至 run-16 历史记录的资源清理均返回成功，保留私有诊断文件。

本次未增加付费模型请求，累计模型费用上界仍为 0.380871 美元。上述结果不代替独立六阶段验证报告、真实商家政策/变更审查、生产兼容性或人工验收；默认版本锁仍为 verified=false。未推送 GitHub。

## 2026-09-30：实施开始

- 执行：当前会话原生执行，用户已明确授权按已审阅文档开发。
- Ruling: 复用 `muse-integration` 的独立交付 checkout，不再另建 checkout — 现有开发文档和 Python 交付基线均在这里，原 Java 项目保持独立 — 若选择不合适，需将本轮明确文件迁到新的隔离分支。
- Ruling: 本机有 Docker CLI，但无可连接的 Docker daemon，未发现 PHP CLI；真实 WordPress/Linux 验证 BLOCKED — 不启动额外桌面窗口或猜测远程环境，继续独立的离线契约实现 — 不能据此宣称平台功能验收。
- 前置接口：P1 定义全部业务模型/表→P2/P4/P5/P7；P2 固定目标和快照→P3/P5/P7；P3 回执→P7；P4 原任务委派→P5/P6；P5 包/预览→P6 验证→P7；P7 发布→P8 新品；P1/P7/P8 API→P9；全部→P10。
- Ruling: P6 可以消费 P1 ChangeSet 模型生成离线验证输入，但不能在 P7 发布内核前执行 live — 解决计划中 P6/P7 的表面循环 — 成本是上线验证必须在 P7 后重做。
- P0 本轮基线：1074 passed / 3 skipped / 1 failed；失败为原 launcher Stop-MUSE 测试中的 Windows taskkill Access denied，发生在 Commerce 修改之前。证据 `work/commerce-baseline.log`；保留原测试，不以旧 1075 历史覆盖。
- Ruling: 本轮先交付 P1 与 P2/P8/P9 的独立离线部分，不把它们称作完整工作流 — P0 的真实环境、P3 写入回执和 P6 隔离尚未具备，故不开放任何发布/付费团队入口 — 代价是需要后续接通真机及任务编排。
- Ruling: 事实审查保守要求所有改写先由商家确认，而非相信模型自报来源 — 文本匹配不能证明新功效/认证是真的 — 代价是首版草稿润色需补商家确认流程。
- Ruling: 增加 Pillow 为运行依赖（已有锁定 12.3.0），用真实解码校验图片 — 只检查 MIME/文件头会接受伪图片 — 代价是安装增加一个依赖；本机 uv.exe 执行被拒，沿用已有 package 只补 root dependency metadata，后续需 uv locked install 实测。
- Ruling: 修正类型生成器为 UTF-8/LF 字节一致并严格 check — 当前 Windows 输出触发真实 git whitespace 错误，测试已 RED→GREEN — 代价是旧 CRLF 生成文件需重生成，不改变业务类型语义。
- 本轮任务脚本按 Windows 原生命令执行，证据留在 `work/commerce-*` 与本持久 ledger；不删除原始测试记录或其他计划空间。
- 当前所有 Commerce 正式验收：NOT_RUN。收费模型请求 0，店铺操作 0。

## 任务状态（截至第八批，仅本机实现与检查）

| 任务 | 状态 | 证据 |
|---|---|---|
| P0 | PARTIAL / 真实环境 BLOCKED | Docker daemon/PHP 缺失；离线版本清单拒绝未验证部署；1074 passed/3 skipped/1 原有环境失败 |
| P1 | OFFLINE_CHECKS_PASS / 未提交 | schema 11 原子迁移、备份、项目/计划/事件 API、乐观锁；独立准备批次审查三项 Important 已修复 |
| P2 | PARTIAL / 真实环境 BLOCKED | 20 个只读目标/重试/脱敏/快照/secret loader 测试；固定 PHP 快照插件待 lint/WP 实测；尚无项目连接 API |
| P3 | PARTIAL | 固定操作合同、许可、持久发送栅栏、内部默认关闭发布器和回执对账；PHP 原子写端及真实店铺未实现/验收 |
| P4 | PARTIAL | 三角色准备任务、持久产物及队列控制已有；真实完整团队业务闭环未验收 |
| P5 | PARTIAL | 七类页面/导航与缺失设置检测、持久草稿；自有原生主题与确定性 ZIP/哈希/不可变 PHP 校验离线通过；尚无 staging 或购买实测 |
| P6 | NOT_RUN | |
| P7 | PARTIAL | 持久审查批准、过期/撤销、主题候选与内部授权已实现；公开发布 API、多步恢复编排及实际发布待做 |
| P8 | PARTIAL | 22 个导入/事实测试通过；持久 CSV 草稿 API 去重/版本保护；图片上传、发布及店铺 SKU 对账未实现 |
| P9 | PARTIAL | 商家项目/新品准备 UI；1440/390 px 与原任务 UI 共 6 项 browser/contract 测试通过；未提供发布按钮 |
| P10 | PARTIAL | 离线格式 1 导出、鉴权 API 和工作台下载；自动恢复、第二环境迁移、真实六案例和最终验收未完成 |

## 继续开发：第二批（2026-09-30）

- P2 更新为 PARTIAL / OFFLINE_CHECKS_PASS：主程序固定 Connector adapter、项目连接/刷新/读取 API 已实现；same-ID 重新绑定不复用旧上下文，失败保留原快照，跨项目/版本阻止，鉴权只保留已知错误 code。真实 WP/身份隔离仍 BLOCKED。
- P4 更新为 PARTIAL：三固定角色、冻结 prose/hash/provider/project 来源、原 SQLite 任务/租约/委派回执/技术审批、根共享预算、输出哈希、一次格式修正、事实 NEEDS_INPUT、取消与模型显式恢复已实现。网站开发只提案；完整代码桥、自动业务阶段推进及六个真实模型闭环尚未验收。
- P9 更新为 PARTIAL：连接 ID/上下文、真实三角色任务卡片、预算与队列、原审批入口提示、显式刷新/恢复已实现。保持原编程入口，390/1440 浏览器通过。尚无真实预览/发布审查/店铺修改 UI。
- Ruling: 固定团队有效工具必须由代码限制，而根 checkpoint 上限包含团队工具合集 — 原委派协议只允许父上限的子集，不能为了网站开发解开 Shell — 代价是 P6 需单独设计隔离 Coding Bridge。
- Ruling: Commerce 固定角色禁止可执行项目 Hooks、语义记忆额外请求和自动记忆收费任务；普通任务保持原配置 — 避免子系统绕过根共享预算 — 原相关运行器/Hook/记忆回归一起验证。
- Ruling: 提交结构提案、委派团队、请求审查仅持久管理记录，按原管理工具免于代码变更 verifier — 实际 RED 证明原 gate 会要求没有权限的代码工具并耗尽请求 — 将来任何真实代码修改必须继续原验证 gate，不给 WP 写操作扩权。
- Ruling: 已知缺政策/运输/付款等事实时不排队模型；保存 NEEDS_INPUT + 缺字段，资料确认后新计划 — 否则付费团队会重复处理已知阻塞 — 实站设置确认仍依赖后续 P5 与商家 UI。
- Ruling: 原 reload 对 Commerce 明确拒绝，角色哈希按计划冻结 — 不能把重载的普通 role snapshot 覆盖商务角色 — 原 Coding reload 不变。
- Ruling: 回执恢复只覆盖四个固定 SQLite 商务管理 handler，每项效果与 managed_call_receipt 在同事务提交，并绑定完整调用/审批/来源 — 无回执可证明事务未提交；损坏回执/外部动作继续 UNKNOWN — 不作为 P3 WordPress 远端 unknown retry 权限。
- Ruling: `read_offload` 纳入三角色固定工具；原任务归属校验和 12,000 字符分页保持 — 支持的长描述需要完整读取事实 — 不开放文件/任意 artifact 路径读取。
- Ruling: 流式秘密测试校验对外前缀及最终 safe(tail)，私有 look-behind 缓冲保持原语义；主适配器短 token 验证异常不显示原 env 输入 — 不以测试假设破坏流式跨片段识别。
- 原始 RED 保留；首轮全量 1202 passed / 3 skipped / 1 原 launcher failure / 4 fixture errors，129.35 秒，证据 `work/commerce2-full.log`。四项新 fixture 错误来自 test-module plugin 加载冲突，改为局部 conftest 共享实际 fixture，不删测试或跳过。
- 独立审查五项 Important 均进入一次修复，并补 crash、冻结 reload、长描述、缺事实和鉴权实际边界回归，详细见 [review-results-round-2.md](review-results-round-2.md)。后续原运行器又证明根任务提前结束/重复 advance 的错误，已 RED→GREEN。
- 第二批最终状态与全量结果记录在 [round-2.md](checkpoints/round-2.md)，本批不覆盖 stage-1 旧源码/截图/hash。所有正式平台验收仍 NOT_RUN；模型费用 0、WordPress 写入 0、没有 Git 提交或推送。

## 本批验收范围

本批为“准备”功能的部分实现，不是 Commerce MVP 全部完成。P3/P4/P6/P7 及 P10 正式闭环仍未实现；缺真实环境时不把离线 UI 叫建站/上新成功。数据库迁移与现有能力兼容的离线回归已执行；全量仍有原 Windows launcher 权限失败，真实平台验收未完成。当前无付费请求、live/staging 写入、推送。

## 审查修复与主题补充

- Final: Important 三项均处置：严格远端快照、共享 verified 版本清单、项目切换后的晚返回导入归属。77 项商家及原前端测试通过；原始 RED 和 GREEN 日志保留。审查无法判定项和风险逐项记录在 review-results.md，不代表放行。
- Ruling: 修复全量回归发现的原记忆并列时间问题，并补重复 ID/保留对象被修改的事实丢失保护 — 原用例和冻结时钟 RED 证据证明有实际影响 — 代价是修改原记忆模块，须保留原断言并跑原记忆与全量回归；15 项相关测试通过。
- 最终准备批次全量：1152 passed / 3 skipped / 1 failed，344.53 秒；仍为原 Windows launcher taskkill Access denied，记忆失败已消失。证据 work/commerce-final.log。
- Ruling: 用户明确回复没有独立环境，继续 P5 可独立验证的原生主题和离线打包，不启用真实建站/发布 — spec §10 允许离线模板/UI 继续但禁止把真实安全验收标通过 — 代价是 PHP/Woo 区块及购买流程仍需独立验证。
- Ruling: render_owned_site/build_site_archive 增加必需 code_revision 参数，不伪造未知代码提交 — 共享 SitePackage 必须绑定真实代码来源 — 代价是集成时须在干净提交/worktree 构建，并额外记录当前未提交源码哈希；当前无可发布产物。
- P5 首批 13 项主题测试 RED→GREEN，补充 7 项主动/外部内容探针，加原结构 3 项合跑 23 passed。检查 ZIP 完整清单、路径、重复、链接、大小、固定 PHP、逐文件 SHA-256、标题转义和失效哈希。WordPress block schema/实际 DOM/购买 NOT_RUN。
- 新 wheel 构建尝试：venv 无 hatchling；该 venv 也无 pip，本机 uv 仍无法执行。未绕过权限或使用历史 wheel 代替当前包，干净安装和主题 wheel 资源检查 BLOCKED。
- 主题补充后最终全量：1172 passed / 3 skipped / 1 failed，145.55 秒；失败仍是原 Windows launcher taskkill 权限问题。证据 work/commerce-final-with-theme.log；不标整轮通过。src/muse 与 tests/muse/commerce Ruff、OpenAPI 字节检查、git diff --check 均通过。

## 第三批：P3 持久发送栅栏与只读回执对账（部分实现）

- Ruling: 先实现独立 SQLite OperationLedger 和固定目标 ReceiptReconciler，不接通 POST、业务 API 或 CLI 写入口 — 远端插件授权/资源原子校验与 Linux 边界尚未验证 — 代价是本批不能创建商品或部署页面，P3/P7 仍未完成。
- Ruling: begin 在发送前即持久化 NEEDS_RECONCILIATION；即使进程在实际 HTTP 前崩溃也不自动重发 — 本地不能证明远端是否执行，宁可阻塞 — 代价是这类窗口需人工/插件回执核查，远端 404 也不能解除锁定。
- 账本按连接+环境+operation_id 去重，绑定项目与完整操作摘要；同一资源未决时阻止新操作。独立 SQLite 连接通过 BEGIN IMMEDIATE 和唯一索引竞争，终态回执持久保存。
- 对账只有一次固定 HTTPS GET，禁止跳转/代理，20 秒总时限、16KiB 上限；严格校验项目、连接、环境、操作、资源和摘要。网络异常/404/不匹配不解锁；不会发 POST。confirm 是内部可信调用，不能作为授权边界；未来发布器须验证远端回执且先 begin 再发送。
- RED 日志：work/commerce3-red.log、work/commerce3-receipts-red.log；首轮 GREEN：14 passed（work/commerce3-green.log）。测试使用真实 SQLite 与外部 HTTP MockTransport，不调用模型或真实店铺。
- Final: fixed Important 压缩回执在大小检查前解压 — 压缩回执 RED→GREEN，15 passed；请求 identity 且正文前拒绝非 identity。不重派审查。
- Final: minor (deferred): 远端成功回执 fingerprint 非法时返回 INPUT_INVALID，锁仍保持；后续远端专用 schema 统一 WRITE_OUTCOME_UNKNOWN。
- Final: Ruling: 审查无法判断远端真实性、插件原子性、掉电、重绑定与完整 P3 — 本批只交付未接通的本地基础，不将其当写授权/正式验收 — 代价是接入发布器前必须补插件和隔离环境证明。
- 第三批最终根目录全量：1233 passed / 3 skipped / 1 failed / 2 warnings，406.23 秒；唯一原 launcher taskkill 权限失败。work/commerce3-full-final.log。15 项新增模块通过；P3 仍部分实现，无模型/店铺写请求或 Git 提交推送。

## 第四批：P3 固定操作契约与内部执行许可

- Ruling: 七类 wire payload 用独立严格模型校验，导航只接受页面 ID、店铺选项只接受四个页面 ID、页面和商品内容先限定纯文本；商品媒体引用暂拒绝 — 避免任意 HTML/URL/设置/未验证图片路径进入写协议 — 代价是富文本和媒体上传需后续 P8 受控实现。
- Ruling: 使用独立至少 32-byte HMAC 密钥，内部许可绑定当前批准 ID、项目、目标连接及 URL、环境、变更集/验证摘要、全部 preconditions、完整 operation digest、签发/到期时间，最长 30 分钟 — spec 未规定 wire 签名算法，采用标准库并禁止公开签发端点 — 代价是后续插件必须实现相同规范并验证真实持久审批/资源状态，本批签名不证明这些已完成。
- Ruling: verify 必须由可信后端传入当前持久 ApprovalGrant，不信任 token 自报状态；目标 project/environment 必须与批准相符 — 支持撤销和环境绑定 — 代价是 P7 必须实现真正的批准存储、变更集成员与验证报告校验，当前模块未与 API/任务/CLI 接通。
- 契约返回深拷贝，不重写已签名操作。主题包复用已有 ZIP/固定代码/哈希校验；所有操作要求显式指纹，new SKU 以规范化 SKU 哈希标识，远端“不存在”指纹计算仍待插件实现。
- 新增 38 tests passed，work/commerce4-focused.log。RED：commerce4-red.log（模块缺失）、commerce4-target-red.log（目标描述符接口未实现）；没有真实模型/站点请求。
- Final: fixed 两项 Important — 畸形已签名 token 2 项与商品数值 7 项 RED→GREEN，47 passed；合法数值边界另复验，不重派审查。
- Final: minor (deferred): base64 token 明文不存在断言较弱；未来 claims wire 测试 decode 逐字段验证。
- Final: Ruling: content_sha256 来源真实性、持久审批、ChangeSet 成员、验证报告、远端所有权和 OS 安全仍待 P7/插件 — 签名只是内部 primitive，不开放写入口 — 代价是正式发布前必须补齐这些证据。
- Final: Ruling: 正确签名 v:true 的 equality 非严格，但唯一内部 issuer 固定 v:1，攻击者修改即签名失效 — 不判当前越权，不新增互操作协议 — 代价是新增签名来源/插件 wire 前必须严格版本类型。
- 第四批最终：根目录全量 1280 passed / 3 skipped / 1 failed / 2 warnings，486.10 秒；唯一原 Windows launcher 权限失败。全量收集新增 47 项，另补 2 项合法边界已合跑；新模块 49 项通过，与第三批合跑 64 passed。日志 commerce4-full-final.log 与 commerce4-boundaries-final.log。P3 未完成，未启用真实写入。

## 第五批：内部一次发送发布器

- Ruling: 新增 default-disabled WordPressPublisher，仅可信后端通过 current approval_lookup 使用，不注册 API/CLI/Agent 工具 — 真实审批仓储/OS 隔离与插件尚未验收 — 代价是本批不能实际建站或上新。
- Ruling: ChangeSet digest 采用完整 model_dump(mode=json) 排除 digest 字段，VerificationReport 全体字段 SHA256 绑定审批；校验操作成员、项目、环境与全部 preconditions，并在远端读取后、发送标记后再次读当前批准 — 避免变更/撤销/到期在 preflight 中漏检 — 代价是 P7 的真实持久审批实现必须遵守此规范并做取消/状态检查。
- Ruling: 本地读快照只消除已知资源变化，不能证明远端原子性；插件必须再次做授权/所有权/指纹与回执锁。缺 navigation/SKU 指纹时阻止写，不依据不完整分页快照证明 SKU 不存在 — 代价是创建商品/导航写需扩远端协议后才可接通。
- 发送前持久 begin；单次 POST 固定路径，禁跳转/proxy/压缩正文，20s/16KiB 上限；网络异常或非终态回执保留待对账。重复操作摘要不同拒绝，同摘要未决只 GET，终态直接回原回执。
- 初次 RED commerce5-red.log；GREEN 14 passed（commerce5-green.log）。全部 HTTP MockTransport，只真实执行本地 SQLite，不调用模型/真实网站。

- Final: fixed 三项 Important（一次修复，无二次审查）：目标重绑、三次 approval_lookup 异常、必要 settings 依赖变化。5 项集成 RED（commerce5-review-red.log）→GREEN；加 restart/旧无来源账本/direct reconcile 边界，共五模块 85 passed（commerce5-focused-final.log）。
- Ruling: target_bindings 将连接+环境永久绑定项目及规范化 URL 的 SHA256；已有未绑定操作不猜测来源，换站点必须新 connection_id — 阻断跨站点旧回执混用 — 代价是旧原型账本需人工核对来源后迁移，不自动放行；凭据轮换不改变 URL 绑定。
- Ruling: 验证所有批准依赖 preconditions，保守拒绝前序操作已改变的依赖 — 不能把原批准指纹默默更新为新值 — 代价是多步 P7 编排须明确基于回执验证后续预期状态/重新审阅，不宣称本模块已经支持完整批量发布。
- 第五批首次全量在 93% 运行器会话丢失，没有结果；保留截断日志，不算通过。追加逐项/退出码完整重跑：1303 passed / 3 skipped / 1 failed / 2 warnings，194.23 秒，失败仍原 Windows launcher Access denied。commerce5-full-rerun.log/exit，退出码 1。相关 85 passed，新增 21 项。P3 仍部分实现，没有实际模型/店铺调用或 Git 推送。

## 第六批：内部持久审批仓储

- Ruling: 复用 schema 11 的 commerce_changesets/commerce_approvals，verification 列保存 report 与项目/计划/目标 binding，approval.data 保存 grant 和批准后计划 binding — 与现有 _invalidate 的列级撤销兼容 — 代价是内部 envelope 尚非公开 API 格式，后续迁移/公开接口必须按类型读取。
- Ruling: stage_review 仅可信 verifier 调用，校验报告形状/证据引用、内容/代码/快照和 operation preconditions；这些不证明真实隔离或浏览器验证运行过，不给 Agent 或 API 开入口 — P6 尚缺真实环境 — 代价是本批只能离线验证，不能用 fixture 报告对真实站点授权。
- Ruling: approve 以明确已审阅 digest 和旧计划版本批准，事务内保存固定 30min grant、更新计划 APPROVED 和事件。重复同次批准读取原 grant，不延长期限；已到期/撤销不能再次点击复活 — 避免旧审查重放 — 代价是过期后的重新审查/恢复入口需后续 P7 实现。
- provider(connection) 与内部 publisher callback 兼容，每次事务读取当前 column status/expiry、项目/计划哈希和版本、当前连接、ChangeSet/report 哈希；不存在/取消/失效拒绝。无公开签发、批准或写端口。
- 首批 13 passed（commerce6-green.log），RED commerce6-red.log。无付费请求/真实店铺写入。
- Final: 一轮审查发现五项 Important，在一次修复阶段处理：重新校验存储报告并固定其摘要、禁止到期列延长批准、撤销/到期更新仍绑定原批准的计划、校验主题包三类来源、拒绝占位来源标识。审查探针 RED 10 failed / 14 passed（commerce6-review-red.log），修复及边界补充后 28 passed（commerce6-focused-final.log）。没有二次审查。
- Ruling: 到期刷新发生于执行 provider、approve 或显式 expire_due，且仅更新仍匹配批准来源的 APPROVED 计划 — 防止覆盖较新的执行/编辑状态 — 代价是后台刷新及 UI 状态展示仍待接入，不能声称目前界面即时刷新。
- Ruling: 包 content_sha256 必须与审查内容来源统一 — 避免错误内容获批 — 代价是 P5/P7 生成链须统一内容摘要算法；当前保守拒绝不一致，不能通过占位来源强行放行。
- P7 仍部分实现：没有真实 verifier、PHP 原子写插件、批准/发布 API、失效后恢复入口或真实购买验收；本批数据库一致性校验不构成物理数据库防篡改认证。
- 第六批最终根目录全量 1331 passed / 3 skipped / 1 failed / 2 warnings，178.70 秒，pytest 退出码 1。唯一失败为原 Windows launcher taskkill Access denied；保留失败，不声称全量通过。证据 commerce6-full-final.log/exit。Ruff、OpenAPI、差异空白检查通过，未调用模型或真实店铺，也未提交推送。

## 第七批：确定性主题审查候选（P7 部分实现）

- Ruling: create_changeset 保留计划接口，用冻结 blueprint/products/code_revision 重建 ZIP，与传入 SitePackage 全字段比较，不接受未验证任意包 — 现有接口仅传元数据，没有 ZIP 参数 — 代价是首版只能审查确定性原生主题，未来 Coding Agent 自定义修改须经可信 P6 产物存储与验证链接入。
- Ruling: 只支持自有 muse-storefront 主题包，不生成页面、导航或商品操作 — 当前快照缺页面所有权、导航和平台 SKU 不存在证明 — 代价是完整建站/新品闭环仍待 P3/P6/P7/P8 远端协议实现，不把本批视为完成这些阶段。
- Ruling: 使用重新规范化的快照核对完整指纹映射，并绑定 theme 和 settings 依赖；候选及 operation ID 包含计划版本，重复同版幂等，新审查不会复用旧回执 — 避免旧内容或手工主题修改进入新候选 — 代价是无关设置变化也保守阻止，后续可细化依赖。
- RED commerce7-red.log（模块缺失）→GREEN commerce7-green.log，22 passed；真实包重建和 SQLite 审批仓储集成，无 HTTP/模型请求。没有开放 API/CLI/Agent 发布端点。
- Final: 一轮审查发现序列化/UTF-8 摘要异常没有业务错误边界，Important 在一次修复阶段处理。三项探针 RED（commerce7-review-red.log）→GREEN，完整输入类型与规范化校验后 26 项模块测试、与审批合跑 54 passed（commerce7-focused-final.log）；一项 plan 字符探针原已受保护，未误称其 RED。没有 Critical/Minor，没有二次审查。
- Final: Ruling: 审查暂不判定实际来源提交、浏览器/购买验证、远端原子安装/模板覆盖和回执及公开流程 — 这些依赖仍明确未实现，不能用离线形状校验放行 — 代价是本批依旧不能实际建站或上架新品，需完成 P3/P6/P7/P8 后真实验收。
- 第七批最终根目录全量：1357 passed / 3 skipped / 1 failed / 2 warnings，162.64 秒。唯一失败仍为原 Windows launcher taskkill Access denied，pytest 退出码 1；不标全量通过。保留审查前 1353 passed 日志为 before-fix，最终证据 commerce7-full-final.log/exit。相关 54 passed，Ruff/OpenAPI/diff 检查均退出 0。

## 第八批：离线项目导出与工作台下载（P10 部分实现）

- Ruling: 在真实发布环境缺失时先实现 P10 独立只读导出子项 — 便于保存当前开发成果，不依赖未实现远端写入 — 代价是 P10、AC08 完整跨环境恢复和业务闭环仍未完成。
- Ruling: 导出格式 1 的 ZIP 使用固定文件名与序号主题路径；仅白名单读取商家项目、计划和商品导入记录，不读取秘密、客户、订单、快照、任务、审批许可 — 避免数据库/工作区全量外发 — 代价是用户输入的私人文本原样保留，分享前需自己检查，导出不是秘密扫描器。
- Ruling: 原生主题必须可从冻结计划确定性重建并匹配内容摘要；无代码版本的计划只导出结构，不假装已有主题包 — 保留可靠来源 — 代价是自定义代码产物仍待可信 P6 产物存储接入。
- Ruling: required_versions 当前只声明导出格式，不猜测 WordPress/Woo 实际兼容版本；README 明确重新配置及验证 — 真实参考环境尚未验证 — 代价是此 ZIP 不是一键迁移/部署包，不能据此放行实际发布。
- RED 模块缺失（commerce8-export-red.log）→GREEN 8 passed；工作台下载按钮缺失 RED（commerce8-browser-red.log）后新增下载卡片。前端生产构建通过，未调用模型或真实店铺。
- Final: 独立审查无 Critical/Important；不派二次审查，不做修复阶段。附加探针确认版本并发一致性、Unicode/非法 JSON/容量边界。商品身份篡改和历史上限补测后导出模块 10 passed；电脑/手机下载两项通过。
- Final: minor (deferred): 容量超限统一 INPUT_INVALID，具体容量原因提示待细化；保留 100 记录与 16 MiB 边界，checkpoint 已写明。
- Final: Ruling: 第二环境恢复、来源提交真实性、自定义主题/媒体迁移和实际平台/购买/部署仍待后续；商家私人输入不自动识别，摘要不证明数据库抗整体篡改 — 保持本批明确离线资料交接语义 — 代价是不能据此宣称 AC08 或完整业务验收，也不能假设下载异常分支已经专项验证。
- 第八批最终根目录全量：1367 passed / 3 skipped / 1 failed / 2 warnings，542.31 秒，pytest 退出码 1。唯一失败原 Windows launcher taskkill Access denied；保留失败。证据 commerce8-full-final.log/exit；生产构建、Ruff、OpenAPI 与差异检查均退出 0。未提交推送或同步桌面项目。

## 第九批：真实本机 WordPress 功能验证与受限写插件（平台验收仍未完成）

- Ruling: 用户要求继续至完整商家版；在缺 Linux/Docker 环境时，在开发目录部署官方便携 PHP 8.4.26、MariaDB 11.4.12、WordPress 7.1.2、WooCommerce 11.1.2，数据库和 HTTP 仅监听 127.0.0.1，不注册 Windows 服务 — 继续验证实际 CMS 功能而非反复仅做离线基础模块 — 代价是 Windows 功能通过不证明 Linux 隔离，versions.lock.verified 仍为 false，公开发布入口继续关闭。
- 官方 PHP/MariaDB ZIP SHA-256、WP 3782 个文件和 Woo 5862 个文件官方清单逐项校验；下载来源摘要在 work/tools/*-download.json。测试用随机秘密仅保存在工作目录，不读取或发送用户模型密钥；付费模型调用为 0，真实商家店铺操作为 0。
- 初次 pytest TEMP WinError 5 是测试运行目录权限问题；显式工作目录 basetemp 后得到真实 RED，不删除或跳过失败。PHP canonical JSON 保留对象/数组、中文和 emoji，HMAC 校验固定目标/项目/连接/环境、30 分钟期限、操作全文及全部资源条件；21 项跨语言 RED→GREEN，commerce9-php-red.log / commerce9-php-green.log。
- 新增固定 POST operations / GET receipts 与独立 InnoDB 回执。应用密码认证和指定服务用户必要；先持久化 NEEDS_RECONCILIATION，再在 CMS 行锁和事务中校验所有权/指纹。确定前置冲突持久 FAILED；不确定异常保持待对账。相同操作摘要回原回执，不同摘要拒绝。
- Ruling: WordPress SQL 变更及成功回执同事务，但 WP hooks 可产生事务外效果，进程崩溃/不确定异常不假报失败或重新发送 — 不宣称跨插件、文件系统和远端 webhook 原子性 — 代价是异常回执可能需人工核对，不能自动解除未知资源锁。
- 真实站点认证、快照、页面写入、重复提交/回执回读、手工编辑和非自有页面拒绝 5 passed（commerce9-writes-green.log）。商品草稿→读回精确价格/库存→发布→重复 SKU 拒绝的真实测试 1 passed（commerce9-product-green.log）。这些使用显式测试签名器，不证明公开业务批准/完整建站已接通。
- Ruling: 新增只读 GET resources?sku= 固定查询，用店铺实际精确 SKU 状态证明不存在，不从有上限的商品快照推断 — P3/P8 需安全支持创建草稿 — 代价是新 SKU 与后续生成 ID/多步批准编排仍需完善；原发布器仍禁止默默替换旧依赖指纹。
- SKU 查询及内部 publisher 前置校验 9 项 RED→GREEN；加原发布器回归共 28 passed（commerce9-publisher-green.log）。七类契约目前插件只宣布实际已实现的五类，主题安装和导航尚未接通。P6 Coding Bridge、真实隔离 verifier、P7 公共审查/发布、多步恢复与 P9 完整审查 UI 仍待开发，不标计划完成。
- P3 继续完成主题 ZIP 校验与安装、导航 ID 引用。ZIP 9 项独立 PHP 测试通过；真实主题安装/文件回读/重复回执 1 passed，导航创建/重复回执 1 passed。安装保留私有固定路径 journal 和旧目录，不将文件系统 swap 当 SQL 原子事务；异常维持待对账。
- Ruling: 主题指纹纳入固定 15 文件 SHA-256，设置纳入首页/商店/购物车/结账 ID，自有页面/商品纳入所有权；既有缺字段快照保持 exclude_unset 兼容 — 实测 CSS 手动修改原指纹不变，需阻止覆盖新修改 — 代价是这些依赖变化会使旧审查失效，不能对既有审批重新计算新指纹。
- Ruling: 自有导航显式绑定 theme 和所有引用页面的批准指纹；仅覆盖本产品拥有的 header DB 模板，拒绝非自有 header。主题安装保留已有自有导航 header，不删除商家模板覆盖 — 禁止导航操作成为隐式覆盖他人模板的入口 — 代价是主题包文件和实际 DB 模板仍需浏览器验证，文件安装成功不等于页面验收通过。
- 真实 abrupt-exit 故障证明 SQL 效果回滚但持久回执仍待对账；重复请求不执行，新操作被资源锁拒绝。操作 ID 同名不同摘要拒绝。故障模块仅位于 tests/fixtures 和临时测试站 mu-plugins，不打包产品插件。2 passed（commerce9-recovery-probes.log）。
- Ruling: 原七类操作没有创建页面的合同，不能在 install_theme_package 内偷偷创建页面。为完成原已批准的建站流程，增加第八类 create_owned_page（严格 slug/纯文本/自有模板、slug 不存在证明、显式资源指纹），同步模型/插件/读证明/生成类型 — 这是初始化必需的独立可审查操作 — 代价是协议允许列表变更，所有调用端与多步编排须升级；仍不自动接管 Woo/商家既有页面。

## 第十、十一批：真实平台补测、代码捕获及本地商品图片

- Ruling: 创建独立最小权限服务用户，应用密码写操作仍只能通过签名 Connector 固定操作；原生 Woo/WP 写权限拒绝 — 管理员凭据不应成为常驻运行身份 — 代价是首次安装仍由临时站管理员完成，不能将这一步称为正式 Linux 服务部署。
- 实站原生购物车/结账模板由实际空白 DOM 故障驱动修正。新增 COD 测试订单、设置引用页面依赖、页面/SKU 创建证明的 entity_fingerprint，手工内容修改使旧证明失效。旧无实体版本证明不自动升级或放行；公开多步批准协议尚待设计。
- 最新临时 Windows WP 功能验证：16 passed，253.03 秒，work/commerce11-wp-green.log，退出 0。覆盖签名权限、重复请求、所有权、主题、导航、版本冲突、崩溃待对账、商品和测试购买；不代表完整商家 UI/模型流程或 Linux 隔离通过。
- Ruling: 可信应用捕获严格固定 15 文件 TAR，重算完整 Git 对象和提交，不相信模型给的 revision — 实际修改代码必须有可检查的来源 — 代价是需要独立私有 source store，并保持静态校验与 OS/browser 验证分开。
- DockerCodingSession 已实现宿主控制参数、固定镜像证明和实际 UID/网络/文件系统探针，但本机没有可连接 Linux daemon；未执行真实隔离验收，不修改 versions.lock.verified=false。
- Ruling: 本地图片解码、清除 EXIF/尾随数据后重编码，按项目内容寻址；每项目最多 100 张/100 MiB；同名异图或同图异名拒绝 — 防止 CSV 图片绑定歧义和无界存储 — 代价是存在容量边界，远端媒体创建/绑定仍待固定签名操作实现。
- 图片上传/导入/导出 19 项通过；桌面/390px 图片选择、刷新、导出及原入口 4 项浏览器检查通过。带图导出为格式 2，无图维持格式 1，总包上限 16 MiB；导出不是自动恢复或部署。
- 原启动器 taskkill 权限失败改为 Win32 按创建时间和当前父子关系核对、持有进程句柄后终止所属树；补真实孙进程和伪旧子 PID 防误杀测试。不会结束任意同名 Python 进程。
- 第十一批全量原始结果保留：1445 passed / 19 skipped / 3 failed / 3 warnings，5891.33 秒，work/commerce11-full.log，退出 1。失败为旧 publisher mock 缺实体版本、新浏览器超时和启动器 90 秒 fixture 提前自然结束。分别更新真实合同 fixture、保留原浏览器断言重跑、fixture 等待显式清理；相关 28 项通过，38.75 秒。尚不能将整套全量记为通过。
- 所有新增商业测试模型费用 0；操作仅限自建临时测试站；未推送、未同步 Desktop。阶段 1–8 封存证据不重写。

## 第十二批（进行中）：接通网站开发角色的真实静态代码编辑

- Ruling: 首先接通固定静态文件读/写/差异/封存工具，草稿与调用回执在同一 SQLite 事务；不依赖宿主执行代码 — 可以推进真实代码工作而不拿 Windows 当 Linux 隔离 — 代价是 Shell 和可信预览验收仍须后续受控环境，不能因此打开发布。
- 固定 PHP 不可修改，全部文件每次写入重新校验；expected_hash 阻止旧版本覆盖，封存后禁止继续编辑；项目来源、角色、租约、取消和业务阶段均核对。旧 checkpoint 工具上限不自动扩权。
- Ruling: 原 Coding 的 verify_command 完成门不适用于纯 SQLite 静态草稿；新增真实源代码包封存检查，明确 site_verified=false，并保留一般代码/命令的原验证门 — 否则受限角色会被迫要求禁止的宿主命令 — 代价是静态准备成功不能当作功能/隔离验收。
- 缺模块、缺工具与未封存运行器 RED 保留在 work/commerce12-code-red.log、commerce12-runtime-red2.log。修改、差异、真实 Git revision、精确 ZIP 字节、重启、越界/PHP/外部内容拒绝、并发、取消、角色权限和运行器封存门，与原团队回归合跑 28 passed，6.33 秒（commerce12-runtime-green2.log）。
- 待开发：可信 staging/browser/facts verifier；符号资源多步批准/发布/恢复；远端商品图片传送；完整商家审查 UI；第二环境恢复；六个真实模型案例及最终平台验收。营销/分析角色遵循原规格后续阶段，不冒充首版已实现。

- 第十二批补充：准确代码包导出替代初始主题再生成（真实 CSS 丢失 RED→GREEN）；新增鉴权/归属/版本保护的只读代码审查 API 和工作台差异卡片。代码/API/导出 20 项通过；桌面/390px 差异与原团队页面 4 passed / 2 第三方弃用 warnings，98.99 秒。运行器完整 edit→seal→submit→final 脚本模型案例 1 passed，调用的是 ScriptedProvider，不是收费模型。

## 第十三批：发布前依赖和回归修复

- Ruling: 商品指纹增加原价/促销价、库存管理/可售状态/缺货订购、分类 ID、主图 ID 和有序图库 ID — 实际同售价的原价改变或分类/图片替换不能逃过旧批准 — 代价是新读取会使原指纹失效；图片 ID 不证明底层媒体文件字节没被修改，媒体字节核验仍在 R4。
- Docker 检查追加拒绝 host PID/IPC/UTS/user namespace；原固定边界与新增 12 项 RED→GREEN，44 passed。该合同测试仍不是 Linux 内核隔离证据。
- 真实 WP 输出空 image_id 是字符串，严格 schema 首次失败；安全诊断只输出字段/类型，插件显式整数化 image_id 后重跑：17 passed，251.19 秒，work/commerce13-wp-green.log，退出 0。实测有效售价不变但原价、库存模式、分类改变，使旧签名发布返回 FAILED。
- 本批根目录全量：1473 passed / 19 skipped / 3 warnings，464.13 秒，work/commerce13-full.log / .exit，退出 0。该次 collection 不包含后续第十四/十五批新增测试；不能当后续修改的最终全量结果。
- 类型字节检查、生产构建、Ruff、git diff --check 通过；Git 自动 CRLF 提示不是 whitespace 错误。无推送或用户 Desktop 同步。

## 第十四批：成功创建回执绑定实体 ID

- Ruling: CreatedResource 仅由完全匹配的创建操作摘要、terminal SUCCEEDED 回执、当前严格资源证明及同项目自有实体指纹联合推导 — 不用模型提供的 ID，也不因 GET 返回现有资源就补签旧批准 — 代价是手工修改后的新实体必须重新审查，未知/失败及旧无 entity_fingerprint 证明均拒绝。
- 模块 src/muse/commerce/release_resources.py 不批准、签发、联网或写入；之后 broker 仍须验证不可变意图成员、当前商家批准、目标、取消/过期与持久执行进度。
- 16 项页面/商品绑定、失败/未知、跨作用域、错误摘要、旧证明、布尔 ID、手工修改和所有权测试通过；与原资源/回执合跑 31 项通过。新增 WP 实测创建→绑定→编辑后拒绝 1 passed，6.03 秒，commerce14-wp-binding.log，退出 0。

## 第十五批（进行中）：不可变发布意图

- Ruling: 多步业务意图与 v1 ChangeSet 分开，先生成新品 create→publish 的符号 DAG，摘要绑定原项目/计划/目标/代码/内容/快照与真实 SKU 不存在证明 — 不给旧 v1 批准更新指纹，也不将依赖记录当执行许可 — 代价是 v2 根批准、逐步投影、PHP 互操作及网站 DAG 仍需开发，公开发布继续关闭。
- ProductReleaseIntent 固定最多 20 个创建/发布配对；精确来源/依赖顺序，创建事实深拷贝，未上传远端的图片引用拒绝。新增改序、源事实/目标变更、缺证明/已有 SKU、整数伪 false、币种及非原生主题边界 RED→GREEN。
- 新品意图与资源绑定合跑 31 passed，0.88 秒；Ruff 全 src/muse、Commerce tests 及 launcher tests 通过。这里只是冻结声明，plan_source_hash 和 code_revision 的形状不是 P6 真实可信代码/浏览器验证；批准仓储必须独立读取当前持久来源和真实证明。
- 后续执行细化计划：docs/superpowers/plans/2026-10-01-commerce-release-continuation.md，承接原 P6–P10。用户持续开发授权用于内部任务切分，不重复等待“是否继续”。

- 最新根目录全量：1504 passed / 20 skipped / 3 warnings，414.32 秒，work/commerce15-full.log / .exit=0。跳过项包含未显式启用的实站测试；不冒充 Linux 或真实模型验收。
- 在独立构建虚拟环境安装 hatchling 1.32.4、构建本地候选 wheel，再在全新安装虚拟环境按现有依赖版本约束安装。Python -I 隔离导入、15 个主题文件、前端字节匹配和 pip check 通过，work/commerce15-wheel-smoke.json。模型调用 0，正式部署 verified=false。后续代码修改后须重建候选 wheel。

## 第十六批：真实店铺运输和付款准备状态

- Ruling: 运输/付款采用 WordPress 管理员 nonce 表单显式确认，并与当前启用的 Woo 方式联合判断；服务角色不能确认，Agent 没有确认工具 — 实际 snapshot 缺少两个字段，导致已配置店铺仍停在 NEEDS_INPUT — 代价是需要商家一次配置确认；此事实不作为购买验证或发布批准。
- 管理员表单仅写两个固定 yes/no 选项；拒绝无权限和非法 nonce，不读取或输出支付密钥。快照只返回两个布尔准备状态，禁用全部对应方式自动失效。
- PHP 独立边界 8 项 RED→GREEN；显式临时 WP 实测商家确认→状态与设置指纹变化→停用付款失效、服务账号无权确认，1 passed，16.94 秒，commerce16-wp-setup.log。新增公开发布权限仍未开放。
- 第十六批全量：1512 passed / 21 skipped / 3 warnings，441.40 秒，commerce16-full.log / .exit=0；此轮 collection 不含之后的第十七批。

## 第十七批（进行中）：逐步商品执行与独立 v2 许可

- Ruling: v2 逐步资源投影只接受完整、有序且完全匹配的 terminal 成功历史；创建 ID 来自回执及实体证明，发布变化只允许 status=draft→publish，其它资源版本保持原始或已验证前序版本 — 不把 GET 到的新指纹补签进旧 v1 批准 — 代价是必须持久保存可信历史，未知结果不能向下推进。
- Ruling: v2 使用 muse-wp-product-step-v2，固定 root 摘要/步骤号/步骤键/operation ID，批准时间与失效时间不随重签变化；只准商品创建/发布。未创建 SKU 的明文查询身份同样受签名，PHP 事务内逐个核验不存在证明 — 批量创建需要检查其他尚未触及 SKU，而 SHA 不能反查原 SKU — 代价是 v2 合同独立升级，v1 验证器仍拒绝 v2。
- Ruling: v2 plan_source_hash 排除 state/revision/error_code，其它源码、事实、团队成果均冻结；受控状态/版本必须由后续持久 broker 另行 CAS 核对 — REVIEW_REQUIRED→APPROVED 不应改变内容来源 — 代价是不能仅凭 source_hash 放行外部状态修改，v1 的全 plan 绑定保持原样。
- 逐步投影、根许可撤销/过期/目标/历史、Python/PHP audience/字段/步骤/SKU 映射合同及旧批准回归合跑 88 passed，5.50 秒，commerce17-source-green.log。单独旧协议与 PHP 组 73 passed / 1 duplicate-ZIP 故障测试 warning，7.71 秒。
- 真实两商品四步签名发布首次因其它 SKU 条件无法查询返回 FAILED；将已验签的 SKU 查询映射传入事务指纹核验后，2 件商品创建→发布、真实 ID 回执推导、逐步重复请求与精确价格/库存回读 1 passed，47.69 秒，commerce17-wp-green.log。该测试由内部测试签名器和临时站完成，不是公开商家批准或 Linux 浏览器报告。
- 下一步仍须持久 v2 业务批准/进度、当前来源与取消 CAS、可信 verifier、网站 DAG、远端媒体和完整公开 UI。现有新模块不会自行开放公开签名/发布接口。
- 第十七批显式临时 WP 全套：19 passed，350.70 秒，commerce17-wp-full.log / .exit=0；包含两商品四步 v2 与原 v1 权限、主题/导航、未知结果及购买故障回归。这不是 Linux 内核/公开工作台验收。

## 第十八批：私有 v2 根批准持久化

- Ruling: 复用事务数据库的私有 artifact 命名空间保存 v2 review 与独立不可变 grant；stage_review 只读取 trusted_product_verification 生产者记录，同时独立校验实际封存代码/包/来源/目标 — 不接受模型报告或公开 artifact 上传替代验证 — 代价是可信 verifier 生产者尚须 R3 实现，不能因此开放商家批准 API。
- 每次加载核对当前 project 全文、plan 内容来源、受控 phase/revision、根任务取消、报告及真实代码；APPROVED/PUBLISHING 变化由仓储同事务维护版本。并发重复批准只生成一个 grant，不续期；独立 grant 防止修改 review 记录延长时限。
- 到期或撤销在原批准阶段恢复 REVIEW_REQUIRED；已进入 PUBLISHING 保留 NEEDS_RECONCILIATION，不假报失败。外部修改/取消/新版本不被旧批准覆盖。v2 与原 v1 批准回归 51 passed，9.04 秒，commerce18-expiry-green.log。

## 第十九批：逐步日志与晚到回执

- Ruling: 两个持久栅栏共同保护发送；attempt 在主库保存原始预检/操作，OperationLedger.begin 在任何 POST 前提交未知状态。重启及本地 begin→journal mark 崩溃窗口只同步为待对账，不授权重发 — 即使插件未收到请求也不能用 404 清除未知状态 — 代价是需要显式只读对账及人工处理无法证明的未送达。
- 成功 ID 只来自已确认 terminal ledger 回执和原意图/当前实体证明；验证所有前序效果，不接受价格变化或插入步骤。已知成功但读回发生冲突仍保存 SUCCEEDED 回执、标 effect_verified=false 并阻止继续，不能伪装失败后重发。
- 撤销/过期后仍允许记录原在途的已确认结果，但不能签发下一步。已知失败停止剩余动作，全部精准读回成功后消耗根 grant；不覆盖新版本或取消后的计划。进度、批准和原 v1 合跑 94 passed，19.65 秒，commerce19-terminal-green.log。

## 第二十批：接通默认关闭的 v2 发布器

- Ruling: 发布器私有入口在每次发送前独立读取当前批准/代码/报告、平台锁、真实 snapshot 与全部 SKU 证明，并重算 v2 projection；secret 和具体 WordPress 凭据不进入角色工具 — 所有公开批准/发布继续等待 R3 真实生产者和 R4 UI — 代价是当前仅能跑内部契约与临时站固定协议测试，不能称为商家完整发布入口。
- 默认 execution_enabled=false；未验证镜像/平台锁或当前来源变化在任何 HTTP 之前拒绝。确认后仍再查取消/撤销，HTTP 非匹配 terminal、超时、取消保留未知结果；恢复仅 GET receipts/snapshot/resources。
- 新旧批准/日志/投影/签名/PHP/发布器与回执合跑 146 passed，28.62 秒，commerce20-regression3.log / .exit=0。覆盖响应丢失后批准到期仍只读对账、崩溃窗口、发送前撤销、目标重绑定、重复完成；这些使用受控内存 HTTP 及显式 verifier unit fixture，不是实际 Linux 验证。模型费用仍 0。


## 第二十一批：商品事实复核与合法批量边界

- Ruling: terminal 成功回执的实体指纹只证明版本关联，不能替代原批准商品事实；创建后另核 SKU/标题/价格/原价/库存/描述/简单类型/库存管理/非促销/禁止缺货订购 — 插件 hook 可能返回自洽但已改写的实体 — 代价是已知写入成功但事实偏差保留结果并停止，不自动修正或重发。
- 9 项 hook 改写事实 RED，修复后与根批准/日志/发布器/签名/PHP 合跑 97 passed，24.92 秒（commerce21-facts-green.log）。
- Ruling: v2 使用 UTF-8 编码并独立限定许可 32768 字节；v1 仍 8192 — 20 件合法长 Unicode SKU 的未创建身份映射超过原上限 — 代价是 v2 HTTP 许可上界增加，操作体及读取上界不放宽。Python/PHP 极限批量 RED→GREEN，旧协议合跑 60 passed / 1 duplicate-ZIP 故障测试 warning，6.47 秒。
- Docker 私有配置打开文件后先核普通文件/所有者/单链接再截断；拒绝链接目录、文件和错误所有者。真实 NTFS hardlink 受害文件保持不变；代码/环境合同组 40 passed，1.75 秒。不是实际 Linux 隔离证据。
- Ruling: R5 离线恢复读取器可以先于真实第二环境部署实现 — 数据/代码迁移独立于 R3 Linux 验证，并可先补齐商家移交入口 — 代价是离线恢复完成不得勾选“第二站部署购买验收”；新连接/快照/代码验证及批准必须重新执行。


## 第二十二批：商家资料恢复与继续开发

- Ruling: 离线恢复创建新的 project 和版本，整包先校验后同事务保存；旧连接、快照、任务、计划批准/许可不导入 — 迁移不能继承旧站的身份或发布结论 — 代价是新连接、SKU 冲突、隔离/买家流程和商家批准必须重新执行。
- ZIP 不提取到文件系统；限定文件名/数量/累计展开体积/格式，拒绝重复路径、链接/加密、额外凭据或许可文件、重复 JSON 字段、摘要/尺寸不符。解析商品、净化图片、固定 15 文件主题；新图片 ID 与商品引用按新项目重新绑定。
- 恢复 API 接受限 16 MiB 的流式 application/zip，使用本地鉴权；相同 workspace/request/archive 去重，变更 archive 冲突，不保存部分项目。主题只读下载和索引核对项目归属与实际字节摘要。
- Ruling: 新计划可以显式选择同项目恢复主题作为代码起点；将 source ID/digest 冻结在原 blueprint 的 required_settings，保持普通旧计划请求摘要不变 — 保存 ZIP 而开发时重新生成初始文件会丢失修改 — 代价是来源变化拒绝继续封存，恢复代码仍不是可信预览或旧发布许可。
- 真实 ThemeCodeBridge 读取准确恢复 CSS、重新封存新 Git revision，并保留原角色/租约/固定 PHP 边界；重新计算 source digest，不能导入旧报告。恢复与代码/团队/API 48 passed，12.28 秒；索引/选择的公开鉴权与跨项目合同 3 passed，2.54 秒。
- Ruling: 含恢复主题来源的再次导出使用格式 3；原格式 1/2 保持输出 — 未创建新计划前二次导出曾漏掉恢复代码 — 代价是消费端需支持新格式。二次恢复精准保留主题包且无活动计划/连接，恢复/导出/代码合跑 37 passed，8.99 秒。
- 初次恢复 UI 在桌面/390px 的实际导出→上传→新项目商品/图片→原 Coding 任务回归 2 passed，45.34 秒。主题来源 UI 扩展另行记录其最终结果，不能用该轮替代。
- 这一步没有部署第二个 WordPress 站，不勾选 R5 第二环境购买验收。真实模型请求/费用 0，未推送或同步 Desktop。


- 第二十二批补充：恢复主题来源的选择与实际 ZIP 下载，桌面/390px 导出→恢复→下载准确字节→原 Coding 任务 2 passed / 2 第三方弃用 warnings，29.73 秒（commerce22-source-browser-green2.log）；前端生产构建、类型字节 check、Ruff 通过。来源选择增加明确的无障碍名称，修复 select 标签包含 option 文本造成的匹配失败。

## 第二十三批：独立 staging 事实核对

- Ruling: 从真实代码/包绑定与新站实际快照独立核对六个实体页面、原生商品详情来源、四个 storefront 选项、运输/付款就绪、商品价格/库存/描述/归属/图片关系、十五文件及有效模板 — 成功回执与代码 ZIP 本身不能证明最终站点使用了同样内容 — 代价是事实结果明确 site_verified=false，不提供 OS、浏览器或购买证明，也不生成批准。
- Ruling: 只接受已观测的 WordPress 主题属性注入和 Woo 11.1.2 固定账户/mini-cart hook，导航只允许原 blueprint 顺序/标签/自有页面/正确 permalink 与对应 header ref — 直接比较磁盘与有效模板字符串会误拒绝真实 CMS 正常转换 — 代价是其它插件转换或未支持的 permalink 明确失败，不宽泛接受任意新模板或指纹。
- 实站另发现 page 默认值被固定插件存为 default；对应 home/shop 期望修正为实际合同，商品详情仍是原生 single-product，不另建实体页面。33 项来源/内容/模板/导航/跨目标攻击检查通过，16.63 秒；实际签名安装、六页创建发布、四个店铺选项、商品和自有导航后独立核对 1 passed，80.89 秒（commerce23-wp-green2.log）。该测试是 Windows 临时站功能验证，正式 verified 锁仍 false。
- 后续仍须 R3 真实隔离 staging 生命周期、可信报告生产者和完整买家验证；R2 网站多步意图、R4 远端媒体和审查发布 UI 没有因此变成完成。

## 第二十四批：实际浏览器截图、页面和链接核对

- Ruling: 浏览器只接受后端已配置 staging 连接，先复核准确封存代码与店铺事实；匿名购物车不传 WordPress 凭据，资源和重定向限定原连接 — 预览不能成为任意浏览器或凭据外发工具 — 代价是外部字体、脚本、跨站链接和未知动作链接不自动放行。
- Ruling: 对普通站内导航实际执行受限 GET，并在响应头后关闭流；跳转逐次核对原站点，未知参数、管理和 API 链接不执行 — 仅比较 URL 同源会把 404 链接判为通过 — 代价是非首版导航形式报告失败，由后续明确合同支持。
- 失效链接 RED 1 failed；修复后桌面/390px、外部资源阻断、404、横向溢出、live 目标拒绝的实际 Chromium 组 6 passed，83.02 秒（commerce24-links-green.log）。固定 viewport PNG 单张最多 5 MiB、总计 32 MiB，结果始终 site_verified=false。
- 实站发现旧 Woo product-title 在当前模板不输出标题，以及商品目录的 page_id URL 被 CMS 重定向到商品详情。改用动态 core/post-title 和配置后的页面 permalink，未放宽标题检查。
- 数量角标实际撑出页面 1px；初次低优先级 margin 被 WordPress flex 样式覆盖，独立桌面/手机样式探针确认更明确的选择器后修复，未隐藏页面溢出或放宽检查。
- 六页创建发布、四项店铺设置、商品/导航、事实核对后实际浏览器访问七类页面、390/1440 布局与 14 张 PNG 全部通过：1 passed，98.92 秒（commerce24-wp-green3.log）。这些是 Windows 临时店铺功能证据，不包含 Linux 内核隔离或本轮测试订单。

## 第二十五批：建站业务意图声明与回归

- Ruling: 网站发布意图使用独立版本 3，冻结准确 package/source digest、蓝图、商品事实、原始规范化快照和不存在证明；旧 v1/v2 协议不解释它 — 主题/页面/导航不是原商品-only v2 的合法动作 — 代价是还须网站专用 broker/逐步效果投影/签名协议，不能凭新意图声明开放发布。
- 固定依赖顺序：主题、六页创建/发布、四项 storefront 设置、导航、最多二十商品创建/发布。所有新 ID 仍是符号引用；不接受已有页面接管、重复资源、图引用或额外依赖。空商品建站保留十五步，不虚构商品。
- 缺模块 RED 11 failed；新旧意图 28 passed，1.37 秒。主题/独立事实/新旧意图合跑 81 passed，8.96 秒。
- 根目录全量回归 1683 passed / 23 skipped / 4 第三方或故障输入 warnings，227.61 秒（commerce25-full.log / .exit=0）。包括预览、恢复和原 Coding 回归；跳过项不是验收通过。该结果在第二十六批界面接入前取得。
- 模型 API 调用/费用仍 0；没有 Git 提交、推送或 Desktop 同步，正式 Linux versions.lock 仍 verified=false。

## 第二十六批：只读商家预览界面

- Ruling: 保存浏览器诊断为独立私有 artifact，不生成 VerificationReport 或授予发布权限；按当前项目、来源、目标、准确 PNG 哈希与宽高复核 — 商家需要查看已完成的截图，但浏览器检查不足以证明隔离和购买 — 代价是没有真实 verifier 记录时界面明确“尚未生成”，不提供上传截图或自行标记通过的接口。
- 前端按页和设备选择截图，显示中文检查与失败原因，明确完整验收未通过。逐张加载，限制单张 5 MiB/累计 32 MiB；每计划最多保存十份诊断。未挂载/重复点击不会继续更新界面。
- 仓储及本地鉴权/跨项目/旧版本/只读 API 的 RED→GREEN 11 passed，7.72 秒。实际桌面/手机工作台通过 HTTP 读取诊断和 PNG、显示准确尺寸/原代码差异且没有发布按钮，合跑 13 passed / 2 第三方 warnings，50.18 秒（commerce26-ui-green.log）。界面测试使用显式诊断 fixture，不替代第二十四批实际 CMS 截图。
- 生产前端构建、API 类型生成/check、Commerce Ruff 已通过。完整公开批准/发布、网站 broker、远端媒体和 Linux verifier 仍未完成。

## 第二十七批：平板检查与预览记录绑定

- Ruling: 按 AC02/P6 补齐 768px，与 390/1440 各检查全部路由；预览元数据最多 78 帧，累计字节上限不提高 — 两档浏览器功能通过不等于原规格三档验收 — 代价是页面复杂或累计截图过大时仍失败，不裁剪证据伪装完整。
- 三档要求 RED 缺 layout_tablet；修复后真实 Chromium 故障/截图与仓储 API 合跑 17 passed，149.11 秒（commerce27-tablet-green.log）。正式隔离和买家订单仍是独立门槛。
- 重新计算预览 JSON 的存储摘要不能篡改同一 capture ID 的结果；新增故障 RED 后校验原 capture ID 绑定的完整 report/binding。12 项仓储/API/源变更/篡改测试通过，6.98 秒；前端生产构建和 Ruff 通过。实站三档扩展结果随后记录。
- 第二十七批实站扩展：独立源码/商品/页面核对后，7 类路由在 390/768/1440 全部通过，21 张准确 viewport PNG；1 passed，139.91 秒（commerce27-wp-tablet.log / .exit=0）。版本锁未改为 verified，仍不是 Linux 隔离、正式发布或本轮订单验收。

## 第二十八批：建站携带明确商品批次

- Ruling: 建站与上新都可冻结明确选择的已校验商品批次，空批次建站仍有效；请求幂等摘要包含批次选择 — 原建站入口忽略 import_id 会丢失商家选好的商品 — 代价是变更批次必须新请求，不能覆写旧计划。
- RED 建站 products 为空；修复后工作流/API/代码桥/网站意图 48 passed，6.01 秒。实际桌面和手机商家界面导入五件商品并选择建站批次通过；合跑 3 passed、1 次初始浏览器导航 ERR_ABORTED，失败发生在应用加载之前，原日志保留。相同手机用例独立重跑 1 passed，19.34 秒（commerce28-ui-repeat.log）。不把该次瞬态失败删掉或计为首跑通过。
- 前端生产构建、生成类型 check、Ruff 通过；所有模型请求/费用仍 0。

## 第二十九批：导航保留准确开发页头

- Ruling: 导航只替换已有页头中唯一导航块的 ref/内联链接，保留其它文字、布局和属性；缺导航或多导航在写数据库前拒绝 — 旧固定页头会静默丢失开发代码 — 代价是已有商家数据库覆盖必须明确合并，不能借导航或安装自动清除覆盖。
- Ruling: staging 页头按封存来源推导，规范化仅限 block JSON 属性顺序和标签间格式空白；Woo 固定 hook 单独核对 — 比较硬编码默认页头会把丢失内容判为成功 — 代价是其它插件转换依然明确失败。
- 自定义文字丢失 RED 1 failed；修复后来源/导航/模板篡改 34 passed，13.66 秒。真实 WordPress 解析/序列化保留自定义文字、布局、className、overlayMenu，并拒绝缺少/多个导航，1 passed，7.12 秒（commerce29-wp-header-green.log）；PHP lint 与 Ruff 通过。完整实站三档浏览器重验结果另记。

- 第二十九批实站重验：签名安装/六页/设置/商品/导航、准确来源核对和七类页面三档截图 1 passed，147.01 秒（commerce29-wp-navigation.log）。该证据仍是 Windows 临时站功能结果。

## 第三十批：网站逐步资源投影

- Ruling: 只有原准确代码与完整匹配成功回执能推导后续页面/商品 ID；每一步完整比较店铺快照的允许效果，不能用任意新快照重签资源版本 — 网站安装和导航会间接改变主题 — 代价是未定义的插件副作用、商家同时修改或 resolved theme 字段变化明确 STALE。
- Ruling: 主题 global styles 只物化来源声明的配色和 theme palette，保留平台默认/商家 palette 的其余项；导航只改变准确来源 header 与自有菜单 — 磁盘哈希不能证明有效主题正在使用新配色 — 代价是其它 theme.json 动态合并需新增明确规则，不宽泛承认 CMS 任意输出。
- 缺模块 RED 14 failed；额外三项准确效果 RED 后修复。网站意图/投影、原商品投影、事实核对 92 passed，28.69 秒（commerce30-combined.log）。真实主题安装→来源绑定下一页面推导 1 passed，17.31 秒（commerce30-wp-effect.log）。

## 第三十一批：独立 v3 网站执行协议

- Ruling: 网站固定页面顺序使用 home/shop/cart/checkout/about/contact，独立 v3 audience，最多 55 步，身份证明严格对应未创建的 slug/SKU；旧 v1/v2 不接受 v3 — 签名不能使非成员动作或任意资源版本合法 — 代价是重排蓝图要恢复固定业务顺序后重新封存。
- 重封存页面重排 RED 1 failed；PHP v3 缺合同 RED 9 failed，随后新旧 Python/PHP 意图/投影/攻击合同 97 passed / 1 故障输入 warning，45.37 秒（commerce31-protocol-green.log）。
- 实际临时 CMS 安装→六页创建发布→四项设置→自有导航，全流程严格来源/前序回执与 v3 许可核对 1 passed，229.07 秒（commerce31-wp-site.log）。测试 grant 明确由 fixture 构造，第一步沿用测试 v1 authority；该结果不替代商家批准、Linux 或商品图片验收。

## 第三十二批：网站持久化私有审查

- Ruling: 共享原产品审查的事务、来源、取消、过期和撤销规则，通过独立 artifact kind、intent/grant 类型与九项检查隔离网站审查 — 复制两套权限实现容易漂移 — 代价是共享模块修改须回归旧商品流水线。
- 网站必须有 layout_tablet，旧产品 verifier artifact 不能复用；私有来源准确保存代码包，供取消后到达的回执核对，不能以保存代码代替当前批准。
- 缺模块 genuine RED 9 failed；网站和原产品批准/执行回归 49 passed，22.92 秒（commerce32-approval-green2.log）。前一次 fixture 缺导航快照导致 setup error 未算 RED。

## 第三十三批：网站持久未知栅栏与迟到回执

- Ruling: 与旧产品日志共享 prepare/send/UNKNOWN/terminal 路径；网站最多 55 步，原产品仍 40 步；核对迟到效果使用批准时准确包 — 商家取消或开发后不能丢掉在途 CMS 成功事实 — 代价是只记录已发生结果，不授予后续写权限。
- 网站 17 步重启、最终消费、未知、ledger 提前 begin 的崩溃窗口、撤销/取消后迟到、成功但效果错误，与原产品和新旧审查合跑 55 passed，14.78 秒（commerce33-journal-green.log）。完整真实批准 producer 仍缺。

## 第三十四批：默认关闭的网站 broker

- Ruling: 共享原商品有界 POST/只读对账，每次 preflight 和发送前重新装载当前批准；v3 再核对准确冻结源码及全部 slug/SKU 证明 — 不能因内部 authority 可签名就开放公开写入 — 代价是 execution_enabled 默认 false、未验证 Linux lock 仍拒绝执行。
- 新网站 17 步、重复完成不发送、丢失响应过期后 GET-only、取消/撤销发送前阻断，与网站日志/批准/原商品组 61 passed，45.47 秒（commerce34-broker-green2.log）；Ruff 通过。
- 一次权限错误在写入时清空了 release_publisher.py；已获明确文件写权限，按此前已验证源码恢复，再回归原商品和新网站组。该事故记录保留，不作为原文件未受影响。
- 远端媒体第九操作、公开审查/发布 UI、Linux staging/可信完整证据 producer、第二站恢复部署、授权后的真实模型验收仍未完成。模型 API 费用 0，无 Git 提交/推送或 Desktop 同步。

## 第三十五批：Windows 停止树竞态与固定媒体合同

- 根目录回归 1758 passed / 25 skipped / 1 failed / 5 warnings，454.71 秒；失败为 Windows managed descendants，未标成全量通过。保留 commerce34-full.log。
- Ruling: 验证根进程创建时间后先持有根和既有子树的原生句柄，父进程提前退出仍终止已核对的子孙；不接受 PID 复用 — 先枚举再打开存在竞态 — 代价是 Windows 原生句柄必须在所有出口清理。
- 新增 hold 后父进程退出的真实 RED，修复后全部 launcher 与媒体/旧操作合同 48 passed，14.65 秒（commerce35-tree-media-green.log）；读取线程保留 UTF-8 替换字符诊断，不能隐去失败。
- 固定第九 create_owned_media 合同仅使用本项目净化字节、SHA、MIME、尺寸和原缺失证明；没有 URL、路径或覆盖字段。缺模块 RED 20 failed，随后合跑通过。尚不构成商品图片发布链。

## 第三十六批：真实媒体上传及未知恢复

- Ruling: 第九媒体操作显式扩大图片请求至 16 MiB，其它操作仍 8 MiB；写文件前持久私有 journal，文件创建使用 exclusive、哈希路径及固定 uploads 根 — SQL 回滚不能撤销文件 — 代价是中断留下未知/孤立文件，只读对账不能盲目重发或覆盖。
- Python/PHP 精确字节与作用域合同 33 passed，2.81 秒。临时数据库/HTTP 进程退出导致首轮读取失败，按原数据启动，未重新安装或旋转凭据。
- 实站正常上传 RED 暴露 Windows 绝对路径被 WP meta unslash 破坏；改为固定相对 _wp_attached_file。正常上传、重复回执、服务用户原生上传拒绝、写文件后 crash→UNKNOWN→重复回执→另一操作拒绝，两项 2 passed，8.47 秒（commerce36-wp-media-green3.log）。仅本地 CMS 功能证据，Linux lock 不变。

## 第三十七批：图片回执绑定商品主图与图库

- Ruling: 商品 payload 可显式携带最多五项完整 media_bindings，但顺序/引用/项目净化字节必须匹配成功创建回执；PHP 再核对实际附件和签名媒体版本 — 不能让模型提供附件 ID 接管任意图片 — 代价是修改附件标题/alt/归属后旧绑定失效。
- 缺 resolver/factory genuine RED 22 failed（前一次测试初始化位置参数错误不算 RED）；Python 绑定/旧媒体/PHP 共 55 passed，8.44 秒。
- 实际两张已上传图片→商品主图/图库 RED（FAILED），实现后与原无图商品重复回执 2 passed，30.56 秒（commerce37-wp-product-media-green.log）。缺签名媒体版本返回 FAILED。v2/v3 冻结业务图仍不允许图片，公开完整发布尚未接通。
- 费用仍 0。无 Git 提交/推送、真实商家写入、Desktop 同步。下一步为图片感知的不可变业务图与独立执行协议，再接完整可信 staging 和公开审查流程。

## 第三十八批：图片感知 v4 业务图

- Ruling: v4 独立冻结准确代码、按商品主图/图库首次出现排序的净化图片、商品事实及全部原资源版本；图最多 155 步，先图片后建站或主题/新品 — v2/v3 固定步位不能静默扩张 — 代价是新意图必须重新验证和批准，旧版本仍拒绝图片业务图。
- Ruling: 首版私有 bundle 保存最多 100 MiB 净化字节的 base64 来源，公开投影只能返回描述符 — 审查到执行必须使用相同字节且保留迟到核对 — 代价是大批次私有 SQLite 存储和校验成本增加，不开放原始 bundle 给模型或网页。
- 缺模块 genuine RED；一次 workflow 参数遮蔽 fixture 的初始化错误不算 RED。图片来源/改图/DAG/未知前序与新旧投影、旧操作合同 114 passed，16.47 秒（commerce38-merchant-green.log）。

## 第三十九批：v4 跨语言与真实四步上新

- Ruling: v4 独立 audience，签名 workflow/image_count/product_count、剩余身份和全部当前条件；PHP 同时核对页/商品/图片基数与固定成员 — HMAC 有效不能使非法计数和额外资源合法 — 代价是固定图不能自行加入其它商家动作。
- 缺 authority RED 10 failed（此前缺 fixture 注册不计 RED）；两个计数攻击 genuine RED 后修复。新旧跨语言/意图合同 90 passed / 1 攻击 archive warning，42.28 秒（commerce39-cardinality-green.log）。
- 实际临时站 v4 创建图片→准确主题→draft→publish，逐步完整效果和前序回执 1 passed，41.35 秒（commerce39-wp-v4-green.log）。测试 grant 非商家批准；随后 PHP 基数加强需实站重验。显式 loopback scope 的预验证问题由该实测 RED 暴露后修复。

## 第四十批：v4 持久批准和图片核对

- 当前审查/每次装载批准核对本项目 MediaRepository 净化字节和完整来源；使用独立 review/grant/verification/attempt kind。准确原 bundle 支持撤销后的迟到核对，不能借此继续写入。
- 缺模块 RED 4 failed；图片业务 18 步、重启、UNKNOWN、撤销迟到和商家改图，以及旧网站/商品回归 77 passed，23.36 秒（commerce40-merchant-journal-green.log）。全部 verifier artifact 是明确的 unit fixture，不是真实 Linux 证据。

## 第四十一批：v4 broker 与 live 导航效果

- 默认关闭的媒体 broker 共用有界发送、原批准重装载和只读对账；100 图片场景读前置仍有 600 秒上限，到发送时再次检查批准期限。
- 新旧 broker/日志/批准 70 passed，30.30 秒（commerce41-merchant-publisher-green.log）：18 步完整、重复消费不发送、图片回复丢失后过期 GET-only、未启用/未验证/撤销均零 POST。
- Ruling: staging 事实验证继续只接 staging；发布效果中的导航则显式核对批准连接环境，允许 live/live-test — 原固定 staging 判断会阻止已批准 live 网站 — 代价是两种调用不能隐式混用环境。
- live 合同完整图 genuine RED 后，新旧来源/导航/事实 64 passed，38.35 秒（commerce41-live-graph-green.log）。该证据为合成 live scope，未写真实商家店铺。

## 第四十二批：staging 图片事实验证

- 事实验证新增净化来源 bundle 与独立 SHA readback，完整核对附件元数据、主图/图库顺序；图片缺失、额外引用、修改元数据/字节/关联均不能通过。结果依然 site_verified=false，不能代替浏览器、订单或 OS。
- 缺参数 RED 15 failed；媒体/来源/新旧业务合同 65 passed，52.49 秒（commerce42-stage-media-green.log）。模型请求/费用仍 0，Linux lock 未变、公开完整审查/发布未开放、无 Git 提交或推送。

## 第四十三批：浏览器图片显示和字节证据

- 图片必须出现在商品主内容中、加载且可见；独立同源请求必须 HTTP 成功、无重定向、MIME/大小/SHA 等于批准的净化字节。请求 10 秒、每图 10 MiB，有界流读取；仍 site_verified=false。
- 缺 images 参数 genuine RED 3 failed；第一次合跑 8 passed / 1 failed，揭示 Chromium 能显示带有效 PNG 内容的 404 响应。新增 HTTP/字节核对后 3 passed，124.59 秒（commerce43-preview-media-green3.log）。第一次绿色测试进程失联未计作通过，重跑结果才作为证据。
- 全量回归在本批源码变化之前已通过 1863 passed / 29 skipped / 4 warnings，306.17 秒（commerce42-full.log）；不包含本批新增测试。

## 第四十四批：预览来源与正式目标版本分离

- Ruling: snapshot_hash 继续绑定封存代码的 staging 来源，新增 target_snapshot_hash 绑定所批准目标的初始完整快照 — 正式站和预览站版本必然不同，不能为发布重封存未经审查的代码 — 代价是 v4 私有记录增加必需字段，旧不完整记录拒绝复用。
- 同一准确代码包直达不同 live scope 的 genuine RED 后，v4 意图/权限/日志/broker 34 passed，28.79 秒。旧协议不变、未执行真实商家写入。

## 第四十五批：公开商家审查、批准、发布与只读恢复

- 公开 DTO 仅返回商品事实、媒体描述符、代码/来源/目标摘要和固定步骤，不返回冻结字节、签名、凭据、原始操作 payload。客户端不能提交 passed/report/资源 ID；审查读取已有可信 artifact，缺证据返回 VERIFICATION_UNAVAILABLE。
- Ruling: 工作台按独立受信部署 adapter 显式触发一项固定发布或只读对账；主 API 不实例化 WordPress 凭据持有者 — 保留连接服务边界且防止恢复点击触发新写入 — 代价是默认发行实例仍因缺少部署/验证 producer 拒绝发布，UI 合同通过不代表 Linux 发布接通。
- 缺模块 RED 4 failed、缺 UI 按钮 RED 2 failed；新旧 API/代码预览/桌面手机 23 passed / 2 deprecation warnings，87.81 秒。进度读取缺方法再 RED→GREEN，新旧批准/日志/broker 55 passed，100.15 秒。生成类型检查、Ruff、生产前端构建通过。
- 发送失败后只刷新当前计划版本与本地审查日志，不自动重发；未知结果时禁止后续发布。终端结果展示 effect_verified，不把 wire success 当作业务效果已核对。

## 第四十六批：独立 staging 许可

- Ruling: v5 audience/purpose 仅 staging-preview，使用独立 grant 类型，正式商家仍 v4 — 验证前必须允许预览准备，但不能因此伪造完整验证/商家批准 — 代价是 PHP 显式增加一个独立许可版本，旧 audience、操作图和权限不扩张。
- 缺模块 RED 5 failed；Python/PHP 预览 purpose/正式环境攻击和新旧签名协议 84 passed / 1 duplicate-archive warning，40.13 秒。没有实际 Linux 验收或真实店铺写入。

## 第四十七批：预览来源授权与持久日志

- 预览源要求当前 VERIFYING 计划和固定成果、项目/代码/图片原字节；由 DockerCodingSession 实际 start/probe/capture 回读精确 15 文件后，同事务保存私有来源/不超过 30 分钟的 staging grant。dict“通过”标志、不同回读文件/探针、旧计划与图片拒绝；主业务计划不进入 APPROVED/PUBLISHING/SUCCEEDED。
- Ruling: 预览日志复用业务效果/UNKNOWN 双栅栏，但终态只更新独立 staging_source/attempt 命名空间，私有 phase 为 STAGED — 预览前不具备完整购买/页面验证，不能消费正式商家任务 — 代价是后续可信 verifier 必须明确读取 staging 完成证据再生成真实审查。
- 缺来源模块 RED 6 failed，来源/原隔离/业务日志 36 passed，6.91 秒。首轮日志 18 passed / 1 fixture failure：基础 fixture 已预插入 unit verification，清除该不相关 artifact 后确认预览不会生成验证。命名空间拒绝 genuine RED→GREEN；合跑来源、预览日志、原商家日志/broker/独立签名 25 passed，22.87 秒。
- Docker session 在测试中由明确继承 fixture 模拟，无一项计作真实 Linux 隔离证据；版本 lock 的 verified=false 未改变。新 staging broker 默认关闭。

## 第四十八批：主程序到独立连接器发布命令

- 新主程序 adapter 使用原固定 Connector URL/令牌，只传项目、计划、意图摘要、版本和 publish/reconcile；不接收 WordPress 凭据、HMAC、任意操作或 passed/report。独立服务显式注入私有 publisher 之后才开放固定命令；默认未注入仍拒绝。
- Ruling: 连接器发布进度与源/批准记录使用受信部署的同一运行数据库，连接器身份须有明确数据库访问权限，WordPress 凭据目录仍仅由连接器加载 — 后端不能凭远端“成功”字符串扩张本地批准 — 代价是部署需配置可信身份/SQLite 访问，不能把数据库暴露给模型工作区或 Docker Coding 容器。
- 缺模块 RED 6 failed；真实 ASGI 服务边界、固定命令、错误正文脱敏、重定向/源/目标/大小攻击和原只读/公开批准回归 35 passed，7.17 秒。请求绝不自动重试；写回复缺失/非法保留 WRITE_OUTCOME_UNKNOWN。
- 便携实际 WP/Woo 在当前 PHP 协议上分别执行 v4/v5 图片→准确主题→商品草稿→发布，完整四步前序效果回读 2 passed，71.24 秒（commerce48-wp-v4-v5.log）。属于临时 CMS 功能证据，不是 Linux/商家批准。

## 第四十九批：新品准备也使用完整预览站

- Ruling: 新品 workflow 在独立 staging 上准备完整页面/导航/商品图，正式意图仍只执行新品图；保留原 launch plan_source_hash、准确代码版本和字节 — 新品同样要验证完整购买路径，不可因 staging 空白而绕过页面验证 — 代价是 preview 与 merchant intent 的执行 DAG 不同，必须各自独立签名、只允许 staging preview。
- 缺 helper RED 2 failed；一个 tuple 修改 fixture 错误不作功能失败，修正后新旧来源/图/日志 26 passed，9.67 秒。真实环境 producer 仍待后续连接。

## 第五十批：显式 Linux 发布服务启动与持久进度校验

- 独立入口增加 --enable-publication/--runtime-database/--versions-lock；默认读取模式不变。显式启用需 Linux、已验证 digest 清单、既有运行数据库、私有目录和逐连接精确签名秘密。缺依赖先拒绝，不新建空业务数据库、不生成假验证或批准。退出释放运行 DB。
- 秘密只由连接服务加载；主程序沿用原 Connector URL/服务令牌。wheel 增加固定 PHP Connector 资源，仍保留原编程入口/模型配置。
- 缺 runtime 模块 RED 2 failed，启动/连接器/私有配置/清单 12 passed，6.51 秒。新增远端伪造 progress genuine RED 后，强制 DTO 全量等于本地受信 DB 来源/attempt 回读；合跑 28 passed，5.01 秒。Ruff 和生成类型检查通过；配置 CLI --help 已验证。
- Ruling: 主程序读取受信 DB 中的 progress，不打开连接器 ledger 或凭据目录 — 固定来源正确的远端响应仍可能伪造完成数 — 代价是并发写导致响应与较新 journal 不一致时需显式刷新，不能把该回复当作完整成功。
- 根目录全量回归 1900 passed / 30 skipped / 4 warnings，949.65 秒（commerce50-full.log，exit 0）。真实 Linux provisioning/购买验证 producer、内容候选确认、第二 CMS 环境与完整验收仍未完成。

## 第五十一批：商家文案确认与新来源批次

- 商品角色仅能提出标题/描述改写，冻结原始事实与候选摘要；价格、库存、SKU、币种、分类、图片和 source_facts 改动不进入确认。公开 API 要求本地身份、精确项目/计划版本和候选摘要，模型角色没有确认工具。
- Ruling: 明确确认同事务创建真实 CSV 校验的新批次、项目版本递增并使旧计划/许可失效、取消旧队伍 — 商家确认是新资料来源，不能给旧代码或批准续权 — 代价是需重新创建团队任务并封存/验证代码。
- 缺模块 genuine RED 10 failed；API 缺路由 RED（另一个工具名断言错误已纠正，不计功能缺陷）。API/文案/原工作流 36 passed，4.50 秒。缺 UI RED 2 failed；桌面/手机文案与原团队浏览器 4 passed / 2 warnings，71.10 秒。
- 并发角色完成暴露候选旧版本无法继续确认，genuine RED 1 failed；刷新只更新预期计划版本，不修改原候选；旧点击拒绝、刷新后可确认、确认重试使用原回执。相关 34 passed，7.84 秒。一次前端编译发现 optional products 未防护，修复后生产构建通过。
- 没有模型请求、没有商家写入、没有生成验证报告。以上 UI/CMS 来源仍不是完整 Linux 验收。

## 第五十二批：分类名称与身份的独立事实核对

- WordPress 快照新增有界分类 id/name，资源版本同时包含分类名；正式效果/预览验证要求指定分类的唯一 ID 与准确名称。分类改名、换 ID、缺失或重复均拒绝。
- 原行为 genuine RED 6 failed；新分类/原上下文/网站执行图/文案 API 58 passed，18.17 秒。便携实际 WordPress 修改分类名而保持同一 ID，确认快照版本变化且旧 publish 失败：1 passed / 26 deselected，19.26 秒（commerce52-wp-category.log）。
- 未指定分类仍沿用 Woo 默认处理；本批未增加任何商家分类覆盖工具。模型费用 0，版本 lock 仍 verified=false。

## 第五十三批：明确启动整批发布与停止后续步骤

- 新增连续发布已批准步骤；每个响应必须维持同一冻结来源/目标并仅增加一个已核对步骤，最多执行固定图的步骤数。未知结果、无确认进度、scope/版本错误立即停止；不自动重试或启动恢复写入。
- Ruling: 当前整批控制在打开的工作台中逐步驱动，关闭面板或点击停止只停止后续步骤，不取消已发送请求 — 现有每步持久 UNKNOWN/回执能安全核对，而浏览器无法撤回 CMS 已执行请求 — 代价是尚不等于脱离工作台的后台发布作业，后台验证 runner 仍是后续必做项。
- 首轮浏览器 3 failed，后续合跑 3 failed / 4 passed：均是测试等待“已批准”文本误匹配新增按钮，过早直接读 DB 导致 REVIEW_STALE/锁竞争，不能记为功能 RED。依据失败栈改为等待准确批准标题后，整批完整/未知/无进度及原审查 UI 5 passed / 2 warnings，144.18 秒（commerce53-browser-green2.log）。回执由测试明确模拟，不计作真实发布或 Linux 验收。
- 新类型检查、Ruff 和生产构建通过，前端 index-DrOQnDaL.js 445.78 KiB。

## 第五十四批：离线资源与参考容器检查合同（A 的部分实现）

- 新模块读取已验证清单中的 Woo ZIP SHA/版本，拒绝越界/链接/重复/异插件/超量资源；只增加固定 12 Connector、15 主题文件及 staging 安全 guard，排除测试故障插件。生成准确 manifest 与固定 tar 来源。
- staging guard 仅在 staging 且有正确 job 常量时启用：屏蔽邮件/外部 HTTP，仅离线 COD、禁索引/cron 的真实设置诊断由只读权限入口提供。
- 容器检查合同要求准确 job/role/image、独立命名卷/网络、loopback web、固定私有密码文件只读绑定、禁止宿主 namespace/socket/设备、限制资源；CLI 与 CMS 服务权限不同。此合同本身不创建容器，也不是实际 daemon/探针证据。
- 缺模块 genuine RED 10 failed；资源与伪造 Docker inspect 攻击 10 passed，0.48 秒，PHP -l 和 Ruff 通过。完整 provisioning/bootstrap/lifecycle 仍未实现，A/B 不勾选通过；模型费用仍 0。

## 第五十五批：实际 PHP guard 合同与持久预览作业

- PHP CLI 测试发现顶层命名函数即使文件提前 return 仍会注册；genuine RED 3 failed。改为条件内声明函数与钩子，非 staging/非法 job 不注册；实际 PHP 过滤器与资源测试 14 passed，0.66 秒。模拟 CMS 函数不计作真实安装安全探针。
- 新 reference_job/request 保存在原事务 DB；准确来源、版本、端口保留，启动先 UNKNOWN，重启不能重新 begin。清理先 CLEANUP_UNKNOWN，全部固定名字只读证实不存在之后才 CLEANED。未知清理不能把端口重新分配。
- 缺作业模块 RED 3 failed；作业/资源/真实 PHP 17 passed，1.00 秒。私有 runner 能调用 ready，但公开或模型无写入方法；完整 runner 实际检查仍待接通。

## 第五十六批：Docker 参考资源准备（尚非完整 bootstrap）

- 固定 runner 校验 Linux daemon/本地 digest 镜像和外部资源不存在，保存密码于私有新目录，先写 UNKNOWN 再创建独立 internal 网络、卷和固定角色容器。无拉取、任意脚本、自动重试/异常后删除；CLI 超时可能已有资源，保持 UNKNOWN。
- 新增实际 inspect 合同对照 network/volume labels、local driver、无外部卷选项/额外容器以及容器 role/source/mount 权限。CMS 允许启动所需六种 capability，CLI 全禁；这些是参考 CMS，原 Coding 仍 UID65532/无网络/无卷权限。
- Ruling: prepare 只返回 site_ready=false 的资源诊断，不把容器运行视为 CMS ready — 还必须离线复制资源、初始化、安装安全设置并实际回读 — 代价是完整商家流程仍未打通，A/B 不能宣称完成。
- 缺 runner RED 3 failed，资源 inspect helper RED 1 failed。扩展测试误插入旧变量块导致 NameError，修复 fixture 位置后 21 passed，1.26 秒（commerce56-resource-green2.log）。Windows 下 Linux 路径均是明确 fake daemon 合同，没有实际容器。
- 新 wheel 已离线构建（commerce56-wheel.log）；尚未完成本批 clean-install/逐资源验收。未消费 API、未改 verified=false、未提交推送。

## 第五十七至六十一批：购买发送记录、只读恢复与离线初始化

- BuyerProbeRepository 在原 DB 发单前持久 UNKNOWN，不接受第二次 begin；回执只保留 order_id/on-hold，不保存邮箱/地址/cookie/key。回执成功仍 buyer_flow_verified=false，尚无实际下单 producer/独立订单回读。缺模块 RED 2 failed，相关 23 passed，3.30 秒。
- reference runner 的 recover 仅 daemon 查询/list/inspect 本作业固定名字与身份；未知作业不自动创建/删除/标记ready。缺方法 RED 1 failed，相关 24 passed，1.72 秒。
- 固定 PHP bootstrap 仅新空数据库：最小 service 身份、离线 COD/配送、禁邮件/网络/索引/cron、运行配置私有文件；拒绝已有站点，不旋转已有凭据。缺文件 RED 8 failed；首次合跑因为全局 fixture 预创建 teams-home 导致断言错误，按原目录基线检查后相关 32 passed，5.12 秒。
- runner 新增准确准备元数据、实际容器/网络回读、一次安装持久 fence、冻结 tar、私有凭据输出消费和 safety 回读。丢失初始化回复/不安全网关/错误资源保留UNKNOWN，重试不能再次安装或轮换账号。PHP 文件逐项 SHA/大小回读拒绝遍历和配置凭据路径。缺方法 RED 1 failed、缺 readback 文件 RED 4 failed；成功路径测试捕获缺 Path 导入 RED 4 failed，修复后合跑 41 passed，5.97 秒（commerce61-bootstrap-green2.log）。
- Ruling: 只有固定资源 daemon 回读、实际 PHP safety 与准确已安装 manifest 都完成才将 reference job 标记READY — 解压或安装进程退出不能替代来源与安全验证 — 代价是任一回读失败须保持UNKNOWN并人工/只读恢复，不能再次安装。
- 本批成功路径 Docker/CMS 明确模拟，PHP仅真实 CLI/模拟CMS输入；没有 Linux daemon 或新真实 CMS 初始化验收。A 的服务/API/registry整合、清理恢复和 B 完整购买验证仍待实现，不能勾选整个阶段。
- uv 启动在沙箱内被 OS 拒绝，未请求升级；改用既有 Python venv/pip 成功仅安装 wheel（--no-deps），这不是完整 fresh-dependencies/pip-check 通过。发布 wheel 待最终重建，旧安装不覆盖本批新文件。模型请求/费用仍 0。
## 第六十二至六十九批：资源清理、只读恢复与预览站工作台

- runner 显式清理先持久 CLEANUP_UNKNOWN，再逐项核对本作业固定资源身份、卷消费者和网络成员；容器/网络按不可变 ID 删除，不使用 prune。每次删除后重新检查，全部固定资源确实不存在才 CLEANED。外部身份/网络成员/外部卷/消费者或丢失回复停在未知状态。私有诊断与凭据不递归删除。
- 缺清理方法 genuine RED 6 failed；第一次 GREEN 2 failed / 4 passed，原因是 fake daemon 按名称存储，错误合并 Docker 容器/卷的独立命名空间；改为类型+名字后清理及资源合同 29 passed，4.15 秒（commerce62-green2.log）。相同名字的不同类型在 recover 中分别返回 resource keys，不用名称集合掩盖缺失类型。
- 新 verify 只读恢复安装完成但安全回读中断的作业：当前项目来源、私有文件权限/固定连接、准备身份、真实 daemon inspect、PHP safety 和文件 manifest 必须重新一致；不重复解压、安装或账号轮换。缺方法 RED 1 failed / 5 passed；相关 12 passed，1.65 秒（commerce63-green.log）。没有存下凭据的丢失安装回复不能自动恢复 READY。
- 独立 ReferenceEnvironmentService 固定宿主端口池、reserve/prepare/bootstrap/verify/recover/cleanup 动作，未知作业不能重复 provision。缺服务 RED 6 failed；服务 6 passed，1.65 秒。独立 Connector 加授权、严格命令 API 与仅 READY 私有连接动态 registry；缺入口 RED 2 failed，相关 8 passed，1.17 秒。
- 启动默认关闭；显式 --enable-reference-environments 要求现有 owner-only 私有目录、现有运行 DB、verified Linux manifest、本地 Woo ZIP hash 与固定端口范围。未提供 daemon 或 verified=false 不启用，不自动下载、拉取或假造镜像清单。
- 主 backend 仅向固定 Connector 发送有限命令；响应必须与共享可信 DB 作业一致，拒绝伪造 READY/跨项目/跳转/超量/压缩响应，不回显远端私密错误、不自动重发。相关 23 passed，5.20 秒（commerce66-green.log）。代码先于这一批客户端攻击测试实现，不计为客户端 genuine RED。
- 清理已绑定预览站时同事务解除该连接、增加项目版本并使原计划/许可失效；缺失解绑 RED 1 failed / 6 passed，修复后合跑通过。
- 工作台增加预留/准备/刷新/只读核验/资源查询/明确勾选清理/就绪后显式绑定。超时不自动轮询写入或重新安装；源项目版本变化不能启动旧预留作业。实际桌面/手机浏览器 2 passed / 2 warnings，4.42 秒（commerce67-browser.log），底层 Docker 明确模拟，不能作为真实 Linux 证据。生产构建 index-D-ENz-HD.js 449.91 KiB，类型检查通过。
- 本地 Woo 11.1.2 源码表明实体 COD 默认 processing；隔离 guard 固定 on-hold，非 staging 不注册。订单 probe 使用私有 HMAC 签名绑定 job/probe/商品/SKU/代码来源/意图；只读查询要求唯一、准确绑定、COD/on-hold 与单件商品，不返回邮箱/地址/cookie/order_key。状态 RED 1 failed / 3 passed；新 PHP probe RED 首轮 1 failed / 5 passed（否定测试缺少检测 missing 的断言，不视为充分 RED），补断言后 6 failed；PHP probe/guard/恢复/清理/服务合跑 29 passed，8.86 秒（commerce69-green.log）。真实 PHP CLI 配模拟 Woo 对象，尚无真正 Store API 下单/独立订单回读验收。
- 当前全量仍是第 50 批 1900 passed / 30 skipped / 4 warnings，不覆盖后续批次；新参考资源/连接边界合跑 78 passed，7.39 秒（commerce65-regression.log），同样不覆盖随后 UI/购买 PHP 变更。
- A 有服务入口与 UI，但尚未接通 B 的每验证作业独立环境、后台 verifier 与真实购买 sender；request_review 尚未产出可信九项报告。D 第二真实站恢复、最终 wheel/fresh deps/全量/最终 review 尚未完成。模型调用和费用 0，未提交推送或同步 Desktop。

## 第七十批：部署可读性与安装前就绪修复

- 发现宿主 0600 密码文件绑定给非 root Apache/CLI 后不可读；写入/fsync 后仅该固定密码文件改为 0444，宿主父目录保持服务 owner-only 0700，容器绑定只读且 Coding 无该挂载。连接与签名文件继续 0600。Windows 文件模式不能证明 Linux 权限，补充记录 chmod 合同 RED 1 failed / 4 passed；不是实际 Linux 安全探针。
- 安装前新增固定只读 PHP 文件/可写目录/数据库连接检查，有总 60 秒与单次 5 秒预算，不把容器 Running 当 CMS/DB ready。缺方法 RED 1 failed / 5 passed；先完成就绪检查，再重新核对作业/项目来源，然后创建一次安装 fence。
- bootstrap/verify 固定 exec 和后续 inspect 改为已核对的不可变容器 ID，避免名称被替换后把资源或凭据发到另一容器。清理也保持容器/网络 ID 删除。源变更或清理并发后不能继续安装。
- PHP 单件数量检查补充 1.5 攻击 RED 1 failed / 6 passed，改为准确数值 1.0，避免整数强转误接受。第 69 批完整新增范围回归 105 passed / 2 warnings，18.75 秒（commerce69-regression.log），不覆盖之后 readiness/密码改动；第 70 批资源/初始化/清理 18 passed，4.21 秒（commerce70-id-green.log）。
- 增加参考站部署/恢复文档 docs/commerce/reference-environments.md，明确默认关闭、verified=false、缺 Linux 环境、请求内运行而非后台，以及真正购买 sender/九项 verifier 仍未完成。模型调用/费用 0。

## 第七十一批：完成预览效果的只读验证来源

- 预览 grant 在所有效果完成后被 consumed，旧 load/start 必须继续拒绝再次写入；新增 verification_source 只读路径，使后续购买/页面 verifier 能读到准确冻结意图和全部独立核对的效果历史。
- 只接受 STAGED/consumed、准确私有 capture、当前项目/计划/代码/媒体/取消状态及完整成功历史；不续期、不产生新 grant、不生成商家 passed 报告。未完成来源 RED 1 failed / 4 passed；预览来源与效果回归 11 passed，5.91 秒（commerce71-green.log）。
- 第 70 批最终启动参数/关闭资源、缺环境拒绝、安装前就绪和 PHP 商品 probe 合跑 22 passed，7.00 秒（commerce70-final.log）；Ruff 通过。Linux 成功启动、实际 Store API 下单、后台九项 verifier 和最终完整回归仍 NOT_RUN/未实现，不能用这些合同结果填验收 PASS。

## 第七十二至七十五批：实际购买发送与独立金额回读

- BuyerProbe 新增严格独立订单证明：准确绑定 job/probe/来源/意图/商品/SKU、COD/on-hold 和单件数量，拒绝额外个人信息字段。发送授权与 UNKNOWN 栅栏在同一事务；回读可核对丢失回复，但不会重发或把 buyer_flow_verified 改为 true。缺方法 RED 15 failed；读回与日志 17 passed，1.40 秒。
- SyntheticBuyer 使用固定 loopback URL、匿名 Cart-Token、固定合成资料/离线 COD 和有限请求预算；只读 safety/probe 访问才使用服务身份。请求下单前再次校验完整部署历史、来源/商品/取消/期限。来源只读核对不续期；新发送要求未过期。缺模块 RED 9 failed；发送器/回读/来源 29 passed，11.47 秒。
- Windows 一次性真实 CMS 首轮发现 Store API add-item 成功实际返回 201，被发送器误拒绝；补测试 RED 1 failed / 10 passed，修复仅允许对应 POST 的 200/201。真实下单、签名独立回读和再次只读核对 1 passed，34.33 秒（commerce74-wp-green.log）。宿主隔离和来源部署在该测试明确模拟，不计作 Linux 或完整业务流程验收。
- 购买栅栏同事务冻结商品价格/币种；独立 PHP 回读增加商品小计、配送、税和总额，要求价格与冻结事实相同、测试配送 5、税 0、总额为商品价格加 5。缺参数 RED 6 failed / 15 passed；相关 46 passed，14.98 秒（commerce75-green.log）。真实 CMS 金额核对 1 passed，22.28 秒（commerce75-wp-amounts.log）。临时 guard/配置已删除并恢复原 fixture 网关设置；测试数据仅留在一次性 CMS。

## 第七十六至七十八批：持久验证作业与防重复执行器

- 私有 VerificationJobRepository 固定六个阶段，冻结项目/计划/封存代码/媒体来源。同一来源不能改 request_id 再创建作业；每一步先事务独占 claim。中断不续租重发；迟到回执可记账，但来源变化或取消阻止下一步。只保存阶段回执 SHA，无凭据、原始 HTTP 数据、passed 报告或批准。缺模块 RED 13 failed；首轮 13 passed，3.39 秒（commerce76-green.log）。
- 私有 VerificationWorker 只执行一次准确阶段；并发 claim、超时、异常、无效回执和取消保留原栅栏。必须完整提供固定生产适配器，缺配置不运行，不能以模拟 fallback 生成通过。缺模块 RED 6 failed / 17 passed；作业和执行器 23 passed，5.40 秒（commerce77-green.log）。测试适配器全部明确模拟，不计作实际后台生产验证。
- 生产购买回读强制要求冻结价格 artifact，缺失不能退回旧无金额日志模式；RED 1 failed / 21 passed。相关合跑 70 passed，27.00 秒（commerce78-green.log）；该结果与前批测试重叠，不相加。新 Python Ruff 与三份 PHP 语法检查通过。
- 当前模块未接入启动循环/API，未接通每作业独立参考站来源绑定或九项生产检查，COLLECTED 不等于验收通过。request_review 继续明确 BLOCKED，不伪造可发布结果。第二真实站恢复、最终 wheel/fresh dependencies/全量/最终 review 未完成。模型调用与费用仍为 0；未提交、推送或同步 Desktop。

- 第 78 批扩展参考站/来源/购买/作业回归 172 passed，39.01 秒（commerce78-regression.log）；当前生产发送器强制价格来源的真实一次性 CMS 测试 1 passed，11.67 秒（commerce78-wp-final.log）。两份临时 MU 文件均已不存在。以上不是全量编程核心回归或 Linux/九项验收。

## 第七十九批：历史作业积压不阻塞新任务

- 检查发现队列先截取最旧 100 个作业再筛选，已完成历史超过 100 个会隐藏后续待执行任务。针对 101 条历史记录的测试 RED 1 failed；改为按 rowid 分页并逐项校验完整性，最多返回 100 个实际待执行任务，不能跳过损坏历史记录。
- 作业/执行器回归 24 passed（commerce79-green.log），Ruff 与 git diff --check 通过。变更仅影响私有排队基础；生产循环、全部验证适配器和可信报告仍未接通。

## 第八十批：每个验证作业独占参考站，不使商家来源失效

- 新 VerificationTargetRepository 在 provision 前事务保存专属 reference 归属，只接受当前 reference claim、同项目/版本/来源和尚未启动的 RESERVED 资源。每个作业只能绑定一个参考站，参考站只能有一个验证归属；不改商家项目连接或版本。使用目标必须已有 READY 和准确绑定/就绪回执，取消、来源变化、清理或证据损坏即拒绝。
- StagingSourceRepository 与 PreviewRepository 接入私有目标读取；有专属绑定时拒绝回退原预览站。prepare_source 仅使用未保存的项目副本适配纯声明构造，授权时仍独立读取真实项目和私有归属，不授权正式目标。
- 首轮 9 failed 中 8 个是缺模块 RED，另一项是测试 loopback 连接未显式设置 HTTP 许可；修正测试配置与嵌套 Pydantic 摘要编码后 9 passed，3.19 秒。扩展完整部署回归首次 1 failed / 56 passed：旧测试 outcome 把导航 URL 写死为 https://shop.test，与新目标不符；改为 connection.base_url，不修改生产校验。专属站点的全部 18 效果、完成后只读来源、清理后失效、截图/来源/作业和既有步骤合跑 75 passed，55.70 秒（commerce80-regression2.log）。所有 Docker/CMS 回执在这些测试明确模拟，不计作 Linux 验收。

## 第八十一批：固定参考站阶段接入私有执行器

- ReferenceVerificationStage 只接收共享可信 DB 的受信 ReferenceEnvironmentService，端口/离线资源由服务固定。按验证 job id 预留参考资源并先写独占归属，再调用原一次准备/初始化；准备完成后、CMS 安装前重新核对验证作业取消和来源，取消不继续安装。
- 丢失 provision 回复后原 worker 保持 NEEDS_RECONCILIATION，不能再次运行发送；明确 reconcile 只读 verify 现有资源/安装证据，然后记录准确就绪摘要。不重新 provision、解压、安装、删除或轮换凭据。缺模块 RED 4 failed；阶段与原服务 11 passed，4.18 秒（commerce81-green.log）。Ruff 通过；成功 runner 明确模拟，没有真实 Linux daemon。
- 第一阶段已接通实际生产服务代码，但完整 worker 尚未接入启动循环，来源捕获/预览部署/购买/浏览器/事实其余阶段仍待生产适配器。九项可信报告、商家审查、第二站恢复、最终打包/全量/验收仍未完成；没有模型调用/费用、提交、推送或桌面同步。

- 本批最终专属目标/执行器/截图/来源/部署步骤/参考站服务/API/恢复清理/购买回归 140 passed，67.60 秒（commerce81-regression.log）。这不是全量原编程核心回归，不与第 80 批 75 或前批 172 相加。

## 第八十二批：商家工作台视觉与响应式布局

- 借鉴 10Web 的工作台组织方式，桌面增加项目内导航、中央网站预览和右侧品牌/团队面板；建站、商品、团队、环境与备份仍使用原业务接口，保留通用编程入口。导航不卸载表单，避免切换区块丢失草稿。
- 使用浅色灰绿、深森林色与青柠强调色建立视觉节奏；新增本地 SVG Bayer 有序抖色图形，不下载图片或远程字体。没有真实截图时明确显示装饰性空状态，不把图形当作店铺预览或执行证据。
- 真实预览仅来自当前有效计划与封存代码；项目/版本变化清除旧预览。右侧团队分工为角色说明，不伪造 Agent 运行进度。新项目采用视觉介绍与品牌表单并排布局。
- 桌面先实现，随后适配 768px 平板和 390px 手机；窄屏导航可横向滚动，整页无横向溢出。动画仅短距离进入与轻微悬停，prefers-reduced-motion 禁用动画与过渡。
- 最终相关浏览器回归 17 passed / 2 warnings，41.60 秒（commerce82-browser-final.log），覆盖桌面/平板/手机、商品导入、代码审查、截图、参考站、团队与发布审查。底层 Docker 与报告 fixture 仍为模拟，不计作真实 Linux/完整商家验收。
- TypeScript 检查与 Vite 生产构建通过，CSS 33.10 kB、JS 459.95 kB。独立视觉脚本检查三个尺寸、导航、页面溢出与减少动画设置，无浏览器 JavaScript 错误；截图位于 work/commerce82-visual-final，使用一次性演示品牌，没有模型调用。
- 本批先实现视觉再补检查，不记录为 genuine RED。没有修改生产发布权限或模型配置，没有提交推送、同步 Desktop 或重建 wheel；后台生产适配器和完整商家验收缺项仍按前批记录保留。


## 第八十三批：工作台专业中性色配色

- 按用户反馈替换森林绿/青柠配色：冷白背景、石墨深色预览、低饱和钢蓝抖色、稳重蓝色操作与选中态。商家工作台打开时外围 MUSE 导航和顶部栏同步配色；退出后沿用原页面样式，业务接口和布局不变。
- 表单焦点和按钮悬停同步蓝色；成功/错误状态保留语义色。保留原抖色几何、动画与响应式结构。
- TypeScript 与 Vite 生产构建通过；一次性演示项目浏览器检查桌面 1440、平板 768、手机 390 的导航、整页溢出和减少动态效果，无 JavaScript 错误。截图位于 work/commerce83-visual，实际查看桌面效果；没有模型调用或外部发布。本次仅改配色，未重复第 82 批业务测试，不将前批 17 项计作本批重新执行。


## 第八十四批：参照竞品的中性后台配色

- 用户否定蓝灰版后，查阅 10Web 官方工作台说明/克隆站点界面、Shopify 官方 Sidekick 展示与 Replit 官方任务面板说明。参考链接：https://help.10web.io/hc/en-us/articles/360016173632-Introduction-to-10Web-Dashboard 、https://10web.io/blog/how-to-clone-a-wordpress-site/ 、https://apps.shopify.com/built-in-features/sidekick 、https://docs.replit.com/features/agent/task-board 。公开展示图/说明并不证明登录后最新版所有界面的配色，当前色值为 MUSE 自主设计，没有声称提取竞品官方设计 token。
- 改为白色卡片、无蓝色底调的浅灰工作区和深灰文字；紫色仅用于主要操作、AI 抖色图与少量焦点。中央空状态使用浅淡紫底，取消大面积深蓝；标题改无衬线，项目选中态使用深灰。外围侧栏同为中性灰，语义成功/失败色保留。
- TypeScript/Vite 构建通过。一次性演示项目实际浏览器检查 1440/768/390 三种宽度的导航、整页溢出及减少动态效果设置，无 JavaScript 错误；查看桌面截图，位于 work/commerce84-visual。仅视觉变化，不重复业务全套回归；没有模型调用、发布或推送。


## 第八十五至八十七批：来源捕获、预览部署与购买阶段

- SourceCaptureStage 固定解析本作业专属 READY 参考站，GET 准确 snapshot/六页 slug/SKU/媒体 SHA，使用原净化媒体和 DockerCodingSession 核对封存代码，再保存 v5 staging 授权。取消/错误目标/外部主题不授权；丢失回复只读取现有 grant，不重新捕获或续期。缺模块 RED 6 failed；首轮 GREEN 2 failed/4 passed 捕获 dataclass 未转换 JSON 的缺陷，改 asdict 后相关 26 passed，11.27 秒。
- StagingVerificationStage 复用固定 StagingReleasePublisher 逐步部署并核对效果；取消、未知或无准确递增回执停止。最后一步丢回复可 GET 对账完成；中途对账仍不能发送剩余步骤。缺模块 RED 4 failed，4 passed，18.58 秒。Ruling: 中途中断后的显式续跑另行实现 — 自动解锁阶段可能重发未知写入 — 代价是目前需要保持 NEEDS_RECONCILIATION，尚不满足完整自动恢复体验。
- BuyerVerificationStage 消费准确 source/staging 回执，复用 SyntheticBuyer 的匿名购物、持久发送栅栏与独立金额核对。checkout unknown 仅 GET 恢复，缺 probe 不能再次购买。缺模块 RED 3 failed，3 passed，44.73 秒。无商品/全零库存仍明确阻塞；独立 disposable fixture 未实现。
- 第 85–87 批合跑 85 passed，72.94 秒（commerce87-regression2.log）。两次错误命令引用不存在的 worker/probe 文件未执行测试，已改用实际文件集合；不把这些命令视为通过。新 Python Ruff 全部通过。
- 本批生产适配器只在明确模拟的 CMS、Docker/捕获和隔离私有 DB 上集成测试。不是实际 Linux 或新实站端到端证据，不生成 trusted_merchant_verification/live 批准；没有模型调用、推送或桌面同步。后台启动循环、浏览器/事实阶段、九项报告、第二站及最终交付继续未完成。


## 第八十八批：浏览器与事实生产适配器

- ReadbackVerificationStage 按当前私有作业重新 GET 预览 snapshot/图片证据、核对固定主题/页面/价格/库存/分类/图片事实，再使用原 capture_staging_preview 保存三档截图。只能消费准确 source/staging 摘要，没有公开 passed 上传接口。
- 浏览器失败保存只读诊断但不记通过回执；事实阶段重新回读，拒绝截图之后的资源或价格变更。证据绑定 job/source/claim token/preview id；恢复只读已保存证据，不重新运行浏览器。
- 缺模块 RED 4 failed；首轮 4 passed，33.46 秒（commerce88-green.log）。补充截图损坏恢复测试 RED 1 failed：阶段原来仅检查汇总摘要，未重读 PNG；新增逐张准确哈希/尺寸检查和末次源校验。相关回归 79 passed，138.06 秒（commerce88-regression.log）；全量仍在运行，最终结果待下条记录。
- 六个阶段已具备固定适配器，但尚无完整后台启动、最终九项报告/商家审查 producer。当前测试 CMS/浏览器捕获/隔离全部显式模拟，不计作实站或 Linux 验收；取消和未知结果仍阻止发布。无商品/零库存独立 fixture、购买后真实库存行为、部分部署明确续跑继续待处理。

- 本批整仓回归：2092 passed / 31 skipped / 1 failed / 4 warnings，606.16 秒（commerce88-full.log）。唯一失败为 Windows launcher 的父进程提前退出用例，停止原生树时报拒绝访问。没有把整仓记为 PASS。启动器原文件未修改；独立六项重跑 6 passed，11.37 秒；同一失败用例连续 12 次重跑均通过（每次约 2.8–3.0 秒）。目前属于未稳定复现的进程退出竞态，根因和修复尚未确认，不扩大权限或放宽 PID/创建时间检查。

## 第八十九批：固定六阶段后台调度层

- 新增 VerificationRuntime：严格要求六个准确适配器类型、同一 jobs/source/service 和正确 browser/facts 阶段；拒绝任意 passed producer。复用原发送前 claim、超时和持久未知栅栏，每轮每个 queued 作业最多推进一个阶段，单轮最多读取 100 个 queued 作业。
- 私有宿主轮询支持明确 stop 事件及有界间隔；未知/取消/收齐作业不进入发送队列。显式 recover_interrupted 只把 RUNNING 改为 NEEDS_RECONCILIATION，不执行外部操作；调用者必须先确保旧进程退出并拥有服务，该操作不在轮询启动时自动执行，以免把另一存活 worker 的 claim 当重启残留。
- 缺模块 RED 4 failed，39.28 秒；初轮相关 28 passed，62.90 秒（commerce89-runtime-green.log）。新增停止事件、非法间隔及宿主协程取消的测试，最终 runtime/jobs/readback/launcher 相关回归 42 passed，109.28 秒（commerce89-confirmed.log）；Python Ruff 与 git diff --check 通过。
- 此模块尚未装配到主程序/Connector 启动配置和公开进度 API；不会生成 trusted_merchant_verification、改变 REVIEW_REQUIRED 或授予发布许可。后台代码能力与服务启动接通分别记录，不宣称已完成 B 整阶段。继续待开发：最终九项报告及审查同事务、宿主正式启动与精简公开进度、部分部署明确续跑和空商品 fixture；真实 Linux/第二站/最终交付仍未验收。

- 修复 Windows 停止脚本退出竞态：修复前相关合跑 39 passed / 1 failed，181.94 秒（commerce89-final.log），再次命中第 88 批失败；确定性原生调用注入测试 RED 1 failed，1.87 秒，证明原实现对正在退出但句柄尚未 signaled 的进程过早报错。现在保留已核验句柄，保存 TerminateProcess 错误后最多等 5 秒；仍存活则拒绝成功，不按 PID 重新打开或放宽创建时间/父子身份。初轮 launcher 7 passed，13.87 秒；补充 live 拒绝反向测试后包含在最终 42 passed 中。此修复后未重跑整仓，不能用局部通过把之前整仓结果改写为全套 PASS。没有模型调用、正式发布、Git 推送或桌面同步。

## 第九十批：固定九项报告与审批来源复核

- 新增 TrustedMerchantVerifier，严格消费 VerificationRuntime 固定适配器，不接受 passed/报告字典。仅对 COLLECTED、未取消、来源仍一致的作业读取准确已消费的预览授权及完整效果日志；重新核验参考环境、只读核对已有订单的签名与金额、逐张复核准确浏览器截图，再 GET 当前预览 snapshot/媒体并重新核对事实。
- 正式目标必须是项目登记的准确连接，不能复用作业专属预览 URL/连接。固定 GET 当前正式目标 snapshot、slug/SKU/媒体 SHA 缺失证据，生成准确 v4 merchant intent；新品图只包含新品正式步骤，预览仍为完整站点。报告九项为 os_boundary/pages/layout_desktop/layout_tablet/layout_mobile/links/product_facts/buyer_flow/media，不用阶段摘要数量直接填 passed。
- 报告与私有 provenance 同事务保存，绑定 job/source、完整证据字节摘要、正式 intent 和原预览授权期限。生成前后复查来源、取消和证据变化；重试不续期，不发 CMS POST，不生成 merchant_release_grant 或自动改变 VERIFYING。MerchantReleaseApprovalRepository 对本生成器的 verification-* 报告再次复核 provenance；其它旧私有报告保留既有语义，没有开放报告上传。
- 缺模块 RED 6 failed，1.74 秒（commerce90-red.log）；首轮 6 passed，75.73 秒（commerce90-green.log）。报告/runtime/原商家 journal 相关 19 passed，247.58 秒（commerce90-regression.log），包括报告后截图变化、过期与生成中取消。补充时钟回拨 RED 1 failed，17.20 秒：缺有效期下界；增加 issued_at 和不超过 1800 秒期限检查，回拨/过期定向 2 passed，29.52 秒。Ruff 与 diff --check 通过。
- 修复后组合首次 18 passed / 1 failed，198.22 秒（commerce90-final.log）。失败发生在 fixture 的 staging 第 3 步，早于 buyer/browser 和报告生成，留 NEEDS_RECONCILIATION；没有把准备失败当作报告测试成功，没有重发该作业。过期与回拨独立重跑均通过；同组合确认回归 19 passed，133.07 秒（commerce90-final-confirm.log），包含回拨保护及原商家审查 API。准备阶段的单次不稳定失败尚未确认根因，保留记录；局部确认通过不等于整仓或实站验收通过。
- 所有新集成测试明确模拟 Docker/CMS/浏览器，不算真实九项或 Linux 验收。尚待接通：报告生成后进入 REVIEW_REQUIRED 与保存审查的同事务转换、主服务启动/公开进度、部分部署明确续跑、空商品 fixture、真实购买库存行为、第二站与最终交付。本批没有模型调用、发布、Git 推送或桌面同步，原 Coding/模型配置不变。


## 第九十一批：报告、待审查状态和审查记录同事务

- TrustedMerchantVerifier.request_review 同事务提交可信报告、provenance、计划 REVIEW_REQUIRED、准确商家审查记录和私有转换锚点；中途失败全部回滚。原 collect 保留诊断用途。重复请求核对现存来源与原期限，不续期、不生成正式发布许可。
- 审查及之后阶段允许准确冻结预览的只读读取；旧 VERIFYING 作业不能覆盖新作业目标。预览部署写入仍需原 VERIFYING 来源，不为展示截图放宽权限。
- RED 3 failed / 31.02 秒，GREEN 3 passed / 34.65 秒；审查、可信报告、验证作业、目标和原发布审批相关 101 passed / 261.02 秒（commerce91-regression.log）。全部外部效果明确模拟；不能据此标记真实 Linux 或实站验收通过。

## 第九十二批：后台验证服务和工作台入口

- CommerceVerificationService 整合固定六阶段轮询与可信审查生产；公开状态只含阶段、进度、版本和固定错误码。报告写入前持久化 UNKNOWN，失败后轮询不自动重跑；报告提交后回复丢失可只读核对既有转换锚点，不重新生成报告或续期。取消 COLLECTED/待审查作业会让其报告不能继续批准。
- 服务启动用 owner-only 目录中的 Linux flock 独占锁；只有持锁服务能把旧 RUNNING 转为 NEEDS_RECONCILIATION。ASGI lifespan 负责启动、取消与释放锁；CLI 增加 --enable-verification，依赖 --enable-reference-environments 和固定 coding 镜像摘要。默认关闭，Windows、未验证版本、无独占锁均拒绝启动；原编程与模型配置保留。
- 两层受鉴权接口提供启动、列表、取消、只读核对；主服务只代理固定命令，连接服务回复必须与共享私有日志一致。不能上传 passed 报告、指定任意 URL 或直接发布。工作台新增六阶段面板与只读自动刷新。验证服务不可用而 BLOCKED 的已完成编码计划可以同事务进入 VERIFYING/创建作业；重复启动用原 request_id 返回同一作业，来源不完整时回滚全部变化。
- 服务首轮 4 passed / 57.53 秒；API/服务/原参考站启动和发布相关 44 passed / 79.15 秒（commerce92-integration.log）。组合首轮 17 passed / 1 failed / 2 warnings：新增代理测试错误使用 fixture 的旧 job.revision，服务正确拒绝，修正为当前持久版本；未放宽生产版本检查。确认回归 19 passed / 2 warnings / 262.05 秒（commerce92-ui-confirm.log），包含桌面/手机真实 Chromium 页面、生成类型、报告事务、伪造响应与丢回复核对。测试中的 Docker/CMS 仍明确模拟；浏览器检查不等于 Linux 或九项实站验收。
- TypeScript 与 Vite 生产构建通过。系统 npm 启动脚本损坏，改用现有 C:/Program Files/nodejs 的 npm-cli.js 构建，无安装新依赖。没有付费模型调用、正式店铺发布、Git 推送或桌面同步。

## 第九十三批：明确续跑预览的未发送步骤

- StagingVerificationStage.resume 必须使用当前版本、原 claim 和仍有效的原 staging grant。先核对持久效果历史；存在未知/待处理 operation 就拒绝，不能借续跑自动核对或重发。已核对部分进度可以事务切回 RUNNING，只发送剩余未启动步骤；失败/取消保留中断栅栏，完成才写阶段回执。不能刷新原许可或操作正式店铺。
- 主服务、连接服务和工作台提供明确续跑动作；只读核对和续跑分开，原授权过期、来源变化、取消或重复旧版本请求会拒绝。涉及网络核对/部署的固定代理命令使用有界 660 秒，不自动重试。
- 缺方法 RED 1 failed / 1.53 秒；阶段 GREEN 5 passed / 77.99 秒（commerce93-green.log）。补充过期/取消与相关整合回归进行中，最终结果以日志为准。空商品/零库存测试商品、实际购买库存行为、第二站完整恢复及最终交付仍待完成；版本锁保持 verified:false，不能将实现进度写作完整验收通过。


第 93 批确认：续跑/后台/API/runtime/启动/生成类型组合 27 passed / 315.52 秒（commerce93-regression.log），包含原许可过期、取消拒绝续跑。验证面板真实 Chromium 1440/768/390 三宽度 3 passed / 2 warnings / 6.24 秒（commerce93-browser.log），明确模拟进度响应；刷新不发送操作，明确核对与取消才发送对应命令。Ruff、TypeScript/Vite 生产构建通过；修正本次写入文件行尾后 git diff --check 通过。

## 第九十四批：签名测试订单的库存保护

- 本地锁定 WooCommerce 代码 wc-stock-functions.php 的 woocommerce_can_reduce_order_stock 确认测试 COD/on-hold 可能触发库存扣减。专属 staging safety guard 保存此前已验证的测试 payload/HMAC，库存过滤器再次验证本作业身份、签名、来源元数据、实际唯一商品/数量与 COD；仅这类 synthetic probe 禁止减库存，不对商家正式站安装，不改变普通预览订单行为。无需后续自动库存补偿写入。
- 缺函数 RED 1 failed / 0.62 秒；签名购买、staging guard、bootstrap PHP 合同组合 20 passed / 1.85 秒（commerce94-stock-green.log）。此处执行真实 PHP 配合固定 Woo API stub，并非完整真实 checkout/库存实测。补充伪造 HMAC 不能免扣库存，待后续合跑。空商品/零库存 disposable 商品仍待实现；不能声称完整商家验收完成。


第 94 批实站补充：增加真实购买后 snapshot.stock_quantity 仍为 3 的断言。第一次因一次性站数据库未运行失败；恢复已有数据库后 HTTP 进程也未运行，随后恢复已有 HTTP 服务。真实购买首次运行成功后测试误读 stock 键而失败，按连接 snapshot 合同改为 stock_quantity；最终 1 passed / 15.91 秒（commerce94-stock-live-final.log），包含真实 Store API signed checkout、独立订单/金额回读、库存保持和只读 reconcile。两个临时 MU 文件已删除，fixture 网关设置已恢复。主机/来源 attestation 在此测试明确模拟，不算 Linux 六阶段或正式店铺验收。

全量回归 commerce94-full.log 在约 53% 时因 C 盘 Free=0 出现大量 fixture 准备错误并停止，不算全套通过；清理本轮 pytest-75/78/79/80 临时目录后约剩 137 MB。E 盘专用 E:/muse-test-temp 写权限已获准；普通沙箱仍 WinError 5，因此按授权隔离目录使用提升执行重跑全量（commerce94-full-e.log），所有 pytest/tempfile 临时数据使用 E 盘新 UUID 子目录，保留代码与日志，结果尚待确认。


第 94 批宿主生命周期与 HMAC 反向补充 14 passed / 1.33 秒（commerce94-lifecycle.log）：持锁期间运行，取消 worker 完成后才释放锁，恢复失败也释放锁；伪造签名的订单保持普通库存扣减语义。新测试不算真实 Linux flock 执行证据。

## 第九十五批进行中：空商品测试 fixture 的独立边界

- 增加 DisposableProductProof/read_disposable_product 固定读取合同，绑定项目、ref 作业连接、确定性 MUSE-PROBE SKU、准确商品 ID，固定隐藏可配送商品、价格 12.50/库存 3/当前币种；严格拒绝错误身份、库存、价格和额外字段。合同本身不授予购买或发布权限，也不进入商家 ProductDraft 审查图。
- 参考站第一次 bootstrap 创建准确隐藏的专用商品；已有 SKU 拒绝，不能重装或重建替换。私有 safety guard 只提供经过服务鉴权的 GET /disposable-product，重新核对实际 WC 商品/元数据。SyntheticBuyer.disposable_product 仅对拥有且 READY 的准确参考站固定安全/商品 GET，并在读取后再次检查目标状态；不会创建 cart、probe、order 或许可。
- 缺模块 RED 13 failed / 0.35 秒；合同 GREEN 13 passed / 0.17 秒。合同/PHP guard/bootstrap 40 passed / 4.93 秒（commerce95-fixture-php.log）；读取与原 sender 32 passed / 2.00 秒（commerce95-reader.log）。PHP 使用准确固定 WC API stub，尚未实际 Linux 初始化验证。固定专用商品尚未接到来源作业、无货购买/浏览器截图及可信报告；目前无货仍保持拒绝通过。接通时必须把测试商品证据单独持久化，不改变商家批准商品或将 fixture 复制到正式站。

第 94 批全量 E 盘结果已确认：2132 passed / 31 skipped / 5 warnings / 846.13 秒（commerce94-full-e.log）。这是第 94 批代码的整仓回归，不覆盖随后第 95 批整合。警告为 websockets 弃用、故意重复 ZIP 条目及 pytest 缓存权限；C 盘耗尽那轮仍是失败历史。

第 95 批整合完成：来源绑定的私有 buyer_fixture_binding 已接入固定购买、浏览器截图和报告 producer。空商品/零库存使用独立隐藏商品验证购买，正式发布图只含商家商品；报告重新读取 fixture 实际来源，篡改商品 ID 拒绝生成报告。预览明确标注“测试商品（不会发布）”。空/零库存和报告组合 5 passed / 62.93 秒（commerce95-empty-report.log）；相关阶段、购买、报告、预览和发布日志组合 100 passed / 453.07 秒（commerce95-regression.log）。模拟 CMS 的能力声明及按 product_id 查找商品修正为正确合同，不放宽生产规则。真实 Linux 初始化和完整六阶段未运行。

## 第九十六批：新安装包与干净环境验证

最新前端生产构建和 wheel 构建成功。离线干净环境首次因 Pillow 无本地缓存而未安装，不算通过；下载公共 PyPI 依赖后，新 E 盘 venv 正常安装并通过 uv pip check。隔离 Python 导入 muse/mewcode、新验证模块、OpenAPI 与默认服务关闭检查通过；33 个前端、连接插件、主题和参考站资源逐文件 SHA256 一致。没有调用模型 API。安装包与证据见 work/commerce96-install.json 和 commerce96-install.log，wheel SHA256 为 d32999ac09e8ea7896c6e2f5266d09e69f5b7263cf8c4a1a47a5758a495b55bc。此安装验证不包含 Docker 宿主可用性或付费模型质量验收。

## 第九十七批：第二项目重新验证与批准

新增端到端合同 test_second_project_verification.py：第一项目导出媒体/准确主题，恢复为无连接/计划/许可的新项目；第二目标刷新上下文后拒绝旧版本商品导入，明确重新确认来源。新计划消费恢复主题并重新捕获封存，运行固定验证链、生成独立报告/审查，第二项目明确新批准可加载，而旧站连接不能加载新许可。整个测试使用明确模拟 Docker/CMS/浏览器，不写真实商家站。

恢复组合最终 15 passed / 1 warning / 27.32 秒（commerce97-restore.log）。新增批准断言最初误用不存在的 grant.plan_id/changeset_digest；按真实 grant.intent_digest 合同修正，不改生产对象。此前单项无批准部分 1 passed / 13.72 秒不是最终整合结果。最新 Commerce/Connector/Commerce tests Ruff 通过；Git 提升身份因仓库拥有者不同，需要显式只读 --git-dir/--work-tree 检查，不改全局 safe.directory。完整回归第 98 批进行中。

## 第九十八批：整仓分批回归与不稳定结果保留

单次整仓 commerce98-full.log 在 45% 后进程消失，没有总结或退出码，不能标记全量通过。依据 collect-only 的全部 2192 个用例划分 5 个互不重复模块批次，清单 work/commerce98-groups.json；每批独立 E 盘 UUID 临时目录并持久 .log.exit。

第 2 批首次为 275 passed / 1 failed / 2 warnings / 38.97 秒：test_site_approval_persists_source_and_idempotent_grant_without_extending_expiry 调用 restarted.start 返回正确 intent，但原连接读到 APPROVED 而非 PUBLISHING。单独审批模块 9 passed / 2.57 秒，原完整批次复跑 276 passed / 2 warnings / 41.78 秒；再用 10 个独立 pytest 进程逐次执行该节点全部通过（commerce98-approval-repeat.log，exit 0）。尚未确定首次状态差异根因，不修改生产规则、不将偶发失败宣称已修复。第一批失败日志后来由相同路径复跑覆盖，准确首轮异常和结果在此保留；最新日志是重跑结果。

其它已完成批次：第 0 批 281 passed / 1 skipped / 3 warnings / 112.18 秒；第 1 批 266 passed / 3 warnings / 220.66 秒；第 4 批原核心等 1080 passed / 3 skipped / 2 warnings / 146.16 秒。第 3 批尚在运行；全部结束前不能写整仓通过。警告包含旧依赖弃用与恶意 ZIP 用例的重复条目，不伪造成产品成功证据。

第 98 批最终确认：第 3 批 258 passed / 27 skipped / 2 warnings / 367.15 秒，全部五批 exit 0。覆盖脚本逐批核对模块不重复、模块集合等于整仓收集集合，逐批 passed+skipped 等于该批原用例数；合计 2161 passed / 31 skipped / 2192 collected（commerce98-coverage.json）。第 2 批首轮异常仍保留为未复现风险；10 次独立节点执行均 exit 0。最新 wheel 无随后生产代码变化，安装资源证据仍有效。最终证据矩阵和运行链自检已更新；不执行 GitHub 推送/模型请求/正式站发布。真正 Linux、付费模型与人工验收仍 NOT_RUN，不能称完整商家版已验收。

## 2026-10-06：真实完整链路与任务目标续接

当前状态以 `full-alignment-continuation-2026-10-06.md` 和 `runtime-acceptance-2026-10-05.md` 为准，以上 Linux/付费模型 NOT_RUN 是旧批次状态。真实 Linux run-14 六阶段、九项独立检查、18/18 发布操作、商品价格/库存/发布状态读回通过，两份测试资源 CLEANED。初始化保留 Woo 自动页面、私有同挂载主题原子部署、最终固定插件/封存主题分别读回已修复；原始失败和超时仍保留。新任务目标从持久根任务提供给角色，未扩大工具权限。

真实建议 3/3、冲突明确选择和歧义追问 2/2 小样本通过；累计实际模型费用上界 0.414043 美元，预算 2 美元。相关回归 44、41、19、28 项组合分别通过（组合有重叠，不能相加）；Ruff 与 Git diff --check 通过。未做 GitHub 推送。生产商家、人工体验及任意环境/第三方插件/多人实时协作仍需另行验收或开发，不能声称整个 Replit 产品等价。

### 同目标建站后上新补齐

run-18 两条业务流程各六阶段/九项独立检查通过；实际建站 18/18、上新 4/4 步，分别读回 12.30 USD/库存4 和 14.50 USD/库存5，均 publish。三个参考作业 CLEANED。角色确定性准备与真实模型小样本分开记录，不混称全程模型驱动实站验收。run-15 脚本误留第一流程 passed=true、run-16 中断、run-17 请求 ID 冲突均保留为失败，不能计入双流程通过。

修复固定初始化器中断恢复与清理，显式受限 tmpfs 覆盖镜像隐式匿名卷；真实未启动辅助容器恢复/清理通过。仅 staging 默认600秒，其余180秒，未知栅栏和原授权有效期不变；上新预发布196.798秒。相关44项和进度3项回归通过，独立复审38项通过（组合重叠）。最新 wheel 内容345文件一致，摘要 ecb245bdfac9b2fc3a61a8686afc7ee9a128281e534beea1bbf30fd9e4c14dc8。没有新增 API 请求、生产写入或 GitHub 推送。
