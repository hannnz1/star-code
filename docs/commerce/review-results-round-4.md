# 第四批审查结果

单次独立审查，仅四个新增文件，无二次审查。

- Critical：无。
- Important 1：已签名畸形 JSON 深度或巨大 issued_at 可抛 RecursionError/OverflowError。两个签名正确的 fixture 复现（RED），异常统一转脱敏 PERMISSION_DENIED（GREEN）。不是越权绕过。
- Important 2：商品价格格式/精度与库存上限不符合现有导入。7 项 RED；增加导入相同 decimal grammar 与 2147483647 上限，GREEN。另校验最大/最小合法数值保持原字符串不四舍五入。
- Minor（延后）：仅断言明文不在 base64 token 中不能充分证明内容排除；后续严格 claims 测试应 decode 并逐字段检查。本批代码只放操作 digest，不放商品/页面正文。
- 未判定：持久批准、操作属于已批准 ChangeSet、真实验证报告、当前资源/远端所有权、OS 隔离。全部是 P7/插件集成 gate，本批不宣称完成。
- Ruling：content_sha256 是 blueprint/draft 来源摘要，无法仅凭 ZIP 重新计算；本批只验证 archive/package/固定代码/manifest，不证明该来源摘要的真实性。须后续验证报告与变更集绑定，不能凭任意元数据发布。
- Ruling：Python equality 接受已正确签名的 v:true 与 v:1，但当前唯一 issuer 输出 v:1，修改后签名失效；本批不作为已存在绕过。插件互操作前仍需严格版本类型 wire schema；若签名来源扩展，此边界必须补测。

RED evidence: work/commerce4-review-red.log（9 failed / 38 passed）。修复后 work/commerce4-focused-final.log（47 passed）；边界与旧账本/回执一起复验见 commerce4-boundaries-final.log。全量最终结果见 checkpoints/round-4.md。
