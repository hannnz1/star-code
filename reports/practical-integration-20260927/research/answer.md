已完成，并已用 `save_artifact` 保存为 **research.md**。

要点概览：
- `asyncio`：更适合 I/O 密集型、网络并发、协程编排、队列/同步/子进程控制。
- `concurrent.futures`：更适合把同步 callable 丢到线程池/进程池/解释器池中执行。
- 取消限制：
  - `Future.cancel()` 只能取消尚未运行的任务；
  - `shutdown(cancel_futures=True)` 只能取消未开始的 pending futures，运行中任务不会被取消。
- CPU 密集型选择：
  - 首选 `ProcessPoolExecutor`；
  - 可考虑 `InterpreterPoolExecutor` 获取真正多核并行；
  - `ThreadPoolExecutor` 通常不作为 CPU 密集型首选，官方还不建议用于长时间运行任务。

我在报告中逐条附了官方来源链接，并明确说明了本次读取到的文档范围内没有额外编造 `asyncio` 取消细节。