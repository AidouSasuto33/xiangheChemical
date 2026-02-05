from .. import constants
from . import inventory_service

def process_start(cvn_obj, user):
    """
    CVN投产处理：扣减原料
    """
    # 映射关系: (Model字段值, Inventory Key, 中文名称)
    materials = [
        (cvn_obj.raw_dcb, constants.KEY_RAW_DCB, "二氯丁烷(新)"),
        (cvn_obj.input_recycled_dcb, constants.KEY_RECYCLED_DCB, "二氯丁烷(回收)"),
        (cvn_obj.raw_nacn, constants.KEY_RAW_NACN, "氰化钠"),
        (cvn_obj.raw_tbab, constants.KEY_RAW_TBAB, "TBAB"),
        (cvn_obj.raw_alkali, constants.KEY_RAW_ALKALI, "液碱"),
    ]

    for qty, key, name in materials:
        if qty and qty > 0:
            # 扣减原料 (负数)
            inventory_service.update_single_inventory(
                key=key,
                change_amount=-qty,
                note=f"批次 {cvn_obj.batch_no} 投料: {name}",
                user=user
            )

def process_finish(cvn_obj, user):
    """
    CVN完工处理：产出粗品 + 回收溶剂
    """
    # 1. 主产物：CVN粗品 (增加)
    if cvn_obj.crude_weight and cvn_obj.crude_weight > 0:
        inventory_service.update_single_inventory(
            key=constants.KEY_INTER_CVN_CRUDE,
            change_amount=cvn_obj.crude_weight,
            note=f"批次 {cvn_obj.batch_no} 产出: CVN粗品",
            user=user
        )

    # 2. 副产物：回收二氯丁烷 (增加)
    if cvn_obj.recovered_dcb_amount and cvn_obj.recovered_dcb_amount > 0:
        inventory_service.update_single_inventory(
            key=constants.KEY_RECYCLED_DCB,
            change_amount=cvn_obj.recovered_dcb_amount,
            note=f"批次 {cvn_obj.batch_no} 回收: DCB溶剂",
            user=user
        )