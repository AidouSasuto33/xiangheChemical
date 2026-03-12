import random
from django.core.management.base import BaseCommand
from production.models import Kettle
from core.constants.kettle_status import *


class Command(BaseCommand):
    help = '生成虚拟釜皿数据以测试高密度看板'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='先清除所有现有釜皿数据',
        )

    def handle(self, *args, **options):
        # 1. 如果带了 --clear 参数，先清空表
        if options['clear']:
            count = Kettle.objects.count()
            Kettle.objects.all().delete()
            self.stdout.write(self.style.WARNING(f'已清除现有 {count} 条釜皿数据...'))

        # 2. 定义基础数据池
        workshops = ['一车间 (合成)', '二车间 (精馏)', '三车间 (高压)', '四车间 (溶剂)']
        capacities = [1000, 2000, 3000, 5000, 10000]
        processes = ['cvn_syn', 'cvn_dist', 'cva_syn', 'cvc_syn', 'cvc_dist']
        products = ['二氯丁烷', 'CVA粗品', 'CVC精品', '回收溶剂', '中间体A']

        total_created = 0

        # 3. 生成 120 个釜皿
        for i in range(1, 121):
            # 命名规则: 车间号-流水号 (如 1-05, 2-12)
            ws_index = (i % 4)
            ws_name = workshops[ws_index]
            k_name = f"{ws_index + 1}-{str(i).zfill(3)}"

            capacity = random.choice(capacities)

            # 随机状态权重 (生产中多一点，显得忙)
            rand_val = random.random()
            if rand_val < 0.5:
                status = KettleState.RUNNING
            elif rand_val < 0.7:
                status = KettleState.CLEANING
            elif rand_val < 0.95:
                status = KettleState.IDLE
            else:
                status = KettleState.MAINTENANCE

            # 根据状态设置液位和批次
            current_level = 0
            current_batch = ""
            last_process = ""
            last_product = ""

            if status == KettleState.RUNNING:
                # 生产中：液位随机 20% ~ 95%
                current_level = capacity * random.uniform(0.2, 0.95)
                current_batch = f"BATCH-20260203-{random.randint(100, 999)}"
                # 既然在生产，也要有“上一批”记录
                last_process = random.choice(processes)
                last_product = random.choice(products)

            elif status == KettleState.CLEANING:
                # 待清洁：可能有少量残留，或者空
                current_level = 0
                last_process = random.choice(processes)
                last_product = random.choice(products)

            elif status == KettleState.IDLE:
                # 空闲：一定是空的，但有上批记录
                current_level = 0
                last_process = random.choice(processes)
                last_product = random.choice(products)

            # 支持的工艺 (随机选 1-3 个)
            supported = random.sample(processes, k=random.randint(1, 3))

            # 创建对象
            Kettle.objects.create(
                name=k_name,
                workshop=ws_name,
                capacity=capacity,
                supported_processes=supported,
                status=status,
                current_level=current_level,
                current_batch_no=current_batch,
                last_process=last_process,
                last_product_name=last_product
            )
            total_created += 1

        self.stdout.write(self.style.SUCCESS(f'成功生成 {total_created} 个虚拟釜皿！'))