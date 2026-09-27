# Python 3.12 后台任务比较：人工复核摘要

这是对研究试用成果的人工复核版本。首版和模型修订版均保留，未覆盖原始证据。

- **异步 I/O 与协程编排**：使用 `asyncio`。`Task.cancel()` 请求在后续执行机会引发取消异常，不是强制终止任意正在执行的代码；清理适合放在 `finally` 中，捕获取消异常后通常应继续传播。`TaskGroup` 会在成员出现非取消异常时取消其余成员。[Python 3.12 任务文档](https://docs.python.org/3.12/library/asyncio-task.html)
- **普通阻塞 I/O**：可使用线程池。**纯 Python CPU 密集计算**：可使用进程池获得多核并行，但函数、参数和结果须满足序列化及子进程导入要求；不能把所有同步调用一概推荐给进程池。[Python 3.12 执行器文档](https://docs.python.org/3.12/library/concurrent.futures.html)
- **取消边界**：执行器的 `Future.cancel()` 不能取消已经开始执行的任务；`shutdown(cancel_futures=True)` 处理尚未开始的任务，运行中的任务不会因此停止。需要中途停止时，必须另外设计协作停止或进程生命周期管理。[执行器与 Future 文档](https://docs.python.org/3.12/library/concurrent.futures.html)
- **版本边界**：本报告不将 `InterpreterPoolExecutor` 作为 Python 3.12 可用方案；原报告对新版功能的推荐缺少这一限制。`TaskGroup` 在 3.12 可用，但不是 3.12 新增功能。[任务文档](https://docs.python.org/3.12/library/asyncio-task.html)、[执行器文档](https://docs.python.org/3.12/library/concurrent.futures.html)

证据：`research-followup/sources.json` 保存两页实际读取的文本、URL、时间和 SHA256；`tool-calls.json` 保存读取和成果生成过程。

质量结论：初稿需要补充，修订稿补齐了主要取消语义；本复核摘要进一步修正了同步调用选型的过度概括。不能据此把初稿或固定 60 次 Benchmark 记为全部通过。
