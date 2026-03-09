from django.utils import timezone
from django.db import transaction
from core import constants
from inventory.services import inventory_service
# 引入我们新写的状态机常量和 Service
from production.services.partial.procedure_state_service import ProcedureStateService


def process_start(cvn_obj, user):
    """
    CVN投产处理：预检 -> 扣减 -> 属性更新 -> 状态联动更新
    """
    # 1. 准备物料清单 (Amount, Key, Name)
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
            formatted_errors = "\n".join([f"• {err}" for err in errors])
            error_msg = f"库存不足，无法投产！缺货详情:\n{formatted_errors}"
            raise ValueError(error_msg)

    # 4. 预检通过，执行实际扣减与状态流转 (放入统一事务中)
    with transaction.atomic():
        # 扣减库存
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

        # 更新釜皿业务属性（状态的防呆和变更交由 StateService 接管）
        kettle = cvn_obj.kettle
        kettle.current_batch_no = cvn_obj.batch_no
        kettle.last_process = 'cvn_syn'
        total_input = (cvn_obj.raw_dcb + cvn_obj.raw_nacn + cvn_obj.raw_tbab + cvn_obj.raw_alkali)
        kettle.current_level = total_input
        kettle.save()

        # 记录时间并调用状态机统一处理状态流转
        if not cvn_obj.start_time:
            cvn_obj.start_time = timezone.now()
        ProcedureStateService.process_action(cvn_obj, constants.ProcedureAction.START_PRODUCTION, user=user)


def process_finish(cvn_obj, user):
    """
    CVN完工处理：产出校验 -> 入库 -> 释釜属性更新 -> 状态联动更新
    """
    # 1. 产出校验
    if (cvn_obj.crude_weight or 0) <= 0:
        raise ValueError("完工必须填写有效的产出重量！")

    with transaction.atomic():
        # 2. 主产物：CVN粗品 (增加)
        if cvn_obj.crude_weight and cvn_obj.crude_weight > 0:
            is_success = inventory_service.update_single_inventory(
                key=constants.KEY_INTER_CVN_CRUDE,
                change_amount=cvn_obj.crude_weight,
                note=f"批次 {cvn_obj.batch_no} 产出: CVN粗品",
                user=user
            )
            if not is_success:
                raise ValueError(
                    f"系统严重错误：\n 物料: CVN粗品库存 应增加{cvn_obj.crude_weight}L \n增加失败！操作已全部回滚！")

        # 3. 副产物：回收二氯丁烷 (增加)
        if cvn_obj.recovered_dcb_amount and cvn_obj.recovered_dcb_amount > 0:
            is_success = inventory_service.update_single_inventory(
                key=constants.KEY_RECYCLED_DCB,
                change_amount=cvn_obj.recovered_dcb_amount,
                note=f"批次 {cvn_obj.batch_no} 回收: DCB溶剂",
                user=user
            )
            if not is_success:
                raise ValueError(
                    f"系统严重错误：\n 物料: DCB溶剂库存 应增加{cvn_obj.recovered_dcb_amount}L \n增加失败！操作已全部回滚！")

        # 4. 清理釜皿业务属性
        kettle = cvn_obj.kettle
        kettle.current_batch_no = None
        kettle.current_level = 0
        kettle.last_product_name = "CVN粗品"
        kettle.save()

        # 5. 记录时间并调用状态机处理完工流转与设备释放
        if not cvn_obj.end_time:
            cvn_obj.end_time = timezone.now()
        ProcedureStateService.process_action(cvn_obj, constants.ProcedureAction.FINISH_PRODUCTION, user=user)