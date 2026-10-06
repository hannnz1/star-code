# 第三批检查点：操作账本与只读对账

状态：P3 部分实现，未完成正式平台验收。

新增独立连接器内部模块：

- OperationLedger：持久化完整操作摘要、连接/环境/项目归属，去重与每资源未决锁。begin 必须在发送前调用，并立即写入待对账状态。重启后禁止重发；终态重复查询返回原回执。
- ReceiptReconciler：显式一次 GET 固定店铺回执路径，校验完整归属、摘要、资源与终态，超时/404/无效回执保持待对账。

这两个模块没有注册公开写接口，也没有接入 CLI 或任务工具。confirm 只允许未来经过验证的内部发布器调用，不能代替签名授权、远端插件资源校验或 OS 隔离。

现已执行离线 SQLite/HTTP 外部边界测试，14 passed；证据 work/commerce3-focused-final.log。RED 收集失败记录在 commerce3-red.log 和 commerce3-receipts-red.log。Ruff 已通过新增模块及对应测试。

尚需：固定操作专用 payload 契约、执行授权验证、PHP 写入/远端回执/原子资源检查、P5 staging 部署、P6 隔离 coding 与购买链路、P7 审批发布、P8 实站新品上传、P10 实际环境验收。没有模型请求、API 费用或实际店铺写入；没有 Git 提交、推送、Desktop 同步。

全量回归与独立审查结果将在本检查点追加，不覆盖前两批证据。

- 初次回归命令仅覆盖 tests/muse 子集：420 passed / 1 skipped / 1 failed / 2 warnings，293.88 秒（work/commerce3-full.log）。仍为原 Windows launcher taskkill Access denied；不能把此子集称全量。压缩回执修复后另跑根目录 pytest -q 作为最终全量，结果待追加。
- 静态检查：ruff check src/muse tests/muse/commerce、muse.openapi_types --check、git diff --check 均通过（Git 仅行尾转换提示）。没有前端变更，本批不重复构建/浏览器验收。
- 三项本批裁决完整记录于 development-ledger.md 第三批；审查延后错误码一致性问题见 review-results-round-3.md。

## 最终验证

- 根目录 `.venv\Scripts\python.exe -m pytest -q`：**1233 passed / 3 skipped / 1 failed / 2 warnings**，406.23 秒；证据 `work/commerce3-full-final.log`。唯一失败仍是 `test_stop_script_matches_serialized_process_time[True-False]` 的 Windows taskkill Access denied，不删、不跳过，不标全量通过。
- 新增模块：15 passed（work/commerce3-focused-final.log），含一次独立审查发现的压缩回执修复。
- Ruff（src/muse、tests/muse/commerce）、OpenAPI 字节校验及 git diff --check 通过。
- 本批只完成 P3 的内部账本/只读对账基础，P3 不标完成；无 API 费用、店铺写入、Git 提交或推送。
