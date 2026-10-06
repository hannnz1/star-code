# MUSE WordPress 商家团队首版 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. 如用户明确选择子 Agent 执行，可改用 superpowers:subagent-driven-development。复选框仅记录后续开发状态，当前全部未执行。

2026-10-01 接口修订：按设计规格 v1.2，P3 增加第八类 `create_owned_page`，以及固定 SKU/page-slug 只读不存在证明；详见 development-ledger 第九批的 Ruling。以下阶段并非均已完成，已实现和测试证据以 ledger/checkpoint 为准。Windows 实站功能测试不得替代 P6 Linux 隔离或 P10 完整业务验收。

**Goal:** 在 WordPress + WooCommerce 上，用店长、网站开发、商品内容三个角色完成“建站”和“新品上线”两条可预览、可审查、可验证的完整流程。

**Architecture:** 新增 Commerce 项目与确定性工作流，复用现有 Python Runtime、任务/事件/预算、角色、worktree 和成果服务。采用自有原生区块主题与固定 Connector Plugin，由隔离发布服务连接 staging/live；生产写入依赖版本绑定的商家批准。

**Tech Stack:** 既有 Python >=3.12、FastAPI、Pydantic 2、SQLAlchemy 2、SQLite、httpx、Playwright、React/TypeScript/Vite、pytest；新增 WordPress/WooCommerce、原生区块主题、固定 PHP Connector、Linux Docker Compose、WP-CLI。版本在 P0 锁定。

**Spec:** `docs/superpowers/specs/2026-09-30-muse-commerce-mvp-design.md`。

**版本:** 1.1｜2026-09-30；本版补齐统一错误协议、分阶段自检与放行，产品实现仍未开始。

## Global Constraints

- 首版仅 WordPress + WooCommerce；单商家、一个逻辑店铺及独立 staging/live。
- 建站采用自有原生区块主题，不采用 Elementor、不重做可视化编辑器、不增加 headless 第二套方案。
- 7 类页面；单语言/币种、实体简单商品；每批最多 20 件；PNG/JPEG/WebP 每文件 10 MiB、每商品 5 张。
- MUSE 核心保持 Python；既有模型配置/凭据不变；原编程入口无需店铺即可用。
- 商家批准有效期 30 分钟，绑定目标、代码/内容、触及资源、验证结果；变更后旧批准失效。
- Agent 自动发布限静态区块模板/样式/结构化内容；不允许生成 PHP、任意 JS 或插件进入首版发布包。
- 只对 Linux Docker Compose 环境做部署支持承诺；Windows 本地不作为真实 OS 隔离证明。
- 不复制 staging 整库到 live，不修改订单；未知结果先对账；人工/外部环境验收保持 NOT_RUN，直到产生证据。
- 错误码、恢复与重试遵循 Spec §7.1；取消只阻止后续动作，已发出的远端请求须对账。

## Review Focus

1. 商家在 WordPress 原生编辑器修改模板/global styles 后，读取实际有效内容并阻止旧代码覆盖（P2/P5/P7）。
2. 同 SKU、大小写/空格、错误货币、空字段、CSV 单元格公式及重复图片导致误上新，导入须规范化、明确拒绝且不修改价格（P8）。
3. HTTP 超时但远端已经成功、进程重启及重复点击，发布必须按 operation_id 回执恢复（P3/P7）。
4. 预览 URL、图片、ZIP 路径、重定向指向越界文件或目标主机，拒绝越界，不让模型借连接器读取凭据（P2/P3/P6）。
5. 店长取消时子任务仍运行、发布前资源变化及 live 新订单，阻止后续动作且保留订单/库存（P4/P7/P10）。

---

## 0. 本地代码基线和复用清单

2026-09-30 只读检查：`muse-integration`，HEAD `4aec15a`；当前已有未跟踪 Shopify 研究文档，保留。本次未运行产品测试、未调用模型、未连接店铺。

| 现有文件 | 复用方式 / 新增缺口 |
|---|---|
| `src/muse/contracts.py` | 保留 scenario/任务权限语义；Commerce 模型放新模块，按 ID 关联任务 |
| `src/muse/tasks/repository.py`、`worker.py` | 复用租约、恢复、事件；新增 Commerce 工作流步骤与回执，不再造 Agent 循环 |
| `src/muse/tasks/delegation.py`、`teams.py` | 复用委派/预算/团队看板；绑定业务依赖及成果哈希 |
| `src/muse/extensions/roles.py`、`worktrees.py` | 复用角色/来源快照及隔离工程；编程 OS 隔离仍需 Linux 实测 |
| `src/muse/artifacts/service.py` | 复用产物存储；新增业务语义、revision 与项目关联 |
| `src/muse/storage/database.py` | 当前 schema 10；在 P1 集中引入 schema 11，延续备份/integrity/audit，不修改旧数据 |
| `src/muse/main.py`、`public_contracts.py` | 挂载 `/api/commerce` router，扩公开业务 DTO；不取消本地 Host/Origin/Token 边界 |
| `frontend/src/main.tsx` | 当前通用任务 UI；新建 Commerce 页面组件，保留原有模式和直接编程入口 |
| `docs/muse-upgrade-status-2026-09-28.md` | 历史记录 1075 passed；不是本轮测试结果，原人工/平台门槛仍独立保留 |

