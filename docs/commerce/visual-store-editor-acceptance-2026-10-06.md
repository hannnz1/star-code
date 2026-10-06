# Crew 可视化商家编辑验收记录

本记录对应 `docs/superpowers/plans/2026-10-06-crew-visual-store-editor-plan.md` 的 A–F。本轮已经实现并测试主要编辑与受审查发布链路，但不能将整份计划标记为全部完成。生产发布及商家人工验收尚未执行。

## 阶段状态

| 阶段 | 已实现 | 仍需完成或验证 |
|---|---|---|
| A | 五种判别区块、最多 20 个区块；版本化保存与幂等；增删、隐藏、排序、样式、撤销重做；项目隔离；冲突保留输入、导出输入及显式读取服务器版本；浏览器后退/同栏目/取消切店保护；慢响应切店专项测试；备份友好的独立版本表；离线导出/恢复图片重新映射 | 人工操作与视觉验收留到开发缺口补齐后 |
| B | 固定 Gutenberg 编译及 Python/PHP 同步白名单；封存设计/图片/代码；非重叠人工代码合并，重叠拒绝；真实隔离站的标题、正文、图片、字体、布局、购买及来源验证；建站 18/18 后连续上新 3/3，保留设计并独立读回 | 合成隔离站通过，不代表生产目标已验收；视觉与品牌文案由商家最后评阅 |
| C | 单 SKU 表单与 CSV 到表单；Decimal 价格、库存、币种及项目媒体校验；新导入版本；本地输入恢复；一级页面导航排序 | 一级分类引用、连接器绑定、事实变更阻断及真实建站读回已实现，见末尾补充；二级导航未开放 |
| D | 无工具局部 AI 建议，前后对比、接受/拒绝、版本检查；接受后可撤销内容再保存新版本；一个请求一次调用；迟到结果不自动应用；费用与用量；真实模型测试 | 第三轮未再出现前轮本地实体店虚构/元叙述，但文案仍泛化，商家首次可接受率尚未评阅 |
| E | 开店清单区分配置与验证；WordPress/WooCommerce 配置页与商家确认页分别提供入口，提示刷新店铺上下文；运费预估及边界；复用独立购买验证、发布审查和 UNKNOWN 读回机制 | Crew 内配送草稿表单及审查后受控写入已实现，真实购物车边界通过，见末尾补充；域名 DNS/TLS、实际支付商户连接没有验收 |
| F | 前端构建、中英文检查、OpenAPI 类型同步；商家回归、浏览器与性能证据；隔离 WordPress 截图；本轮模型用量证据 | 上述缺口完成后再做最终全量验收；人工验收安排最后 |

## 自动测试口径

本次继续开发的整合回归：`work/visual-editor-current-integration.xml`，**61 passed**，231.55 秒。其后新增的当前开店资料检查单独验证为 **17 passed**（`visual-editor-current-setup.xml`）；图片同步与编辑浏览器回归 **6 passed**（`visual-editor-media-sync-final.xml`）；相同页面点击/取消后退/取消切店保护复测 **1 passed**（`visual-editor-same-route.xml`）。这些报告有重叠，不能相加为独立覆盖总数。最终前端构建通过，检查 1,006 条翻译、776 处明确 UI 文案调用。

本次实际修复：浏览器后退/哈希跳转的草稿离开保护；取消切店后恢复选择器；点击当前栏目不丢弃草稿；UNKNOWN 初始化事务回滚不留下额外结构方案；新品沿用主题时阻止过期语言/币种并重新核对付款及政策；上传素材后商品表单和首页编辑器即时更新，不清空表单；图片选择器名称不随选项变化。

最新整合报告 `work/visual-editor-final-focused.xml`：**80 passed / 1 failed**，408.13 秒。失败为第二浏览器尚在懒加载工作台时，测试按 5 秒等待编辑器超时；已修正测试启动等待，使其从现有地址直接等待编辑器加载，不再提前点击导航。浏览器复测 `work/visual-editor-final-browser.xml`：**6 passed**，14.84 秒。另有慢响应跨店测试 `work/visual-editor-late-store-response.xml`：**1 passed**，验证旧店铺迟到响应不会覆盖新店铺。保留原失败报告；没有重新宣称最新整合全量已通过，也没有合并重叠覆盖数字。

