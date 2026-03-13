# inventory/management/commands/init_inventory.py

from django.core.management.base import BaseCommand
from django.db import transaction
from inventory.models import Inventory, CostConfig
from core.constants.procedure_bom import PROCEDURE_BOM_MAPPING


# 导入路径严格遵循你的要求

class Command(BaseCommand):
    help = '基于 PROCEDURE_BOM_MAPPING 自动初始化库存与价格配置'

    def handle(self, *args, **options):
        self.stdout.write("开始扫描工艺 BOM 进行数据初始化...")

        # 1. 提取所有物料及其元数据 (去重)
        # 结构: { field_key: { 'name': display_name, 'is_cvn_input': bool } }
        material_registry = {}

        # 确定 CVN 合成的原料字段列表，用于后续 10000 库存的特殊处理
        cvn_inputs = [
            item['field'] for item in PROCEDURE_BOM_MAPPING.get('cvnsynthesis', {}).get('inputs', [])
        ]

        for proc_key, config in PROCEDURE_BOM_MAPPING.items():
            # 扫描 inputs 和 outputs
            for category in ['inputs', 'outputs']:
                for item in config.get(category, []):
                    field = item['field']
                    name = item['name']

                    if field not in material_registry:
                        material_registry[field] = {
                            'name': name,
                            'is_cvn_input': field in cvn_inputs
                        }

        # 2. 执行数据库操作 (原子事务)
        with transaction.atomic():
            created_count = 0
            updated_count = 0

            for field_key, info in material_registry.items():
                # --- A. 初始化库存 (Inventory) ---
                # 根据要求：cvn_syn 的原料设为 10000，其余为 0
                initial_qty = 10000 if info['is_cvn_input'] else 0

                inv_obj, inv_created = Inventory.objects.get_or_create(
                    key=field_key,
                    defaults={
                        'name': info['name'],
                        'quantity': initial_qty,
                        'unit': 'kg',  # 默认单位，后续可在后台修改
                        'category': 'raw' if info['is_cvn_input'] else 'inter'
                    }
                )

                # --- B. 初始化价格配置 (CostConfig) ---
                conf_obj, conf_created = CostConfig.objects.get_or_create(
                    key=field_key,
                    defaults={
                        'label': info['name'],
                        'price': 0,
                        'unit': 'kg',
                        'category': 'material'
                    }
                )

                if inv_created:
                    status = f"已创建 (初始库存: {initial_qty})"
                    created_count += 1
                else:
                    status = "已存在 (跳过创建)"
                    updated_count += 1

                self.stdout.write(f"  - [{field_key}] {info['name']}: {status}")

        self.stdout.write(self.style.SUCCESS(
            f"\n初始化完成！新增: {created_count}, 跳过: {updated_count}"
        ))