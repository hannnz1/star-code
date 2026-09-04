# Spec 文档质量整改记录

## 本轮发现的问题

1. 根目录 V1 草案与 `specs/chapter/` 同时声称权威，需求冲突时无法判断实现依据。
2. 章节状态使用 `Implemented/PARTIAL/完成` 等多套写法，且把“缺人工证据”误写成“代码未实现”。
3. ch08、ch09、ch11 默认 Conversation 只有纯文本，和 Agent Loop、JSONL、Fork 的结构化工具协议矛盾。
4. 一些需求把多个可独立失败的行为写在同一个 F/AC 下，无法建立测试到需求的一对一追踪。
5. Plan/Tasks 中残留 `com.mewcode`、Maven、Spotless、Lanterna 等并不属于 Star Code 的实现约束。
6. 后续章节覆盖前文时没有写 override 关系，例如 ch14 为 slash 命令增加受控参数能力。
7. implementation report 的测试数量、会话清理天数和已知缺口会随代码演进而失真。
8. 缺少全局数据合同，导致工具调用可以在 UI、Conversation、JSONL、Provider 四处使用不同表示。

## 已完成的文档修复

- [`README.md`](README.md) 成为唯一规格索引，并定义 DRAFT/APPROVED/PARTIAL/IMPLEMENTED/VERIFIED/SUPERSEDED。
- 根目录四份 V1 文档已标记 SUPERSEDED，不再与章节规格竞争。
- [`architecture-contracts.md`](architecture-contracts.md) 固化结构化消息、调用闭合、JSONL 无损、replacement 恢复、事务切换和验证证据合同。
- ch08、ch09、ch10、ch11 已重写为可追踪的 G/F/N/AC 编号，拆开原先成组需求。
- ch04/ch08/ch09/ch11/ch13 的结构化历史表述已统一；ch14 的命令参数扩展被记录为对 ch10 的显式覆盖。
- 所有实现章节状态统一为大写枚举；真实 Provider、Git、tmux/iTerm2 只缺验证时标记 IMPLEMENTED 而不是 PARTIAL。
- implementation report 已更新为当前代码与测试事实，不再使用旧测试数量或旧纯文本 Conversation 假设。

## 后续编辑规则

- 一个 `F` 只描述一个可独立实现的行为，一个 `AC` 至少能映射到一个确定性验证。
- Spec 写目标，Plan 写设计，Tasks 写顺序，Checklist/Report 写证据；不得把当前缺陷反写成目标。
- 新章节改动已有公共模型时，必须先更新全局合同并列出被覆盖的需求编号。
- “自动测试通过”“人工测试通过”“代码完成”是三个不同结论；只有前两者都有证据才使用 VERIFIED。
- 所有数字型限制必须写清单位、边界、超限行为和失败降级。
- 所有异步/持久化功能必须写清所有权、原子边界、取消、关闭和恢复语义。

