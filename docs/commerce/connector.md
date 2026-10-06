# 连接器开发状态

2026-10-06：固定平台隔离部署、购买验证 producer、六阶段到九项独立报告、合成审查及测试站发布已完成真实 Linux 建站联调，见 [最新运行证据](full-alignment-continuation-2026-10-06.md)。下文早期“待完成”为历史批次；生产商家与人工验收仍未执行，不能凭测试批准放行生产。

独立 Python 服务默认仅读取。显式配置 Linux 发布服务后，增加按 connection_id、project_id、plan_id、intent_digest 绑定的发布下一步/只读对账接口，不接受任意 URL、操作 payload 或模型验证报告。工作台已提供审查、明确批准和进度界面；必须已有可信验证来源，缺少部署/验证条件时明确拒绝。

固定 PHP 插件 v0.3.0 已实现九类受限操作及持久 InnoDB 回执，并在工作目录的便携 WordPress 7.1.2 / WooCommerce 11.1.2 临时站执行真实功能/冲突/故障测试。第九类为来源图片创建，成功回执绑定商品主图/图库。完整业务图、私有批准日志和公开界面有合同测试；没有连接真实商家店铺，**尚未证明完整 Linux 建站/发布流程**。插件是产品维护代码，不允许交给 Agent 修改后自动发布。

Linux 服务配置 JSON 字段为 token 与 connections。每条 connection 包括 connection_id、project_id、environment、base_url、username、application_password，以及默认 false 的 approved_development_http。不要把实际文件放进仓库、Agent workspace 或导出包。配置和父目录须归独立连接器 UID 所有，权限分别 0600 / 0700；普通 MUSE/coding UID 不得读取。Windows 配置加载拒绝启动。

运行命令：`.venv/bin/python -m muse.commerce_connector --config /独立服务目录/connections.json`。服务仅绑定 127.0.0.1:8787，关闭访问日志及公开 API 文档。这个绑定本身不是隔离证明：后续部署须设置独立网络命名空间、受控反向代理与 Linux 探针，禁止 coding 容器访问服务和 live。

WordPress 使用专用 `muse_connector_service` 角色与 Application Passwords，仅具有 `read`、`muse_read_context`、`muse_execute_owned`。管理员将 MUSE_SERVICE_USER_ID 指向这个服务账号，不能指向管理员或 Shop Manager。服务账号带有额外权限时拒绝上下文和写入；人类管理员仍可读上下文，不能执行连接器写操作。原生页面/商品/媒体/用户后台接口不向服务身份授予管理能力。

远端凭据只在独立服务读取。生产必须 HTTPS；HTTP 仅用于配置明确确认的 loopback staging，不接受局域网 HTTP 或任何 live HTTP。重定向拒绝；只读最多两次额外重试，整体 deadline、1/2 秒等待、Retry-After 上限 60 秒；根任务剩余预算不足即停止。返回页面/商品/实际有效模板和样式，剔除订单、客户记录和鉴权元数据。

主程序现有 `/api/commerce/projects/{id}/connections`、`refresh-context`、`context` API 和工作台连接卡片；调用固定 Connector 的连接身份、能力和快照路由。相同 request ID 去重，版本/项目/环境校验，重新绑定后旧快照失效；远端鉴权和权限错误只保留 allowlist 中的错误 code，不返回远端错误正文。主程序的服务令牌不出现在公开 settings、模型输出、记忆或 trace。

## 固定插件写协议

可信运营配置须在 wp-config.php 中设置 `MUSE_PROJECT_ID`, `MUSE_CONNECTION_ID`, `MUSE_ENVIRONMENT`, `MUSE_TARGET_URL`, `MUSE_SERVICE_USER_ID`、至少 32-byte 的独立 `MUSE_EXECUTION_SECRET`。目标 URL 必须与 WordPress home URL 完全匹配。该服务用户须通过 Application Passwords 认证；普通网页登录不能调用写操作。签名秘密不是模型 API 密钥，不交给模型、公开 API、记忆或导出包。

