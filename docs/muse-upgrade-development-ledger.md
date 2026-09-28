# MUSE 升级开发日志

## 2026-09-28 — M2–M5 开发收口

- M2 RED：缺失 maintenance 模块；实现后关闭默认/去重/来源/确认/撤回/冲突/预算/语义/整理门槛和原证据22项相关通过。维护默认关闭，不消费实际API。
- M3 RED：4项入口失败；M4 RED：缺失OS模块。实现协调者统一工具限制、显式可信来源和角色快照、原子Skill请求、trace/plan、可选failclosed平台包装。
- Ruling: API与独立Worker都设置来源 snapshot_factory，新worktree子任务创建时冻结用户来源，不能延迟到领取时读取；用户reload在停止状态冻结新版本。
- Ruling: 自动记忆只接受用户根任务，不把模型委派、角色或Skill提示当用户事实。关闭开关后按作业kind过滤，保留队列但不发新请求。
- 独立全分支审查6项问题：子提示污染记忆、其他workspace验证冒充统一验证、Skill创建抢占窗口、隔离子任务无来源快照、关闭提取仍消费队列、trace父ID错误。全部6项回归先失败（review-red.log）再通过（review-green.log）；独立审查员复核6 passed，无六项范围内剩余阻塞。新增真实父workspace验证命令及审批后7 passed。
- Ruling: 不增加另一套Skill运行时；任务与pending_calls/source hash同事务INSERT。源变更拒绝旧请求，内置别名优先。
- Ruling: 沙箱网络允许列表无法可靠执行时明确拒绝，不放开宿主网络。Windows unsupported；Linux/macOS真实探针已准备，缺主机BLOCKED。
- U02补测 completed reasoning item无delta漏摘要：RED后修复，14协议项通过。流摘要Web/终端可见，内部协议仅私有checkpoint回放。
- Schema10新增自动迁移前SQLite online backup/integrity/audit；旧记忆ID/作用域不变。发现sqlite context manager不关闭连接造成Windows restore锁，明确closing修复后迁移/备份/策略29项通过。
- 第一轮全量1066 passed/2 skipped（128.84s）；最终全量1075 passed/2 skipped/2依赖警告（123.26s），work/upgrade-final/full2.log。随后仅添加真实平台probe（Windows SKIP）与保持原换行；产品逻辑未变。44项worktree/roles/skills/完成回归通过。
- Ruff、Web TypeScript/Vite生产构建、API类型、git diff --check通过。为不改动整文件，matched行保留HEAD换行，新增行LF。
- 60个预标注记忆夹具及SHA manifest已准备；需要双人工评审后冻结，API NOT_RUN/指标null，不用合成离线单例预填正式成绩。
- 收口文档：升级状态、release notes、human acceptance。真实模型和平台/人工门槛未通过，不能宣称Java完全替代版正式验收；所选模型/密钥配置未修改、收费API调用0、未推送，未伪造Git身份。

## 2026-09-28 — M1 核心策略和协议

- U03 RED 8 failed / 2 passed；新任务 default 写审批、acceptEdits 工作区编辑、plan 只读分别落地。Schema 9 保留旧任务 legacy 策略及未消费审批绑定，模式变化增加版本并使旧审批失效。
- U03 相关回归 61 passed；实际网页写成果审批流程修正后 1 passed。证据 `work/upgrade-m1/policy-regression1.log`、`policy-browser2.log`。
- U02 RED 7 failed / 4 passed；三协议显式 thinking 能力，未知拒绝，签名/加密块只存私有检查点并支持新 Worker 回传。
- U02/U03 最新相关回归 50 passed，Ruff 通过；`work/upgrade-m1/thinking-green4.log`。网页生产构建通过。收费 API 调用 0；实际服务冒烟尚未运行。
- Ruling: 不通过切换模型使 thinking 生效；能力由用户所选配置显式声明。摘要只展示服务已返回内容，不展示内部签名/opaque 状态。
- Ruling: 默认写审批是有意的兼容变化；旧行为测试显式采用 acceptEdits，新增测试独立验证 default，网页测试真实审批而非绕过。

Spec: `docs/superpowers/specs/2026-09-28-muse-mewcode-upgrade-design.md`

## 2026-09-28 — M0 开始

