# SDD ledger — plan: ../../MUSE基于mewcode-python的替代方案.md

2026-09-27 开发记录。

采用 executing-plans / TDD，在独立 outputs/muse-next 仓库的 muse-integration 分支实施。原 Java、mewcode-python、已有 MUSE 工程均未覆盖。

Ruling: 源目录没有独立 Git 仓库，当前任务无可用附加 worktree；建立独立副本并初始化 Git，避免修改来源目录。只复制包、测试和构建文件，不复制 .mewcode 的本机配置及技能；技能资源后续逐项审查来源与许可再导入。

共享接口：原 provider 配置 → 新模型客户端，先处理协议与密钥来源；工具 → Worker/权限/验证，尚待统一；扩展 → 持久化子任务，尚待接入。

## 本轮

- 锁文件依赖已安装，Python 3.12.14；初次沙箱网络失败，批准联网后成功。原锁文件未修改。
- 原测试实测：656 PASS / 4 FAIL / 3 SKIP，见 reports/baseline.xml。真实外部模型测试禁用，未向外部发送项目源码。
- 两项 provider 回归先 RED：openai-responses 不支持、忽略显式 api_key_env 导致误用 OPENAI_API_KEY。修复后 GREEN，配置与相关模块定向测试 57 PASS。
- provider 支持 StarCode Responses 别名及指定环境变量；指定变量缺失不降级为其他凭据，密钥字段从 repr 隐藏。代理、预算及完整启动兼容尚未完成，不能宣称原配置已经完整接入。
- 原失败用例修复：Agent 测试改用 tmp_path；空指令测试增加独立仓库边界；空技能测试隔离用户技能目录。保持原断言。
- 受限路径检查在 ancestor.exists() 抛 PermissionError，现将该步骤纳入 OSError 拒绝分支，不让路径权限检查崩溃。

## 待完成

阶段 1：逐文件 Java 映射、测试覆盖矩阵和完整源快照清单。
阶段 2：配置代理/预算兼容、结构化退出码、Windows 进程树和统一审批。
阶段 3：整合现有 MUSE Worker、数据库、API、工作台、研究与资料功能。
阶段 4：扩展统一接入并验证崩溃恢复及团队协作。
阶段 5：正式 Benchmark、干净主机、无 Java 发布和回滚演练。

当前是开发基线，不是全量替代发行版；尚未执行新的真实模型 Benchmark。原基线失败报告保留，不由新报告覆盖。

最终本轮全量回归：662 PASS / 3 SKIP，1 条未注册 timeout 标记警告；证据 reports/integrated.xml。跳过项不计通过。
