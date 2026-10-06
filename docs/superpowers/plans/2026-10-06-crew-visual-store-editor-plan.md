# Crew 可视化建站与商家编辑 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立从首页区块编辑、保存预览，到商品编辑、AI 局部修改和受审查发布的完整商家操作流程。

**Architecture:** 沿用 Crew 的 Python API、任务/审批系统和受控 WordPress 主题。新增版本化页面文档，让表单、AI、预览和主题打包共享相同来源；扩展现有商品、媒体和发布模块，不另建一套任务系统。

**Tech Stack:** Python / Pydantic / FastAPI / SQLite、React / TypeScript、WordPress / WooCommerce、pytest / Playwright。

**Spec:** [设计与边界](../specs/2026-10-06-crew-visual-store-editor-design.md)

## Global Constraints

- 平台为 WordPress + WooCommerce，保留 Crew 通用编程入口和三个商家角色。
- schema_version=1，最多 20 个首页区块，首期五种区块；不接受任意 HTML/PHP/CSS。
- 手动编辑、AI 修改、预览与发布共享版本化文档；保存不等于发布。
- 七类必要页面及购物车/结账交易模板保留；商品首期单 SKU。
- 桌面优先，然后 900、390、360px；每个用户可见字符串提供中英文。
- 既有文件有大量未提交改动；实施前记录基线并做针对性备份，禁止重置或覆盖无关工作。
- 不自动推送 GitHub或生产发布；历史数据不删除。真实 API 验收另行限定预算。
- 计划中的新文件、接口和性能数字均为设计目标，不是已实现结果。

## Review Focus

- T1/T2：慢响应、断网、切换项目和双标签页同时保存，不能串店或静默覆盖。
- T1/T3：旧草稿缺字段、损坏媒体、跨项目资源引用，迁移可重复且失败不破坏旧记录。
- T3：结构修改与人工代码改动冲突，不覆盖代码；审批来源变更必须过期。
- T4：价格精度、币种/库存、分类删除与导航失效，不能误报发布或订单成功。
- T5/T6：过期 AI 建议、重复请求及发布状态 UNKNOWN，不重复收费执行或盲目重发。

## 当前基线与文件归属

| 已有模块 | 复用方式 |
|---|---|
| frontend/src/commerce/SiteBlueprint.tsx；src/muse/commerce/repository.py | 保留页面清单与版本检查，接入设计文档引用 |
| CommerceHome.tsx / StorePreview.tsx / studio.css | 编辑入口、真实预览与布局 |
| ProductImport.tsx / ProductImages.tsx；products.py / media.py | 商品合同、导入与媒体校验 |
| theme.py；wordpress/muse-storefront；site_release.py | 编译、校验、部署与读回 |
| CodeIntegration.tsx；code_integration.py | 用户代码改动及来源冲突检测 |
| ManagerPanel.tsx；orchestration.py / tools.py | 局部 AI 提案及角色任务 |
| VerificationPanel.tsx / MerchantRelease.tsx；merchant_review.py | 清单状态、验证与正式发布审查 |

以下新增目录为建议，不要求重构现有无关模块。

## 阶段与依赖

| 阶段 | 任务 | 可交付结果 | 估算有效工程日 |
|---|---|---|---:|
| A | T1–T2 | 首页可编辑、可保存、可看结构预览 | 8–12 |
| B | T3 | 同一草稿生成真实 WordPress 预览并验证 | 5–7 |
| C | T4 | 商品单条编辑、素材复用、导航排序 | 4–6 |
| D | T5 | AI 局部修改、差异审查、接受与撤销 | 4–6 |
| E | T6 | 开店配置与发布检查整合 | 5–8 |
| F | T7 | 回归、实际部署验证及人工验收交付 | 3–5 |

依赖：T1 → T2 → T3；T4 依赖 T1，T5 依赖 T2/T3，T6 依赖 T3/T4；T7 汇总所有阶段。估算为一位熟悉项目的工程师全职推进，合计 29–44 工程日，约 6–9 周；并非 AI 连续运行时长承诺。环境/账号准备、商家补充资料、人工审核等待不计入，完成 T1 后复估。

## Task 1：版本化设计文档与兼容迁移

**Files:** Create `src/muse/commerce/design_models.py`, `design_repository.py`, `design_api.py`; Modify `src/muse/commerce/api.py`, `schema.py`; Test `tests/muse/commerce/test_design_api.py`.