首次商家全量回归：**1,220 passed / 3 failed / 28 skipped**，用时 25 分 10 秒。三项失败均是原商品图片上传控件与新增图片选择器标签重复；已改为“选择商品图片”，原三项浏览器复测通过。不能将该首次报告直接写成最终全量通过。

后续修改均以新的针对性回归记录为准，不累加重复执行的用例冒充本轮覆盖数量。Junit 文件位于 `work/visual-editor-*.xml`。最终构建检查了 1,006 条翻译和 776 处明确 UI 文案调用；OpenAPI 类型同步检查通过。

已确认的覆盖包括：设计幂等初始化与保存、陈旧版本/跨店资源拒绝、UNKNOWN 写入阻断、项目版本重绑定、XSS 安全编译、人工代码冲突、设计导出恢复、商品草稿合同、局部提案和过期接受、商品上新保留主题文件的声明检查、运费门槛、保存刷新和双窗口冲突。

性能证据：`work/visual-editor-evidence/latency.json`，20 个区块、30 次编辑与保存，包含 Playwright 开销，排除模型与远程建站。本次最新测量编辑 p95 **11.518ms**、保存 p95 **83.746ms**；目标分别 ≤200ms、≤1,000ms。

## 真实模型测试

本轮授权上限 **USD 2**。沿用现有 `gpt-5.4-mini`，只发送合成测试店铺的选中区块、修改要求及品牌/语言信息，没有发送项目源码或密钥。

三轮共九次调用，首轮费用保守计量 USD 0.001418，补充品牌上下文后的复测 USD 0.001616，补齐区块类型/受众/风格和顾客文案指令后的第三轮 USD 0.001795，累计 **USD 0.004829**。第三轮另设 USD 0.05 限额，属于本轮 USD 2 总授权内。费用是依据返回用量的本地保守估算，以服务商账单为最终依据；不是固定测试价格。

每轮三个案例：首屏文案、品牌介绍、诱导执行命令并发布的恶意要求。两轮各 3/3 返回符合合同的建议；6/6 在接受前不修改设计；工具调用 0；恶意案例没有改变资源路径或执行发布。两个普通案例的程序化接受仅用于验证接受接口，不代表商家批准文案质量。

复测延迟为 2.188s、1.547s、1.609s；输入 1,348 tokens、输出 134 tokens。所有六次合计输入 2,468、输出 262，总计 2,730 tokens。

**质量未通过商家验收。** 首轮品牌介绍没有得到品牌名；已补充品牌上下文。复测保留了品牌名，但首屏仍出现未提供依据的“local pet shop”，品牌介绍包含“a brand name supplied for this section”等元叙述。不能把 3/3 结构合法率写成 100% 文案首次可接受率。

原始证据：`work/design-model-live-20261006/{results,cost}.json`，`work/design-model-live-refined-20261006/{results,cost}.json`。

第三轮证据：`work/design-model-live-customer-copy-20261006/{results,cost}.json`。3/3 合同合法，接受前均未改设计；恶意要求的结果保持原区块不变。普通文案未再出现前轮的本地实体店虚构和编辑过程说明，但品牌介绍仍较泛化，不能算商家已验收。延迟 2.546/1.797/1.547 秒；输入 1,636、输出 126 tokens。九次累计输入 4,104、输出 388，共 4,492 tokens。

## 本次独立代码审查

按计划进行只读代码审查，发现商品保存期间可切换来源、A→B→A 旧保存响应误标新输入、协议相对按钮链接可跨主机，以及 AI 接受后缺少撤销记录。四项均已实现修复，审查复核没有发现新的 Critical/Important 问题；这不替代运行验收。前三项和 AI 撤销均先观察到专项测试失败；PHP 内部链接边界报告 `work/visual-editor-php-link-boundary.xml` 为 **6 passed**。

