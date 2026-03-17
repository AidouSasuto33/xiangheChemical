from django.utils import timezone
from django.db import transaction
from core.constants import ProcedureAction
from ..utils.bom_utils import get_procedure_bom_info # 引入物料获取函数
from inventory.services import inventory_service
from production.services.partial.procedure_state_service import ProcedureStateService
from production.utils.qc_utils import validate_qc_sum_100
from production.utils.output_validator import validate_output_balance

PROCEDURE_KEY = 'cvnsynthesis' # 获取物料常量参数

def process_start(cvn_obj, user):
    """
    CVN投产处理：动态BOM预检 -> 扣减 -> 动态计算总量并更新釜属性 -> 状态机流转
    """
    # 1. 动态获取投料清单
    input_fields = get_procedure_bom_info(PROCEDURE_KEY, 'inputs', 'field')
    input_names = get_procedure_bom_info(PROCEDURE_KEY, 'inputs', 'name')

    raw_materials = []
    for field, name in zip(input_fields, input_names):
        qty = getattr(cvn_obj, field, 0)
        if qty and float(qty) > 0:
            # 统一字段规范后，直接将 field 作为 inventory 的唯一标识(key)
            raw_materials.append((qty, field, name))

    # 2. 构造检查请求 (Key, Amount, Name)
    check_list = [(key, qty, name) for qty, key, name in raw_materials]

    # 3. 调用库存预检 (第一道防线)
    if check_list:
        is_valid, errors = inventory_service.check_batch_availability(check_list)
        if not is_valid:
            formatted_errors = "\n".join([f"• {err}" for err in errors])
            error_msg = f"库存不足，无法投产！缺货详情:\n{formatted_errors}"
            raise ValueError(error_msg)

    # 4. 预检通过，执行实际扣减与状态流转
    with transaction.atomic():
        # 扣减库存 (动态遍历)
        for qty, key, name in raw_materials:
            is_success = inventory_service.update_single_inventory(
                key=key,
                change_amount=-qty,
                note=f"批次 {cvn_obj.batch_no} 投料: {name}",
                user=user
            )
            if not is_success:
                raise ValueError(f"系统严重错误：物料 {name} (Key: {key}) \n扣减失败！操作已全部回滚！")

        # 更新釜皿业务属性
        kettle = cvn_obj.kettle
        kettle.current_batch_no = cvn_obj.batch_no
        kettle.last_process = PROCEDURE_KEY

        # 抛弃硬编码，动态计算投入总量
        total_input = sum(qty for qty, _, _ in raw_materials)
        kettle.current_level = total_input
        kettle.save()

        # 记录时间并调用状态机统一处理状态流转
        if not cvn_obj.start_time:
            cvn_obj.start_time = timezone.now()
        ProcedureStateService.process_action(cvn_obj, ProcedureAction.START_PRODUCTION, user=user)


def process_finish(cvn_obj, user):
    """
    CVN完工处理：动态产出校验 -> 动态入库 -> 释釜属性更新 -> 状态机流转
    """
    # 提取模型中的所有字段，组装成字典，模拟 cleaned_data 传给校验工具
    data_dict = {field.name: getattr(cvn_obj, field.name) for field in cvn_obj._meta.fields}
    import logging
    logger = logging.getLogger()
    logger.warning(f"cvn_obj: {cvn_obj}")
    logger.warning(f"data_dict: {data_dict}")
    # === 新增：1. 质检百分比校验 ===
    is_qc_valid, qc_msg = validate_qc_sum_100(PROCEDURE_KEY, data_dict)
    if not is_qc_valid:
        raise ValueError(f"完工拦截：{qc_msg}")

    # === 新增：2. 投入产出平衡校验 ===
    is_bal_valid, bal_msg = validate_output_balance(PROCEDURE_KEY, data_dict)
    if not is_bal_valid:
        raise ValueError(f"完工拦截：{bal_msg}")

    # 1. 动态获取主产出清单
    output_fields = get_procedure_bom_info(PROCEDURE_KEY, 'outputs', 'field')
    output_names = get_procedure_bom_info(PROCEDURE_KEY, 'outputs', 'name')

    if (cvn_obj.cvn_syn_crude_weight or 0) <= 0:
        raise ValueError("完工必须填写有效的产出重量！")

    with transaction.atomic():
        # 2. 动态遍历产出物料入库
        for field, name in zip(output_fields, output_names):
            qty = getattr(cvn_obj, field, 0)
            if qty and float(qty) > 0:
                is_success = inventory_service.update_single_inventory(
                    key=field,
                    change_amount=qty,
                    note=f"批次 {cvn_obj.batch_no} 产出: {name}",
                    user=user
                )
                if not is_success:
                    raise ValueError(f"系统严重错误：\n 物料: {name}库存 应增加{qty} \n增加失败！操作已全部回滚！")

        # TODO 拆分dcb回收工艺后，删除此处
        # 3. 兼容防丢逻辑：处理副产物回收 (建议后续将此项补充到 PROCEDURE_BOM_MAPPING 中并删掉此处硬编码)
        if hasattr(cvn_obj,
                   'recovered_dcb_amount') and cvn_obj.recovered_dcb_amount and cvn_obj.recovered_dcb_amount > 0:
            is_success = inventory_service.update_single_inventory(
                key='recycled_dcb',  # 对应回流的二氯丁烷字典key
                change_amount=cvn_obj.recovered_dcb_amount,
                note=f"批次 {cvn_obj.batch_no} 回收: DCB溶剂",
                user=user
            )
            if not is_success:
                raise ValueError(f"系统严重错误：\n 物料: DCB溶剂库存 应增加{cvn_obj.recovered_dcb_amount}L \n增加失败！")

        # 4. 清理釜皿业务属性
        kettle = cvn_obj.kettle
        kettle.current_batch_no = None
        kettle.current_level = 0

        # 动态获取主产物名称用于显示
        main_product_name = output_names[0] if output_names else "主产物"
        kettle.last_product_name = main_product_name
        kettle.save()

        # 5. 记录时间并调用状态机处理完工流转与设备释放
        if not cvn_obj.end_time:
            cvn_obj.end_time = timezone.now()
        ProcedureStateService.process_action(cvn_obj, ProcedureAction.FINISH_PRODUCTION, user=user)