## 1. 文件与接口分工

所有下列路径相对 `outputs/muse-next`；每个目录包含标准 `__init__.py`（PHP/前端除外）。

| 新增目录/模块 | 职责 |
|---|---|
| `src/muse/commerce/models.py`, `repository.py`, `api.py` | 项目、上下文、工作流、成果、审查 DTO 和持久 API |
| `commerce/platforms/base.py`, `wordpress.py` | 不持密钥的 Connector 客户端；平台能力映射 |
| `commerce/context.py`, `planning.py`, `orchestration.py`, `tools.py` | 快照、结构化规划、三角色调度、业务草稿工具 |
| `commerce/site.py`, `coding.py`, `products.py`, `verification.py` | 主题/页面方案、编程任务桥、商品导入、验证 |
| `commerce/changesets.py`, `approval.py`, `publishing.py`, `export.py` | 变更哈希、业务批准、发布请求/对账、可迁移导出 |
| `src/muse/commerce_connector/` | 独立 Python 服务：secret_store.py、api.py、wordpress.py、publisher.py；仅此服务持有远端凭据 |
| `wordpress/muse-connector/` | 固定 PHP 插件：入口、权限、快照、操作与回执、固定主题部署器 |
| `wordpress/muse-storefront/` | 自有区块主题：theme.json、templates、parts、assets；固定 PHP 文件只由产品开发维护 |
| `deploy/commerce/`, `scripts/commerce/` | Compose、受控预置、隔离策略、版本锁、正式部署指南 |
| `frontend/src/commerce/` | 项目首页、向导、单入口会话、团队进度、审查和成果 |
| `tests/muse/commerce/`, `tests/wordpress/`, `benchmarks/commerce/` | 离线合同、真实 WP/PHP、浏览器、真实模型与人工验收 |

### 共享模型（P1 完整定义，后续只引用）

- `StoreProject(id, workspace_id, platform='wordpress', revision, brand, environment_refs)`；environment refs 只有连接 ID/公开 URL，无秘密。
- `StoreSnapshot(project_id, environment, resource_fingerprints, settings, pages, products, theme_identity)`；仅必要商品/页面/配置，排除订单与客户资料。
- `SiteBrief(brand_name, language, currency, audience, style, merchant_supplied_policies)`。
- `SiteBlueprint(pages, navigation, design_tokens, required_settings)`；页面种类限定上述 7 类。
- `ProductDraft(sku, title, price: Decimal, currency, stock: int, description, source_facts, media_refs)`；不使用 float 计算价格。
- `CommercePlan(id, project_id, kind: 'build_site'|'launch_products', revision, snapshot_hash, blueprint, products, code_revision, content_hash, steps)`。
- `CommerceStep(id, role, dependencies, task_id, status, output_hash)`；角色值只有三个首版 ID。
- `ChangeSet(id, plan_id, project_id, environment, operations, resource_preconditions, package_hash, content_hash, digest)`。
- `ChangeOperation(operation_id, kind, resource_key, expected_fingerprint, payload)`；仅操作类型枚举，禁止 raw SQL/Shell/任意 API URL。
- `VerificationReport(id, changeset_digest, code_revision, snapshot_hash, passed, checks, evidence_refs)`；检查含 PASS/FAIL/BLOCKED。
- `PublishReceipt(id, changeset_digest, state, operation_receipts, next_action)`；state 包含 SUCCEEDED/PARTIAL/NEEDS_RECONCILIATION/FAILED/STALE。
- `EnvironmentRef(id, project_id, environment, public_url, connector_ref)`；environment 只有 staging/live/live-test，reference 不含凭据。
- `PlatformCapabilities(wordpress_version, woocommerce_version, theme_id, supported_operations, missing_requirements)`；不满足锁定清单不得自动发布。
- `SitePackage(code_revision, files_manifest, package_sha256, immutable_code_sha256, content_sha256)`；files_manifest 项为 path/sha256/bytes，不能省略不可变代码检查。
- `PreviewRef(id, plan_id, environment_ref, url, code_revision, content_sha256, snapshot_hash)`；只能指向本项目 staging，修改后旧 PreviewRef 失效。
- `ApprovalGrant(id, changeset_digest, project_id, environment, resource_preconditions, verification_hash, expires_at, status)`；status 为 approved/revoked/consumed；后端批准与隔离连接器校验，不使用前端自报批准。
- `MediaInput(name, mime_type, sha256, byte_size, artifact_ref)`；原图字节存在成果存储，连接器按 artifact_ref 获取已校验上传，不接受任意 URL。
- `ProductImportResult(drafts: list[ProductDraft], errors: list[ImportIssue])`；`ImportIssue(row, field, code, message)`，errors 非空时不生成可发布计划。
- `ExportManifest(project_id, revision, files_manifest, required_versions)`；相对路径/哈希/大小，不含任何服务身份。
- CommercePlan 业务状态为 NEEDS_INPUT/PLANNING/BUILDING/VERIFYING/REVIEW_REQUIRED/APPROVED/PUBLISHING/SUCCEEDED/PARTIAL/NEEDS_RECONCILIATION/STALE/BLOCKED/FAILED/CANCELLED；独立于已有 TaskStatus，不给原任务枚举混入业务状态。
- `CommerceError(code, message, field_errors, retryable, next_action, project_id, plan_id, operation_id)`；code 固定采用 Spec §7.1 枚举；ID 未创建时为 null；不得返回原始远端鉴权或未脱敏错误。

