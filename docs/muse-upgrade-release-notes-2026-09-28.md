# MUSE Python 升级说明

依据 SPEC-MUSE-UPGRADE-001。功能开发与离线验证完成情况见 `muse-upgrade-status-2026-09-28.md`；真实平台、模型质量和用户验收单独记录。本次未改所选 StarCode provider/model/密钥，未调用收费 API，未推送 GitHub。

## 使用入口

- 新任务权限默认为 `default`：读取不审批，写入及执行审批；`acceptEdits` 允许工作区编辑、执行仍审批；`plan` 只读。Web 选择器、CLI `--mode`、TUI/终端 `/mode` 共用服务。运行中不能变更策略，旧任务冻结为 legacy。
- Web 新任务可以勾选“协调者”；终端 `/coordinator on` 对新任务生效。根任务只读取、委派、发送消息、审查和受审批集成，不能直接编辑/运行命令。最终修改需要**父工作区** verification 角色的真实成功命令回执；其他 worktree 的测试不能代替统一验证。
- `/skill NAME` 查看；`/run-skill NAME [ARGS]` 创建原子持久化执行请求。无冲突别名可直接调用，内置命令优先；`GET /api/workspaces/{id}/skills` 给出禁用原因。参数按原文保存，无终端 Shell 拼接；源文件变更后旧请求拒绝执行。
- `/trace [TASK_ID]` 查看任务树及审批/工具/维护事件；`GET /api/tasks/{id}/trace?format=jsonl` 导出。直接委派父 ID 与 follow-up 父 ID 分开，工具耗时来自单调时钟。
- `/do` 从完成的只读计划创建新任务，保存计划 ID、结果哈希、用户请求；源内容不匹配时拒绝。`/rewind CALL_ID files` 恢复文件，`/rewind SEQUENCE conversation PROMPT` 创建会话分叉。`both` 不支持并在执行前拒绝。
- `/thinking` 显示服务摘要及进行中片段；Web 实时摘要可见。没有返回摘要明确显示“未返回摘要”；签名/encrypted 块只存在私有检查点，不能导出为公开 trace。
- `/memory-candidates`、`/confirm-memory ID`、`/withdraw-memory ID`、`/memory-history ID`、`/memory-jobs` 管理维护结果，Web 可确认/撤回候选。`GET /api/tasks/{id}/memory-recall` 查看 fallback、选中版本、截断及未选原因。
- `/sandbox` 显示探测能力；修改用户配置后重启用于新任务。旧任务保留冻结策略。

## 可选设置示例

以下字段合并进现有 YAML，不替换 providers。示例维护仍关闭；用户启用维护前指定预算。

```yaml
memory:
  auto_extract: false
  auto_consolidate: false
  semantic_recall: false
  budget_tokens: 0
  max_requests: 8
  recall_top_k: 10
instruction_roots: []
agent_roots: []
sandbox:
  policy: off
  runtime_roots: []
  network_allowlist: []
```

自动维护仅提取有明确用户来源的根任务：成功且非只读的任务及其压缩前来源快照。模型委派/角色/Skill 提示不是用户事实。项目无冲突事实可发布；用户级和冲突内容待确认。整理要求 ≥24 小时及 ≥5 个新增合格会话，只自动归并完全相同的事实；冲突需要确认，原证据不物理删除。

维护模型与普通任务相同，不提供任何执行工具。请求预留输入字节与最大输出的保守 Token 配额，消耗独立全局维护配额及根任务模型请求上限；费用未知保留未知，不能报为零。失败/租约过期不自动重发可能已收费的请求。预算耗尽标记 `BUDGET_EXHAUSTED`。关闭各类开关后对应队列不继续发新请求。

语义召回使用同一 provider，最多 100 候选、10 条注入；失败回退本地检索并标注 `fallback=true`。新投影只包含生效记录，内容与来源受配额截断。撤回不是删除不可变会话历史，历史审计仍可能保留旧引用，不能把它当当前有效记忆。

thinking 默认不额外启用。用户明确确认所选服务支持后，可在该 provider 配置 `thinking: true`、`thinking_capability: openai-reasoning` 或对应 Anthropic manual/adaptive、`reasoning_effort`、`thinking_summary`。未知组合 `UNSUPPORTED_THINKING`；manual budget 至少 1024 且小于 max_output_tokens。关闭不添加显式参数，也不声称模型内部完全不推理。参考：[OpenAI reasoning](https://developers.openai.com/api/docs/guides/reasoning)、[Claude extended thinking](https://platform.claude.com/docs/en/build-with-claude/extended-thinking)。

## 来源与平台边界

来源按显式用户目录→工作区→工作区内当前目录祖先→local 加载，后面的项目偏好优先，相同文件去重。@ 引用只进入工作区或显式可信目录，链接/循环/深度边界保留。角色 builtin 名称不可覆盖；其他角色项目覆盖用户目录，所有来源可查。创建时冻结正文、哈希和顺序；`/reload` 在停止状态创建新版本，不自动改变运行任务。

bwrap/Seatbelt 实现为默认拒绝网络、工作区外文件和任意宿主根挂载的 argv 包装；只放行工作区、临时目录和必要运行时。required 后端缺失、变化或启动失败绝不裸执行。Windows 明确 `OS_SANDBOX_UNSUPPORTED`。本轮不能可靠实施网络允许列表，非空列表明确拒绝 `OS_SANDBOX_NETWORK_ALLOWLIST_UNSUPPORTED`，不能偷偷放开全部网络。Linux/macOS 真实探针未验收前不宣称内核隔离已通过；部分开发工具可能需要显式运行时目录，不能用关闭沙箱掩盖 required 失败。

## 迁移与回退

1. 停止旧 API/Worker，使用现有 state-backup 命令保存完整状态包。
2. 启动新版时 schema <10 的数据库自动产生 `migration-backups/v*-before-v10-*.sqlite3`，SQLite online backup 后做 integrity_check；迁移事务提交审计。旧任务权限和历史审批可查。
3. 旧记忆保留 ID、作用域和内容，来源缺失标为 legacy/manual；新修改和撤回保留版本。
4. 回退时停止新版服务，另存升级后的完整状态包，然后用迁移前完整包恢复至新目录，再启动对应旧版。旧二进制不能直接读 schema 10。数据库快照不是完整附件/配置备份；升级后新任务不会自动搬回旧版。

SQLite 继续是权威存储；JSONL 是导出格式。子 Agent 继续使用持久化 Worker；不恢复 tmux/iTerm2、--teammate、bypassPermissions、远程自动 0.0.0.0 绑定、旧 NDJSON 逐字段兼容或联合 both 回退。
