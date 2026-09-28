# Python 运行、恢复与 Java 替代边界

新版命令入口 `muse`、`mewcode` 和 `python -m mewcode` 共用 MUSE API/Worker。React 网页与 Textual 终端使用同一任务、审批和事件记录。保留的 mewcode 旧辅助类用于兼容与回归，不是默认启动的另一套 Agent。

继续通过 `--config` 或 `MUSE_STARCODE_CONFIG` 指定原 StarCode 配置。不复制密钥到新源码，不通过 Skill/角色元数据切换模型；API 和 Worker 必须一起使用同一配置。Python 要求 3.12 或更高版本。

## 查看与控制

- `/tasks`、`/use ID`、`/status`：选择并查看任务。
- `/pause`、`/resume`、`/cancel`：控制所选任务；取消父任务会取消后代。暂停所选任务不等于暂停所有独立后台任务。
- `/children`、`/child ID`、`/back`、`/team`、`/board`：查看子任务、消息组与共享工作项。
- `/approvals`（别名 `/permission`）：先查看实际动作，再 `/approve ID` 或 `/deny ID`。过期审批 `/renew ID` 后仍需重新查看并审批。
- `/skills`、`/skill NAME`、`/active-skills`、`/reload-skills`、`/agents`、`/hooks`、`/mcp`：查看配置及任务已调用的扩展。列目录不会执行扩展。
- `/model`、`/cost`、`/context`：查看选定模型与记录的指标；没有价格配置时，不把 token 数当成货币费用。
- `/compact`、`/reload`：只在无待执行调用的排队或暂停任务上操作；不会改变任务目标或绕过权限。

普通文本创建编程任务；`/plan`、`/review` 创建只读任务，`/do` 创建可修改任务。退出客户端不会停止 Worker 中的后台任务。`mewcode -p` 的返回码：0 成功、1 失败/取消、2 等待输入/审批/暂停、3 客户端等待超时。

## 对话与文件恢复

`/checkpoints` 列出模型轮次检查点。暂停任务或选择已结束任务后，执行：

```text
/rewind 2 conversation 从这里继续检查测试结果
```

该操作新建持久化任务，复制完整历史作为参考，不重放过去的工具、不自动回退工作区文件。原任务和证据保留。新任务预算重新开始，原有只读和工具限制保留。

`/rewind` 列出文件历史；`/rewind CALL_ID files` 使用对应文件快照恢复。外部编辑导致哈希不匹配时拒绝恢复。对话与文件恢复是两个独立动作，不提供隐式“同时全部回退”。

`/uncertain` 列出中断后无法确定结果的外部操作。实际检查外部状态后，才使用 `/resolve CALL_ID success|failed 核对依据`。人工声明仅用于解除“不确定”，不伪造成功测试退出码；需要执行 `/resume` 才会恢复任务。文件写入有单独的哈希核对路径。

## 扩展约定

项目说明支持工作区内的 AGENTS/MUSE/MEWCODE/STARCODE 文档与受限 `@` 包含；不自动读取工作区外的祖先或用户私有目录。说明以快照绑定任务，`/reload` 后在下一轮重新加载。

项目角色放在 `.muse/agents/*.md` 或 `.mewcode/agents/*.md`。工具限制与父任务取交集；隔离角色通过带 `role` 的 `spawn_worktree` 使用确切提交创建工作区。原配置模型不变。

技能支持 Markdown 或 `skill.yaml` 加 `prompt.md`；项目技能优先，显式 `skill_roots` 可增加外部技能根目录。安装工具只接受 `owner/repository`、完整 40 位提交、目录路径和名称，先审批后下载，拒绝覆盖现有技能。技能安装不自动执行其中代码。

Hook 的 startup/shutdown 表示任务运行边界；异步 Hook 是持久化子任务，共享预算并经过动作审批。父任务等待子任务结束；失败不会冒充完成。命令与 HTTP Hook 不因写在配置里而跳过审批。

MCP 从选定配置加载：发现服务器也需要审批，发现不等于批准远程工具调用。HTTP 不自动重定向或继承环境代理；stdio 使用受控进程树。声明 readOnly 的远端工具同样不能自行获得执行权限。

团队工作项支持依赖、认领、完成、释放、取消与版本检查。成员结束时释放未完成的认领；父任务不能在工作项仍未完成时报告成功。独立任务组不可互相读写团队消息。

