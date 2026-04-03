# production/urls.py
from django.urls import path
from django_ratelimit.decorators import ratelimit

from production.views import \
    KettleDashboardView, \
    CVNSynthesisCreateView, CVNSynthesisUpdateView, CVNSynthesisListView, \
    CVNDistillationCreateView, CVNDistillationUpdateView, CVNDistillationListView, \
    CVASynthesisCreateView, CVASynthesisUpdateView, CVASynthesisListView, \
    CVCSynthesisCreateView, CVCSynthesisUpdateView, CVCSynthesisListView, \
    CVCExportCreateView, CVCExportUpdateView, CVCExportListView, ChartAPIView
from .views.partial.attachment_view import AttachmentUploadView, AttachmentManageView
from .views.partial.labor_record_view import LaborUpdateView, LaborDeleteView # 假设你将异步视图放在这里

app_name = 'production'

# 定义生产开单限流器：防恶意刷单和重复提交，限制单个用户每分钟只能提交 3 次 POST 请求
strict_limit = ratelimit(key='user', rate='60/m', method='POST', block=True)
# 定义一个防刷接口的限流器（例如每分钟最多上传 20 张图）
upload_limit = ratelimit(key='user', rate='20/m', method='POST', block=True)

urlpatterns = [
    # === 看板 (Dashboard) ===
    # 看板以查阅为主，不限制
    path('dashboard/kettle/', KettleDashboardView.as_view(), name='kettle_dashboard'),

    # === 1. CVN 合成 (CVN Synthesis) ===
    # 🔐 核心防线：对新建和更新操作加装限流器
    path('create/cvn-synthesis/', strict_limit(CVNSynthesisCreateView.as_view()), name='cvn_synthesis_create'),
    path('update/cvn-synthesis/<int:pk>/', strict_limit(CVNSynthesisUpdateView.as_view()), name='cvn_synthesis_update'),
    path('list/cvn-synthesis/', CVNSynthesisListView.as_view(), name='cvn_synthesis_list'),

    # === 2. CVN 精馏 (CVN Distillation) ===
    path('create/cvn-distillation/', strict_limit(CVNDistillationCreateView.as_view()), name='cvn_distillation_create'),
    path('update/cvn-distillation/<int:pk>/', strict_limit(CVNDistillationUpdateView.as_view()), name='cvn_distillation_update'),
    path('list/cvn-distillation/', CVNDistillationListView.as_view(), name='cvn_distillation_list'),

    # === 3. CVA 合成 (CVA Synthesis) ===
    path('create/cva-synthesis/', strict_limit(CVASynthesisCreateView.as_view()), name='cva_synthesis_create'),
    path('update/cva-synthesis/<int:pk>/', strict_limit(CVASynthesisUpdateView.as_view()), name='cva_synthesis_update'),
    path('list/cva-synthesis/', CVASynthesisListView.as_view(), name='cva_synthesis_list'),

    # === 4. CVC 合成内销 (CVC Synthesis) ===
    path('create/cvc-synthesis/', strict_limit(CVCSynthesisCreateView.as_view()), name='cvc_synthesis_create'),
    path('update/cvc-synthesis/<int:pk>/', strict_limit(CVCSynthesisUpdateView.as_view()), name='cvc_synthesis_update'),
    path('list/cvc-synthesis/', CVCSynthesisListView.as_view(), name='cvc_synthesis_list'),

    # === 5. CVC 外销精制 (CVC Export) ===
    path('create/cvc-export/', strict_limit(CVCExportCreateView.as_view()), name='cvc_export_create'),
    path('update/cvc-export/<int:pk>/', strict_limit(CVCExportUpdateView.as_view()), name='cvc_export_update'),
    path('list/cvc-export/', CVCExportListView.as_view(), name='cvc_export_list'),


    # === 通用 API 接口 ===
    # 🔐 附件上传接口，加装上传频率限制
    path('attachment/upload/', upload_limit(AttachmentUploadView.as_view()), name='upload_attachment'),
    path('attachment/manage/', AttachmentManageView.as_view(), name='manage_attachment'), # 查看附件路径

    # 人工投入组件的异步接口 - 单条修改与删除
    path('labor-record/single-async/', LaborUpdateView.as_view(), name='labor_sync_async'),
    path('labor-record/delete-async/', LaborDeleteView.as_view(), name='labor_delete_async'),

    # === 图表接口 ===
    path('charts/', ChartAPIView.as_view(), name='charts'),
]