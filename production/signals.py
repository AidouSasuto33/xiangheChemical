from django.dispatch import Signal

"""
工单状态变更信号
发送此信号时，期望传递以下参数（kwargs）：
- instance: 发生变更的工单实例（如 CVNSynthesis 的具体对象）
- old_status: 变更前的状态代码
- new_status: 变更后的状态代码
- user: 触发此变更的操作人（User 实例）
"""
post_procedure_state_change = Signal()