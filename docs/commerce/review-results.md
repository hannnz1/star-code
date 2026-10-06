# Commerce 准备功能审查与处置

日期：2026-09-30。基线：`4aec15a`；审查范围见 [review-package.md](review-package.md)。本次独立审查覆盖准备功能批次，不代表完整 Commerce MVP 审查通过。

## Important 问题与修复

1. **不完整远端快照被接受**：增加 RemoteSnapshot 及页面、商品、设置、模板、global styles 严格类型。缺失/非法响应返回脱敏 READ_TEMPORARY_FAILURE，合法空集合仍可读取，显式 null 库存保留。
2. **能力检查与部署清单字段不一致**：共用 wordpress/woocommerce 字段及 validate_lock，未 verified 或无镜像 digest 的版本锁不能通过能力检查。
3. **项目切换后导入晚返回**：使用同步更新的 activeProject 引用核对成果所属项目。真实浏览器延迟 A 项目 POST、切到 B 再返回，验证 B 不显示 A 商品而数据库仍正确归属 A。

失败证据：`work/commerce-review-red.log`、`work/commerce-review-ui-red2.log`。修复后 `work/commerce-review-green.log`：77 passed（当时 75 项 Commerce 与 2 项原前端）。保留原始失败，不解除 CSP、不削弱断言、没有重复评审覆盖结果。

全量回归另发现原记忆合并在 updated_at 相同下保留对象不稳定。冻结时钟补测发现重复 ID 和保留对象已修改也可能错误归档事实；增加持久 memory_versions 顺序、ID 去重拒绝、保留对象当前版本和内容检查。3 项复现先失败后通过，与原记忆合跑 15 passed；最终全量此问题未再失败。不据此宣称 8 小时 benchmark 或全部并发场景重新验收。

## Declined to judge 的处置

每项均为未完成门槛；不把离线测试用作替代。

| 范围 | 决定及风险 |
|---|---|
| PHP/WP 实际快照、有效模板 | 固定只读插件保留，真实环境 BLOCKED；必须运行 PHP lint、编辑器覆盖/global styles 回读 |
| 手工编辑覆盖前提条件 | 不开放发布；P7 必须写前比较实际资源版本 |
| 店铺已有 SKU 对账 | 明确 store_conflicts_checked=false；当前不是可发布新品 |
| 图片持久存储和所有权 | 解码已测试，上传 API/UI 未开放；尚需成果项目归属验证 |
| ZIP/主题/预览边界 | 审查后补离线主题 ZIP/不可变文件检查；真实 WP/staging/预览边界仍 BLOCKED |
| 写幂等、超时、重启回执 | 无写接口；P3/P7 必须真实故障注入和对账 |
| 取消子任务/在途发布 | Commerce 编排未开放；原任务取消不能代替业务取消语义 |
| 订单、库存保留 | 零店铺写入，无整库覆盖入口；需实际订单新增后发布页面验收 |
| Linux 身份/网络/socket/秘密隔离 | 无环境，BLOCKED；须以 coding 身份实测越权失败 |
| 镜像 digest、邮件/支付/索引限制 | versions.lock.json verified=false，部署拒绝；配置标志不是运行时限制证据 |
| 模型、预算、三角色、买家流程 | 零模型调用、无 Commerce 子任务；P4/P10 未实现，不复用旧 benchmark/费用授权 |
| 第二套环境恢复 | NOT_RUN；P10 要求导出、恢复及重新购买验证 |
| 干净锁定安装和 wheel | uv 执行被拒、venv 无 hatchling/pip，BLOCKED；需 locked install 与 wheel 内主题资源验证 |
| 最终全量回归 | 实施者执行，结果见阶段检查点；原 Windows taskkill 权限测试仍未通过 |

独立审查没有 Critical/Minor，三个 Important 已修复。审查后的主题补充有离线测试，尚无独立主题审查/真实 WP 验证。整个 Commerce MVP 未具备交付条件。
