# core/utils/bom_utils.py

from core.constants.procedure_bom import PROCEDURE_BOM_MAPPING


def get_procedure_materials(procedure_key, obj, material_type='inputs'):
    """
    根据工艺字典动态获取物料清单及实际数量。

    :param procedure_key: 工艺的键名，例如 'cvnsynthesis'
    :param obj: 对应的模型实例（如 CvnSynthesis 实例）
    :param material_type: 'inputs' (投入) 或 'outputs' (产出)
    :return: 包含 (数量, 字段/Key, 名称) 的列表，剔除了数量为0或空的物料
    """
    if procedure_key not in PROCEDURE_BOM_MAPPING:
        raise ValueError(f"系统严重错误：工艺字典中未定义 {procedure_key} 的规则！")

    config = PROCEDURE_BOM_MAPPING[procedure_key]
    materials_config = config.get(material_type, [])

    actual_materials = []

    for item in materials_config:
        field_name = item['field']
        display_name = item['name']

        # 动态从对象中获取对应字段的值，默认为 0
        amount = getattr(obj, field_name, 0)

        # 只返回实际有数值的物料
        if amount and amount > 0:
            actual_materials.append((amount, field_name, display_name))

    return actual_materials