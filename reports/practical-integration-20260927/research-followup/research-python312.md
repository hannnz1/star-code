# Python 3.12 后台任务研究修订报告：`asyncio` vs `concurrent.futures`

> 目标：补充并修正上一份后台任务研究报告，重点比较 **`asyncio.Task.cancel()` / 取消传播** 与 **线程/进程任务的取消限制**，并给出 **适用于 Python 3.12 的 CPU 密集型方案**。  
> 约束：仅依据本次实际读取到的 Python 3.12 官方文档；区分不属于 3.12 的功能；若关键页面不可访问或内容未取得，明确标为未完成。

## 已读取的官方文档

1. `asyncio` 任务页（Python 3.12.14）：https://docs.python.org/3.12/library/asyncio-task.html  
   - 本次已实际读取到页面内容，且覆盖了 `create_task()`、`Task cancellation`、`TaskGroup`、`shield()`、`timeout()` 等相关段落。
2. `concurrent.futures` 页（Python 3.12.14）：https://docs.python.org/3.12/library/concurrent.futures.html  
   - 本次已实际读取到页面内容，且覆盖了 `Executor`、`ThreadPoolExecutor`、`ProcessPoolExecutor`、`shutdown(cancel_futures=...)` 等相关段落。

## 结论 1：`asyncio` 的 `Task.cancel()` 是协作式取消，不是强杀

### 结论
- 在 `asyncio` 中，任务被取消后，`CancelledError` 会在**下一个可执行机会**注入到任务里，而不是立即中断正在执行的 Python 代码。
- 文档明确建议用 `try/finally` 做清理；若显式捕获 `CancelledError`，通常应在清理后继续传播。
- `asyncio` 的结构化并发组件（如 `TaskGroup`、`timeout()`）内部使用取消机制，因此如果协程吞掉 `CancelledError`，这些组件可能表现异常。
- 用户代码通常不应直接调用 `uncancel()`；如果确实要抑制取消，还需要同时调用 `uncancel()` 清除取消状态。

### 依据
- “When a task is cancelled, `asyncio.CancelledError` will be raised in the task at the next opportunity.”
- “It is recommended that coroutines use try/finally blocks to robustly perform clean-up logic.”
- “In case `asyncio.CancelledError` is explicitly caught, it should generally be propagated when clean-up is complete.”
- “The asyncio components that enable structured concurrency, like `asyncio.TaskGroup` and `asyncio.timeout()`, are implemented using cancellation internally and might misbehave if a coroutine swallows `asyncio.CancelledError`.”
- “user code should not generally call `uncancel`.”
- “if suppressing `asyncio.CancelledError` is truly desired, it is necessary to also call `uncancel()` to completely remove the cancellation state.”

### 来源
- `asyncio` 任务页：<https://docs.python.org/3.12/library/asyncio-task.html>

## 结论 2：`asyncio` 取消会沿着结构化并发边界传播；`TaskGroup` 会联动取消剩余任务

### 结论
- `TaskGroup` 是 Python 3.11+ 的结构化并发 API，3.12 仍可用。
- 在 `TaskGroup` 中，只要组内任一任务抛出**非 `CancelledError`** 异常，剩余任务会被取消。
- 若 `async with` 体本身还在执行，包含该 `async with` 的外层任务也会被取消；该 `CancelledError` 会打断一次 `await`，但不会冒泡出 `async with`。
- 最终如果有非取消异常，会被组合成 `ExceptionGroup` 或 `BaseExceptionGroup` 抛出。

### 依据
- “Tasks can be added to the group using `create_task()`.”
- “All tasks are awaited when the context manager exits.”
- “The first time any of the tasks belonging to the group fails with an exception other than `asyncio.CancelledError`, the remaining tasks in the group are cancelled.”
- “At this point, if the body of the `async with` statement is still active … the task directly containing the `async with` statement is also cancelled.”
- “The resulting `asyncio.CancelledError` will interrupt an `await`, but it will not bubble out of the containing `async with` statement.”
- “Once all tasks have finished, if any tasks have failed with an exception other than `asyncio.CancelledError`, those exceptions are combined in an `ExceptionGroup` or `BaseExceptionGroup` …”

### 来源
- `asyncio` 任务页：<https://docs.python.org/3.12/library/asyncio-task.html>