## 2. 实施任务

命令约定：当前 Windows 会话的 PATH 无 `python`，本机实际可用的是 `.\.venv\Scripts\python.exe`。下文 `python -m ...` 在 Windows 执行时使用此完整可执行路径；Linux 使用已安装本项目及 dev 依赖的 `.venv/bin/python`。Windows 前端使用 `npm.cmd`，Linux 使用 `npm`。本次文档检查已用现有 venv 运行成功，不新增产品依赖。

### P0：冻结基线和 WordPress 参考环境（2–3 人日）

**Files:** 创建 `deploy/commerce/compose.yaml`, `deploy/commerce/versions.lock.json`, `scripts/commerce/bootstrap.py`, `docs/commerce/environment.md`；测试 `tests/muse/commerce/test_environment_manifest.py`。

**Interfaces:** `bootstrap_environment(project_id: str, environment: Literal['staging','live-test']) -> EnvironmentRef`；只接受固定 Compose 服务，不接受任意容器参数。

- [ ] 写测试 `test_manifest_has_no_latest_and_separate_databases`：所有镜像有 digest，staging/live-test 的数据库/卷独立；测试环境默认禁邮件/支付真实请求且不被搜索引擎索引。
- [ ] `python -m pytest tests/muse/commerce/test_environment_manifest.py -q`，先见真实缺口，再实现锁定清单/预置脚本并通过；选择兼容受支持版本，记录选择理由。
- [ ] 执行 `docker compose -f deploy/commerce/compose.yaml config` 并在独立 Linux 主机创建两套环境；WP-CLI 检查核心、WooCommerce、PHP 版本符合清单，生成无客户资料的 5 商品 fixture。
- [ ] 冻结完整代码提交、运行现有 `python -m pytest -q`，记录本轮真实通过/跳过/失败及现有问题；不套用 1075 的历史计数。
- [ ] 提交本任务涉及的具体文件，建议提交名 `test: freeze commerce reference environment`。

**放行:** 无 Linux/Docker 时只能完成离线清单；真实部署标 BLOCKED，不推进代码发布安全验收。

### P1：商家项目、业务契约和迁移（3–4 人日）

**Files:** 创建 `commerce/models.py`, `repository.py`, `api.py`；修改 `storage/database.py`, `main.py`, `public_contracts.py`；测试 `tests/muse/commerce/test_project_api.py`, `test_commerce_migration.py`。

**Interfaces:** `CommerceRepository.create_project(workspace_id: str, brief: SiteBrief, client_request_id: str) -> StoreProject`；`save_plan(plan: CommercePlan, expected_revision: int) -> CommercePlan`；API `POST/GET /api/commerce/projects`，`GET /api/commerce/projects/{id}`。项目、计划、步骤、快照、审查与发布表在 schema 11 一次定义，后续任务使用，不私自修改结构。

- [ ] 写 `test_project_creation_is_idempotent_and_workspace_bound`：重复 request 返回同 ID，变更内容复用 key 返回 409；未知 workspace 拒绝；项目 B 不能读取 A 的成果。
- [ ] 写 `test_v10_migration_preserves_tasks_memories_and_approvals`：升级备份存在、integrity=ok、旧任务/记忆/批准逐项不变；失败升级不部分写入。
- [ ] 写 `test_commerce_errors_have_stable_public_schema`：错误包含固定 code/恢复动作，ID 未创建为 null；敏感信息不泄漏，业务状态与原 TaskStatus 分开。
- [ ] 运行上述测试确认失败；实现共享模型、schema 11 的正确上限/备份检查和路由；既有 TaskRequest 不增加 Commerce scenario。
- [ ] 运行 `python -m pytest tests/muse/commerce/test_project_api.py tests/muse/commerce/test_commerce_migration.py tests/muse/integration/test_api_contract.py tests/muse/integration/test_migration.py -q`，全部通过。
- [ ] 提交 `feat: add durable commerce projects and contracts`，仅加入本任务文件。

### P2：隔离连接服务、只读店铺上下文（4–6 人日）

