# Crew — Your AI commerce team

**你的 AI 商家团队：从建站到新品上线，同时保留完整的编程工作空间。**

Crew 面向独立站商家，把目标拆解、网站开发、商品内容、预览审查和发布执行放进同一个工作台。首版固定采用 **WordPress + WooCommerce**，团队设店长、网站开发、商品内容三个角色，优先做通「建站」与「新品上线」两条流程。

项目由 StarCode / mewcode-python 演进而来，Agent 核心使用 Python。产品名称已更新为 Crew；`muse`、`mewcode` 命令、包名及部分配置名称继续保留，以兼容现有使用方式。

> **状态更新：2026-10-07 · 0.3.0rc8 开发候选版**
>
> 商家工作台、可视化编辑、分类导航和配送规则代码已上传本仓库的 `muse-python-rc8` 分支。专项测试及一次真实隔离建站有通过证据；最新「建站 → 上新」完整连续验收仍未通过浏览器检查。生产商家发布和人工体验尚未验收，不能视为正式生产版本。

## 可以做什么

| 工作区域 | 当前能力 |
| --- | --- |
| 商家工作台 | 管理店铺项目、查看任务看板和执行进度、审查成果、继续后续任务；支持中英文界面 |
| 建站方案 | 七类页面结构草稿、编辑当前方案、保留历史版本；结构草稿与实际建站状态分开呈现 |
| 可视化首页编辑 | 五类受控区块，添加、删除、隐藏、排序，图片和样式设置，撤销/重做及版本冲突处理 |
| AI 局部修改 | 针对局部内容生成建议，查看修改前后差异，再接受或拒绝；应用前校验版本 |
| 商品准备与上新 | 单 SKU 表单、CSV 商品批次、本地图片、价格/库存/币种校验及商品内容准备 |
| 分类导航 | 从本店商品批次选择一级分类，编辑显示名称和顺序；发布时绑定实际分类与站内链接 |
| 配送规则 | 编辑国家区域、固定运费和订单金额免运门槛，按国家及购物车小计试算草稿运费 |
| 团队协作 | 店长、网站开发、商品内容角色围绕持久化任务协作，保留状态和成果记录 |
| 开发空间 | 独立使用编程助手、网页研究、资料整理和后台任务，无需先创建店铺 |

**保留的 Coding Agent 能力：** 文件读写、命令执行、代码修改与验证、MCP 工具发现与按需加载、Skill、子 Agent、隔离工作树及受控合并。任务、事件和记忆可持久化，支持恢复、暂停与人工审批。自动记忆提取等可选模型能力默认关闭，启用后会产生模型调用费用。

商家功能目前仅支持固定平台与受控主题方案。多级分类导航、实时承运商报价、税务引擎、订单履约，以及营销和分析 Agent 不属于本版已完成范围。

## 两条业务流程

**建站：** 创建店铺 → 准备商品和品牌资料 → 编辑页面、导航及配送草稿 → 团队准备 → 封存版本 → 隔离预览与购买验证 → 审查并批准 → 执行及读回核对。

**新品上线：** 准备商品批次 → 校验商品事实和图片 → 团队准备 → 在保留现有主题、导航与配送的前提下预览 → 审查并批准 → 执行及核对。

保存草稿不会发布到远程店铺，也不会调用模型。启动模型任务或使用 AI 局部修改才涉及模型调用。打开本地工作台不等于已创建 WordPress 网站；真实建站需要配置店铺连接、连接器和隔离运行环境。

## 快速启动：Windows 源码版

准备 Python 3.12+、Node.js/npm 和 Git，以及已有的 StarCode 模型配置。安装过程需要联网下载依赖和 Chromium。

```powershell
git clone --branch muse-python-rc8 --single-branch https://github.com/hannnz1/star-code.git crew
cd crew
.\Setup-MUSE.ps1
```

以下方式沿用原配置中的模型；如果当前终端设置了 `MUSE_MODEL`，该环境变量仍会覆盖配置。将示例配置路径替换为实际路径，不要把 API 密钥写进命令或提交到 Git。

