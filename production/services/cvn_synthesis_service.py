from .. import constants
from . import inventory_service

def process_start(cvn_obj, user):
    """
    CVN投产处理：预检 -> 扣减
    """
    # 1. 准备物料清单 (Amount, Key, Name)
    # 注意：这里我们构造两个列表，一个用于检查(check_list)，一个用于执行(raw_materials)
    raw_materials = [
        (cvn_obj.raw_dcb, constants.KEY_RAW_DCB, "二氯丁烷(新)"),
        (cvn_obj.input_recycled_dcb, constants.KEY_RECYCLED_DCB, "二氯丁烷(回)"),
        (cvn_obj.raw_nacn, constants.KEY_RAW_NACN, "氰化钠"),
        (cvn_obj.raw_tbab, constants.KEY_RAW_TBAB, "TBAB"),
        (cvn_obj.raw_alkali, constants.KEY_RAW_ALKALI, "液碱"),
    ]

    # 2. 构造检查请求 (Key, Amount, Name)
    check_list = []
    for qty, key, name in raw_materials:
        if qty and qty > 0:
            check_list.append((key, qty, name))

    # 3. 调用库存预检 (第一道防线)
    if check_list:
        is_valid, errors = inventory_service.check_batch_availability(check_list)
        
        if not is_valid:
            # 使用标准换行符 \n，保持 Service 层纯净
            formatted_errors = "\n".join([f"• {err}" for err in errors])
            error_msg = f"库存不足，无法投产！缺货详情:\n{formatted_errors}"
            raise ValueError(error_msg)

    # 4. 预检通过，执行实际扣减 (第二道防线执行)
    for qty, key, name in raw_materials:
        if qty and qty > 0:
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