# 独立 Windows 验收

状态：用户确认有独立环境，连接方式与环境信息待提供。当前集成版仍在开发，本文件不代表发布批准。

## 环境信息

需要 Windows 版本、可用连接方式、测试目录、Python 3.12 或更高版本，以及文件符号链接权限是否可用。不要把模型密钥写入聊天、报告或截图；模型继续使用原 StarCode 配置，在测试机本地指定配置路径。

## 必须保留的证据

| 项目 | 通过标准 | 证据 |
|---|---|---|
| 无 Java 依赖 | 测试机没有 java、javac、gradle，仍能安装、启动、运行和打包 | 工具检测、安装与启动日志 |
| 干净安装 | 从新源码包或 wheel 安装，不借用开发机虚拟环境 | Python 版本、锁文件、安装输出 |
| 文件链接 | 测试确实创建 Windows 文件符号链接，并拒绝越界读取；跳过不计通过 | 对应测试输出 |
| 网页与终端 | 创建、暂停、恢复、取消、审批、补充输入、查看成果及子任务有效 | 浏览器报告与终端记录 |
| 后台恢复 | 中断 Worker 后，已完成操作不重复；不确定外部操作等待核对 | 数据库状态、事件和恢复测试 |
| 工作树 | 指定提交、父目录未提交内容保留、子任务能读写验证、结束后保留工作树 | Git 状态与任务记录 |
| 编程／研究／资料 | 三类真实任务各有可检查成果，沿用原模型；外发仅限明确授权文件 | 输入清单、实际输出与验证记录 |
| 正式 Benchmark | 按测试标准 G1—G8、固定 20 场景 × 3 轮执行；跳过和阻塞独立列出 | 原始记录与汇总 |
| 迁移／回滚 | 用测试副本演练数据升级及恢复旧副本，不操作唯一生产数据 | 迁移前后哈希和恢复日志 |

## 本地夹具回归命令

以下在集成工程根目录运行。先完成依赖安装和前端构建；不得将已有开发机环境复制后冒充干净安装。

```powershell
uv sync --all-groups
npm --prefix frontend ci
npm --prefix frontend run build
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path (Get-Location) 'work/browsers'
.venv/Scripts/python.exe -m playwright install chromium
$env:MEWCODE_TEST_API_KEY = ''
.venv/Scripts/python.exe -m pytest tests -q --junitxml=reports/clean-windows.xml
uv build --wheel
```

`MEWCODE_TEST_API_KEY` 留空，以免原基线的独立在线测试使用其他服务。真实模型验收是另一项独立操作，必须记录实际配置和获授权的输入清单。

文件符号链接用例：

```powershell
.venv/Scripts/python.exe -m pytest tests/test_permissions.py::TestPathSandbox::test_symlink_escape -v -rs
```

该用例在当前开发机返回 WinError 1314 时会明确跳过。独立机验收要求该用例真正通过；不能把权限错误改成断言成功，也不能用目录 junction 替代文件符号链接。

完整替代结论还取决于 Java 行为映射、终端统一和剩余扩展功能，不能只看本文件列出的测试是否通过。
