# MUSE M1 File Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 实现 U07 的兼容分页读取、大小写搜索和可强制终止的正则搜索。

**Architecture:** 保留 read_file 无分页参数时的原始字符串结果。分页输出 JSON，行号从 1 开始、offset 从 0 开始。正则在独立 Python 子进程中编译和匹配，通过受限 JSON 协议传递文本；父进程执行单文件 250ms 和整次 5s 上限，取消/失败均关闭子进程。

**Tech Stack:** Python asyncio/subprocess、标准库 re/json、现有 WorkspacePolicy/ToolRegistry、pytest。

**Spec:** `docs/superpowers/specs/2026-09-28-muse-mewcode-upgrade-design.md`，U07；本计划不包含同属 M1 的 U02/U03。

## Task 1 — 分页和字面搜索

Files: `src/muse/tools/files.py`、`src/muse/tools/registry.py`、`tests/muse/integration/test_file_paging_search.py`。

- [x] 写测试并观察缺少参数/schema 的失败：首末行、空文件、EOF、CRLF、BOM、默认页大小、负偏移/非法 limit、旧调用结果。
- [x] 实现 offset=0、limit=2000（1–10000）、lines/line/text、next_offset/truncated；保留脱敏、16 MiB 和 offload 边界。
- [x] 字面搜索保留 regex=false/case_sensitive=false；case_sensitive=true 不忽略大小写。
- [x] 路径越界和私有状态读取仍拒绝，运行工具回归。

## Task 2 — 有界正则

Files: `src/muse/tools/regex_search.py`、`src/muse/tools/regex_worker.py`、上一任务文件/测试。

- [x] 写有效/无效正则、glob/数量、灾难回溯和取消测试，观察当前缺口。
- [x] 子进程仅接收文本，不执行模型代码，不访问工作区，不继承 API 凭据；错误编译为 INVALID_ARGUMENTS。
- [x] 父进程在单文件/总时间上限终止子进程并返回 SEARCH_TIMEOUT，保留可用部分结果和限制信息，不伪装无匹配。
- [x] 保持最多 500 候选文件和 100 命中；标记结果不完整原因。
- [x] 跑针对性测试、完整离线回归、Ruff 和独立审查；修复重要问题并更新日志。

## Constraints

- 不调用付费 API，不修改所选 provider/model，不添加第三方依赖。
- 不引入批量替换功能；源码和资料继续作为不可信数据。
- 当前 feature checkout 继续保留已有用户工作，不自动发布。
- U02 thinking、U03 权限模式、记忆、协调者、平台沙箱和最终 benchmark 仍按总 Spec 独立推进。