初次回归 `work/visual-editor-review-fixes.xml` 为 **23 passed / 2 failed**，275.65 秒；失败时初始化 POST 尚未返回，测试过早断言输入框。已改为等待实际初始化响应 200 再检查功能，保留原失败报告。专项复测 **2 passed**（48.41 秒）。最终整合 `work/visual-editor-review-fixes-final.xml` 为 **31 passed**，222.49 秒；覆盖商品保存竞态、AI 撤销与保存新版本、设计隔离和 PHP 链接边界。随后补查 Gutenberg JSON 属性、theme.json 背景资源隐藏链接绕过，先红后修；当前主题/链接/蓝图报告 `work/visual-editor-theme-link-boundary-final.xml` 为 **21 passed**，4.44 秒。测试使用与正式主题相符的无斜杠转义 JSON，不放宽生产反斜杠禁令。两份报告有重叠，不相加为独立测试总数。最终只读复核在本次修改范围内未发现剩余阻塞缺陷。

## WordPress 验收与环境

隔离发行版：`MUSE-Commerce-Test-20261005`，固定版本锁 `/opt/muse-acceptance/candidate.lock.json`。合成商品和一次性 Docker 站点，不使用生产商家账号，不调用付费模型。测试程序使用明确的合成测试授权执行发布，这不能替代商家人工批准。

本轮修复了两类真实环境问题：主题更新后的 WordPress Theme JSON 进程缓存使回执与后续快照不一致；首页改名后旧浏览器检查仍要求默认首页标题。保留严格效果校验，并分别修正缓存失效及按封存设计核对标题、正文、图片字节和字体。

`/opt/muse-acceptance/design-editor-heading-20261006/evidence.json` 记录六阶段及隔离目标发布。六阶段 reference/source_capture/staging/buyer/browser/facts 已通过。最终发布状态以复制到 `work/visual-editor-evidence/wordpress-build-evidence.json` 的最终证据为准。

桌面/手机真实截图：`work/visual-editor-evidence/wordpress-home-1440.png`、`wordpress-home-390.png`。公开浏览器报告 `wordpress-preview-report.json` 带封存来源摘要和每帧摘要。本地结构编辑截图 `editor-1440-zh.png`、`editor-360.png` 与真实站截图明确分开。

连续流程复测证据 `work/visual-editor-evidence/wordpress-build-launch-rerun.json`：建站六阶段全部通过，发布 **18/18 SUCCEEDED**，最终商品事实和主题源码文件摘要读回通过。随后新品上线在 `source_capture` 阶段进入 **NEEDS_RECONCILIATION**；整体 `passed=false`。这不是已通过的“建站→新品上线”闭环。最新诊断复测使用 `/opt/muse-acceptance/design-editor-launch-diagnosed-20261006`，尚未完成；只有公开异常类型、代码、函数位置会进入诊断证据，凭据不会写入公开报告。

已复现源捕获失败：独立完整预览复制了新品计划的 `retain_existing_theme` 限制，与预览 `build_site` 的主题安装要求冲突。初步通过的 34 项回归没有发现移除标记会改变真正封存来源的内容摘要；真实复测再次报 REVIEW_STALE。现已加强用例，创建包含该标记的真实封存源码包，保持整个蓝图和内容摘要不变；主题保留检查只作用于商家 `launch_products` 图，独立预览仍完整安装原封存主题。相关报告为 `work/visual-editor-sealed-preview-retention.xml`。

最新已结束连续验收 `work/visual-editor-evidence/wordpress-build-launch-sealed.json`：建站六阶段及 **18/18 发布 SUCCEEDED**，最终商品事实、设计源码读回通过；上新 source_capture、staging、buyer 均通过，随后 browser 阶段失败，状态 **NEEDS_RECONCILIATION**、异常类型 ValueError；整体 `passed=false`。上轮三个一次性目标均确认 **CLEANED**。没有上新发布成功证据，不能宣称闭环完成。

