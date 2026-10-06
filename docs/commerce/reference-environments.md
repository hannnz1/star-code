# 隔离预览站：部署与恢复

> 当前实现状态（2026-10-06）：本文按开发批次保留历史说明，早期“尚未接通”“没有真实 Linux”不是当前状态。六阶段执行器、九项可信报告、发布审查、启动循环和工作台入口均已接通。固定平台的真实 Linux 隔离副本和完整建站测试链路已通过，见 [最新证据](full-alignment-continuation-2026-10-06.md)。生产商家和人工体验未验收，默认版本锁仍为 `verified: false`。

2026-10-05 全部商家模块去重后 1161 个用例通过，包括干净 Windows 一次性 CMS 的 28 项功能测试。旧测试数据库达到 200 页上限时的两项失败已保留，新数据库重跑未修改产品上限。详情和原始证据见 [最新验收记录](acceptance-evidence-2026-10-02.md)。此结果不替代真实 Linux 隔离或正式商家发布验收。

完整本机商家回归可执行：

```powershell
& '.venv\Scripts\python.exe' scripts/commerce/verify_task_board.py --scope merchant
```

此模式按文件名区分全部商家后端及浏览器测试，再检查前端类型、构建和 OpenAPI，保存日志、JUnit、跳过项原因和源码 SHA-256。结果属于本机合同回归；不会生成 Linux 隔离通过证明或真实店铺发布批准。

当前实现提供固定参考站准备、初始化回读、资源清理以及工作台入口；固定购买发送器也已完成真实本地 Store API 测试。后台验证已有持久作业和执行器基础，但尚未接通全部生产检查、九项验收和自动进入商家发布审查，不能作为完整商家版已验收的证明。

## 受信服务前提

- 独立 Linux Connector 服务身份；其私有目录、Docker 权限和 WordPress 凭据不能出现在 Coding 容器或 Agent 工作区挂载中。
- 已存在的 MUSE 运行数据库，与主程序共享经过权限控制的事务数据；Connector 密码文件不共享给主程序。
- 手工验证过兼容性的版本清单：`verified: true`、WordPress/Woo 版本、三个本地 Linux 镜像 digest，以及离线 Woo ZIP 的 `woocommerce_sha256`。现有仓库默认清单仍是 `verified: false`，不会自动改为通过。
- 镜像必须已在本地；服务不执行拉取或下载。参考站仅绑定 loopback，使用独立 internal 网络及新卷，不复制现有商家数据库。
- 私有根目录在 Linux 上归服务身份所有、权限 0700。CMS 密码文件在写入后变为 0444，以便只读挂载供容器内不同 UID 使用；其宿主父目录始终 0700，Coding 容器没有此挂载。连接/签名密钥文件仍 0600。

示例（路径代表运维已准备的文件，不含密钥）：

```bash
python -m muse.commerce_connector \
  --config /opt/muse-private/connector.json \
  --runtime-database /opt/muse-state/runtime.sqlite \
  --versions-lock /opt/muse-private/verified-versions.json \
  --enable-reference-environments \
  --reference-private-directory /opt/muse-private/reference-jobs \
  --woocommerce-archive /opt/muse-assets/woocommerce.zip \
  --reference-port-start 63800 --reference-port-count 4
```

参考站开关默认关闭。Windows、缺少已验证清单或资源文件时拒绝启动此功能。`--enable-publication` 是独立开关；开启参考站不会授予商家发布许可。

## 工作台操作

1. 打开商家项目，在“隔离预览站”预留作业。
2. 点击“开始准备预览站”。服务先持久记录 UNKNOWN，再建立固定资源；检查 WordPress 文件权限和数据库可读就绪后，仅初始化一次。
3. 容器身份、资源 SHA、PHP 安全设置均实际回读成功，才显示“预览站就绪”。显式绑定站点后，在团队面板读取店铺上下文。
4. 失败或丢失回复后先“刷新预览作业”。UNKNOWN 不能重新 provision。
5. 如果安装已存下私有连接，可“只读核验安装结果”恢复 READY；缺少安装回执或身份不一致时不能靠再次安装补救。“只读查询资源”仅查看资源是否存在，不证明站点就绪。
6. 明确勾选删除测试数据后清理。服务先解除本作业已绑定的连接，使旧计划失效；只删除准确属于本作业的资源。未知清理可显式继续核对，不自动重发旧删除。

