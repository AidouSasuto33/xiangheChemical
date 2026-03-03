from django.urls import path

from production.views import \
    KettleDashboardView, \
    CVNSynthesisCreateView, CVNSynthesisUpdateView, CVNSynthesisListView, \
    CVNDistillationListView, CVNDistillationCreateView, CVNDistillationUpdateView

app_name = 'production'

urlpatterns = [
    # === 看板 (Dashboard) ===
    path('dashboard/kettle/', KettleDashboardView.as_view(), name='kettle_dashboard'),

    # === CVN 合成 (CVN Synthesis) ===
    path('create/cvn-synthesis/', CVNSynthesisCreateView.as_view(), name='cvn_synthesis_create'),
    path('update/cvn-synthesis/<int:pk>/', CVNSynthesisUpdateView.as_view(), name='cvn_synthesis_update'),
    path('list/cvn-synthesis/', CVNSynthesisListView.as_view(), name='cvn_synthesis_list'),

    # === CVN 精馏 (CVN Distillation) ===
    path('create/cvn-distillation/', CVNDistillationCreateView.as_view(), name='cvn_distillation_create'),
    path('update/cvn-synthesis/<int:pk>/', CVNDistillationUpdateView.as_view(), name='cvn_synthesis_update'),
    path('list/cvn-distillation/', CVNDistillationListView.as_view(), name='cvn_distillation_list'),
]