**Interfaces:** `DesignRepository.get_or_create(project_id: str, expected_project_revision: int) -> StoreDesignDocument`；`save(project_id: str, expected_project_revision: int, expected_revision: int, client_request_id: str, document: StoreDesignDocument) -> StoreDesignDocument`。文档字段按设计文件固定。API `GET /projects/{id}/design`（未初始化返回明确空状态）；`POST /projects/{id}/design` 初始化；`PATCH /projects/{id}/design` 版本检查保存。归属 `/api/commerce`。

- [ ] 写 `test_initialize_once_from_existing_blueprint`：同一来源重复初始化返回同一文档；旧方案数量不变。
- [ ] 写 `test_stale_save_and_cross_project_media_rejected`：旧 expected_revision 返回 409；跨店媒体不接受，原文档保持不变；未知 schema 和 21 个区块返回 422。
- [ ] 运行 `.\.venv\Scripts\python.exe -m pytest tests/muse/commerce/test_design_api.py -q`，确认新接口用例先失败。
- [ ] 实现五种区块判别联合、稳定 ID、白名单属性、幂等请求摘要和事务保存。存储使用显式的设计版本表及当前版本指针，不修改历史 blueprint 数据。项目变更时要求重新绑定来源并保留人工内容供确认。
- [ ] 重跑上述测试，检查迁移重复执行和数据库备份恢复；更新 OpenAPI 生成类型。
- [ ] 自检 diff，仅将本任务文件记录到变更清单；需要提交时只提交已验证的本任务改动。

## Task 2：首页编辑器、结构预览与保存反馈

**Files:** Create `frontend/src/commerce/editor/StoreEditor.tsx`, `SectionTree.tsx`, `SectionInspector.tsx`, `DesignCanvas.tsx`, `useDesignDraft.ts`, `editor.css`; Modify `CommerceHome.tsx`, `navigation.ts`, `frontend/src/i18n/extra.json`; Test `tests/muse/commerce/test_design_editor_browser.py`.

**Interfaces:** `StoreEditor({api, project}: {api: Api; project: StoreProject})` 使用 T1 API；`DesignCanvas({document, selectedSectionId, onSelect})` 只渲染经过校验的数据。useDesignDraft 负责 CLEAN/DIRTY/SAVING/CONFLICT、撤销栈、请求代次和离开提示。

- [ ] 写 `test_edit_save_reload_and_cancel`：修改标题、图片、链接与顺序，保存刷新一致；取消不保存；一次撤销恢复前一步。
- [ ] 写 `test_delayed_response_project_switch_and_conflict`：迟到响应不串店；双标签页保存冲突保留当前输入；请求失败后可以显式重试。
- [ ] 运行 `.\.venv\Scripts\python.exe -m pytest tests/muse/commerce/test_design_editor_browser.py -q`，确认功能缺失导致失败。
- [ ] 实现三栏编辑器、当前区块高亮、五种区块增删/隐藏/排序、主题色/字体预设、保存反馈。拖动必须有键盘上下移动替代操作；空画布提供添加区块入口。
- [ ] 构建前端并重跑测试，检查 1440/1280/900/390/360px、中英文、键盘操作及恶意文本安全显示；结构预览明确注明不代表 WooCommerce 实际效果。
- [ ] 自检和保存验收截图，本阶段不显示“真实网站已建成”。

## Task 3：受控主题编译、真实预览与来源绑定

**Files:** Create `src/muse/commerce/design_render.py`; Modify `theme.py`, `orchestration.py`, `preview_repository.py`, `site_release.py`, `code_integration.py`，按需要扩展 `wordpress/muse-storefront` 及连接器图片映射；Test `tests/muse/commerce/test_design_render.py`, `test_design_wordpress.py`.

**Interfaces:** `render_design(document: StoreDesignDocument, resources: ResolvedDesignResources) -> RenderedDesign`；ResolvedDesignResources 提供已验证媒体/商品映射，RenderedDesign 包含允许的模板内容及文档摘要。产物附 ThemeArtifactBinding，具体字段见设计文件。

- [ ] 写 `test_design_compiles_to_allowed_blocks`：五种区块、导航、媒体均可编译，内容正确转义；受控交易模板完整。
- [ ] 写 `test_manual_code_conflict_and_stale_approval`：冲突不覆盖源文件；文档变更后旧预览及批准不能发布。
- [ ] 运行 `.\.venv\Scripts\python.exe -m pytest tests/muse/commerce/test_design_render.py -q`，先确认失败。
- [ ] 实现设计到 Gutenberg 主题内容的确定性映射；只按需扩展区块/资源白名单，同时更新校验与安全测试；编译流程禁止执行 AI PHP。定义结构区域与人工代码归属，接入原有预览和发布绑定。
- [ ] 在隔离 WordPress/WooCommerce 中验证文本、图片、商品、链接、购物车/结账；运行 `test_design_wordpress.py`，真实环境未连接则记录 BLOCKED。不能以静态页面截图代替。
- [ ] 审查产物摘要、主题包和独立读回报告；保存对应版本的桌面与手机证据。

