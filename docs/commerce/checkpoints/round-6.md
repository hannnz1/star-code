# 第六批：持久审批基础（P7 部分实现）

新增内部 ApprovalRepository，复用现有变更集和批准表，支持审查保存、摘要与版本确认、固定 30 分钟批准、重复请求幂等、撤销、到期刷新及执行前读取当前批准。事务同时保存批准和计划状态；重启与并发重复批准有回归测试。

本批没有接通 API/CLI/Agent 发布入口。实际 WordPress 写入仍关闭，原 Coding Agent 和模型配置继续保留。

模块验证：28 passed（work/commerce6-focused-final.log）。Ruff、OpenAPI 字节检查与 git diff --check 通过，Git 仅报告已有换行转换提示。

根目录完整回归：1331 passed / 3 skipped / 1 failed / 2 warnings，178.70 秒；work/commerce6-full-final.log，pytest 退出码 1（work/commerce6-full-final.exit）。唯一失败仍是原 Windows launcher test_stop_script_matches_serialized_process_time[True-False]，taskkill 返回 Access denied，未删除或跳过。不能标记全量通过。

审查处理见 ../review-results-round-6.md。仍缺实际沙箱开发/验证器、远端原子写插件、部署环境，以及建站/新品/购买链路验收。本批不等于 P7 或整个 MVP 完成。没有调用付费模型、真实站点写入、提交推送或同步 Desktop 项目。