## 结论 3：`concurrent.futures` 的取消能力只覆盖“尚未开始执行”的 future，运行中的线程/进程任务不能被该 API 强制取消

### 结论
- `Executor.shutdown(cancel_futures=True)` 只能取消**尚未开始运行**的 pending futures。
- 已完成或正在运行的 futures **不会**被取消。
- 所以 `concurrent.futures` 不能像协作式 `asyncio` 那样，把一个已经开始的线程/进程调用“打断”到立即停止。
- 这意味着：如果 CPU 密集任务已经进入线程池或进程池并开始执行，标准 `shutdown(cancel_futures=True)` 只能阻止未启动的任务，不能终止正在跑的那个任务。

### 依据
- “If `cancel_futures` is `True`, this method will cancel all pending futures that the executor has not started running.”
- “Any futures that are completed or running won’t be cancelled, regardless of the value of `cancel_futures`.”
- “If both `cancel_futures` and `wait` are `True`, all futures that the executor has started running will be completed prior to this method returning. The remaining futures are cancelled.”

### 来源
- `concurrent.futures` 页：<https://docs.python.org/3.12/library/concurrent.futures.html>

## 结论 4：线程池与进程池的取消语义不同，但对“正在执行的任务”都没有强制中断能力

### 结论
- `ThreadPoolExecutor` 和 `ProcessPoolExecutor` 都实现 `Executor` 接口，因此共享同一套“只取消未启动 future”的关闭语义。
- 文档没有说明 `shutdown(cancel_futures=True)` 能终止已运行中的线程函数或子进程函数；相反，文档明确说运行中的 future 不会被取消。
- 因此，对于需要“可中断”的后台计算，应设计任务为**协作式检查停止标记**，而不是指望 `concurrent.futures` 的取消 API 直接中断执行体。

### 依据
- “The concurrent.futures module provides a high-level interface for asynchronously executing callables.”
- “The asynchronous execution can be performed with threads, using `ThreadPoolExecutor`, or separate processes, using `ProcessPoolExecutor`. Both implement the same interface, which is defined by the abstract `Executor` class.”
- `shutdown(cancel_futures=True)` 段落中关于 pending / running futures 的说明（见结论 3）。

### 来源
- `concurrent.futures` 页：<https://docs.python.org/3.12/library/concurrent.futures.html>

## 结论 5：Python 3.12 下 CPU 密集型方案首选 `ProcessPoolExecutor`；需要真多核并行时可考虑解释器池，但这**不属于本次 3.12 官方文档已读取内容**

### 结论
- 对 CPU 密集型工作，**`ProcessPoolExecutor` 是 3.12 文档中明确存在且适用的方案**。
- 它使用多进程，可以“side-step the Global Interpreter Lock”，适合 CPU 密集型计算。
- 但它要求任务参数和返回值可 pickle，且 `__main__` 必须可被 worker 子进程导入；因此交互式解释器中不可用。
- `ThreadPoolExecutor` 默认 worker 数量的说明明确提到它“often used to overlap I/O instead of CPU work”，暗示它更偏 I/O 重叠，不是 CPU 密集型首选。
- **`InterpreterPoolExecutor` 不应写入本次 3.12 结论**：本次实际读取到的 3.12 `concurrent.futures` 页面内容里没有出现该类；因此不能把它作为本报告的 3.12 官方结论。

### 依据
- “The `ProcessPoolExecutor` class is an `Executor` subclass that uses a pool of processes to execute calls asynchronously.”
- “`ProcessPoolExecutor` uses the `multiprocessing` module, which allows it to side-step the Global Interpreter Lock but also means that only picklable objects can be executed and returned.”
- “The `__main__` module must be importable by worker subprocesses. This means that `ProcessPoolExecutor` will not work in the interactive interpreter.”
- “ThreadPoolExecutor is often used to overlap I/O instead of CPU work …”
- “This default value preserves at least 5 workers for I/O bound tasks. It utilizes at most 32 CPU cores for CPU bound tasks which release the GIL.”

### 来源
- `concurrent.futures` 页：<https://docs.python.org/3.12/library/concurrent.futures.html>

## 结论 6：`asyncio` 适合 I/O 并发与协程编排，不是 CPU 密集型计算框架

