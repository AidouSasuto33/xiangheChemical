# core/constants/process_bom.py

"""
全局工艺物料清单 (Process BOM) 与验证字典
这是整个系统的“数据大动脉”，所有的物料平衡、质检核对均基于此字典自动流转。
根据最新的统一字段规范，所有工艺的主产物均统一命名为 crude_weight。
"""

PROCEDURE_BOM_MAPPING = {
    # ==========================================
    # 1. CVN 合成
    # ==========================================
    'cvnsynthesis': {
        'name': 'CVN合成',
        'inputs': [
            {'field': 'raw_dcb',            'name': '二氯丁烷(新)'},
            {'field': 'input_recycled_dcb', 'name': '二氯丁烷(回)'},
            {'field': 'raw_nacn',           'name': '氰化钠'},
            {'field': 'raw_tbab',           'name': 'TBAB'},
            {'field': 'raw_alkali',         'name': '液碱'},
        ],
        'outputs': [
            {'field': 'crude_weight',       'name': 'CVN粗品'}
        ],
        'qc_fields': ['content_cvn', 'content_dcb', 'content_adn']
    },

    # ==========================================
    # 2. CVN 精馏
    # ==========================================
    'cvndistillation': {
        'name': 'CVN精馏',
        'inputs': [
            {'field': 'input_total_cvn_weight', 'name': 'CVN粗品(投入)'}
        ],
        'outputs': [
            {'field': 'crude_weight',       'name': 'CVN精品'},
            {'field': 'residue_weight',     'name': '釜残危废'}
        ],
        # 精馏特殊：有精前质检和精品质检
        'qc_fields': ['output_content_cvn', 'output_content_dcb', 'output_content_adn'],
        'qc_pre_fields': ['pre_content_cvn', 'pre_content_dcb', 'pre_content_adn']
    },

    # ==========================================
    # 3. CVA 合成及脱水
    # ==========================================
    'cvasynthesis': {
        'name': 'CVA合成',
        'inputs': [
            {'field': 'input_total_cvc_dis_weight', 'name': 'CVN精品(投入)'},
            {'field': 'raw_hcl',                    'name': '盐酸'},
            {'field': 'raw_alkali',                 'name': '液碱'},
        ],
        'outputs': [
            {'field': 'crude_weight',       'name': 'CVA粗品'}
        ],
        'qc_fields': ['content_cva', 'content_cvn', 'content_water']
    },

    # ==========================================
    # 4. CVC 合成 (内销)
    # ==========================================
    'cvcsynthesis': {
        'name': 'CVC合成',
        'inputs': [
            {'field': 'input_total_cva_weight', 'name': 'CVA粗品(投入)'},
            {'field': 'raw_socl2',              'name': '二氯亚砜'},
        ],
        'outputs': [
            {'field': 'crude_weight',             'name': 'CVC合格品'},
            {'field': 'distillation_head_weight', 'name': '前馏份'}
        ],
        'qc_fields': ['content_cvc', 'content_cva']
    },

    # ==========================================
    # 5. CVC 外销精制
    # ==========================================
    'cvcexport': {
        'name': 'CVC外销',
        'inputs': [
            {'field': 'input_total_cvc_weight', 'name': 'CVC合格品(投入)'}
        ],
        'outputs': [
            {'field': 'crude_weight',           'name': 'CVC精品'}
        ],
        'qc_fields': ['content_cvc', 'content_cva']
    }
}