准备命令目前在受信请求内执行，尚非脱离工作台的后台验证作业；超时后共享数据库保留作业状态。关闭页面不会撤销服务器已发送的安装或清理命令。

## 证据边界

桌面/手机浏览器、请求授权、来源版本、未知结果、PHP 签名订单回读及伪造 Docker inspect 测试已覆盖代码合同。当前没有真实 Linux/Docker 验收环境；模拟 daemon 成功不等于隔离部署成功。

固定 SyntheticBuyer 只访问当前 READY 作业的 loopback staging，匿名购物请求不携带服务身份；完成加购、固定测试配送、COD 下单后，使用私有服务身份独立读取签名绑定的订单。实际商品小计、币种、配送、税额和总额必须匹配冻结购买事实；丢失下单回复只允许显式只读核对，不能重发。Windows 一次性 CMS 已实际通过这些 HTTP 操作，但测试明确模拟了宿主隔离与完整来源授权，因此仍不能作为 Linux 或整个九项验收的证明。

VerificationJobRepository 和 VerificationWorker 目前是私有模块，未接入启动循环或公开 API。固定阶段为参考站、来源捕获、预览部署、购买、浏览器、事实核对；每阶段发送前事务写入独占 claim，中断保持待核对。同一冻结来源不能换 request_id 再创建一个作业。COLLECTED 只表示收齐阶段回执摘要，不代表验收通过，不生成商家批准。

每个验证作业现在可私有绑定一个尚未 provision 的参考站，并保存独占归属；不把站点写入商家项目 environment_refs，不增加项目版本。使用前要求参考站 READY、准确就绪回执、当前代码/媒体来源和未取消作业。StagingSourceRepository 和 PreviewRepository 均识别该私有目标；绑定存在时不能回退到原商家预览站。资源进入清理后拒绝继续授权或读取当前预览。

ReferenceVerificationStage 已接通受信宿主 ReferenceEnvironmentService 的固定资源准备与一次初始化；准备后、安装前再次核对验证作业取消/来源。UNKNOWN 只可明确调用 reconcile，执行只读 verify 后记账，不重新 reserve/provision/install 或轮换凭据。此阶段仍需要真实 Linux 服务；当前成功测试用明确模拟 runner，不能作为真实部署验收。来源捕获等其余生产适配器、启动循环、九项可信报告和 request_review 整合仍待开发。


## 私有验证阶段整合（第 85–87 批）

新增 SourceCaptureStage、StagingVerificationStage、BuyerVerificationStage，均为受信宿主调用的固定适配器，不注册为 Agent 工具或公开 passed 上传接口。

- 来源阶段只解析当前验证作业专属 READY 参考站，固定 GET 页面 slug、SKU、图片 SHA 与 snapshot；加载原项目净化媒体，经原 DockerCodingSession 捕获准确封存主题后保存 v5 staging grant。180 秒总只读预算，取消/来源变化拒绝。回复丢失后只读现有 grant，不重新授权或续期。
- 部署阶段复用 StagingReleasePublisher，逐步发送固定意图并独立核对效果。运行期间取消或未知结果停止；明确 reconcile 仅调用原回执对账，不发送剩余步骤。若对账后仍有未执行步骤，作业保持 NEEDS_RECONCILIATION，显式续跑策略尚待整合。
- 购买阶段复用 SyntheticBuyer 和独立金额回读，将购买证明绑定本作业 source/staging 回执。checkout 回复丢失后仅 GET 核对，缺 probe 不重新下单。无商品或全部零库存时保持 VERIFICATION_UNAVAILABLE，尚未实现单独绑定的 disposable buyer fixture。

这些适配器的集成测试使用明确模拟的 CMS/Docker，不新增真实 Linux 证据。第 88 批已补齐浏览器与事实阶段；后台启动循环、九项可信报告和 request_review 自动整合仍未完成。现有 verified=false 与发布门槛不变。

## 浏览器与事实核对（第 88 批）

