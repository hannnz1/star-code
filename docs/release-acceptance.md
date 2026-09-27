# MUSE Python RC7 验收记录

版本 0.3.0rc7；冻结源码提交 `7ccedb5`；当前发布判定 **NOT_ACCEPTED**。Python 已承担 Agent、持久化任务、API、Worker、终端、审批、研究、文档与扩展运行时；网页仍使用 React/TypeScript。原 StarCode 模型与服务配置沿用，未覆盖桌面上的两个原项目。

## 已完成的工程验证

- 完整 pytest：959 通过、2 跳过、2 条第三方依赖弃用警告，见 `reports/rc7-full.xml`。跳过项涉及基线外部在线测试及本机无法创建的文件符号链接，均不记通过。
- Ruff、OpenAPI 类型同步、70 包锁文件离线一致性通过。前端源码未变，RC6 的 TypeScript/Vite 构建通过；RC7 wheel 包含 207 个条目和网页资源。
- 新本地虚拟环境在 Java/Javac/Gradle 不在 PATH 时，wheel 的 API 200、网页 200、Worker 完成、两个命令入口及进程启停均通过；这不是独立干净 Windows 机器。
- 180 动作权限回放：中位数 9、总确认 94、50/50 风险探针拒绝，无正常动作错误。原 Java 的 8 次确认属于不同的会话授权策略，未复现。
- RC7 本机工程性能回放 p95：任务创建 6.60 ms、事件提交至浏览器可见 835.24 ms、取消状态确认 2.98 ms、进程树停止 93.39 ms、过期租约恢复 3.85 ms，见 `reports/rc7-performance.json`。未测 UI 点击延迟、跨机器耗时或独立进程 RSS，不能据此声称满足这些指标。
- 原 407 个登记源文件哈希保持不变；发行包内未检出原模型密钥、Java/JAR/class、数据库或私有配置。数据备份、旧 v1→v8 副本升级和恢复回归包含在全量测试中。

RC7 wheel：`dist/rc-7ccedb5/muse_personal_agent-0.3.0rc7-py3-none-any.whl`，SHA-256 `7da4011d981cb95e080e7f22b6286ff0177b5b666abfad6b51fa767053be10cb`。

RC7 源码 ZIP：`dist/rc-7ccedb5/MUSE-Python-0.3.0rc7-7ccedb5.zip`，SHA-256 `cf9a9d27d4250808d33d58525d721a94eced15309dfe8533fad118a67481b4b5`。两者均从同一冻结提交制作，哈希记录在同目录 `SHA256.json`；本验收文档作为包外证据单独交付。

## 自动 Benchmark 的真实结果

| 项目 | RC7 结果 | 结论 |
| --- | --- | --- |
| 原多 Agent 三题 | 1/3；text 通过，checkout 最终 Java 边界验证失败，numeric 未完成有效整合 | 未达到计划 3/3，不能宣称原指标完全迁移 |
| 原长上下文三次 | 第 1 次完整；后 2 次遇到服务错误，未完成 | RC7 不能沿用 RC6 的三次通过成绩 |
| 原 MCP FULL/LAZY 各十题 | 20/20 遇到同一服务错误，0 项完成 | 不能用 RC6 的 10/10 + 10/10 充当 RC7 成绩 |
| MUSE-Bench 固定 60 槽位 | 11 FAIL、49 NOT_RUN；11 项均发生模型服务错误 | 本批次中止，固定分母和原始失败全部保留 |

在运行中，原服务对一个仅含合成 “Reply with OK” 的最小请求返回 HTTP 200 与流内 `error` 事件；脱敏诊断只识别到 billing 相关文字类别，未得到可辨认的具体错误码。不能据此断定余额、组织额度或项目上限中的哪一项。错误证据见 `reports/rc7-provider-probe.json`、`reports/rc7-provider-event-probe.json`。为避免继续消耗调用，11 个业务用例连续失败后停止批次。请按 [OpenAI 官方 API 用量与支出排查说明](https://help.openai.com/en/articles/6614457-troubleshooting-api-usage-and-spend-limits)检查原配置所属账户的 API 余额、组织及项目限制；不要在聊天中粘贴密钥。

2026-09-27 按用户要求使用本机 OpenAI API 再试一次最小请求，仍为 HTTP 200、流内 `error`、脱敏类别 `billing`，见 `reports/provider-resume-probe.json`。本机 `OPENAI_API_KEY` 与原 StarCode 配置中的密钥相同，因此没有发现另一套可供切换的本机凭据；未继续发起需要模型输出的批量测试。

脱敏证据导出位于 `reports/release-candidate/7ccedb5/`，含 60 行 `manual-review.csv`：11 项 FAIL、49 项 NOT_RUN，不能当作人工可评分的完整正式批次。RC6 的完整旧批次是 57 项自动预筛待人工审核、3 项本机符号链接阻塞；详见 [RC6 封存报告](rc6-release-acceptance.md)。两个版本不可拼接或替换分数。

## 最后需要关闭的门槛

1. 模型服务恢复后，以固定 RC7 源码、原模型配置和同一预算重新完整执行长上下文、MCP 配对、原多 Agent 三题及 MUSE-Bench 60 槽位；所有新失败继续保留，不与旧轮次拼接。
2. 多 Agent 必须在同一候选的三题中达到 3/3，包括两个子任务实际提交、重叠、主任务复核整合与统一验证；当前 1/3 是未关闭的自动质量问题，不能转为人工待审。
3. 按 [人工 Benchmark 清单](manual-benchmark-handoff.md)审阅完整批次的事实、引用和成果，并由第二位独立人工评审复核文本通过项及争议项。
4. 按 [独立 Windows 验收](clean-windows-acceptance.md)在无 Java 的干净机器安装同一包，实际创建文件符号链接并通过越界拒绝用例；本机 WinError 1314 与跳过不能计通过。

发行范围还需要源项目主许可证核实；本包仅供本地验收，不公开推送或分发。8 小时耐久、完整 RSS 和单/多 Agent 加速比未测，不作为已实现指标。
