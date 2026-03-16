# core/utils/bom_utils.py
from core.constants.procedure_bom import PROCEDURE_BOM_MAPPING

def get_procedure_bom_info(procedure_key, material_type='inputs', return_type='field'):
    """
    根据工艺键名获取物料清单信息。

    :param procedure_key: 工艺键名, 如 'cvnsynthesis'
    :param material_type: 物料类型, 可选: 'inputs', 'outputs', 'qc_fields', 'qc_pre_fields'
    :param return_type: 返回类型, 'field' (模型字段名) 或 'name' (页面显示名)
    :return: 字段列表或名称列表
    """
    # 1. 安全获取工艺配置
    procedure_config = PROCEDURE_BOM_MAPPING.get(procedure_key)
    if not procedure_config:
        return []

    # 2. 获取对应的物料/质检列表
    data_list = procedure_config.get(material_type, [])

    # 3. 处理字典列表结构
    if return_type == 'field':
        return [item.get('field') for item in data_list if 'field' in item]
    elif return_type == 'name':
        return [item.get('name') for item in data_list if 'name' in item]

    return []


def get_display_name(procedure_key):
    """获取工艺的中文显示名称"""
    return PROCEDURE_BOM_MAPPING.get(procedure_key, {}).get('name', '未知工艺')


def validate_field_in_procedure(procedure_key, field_name, material_type='inputs'):
    """校验某个字段是否属于该工艺的指定物料类型"""
    fields = get_procedure_bom_info(procedure_key, material_type, return_type='field')
    return field_name in fields