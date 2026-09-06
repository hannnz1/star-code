# 人工盲审说明

请只打开 manual-review-blind.csv。不要在完成前打开 manual-review-key.csv、自动评分报告或采样统计中的版本/分数信息。

每行阅读 original_fact、source_context，以及完整 compressed_context_or_summary，然后填写 human_label 和 human_notes。原文和待判断文本都完整保存，没有只截取自动评分支持的片段。请注意：部分长文本可能超过 Excel 单元格长度限制；使用不会截断长文本的 CSV 工具。CSV 是标准 UTF-8 BOM、带引号的多行字段，物理行数不等于记录数。

- PASS：核心事实和含义完整保留，没有影响后续任务执行的错误。
- PARTIAL：保留主要语义，但丢失重要限定、参数或细节。
- FAIL：缺失、错误、反转、混淆，或无法从待判断文本恢复。
- UNCERTAIN：现有上下文不足以可靠判断。

请按整条事实判断主体、数值和单位、否定关系、失败/待办状态；允许正确同义改写。不要修改 review_id 或原文列。human_notes 建议写证据及具体缺失/错误。完成后运行 quality-v1/compare_manual.py；该脚本才读取独立 key。模型没有代填人工标签，当前 human audit=PENDING。

人工样本按最新要求为约800候选的20%，即160条；不是全部4000 fact/view记录的20%。不同类别和分数层有意覆盖，样本一致率不能直接当作全体无偏错误率。
