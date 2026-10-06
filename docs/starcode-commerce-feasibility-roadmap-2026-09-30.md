# StarCode Commerce 可行性与开发路线图（2026-09-30）

依据：用户提供的升级规格书 `E:/2026-09-29-starcode-commerce-upgrade-spec.md` 及当前 Python MUSE 工作树。本文是规划和代码基线审阅，不代表 Commerce 功能已实现或 Shopify 开发店已验证。

## 判断

**方向可行，但这是新电商产品层，不是对现有 Coding Agent 的小幅功能升级。** 现有 Python Runtime 可复用任务、工具、事件、审批和隔离工作树；Shopify 应用身份、Commerce 领域模型、确定性能力路由、商家审批及安全发布闭环需新建。先完成一条开发店 Campaign 竖切，再扩到上新、组件和 Coding Mode。生产多商家版本还需要应用分发、安全存储、运营与平台审核。

不沿用规格书的“25–35% readiness”作当前实测百分比：那是未审最新代码时的产品层估算，缺少统一分母。当前可复用和缺口应按下面的证据与验收门槛判断。

## M0：已核对的代码基线

| 范围 | 现有证据 | Commerce 含义 |
| --- | --- | --- |
| Python 服务与 Worker | `src/muse/main.py`、`src/muse/tasks/worker.py`、`src/muse/agent/loop.py` | 可以承载持久任务与 Coding Bridge；不重写 Agent Loop |
| 任务与事件 | `src/muse/tasks/repository.py` 的 SQLite 任务/事件；`src/muse/main.py` 的 `/api/tasks` 和 SSE，按 sequence 继续读取 | 可复用任务审计与断线查看；Commerce 操作需独立状态、幂等键和对账 |
| 审批 | `src/muse/tasks/repository.py` 的一次工具审批；`frontend/src/main.tsx` 显示技术动作 | 不足以让商家批准含店铺、快照、代码版本和操作列表的业务 ChangeSet |
| 成果与文件恢复 | `src/muse/artifacts/service.py`、`src/muse/main.py` 成果/文件历史接口 | 可保存报告和 Diff 证据；缺少带 Commerce revision 的 Preview/Verification 契约 |
| 权限与执行 | `src/muse/permissions/`、`src/muse/extensions/worktrees.py` | 可限制文件工具与子工作区；不能据此声称 Shell 与 Shopify Token 已隔离，Windows OS 沙箱仍不支持 |
| 网页与身份 | React 工作台 `frontend/src/main.tsx`；`src/muse/main.py` 使用共享本地 Bearer Token，API 默认回环地址 | 现有登录不表示 Shopify 商家身份或多店铺租户授权；需重做 Commerce 身份边界 |
| Shopify 领域 | `src/muse/` 与 `frontend/src/` 未见 Commerce/Shopify 模块或路由 | StoreConnection、Adapter、Router、ChangeSet、Publish Orchestrator 均为新增 |

基线补充检查：在开发开始时冻结 Git 提交、完整自动回归、接口契约、开发店资格和模型配置；不要把此前 MUSE 1075 项本机回归等同 Commerce 验收。

## 平台可行性与规格修正

