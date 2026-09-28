# M4 — 可选 OS 沙箱

- [x] RED：Windows required、后端缺失及配置变化均禁止裸执行。
- [x] off/required 配置与任务冻结快照；统一 argv 包装，无 Shell 拼接。
- [x] bwrap 与 Seatbelt 默认拒绝工作区外读写及网络，显式运行时与临时目录。
- [x] 复用受管进程树取消；能力查询与终端 `/sandbox`。
- [ ] 本机自动契约测试；独立 Linux/macOS 哨兵/网络/进程真实探针无环境时 BLOCKED。

声明限制：不提供 Windows 内核隔离；无法可靠执行的网络允许列表必须拒绝，不能放开全部网络。真实平台通过前不宣称 OS 支持验收完成。

参数依据 bubblewrap 官方源码 https://github.com/containers/bubblewrap/blob/main/bubblewrap.c 。Seatbelt 配置使用现有基线 SBPL 语法，必须在真实 macOS 上验收。
