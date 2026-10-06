# WordPress 参考环境状态

当前正式隔离平台验收 BLOCKED：本机 Docker Linux daemon 不可连接，独立 Linux 环境未提供。2026-10-01 已在工作目录搭建经官方清单校验的便携 PHP 8.4.26、MariaDB 11.4.12、WordPress 7.1.2、WooCommerce 11.1.2 本机临时站，只监听 127.0.0.1，不注册系统服务；真实快照、页面、主题、导航、商品及故障测试已开始。Windows 功能测试不证明 Linux 隔离，清单 verified 仍为 false。

2026-09-30 根据 WordPress 和 WooCommerce 官方发行页选择 WordPress 7.1.2 / WooCommerce 11.1.2 作为待验证候选。此选择不表示两者已完成兼容验证。`deploy/commerce/versions.lock.json` 保持 `verified=false`，镜像 digest 空缺；预置脚本因此拒绝部署，禁止猜测哈希或使用 latest。

Linux 测试环境需要：解析 WordPress/PHP、MariaDB、WP-CLI 的实际镜像 digest；分别部署 staging/live-test；安装锁定 WooCommerce 版本和固定 Connector；禁邮件、真实付款和索引；验证版本、5 件测试商品和测试订单后，才可记录 verified=true。Compose 只提供独立卷、服务网络和秘密文件绑定；它本身不表示邮件/支付隔离已实现。

当前命令只执行无副作用 preflight：

```powershell
.\.venv\Scripts\python.exe scripts/commerce/bootstrap.py --project shop-001 --environment staging
```

未验证清单的预期结果是退出码 2。真实 bootstrap、WP-CLI 预置和完整部署验收仍待 Linux 环境实现/验证。
