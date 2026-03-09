from django.db import models
from django.contrib.auth.models import User


class Department(models.Model):
    """
    部门模型：用于行政隶属关系（如：生产部、财务部、人事部）
    """
    name = models.CharField(max_length=100, verbose_name="部门名称")
    parent = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='children',
        verbose_name="上级部门"
    )

    class Meta:
        verbose_name = "部门"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


class Workshop(models.Model):
    """
    车间/工段模型：用于业务管辖关系（如：合成车间、精馏车间）
    """
    name = models.CharField(max_length=100, unique=True, verbose_name="车间名称")
    code = models.CharField(max_length=50, unique=True, verbose_name="车间编码")
    description = models.TextField(blank=True, verbose_name="描述")

    class Meta:
        verbose_name = "车间"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


class Employee(models.Model):
    """
    员工档案：对原生 User 模型的扩展
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='employee',
        verbose_name="关联用户"
    )
    employee_id = models.CharField(max_length=50, unique=True, verbose_name="工号")
    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name='employees',
        verbose_name="所属部门"
    )

    # 实现“1对多”车间管辖的核心字段
    workshops = models.ManyToManyField(
        Workshop,
        blank=True,
        related_name='staff',
        verbose_name="管辖车间"
    )

    phone = models.CharField(max_length=20, blank=True, verbose_name="联系电话")
    position = models.CharField(max_length=100, blank=True, verbose_name="职位")

    class Meta:
        verbose_name = "员工档案"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.user.last_name}{self.user.first_name} ({self.department.name})"