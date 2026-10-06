# 第五批审查结果

一次独立审查，仅发布器与既有模块的集成；未重复前批，修复后无二次审查。

三项 Important：

1. 目标重新绑定后旧操作可能对新站点对账。新增持久 target_bindings；Publisher、直接 ReceiptReconciler 在查账/网络前确认。跨实例重启有效；未知来源旧账本拒绝建立绑定。换站点必须新 connection_id。
2. approval_lookup 的三处异常可能泄露内部消息。普通 Exception 转 VERIFICATION_UNAVAILABLE；取消继续传播；发送标记后的错误不解除待对账。测试分别覆盖三次 lookup，零 POST。
3. 当前操作之外的批准依赖未比较真实快照。改为检查全部批准 preconditions；currency 改变、页面未变也零 POST。前序合法步骤改变依赖不能隐式更新原批准，P7 必须实现明确的后继状态/回执验证。

RED：work/commerce5-review-red.log（5 failed / 14 passed）。修复后五模块 85 passed，work/commerce5-focused-final.log。

未判定项：真实 WordPress、当前持久审批 provider 正确性、OS 隔离、物理掉电、远端原子锁。这些仍是部署/插件/P7 验收边界，本批 default-disabled，无公开写路由。不能用预检查代替插件授权/所有权/原子指纹检查。审查未发现额外 Minor，之前批次的延后项仍保留。