## Task 4：商品表单、素材选择与导航

**Files:** Create `frontend/src/commerce/ProductEditor.tsx`, `NavigationEditor.tsx`, `MediaPicker.tsx`, `src/muse/commerce/product_drafts.py`; Modify `ProductImport.tsx`, `api.py`, `models.py` 及必要的导航连接器；Test `test_product_draft_api.py`, `test_product_editor_browser.py`, `test_navigation_editor.py`，均在 `tests/muse/commerce/`。

**Interfaces:** `ProductDraftRepository.save(project_id, expected_project_revision, expected_revision, draft: ProductDraft) -> SavedProductDraft`；现有导入记录保持不可变，表单编辑形成新版本/新来源绑定再进入工作流。NavigationTarget 为 page 或 collection 的类型化引用，避免直接信任任意 URL。

- [ ] 写 `test_product_edit_preserves_confirmed_facts`：Decimal 价格精度、币种、库存和媒体归属正确，商品保存不直接上架。
- [ ] 写 `test_navigation_sort_and_deleted_target`：顺序保存刷新一致；删除分类后不能发布失效链接；商品模板不作为固定页面目标。
- [ ] 运行三个新增测试文件，确认新行为先失败。
- [ ] 实现单商品编辑与图片选择，CSV 到表单的明确入口；实现一级导航排序。二级导航必须与连接器、读回验证同批开发和测试，否则入口保持不提供。
- [ ] 构建并重跑用例，回归原有商品导入和上新工作流；检查空商品、无图片、非法价格及手机编辑。
- [ ] 自检商家草稿、平台草稿和已发布状态有清晰差别，保存测试证据。

## Task 5：针对区块的 AI 修改提案

**Files:** Create `src/muse/commerce/design_proposals.py`, `frontend/src/commerce/editor/DesignProposal.tsx`; Modify `tools.py`, `orchestration.py`, `ManagerPanel.tsx`; Test `tests/muse/commerce/test_design_proposals.py`。

**Interfaces:** `DesignProposalService.propose(project_id, design_revision, section_id, instruction, client_request_id) -> ProposalJob`；`accept(project_id, proposal_id, expected_design_revision) -> StoreDesignDocument`。提案保存 base_revision、section_id、patch、差异、任务身份及费用引用。

- [ ] 写 `test_proposal_scope_and_accept_once`：仅修改选中区块；重复接受幂等；拒绝不改文档。
- [ ] 写 `test_stale_proposal_and_untrusted_instructions`：用户后续编辑导致冲突；提示词中的任意代码/发布要求不能扩权；中止任务后不偷偷应用。
- [ ] 使用确定性提供者运行 `.\.venv\Scripts\python.exe -m pytest tests/muse/commerce/test_design_proposals.py -q`，确认先失败。
- [ ] 实现结构化提案、允许字段校验、前后比较、接受/拒绝；店长协调现有角色，所有写入复用 T1 保存服务。失败保留手动编辑入口。
- [ ] 通过确定性测试后再按独立预算运行真实模型验收，累计失败/重试成本；保存越界率、首次可接受率、延迟和实际 token，不预填效果数字。
- [ ] 自检真实 API 未运行时明确 NOT_RUN，不能把固定响应测试算作模型效果。

## Task 6：开店配置、检查与发布整合

**Files:** Create `src/muse/commerce/store_readiness.py`, `frontend/src/commerce/StoreReadiness.tsx`; Modify `BrandSettings.tsx`, `VerificationPanel.tsx`, `MerchantRelease.tsx`, `merchant_review.py`，按需扩展 `wordpress/muse-connector/includes/store-setup.php`；Test `test_store_readiness.py`, `test_store_readiness_browser.py`。

**Interfaces:** `StoreReadinessService.evaluate(project_id: str) -> StoreReadinessReport`；每项包含 key、configuration_status、verification_status、evidence_ref、action。状态来自已保存事实和真实检查结果，不允许客户端勾选通过。

