from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import transaction

from production.models import LaborRecord
from inventory.models import CostConfig


class LaborRecordService:
    """
    专门处理人工投入成本 (LaborRecord) 相关的业务逻辑。
    架构设计：采用“单条原子操作 + 批量幂等同步”的双轨模式。
    """

    @classmethod
    def save_labor_records(cls, procedure_instance, labor_data):
        """
        批量幂等同步人工投入记录（兜底逻辑）。
        用于工单状态切换（如完工、投产）时，确保前端表格数据完整落库。
        """
        batch_no = procedure_instance.batch_no
        if not batch_no or not labor_data:
            return

        # 确定工艺类别标识
        procedure_type = getattr(procedure_instance, 'PROCEDURE_KEY', procedure_instance.__class__.__name__.lower())

        records = labor_data.get('records', [])
        for item in records:
            # 这里的 item 结构需符合: {'id': xxx, 'cost_config_id': xxx, ...}
            cls.update_single_record(batch_no, procedure_type, item)

    @classmethod
    def update_single_record(cls, batch_no, procedure_type, item):
        """
        同步单条记录（Ajax 与 批量同步共用的核心逻辑）。
        """
        record_id = item.get('id')
        config_id = item.get('cost_config_id')

        if not config_id:
            return None

        try:
            config_obj = CostConfig.objects.get(id=config_id)
            worker_count = int(item.get('worker_count', 0))
            work_hours = float(item.get('work_hours', 0))
            record_date = item.get('record_date') or timezone.now().date()
        except (CostConfig.DoesNotExist, ValueError, TypeError):
            raise ValidationError(f"人工数据无效：配置ID {config_id}")

        if record_id:
            # 【场景 A】 更新已有记录 (带上 batch_no 确保安全隔离)
            LaborRecord.objects.filter(id=record_id, batch_no=batch_no).update(
                cost_config=config_obj,
                worker_count=worker_count,
                work_hours=work_hours,
                record_date=record_date,
                cost_snapshot=config_obj.price  # 重新保存时按最新配置更新快照
            )
            return record_id
        else:
            # 【场景 B】 创建全新记录
            new_record = LaborRecord.objects.create(
                batch_no=batch_no,
                procedure_type=procedure_type,
                cost_config=config_obj,
                worker_count=worker_count,
                work_hours=work_hours,
                record_date=record_date,
                cost_snapshot=config_obj.price
            )
            return new_record.id

    @classmethod
    def delete_single_record(cls, record_id, batch_no):
        """
        异步物理删除。
        """
        if not record_id or not batch_no:
            return False

        # 安全校验：必须限定在本工单 batch_no 下
        deleted_count, _ = LaborRecord.objects.filter(id=record_id, batch_no=batch_no).delete()
        return deleted_count > 0