# MUSE 后台任务技术比较报告：`asyncio` vs `concurrent.futures`

> 依据：仅基于已实际读取的 Python 官方文档。
> 说明：下文所引述的结论都能在文末“来源链接”中对应到官方页面；若某项能力不在两份文档中直接说明，本文不会擅自扩展。

## 1. 结论摘要

- **`asyncio`** 更适合 **I/O 密集型、网络通信、异步协程编排、需要对任务执行过程做精细控制** 的后台任务。
- **`concurrent.futures`** 更适合 **把普通可调用对象丢到线程池/进程池/解释器池中并行执行** 的场景，尤其适合：
  - `ThreadPoolExecutor`：偏 **I/O 并发**，不推荐长时间运行任务；
  - `ProcessPoolExecutor`：适合 **CPU 密集型**、需要绕开 GIL 的工作；
  - `InterpreterPoolExecutor`：可获得 **真正多核并行**，但并发代码需要更谨慎，且数据不能共享可变对象。

## 2. 各适合哪些任务

### 2.1 `asyncio` 适合的任务

官方文档明确写到：`asyncio` 是“使用 `async/await` 语法编写并发代码”的库，且“通常非常适合 I/O-bound 和高层结构化网络代码”。它还提供了高层 API 来执行协程、网络 I/O、IPC、子进程、队列和同步原语。

**因此，适合：**
- 网络请求、Socket 通信、协议处理
- 需要大量等待 I/O 的后台任务
- 需要协程编排、队列调度、任务同步的异步服务
- 与子进程、IPC 交互的异步控制逻辑

**不应把它理解为**：专门用于纯 CPU 计算加速的模块。官方页面的定位是 asynchronous I/O，而非 CPU 并行计算。

### 2.2 `concurrent.futures` 适合的任务

官方文档将其定义为“用于异步执行 callable 的高层接口”，可通过线程、进程或解释器来执行。

**因此，适合：**
- 把已有的同步函数并行化执行
- 批量提交独立任务并收集结果
- 需要线程池、进程池或多解释器池的后台作业
- 需要把任务包装成 `Future`，由外部统一等待、回调或取消

#### 子类适用性

- **`ThreadPoolExecutor`**：官方示例与说明都表明它常用于 **I/O 叠加并发**；默认最大线程数的设计也明确提到“保留至少 5 个 worker 用于 I/O bound 任务”。
- **`ProcessPoolExecutor`**：官方明确指出它使用多进程，**绕过 GIL**，适合 CPU 密集型并行。
- **`InterpreterPoolExecutor`**：官方明确指出它带来 **true multi-core parallelism**，但每个 worker 在自己的解释器中运行，数据隔离更强，代价是并发代码要更谨慎地处理共享与序列化。

## 3. 取消（Cancellation）的限制

### 3.1 `concurrent.futures.Future.cancel()` 的限制

官方文档对 `Future.cancel()` 的描述是：
- 只能“尝试取消”任务；
- 如果任务已经在执行，或已经执行完成，则返回 `False`，无法取消；
- 如果成功取消则返回 `True`。

此外，`Executor.shutdown(cancel_futures=True)` 只能取消 **尚未开始运行** 的 pending futures：
- **已经完成或正在运行的 future 不会被取消**；
- 如果 `wait=True` 且 `cancel_futures=True`，正在运行的任务会先完成，剩余未开始任务才会被取消。

这意味着：
- `concurrent.futures` 的取消是 **协作式、且有状态限制** 的；
- 一旦任务已进入运行态，通常不能靠 `cancel()` 把它“硬停掉”。

### 3.2 `asyncio` 的取消

本次读取到的 `asyncio` 总览页只明确说明它提供任务、协程、同步、队列、子进程等高层 API；**当前读取的页面片段中没有出现 `Task.cancel()` 等更细节的取消语义说明**。因此，本报告**不对 `asyncio` 的取消机制做超出该页文字的推断**。

> 说明：若需要比较 `asyncio` 的任务取消细节，应进一步读取 `asyncio` 中关于 Tasks / Futures 的专门页面；但本次按要求仅依据已实际读取的官方文档，不额外扩展。

## 4. CPU 密集型工作怎么选择

### 4.1 首选：`ProcessPoolExecutor`

官方文档明确写到：`ProcessPoolExecutor` 使用多进程，**可以绕开 Global Interpreter Lock**。这使它成为 CPU 密集型工作最直接的选择。

同时，文档还指出：
- 只能执行和返回 **可 pickle** 的对象；
- `__main__` 模块必须可被 worker 子进程导入；
- 在交互式解释器里不工作；
- 在 submit/map 的 callable 中调用 `Executor` 或 `Future` 方法可能导致死锁。

