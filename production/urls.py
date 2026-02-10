from django.urls import path
from production.views import KettleDashboardView, \
    CVNSynthesisCreateView, CVNSynthesisUpdateView, CVNSynthesisListView

app_name = 'production'

urlpatterns = [
    # === 看板 (Dashboard) ===
    path('dashboard/kettle/', KettleDashboardView.as_view(), name='kettle_dashboard'),

    # === CVN 合成 (CVN Synthesis) ===
    path('create/cvn-synthesis/', CVNSynthesisCreateView.as_view(), name='cvn_synthesis_create'),
    path('update/cvn-synthesis/<int:pk>/', CVNSynthesisUpdateView.as_view(), name='cvn_synthesis_update'),
    path('list/cvn-synthesis/', CVNSynthesisListView.as_view(), name='cvn_synthesis_list'),
]