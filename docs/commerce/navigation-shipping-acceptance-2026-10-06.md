# Crew 分类导航与配送规则验收

本轮对应可视化编辑计划的 C、E 补充：一级分类导航和 Crew 内配送规则表单。实现位于本地 `outputs/muse-next`，预览地址为 http://127.0.0.1:8876/；不据此推断已推送 GitHub或同步桌面旧目录。

## 使用方法

1. 在“商品”校验并保存商品批次，填写商品分类。
2. 在“网站 → 建站方案”生成或打开当前结构草稿。
3. 在“分类导航草稿”选择本店当前版本的商品批次，勾选分类、修改显示名称并调整顺序，再保存。
4. 在“配送规则草稿”填写区域名称、ISO 国家代码、固定运费和可选免运门槛。金额按店铺币种，最多两位小数；多个区域的国家不能重复。
5. 保存后可以按国家和购物车小计计算草稿运费。未保存的修改不能充当已确认报价。
6. 后续建站选择同一商品批次，经过封存、隔离预览、购买验证和发布审查，再明确批准执行。保存草稿本身不改变远程店铺。

界面支持中英文及 1440/390px。两个表单独立保留未保存输入；错误和冲突保留编辑内容；切店、切版本及卸载后的旧响应不能回写当前视图。

## 实现范围

分类来自批准的商品事实，发布时才绑定实际分类 ID、slug 和同源链接；不接受任意目标 URL。分类丢失、名称变化或来源批次不一致阻断流程，不猜测替代链接。当前只支持一级分类导航，最多十项；原页面导航保留。

配送最多十个区域，每个区域最多二十个国家；固定运费及订单金额免运按 Decimal 精确计算，门槛包含相等值。只管理本项目拥有的地区和配送方式，独立核对已有方式身份和外部配置摘要。未知写入结果进入核对状态，不能盲目重发。税务、实时承运商报价、履约、域名和正式支付连接不属于本轮。

新商品上线保留已建站的导航、配送及主题。若独立预览缺少旧导航分类，可在一次性预览中建立隐藏、零库存、零价格的辅助商品；种子只接受 v8 staging 授权，必须明确读回 hidden，绝不进入商家发布图。业务批次仍限二十件，预览额外最多十个种子；旧协议上限保持不变。

自动购买验证目前提供 US/AU/GB/CA/DE/FR/JP 的合成地址，其他国家的规则可以编辑和算草稿报价，但没有自动真实购买通过证据；不将支持 ISO 国家输入等同于逐国端到端验收。

## 自动证据与边界

- `work/visual-editor-evidence/navigation-shipping-contracts-final.xml`：151 passed，涵盖来源、API、冻结图、Python/PHP 协议、购买事实及旧流程兼容。
- `navigation-shipping-final-contracts.xml`：40 passed，补充满额二十商品＋缺失分类、PHP 容量兼容和种子必须明确 hidden。
- `navigation-shipping-browser-final.xml`：4 passed，分类、配送、语言、响应式、跨表单保存保留及版本变化期间慢响应。
- `navigation-shipping-late-success-csp.xml`：3 passed，旧店失败、A→B 迟到成功及 A→B→A 迟到成功均不回写。
- 前端构建、1036 条翻译/816 处明确文案检查和 OpenAPI 类型同步通过。
- 只读代码复审确认满额商品预览、卸载代次、父回调版本绑定和隐藏种子读回检查已闭合。

报告覆盖有重叠，不能相加为独立用例总数；本轮没有重跑整个历史测试集。API 调用和费用均为零。

真实 WordPress/WooCommerce 建站报告 `wordpress-navigation-shipping-build-passed.json`：六阶段通过，19/19 发布完成，分类页面可访问，实际购物车三项边界通过（小计 12.30/24.60/36.90，运费分别 6/0/0）。

首次连续上新报告 `wordpress-navigation-shipping-build-launch-failed.json`：建站通过，上新 reference/source_capture/staging/buyer 通过，browser 中途报告 BROWSER_UNAVAILABLE，整体未通过；两资源均 CLEANED。当时 Windows 宿主盘已满。保留失败报告，重新验证不代替失败历史。

最新原生副本共 227 个文件，清单为 `navigation-shipping-final-runtime-manifest.json`。最终复测 `wordpress-navigation-shipping-final-browser-failed.json` 已结束：reference/source_capture/staging/buyer 通过，browser 报 STOREFRONT_LINK_FAILED、PAGE_CAPTURE_FAILED 和 BROWSER_UNAVAILABLE，仅捕获 1 帧，整体未通过；未进入发布。此时磁盘已有可用空间、隔离系统可用内存充足，不能将失败归因已满磁盘，也不能宣称最终连续验收通过。浏览器/预览转发环境的确切原因仍待定位；没有跳过检查或重发未知写入。

结论：本轮两项功能已实现，专项自动测试、真实建站分类及运费边界有通过证据；最新完整连续旅程验收仍未通过。所有真实测试均为合成一次性隔离站；生产商家发布、AUD 店铺品牌效果及人工体验尚未验收。
