from production.models import CVNSynthesis, CVNDistillation, CVASynthesis, CVCSynthesis, CVCExport
from inventory.models import Inventory, CostConfig

# 后端注册表：将前端的业务 key 映射到真实的 Model 和基础过滤条件
DATASET_REGISTRY = {
    'cvn_production': {
        'model': CVNSynthesis,
        'base_filters': {'status': 'completed'},
        'time_field': 'created_at'
    },
    'cva_quality': {
        'model': CVASynthesis,
        'base_filters': {'process_type': 'cvasynthesis'},
        'time_field': 'created_at'
    },
    # 未来加新业务，只需在这里加一行配置，无需改动任何核心代码
}