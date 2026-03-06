from django.utils import timezone
from django.db import transaction
from production.models.core import BaseProductionStep
from core import constants
from inventory.services import inventory_service

def process_start(cvn_obj, user):
    """
    CVN投产处理：釜皿锁定 -> 预检 -> 扣减 -> 状态更新
    """
    # 1. 釜皿检查与锁定 (Kettle Control)
    kettle = cvn_obj.kettle
    if kettle.status != 'idle' and kettle.current_batch_no != cvn_obj.batch_no:
        raise ValueError(f"设备 {kettle.name} 当前非空闲，无法投产！")

    kettle.status = 'running'
    kettle.current_batch_no = cvn_obj.batch_no
    kettle.last_process = 'cvn_syn'
    # 估算当前液位 = 所有原料之和
    total_input = (cvn_obj.raw_dcb + cvn_obj.raw_nacn + cvn_obj.raw_tbab + cvn_obj.raw_alkali)
    kettle.current_level = total_input
    kettle.save()

    # 2. 准备物料清单 (Amount, Key, Name)
    raw_materials = [
        (cvn_obj.raw_dcb, constants.KEY_RAW_DCB, "二氯丁烷(新)"),
        (cvn_obj.input_recycled_dcb, constants.KEY_RECYCLED_DCB, "二氯丁烷(回)"),
        (cvn_obj.raw_nacn, constants.KEY_RAW_NACN, "氰化钠"),
        (cvn_obj.raw_tbab, constants.KEY_RAW_TBAB, "TBAB"),
        (cvn_obj.raw_alkali, constants.KEY_RAW_ALKALI, "液碱"),
    ]

    # 3. 构造检查请求 (Key, Amount, Name)
    check_list = []
    for qty, key, name in raw_materials:
        if qty and qty > 0:
            check_list.append((key, qty, name))

    # 4. 调用库存预检 (第一道防线)
    if check_list:
        is_valid, errors = inventory_service.check_batch_availability(check_list)
        
        if not is_valid:
            # 使用标准换行符 \n，保持 Service 层纯净
            formatted_errors = "\n".join([f"• {err}" for err in errors])
            error_msg = f"库存不足，无法投产！缺货详情:\n{formatted_errors}"
            raise ValueError(error_msg)

    # 5. 预检通过，执行实际扣减 (第二道防线执行)
    with transaction.atomic():
        for qty, key, name in raw_materials:
            if qty and qty > 0:
                is_success = inventory_service.update_single_inventory(
                    key=key,
                    change_amount=-qty,
                    note=f"批次 {cvn_obj.batch_no} 投料: {name}",
                    user=user
                )
                if not is_success:
                    raise ValueError(f"系统严重错误：物料 {name} (Key: {key}) \n扣减失败！操作已全部回滚！")

        # 6. 更新单据状态
        cvn_obj.status = 'running'
        if not cvn_obj.start_time:
            cvn_obj.start_time = timezone.now()
        cvn_obj.save()


def process_finish(cvn_obj, user):
    """
    CVN完工处理：产出校验 -> 释釜 -> 入库 -> 状态更新
    """
    # 1. 产出校验
    if (cvn_obj.crude_weight or 0) <= 0:
        raise ValueError("完工必须填写有效的产出重量！")

    # 2. 释放釜皿
    kettle = cvn_obj.kettle
    kettle.status = 'to_clean'  # 转入待清洗
    kettle.current_batch_no = None  # 清空占用
    kettle.current_level = 0
    kettle.last_product_name = "CVN粗品"
    kettle.save()

    with transaction.atomic():

        # 3. 主产物：CVN粗品 (增加)
        if cvn_obj.crude_weight and cvn_obj.crude_weight > 0:
            is_success = inventory_service.update_single_inventory(
                key=constants.KEY_INTER_CVN_CRUDE,
                change_amount=cvn_obj.crude_weight,
                note=f"批次 {cvn_obj.batch_no} 产出: CVN粗品",
                user=user
            )
            if not is_success:
                raise ValueError(f"系统严重错误：\n 物料: CVN粗品库存 应增加{cvn_obj.crude_weight}L \n增加失败！操作已全部回滚！")

        # 4. 副产物：回收二氯丁烷 (增加)
        if cvn_obj.recovered_dcb_amount and cvn_obj.recovered_dcb_amount > 0:
            is_success = inventory_service.update_single_inventory(
                key=constants.KEY_RECYCLED_DCB,
                change_amount=cvn_obj.recovered_dcb_amount,
                note=f"批次 {cvn_obj.batch_no} 回收: DCB溶剂",
                user=user
            )
            if not is_success:
                raise ValueError(f"系统严重错误：\n 物料: DCB溶剂库存 应增加{cvn_obj.recovered_dcb_amount}L \n增加失败！操作已全部回滚！")

        # 5. 更新单据状态
        cvn_obj.status = BaseProductionStep.STATUS_COMPLETED

        if not cvn_obj.end_time:
            cvn_obj.end_time = timezone.now()
        cvn_obj.save()