**结论**：
- 如果任务是纯 Python CPU 计算、彼此独立、且参数/返回值可序列化，优先选 `ProcessPoolExecutor`。

### 4.2 次选：`InterpreterPoolExecutor`

官方文档指出它具有 **true multi-core parallelism**，因为每个解释器有自己的 GIL。相较于线程池，它能实现真正的多核并行；但代价是：
- worker 之间不能共享可变对象；
- 需要显式处理跨解释器的数据传递；
- 初始化参数、调用参数、返回值都要通过 pickle 序列化。

**结论**：
- 如果你希望多核并行，同时愿意接受解释器隔离带来的数据传递成本，`InterpreterPoolExecutor` 也是 CPU 密集型候选。

### 4.3 不推荐：`ThreadPoolExecutor` 作为 CPU 密集型首选

官方文档对 `ThreadPoolExecutor` 的说明强调：
- 它通常用于 **I/O overlap**；
- 默认 worker 数量设计也偏向 I/O；
- 对 CPU bound 任务，只有在 **任务会释放 GIL** 时，线程池才可能利用更多 CPU；
- 还特别警告：**不推荐用于长时间运行任务**。

**结论**：
- 对 CPU 密集型纯 Python 计算，不优先选线程池；
- 除非你的计算代码主要在释放 GIL 的扩展里完成，否则线程池通常不是最佳方案。

## 5. 面向 MUSE 后台任务的选型建议

### 5.1 适合用 `asyncio` 的后台任务

- 网络爬取、API 聚合、异步数据库访问、消息队列消费
- 大量等待外部 I/O 的调度器
- 需要在单进程内管理大量并发连接的任务
- 需要协程级别的生命周期控制、同步和队列管理

### 5.2 适合用 `concurrent.futures` 的后台任务

- 现有同步函数的并行批处理
- 独立文件处理、图像处理、加解密、数据转换等任务封装成 callable 后分发
- 需要线程池/进程池/解释器池做隔离执行的工作

### 5.3 简化决策

- **I/O 密集型、网络并发、协程友好** → 优先 `asyncio`
- **CPU 密集型、需要多核并行** → 优先 `ProcessPoolExecutor`
- **需要多核并行且愿意接受解释器隔离** → 可考虑 `InterpreterPoolExecutor`
- **同步 I/O 并发、老代码快速并行化** → 可用 `ThreadPoolExecutor`

## 6. 注意事项

- `concurrent.futures.Future` 不应与 `asyncio.Future` 混淆；前者用于执行器任务，后者用于 `asyncio` 任务和协程。
- `ThreadPoolExecutor` 可能发生死锁，尤其是任务内部再等待同一线程池中的其他 future。
- `ProcessPoolExecutor` 和 `InterpreterPoolExecutor` 都有序列化限制；代码、参数、返回值需要可传递。
- 两个模块在 WebAssembly 上均不可用或不可工作（官方页面均有此说明）。

## 7. 逐条来源链接

1. `asyncio` 总览：
   - https://docs.python.org/3/library/asyncio.html
   - 证据点：`asyncio` 用于 `async/await` 并发代码；适合 I/O-bound 和结构化网络代码；提供网络 I/O、IPC、子进程、队列、同步原语等高层 API。

2. `concurrent.futures` 总览：
   - https://docs.python.org/3/library/concurrent.futures.html
   - 证据点：高层异步执行 callable；可用线程、进程、解释器执行。

3. `Executor.shutdown(cancel_futures=...)`：
   - https://docs.python.org/3/library/concurrent.futures.html
   - 证据点：只能取消尚未开始的 pending futures；运行中或完成的不会取消。

4. `Future.cancel()`：
   - https://docs.python.org/3/library/concurrent.futures.html
   - 证据点：任务已在执行或已完成则返回 `False`，无法取消。

5. `ThreadPoolExecutor`：
   - https://docs.python.org/3/library/concurrent.futures.html
   - 证据点：用于线程池异步执行；不推荐长期运行任务；默认配置偏向 I/O overlap；CPU-bound 仅在释放 GIL 时受益。

6. `ProcessPoolExecutor`：
   - https://docs.python.org/3/library/concurrent.futures.html
   - 证据点：多进程、绕过 GIL、仅可 pickle 的对象；适合 CPU 并行。

7. `InterpreterPoolExecutor`：
   - https://docs.python.org/3/library/concurrent.futures.html
   - 证据点：每个 worker 解释器隔离、拥有自己的 GIL、支持 true multi-core parallelism，但不能共享可变对象。

## 8. 备注

- 本报告仅使用已实际读取的官方文档内容，不引入未读取页面的补充解释。
- 若需要进一步细化“`asyncio` 任务取消、TaskGroup、shield、timeout”等细节，建议再读取 `asyncio` 的专门章节后补充。