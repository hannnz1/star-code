# 第五批检查点：内部发布器

P3 部分实现，不代表实站发布验收。

- 内部 WordPressPublisher 默认关闭；接通固定操作、当前批准/ChangeSet/报告哈希、成员校验、版本/capability 和真实资源指纹预检查。
- 发送前再次验证当前批准，先提交 SQLite send marker；单次固定 POST，超时或无效回执待对账；重复调用只读回执或返回终态，不重发。
- target_bindings 持久绑定实际站点，跨实例/重启也拒绝换目标对旧操作对账。旧无来源记录不猜测；换站点使用新连接 ID。
- 批准查询普通异常脱敏；取消传播；批准中必要依赖设置变更导致零 POST。

五模块 85 passed（commerce5-focused-final.log），Ruff 通过。全量最终结果将追加。HTTP 均 MockTransport，无模型/真实店铺请求、费用、Git 提交推送或 Desktop 同步。

未接通：API/CLI/Agent 写入口、持久审批服务、PHP 原子写端、部署安全隔离及购买链路。SKU/导航目前没有可验证的快照指纹，拒绝写；多步发布中前序步骤改变依赖也保守阻止，P7 后续必须定义合法后继状态和回执验证。真实 WordPress/插件仍需独立环境验收。

## 最终验证

- 首次根目录全量日志 commerce5-full-final.log 在 93% 截断，运行器会话丢失且无 Python 进程/无最终汇总。原因未判定，不按通过计；原日志保留。
- 重新执行完整根目录 pytest -q -vv 并保存退出码：**1303 passed / 3 skipped / 1 failed / 2 warnings**，194.23 秒。失败仍是原 Windows `test_stop_script_matches_serialized_process_time[True-False]` 的 taskkill Access denied。证据 commerce5-full-rerun.log、commerce5-full-rerun.exit（1）。不标全量通过，不删除/跳过原失败。
- 相关五模块合跑 85 passed（commerce5-focused-final.log）。本轮新增 publisher 19 项、账本/回执绑定各 1 项，共新增 21 项。
- Ruff src/muse 与 tests/muse/commerce、OpenAPI 字节检查、git diff --check 通过。
- P3 仍部分实现，真实插件、独立环境及发布/新品闭环未验收；无付费模型、真实站点写入、Git 提交推送或 Desktop 同步。
