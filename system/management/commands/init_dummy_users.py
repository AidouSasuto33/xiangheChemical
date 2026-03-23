# system/management/commands/init_dummy_users.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from system.models.accounts import Department, Workshop, Employee
from django.db import transaction


class Command(BaseCommand):
    help = '初始化车间、部门及预设生产人员数据 (支持 Employee 扩展模型)'

    def handle(self, *args, **options):
        # 预设的哈希密码 (pbkdf2_sha256)
        hashed_password = "pbkdf2_sha256$1200000$DO8obDCKX2TZtc4POH8IXx$L7cyCVa5eIJEzJNEWAKkSH7caQcFRTc4kM6fdPixaVQ="

        # 1. 详细的车间配置信息
        workshop_configs = [
            {"name": "CVN粗蒸车间", "code": "CVN_SYN", "desc": "负责 CVN 粗产品的初步蒸馏与杂质去除"},
            {"name": "CVN精馏车间", "code": "CVN_DIS", "desc": "负责 CVN 精品的高纯度精馏，产出合格精品"},
            {"name": "CVA合成车间", "code": "CVA_SYN", "desc": "负责 CVA 中间体的合成反应与工艺控制"},
            {"name": "CVC粗蒸车间", "code": "CVC_SYN", "desc": "负责 CVC 粗制品的减压蒸馏处理"},
            {"name": "CVC精馏车间", "code": "CVC_DIS", "desc": "负责 CVC 外销品精馏处理"},
        ]

        # 2. 用户配置信息
        user_configs = [
            {"first_name": "殷总", "username": "yinzong", "is_admin": False, "emp_id": "2"},
            {"first_name": "董总", "username": "dongzong", "is_admin": False, "emp_id": "3"},
            {"first_name": "军主任", "username": "junzhuren", "is_admin": False, "emp_id": "4"},
            {"first_name": "张三", "username": "zhangsan", "is_admin": False, "emp_id": "5"},
            {"first_name": "东来", "username": "wxxxx", "is_admin": True, "emp_id": "1"},  # 超级管理员
        ]

        try:
            with transaction.atomic():

                # A. 创建车间
                workshops = []
                for cfg in workshop_configs:
                    ws = Workshop.objects.create(
                        name=cfg['name'],
                        code=cfg['code'],
                        description=cfg['desc']
                    )
                    workshops.append(ws)
                self.stdout.write(f"已创建 {len(workshops)} 个车间。")

                # B. 创建部门
                dept_prod = Department.objects.create(name="生产部门")
                self.stdout.write("已创建部门：生产部门。")

                # C. 创建用户与员工档案
                for cfg in user_configs:
                    # 1. 创建原生 User
                    new_user = User.objects.create(
                        username=cfg['username'],
                        first_name=cfg['first_name'],
                        email="123@123.com",
                        is_staff=cfg['is_admin'],
                        is_superuser=cfg['is_admin']
                    )
                    # 注入密码
                    new_user.password = hashed_password
                    new_user.save()

                    # 2. 创建关联的 Employee 档案
                    employee = Employee.objects.create(
                        user=new_user,
                        employee_id=cfg['emp_id'],
                        department=dept_prod,
                        position="高级管理" if cfg['is_admin'] else "生产管理"
                    )

                    # 3. 注入管辖车间 (所有人都管辖所有车间)
                    employee.workshops.set(workshops)

                    admin_tag = " (SuperUser)" if cfg['is_admin'] else ""
                    self.stdout.write(f"成功注入: {cfg['first_name']} | 档案号: {cfg['emp_id']}{admin_tag}")

                self.stdout.write(self.style.SUCCESS("\n所有用户数据注入成功。"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"初始化失败: {str(e)}"))