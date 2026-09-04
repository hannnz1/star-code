# Feature 006 实现报告

## 已实现

- 五层权限判定及短路。
- 内置危险命令黑名单。
- 复用并强化 ToolContext 工作区/符号链接防逃逸。
- 用户、项目、本地三级 YAML allow/deny 规则和默认模式。
- default / acceptEdits / plan / bypassPermissions 模式。
- Shift+Tab、`/plan`、`/do` 模式切换。
- 终端审批三选一及本地精确规则持久化。
- 拒绝结构化回灌，Agent Loop 不终止。
- `.starcode/permissions.local.yaml` 已加入 gitignore。

## 规格校正

- 仓库原有路径保护并非“裸奔”，本功能把它纳入正式沙箱层。
- 旧环境变量写/Bash 开关由权限流水线取代。
- 仓库使用 Gradle 而非 Maven。
- 当前 UI 为滚动式终端，模式通过启动/切换提示显示，不是固定底栏。

## 人工测试

请验证 default 写入审批的三个选项、永久规则重启、Shift+Tab 四档循环、审批中 Esc/Ctrl+C，以及 bypassPermissions 下危险命令仍被拒绝。