**Files:** 创建 `commerce/platforms/base.py`, `wordpress.py`, `context.py`；创建 `commerce_connector/secret_store.py`, `api.py`, `wordpress.py`；创建插件 `muse-connector.php`, `includes/permissions.php`, `snapshot.php`；测试 `test_wordpress_context.py`, `test_connector_boundary.py` 和 `tests/wordpress/test_snapshot.py`。

**Interfaces:** `CommercePlatform.snapshot(project_id: str, environment: str) -> StoreSnapshot`；`capabilities(project_id: str) -> PlatformCapabilities`；`resolve_effective_templates()` 由插件回传 DB 覆盖模板/global styles 的实际结果；业务 API `POST /projects/{id}/connections`、`POST /projects/{id}/refresh-context`。

- [ ] 写测试：页面和价格手动改动改变对应 fingerprint；新订单不改变无关页面 fingerprint；有效模板读取含编辑器 DB 覆盖；页面/商品输入中的提示注入仅作资料、不成为权限。
- [ ] 写测试：连接信息在公开 DTO/日志/模型上下文没有 Token；非允许目标/跨主机重定向/无 HTTPS 的生产连接拒绝；只有已确认 staging 地址可使用开发 HTTP，不能泛化到局域网或 live。
- [ ] 写测试：失效凭据/缺 capability/不支持版本分别生成 Spec 错误码；只读超时最多额外 2 次重试，1/2 秒退避，合法 Retry-After 超过 60 秒或根预算不够时停止自动重试；写客户端零透明重试。
- [ ] 确认测试失败后实现 HTTPS/Application Passwords、服务秘密存储、固定目标解析和只读插件；服务秘密路径仅连接器身份可访问，MUSE 普通 API 只记录引用。
- [ ] `python -m pytest tests/muse/commerce/test_wordpress_context.py tests/muse/commerce/test_connector_boundary.py -q`；在 Linux 运行 `python -m pytest tests/wordpress/test_snapshot.py -q`。未配置真实环境的测试显示 SKIP/NOT_RUN，不能计算为通过。
- [ ] 提交 `feat: connect WordPress store context through isolated service`。

### P3：受限 WordPress 写操作和持久回执（4–6 人日）

**Files:** 创建插件 `includes/operations.php`, `receipts.php`, `theme-deploy.php`；扩 `commerce_connector/publisher.py`, `api.py`；测试 `tests/wordpress/test_operations.py`, `test_receipts.py`，Python `test_operation_contract.py`。

**Interfaces:** 插件 `POST /wp-json/muse/v1/operations` 接受固定 `ChangeOperation` 和后端验证过的执行授权；`GET /wp-json/muse/v1/receipts/{operation_id}` 回读结果。操作枚举：`install_theme_package`, `update_owned_page`, `set_owned_navigation`, `create_product_draft`, `publish_product`, `publish_owned_page`, `set_storefront_options`。

- [ ] 写测试：unauthorized=403、重复 operation_id 相同 payload 返回原回执、不同 payload=409；过期/目标错配授权拒绝；资源指纹不符不写。
- [ ] 写测试：ZIP 中 `../`、绝对路径、符号链接、PHP/JS 变更、非自有主题路径拒绝；固定主题代码哈希不符拒绝；覆盖 DB 模板必须有明确 precondition，不能强行删除商家编辑。
- [ ] 写测试：远端执行成功后响应丢失，GET receipt 能找回，重启后重复调用不新增商品；operation_id 持久唯一并加每资源锁，解释 WP hooks 的非原子副作用。
- [ ] 确认失败后实现 capability 检查、operation ledger 与受限资源写入；不开放任意 wp-cli、SQL、主题目录或插件安装接口。
- [ ] 跑 PHP 语法检查与 `python -m pytest tests/wordpress/test_operations.py tests/wordpress/test_receipts.py tests/muse/commerce/test_operation_contract.py -q`，保留 API 回执和数据库对账。
- [ ] 提交 `feat: add bounded WordPress operations and durable receipts`。

### P4：店长、网站开发、商品内容角色和调度（4–5 人日）

**Files:** 创建 `commerce/planning.py`, `orchestration.py`, `tools.py` 和 `commerce/agents/store_manager.md`, `site_developer.md`, `product_content.md`；修改 `extensions/roles.py`, `tools/registry.py`；测试 `test_commerce_roles.py`, `test_commerce_workflow.py`。

**Interfaces:** `create_workflow(project: StoreProject, kind: str, prompt: str, request_id: str) -> CommercePlan`；`advance(plan_id: str, expected_revision: int) -> CommercePlan`；业务工具 `submit_blueprint`, `submit_product_drafts`, `request_review` 只提交结构化候选；`dispatch_step(plan_id: str, step_id: str) -> TaskRecord` 使用原委派事务及预算。

