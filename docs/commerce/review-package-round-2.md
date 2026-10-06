# 第二批审查范围：店铺上下文与三角色准备团队

这是增量实现，不是全部 Commerce MVP 验收。工作目录 `outputs/muse-next`，HEAD/base 均为 `4aec15ae79648f1e398b29e975177b73ca532fb6`，修改尚未提交；不能用空的 HEAD..HEAD 代替工作文件审查。前一批准备/主题审查已完成，结果在 `review-results.md`，本次不重复它。

## 绑定要求与文件

设计 `docs/superpowers/specs/2026-09-30-muse-commerce-mvp-design.md`、计划 `docs/superpowers/plans/2026-09-30-muse-commerce-mvp.md`。本批仅实现 P2 的主程序连接/上下文、P4 的提案协作内核、P9 的对应 UI。

- `commerce/platforms/{base,wordpress}.py`、`connections.py`、`commerce_connector/api.py`、`config.py`：固定 Connector 服务，连接 ID 注册、同项目/环境身份、版本清单、无任意 URL/凭据暴露；刷新失败保留旧上下文；重新绑定 ID 必须失效旧上下文。
- `commerce/{orchestration,roles,planning,tools}.py`、`commerce/agents/*.md`：同数据库事务创建计划/步骤/根任务/预算；复用原租约、审批、委派回执；三个固定有效权限；共享预算与冻结 provider 身份；取消、异常恢复、只允许一次格式修正；哈希成果；不得假称部署/发布。
- `tasks/{repository,delegation,worker}.py`、`agent/{loop,instructions}.py`、`extensions/{roles,hooks}.py`、`tools/{registry,context,verification}.py`、`memory/service.py`、`tasks/trace.py`：检查商务 checkpoint 不能从普通用户 API 注入；原 Coding 行为、权限和验证保持；Commerce 不能继承可执行 Hooks 或发生额外付费记忆请求；凭据脱敏。
- `commerce/api.py`、`main.py`、`frontend/src/commerce/{StoreTeam,CommerceHome,api}.tsx/ts`、生成类型：项目作用域、幂等、乐观锁、手机宽度、切换项目后异步晚返回归属；错误不伪造进度。

## 本批明确裁决

P6 隔离环境尚无，网站开发角色仅结构提案，不授予 Shell/改文件；整个协作团队不执行 WordPress 写入、部署或发布。只有具备验证过的连接和当前 staging 快照才能排队；实际模型执行沿用用户配置，UI 明示消耗额度。离线测试使用 ScriptedProvider 和 HTTP 外部边界 fixture，无真实费用。

原任务能力上限需包含三角色内部工具，才能复用原子集委派协议；每个角色的有效工具集合由代码固定过滤，角色 prose/checkpoint 不能扩权。Commerce 禁止 executable Hooks 与语义记忆额外模型请求，不更改普通任务。

提交提案/团队委派/请求审查只修改结构化记录，按原管理记录工具处理，不当作代码修改；未来 Coding Bridge 必须继续执行代码验证 gate。不能把“未生成可部署代码”升级成站点成功。

Windows `stream_prefix` 的私有尾部本来用于识别跨片段秘密；测试断言对外前缀及最终 safe(tail)，而非要求私有缓冲始终不含秘密。短环境令牌错误已隐藏原输入。项目事实/连接/快照改变将旧计划标 STALE 并取消旧团队。

## 当前证据与未完成

连接及上下文 10 项测试，工作流/运行器审批/脱敏相关 36 项测试通过，真实浏览器 1440/390 各一项通过。新 API 测试验证重复排队、作用域、错误条件；前端 build 通过。全量待本轮最终命令，原 Windows launcher Access denied 失败不得隐藏。

真实 WordPress、PHP lint、镜像 digest、Linux 隔离、购买流程、模型闭环、完整 wheel/干净安装、P3/P6/P7/P10 仍未验收；这些阻塞不作为离线 PASS。报告应逐项列明审查发现和 declined-to-judge。