诊断续测 `/opt/muse-acceptance/design-editor-launch-observable-20261006` 已结束：建站浏览器 21 帧及五项检查通过，但报告阶段失败，整体未通过。诊断包装将对象换为函数，丢失 `evidence/reconcile` 读回接口；这是诊断脚本的新增缺陷，不能当作产品发布失败的原因。现使用保留属性接口的代理，并为报告生成增加安全堆栈位置记录；脚本测试先红后绿，`work/visual-editor-diagnostic-wrapper.xml` 为 **4 passed**。该次两个参考资源均 CLEANED。全新 `/opt/muse-acceptance/design-editor-launch-diagnostic-fixed-20261006` 正在重跑，无付费模型调用，不重试任何生产 UNKNOWN 写入。

本轮另完成 `work/visual-editor-preview-release-regression.xml`：**53 passed**、134.83 秒，覆盖独立读回、预览来源和发布回归。与上述报告重叠，不合并为独立总数。

后续工作台/性能整合 `work/visual-editor-merchant-ui-final.xml` 为 **19 passed / 1 failed**、388.02 秒；900px 用例在登录后商家模块仍加载时按默认 5 秒断言，已将统一 fixture 改为等待已加载工作台，再开始场景。专项复测 `work/visual-editor-ui-startup-recheck.xml` 为 **1 passed**、23.82 秒，保留原失败报告，不宣称这份整合报告全绿。

`wordpress-build-launch-diagnostic-fixed.json` 已结束：参考及来源阶段通过，staging 在 617.737 秒停止，600 秒阶段上限触发取消；6 步效果已验证，第 7 步 NEEDS_RECONCILIATION，两个参考资源 CLEANED，整体未通过。只读性能定位显示一次封存源码读取约 **9.409s**，其中主题文件读取约 **6.498s**；当前程序从 Windows 挂载目录运行。正在准备排除密钥/配置/私有状态的原生 Linux 代码和前端副本，以逐文件 SHA256 清单校验；使用既有验收 virtualenv，不宣称已打包可独立安装的全部依赖。不提高生产超时或重发未知步骤。

原生副本首版遗漏三份商家角色 Markdown 资源，启动明确报 FileNotFoundError，资源已 CLEANED；失败报告 `wordpress-native-missing-roles.json` 保留。扩展名规则和复制测试已补齐。审查另发现目标词法路径可通过父目录链接或 `..` 逃逸；已在任何创建前检查解析后的边界并拒绝父目录链接，新测试先红后绿，`visual-editor-runtime-boundary-final.xml` 为 **6 passed / 2 skipped**（Windows 无符号链接权限）。Linux 实测来源链接、目标父级链接、父目录逃逸均被拒绝，私有 `.env` 未复制，文件摘要一致；审查复核确认该 Important 已关闭。

当前原生副本 `/opt/muse-acceptance/runtime-visual-editor-complete-20261006`：**222 个文件**、3 个角色、主题/连接器资源和前端入口预检通过，逐文件摘要保存于 `work/visual-editor-evidence/linux-runtime-manifest.json`。实际 API 健康检查及前端两项入口资源服务通过；预检 TestClient 必须使用产品已有 loopback 主机限制，不修改安全中间件。相同封存源码在原生读取约 **0.091s**（单次测量，不是整体工作流 p95），对照证据 `source-read-performance.json`。新版完整流程 `/opt/muse-acceptance/design-editor-launch-native-complete-20261006` 正在执行；目前建站六阶段及审查已通过，发布尚未结束，不标记闭环完成。

浏览器草稿保护复测发现取消后退会覆盖上一历史项，使再次后退离开 Crew；已改为按历史位置恢复，整份编辑器回归 **7 passed**、89.71 秒（`visual-editor-history-integrity.xml`），补充前进/取消前进后重试 **1 passed**、19.65 秒（`visual-editor-back-forward-integrity.xml`）。五个屏幕宽度的语言/刷新回归 **5 passed**、112.38 秒（`visual-editor-history-responsive.xml`）。只读审查未发现本轮新阻塞；旧版本或外部无位置标记历史项的恢复方向尚有健壮性限制，留为专项，不能声称所有跨版本历史均已验证。

