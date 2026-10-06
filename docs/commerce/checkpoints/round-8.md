# 第八批：离线导出与工作台下载

新增 ProjectExporter、格式 1 ZIP/文件摘要清单、带当前项目版本的鉴权 API，以及工作台「下载项目资料」入口。仅白名单读取本项目商家输入、计划历史、当前版本商品草稿；自有原生主题必须可确定性重建且内容摘要匹配。不会读取凭据、客户、订单、快照、任务提示或审批许可。

导出是离线交接，不是自动恢复/部署。required_versions 目前仅声明导出格式；真实平台兼容、第二套环境导入、浏览器/购买验证未完成。用户输入私人文本原样保存，分享前需检查。100 条计划/导入上限、16 MiB 内容上限、固定 ZIP 文件名和主题序号路径，不把 Agent 输入作为文件路径。

首批 8 项 API/导出测试；随后增加跨项目篡改和历史上限，导出模块共 10 passed。电脑/手机浏览器下载与原功能回归两项通过；实际下载的 ZIP 中商品价格和秘密排除断言通过。前端生产构建通过。

本批未调用付费模型、真实店铺写入、同步 Desktop 或提交推送。发布插件、实际验证器、建站和新品上线闭环仍未完成；本批只推进 P10 的独立导出子项。

## 最终验证

- 根目录完整回归：1367 passed / 3 skipped / 1 failed / 2 warnings，542.31 秒。pytest 退出码 1，work/commerce8-full-final.log/exit。唯一失败仍为原 Windows launcher test_stop_script_matches_serialized_process_time[True-False]，taskkill Access denied；不删、不跳过，不标全量通过。
- 导出模块 10 passed（commerce8-export-boundaries.log）；首次导出 8 项与电脑/手机浏览器两项合跑 10 passed（commerce8-focused.log）。前端生产构建、Ruff、OpenAPI 字节校验及 git diff --check 均退出 0，分别保留日志与退出码。
- 一轮审查没有 Critical/Important；容量错误提示细节为暂缓 Minor，见 ../review-results-round-8.md。
- 本机截图保存在 work/commerce/checkpoints/round-8/merchant-1440.png、merchant-390.png。全部使用演示资料，不证明真实店铺验收。
