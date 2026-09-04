# Skill 系统 Spec 质量分析

## 总评

当前质量约为 **8.8/10**。核心目标、目录覆盖、延迟加载、执行模式、接口反转与安全默认均较清晰；经过实现校准后，远程安装、fork 生命周期和 provider/model 选择也已有明确落点。剩余问题主要是部分早期 Plan 与最终实现命名不统一，以及少数有意保留的产品边界。

## 设计优点

- 用户级与项目级两层覆盖关系明确。
- phase-1 元数据发现、phase-2 正文热重读兼顾启动速度与编辑体验。
- `SkillHost` / `SkillForkHost` 避免 skill 包反向依赖 TUI/Agent。
- inline、fork、`fork_context` 与 `$ARGUMENTS` 的语义清楚。
- 单个技能损坏、目录缺失和热重读失败都有隔离策略。
- 动态命令有 Skill 来源标记，可安全卸载重注册，不影响内置命令。
- 远程安装采用允许列表、限额、临时目录校验和原子移动，安全边界可测试。

## 已解决的原始矛盾

1. F3 与早期 Plan 对格式支持不一致：最终统一支持 `SKILL.md` 和 `skill.yaml + prompt.md`。
2. F13 与早期 ZIP 方案冲突：最终统一使用 GitHub Contents API，不自行解压不可信 ZIP。
3. phase-1 不读正文与描述回退冲突：实现只做受限的首行扫描，不加载完整正文。
4. Slash 零参数与 Skill 参数冲突：当前显式命令保持零参数；渲染层保留 `$ARGUMENTS` 能力供程序入口使用。
5. model 缺少 provider 解析规则：新增 `provider` 字段；缺省沿用当前 provider，`model` 仅覆盖所选 provider 的模型。
6. fork 生命周期不完整：已补充取消传播、事件流展示、独立历史、最终结果回填和 token 合并。

## 仍建议补充到后续 Spec

- 为真实 GitHub Contents API 增加可注入 HTTP transport，以便做完全离线的响应体、限额、超时和错误码测试。
- 明确 `skills.sh` 的可信解析协议后再开放该来源，避免将网页跳转或第三方脚本直接当安装协议。
- 如未来支持 Slash 参数，需要单独升级 ch10 dispatcher 的 tokenizer、补全与引用/转义规则。
- 明确 Skill 名与内置命令冲突时的产品策略；当前实现选择跳过冲突 Skill 命令并保留内置命令。
- 若要支持 GitHub 含 `/` 的分支名，应改为 API 参数式安装源或显式拆分 ref/path，而不是继续猜 URL 边界。