- [ ] 写 `test_configured_is_not_verified`：填写政策/运费不能自动使购买验证通过；支付/域名不可用显示明确下一步。
- [ ] 写 `test_shipping_boundary_and_unknown_release`：免运门槛边界金额正确；UNKNOWN 发布必须先读回，不重复提交。
- [ ] 运行两个新增文件确认先失败，再实现清单、配置表单和修复跳转；复用已有可用设置能力，补齐的远程写操作必须配套幂等回执和读回。
- [ ] 验证配置变化使相关旧审查失效，未保存输入不丢失；税务只显示状态和配置入口，不假定用户纳税义务。
- [ ] 在隔离站运行真实运费、付款测试模式及购买读回；目标或凭据缺失时报告阻塞项及可继续的工作。
- [ ] 审查发布按钮始终说明目标、版本和修改范围，保留原有商家确认机制。

## Task 7：完整回归与交付

**Files:** Create `tests/muse/commerce/test_visual_store_journey.py`, `docs/commerce/visual-store-editor-acceptance-2026-10-06.md`; 更新相关 quickstart。

**Interfaces:** 使用前六任务产出的设计版本、产物绑定、模型提案与 readiness report，形成同一宠物店验收证据链。

- [ ] 写完整旅程：建立店铺 → 改首页/图片/导航 → 保存刷新 → 编辑 AUD 商品 → AI 提案审查 → 真实隔离预览 → 发布审查 → 读回。
- [ ] 自动验证浏览器刷新、断线、重复请求、多标签冲突和旧批准失效；维持原编程入口、看板、归档恢复、导入功能。
- [ ] 运行前端构建、OpenAPI 类型同步检查，以及新增测试和相关既有回归。所有失败必须定位；不以累计历史测试数宣称本轮通过。
- [ ] 记录本地结构预览、真实 WordPress 预览和生产发布的不同完成状态；本地演示不是生产站。
- [ ] 最后交用户人工检查：首次使用可理解性、宠物店视觉与文案、移动端、政策/配送准确性，以及正式目标发布决定。

## 通用验证命令

在 `outputs/muse-next` 目录执行：

```powershell
.\.venv\Scripts\python.exe -m muse.openapi_types
npm.cmd --prefix frontend run build
.\.venv\Scripts\python.exe -m muse.openapi_types --check
.\.venv\Scripts\python.exe -m pytest tests/muse/commerce/test_site_api.py tests/muse/commerce/test_site_blueprint.py tests/muse/commerce/test_commerce_workflow.py tests/muse/commerce/test_workflow_api.py tests/muse/commerce/test_crew_ui_upgrade_browser.py -q
```

新增测试按所属任务执行。WordPress 集成测试必须输出目标、来源版本与真实运行标志；未配置环境应显式跳过并在交付表记为 BLOCKED。

## 目标指标与完成门槛

| 指标 | 本轮目标及测量口径 |
|---|---|
| 受控首页编辑 | 五种区块均可保存/恢复/预览；同一版本内容比对全部一致 |
| 本地交互 | 固定本机、20 区块、30 次输入测量，输入到结构画布更新 p95 ≤200ms；不含网络或 AI 等待 |
| 保存 | 固定本机小文档、30 次保存 p95 ≤1s；不含图片上传和真实站构建；超时保留输入 |
| 数据隔离 | 跨店引用、旧版本覆盖、重复副作用的自动用例全部通过 |
| UI | 指定五个宽度无页面横向溢出；关键任务中英文、键盘可操作 |
| WordPress 一致性 | 修改后的标题/图片/导航/商品与封存版本逐项读回一致 |
| 真实购买 | 隔离环境购买闭环与付款测试模式通过，不混入真实交易 |
| AI 效果 | 报告实际成功率/费用/延迟；结果需人工评阅，不以演示假数据替代 |
| 用户验收 | 用户实际完成首页修改和新品准备；未完成的人工项明确列出 |

## 开始条件与本次交付

可立即开始 T1/T2，开发及确定性测试不依赖新增付费 API。T3/T6 的真实验证需要先核查既有隔离环境能否启动；不可用时可继续离线实现但保留验收阻塞。正式发布需要明确真实商家目标和既有审查流程；AI 真实效果测试需要本轮费用上限。

建议按本对话连续实现、每阶段自检的方式推进，先交付 A 阶段供用户体验，再继续其余阶段。已开始并实现主要 A–F 链路；隔离建站 18/18 后连续上新 3/3 已通过独立验证与设计读回。当前逐阶段证据和未完成项见 [2026-10-06 验收记录](../../commerce/visual-store-editor-acceptance-2026-10-06.md)。分类导航、Crew 内远程配送配置、文案质量和人工验收仍有缺口，不标记整体完成。