1. **认证与分发先定路线。** Shopify Admin API 要求已安装应用的 Token 与获批 scopes。CLI 模板可处理常见认证流程；嵌入式应用通常走 token exchange，外部独立应用走 authorization code grant。若目标是多个独立商家，需选公共分发并完成 Shopify 审核；自定义分发主要服务单店、同 Plus 组织或受限开发店。不能把目前的本地共享令牌直接暴露给商家。[Shopify 认证](https://shopify.dev/docs/apps/build/authentication-authorization)、[分发](https://shopify.dev/docs/apps/launch/distribution)
2. **主题路线现实，但不是任意位置自动放置。** Theme App Extensions 支持与 Online Store 2.0 主题集成，商家可在 Theme Editor 添加和配置 App Blocks。产品需显示主题兼容性和需商家手动激活的步骤，不能承诺所有主题/页面一键应用。[Theme App Extensions](https://shopify.dev/docs/apps/build/online-store/theme-app-extensions)
3. **任意主题写入仍受限。** `themeFilesUpsert` 需要 `write_themes` 和 Shopify exemption，且操作可异步。V1 默认只修改自有 Extension 工程，不把“AI 直接改 live theme”列为可用发布路径。[themeFilesUpsert](https://shopify.dev/docs/api/admin-graphql/latest/mutations/themeFilesUpsert)
4. **商品上新有隐藏破坏性。** `productSet` 的 list 字段具有同步语义：输入缺失的现有 collections、metafields、variants 项可能被删除。Adapter 必须只在完整快照和明确映射后使用它，或改用更窄的 mutation；发布前展示精确 Diff。[productSet](https://shopify.dev/docs/api/admin-graphql/latest/mutations/productSet)
5. **Flow 放后续。** Shopify Flow 已提供 trigger/action 扩展；V1 没必要重造任意持久自动化。计划中的自定义 App 类型和目标商家套餐还影响可用性。[Flow](https://shopify.dev/docs/apps/build/flow)
6. **接口语言改为 Python。** 规格中的 Java `CommerceCodingPort` 是概念接口，落地应是 Python Protocol/服务，调用现有持久化任务与隔离工作区。Commerce Service 单独持有 Shopify Token；Coding 子任务只拿脱敏快照和代码工程。由于目前 Windows 没有 OS 沙箱，Shell 与 Token 的隔离不能只靠“Agent 不提示 Token”，需隔离进程/部署身份、环境变量和网络出口，实测越权失败后才启用 CODE 路径。
7. **审批身份要独立于技术审批。** 商家批准的是绑定 store、ChangeSet 哈希、资源版本、代码 revision、验证结果与到期时间的业务动作。技术工具审批仍保留，但不能代替 Commerce 发布批准。

## 建议范围与顺序

首个可演示版本限定：**一间 Shopify 开发店、一个受控 Campaign 场景、原生百分比/固定金额优惠、已支持的 Banner、人工批准后发布**。先不承诺自动主题注入、复杂买赠、批量新品、任意商店改版或正式多商家托管。这样既能证明 CONFIG 优先，也能把每次 live 写入的证据链跑通。

| 阶段 | 交付与主要实现位置 | 放行标准 / 依赖 |
| --- | --- | --- |
| G0 基线与决定 | 冻结 MUSE HEAD、接口与自动测试；选定 Shopify 开发店、App 分发/认证方式、API 固定版本、主题与最小 scopes；`docs/` 记录 | 形成文件级复用/新增清单；开发店和安装方式可执行；不写店铺 |
| G1 通用审查边界 | `src/muse/main.py`、`repository.py`、`frontend/` 增加可复用业务审查入口、revision 绑定 Diff/验证/Preview 状态；不改变原编程任务语义 | 代码或配置变更使旧验证/预览失效；断线重连事件不丢失，重连不重复动作 |
| G2 Shopify 只读接入 | 新建 `src/muse/commerce/shopify/` 与连接表；安全安装/撤销、scope 查询、限流客户端、产品/集合/优惠/主题只读摘要 | 开发店身份和 scopes 正确；令牌不进日志/前端/模型；无写操作 |
| G3 Domain 与确定性 Router | 新建 `commerce/models.py`、`capabilities.py`、`router.py`、`planner.py`；定义 StoreSnapshot、CommerceTask、Plan、ChangeSet 及 CONFIG/COMPOSE/CODE/UNSUPPORTED/NEEDS_INPUT | 固定 30 条需求路由稳定；缺 scope/主题不兼容/结账能力不足明确拒绝或询问，不靠模型自行放行 |
| G4 安全发布内核 | 新建 `commerce/changesets.py`、`verification.py`、`publisher.py`、`reconcile.py`；后端审批 digest、幂等键、逐步回执、冲突与未知结果对账 | 未批准零写入；重复点击不重复创建；超时先对账；部分成功显示 PARTIAL；资源变更使审批失效 |
| G5 Campaign 首条竖切 | 语义化 Discount Preview/Apply、商家 Review UI；先只做 CONFIG 路径 | 开发店实现 Prompt→Plan→Review→Approve→Create Discount→Verify；模型没有直接 GraphQL/发布权限 |
| G6 组件与完整 Demo A | Shopify CLI 管理的 Theme App Extension；首个 Banner block、catalog、商家激活指引与 Preview | 店铺主题兼容、桌面/移动基础检查通过；商家能完成优惠+Banner，未激活时不宣称已上线 |
| G7 上新 | 受限 CSV/结构化导入、重复识别、Draft→Review→Active、集合映射；后续按需加入图片批处理 | 5 件固定 fixture 逐条对账；歧义求确认；图片或部分 mutation 失败报 PARTIAL |
| G8 Coding Bridge | `commerce/coding.py` 将业务验收条件映射到现有任务/worktree；只修改自有 Extension；隔离运行身份；build/theme-check/行为测试绑定 revision | 未通过验证不能发布；修改后旧预览/审批 STALE；越权读 Token/访问 Shopify API 实测被阻断 |
| G9 Automation 与生产化 | Flow 方案或有限受控任务；Webhook/卸载、加密存储、托管身份、审计、备份、API 版本升级测试和应用分发 | 无人工批准不激活；满足相应 Shopify 分发/审核和独立环境安全验收 |

依赖关键路径：`G0 → G1/G2 → G3 → G4 → G5 → G6` 才算完整 Campaign Demo A；`G7` 与 `G8` 在发布内核稳定后开展。原规格把 Campaign 的 Publish 放在 M4、完整 Safe Publish 放在 M8，容易出现过早写店铺；这里把发布内核提前到 G4。产品上新与 Coding Mode 可在 G6 后按目标优先级交换，二者都不能绕过 G4。

## 测试与投入控制

- 单元与合同测试：Router 30 固定需求；缺 scope；GraphQL `userErrors`；`productSet` list-field 保护；审批过期/资源版本变化；重复提交；未知结果；商家身份与店铺隔离。
- 集成：Shopify 开发店只读接入先行；写入测试仅在审批过的测试资源上运行，记录请求 ID、资源 ID、前后状态和恢复步骤。
- 发布候选：规格 C01–C25 全部逐项留证；Demo A/B/C 分开标注。没有 Theme App Extension 商家激活或 G8 隔离证据时，不声称三个 Demo 全完成。
- 真实模型仅负责意图和方案候选；确定性 Router、审批及 Apply 在服务端。保留当前 MUSE 评测模型与预算配置，不把历史 benchmark 分数移植到 Commerce。
- 工作量以依赖和范围为准：G0 小，G1/G2/G3 中，G4/G6/G7 大，G8 中到大，G9 大。实际日程需在 G0 确认 Shopify 开发店/App 身份、所需组件和托管方式后估算；当前不以无依据的“几周完成”作承诺。

## 开工前待定输入

1. 是否已有可用的 Shopify 开发店、Partner/Dev Dashboard 应用及 Online Store 2.0 主题？没有时先用离线 Adapter mock 做 G1/G3，真实 G2/G5 不能验收。
2. 目标是单商家定制安装，还是最终面向多个独立商家分发？这决定认证、分发与托管路线；选择前不要把 Demo 凭据模型做成生产身份模型。
3. 首条 Campaign 是“折扣+Banner”，还是只证明折扣发布？推荐前者作为 Demo A，先实现 G5 折扣竖切再补 G6。
4. 能否提供独立的开发/预览店铺和无需客户数据的测试商品？真实 Shopify 写入只用于这些经确认的测试资源。

未提供上述输入时，G0、G1、G3 的离线合同、Router 与 Review 设计仍可推进；所有真实 Shopify 连接与发布验收保持 NOT_RUN。
