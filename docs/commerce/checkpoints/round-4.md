# 第四批检查点：固定操作协议和内部授权

P3 部分实现；未开放写入口，未完成建站/新品实站验收。

新增：

- 七类固定操作 payload 严格验证，拒绝额外字段、资源 ID 不符、缺资源指纹、浮点价格、主动 HTML 和未接通的媒体引用。原生主题包复用已有安全 ZIP 校验。
- 内部 ExecutionAuthority：独立 HMAC 密钥，授权绑定实际站点 URL/项目/环境、批准 ID、变更集/验证摘要、资源条件、操作内容及 30 分钟以内期限。验证时必须传当前可信批准，撤销/目标重绑/内容变化均拒绝。

当前模块未接入公开 API、任务工具或 CLI。签名有效不证明商家已审阅此操作：P7 尚需真实批准存储、ChangeSet 成员/报告真实性/当前资源条件校验。插件端授权、原子写入、独立 Linux 隔离仍未实现或未验收。本批纯文本/no-media 范围和签名协议裁决记录在 development-ledger.md 第四批。

新增 38 项测试通过（work/commerce4-focused.log），本批无模型请求、API 费用、店铺写入、Git 提交/推送或 Desktop 同步。独立审查和全量回归结果将追加于此；不会覆盖第三批记录。

## 审查后验证

- 两项 Important 已完成一次 RED→GREEN 修复：签名正确的深层 JSON/巨大 issued_at 统一脱敏拒绝；价格格式/精度及库存上限与现有 CSV 导入保持一致。
- 新增 49 项测试通过；与第三批账本/回执合跑 **64 passed**（work/commerce4-boundaries-final.log）。最大合法金额/库存及小数边界保持原字符串。
- 初次审查后 focused run 47 passed；随后补两项合法边界测试单独合跑。全量命令可能在补测试前已完成 collection，最终数量以原始日志为准，不将新增两项计入未执行的全量命令。
- Ruff（src/muse、tests/muse/commerce）、OpenAPI 校验和 git diff --check 通过。完整审查及未判定边界见 review-results-round-4.md；版本字段严格类型、token decode 断言仍待互操作测试补充。

## 最终结果

根目录 `.venv\Scripts\python.exe -m pytest -q`：**1280 passed / 3 skipped / 1 failed / 2 warnings**，486.10 秒；唯一失败仍是原 `test_stop_script_matches_serialized_process_time[True-False]` 的 Windows taskkill Access denied。证据 work/commerce4-full-final.log，不标全量通过。

该次全量 collection 覆盖新增 47 项；随后新增的 2 项合法数值边界已在单独合跑中执行，本轮新增共 49 项均通过，四个模块合跑 64 项通过。未修改生产代码后重复全量；测试范围以以上两份原始日志分别说明。

P3 仍未完成：没有公开写 API、真实审批存储/报告绑定、PHP 插件写端/原子资源锁、staging 部署或购买链路验收。原模型配置和 coding 入口保持。没有 API 费用、真实店铺写入、Git 提交/推送和 Desktop 同步。
