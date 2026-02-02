# Django基础ORM管理
from django.db import models
# 引入 Postgres 特有的 ArrayField (虽然 JSONField 更通用，但这里用 JSON 兼容性更好)
from django.db.models import JSONField
# django用户管理库
from django.contrib.auth.models import User
# 批号生成器
from .utils.batch_generator import generate_batch_number
# Django事务管理
from django.db import transaction
# Django异常处理
from django.core.exceptions import ValidationError