- [ ] 写测试：店长无 Shell/生产写工具，内容角色无 Shell；角色文件不能扩权；开发角色任务仍为 coding；来源快照和当前 provider 不变；普通编程任务不受 Commerce 限制。
- [ ] 写测试：真实创建两个角色子任务，依赖未完成不得提交后续阶段；同 step 重试仍同 child ID；取消/耗尽共享预算/Worker 重启不重复创建步骤。
- [ ] 写测试：结构化产物最多一次修正且计入预算；模型服务异常没有自动重复付费请求；配额问题 BLOCKED、预算耗尽 FAILED，已有两方成果保留；恢复仍使用原根预算与 provider。
- [ ] 确认失败后实现业务角色固定来源和工具允许列表；复用原 `spawn_task`/worktree/团队看板，店长需要整合两份带哈希成果才可提交审查。
- [ ] `python -m pytest tests/muse/commerce/test_commerce_roles.py tests/muse/commerce/test_commerce_workflow.py tests/test_durable_roles.py tests/test_durable_delegation.py -q`，业务权限和原委派回归均通过。
- [ ] 提交 `feat: orchestrate three commerce roles on existing runtime`。

### P5：自有主题、结构化建站与 staging（5–7 人日）

**Files:** 创建 `wordpress/muse-storefront/{style.css,theme.json,functions.php,templates/,parts/,assets/}`，`commerce/site.py`；创建 `tests/muse/commerce/test_site_blueprint.py`, `tests/wordpress/test_site_build.py`；创建固定 `tests/fixtures/commerce/site-brief.json`。

**Interfaces:** `build_site_blueprint(brief: SiteBrief, snapshot: StoreSnapshot) -> SiteBlueprint`；`render_owned_site(blueprint: SiteBlueprint, drafts: list[ProductDraft]) -> SitePackage`，其中 SitePackage 明确定义文件 manifest、不可变代码哈希、内容哈希；`stage(plan_id: str) -> PreviewRef` 只用 staging grant。

- [ ] 写测试：7 类页面、全站风格一致、导航有效；无币种/未确认必要运输配置/政策缺失标 NEEDS_INPUT；原生购物车与结账使用 Woo 区块，不生成支付逻辑。
- [ ] 写测试：模板编辑覆盖与 theme.json 冲突返回 STALE，原生编辑器内容不静默丢失；商家图片 mime/大小/数量越限拒绝。
- [ ] 确认失败后实现固定主题和 Blueprint→原生区块/页面映射；先批准结构/风格再生成，保留每阶段产物。
- [ ] `python -m pytest tests/muse/commerce/test_site_blueprint.py -q`；真实 WP `tests/wordpress/test_site_build.py` 检查页面、5 商品和测试购物车/结账。
- [ ] 提交 `feat: build commerce sites with owned block theme`。

### P6：Coding Bridge、代码产物与版本绑定验证（4–6 人日）

**Files:** 创建 `commerce/coding.py`, `verification.py`，`deploy/commerce/coding-sandbox.yaml`；测试 `test_commerce_coding.py`, `test_commerce_verification.py`, `tests/wordpress/test_coding_isolation.py`。

**Interfaces:** `create_coding_task(plan_id: str, brief: str, allowed_paths: list[str]) -> TaskRecord`；`verify(changeset: ChangeSet, preview: PreviewRef) -> VerificationReport`；代码批准、工程路径、来源快照沿用现有契约。

- [ ] 写测试：自然语言“修改新品区块和手机布局”生成真实 diff 和 commit revision；仅允许 templates/parts HTML、assets CSS、theme.json；不可变 PHP/JS、插件和非自有路径修改均不能打包。
- [ ] 写测试：代码修改后旧报告失效；编程子任务成功但目标购买流程失败时 report.passed=false；缺浏览器/构建器为 BLOCKED，不伪造 PASS。
- [ ] 确认失败后接现有隔离 worktree、Linux 受限执行器和确定性验证；验证代码/区块 schema、390/768/1440 px 页面与 DOM 行为、测试订单。
- [ ] Linux 实测读连接器秘密目录、访问 live、请求连接器执行、读 Docker socket 均失败；允许 staging 页面读取成功。若现有网络沙箱不支持该策略，补可验证容器边界或阻止 CODE 自动发布，不能降级放行。
- [ ] `python -m pytest tests/muse/commerce/test_commerce_coding.py tests/muse/commerce/test_commerce_verification.py tests/wordpress/test_coding_isolation.py -q`。
- [ ] 提交 `feat: verify commerce coding artifacts in isolated environment`。

### P7：业务 ChangeSet、审查批准与发布恢复（5–7 人日）

**Files:** 创建 `commerce/changesets.py`, `approval.py`, `publishing.py`；扩 `api.py` 和 connector `publisher.py`；测试 `test_commerce_publish.py`, `test_commerce_approval.py` 和真实 `tests/wordpress/test_publish_recovery.py`。