开店运费预估复现跨店结果残留；请求代次与项目版本检查、切店清空结果已修复。`work/visual-editor-shipping-scope.xml` 为 **3 passed**、24.10 秒，覆盖旧店延迟响应、币种切换和免运边界。这仍是预估工具，不是 Crew 内远程配送配置表单。

本轮原生完整流程最终报告 `work/visual-editor-evidence/wordpress-build-launch-native-protocol-failure.json`：建站六阶段、18/18 发布及设计源码读回通过；新品上线六阶段也全部通过，21 帧及五项浏览器检查均通过。上新正式测试目标在 1/3 发布步骤后返回 **WRITE_OUTCOME_UNKNOWN**，整体未通过，三个一次性资源均 CLEANED。程序没有盲目重发；这不能写成完整旅程成功。

已定位实际发布协议缺陷：Python 保留主题的上新图省略主题安装，而 WordPress v4 校验仍按含安装步骤的旧偏移判断。现使用独立 **v6 retained merchant audience**，只接受上新媒体与商品步骤；旧 v4/v5 行为保持原样。执行器 SKU 身份指纹分支同步支持 v6；审查发现遗漏后增加有图/无图及单商品/双商品的逐步骤生产 PHP 指纹检查，先失败后修复。平台 SKU 读回仍为测试 stub，真实 WordPress 复测不可省略。相关六文件回归 `visual-editor-retained-protocol-final.xml` 为 **92 passed**、57.20 秒；冻结最终测试入口后的协议复测 `visual-editor-retained-wire-final.xml` 为 **46 passed**、34.21 秒。报告覆盖重叠，不相加。只读审查确认 Important 已关闭，未发现其余相关版本白名单遗漏。

工作台复测曾出现蓝图用例拦截晚于概览预取的问题；测试现在在全新加载前安装延迟路由，仍断言加载时按钮禁用，未放宽产品验证。最新工作台与性能整合 `work/visual-editor-evidence/visual-editor-merchant-ui-fixed.xml` 为 **20 passed**、55.01 秒。下一轮原生副本及真实连续旅程正在准备，当前仍不宣称所有 A–F 完成。

### 最新已完成连续旅程

`work/visual-editor-evidence/wordpress-build-launch-retained-v6-final.json` 的整体 **passed=true**：

| 流程 | 六阶段独立验证 | 发布步骤 | 最终商品事实 | 设计源码读回 |
|---|---|---|---|---|
| 建站 | 全部通过 | 18/18 SUCCEEDED | 通过 | 通过 |
| 新品上线 | 全部通过 | 3/3 SUCCEEDED | 通过 | 通过，launch_retains_design=true |

两轮浏览器分别 **21 帧**，页面、三种屏幕尺寸与链接五项检查均通过；三个一次性资源均 CLEANED。没有新付费模型调用。该报告使用明确合成测试授权，**human_acceptance=false / production_verified=false**。v6 修复后的 Python/连接器资源一同来自 `/opt/muse-acceptance/runtime-visual-editor-retained-v6-final-20261006`，222 文件摘要保存在 `linux-runtime-retained-v6-manifest.json`；仍使用既有验收 virtualenv，不是可独立安装的完整发行包。

验证过 SHA256 与 PNG 尺寸的首页截图和索引位于 `work/visual-editor-evidence/wordpress-retained-v6-screenshots/`：1/2 为建站的桌面/手机，3/4 为上新预览的桌面/手机。它们是合成内容与色块素材的**功能证据**，不是 AUD 宠物店成品或品牌视觉验收。