**终端一：启动工作台 API**

```powershell
.\.venv\Scripts\python.exe -m muse api --config 'C:/path/to/star-code/config.yaml' --data-dir './.muse' --port 8765
```

浏览器打开 <http://127.0.0.1:8765/>。API 单独运行可以查看工作台、编辑草稿；后台模型任务需要 Worker。

**终端二：读取本地访问令牌**

```powershell
.\.venv\Scripts\python.exe -m muse token --data-dir './.muse'
```

将输出填入登录页的「本地访问令牌」。这是工作台访问凭据，**不是模型 API Key**；不要公开分享。令牌命令的 `--data-dir` 必须与 API 一致。

**终端三：运行后台 Worker**

```powershell
.\.venv\Scripts\python.exe -m muse worker --config 'C:/path/to/star-code/config.yaml' --data-dir './.muse'
```

Worker 会处理待执行任务，模型任务可能产生 API 费用。API 和 Worker 必须使用同一数据目录及一致的模型配置；手动启动的服务可在各自终端按 `Ctrl+C` 停止。

也可使用 `Start-MUSE.ps1 -Config <配置路径> -Model <模型名>` 同时启动 API/Worker，再用 `Stop-MUSE.ps1` 停止。注意：启动脚本省略 `-Model` 时会使用脚本默认值 `gpt-6-sol`，并非自动沿用配置中的模型。

**已有本地开发预览的用户：** 如果服务使用端口 `8876` 和 `./work/commerce-preview-state`，应继续打开 <http://127.0.0.1:8876/>，并使用下列命令获取对应令牌。切换数据目录会看到不同的店铺和任务。

```powershell
.\.venv\Scripts\python.exe -m muse token --data-dir './work/commerce-preview-state'
```

更多说明见 [商家快速开始](docs/commerce/quickstart.md) 与 [运行、恢复和迁移指南](docs/python-runtime-operations.md)。

## 技术架构与执行边界

| 层次 | 实现与职责 |
| --- | --- |
| 工作台 | React、TypeScript、Vite；商家表单、可视化编辑、任务和成果审查 |
| 服务与后台任务 | Python、FastAPI、独立 Worker；任务编排、工具调用、审批和恢复 |
| 状态 | SQLite / SQLAlchemy；任务、事件、记忆及执行记录 |
| Agent 扩展 | MCP、Skill、子 Agent 与工作树；沿用 StarCode 模型配置 |
| 电商执行 | WordPress + WooCommerce、项目连接器与受控主题；WordPress 侧仍包含 PHP |
| 验证 | pytest、Playwright、Python/PHP 协议测试、隔离站购买验证 |

发布审批绑定封存的方案、商品、图片、代码和目标前置状态。执行后独立读回核对；未知写入结果进入待核对状态，不能直接重复发送。草稿已保存、代码已生成和真实发布成功是不同状态。

Linux 隔离测试已有实际运行证据，但不能据此宣称所有部署环境均已验收。通用 Agent 的 OS 沙箱为可选能力；Windows 不支持该内核沙箱，要求隔离的模式不能静默降级。生产连接与隔离环境的准备见 [连接器说明](docs/commerce/connector.md)、[环境配置](docs/commerce/environment.md) 和 [参考环境](docs/commerce/reference-environments.md)。

## 测试与当前验收状态

下面是已记录的结果，不代表每次提交都已重跑全量测试，也不能把覆盖重叠的报告数量相加。