**Interfaces:** `create_changeset(plan: CommercePlan, snapshot: StoreSnapshot, package: SitePackage | None) -> ChangeSet`；`approve(id: str, digest: str, expected_revision: int) -> ApprovalGrant`；`publish(id: str, grant: ApprovalGrant) -> PublishReceipt`；`reconcile(id: str) -> PublishReceipt`。API `POST /plans/{id}/review`, `/changesets/{id}/approve`, `/changesets/{id}/publish`, `/changesets/{id}/reconcile`。

- [ ] 写测试：未批准、过期 30 分钟、目标改动、批准撤销、代码/内容改变、任务取消均为零 live 写入；新订单不使无关页面 precondition 变化。
- [ ] 写测试：步骤 2 超时/部分成功→NEEDS_RECONCILIATION/PARTIAL；重启和重复点击只回读 receipt；审核产品数量/价格/库存与实际操作严格一致。
- [ ] 写测试：发布途中 WordPress 手动改页面导致资源冲突；回退拒绝覆盖后来修改、订单和库存；模拟订单新增后发布页面，订单仍存在。
- [ ] 写测试：取消前已发出远端操作时先阻止新操作，再只读对账；成功部分为 PARTIAL、未知部分为 NEEDS_RECONCILIATION，均不得显示已撤回；批准期限到达后不再发新操作，已发出的操作只回读回执，剩余部分重新审查。
- [ ] 确认失败后实现 canonical JSON/SHA-256、30 分钟后端批准、每项 revision precondition、资源锁和持久回执；插件再次检查目标/操作授权，不依赖前端按钮禁用。
- [ ] 跑 `python -m pytest tests/muse/commerce/test_commerce_publish.py tests/muse/commerce/test_commerce_approval.py tests/wordpress/test_publish_recovery.py -q`，在 live-test 逐项核对变化。
- [ ] 提交 `feat: publish reviewed commerce changes with reconciliation`。

### P8：新品导入、事实约束、草稿到发布（4–6 人日）

**Files:** 创建 `commerce/products.py`，fixture `tests/fixtures/commerce/new-products.csv` 和 `images/`；测试 `test_product_import.py`, `test_product_facts.py`, `tests/wordpress/test_product_launch.py`。

**Interfaces:** `parse_products(csv_bytes: bytes, images: list[MediaInput], currency: str) -> ProductImportResult`；`prepare_product_launch(project_id: str, drafts: list[ProductDraft]) -> CommercePlan`；列固定 `sku,name,price,currency,stock,category,description,image_names`，result 包含逐行错误和 normalized drafts。

- [ ] 写测试：5 件正确草稿；空/重复 SKU、空名、负价/负库存、非整数库存、货币不符、公式起始单元格、21 件、图片伪 mime/缺图片引用/超限明确拒绝；SKU trim+casefold 用于批内与店铺冲突判定，展示保留原值。
- [ ] 写测试：内容候选新增材质/认证/功效等输入未提供的事实不能通过审查；事实缺口列入待确认项，价格和库存只能来自用户已确认输入。
- [ ] 确认失败后实现导入、结构化事实来源、SKU 冲突处理和新品区块映射，调用 P7 发布；每件先 draft 再回读再 publish，支持逐项 PARTIAL。
- [ ] `python -m pytest tests/muse/commerce/test_product_import.py tests/muse/commerce/test_product_facts.py tests/wordpress/test_product_launch.py -q`；重复完整提交远端仍为 5 件，故障注入保留成功/失败清单。
- [ ] 提交 `feat: launch reviewed product drafts without duplicate writes`。

### P9：商家工作台和独立编程入口（4–6 人日）

**Files:** 创建 `frontend/src/commerce/{types.ts,api.ts,CommerceHome.tsx,SiteWizard.tsx,ProductImport.tsx,TeamProgress.tsx,ReviewPanel.tsx}`；修改 `frontend/src/main.tsx`, `frontend/src/style.css`；重新生成 `frontend/src/api.generated.ts`；测试 `tests/muse/commerce/test_commerce_browser.py`。除非新 DTO 需要补生成器能力，否则不修改现有 `src/muse/openapi_types.py`。

**Interfaces:** 前端按 P1/P7 OpenAPI 生成类型；新增建站/新品卡片，单店长对话入口和两个子任务进度；ReviewPanel 展示 ChangeSet digest、差异、预览、测试结果和失效原因。

- [ ] 写 Playwright 测试：创建建站项目→确认结构/风格→查看 staging→审查→批准→看到回读成功；新品导入→逐行错误→修正→审查→发布；刷新从 SSE sequence 恢复，批准重复点击不重发。
- [ ] 写测试：390 px 下关键操作可用；隐私 Token 不出现在 DOM；预览在受控新窗口打开；STALE 禁止批准并可重验；原 coding/research/documents/记忆入口仍可访问，无店铺时 coding 可运行。
- [ ] 确认失败后实现组件和 API，保留 `main.py` 的 Host/Origin/CSP；WordPress Site Editor 显式打开，回到 MUSE 时刷新有效快照。
- [ ] `python -m muse.openapi_types` 后执行 `python -m muse.openapi_types --check`；`python -m pytest tests/muse/commerce/test_commerce_browser.py tests/muse/integration/test_frontend.py tests/muse/integration/test_generated_contracts.py -q`；`npm.cmd --prefix frontend run build`，类型、原 UI 回归和生产构建均通过。
- [ ] 提交 `feat: add merchant workflows and review workspace`。