- 执行方式：当前会话原生执行；用户已授权根据 Spec 继续开发。
- Ruling: 沿用现有 muse-integration feature checkout — 这是此前交付目录且有用户已有变更；不新建空 checkout 丢失未提交文档/benchmark 工作，不修改 main。
- Ruling: 总 Spec 按 M0–M6 分拆计划 — M0 先解决已复现的 worktree 阻塞，后续阶段独立验证。
- Ruling: 不重复询问计划是否继续 — 当前用户指令明确授权开发；实施中的常规选择写入日志。
- Pre-flight: Task 1 的绝对目标和根快照供 Task 2 回执归因使用；完成判定按实际成功/失败回执处理，不使用路径长度推测任务结果。
- 已有无关变更：两个 MCP benchmark 文件、release benchmark 测试和三份审计/benchmark 文档，保留。
- Git 2.43 源码调查：worktree 内部将输入 path/.git 作为子进程 GIT_DIR；setup 检查 PATH_MAX-40。当前失败 fixture 的绝对 checkout/.git 超过对应边界。计划改用等价相对输入，而非仅打开 core.longpaths。
- 参考源码：https://github.com/git-for-windows/git/blob/v2.43.0.windows.1/builtin/worktree.c#L493；https://github.com/git-for-windows/git/blob/master/setup.c#L1121。
- Task 1 RED：6 failed / 1 passed；深路径、中英文、配置和根冻结缺口复现。
- Task 1/2 GREEN：深路径 worktree、生命周期、完成判定、委派共 29 passed（16.20s），日志 `work/upgrade-m0/green3.log`。
- Task 2 RED：修正测试租约/审批初始化后，两个真实完成判定断言失败，两个已有兼容场景通过；随后加入回执检查。
- Ruling: 退休内部始终使用 worktree 绝对路径，单独改相对输入不足 — 默认过长根采用就近短祖先、按状态目录哈希隔离的命名空间，显式长配置在创建前拒绝，绝不 force 删除。
- Ruling: 原任务不提供模型可触发的串行逃逸 — 用户明确创建串行后续任务，原失败证据保留。
- M0 首次完整离线：984 passed / 4 failed / 2 skipped。环境复测确认缺 Playwright headless shell，安装官方依赖后 991 passed / 2 skipped / 2 warnings，见 `work/upgrade-m0/full2.log`。
- 独立审查并修复：Git tree 路径预检、无 executable row 的参数/Hook 拒绝回执、机器 stdout 与显示 stderr 分开、幂等回放保持原 DB 时间。相关 38 项自动测试通过。
- M1/U07 RED：正确初始化临时目录后 13 failed / 6 passed，缺少 schema/分页/正则/限额契约真实复现。
- M1/U07 review RED：跨行私钥分页脱敏、枚举阶段超时、溢出正则错误码三项真实失败；随后修复完整原文行投影、可取消有界枚举、编译异常归一。
- M1/U07 GREEN：分页和工作区工具 31 passed（17.99s），RuntimeWarning 当 error，Ruff 通过；最终独立复查未发现阻塞项。
- Ruling: 不增加第三方 regex 依赖 — 独立 Python 文本处理子进程实现强制终止；环境仅保留运行必需变量，不带模型凭据。
- Ruling: 底层文件系统操作不能在线程中强制中止 — 父调用遵守截止时间，停止标志阻止操作返回后的继续枚举；已记录限制，不宣称 OS 隔离。
- Ruling: 保留现有 output offload — 大分页/搜索完整 JSON 从成果回读；不改所有工具已有截断展示契约。
- 最终完整离线回归：1018 passed / 2 skipped / 2 依赖弃用警告（329.44s），`work/upgrade-m0/full3.log`。随后仅强化测试，明确重新实例化 Worker，以及真实审批→配置更改→新租约后目标/digest 不变；深路径针对性 10 passed（20.15s），`work/upgrade-m0/approval-final.log`，未改产品行为。
- 收口：保留 registry 原有混合换行的未修改行，避免无关整文件格式变化；本轮 diff --check、Ruff 均通过。
- 状态：需求/AC 状态见 `docs/muse-upgrade-status-2026-09-28.md`。U02/U03 和后续阶段待开发，付费 API 调用 0。Git 作者未配置，不伪造身份或写全局设置。