`/worktree` 查看保留的子工作区。`worktree_manage` 提供审批后的 review/merge/integrate/remove：merge 仅快进；integrate 对经过复核的确切父/子提交执行普通合并，支持两个独立子分支。两者都要求任务结束、工作区干净；冲突保留给用户处理，不自动 reset。删除要求子任务结束、无活动任务、包含忽略文件在内完全干净且提交已合入父分支。不自动删除分支、不复制私有忽略文件、不执行仓库 Hook。

## Windows 深路径 worktree

升级实现会在创建与退休时校验 Git 子进程的路径限制。默认路径过长时，使用就近较短祖先目录中的独立命名空间；实际绝对目标在审批中展示并冻结在任务检查点。可在选定配置中明确指定短根：

```yaml
worktrees:
  managed_root: C:/MUSE/checkouts
```

根目录不能位于私有应用状态目录，也不能通过链接替换。修改配置只影响新任务，不移动旧工作树或改变待审批任务的目标。无法安全支持的路径返回 WORKTREE_PATH_UNSUPPORTED，且不会创建分支或目录。Git 内部命令采用等价相对路径；审批仍绑定绝对路径和提交。

未解决的创建、整合或当前有效隔离子任务失败，不能仅凭模型最终文字标为成功。同等操作重试成功可以消除之前的失败；其他子任务成功不能替代失败工作。用户选择串行处理时，创建明确的串行后续任务，保留原失败记录。

## 分页读取和有界搜索

`read_file` 不传 offset/limit 时仍返回原始全文。传入任一参数后返回 JSON：`lines` 包含原始 1-based 行号和文本，offset 从 0 开始，默认 limit=2000，合法范围 1–10000；`next_offset=null` 表示读完。CRLF、UTF-8 BOM 不改变行号。跨行敏感内容在切页前识别，受影响的整行遮蔽，不能从中间页读出私钥正文。

`search_text` 默认字面、不区分大小写；regex=true 开启正则，case_sensitive=true 区分大小写。默认上限为 500 候选文件、100 命中、正则单文件 250ms、整次搜索 5s，结果携带 `limits` 和 `truncation_reason`。超时返回 `SEARCH_TIMEOUT` 与部分结果，非法正则/分页参数返回 `INVALID_ARGUMENTS`。候选枚举纳入总预算；底层文件系统调用在线程中执行，取消后停止继续遍历，该调用本身在返回前不能强制中断。

正则在独立 Python 子进程执行，超时/取消后终止并等待退出，不依赖阻塞正则的协程超时。它仅处理文本，清除模型凭据环境变量；这不是 OS 沙箱。路径保护、16 MiB 文件上限和敏感目录限制继续生效。

大分页或搜索 JSON 仍可能触发现有 output offload；通过工具回执 `metadata.offload_id` 和 `read_offload` 读取完整成果，不能把截断的展示字符串直接当完整 JSON 解析。

## 状态备份与回滚演练

先停止 API/Worker，确保没有正在运行的任务。备份包含本地状态与访问令牌，应保存在私有位置；不提交、上传或公开分享。工作区文件和外部模型配置不包含在状态备份中。

```powershell
muse --data-dir C:\MUSE\state backup-state --output C:\MUSE\backup\state.zip
muse --data-dir C:\MUSE\restored restore-state --source C:\MUSE\backup\state.zip
```

恢复目录必须不存在。恢复会校验文件清单和哈希，迁移数据库、重新定位成果/历史快照路径，将未完成任务暂停、未知副作用标为待核对、旧审批作废。原目录和工作区内容保留。核对后以恢复目录同时启动 API 和 Worker；需要回滚时停止服务并重新指向保留的原目录。

0.3.0rc1 使用数据库 schema 8，增加手动压缩原文归档；旧轮次检查点保持原样。升级前先备份。回滚旧版本时恢复升级前的副本，不把已升级的新数据库直接交给旧程序。

开发机的备份/恢复、成果路径迁移、真实进程崩溃恢复均有自动回归。独立干净 Windows 的安装、文件符号链接和无 JVM 验收见 `clean-windows-acceptance.md`；尚未提供环境前不能把这些标为通过。

## 对照证据

`java-migration-matrix.csv` 覆盖 209 个生产文件，`java-test-matrix.csv` 覆盖 58 个测试/辅助文件，`java-behavior-audit.md` 列出关键断言意图与替代契约。映射不代表每一个 Java 内部实现细节保持相同；逐次审批、持久化任务、确定性压缩及保守工作区管理是明确改变的行为。

最终测试结果以本轮 JUnit 和 Benchmark 报告为准。旧工程不删除，原始失败记录不覆盖；源项目主许可证未核实前不公开分发。