| 项目 | 已有证据与限制 |
| --- | --- |
| 分类导航、配送规则专项 | 151 项契约测试通过；后续 40 项最终契约测试通过，含满额商品、预览容量及隐藏种子读回；上传前再次运行该 40 项通过 |
| 界面专项 | 4 项浏览器测试、3 项迟到响应/跨店保护测试通过；覆盖表单、语言、响应式和版本保护 |
| 前端与接口 | 前端构建、1036 条翻译 / 816 处明确文案检查、OpenAPI 类型同步通过 |
| 真实隔离建站 | 分类与配送建站报告六阶段通过、19/19 发布完成；实际购物车小计 12.30 / 24.60 / 36.90，对应运费 6 / 0 / 0 |
| 最新完整连续旅程 | **未通过**。最终复测浏览器阶段出现 `STOREFRONT_LINK_FAILED`、`PAGE_CAPTURE_FAILED`、`BROWSER_UNAVAILABLE`；未进入发布，原因仍待定位 |
| 生产及人工验收 | 真实商家生产发布、AUD 宠物店品牌效果、人工操作体验及独立干净 Windows 安装验收仍待完成 |

真实站点测试使用合成的一次性隔离站。历史版本的建站和上新通过记录不能替代加入分类、配送后的最新连续验收。详细证据及报告文件名见 [分类导航与配送验收](docs/commerce/navigation-shipping-acceptance-2026-10-06.md) 和 [可视化编辑验收](docs/commerce/visual-store-editor-acceptance-2026-10-06.md)。

本地可执行以下基础检查；它们不等于完整电商验收：

```powershell
npm.cmd --prefix frontend run build
.\.venv\Scripts\python.exe -m muse.openapi_types --check
```

## Benchmark：仅报告已验证口径

历史 RC8 冻结基线的 MCP 配对试验覆盖 100 个工具、90 对 / 180 次运行，两组任务均为 90/90 成功：

| 指标 | 历史实测 |
| --- | --- |
| 首轮工具 schema Token 降幅 | 95.85% |
| 全会话 MCP 工具描述 Token 降幅 | 78.88%，95% bootstrap 区间 78.51%–79.26% |
| API 输入 Token 降幅 | 26.72% |

这些指标来自固定版本和模型，不等于当前商家流程的费用降幅或整体性能。短上下文合成压力测试的 306/306 字段断言通过，也不能当作「8 小时以上事实保留」的证明。

当前汇总尚无可计入本版本的 SWE-bench-Live 官方完整评分；「权限弹窗 30 次降至 5 次」「信息保留率 17%→100%」「多 Agent 加速 60%」也不能作为已完成的正式成绩。测试设计和统计范围见 [Benchmark 计划](docs/mewcode-resume-benchmark-plan.md)、[历史结果与限制](docs/mewcode-resume-benchmark-results-2026-09-28.md)。

## 兼容、数据与后续工作

- Python 核心保留编程入口，Java 替代的映射与差异见 [生产文件映射](docs/java-migration-matrix.csv)、[测试映射](docs/java-test-matrix.csv) 和 [行为审计](docs/java-behavior-audit.md)。不能将代码迁移等同于全部正式验收完成。
- 完整状态备份前停止 API/Worker。回滚需恢复升级前状态副本，不能让旧程序直接读取升级后的数据库；操作见运行指南。
- 配置、API 密钥、本地访问令牌、状态包和商家运行数据不应提交到 Git。
- 下一步优先定位浏览器/预览转发失败，重跑完整建站→上新旅程，再完成真实商家、人工体验及干净安装验收。

## 文档索引

- [商家快速开始](docs/commerce/quickstart.md)
- [可视化编辑开发计划](docs/superpowers/plans/2026-10-06-crew-visual-store-editor-plan.md)
- [分类导航与配送使用及验收](docs/commerce/navigation-shipping-acceptance-2026-10-06.md)
- [连接器与发布协议](docs/commerce/connector.md)
- [Python 运行、恢复与迁移](docs/python-runtime-operations.md)
- [Agent 升级说明](docs/muse-upgrade-release-notes-2026-09-28.md)
- [Agent 人工验收清单](docs/muse-upgrade-human-acceptance-2026-09-28.md)
- [独立 Windows 验收](docs/clean-windows-acceptance.md)

本项目保留 StarCode 与 mewcode-python 的来源标注。上游根级许可证及分发范围尚待核实；仓库公开可见不等于已确认全部第三方代码的再分发许可。
