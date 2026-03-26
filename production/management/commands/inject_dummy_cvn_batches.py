import random
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from production.models.cvn_synthesis import CVNSynthesis


class Command(BaseCommand):
    help = '为 xiangheChemical 演示生成 10 万条 CVN 模拟数据 (修正字段名版)'

    def handle(self, *args, **options):
        total_records = 100000
        start_date = datetime(2010, 1, 1)
        end_date = datetime(2026, 3, 26)
        delta_days = (end_date - start_date).days

        self.stdout.write(self.style.SUCCESS(f"东来，正在使用正确的字段名注入 {total_records} 条数据..."))

        batches = []
        records_count = 0
        current_date = start_date
        avg_batches_per_day = total_records // delta_days

        while records_count < total_records and current_date <= end_date:
            daily_limit = random.randint(
                int(avg_batches_per_day * 0.5),
                int(avg_batches_per_day * 1.5)
            )

            for i in range(daily_limit):
                if records_count >= total_records:
                    break

                # 模拟一天内的随机时间点
                random_hour = random.randint(0, 18)
                random_minute = random.randint(0, 59)
                base_time = current_date + timedelta(hours=random_hour, minutes=random_minute)
                aware_time = timezone.make_aware(base_time)

                # 生成批次对象
                batch = CVNSynthesis(
                    # 修正后的字段名
                    kettle_id=random.randint(1, 120),
                    workshop_id=1,
                    operator_id=1,  # 假设 ID 为 1 的用户存在
                    status='completed',

                    # 核心时间字段
                    created_at=aware_time,  # 对应 BaseProductionStep.created_at
                    start_time=aware_time,  # 对应 BaseProductionStep.start_time
                    end_time=aware_time + timedelta(hours=random.randint(4, 8)),
                    test_time=aware_time + timedelta(hours=random.randint(2, 4)),

                    # 业务数据
                    raw_dcb=random.uniform(600, 900),
                    recycled_dcb=random.uniform(150, 250),
                    raw_nacn=random.uniform(250, 350),
                    raw_tbab=random.uniform(8, 12),
                    raw_alkali=random.uniform(80, 120),
                    cvn_syn_crude_weight=random.uniform(900, 1100),
                    consumed_weight=0,

                    content_cvn=random.uniform(88.0, 95.0),
                    content_dcb=random.uniform(2.0, 4.0),
                    content_adn=random.uniform(0.5, 1.5),

                    recovered_dcb_amount=random.uniform(60, 90),
                    recovered_dcb_purity=random.uniform(92, 98),
                    waste_batches=random.randint(1, 2),

                    # 乐观锁版本号
                    version=1
                )

                # 构造批次号
                batch.batch_no = f"{current_date.strftime('%Y%m%d')}-{batch.kettle_id:03d}-{i:02d}"

                batches.append(batch)
                records_count += 1

            if len(batches) >= 5000:
                # bulk_create 可以写入带有 auto_now_add=True 的字段值
                CVNSynthesis.objects.bulk_create(batches)
                batches = []
                self.stdout.write(f"已处理 {records_count} 条...")

            current_date += timedelta(days=1)

        if batches:
            CVNSynthesis.objects.bulk_create(batches)

        self.stdout.write(self.style.SUCCESS(f"注入完成！10万条带『历史印记』的数据已就绪。"))