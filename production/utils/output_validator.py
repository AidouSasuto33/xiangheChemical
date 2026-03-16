# production/utils/mass_balance_utils.py
from logging import getLogger

from core.constants.procedure_bom import PROCEDURE_BOM_MAPPING

def validate_output_balance(model_name, cleaned_data):
    """
    通用物料平衡校验：总产出 (包含 crude_weight 等) 不可大于 投入+辅料总重
    自动适配 process_bom.py 中定义的 inputs 和 outputs
    """
    config = PROCEDURE_BOM_MAPPING.get(model_name.lower())

    if not config:
        return True, ""

    total_input = 0.0
    total_output = 0.0

    # 1. 累加所有的投入与辅料 (遍历 inputs 列表中的 field)
    for item in config.get('inputs', []):
        field_name = item.get('field')
        val = cleaned_data.get(field_name)
        if val is not None:
            try:
                total_input += float(val)
            except ValueError:
                pass

    # 2. 累加所有的产出量 (遍历 outputs 列表中的 field)
    for item in config.get('outputs', []):
        field_name = item.get('field')
        val = cleaned_data.get(field_name)
        if val is not None:
            try:
                total_output += float(val)
            except ValueError:
                pass

    # 3. 校验逻辑
    # 仅当填写了产出量时才进行严格拦截。加入 round 避免浮点数精度引发误报。
    if total_output > 0 and round(total_output, 2) > round(total_input, 2):
        return False, f"物料平衡异常：产出总重量 ({round(total_output, 2)}kg) 不可大于投入与辅料总重量 ({round(total_input, 2)}kg)"

    return True, ""