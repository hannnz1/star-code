# Feature 011 Skill 系统实现报告

## 已实现

- 两层 Skill 发现：用户级 `~/.mewcode/skills/` 与项目级 `.mewcode/skills/`，项目同名覆盖用户。
- 支持 `SKILL.md`（可选 YAML frontmatter）以及 `skill.yaml + prompt.md` 两种格式。
- 启动期只加载元数据，执行时通过 `getFull` 重读正文；热重读失败保留旧缓存。
- Skill 自动注册为 `/<name>` 提示词命令，并提供 `/skill`、`/active-skills`、`/reload-skills`。
- inline 与 fork 两种执行模式；fork 支持 `none/recent/full` 上下文种子、取消传播、事件展示和 token 用量回并。
- Skill 可通过 `provider` 和 `model` 选择已配置 provider 或覆盖模型；配置不存在时返回明确错误。
- `LoadSkill` 只读工具：允许模型按自然语言意图加载 Skill，并把 SOP 固定到后续轮次环境上下文。
- `/clear` 清除活动 Skill，但保留磁盘 Catalog；重新加载会原子替换 Skill 命令，不影响内置命令。
- `InstallSkill` 写操作工具：支持 GitHub tree URL 与 raw `SKILL.md` URL，经 GitHub Contents API 安装到用户级目录。
- 安装安全限制：仅 HTTPS GitHub 域名、拒绝重定向和异常文件类型、限制单文件 1 MiB、总计 8 MiB、64 文件、4 层深度；使用临时目录校验后原子移动。
- 安装成功后立即刷新 Catalog 与 Slash 命令，无需重启。
- inline、fork 和 `load_skill` 激活均向当前 session 的 `skill-invocations.jsonl` 追加 name/source/timestamp/sessionId；审计失败不阻断 Skill。
- fork recent/full 保留结构化 tool call/result 历史，recent 截断点不会落在 tool result 中间。

## 当前边界

- Slash Command 仍遵循 ch10 的零参数设计；`$ARGUMENTS` 的程序接口已具备，但 `/<skill> args` 暂不开放。
- `skills.sh` 未启用：其稳定下载协议和可信来源规则尚未在 Spec 中定义；当前只接受可验证的 GitHub URL。
- GitHub 分支名含 `/` 时 URL 的 ref/path 边界不明确，当前要求使用不含 `/` 的 ref 或 raw URL。
- 远程安装不实现 OAuth、代理、自动更新、覆盖已有技能或依赖解析。

## 验证范围

- 单元测试覆盖目录优先级、两种文件格式、BOM、损坏技能隔离、热重读、参数渲染、fork 种子、命令卸载重载、LoadSkill、provider/model 解析及安装 URL 安全校验。
- 人工验证已覆盖 inline、YAML 分离格式、热重载、`/clear`、`/resume` 与 fork 后继续对话。