`POST /wp-json/muse/v1/operations` 只接受 operation 与 execution_authorization。HMAC 许可绑定项目、连接、环境、URL、完整操作摘要、全部资源条件、审查/批准摘要及不超过 30 分钟的期限。插件检查实际资源所有权与版本。九类操作是主题包安装、自有页面创建/更新/发布、自有导航、简单商品草稿/发布、四个商店页面选项和来源图片创建；没有任意 SQL、Shell、插件安装或 HTML/JS/PHP 生成入口。

图片仅接收已净化 PNG/JPEG/WebP 的精确字节、SHA、尺寸和项目引用，每图 10 MiB/20M 像素、项目最多 100 张/100 MiB。不接收远程 URL 或路径，不覆盖既有文件；文件中断保留未知结果。商品最多五张图片，主图与图库顺序绑定完整附件事实和受签名版本。现有 v2/v3 业务许可仍拒绝带图片的业务图，不能用测试 v1 grant 冒充商家批准。

`GET /wp-json/muse/v1/receipts/{operation_id}` 读取持久结果。相同 ID/摘要返回同一回执；不同摘要拒绝。发送/进程崩溃/未知 SQL 或文件系统结果保留 NEEDS_RECONCILIATION，后续同资源操作被拒绝。SQL 效果和成功回执同事务，WP hooks 或文件 swap 不属于该事务；不得宣称跨系统原子性。

主题包还需 `MUSE_PACKAGE_STORAGE`，指向 WordPress 根目录之外、受信任服务独占的私有目录。该目录与部署主题必须位于同一文件系统和挂载视图，否则 Linux 原子 rename 会失败。固定副本将整卷挂载在私有路径，以 site 子目录单独提供网站；可通过受信任配置 `MUSE_DEPLOY_THEME_ROOT` 指定部署挂载别名，目录的设备号和 inode 必须与当前主题相同，不能指定其他目录或符号链接。固定文件白名单、尺寸、路径、符号链接、不可变 PHP、静态内容与逐文件摘要均验证；不使用 ZIP 自动提取。安装保存私有 journal 与之前目录，不自动清理未知状态；目前最多保留 100 次安装记录。主题/导航存在非自有 DB header/template 覆盖时拒绝，不能删除商家编辑来“修好”预览。

待完成：隔离环境自动准备及真实 Linux 兼容验证、可信购买验证 producer、完整团队到真实验证/批准的联调和独立环境恢复验收。插件底层测试签名不代表真实商家批准；三角色提案回执也不代表 WordPress 写入完成。

## 显式启用独立发布服务

配置 JSON 可增加 execution_secrets，键须与 connections 的连接 ID 完全相同，值是与目标 wp-config.php 的 MUSE_EXECUTION_SECRET 相同的 UTF-8 字节（至少 32 byte）。只保存在连接服务的 0600 文件；不放入主程序配置、仓库、导出、Agent 工作区或聊天。

```bash
python -m muse.commerce_connector --config /srv/muse-connector/connections.json \
  --enable-publication --runtime-database /srv/muse-runtime/state.sqlite3 \
  --versions-lock /srv/muse-connector/versions.lock.json
```

上述路径仅是部署示例，须由运营人员配置受信 Linux 身份和明确数据库 ACL。连接器需访问既有运行数据库，主程序仍只配置固定 Connector 服务 URL/令牌；主程序不读取 WordPress/HMAC 秘密。Coding 容器不能挂载运行数据库、私有配置、Docker socket 或服务网络。禁止将 verified=false 改成 true 来绕过兼容/隔离测试；仓库当前清单不能启用发布。

商家正式图使用 v4 独立 audience；预览准备使用 v5 staging-preview purpose，只接受 staging，不能作为 live/live-test 许可或商家批准。预览准备只将私有来源日志标为 STAGED，商家计划仍 VERIFYING。两种图都有持久未知栅栏；过期/撤销/取消后的迟到结果可记账，但不能继续发送。

公开审查只返回冻结事实、图片描述符、代码和目标摘要、固定步骤及精简进度。发布回复须与共享受信 DB 的来源和日志一致，不能凭远端完成数放行。恢复按钮仅 GET 回执并核对，不会创建新写入；默认服务不生成验证报告或批准。
