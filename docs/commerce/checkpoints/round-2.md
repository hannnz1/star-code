# 第二批检查点：店铺上下文和三角色提案协作

日期：2026-09-30。决定：**只可继续独立开发；Commerce MVP 和生产发布未放行**。

HEAD `4aec15ae79648f1e398b29e975177b73ca532fb6`，分支 `muse-integration`，本批尚未提交。当前源码/输入清单 `work/commerce/checkpoints/round-2/source-manifest.json`；日志/截图哈希 `evidence-manifest.json`。它们属于本批，不覆盖 stage-1 的旧清单与截图；未经提交的清单不是可发布代码版本。

| 项目 | 实际结果 |
|---|---|
| P2 主程序适配与 API | 连接注册绑定、能力/项目/环境/版本校验、固定目标、不泄露 WordPress 凭据、重绑定失效上下文、刷新保留旧数据、资源变化取消旧团队 |
| P4 提案团队 | 原 SQLite 事务创建根任务/步骤/预算，固定三角色有效权限，冻结 provider/prose/project 来源，原技术审批、委派去重、输出哈希、格式一次修正/事实 NEEDS_INPUT、原任务显式恢复 |
| P4 重启/错误边界 | SQLite 管理效果与调用回执同事务，租约恢复核对完整 digest；损坏证据及外部工具继续 UNKNOWN；缺已知事实零排队；根任务早停不能伪造团队完成；状态重读不改版本 |
| P9 | 实际连接/上下文和团队队列 UI、共享预算、任务 ID/成果哈希、缺字段/阻塞/恢复、刷新后持久恢复；原 Coding 入口保持独立 |
| 独立审查 | 五项 Important 已按一次修复处理，回归证据及未判定裁决见 review-results-round-2.md；没有第二次 reviewer 放行结论 |
| 全量回归 | **1218 passed / 3 skipped / 1 failed / 2 warnings**，423.16 秒，`work/commerce2-full-final.log` |
| 唯一失败 | 原 `tests/muse/integration/test_launcher.py::test_stop_script_matches_serialized_process_time[True-False]`，Windows taskkill Access denied；开发前已失败，本批不删断言、不改成 skip |
| 首轮失败保留 | 1202 passed / 3 skipped / 1 原有失败 / 4 新 fixture 加载错误；移至局部 conftest 后最终零 fixture error，日志 `work/commerce2-full.log` |
| 针对性最终测试 | 连接/编排/API/审查回归四组 **44 passed**，`work/commerce2-review-final2.log`；44 不代表完整平台验收 |
| 浏览器 | 最终全量包含新团队与原商家 1440/390 测试；真实 Chromium + 本地 API/DB，横向溢出、持久恢复、原入口及错误展示通过。截图 round-2/merchant-*.png、team-*.png |
| 类型/构建/静态检查 | `muse.openapi_types --check`、`npm --prefix frontend run build`、`ruff check src/muse tests/muse/commerce`、`git diff --check` 通过；旧根目录 lint 不在本范围 |
| 费用/外部操作 | 项目模型 API 调用 0、WordPress 写入 0；ScriptedProvider/外部 HTTP fixture 只验证契约，不是付费模型或实站成绩 |

## 本批不能声称的完成项

独立 Linux/Docker 环境没有提供，本机 Docker daemon/PHP 仍不可用；候选镜像/版本清单未实测。P3 WordPress 固定写操作及回执、P5 真 staging、P6 隔离 Coding Bridge 与买家路径、P7 版本审批/发布/对账、P8 图片与实站 SKU 对账、P10 导出/二环境迁移/六模型案例尚未完成。wheel/干净安装仍受构建器和 uv 权限限制，不能用历史产物代替。

工作流中的网站开发角色现在只提交结构提案。资料和三个成果齐备仍因缺代码包/实站验证返回 BLOCKED / VERIFICATION_UNAVAILABLE，不能创建发布批准。原 Coding Agent 保留 Shell/改码/多任务能力，Commerce 团队暂不获得这些权限。

下一阶段：实现 P3 的固定店铺操作/持久 operation 回执，再接通自有主题/staging/隔离代码桥、确定性验证、商家审查和发布恢复。独立环境实测仍是这些能力正式放行的必要条件；当前不把离线准备称为建站/新品上线成功。
