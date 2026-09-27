# MUSE 模型性价比试验

日期：2026-09-27。用户要求在给原 API 账户充值后改用更有性价比的模型。MUSE 保留原 StarCode 的 OpenAI Responses 地址、代理及环境变量凭据；原 `config.yaml` 未修改。`Start-MUSE.ps1` 默认以 `MUSE_MODEL=gpt-6-luna` 启动 API 与 Worker，`-Model gpt-5.4-mini` 可以切回原模型。直接运行 Python 命令时，未设置 `MUSE_MODEL` 仍读取原配置中的 `gpt-5.4-mini`。

## 价格和适用范围

2026-09-27 查阅的 [OpenAI 官方 GPT-6 Luna 模型页](https://developers.openai.com/api/docs/models/gpt-6-luna)列出标准文本价：每百万输入 token $0.10、输出 token $0.50；它支持 Responses API 和函数调用，定位为聚焦、高吞吐任务。[GPT-5.4 Mini 模型页](https://developers.openai.com/api/docs/models/gpt-5.4-mini)列出每百万输入 $0.75、输出 $4.50，定位更偏向编程、子 Agent 与工具任务。价格和账户可用性可能变化，最终以 API 账单为准。

## 本机合成任务实测

两款模型各完成一次简短回复和一次指定参数的函数调用，四次均通过；原始用量见 `reports/model-value-probe.json`。Luna 又以原 StarCode API 地址、代理和密钥执行固定 MUSE-Bench 的第 1 轮 20 场景，结果为 **17 AUTO_PASS_REVIEW_REQUIRED、2 FAIL、1 BLOCKED**，见 `reports/model-value-evidence/luna-full1/summary.json` 和完整脱敏证据目录。154 份导出证据的哈希记录在同目录 `evidence-files.sha256.json`。R01 资料研究与 C02 代码修复另做过两项先导试验，均通过自动检查；先导结果不加到这一轮分数。

- D01：自动字面断言失败。产物包含三个正确预算，但采用 `USD 42,000` 等格式，而冻结断言要求 `Budget 42000 USD`。原始 FAIL 保留，等待人工语义审查。
- C01：只读代码分析漏列 `settings.py`，属于实际内容缺漏，原始 FAIL 保留。
- P01：本机 WinError 1314，不能创建文件符号链接；属于环境阻塞，不能算模型通过。

该轮记录 113,846 输入及 5,565 输出 token。按上述标准价并把输入全部视为未缓存，估算 $0.014167。历史 RC6 的 Mini 第 1 轮为 19 AUTO_PASS_REVIEW_REQUIRED、1 BLOCKED，记录 106,279 输入及 4,664 输出 token；同法估算 $0.100697。两个版本与运行时条件不同，这只是量级比较，**不是受控 A/B、账单金额或质量等效证明**；缓存、额外工具费用和重试成本未计入。

Luna 的本轮成本估算约低 85.9%，但 C01 缺漏表明其不可直接替代质量模型的复杂编程验收成绩。当前将 Luna 作为省钱试用默认；重要代码修改可以通过 `-Model gpt-5.4-mini` 使用原模型，或显式选用 Sol，并分别记录模型身份及结果。完整三轮、长上下文、MCP、多 Agent 和人工质量复核尚未针对 Luna 完成，不把其他模型成绩记给 Luna。

## RC8 质量模型边界

后续真实多 Agent 原夹具显示 `gpt-6-sol` 在修复父任务等待与最终验证顺序后的预冻结源码 `a416e60` 上达到 checkout、numeric、text **3/3**；同一源码的长上下文三次与 MCP FULL/LAZY 各十题亦完成。正式 RC8 质量批次固定使用 Sol，启动器的 Luna 仍为经济试用默认，原 `config.yaml` 的 Mini 模型、地址、代理和密钥来源不变。Sol 的结果不能转给 Luna 或 Mini；最终发布判定仍需 RC8 同一冻结源码的完整复测、业务 60 次、独立 Windows 和人工审核。模型价格以各自 [Sol 官方页](https://developers.openai.com/api/docs/models/gpt-6-sol)与[Luna 官方页](https://developers.openai.com/api/docs/models/gpt-6-luna)的当前信息和实际账单为准。

## 工程验证

`MUSE_MODEL` 覆盖只改变选中 provider 的模型 ID；缺省仍读取原配置值。回归测试同时确认原配置文件和 API 凭据不被改写。`muse doctor` 在 Luna 覆盖下通过；PowerShell 启动脚本语法检查及 Ruff 通过。完整自动回归为 **960 通过、2 跳过、2 条依赖弃用警告**，见 `reports/model-value-full-final.xml`。跳过项不计通过，独立 Windows 与文件符号链接验收仍未完成。