### P10：两条真实闭环、导出与发布候选验收（4–6 人日）

**Files:** 创建 `commerce/export.py`，`benchmarks/commerce/{cases.json,run.py,score.py}`，`tests/muse/commerce/test_commerce_export.py`，`docs/commerce/{quickstart.md,acceptance.md,results.md}`；扩部署操作指南。

**Interfaces:** `export_project(project_id: str, revision: int) -> ExportManifest`；manifest 为主题包/页面/商品/配置引用和校验和，排除凭据、客户、订单；benchmark 结果格式为 `case_id, commit, environment_digest, first_attempt, final_status, interventions, usage, cost, evidence`。

- [ ] 写测试：导出不含秘密/订单；第二套同版本环境导入后得到相同核心页面/商品事实；全流程根任务取消、预算耗尽和 Worker 重启都保留回执、无额外发布。
- [ ] 确认失败后实现有版本的导出和固定案例评测器；建站 3 例、新品 3 例输入先冻结；正式结果初始全 NOT_RUN。
- [ ] 离线全套 `python -m pytest -q`、Ruff、前端生产构建、API 类型校验、`git diff --check`。不为凑计数删除原失败或跳过项。
- [ ] Linux 独立环境执行 WordPress/PHP/浏览器和 AC06/AC07 探针，保存实际截图、diff、operation receipt、订单对账和镜像 identity。
- [ ] 使用用户确认的现有模型配置与本轮专用费用上限运行 6 个真实模型案例；历史“5 美元 benchmark”额度不自动复用到 Commerce。未取得本轮预算或服务不可用时模型验收为 NOT_RUN，不以模拟代替。
- [ ] 商家人工确认外观、描述事实、操作审查和编辑体验；结果逐项 PASS/FAIL/BLOCKED/NOT_RUN；仅所有必需门槛通过才称首版验收。
- [ ] 提交 `test: document verified commerce MVP acceptance`；是否推送/上线另按当时用户授权，计划编写不代表发布。

## 3. 顺序与投入估计

```text
P0 → P1 → P2 → P3
       └→ P4 → P5 → P6
P3 + P6 → P7 → P8 → P9 → P10
```

P9 可先用合同数据做 UI，最终联调必须等待 P7/P8；安全批准/发布内核先于任何 live 写入。技术实现可分为三个连续交付包：P0–P4（项目/连接/团队）、P5–P7（建站/验证/发布）、P8–P10（新品/工作台/验收），每包结束提供可运行演示和未完成门槛，不把单包称完整产品。

### 3.1 每项任务的强制自检

- [ ] 确認前置接口/版本及环境可用；注明任何 mock 和真实环境差异。
- [ ] 保存失败测试与修复后结果；验收断言验证可观察行为，不能只验证实现内部调用。
- [ ] 运行本任务命令、故障检查和受影响的原功能回归；保留命令退出码、失败/跳过列表。
- [ ] 核对未批准 live 写入为 0、重复执行不新增资源、产物/审批绑定当前 revision；不涉及这些行为时写明“不适用及理由”。
- [ ] 保存脱敏日志/截图/回执；更新阶段报告中的 task 状态后才勾选该任务。
- [ ] PASS 才允许依赖任务放行；FAILED 修复复测；BLOCKED/NOT_RUN 写出依赖及继续可做的离线工作，不能当通过。

### 3.2 三阶段自检报告与放行

创建文件：`docs/commerce/checkpoints/stage-1.md`, `stage-2.md`, `stage-3.md`；原始脱敏证据放 `work/commerce/checkpoints/stage-N/`，检查报告记录 SHA-256 和相对证据路径。报告在实际执行时创建，本计划不预填成绩。

| 阶段 | 自检必须覆盖 | 必须演示 | 放行条件 |
|---|---|---|---|
| 1：P0–P4 | 基线/迁移/只读快照/凭据与 URL 边界/操作回执/角色依赖与预算/原编程兼容 | 创建项目、读取实际店铺、创建三角色任务、合法固定操作与非法操作拒绝 | 每项相关测试通过且真实连接/回执证据存在；仅 mock 时保留真实平台 BLOCKED，允许独立离线任务继续 |
| 2：P5–P7 | 页面/购买流程/有效模板冲突/隔离/版本审批/超时对账/部分成功/取消在途 | 完整建站预览→审查→批准→live-test 发布→API 与页面回读 | 安全探针及真实建站路径通过；缺 Linux、测试失败或无批准则不放行真实发布 |
| 3：P8–P10 | 新品错误输入/事实来源/重复发布/UI/旧入口/独立部署/导出/模型与人工门槛 | 建站与新品两条最终流程，5 商品重复发布不新增、6 固定模型案例 | AC01–AC09 各有证据；必需门槛无 FAIL/BLOCKED/NOT_RUN，人工确认完成后才称首版验收 |

