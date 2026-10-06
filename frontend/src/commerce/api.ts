export type Api = <T>(path: string, init?: RequestInit) => Promise<T>;

export function commerceErrorMessage(error: {code?: string; field_errors?: {row?: number; field?: string; code?: string}[]}): string {
  const codes: Record<string, string> = {
    PROJECT_BUSY: '请先停止运行中任务、核对未知结果，并清理预览环境，再移除店铺',
    PROJECT_ARCHIVED: '店铺已归档，请在设置中恢复后继续',
    INPUT_INVALID: '输入校验未通过', RESOURCE_CONFLICT: '资料已更新，请重新打开项目后提交',
    NOT_FOUND: '未找到商家项目', VERIFICATION_UNAVAILABLE: '店铺服务尚未配置',
    APPROVAL_REQUIRED: '请先审查并批准当前变更', AUTH_REQUIRED: '请重新连接店铺',
    UNSUPPORTED_CAPABILITY: '店铺版本或主题未通过能力验证', READ_TEMPORARY_FAILURE: '店铺读取暂时失败，原上下文已保留',
    PERMISSION_DENIED: '连接权限不足', MODEL_UNAVAILABLE: '模型配置或服务不可用',
    FACTS_INCOMPLETE: '商家事实未完整确认', MODEL_OUTPUT_INVALID: '模型结构化输出未通过校验',
    BUDGET_EXHAUSTED: '团队共享预算已耗尽',
    REVIEW_STALE: '审查内容已变化，请刷新团队状态后重新审查',
    APPROVAL_EXPIRED: '商家批准已过期，请重新审查',
    EXECUTION_BOUNDARY_UNAVAILABLE: '隔离执行环境尚未配置或通过验证',
    WRITE_OUTCOME_UNKNOWN: '发送结果未知，请只读核对发布结果',
    VERIFICATION_FAILED: '店铺验证未通过，请查看诊断后修复',
  };
  const fields: Record<string, string> = {sku: 'SKU', name: '名称', price: '价格', currency: '币种',
    stock: '库存', category: '分类', description: '描述', image_names: '图片', csv: 'CSV',
    brand_name: '品牌名称', language: '语言'};
  const reasons: Record<string, string> = {DUPLICATE_SKU: '批内重复', SKU_CONFLICT: '店铺已存在',
    BATCH_LIMIT: '每批需要 1–20 件商品', FORMULA_REJECTED: '不接受公式单元格',
    DUPLICATE_IMAGE: '存在重复图片', INPUT_INVALID: '请检查格式、内容和项目设置'};
  const details = (error.field_errors || []).map(item =>
    `${item.row ? `第 ${item.row} 行 · ` : ''}${fields[item.field || ''] || item.field || '字段'}: ${reasons[item.code || ''] || '请检查输入'}`);
  return [codes[error.code || ''] || '商家操作未完成', ...details].join('\n');
}