设计/商品/提案/开店/浏览器与复制边界整合报告 `visual-editor-final-contracts.xml` 为 **30 passed / 2 skipped**、215.97 秒，跳过项为 Windows 符号链接权限，Linux 边界证据仍单独保留。补查旧蓝图请求切店场景已通过；现有组件按店铺重建已有效防止旧响应写入新店，不新增猜测性修复。商家全量报告已结束：`work/visual-editor-evidence/visual-editor-full-commerce-final.xml` 为 **1,262 passed / 2 failed / 30 skipped**，2,894.67 秒；保留失败报告，不标记最终全量通过。运行期间另补了单独验收的开店指引，不能称该报告覆盖之后的全部修改。

### 开店配置指引与保存同步补充

商品浏览器复测先出现 **6 passed / 1 failed**：保存按钮已显示忙碌，但测试的 `route.fetch()` 尚未完成，断言过早。测试改为等待拦截响应就绪，继续保持响应挂起并验证来源选择禁用；最终 `product-save-synchronization.xml` 为 **4 passed**、77.24 秒，没有放宽商品保存逻辑。

配送和支付现在分别提供“打开店铺配置”和“确认店铺配置”，后者指向连接器已有的商家确认页面。提示配置后刷新上下文，且不能将商家确认当作购买验证或发布批准。`readiness-configuration-guidance.xml` 为 **13 passed**、33.42 秒，含已有连接器检查、中英文链接文案、1440/390px 无横向溢出；截图位于 `readiness-guidance/`。这批新 UI 测试不替代真实管理员配置、确认、再刷新上下文的操作验收，也没有新增远程运费写入接口。

前端构建通过：1,008 条翻译、778 处明确 UI 文案调用；OpenAPI 类型同步检查通过。只读审查未发现新 Critical/Important 问题。本地 API 预览已重新加载新接口，首页 HTTP 200；没有启动通用任务 worker，没有新增付费调用。

全量另一项失败发生在切店后的 CSV 图片引用：测试只等待店名，未等待异步图片列表及勾选完成，预期第二次导入没有保存。原测试没有记录拦截响应状态，不能将其进一步断言为特定 HTTP 错误。场景现在等待 `使用图片 cup.png` 已勾选，同时明确断言拦截 POST 返回 201；商家/商品两个文件复测 `commerce-product-browser-synchronized.xml` 为 **7 passed**、140.88 秒。增加慢图片读取用例后复现保存按钮仍可点击的交互缺口，已将读取/上传忙碌状态传回 CSV 表单，同时在按钮和保存处理器阻止提前提交。最终 `commerce-media-final-browser.xml` 为 **8 passed**、157.90 秒，覆盖慢读取、三个屏幕宽度原流程和商品表单。最终构建及 OpenAPI 同步通过，本地实际服务入口为 `index-BSEJ6o6j.js`。

这轮全量的 30 项跳过分别为 **28 项需显式一次性 WordPress fixture**、**2 项宿主不能创建符号链接**；真实 Linux 连续旅程与边界证据另行列出，不把跳过计为通过。代码审查未发现 CSV 忙碌保护的新 Critical/Important；Minor 限制：图片读取失败后显示错误，图片引用仍由后端拒绝，重试读取需要刷新或重新进入店铺。

## 使用及人工验收

本轮本地 UI 预览：`http://127.0.0.1:8876/`。进入商家工作台，选择店铺 → 网站 → 准备编辑草稿 → 编辑/保存。产品页的单商品表单保存后形成新的商家导入来源，保存本身不会上架。

该预览只启动 API，不启动可消费任意既有模型队列的通用 worker。真实 AI 测试用私有、指定 job 的测试器完成。正常使用可按原项目启动脚本启动 worker；用户主动任务的后续 API 费用不属于本次已完成的测试计量。

最终人工项：首次使用理解、宠物店品牌和文案、桌面及手机操作、实际商品/政策/配送准确性、正式商家目标及发布决定。均为 **NOT_RUN**，留到开发缺口补齐后交由用户验收。

## 分类导航与配送表单补充

2026-10-06 后续实现已补齐一级分类导航、Crew 内配送草稿表单、精确报价及审查发布链路。历史未完成和失败记录保留，最新范围与证据以 [分类与配送验收](navigation-shipping-acceptance-2026-10-06.md) 为准；连续上新复测仍在记录中。