### 结论
- `asyncio` 文档强调它是 asynchronous I/O，`create_task()` 用于并发调度协程。
- 它非常适合网络 I/O、等待型工作、任务编排、超时和结构化并发控制。
- 对纯 CPU 密集型工作，`asyncio` 本身不会提供多核并行；若直接在事件循环里执行长时间 CPU 计算，会阻塞循环。
- `loop.run_in_executor()` 可把同步 callable 转移到 executor，但这已经是在借助 `concurrent.futures`。

### 依据
- 页面标题与导语：“asyncio — Asynchronous I/O”
- “Tasks are used to schedule coroutines concurrently.”
- “A good example of a low-level function that returns a Future object is `loop.run_in_executor()`.”

### 来源
- `asyncio` 任务页：<https://docs.python.org/3.12/library/asyncio-task.html>

## 适用于 Python 3.12 的 CPU 密集型方案建议

### 推荐方案
1. **首选：`concurrent.futures.ProcessPoolExecutor`**
   - 适合 CPU 密集型纯 Python 计算。
   - 使用多进程绕过 GIL。
   - 注意：任务必须可 pickle，且代码结构要满足子进程导入要求。

2. **如果任务本质上可拆分成很多独立工作单元**
   - 仍然优先用 `ProcessPoolExecutor` 分片执行。
   - `map(..., chunksize=...)` 在 `ProcessPoolExecutor` 下可显著改善长序列性能。

3. **如果需要与 asyncio 协程系统集成**
   - 用 `asyncio` 编排 I/O，CPU 部分通过 `loop.run_in_executor()` 接到进程池。
   - 这属于“asyncio + process pool”的组合，而不是把 CPU 任务塞进事件循环。

### 依据
- `ProcessPoolExecutor` 绕过 GIL、可并行执行。
- `map()` 在 `ProcessPoolExecutor` 下会切分 iterable，并且 “For very long iterables, using a large value for chunksize can significantly improve performance compared to the default size of 1.”
- `asyncio` 可通过 `run_in_executor()` 调用 executor。

### 来源
- `concurrent.futures` 页：<https://docs.python.org/3.12/library/concurrent.futures.html>  
- `asyncio` 任务页：<https://docs.python.org/3.12/library/asyncio-task.html>

## 不属于本次 3.12 已取得文档范围的功能，不能作为 3.12 结论

### 1. `InterpreterPoolExecutor`
- 本次实际读取到的 `concurrent.futures` 3.12 页面内容中**未出现**该类。
- 因此它不能作为本报告“Python 3.12 官方文档已证实”的 CPU 方案结论。
- **状态：未完成（本次 3.12 官方页面未取得对应内容）**。

### 2. 其它未在已读取页面中出现的取消/执行细节
- 例如更细粒度的 `Task.cancel()` 实现细节、内部取消计数、或其他版本新增特性，如果未在本次已读取的 3.12 官方页面中出现，都不应在本报告中作为 3.12 结论扩展。
- **状态：未完成（仅以本次读取到的文档为准）**。

## 给 MUSE 后台任务的简明选型

- **I/O 密集、并发网络请求、协程编排、限时取消、任务组管理**：优先 `asyncio`。
- **同步阻塞调用、CPU 密集计算、需要多核并行**：优先 `ProcessPoolExecutor`。
- **需要从 asyncio 中调用 CPU 任务**：`asyncio` 负责调度，CPU 任务交给 `ProcessPoolExecutor`。
- **不要指望 `concurrent.futures` 中运行中的线程/进程任务能被 `cancel_futures=True` 强制停掉**；它只影响尚未开始的 futures。
- **不要让 CPU 密集逻辑长时间占用事件循环线程**；否则会阻塞所有协程。

## 版本边界说明

- 本报告只按 **Python 3.12** 官方文档写作。
- `TaskGroup` 属于 **3.11+**，在 3.12 可用；但它不是 3.12 才新增的功能，不能写成“3.12 新特性”。
- 本次已读取到的 3.12 `concurrent.futures` 页面内容中没有 `InterpreterPoolExecutor`，因此不能把它写成本报告的 3.12 结论。

## 参考来源

- `asyncio` 任务页：<https://docs.python.org/3.12/library/asyncio-task.html>
- `concurrent.futures` 页：<https://docs.python.org/3.12/library/concurrent.futures.html>
