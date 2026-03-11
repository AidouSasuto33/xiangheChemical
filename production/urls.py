from django.urls import path
from django_ratelimit.decorators import ratelimit

from production.views import \
    KettleDashboardView, \
    CVNSynthesisCreateView, CVNSynthesisUpdateView, CVNSynthesisListView, \
    CVNDistillationListView, CVNDistillationCreateView, CVNDistillationUpdateView
from .views.partial.attachment_view import ProductionAttachmentUploadView

app_name = 'production'

# 定义生产开单限流器：防恶意刷单和重复提交，限制单个用户每分钟只能提交 3 次 POST 请求
strict_limit = ratelimit(key='user', rate='60/m', method='POST', block=True)
# 定义一个防刷接口的限流器（例如每分钟最多上传 20 张图）
upload_limit = ratelimit(key='user', rate='20/m', method='POST', block=True)

urlpatterns = [
    # === 看板 (Dashboard) ===
    # 看板以查阅为主，不限制
    path('dashboard/kettle/', KettleDashboardView.as_view(), name='kettle_dashboard'),

    # === CVN 合成 (CVN Synthesis) ===
    # 🔐 核心防线：对新建和更新操作加装限流器
    path('create/cvn-synthesis/', strict_limit(CVNSynthesisCreateView.as_view()), name='cvn_synthesis_create'),
    path('update/cvn-synthesis/<int:pk>/', strict_limit(CVNSynthesisUpdateView.as_view()), name='cvn_synthesis_update'),
    path('list/cvn-synthesis/', CVNSynthesisListView.as_view(), name='cvn_synthesis_list'),

    # === CVN 精馏 (CVN Distillation) ===
    # 🔐 核心防线：对新建和更新操作加装限流器
    path('create/cvn-distillation/', strict_limit(CVNDistillationCreateView.as_view()), name='cvn_distillation_create'),
    path('update/cvn-distillation/<int:pk>/', strict_limit(CVNDistillationUpdateView.as_view()), name='cvn_distillation_update'),
    path('list/cvn-distillation/', CVNDistillationListView.as_view(), name='cvn_distillation_list'),

    # === 通用 API 接口 ===
    # 🔐 附件上传接口，加装上传频率限制
    path('attachment/upload/',upload_limit(ProductionAttachmentUploadView.as_view()),name='upload_attachment'),
]