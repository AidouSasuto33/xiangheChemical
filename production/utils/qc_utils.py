from core.constants.procedure_bom import PROCEDURE_BOM_MAPPING

def validate_qc_sum_100(model_name, cleaned_data):
    """
    校验指定工艺的质检字段总和是否超过 100%
    自动适配 process_bom.py 中定义的 qc_fields (以及精馏特有的 qc_pre_fields)
    """
    config = PROCEDURE_BOM_MAPPING.get(model_name.lower())
    if not config:
        return True, ""

    # 1. 校验标准产出的质检字段 (qc_fields)
    qc_fields = config.get('qc_fields', [])
    if qc_fields:
        total = 0.0
        for field in qc_fields:
            val = cleaned_data.get(field['field']) # 获取的field格式：{'field': 'content_cvn', 'name': 'CVN含量%'}，所以要用field['field']
            if val is not None:
                try:
                    total += float(val)
                except ValueError:
                    pass

        if total != 100.0:
            return False, f"质检数据异常：各项含量总和 ({round(total, 2)}%) 必须等于 100%"

    # 2. 校验精前质检字段 (如 CVN精馏 特有的 qc_pre_fields)
    qc_pre_fields = config.get('qc_pre_fields', [])
    if qc_pre_fields:
        pre_total = 0.0
        for field in qc_pre_fields:
            val = cleaned_data.get(field['field'])
            if val is not None:
                try:
                    pre_total += float(val)
                except ValueError:
                    pass

        if 99.9 > pre_total > 100.1:
            return False, f"精前质检数据异常：各项含量总和 ({round(pre_total, 2)}%) 需约等于 100%"

    return True, ""

# 预留的合格标准评估逻辑（待未来在 BOM 中补充具体阈值后激活）
def evaluate_qc_status(model_name, data):
    """评估产品是否达到质检合格标准 (预留接口)"""
    return True, {}