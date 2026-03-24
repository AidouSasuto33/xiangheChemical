from django.core.exceptions import ValidationError
from django.utils import timezone
from production.models import LaborRecord
from inventory.models import CostConfig


class LaborRecordService:
    """
    专门处理人工投入成本 (LaborRecord) 相关的业务逻辑
    """

    @staticmethod
    def save_labor_records(procedure_instance, post_data):
        """
        解析前端动态表单，批量保存、更新或删除人工投入记录。
        注意：此方法应当在 BaseProcedureService 的外层事务 (@transaction.atomic) 中被调用。
        """
        batch_no = procedure_instance.batch_no
        if not batch_no:
            return  # 新建状态下如果没有生成批号，直接跳过保存

        # 提取工艺类别标识 (假设模型名为 CVNSynthesis 等，或者直接使用预设的 procedure_type)
        procedure_type = getattr(procedure_instance, 'procedure_type', procedure_instance.__class__.__name__)

        # 1. 执行物理删除 (处理前端点垃圾桶移除并提交的记录)
        deleted_ids = post_data.getlist('deleted_labor_records')
        if deleted_ids:
            # 安全校验：强制加上 batch_no 过滤，防止跨工单恶意删表
            LaborRecord.objects.filter(id__in=deleted_ids, batch_no=batch_no).delete()

        # 2. 提取前端表单传递的并行数组
        record_ids = post_data.getlist('labor_record_id')
        config_ids = post_data.getlist('labor_config_id')
        counts = post_data.getlist('worker_count')
        hours = post_data.getlist('work_hours')
        dates = post_data.getlist('record_date')

        # 3. 遍历并执行 Upsert (更新或插入)
        for i in range(len(config_ids)):
            config_id_str = config_ids[i].strip()

            # 跳过没有选择工种的空行（例如前端隐藏的模板行，或者用户新增后没选的行）
            if not config_id_str:
                continue

            # 安全校验：验证工种是否存在
            try:
                config_id = int(config_id_str)
                config_obj = CostConfig.objects.get(id=config_id, category='labor')
            except (ValueError, CostConfig.DoesNotExist):
                raise ValidationError(f"无效的工种配置项。")

            # 安全校验：强制转换并拦截恶意数值（F12防篡改）
            try:
                worker_count = max(1, int(counts[i]))
                work_hours = max(0.5, float(hours[i]))
            except (ValueError, IndexError):
                raise ValidationError("投入人数和耗时必须是有效的数值。")

            # 日期处理，防御性取值
            try:
                record_date = dates[i] if dates[i] else timezone.now().date()
            except IndexError:
                record_date = timezone.now().date()

            record_id_str = record_ids[i] if i < len(record_ids) else ""

            if record_id_str:
                # [场景 A] 更新已有记录
                try:
                    record = LaborRecord.objects.get(id=int(record_id_str), batch_no=batch_no)
                    record.cost_config = config_obj
                    record.worker_count = worker_count
                    record.work_hours = work_hours
                    record.record_date = record_date
                    # 既然解锁修改了，应当按当下的最新价格更新快照
                    record.cost_snapshot = config_obj.price
                    record.save()
                except (ValueError, LaborRecord.DoesNotExist):
                    pass  # 忽略伪造或非法的 ID
            else:
                # [场景 B] 创建全新记录
                LaborRecord.objects.create(
                    batch_no=batch_no,
                    procedure_type=procedure_type,
                    cost_config=config_obj,
                    worker_count=worker_count,
                    work_hours=work_hours,
                    record_date=record_date,
                    cost_snapshot=config_obj.price  # 固化发生时的单价
                )