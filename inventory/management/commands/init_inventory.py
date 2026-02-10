from django.core.management.base import BaseCommand
from inventory.models import Inventory
from inventory.models import CostConfig
from production import constants as k  # 引入我们刚才写的常量文件


class Command(BaseCommand):
    help = '初始化系统基础数据：Inventory(数量0) 与 CostConfig(基础价格)'

    def handle(self, *args, **options):
        # 定义初始化清单
        # type: 'material' #会同时创建库存和价格配置
        # type: 'expense' #只创建价格配置

        INIT_DATA = [
            # --- 原材料 ---
            {'key': k.KEY_RAW_DCB, 'name': '二氯丁烷', 'type': 'material', 'unit': 'kg', 'safe_stock': 1000},
            {'key': k.KEY_RECYCLED_DCB,'name': '回收二氯丁烷','type': 'material','unit': 'L'},  # 模型中定义的是 L，这里保持一致'cat': 'raw'  # 分类归为原料，因为后续会再次投入使用},
            {'key': k.KEY_RAW_NACN, 'name': '液体氰化钠', 'type': 'material', 'unit': 'kg', 'safe_stock': 500},
            {'key': k.KEY_RAW_TBAB, 'name': 'TBAB催化剂', 'type': 'material', 'unit': 'kg', 'safe_stock': 100},
            {'key': k.KEY_RAW_ALKALI, 'name': '液碱', 'type': 'material', 'unit': 'kg', 'safe_stock': 2000},
            {'key': k.KEY_RAW_HCL, 'name': '盐酸', 'type': 'material', 'unit': 'kg', 'safe_stock': 1000},
            {'key': k.KEY_RAW_SOCL2, 'name': '二氯亚砜', 'type': 'material', 'unit': 'kg', 'safe_stock': 1000},

            # --- 中间品 ---
            {'key': k.KEY_INTER_CVN_CRUDE, 'name': 'CVN粗品', 'type': 'material', 'unit': 'kg'},
            {'key': k.KEY_INTER_CVN_PURE, 'name': 'CVN精品', 'type': 'material', 'unit': 'kg'},
            {'key': k.KEY_INTER_CVA_CRUDE, 'name': 'CVA粗品', 'type': 'material', 'unit': 'kg'},

            # --- 成品 ---
            {'key': k.KEY_PROD_CVC_NX, 'name': 'CVC合格品(内销)', 'type': 'material', 'unit': 'kg', 'cat': 'product'},
            {'key': k.KEY_PROD_CVC_WX, 'name': 'CVC精品(外销)', 'type': 'material', 'unit': 'kg', 'cat': 'product'},
            {'key': k.KEY_WASTE_HEAD, 'name': '前馏份/回收液', 'type': 'material', 'unit': 'kg', 'cat': 'intermediate'},

            # --- 费用配置 (只进 CostConfig) ---
            {'key': k.KEY_WAGE_GROUP_CVN, 'name': 'CVN组时薪', 'type': 'expense', 'unit': 'person_time',
             'cat': 'labor'},
            {'key': k.KEY_WAGE_GROUP_CVA, 'name': 'CVA组时薪', 'type': 'expense', 'unit': 'person_time',
             'cat': 'labor'},
            {'key': k.KEY_WAGE_GROUP_CVC, 'name': 'CVC组时薪', 'type': 'expense', 'unit': 'person_time',
             'cat': 'labor'},
            {'key': k.KEY_WAGE_GENERAL, 'name': '普工时薪', 'type': 'expense', 'unit': 'person_time', 'cat': 'labor'},
            {'key': k.KEY_COST_WASTE_WATER, 'name': '污水处理费', 'type': 'expense', 'unit': 'batch', 'cat': 'waste'},
        ]

        self.stdout.write("开始初始化系统数据...")

        for item in INIT_DATA:
            # 1. 处理库存 (Inventory)
            if item['type'] == 'material':
                # 使用 get_or_create 确保只在第一次创建时 quantity 为 0
                # 这样如果脚本重复运行，不会把已经修正好的库存清零
                inv_obj, inv_created = Inventory.objects.get_or_create(
                    key=item['key'],
                    defaults={
                        'name': item['name'],
                        'category': item.get('cat', 'raw'),  # 默认为 raw，除非指定
                        'unit': item['unit'],
                        'quantity': 0,  # 【关键】初始库存设为 0
                        'safe_stock': item.get('safe_stock', 0)
                    }
                )
                if inv_created:
                    self.stdout.write(f"  [库存] 创建: {item['name']}")
                else:
                    # 如果需要更新名称等元数据，可以在这里写逻辑，但暂不更新 quantity
                    pass

            # 2. 处理价格配置 (CostConfig)
            # 无论 material 还是 expense 都有价格
            config_cat = item.get('cat', 'material')
            if item['type'] == 'material' and 'cat' not in item:
                config_cat = 'material'

            conf_obj, conf_created = CostConfig.objects.get_or_create(
                key=item['key'],
                defaults={
                    'label': item['name'],
                    'category': config_cat,
                    'unit': item['unit'],
                    'price': 0  # 初始价格设为 0，等待财务录入
                }
            )
            if conf_created:
                self.stdout.write(f"  [配置] 创建: {item['name']}")

        self.stdout.write(self.style.SUCCESS("初始化完成！所有库存已归零，请通知文员进行盘点修正。"))