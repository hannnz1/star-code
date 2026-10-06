# 第七批：计划生成审查候选（P7 部分实现）

新增 create_changeset(plan, snapshot, package)。仅对已进入 VERIFYING/REVIEW_REQUIRED 的建站计划生成自有主题包候选：重新规范化快照并核对资源指纹，重建完整 ZIP，对比包元数据、内容和代码来源，绑定主题及设置依赖。重复生成同一计划版本得到相同候选和操作 ID；新版本不会复用旧操作回执。

生成结果是审查候选，不表示通过网站验证。没有开放 API/CLI/Agent 批准或发布入口，没有实际部署、模型调用或店铺写入。

26 项新增测试、与原审批模块合跑 54 passed。集成测试使用真实本地 SQLite、主题 ZIP、签名及内部发布授权模块，证明候选可以保存、批准和读取；默认发布关闭，撤销后旧许可拒绝。人工构造报告不证明真实浏览器或购买链路已验证。

仍缺：可信 P6 验证器、页面所有权/导航/SKU 证据、商品逐件 draft→回读→publish、PHP 原子写插件、实际发布编排、界面与真实 WordPress 环境验收。商品候选暂返回 UNSUPPORTED_CAPABILITY；分页读取到零件商品不能证明 SKU 不存在。完整建站与新品上线尚未验收。

来源策略：当前只接受冻结输入可确定性重建的原生主题。未来 Coding Agent 自定义主题修改须接可信产物存储与实际验证链；不通过传入包哈希假装代码已接受。代码提交标识仍需未来 verifier 核实其真实来源。

## 最终验证

- 审查前全量：1353 passed / 3 skipped / 1 failed，156.86 秒。保留 commerce7-full-before-fix.log/exit；不替代修复后证据。
- 修复后根目录全量：1357 passed / 3 skipped / 1 failed / 2 warnings，162.64 秒，pytest 退出码 1，证据 commerce7-full-final.log/exit。失败仍为原 Windows launcher test_stop_script_matches_serialized_process_time[True-False]，taskkill Access denied；没有删除/跳过，不标全量通过。
- Ruff、OpenAPI 字节检查、git diff --check 均退出 0；对应 commerce7-ruff-final、commerce7-openapi-final、commerce7-diff-check 日志/退出码。
- 一轮审查及一次修复见 ../review-results-round-7.md；无模型/API 成本、实际店铺写入、Git 提交推送或 Desktop 同步。
