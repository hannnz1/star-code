# 本批代码审查范围

BASE / HEAD: `4aec15a`，修改尚未提交。审查 `git diff` **及未跟踪文件**；`git diff --stat` 不包含新模块。

路径：src/muse/commerce/、src/muse/commerce_connector/、wordpress/muse-connector/、deploy/commerce/、scripts/commerce/、frontend/src/commerce/、tests/muse/commerce/、tests/fixtures/commerce/；已跟踪修改 main.py/database.py/openapi_types.py、frontend main/style/generated、pyproject/uv.lock、test_state_backup.py。旧 Shopify 研究文档不属代码范围。

需求：`docs/superpowers/specs/2026-09-30-muse-commerce-mvp-design.md` 与 `docs/superpowers/plans/2026-09-30-muse-commerce-mvp.md`。决策见 `docs/commerce/development-ledger.md` 的 Ruling 行。

已实现 P1 离线契约/迁移/项目与版本 API；P0 未验证版本锁拒绝部署；P2 独立服务只读骨架、固定目标/超时/快照/秘密加载及固定插件（无 PHP/WordPress 实测）；P5 七页结构草稿；P8 严格 CSV/图片解码/保守事实校验与持久草稿；P9 中文准备界面和原入口兼容。**没有开放店铺写 API，未声称三角色、主题、staging、批准、发布、Linux 隔离、模型闭环完成。** P2 尚无 MUSE 连接 API；其余缺项明确 backlog，不得将本批当最终上线。

重点检查真实已开放接口的鉴权/输入/项目边界/版本/重复请求/旧数据迁移/旧编程兼容、Connector 凭据/固定路由/重定向/重试deadline、导入不合规不能存草稿、事实变更不能通过、前端显示不夸大状态。另检查任何未提交功能内部会隐藏关键错误或形成后续安全陷阱。

计划原 Review Focus：
1. 商家在 WordPress 原生编辑器修改模板/global styles 后，读取实际有效内容并阻止旧代码覆盖（P2/P5/P7）。
2. 同 SKU、大小写/空格、错误货币、空字段、CSV 单元格公式及重复图片导致误上新，导入须规范化、明确拒绝且不修改价格（P8）。
3. HTTP 超时但远端已经成功、进程重启及重复点击，发布必须按 operation_id 回执恢复（P3/P7）。
4. 预览 URL、图片、ZIP 路径、重定向指向越界文件或目标主机，拒绝越界，不让模型借连接器读取凭据（P2/P3/P6）。
5. 店长取消时子任务仍运行、发布前资源变化及 live 新订单，阻止后续动作且保留订单/库存（P4/P7/P10）。

真实外部环境项尚未实现或未运行。审查报告须逐项说明当前影响，明确 Declined to judge，禁止假装这些门槛通过；本批 ready 与整个 MVP ready 分开。
