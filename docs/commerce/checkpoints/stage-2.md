# 第二阶段检查点：离线主题部分实现

日期：2026-09-30。状态：**PARTIAL / 正式部署、验证与发布 BLOCKED**。第一阶段未整体放行；此处仅记录 spec 允许独立继续的离线模板原型，不宣称进入生产发布阶段。

源码基线、389 个文件的 SHA-256 清单、环境锁及最终全量回归见 [stage-1.md](stage-1.md)。主题补充在独立准备批次审查之后开发，没有独立主题评审。无模型调用、无店铺操作、无可发布包。

| 任务/检查 | 实际状态 |
|---|---|
| P5 七页/导航结构 | 持久结构草稿、缺失设置与修改后 STALE 已实现；原生主题文件已创建 |
| P5 离线包 | 确定性 ZIP、文件 manifest/大小/哈希、固定 PHP、禁止 JS/越界/重复/符号链接、静态内容外部资源检查已实现 |
| P5 原生编辑器与 Woo 实际渲染 | NOT_RUN；PHP lint、WordPress block schema、模板覆盖、native cart/checkout 均需真实环境 |
| P6 coding 隔离/成果桥/购买验证 | NOT_IMPLEMENTED / NOT_RUN |
| P7 30 分钟审批/版本绑定/发布恢复 | NOT_IMPLEMENTED / NOT_RUN |
| 干净安装与 wheel 主题资源 | BLOCKED：uv 执行拒绝、venv 无 hatchling/pip；仅配置 force-include，未证明安装成功 |

实际自检：首批主题测试 13 failed（模块缺失）→13 passed；补充主动/外部内容探针和原结构用例合跑 23 passed。证据：`work/commerce-theme-red.log`、`work/commerce-theme-green.log`、`work/commerce-theme-integrity.log`。

```powershell
.\.venv\Scripts\python.exe -m pytest tests/muse/commerce/test_site_package.py tests/muse/commerce/test_site_blueprint.py -q -p no:cacheprovider --basetemp work/commerce-theme-integrity-tmp
```

加入主题后最终全量为 1172 passed、3 skipped、1 原 launcher 权限失败；完整日志 `work/commerce-final-with-theme.log`。不把 ZIP 检查通过算作可购买网站通过，不把固定 PHP 内容匹配算作 PHP lint 或运行隔离通过。

阶段决定：**不放行发布**。下一步需接好 P2/P3 与业务编排、冻结干净代码版本，完成 staging、受限 coding 及确定性验证，再实现批准和逐项发布/对账。真实安全探针、失效批准、部分成功、断网和手工编辑冲突尚无通过证据。