每份阶段报告按以下固定字段填写：

```text
阶段与任务：
源代码 commit + 未提交文件 manifest 哈希：
环境版本/镜像 digest/测试 fixture 哈希：
检查项 | 命令/操作 | 预期 | 实际 | PASS/FAIL/BLOCKED/NOT_RUN | 证据：
首次失败、修复 revision 与复测结果：
原编程及受影响功能回归：
失败/跳过/阻塞和恢复动作：
未批准写入数、去重/冲突/取消检查：
自动检查、真实模型和人工验收分别记录：
阶段决定：放行 / 仅离线任务可继续 / 阻止依赖任务
下一阶段的具体依赖：
```

阶段 1/2 只运行对应相关回归；阶段 3 跑完整套件。发现新问题影响原 Runtime 或发布边界时，才扩大回归范围，不重复执行无新增信息的全量测试。

单名熟悉本项目的开发者初估 **43–62 人日，约 9–13 个工作周**，另预留 20% 联调缓冲。估计基于上表逐项求和，不是交付承诺；AI 辅助不直接折算成保证提速。P0 实测和 P3 Connector 原型后重估；Linux 环境、域名/HTTPS、商家素材和付款配置的等待时间另算。公共 SaaS/任意主题/自动投放不包含在此估计中。

## 4. 验收指标与证据

| 范围 | 首版目标 | 测量方法 |
|---|---|---|
| 两条模型业务闭环 | 建站 3/3、新品 3/3；首次失败与恢复后状态分列 | 冻结 6 案例，记录代码与环境哈希、人工介入、模型消耗 |
| 买家路径 | 5 fixture 商品浏览→加购→结账→测试订单成功；三个屏幕宽度 | Playwright + Woo API/订单核对，禁止真实扣款 |
| 三角色协作 | 每例两份角色产物可追溯，店长汇总；依赖/取消/预算行为正确 | Task trace、team board、产物哈希和根预算 |
| 未批准写入 | 0 次 live 写入 | mock/真实插件 ledger 与数据库资源差异 |
| 幂等恢复 | 重复请求不新增商品；未知结果必须先对账 | 丢响应、重启、重复点击故障注入 |
| 上下文/冲突 | 资源变化使旧批准失效；手工编辑与订单保留 | WP 原生编辑器/新订单 fixture 前后对照 |
| 代码能力 | 原编程入口不依赖店铺；Commerce 修改有 diff 和版本绑定验证 | 原核心回归 + 自定义新品区块真实任务 |
| 可迁移 | 第二环境恢复主题和核心页面/商品事实，秘密零导出 | manifest 校验 + 第二环境真实验证 |
| 人工体验 | 商家逐例确认页面、事实及发布差异 | 人工清单；人工未完成就保留 REVIEW_REQUIRED |

暂不承诺转化率提升、销售增长、多 Agent 60% 提速或任意站点生成时间；首版记录实际时长/成本，积累数据后建立新 benchmark。旧 Coding/SWE/MCP 指标继续独立维护。

## 5. 开始开发所需输入

已确认：WordPress + WooCommerce；两条流程；三角色；保留编程入口和现有模型配置。

开发可先完成离线契约和模拟；真实验收前必须准备独立 Linux/Docker 主机、staging/live-test 域名或地址、授权连接、5 商品与图片素材、语言/币种/运输付款设置。本轮尚未读取任何店铺凭据或建立连接。营销/分析 Agent 等待至少 10 次实际任务反馈后另行规划。

## 6. 计划自检

- AC01→P0/P1/P4/P9/P10；AC02→P5/P6/P7/P9；AC03→P8；AC04→P2/P5/P7；AC05→P4/P10；AC06→P2/P3/P6/P7；AC07→P3/P7/P8/P10；AC08→P10；AC09→P5/P8/P9。
- 首版首个平台只有 WordPress；7 类页面、20 件批量、图片限制、30 分钟审批、三个角色 ID 在 Spec/Plan 一致。
- 每任务有明确文件/接口/失败测试/实现/验证/提交步骤；路径占位不作为现有文件宣称；新增模块明确标 Create。
- Spec §7.1 错误分类→P1/P2/P3/P4/P5/P6/P7/P8/P9/P10；Spec §11 三阶段自检→本计划 §3.1/§3.2。BLOCKED 已加入业务模型，取消在途操作和批准过期后续操作已有独立测试断言。
- 已有 Runtime 的成功历史不当 Commerce 成绩；没有真实安全环境、模型预算或人工验收时不标 PASS。
- 本次仅保存设计和计划文件，无产品代码/依赖/模型配置修改，无 API 费用、店铺写入、Git 提交或推送。
