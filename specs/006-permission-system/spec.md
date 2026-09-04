# 权限系统 Spec

## 背景与目标

Star Code 已能自主调用工具。本功能在 Agent 编排层增加不可绕过的命令黑名单、工作区路径沙箱、三级配置规则、四档权限模式和人在回路审批；拒绝以结构化工具结果回灌，不终止 Agent Loop。

## 五层流水线

1. 危险命令黑名单：命中即 Deny，任何模式和规则均不能放行。
2. 路径沙箱：文件类工具只能访问启动工作区；拒绝绝对路径、`..` 和符号链接逃逸，新文件按现存祖先判断。
3. 规则引擎：本地 > 项目 > 用户，同层 deny > allow；支持 `Tool(pattern)` 精确或 glob 匹配。
4. 模式兜底：default、acceptEdits、plan、bypassPermissions，只返回 Allow/Ask。
5. 人在回路：Ask 时支持允许一次、永久精确允许和拒绝一次。

## 功能需求

- F1：内置不可配置黑名单覆盖根目录递归删除、格式化、块设备写入、fork bomb 和磁盘操作。
- F2：Read/Write/Edit/Glob/Grep 走工作区沙箱，Bash 不做路径静态推断。
- F3：友好工具名 Bash/Read/Write/Edit/Glob/Grep；`*` 和文件路径 `**` glob。
- F4：加载用户 `~/.starcode/permissions.yaml`、项目 `.starcode/permissions.yaml`、本地 `.starcode/permissions.local.yaml`；缺失/非法安全降级。
- F5：default 自动允许只读；acceptEdits 自动允许文件编辑；plan 保持只读工具集；bypassPermissions 自动允许非黑名单、非越界调用。
- F6：逐层短路，未知类别按 Ask。
- F7：Shift+Tab 循环切换四档模式；`/plan` 进入 plan，`/do` 返回 default。
- F8：审批支持方向键/回车及数字 1/2/3；永久允许写入本地配置。
- F9：Deny 生成含来源的 `PERMISSION_DENIED_*` 工具结果，保持调用 ID 和顺序并继续 Loop。

## 非功能需求

- 黑名单和沙箱不能被 bypassPermissions 绕过。
- 只读批处理继续并发，不触发审批。
- 审批可由 Esc/Ctrl+C 取消，不退出程序。
- Provider 适配层不包含权限逻辑，OpenAI/Anthropic 行为一致。
- 本地权限文件被 `.gitignore` 排除。
- 本项目使用 Java 21 + Gradle，以 `gradlew test shadowJar --warning-mode all` 验收。

## 已知实现边界

- 黑名单是启发式防御，不是 OS 沙箱。
- 当前滚动式终端没有固定底部状态栏；模式会在启动和每次切换时明确显示。
- 本章不做网络限制、资源配额、审计日志、MCP 工具权限或多工作区授权。

## 验收

自动测试覆盖黑名单不可绕过、路径越界、新建嵌套路径、规则精确/glob、deny 优先、三级优先级、配置降级、模式矩阵、拒绝回灌继续 Loop、既有 Agent/缓存回归。真实终端另验收 Shift+Tab、三选一、永久规则重启生效及审批取消。
