# MUSE Python 集成开发版

本目录以 `mewcode-python` 为源码基线，整合 MUSE 的持久化 Worker、网页工作台、资料整理和研究能力。原 StarCode 模型、服务地址、代理和凭据来源继续使用原配置。

**当前尚未达到“完整替代 Java”的验收标准。** 不覆盖桌面上的 StarCode 或 mewcode-python 原项目。来源标注保留；本地尚未确认上游主项目的根级许可证，公开分发前需核实。

## 已接入的运行路径

- `muse api`、`muse worker`、`muse terminal`、`muse tui` 共用任务服务与数据库。
- 编程工具具有文件检查点、审批、真实验证退出码和受控进程树。
- 网页研究、资料提取整理、成果版本、来源记录、项目记忆与历史导入。
- MCP HTTP/stdio 发现与调用、分页目录、Markdown/YAML Skill、固定提交技能安装、同步与异步 Hook。
- 内置与项目角色、指定提交的工作树子任务、审批后的快进合并和保守回收、持久化团队消息与依赖看板。
- 对话检查点、文件回退、不确定外部操作核对、状态备份及旧库升级/回滚。

`mewcode` 命令和 `python -m mewcode` 已改为统一服务的兼容入口：默认进入新 Textual 界面，`-p` 通过 HTTP 提交持久化任务，`--remote` 启动同一个回环 Web API。旧私有运行函数作为基线参考保留，但公开启动入口不再调用它们。具体命令、恢复操作和改变的 Java 行为见[运行说明](docs/python-runtime-operations.md)。

## 启动

需要 Python 3.12+；从源码构建网页还需要 Node.js/npm；工作树需要 Git。

```powershell
.\Setup-MUSE.ps1
.\Start-MUSE.ps1 -Config 'C:\Users\Administrator\Desktop\project\star code\config.yaml'
```

API 和 Worker 启动后，可另开终端使用同一数据目录：

```powershell
.venv/Scripts/python.exe -m muse tui --data-dir .muse --workspace 'C:\Projects\your-project'
# 或纯文本终端
.venv/Scripts/python.exe -m muse terminal --data-dir .muse --workspace 'C:\Projects\your-project'
```

若启动时使用了其他端口，终端也传相同的 `--port`。输入 `/help` 查看已接入命令；`/children` 查看子任务，`/child ID` 进入其工作区，`/back` 返回。关闭终端不取消后台任务；取消请使用任务控制。

```powershell
.\Stop-MUSE.ps1
```

正式 wheel 必须在 `npm --prefix frontend run build` 后构建，工作台资源随包提供。开发模式安装不要求预先构建前端。

## 验证证据与待办

- 最新交付回归见 `reports/delivery-ui-final.xml`；此前 `reports/delivery-final.xml` 为 914 通过、2 跳过。每次运行独立保留，不把定向测试机械加到旧全量成绩中。
- 三类原配置真实试用：`reports/practical-integration-20260927`。编程先失败后通过，测试文件及三份原文档未改。研究首版有质量缺口，追加的 3.12 修订记录单独保留；任务状态不替代人工质量验收。
- [开发记录](docs/progress.md)、[209 文件行为映射](docs/java-migration-matrix.csv)、[58 测试文件对照](docs/java-test-matrix.csv)、[224 项断言意图和改变的契约](docs/java-behavior-audit.md)、[源文件哈希](docs/source-manifest.json)。映射是可追溯依据，不冒充所有 Java 断言逐项等价通过。
- [独立 Windows 验收](docs/clean-windows-acceptance.md)：测试环境信息待用户提供。当前机器文件符号链接权限不足，不能以跳过代替通过。

已执行两批固定 20 场景 × 3 轮 Benchmark，全部 120 次记录保留在 `reports/benchmark-python`。第二批复核为 35 通过、17 失败、8 阻塞（包含一项有依据的字面检测误报，原记录保留）。间歇性模型连接失败和本机文件符号链接权限使其不能放行。两批不拼接“最好成绩”；旧工程的 56 PASS / 1 FAIL / 3 BLOCKED 历史结果不改写。

本机 wheel 构建、无 Java PATH 冒烟、v1→v7 数据恢复和原目录回滚保留均有证据；这些不替代独立干净 Windows 验收。原项目清单中的 407 个源文件哈希复查无变化。

## 旧命令兼容与审批续期

API 和 Worker 必须已启动；兼容入口使用相同数据目录和端口。例如：

```powershell
.venv/Scripts/python.exe -m mewcode --data-dir .muse --workspace 'C:\Projects\your-project'
.venv/Scripts/python.exe -m mewcode --data-dir .muse -p '先检查项目结构，不修改文件' --mode plan --output-format stream-json
```

`-p` 退出码：0 为任务成功，1 为失败／取消，2 为需要审批、输入或恢复，3 为客户端等待期限到达。后两种状态保留任务，可在网页或终端 `/use ID` 继续；等待超时不取消后台任务。JSON 输出使用持久化 `event` 和 `task` 记录，不承诺与旧原生事件格式逐字段相同。

过期审批可在网页点击“续期后重新审阅”；终端先 `/approvals`、再 `/renew ID`，然后重新 `/approvals` 和 `/approve ID`。续期不会批准或执行操作。

兼容限制：不支持旧 `bypassPermissions` 自动放行及 `--teammate` 子进程标志；参数会明确报错。`--remote` 只启动本机 API，Worker 另行启动。`--config`／`--provider` 用于核对正在运行的服务配置，不能通过客户端参数热切换服务端模型。完整选项与命令的行为迁移仍需验收。