ReadbackVerificationStage 是受信宿主的固定阶段，不允许 Agent 上传“检查通过”。浏览器阶段重新回读当前专属预览站、核对部署事实，调用固定 Playwright 捕获七类页面与三种宽度的截图。失败保留诊断，不生成通过回执。事实阶段再次回读，要求来源、部署意图和 snapshot 与已保存的浏览器证据一致；截图之后的价格或资源变化会阻断。

回复丢失后只读取准确作业、阶段和 claim token 对应的持久证据，逐张复核 PNG 哈希及尺寸，不重新打开浏览器。六阶段收齐回执仍只表示 COLLECTED，不表示九项验收通过，也不授予商家发布许可。

本批相关回归 79 项通过，包含损坏截图恢复、失败页面阻断及浏览器之后价格变更。测试的 CMS、浏览器捕获与隔离环境为明确模拟；没有新增真实 Linux、实站端到端或付费模型验收证据。

## 私有后台调度层（第 89 批）

VerificationRuntime 固定装配六种阶段，并核对共享作业、来源和参考服务；每轮为每个 queued 作业推进一个阶段，unknown/取消/COLLECTED 不重新执行。宿主可以使用 stop 事件结束轮询，取消执行中的协程仍保留待核对 claim。显式 recover_interrupted 仅做持久记账，必须由已确认独占服务的宿主在旧进程退出后调用，不在轮询启动时自动运行。

这是私有后台模块，尚未接入正式服务启动配置、公开作业进度和最终九项报告。没有新增公开调用指令或模型工具；现有工作台仍不能通过该模块直接获得正式发布批准。

## 固定九项报告（第 90 批）

TrustedMerchantVerifier 私有模块已经实现报告生成：只消费当前作业的准确 Docker 捕获授权、完整部署日志、已有订单独立回读和准确浏览器证据，重新 GET 核对页面/商品/图片；再读取项目登记的正式目标快照与缺失证据，绑定正式 v4 发布意图。COLLECTED 本身仍不表示通过；缺项、来源变化、取消、过期或损坏截图均拒绝报告。

报告附带私有 provenance，期限沿用原预览授权，最长 30 分钟；重试不续期，时钟回拨也拒绝审批。商家审查服务会再次核对生成器报告的来源、证据字节摘要及有效期。生成器没有写入正式站、批准发布或改变计划为 REVIEW_REQUIRED 的行为；审查状态转换、正式宿主启动与工作台进度仍需整合。

模块验证使用明确模拟的 Linux/Docker、CMS 和浏览器捕获；仓库默认 verified=false 不变，不能以这些测试替代真实部署验收。


### 固定后台验证（默认关闭）

连接服务可另加 `--enable-verification`，必须同时启用 `--enable-reference-environments`，并在已验证 Linux 版本锁的 `images.coding` 填入真实兼容镜像的 `@sha256:` 摘要。现有仓库版本锁仍未完成 Linux 验收，不能只修改 verified 来跳过验证。服务与原参考站共享数据库；私有目录必须由独立服务身份拥有且权限为 0700，代理访问令牌与 CMS 密钥分离。

启动后持有 `verification.lock` 的 OS 锁；另一进程不能并行接管。重启遗留 RUNNING 只进入待核对，不重新部署/下单。工作台团队任务内可启动六阶段验证、查看进度、取消、明确只读核对；部分预览核对成功后可明确继续未发送步骤，原授权过期或仍有未知操作时拒绝。报告生成只进入待审查，正式发布仍需原商家审查/批准流程。未配置服务时返回 VERIFICATION_UNAVAILABLE，不模拟通过。

### 无货时的独立测试商品

全无商品或没有可购库存时，新参考站初始化一次性创建隐藏的 `MUSE-PROBE-<reference job>` 商品，固定价格 12.50、库存 3、使用当前商家币种。它只用于测试配送、购物车、离线 COD 下单和浏览器页面，不加入商家批准商品、不复制到正式站。已有同 SKU 或不符实际元数据即拒绝初始化/验证，不自动修复。

服务只读确认实际商品和独立来源绑定；购买前后核对来源、部署日志和商品 ID。准确签名的本作业测试订单不会扣库存，普通订单仍使用原 WooCommerce 行为。截图单独标记“测试商品（不会发布）”。参考站证据、恢复资料和发布许可分开：恢复到第二项目须重新登记连接、确认商品来源、封存代码、验证及批准。最新验收边界见 acceptance-evidence-2026-10-02.md。
