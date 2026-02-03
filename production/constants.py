# production/constants.py

# =========================================================
# 1. 物料 Keys (Material Keys) - 对应 Inventory & CostConfig
# =========================================================

# --- 原材料 (Raw Materials) ---
KEY_RAW_DCB = 'raw_dcb'       # 二氯丁烷
KEY_RAW_NACN = 'raw_nacn'     # 液体氰化钠
KEY_RAW_TBAB = 'raw_tbab'     # TBAB催化剂
KEY_RAW_ALKALI = 'raw_alkali' # 液碱
KEY_RAW_HCL = 'raw_hcl'       # 盐酸
KEY_RAW_SOCL2 = 'raw_socl2'   # 二氯亚砜

# --- 中间品 (Intermediates) ---
KEY_INTER_CVN_CRUDE = 'inter_cvn_crude'  # CVN粗品 (Step 1 产出)
KEY_INTER_CVN_PURE = 'inter_cvn_pure'    # CVN精品 (Step 2 产出)
KEY_INTER_CVA_CRUDE = 'inter_cva_crude'  # CVA粗品 (Step 3 产出)

# --- 成品/副产物 (Products & By-products) ---
KEY_PROD_CVC_NX = 'prod_cvc_nx'    # CVC合格品/内销 (Step 4 产出)
KEY_PROD_CVC_WX = 'prod_cvc_wx'    # CVC精品/外销 (Step 5 产出)
KEY_WASTE_HEAD = 'waste_head'      # 前馏份/回收液 (Step 4/5 副产出)
KEY_RECYCLED_DCB = 'recycled_dcb'  # 回收二氯丁烷

# =========================================================
# 2. 费用 Keys (Expense Keys) - 仅对应 CostConfig
# =========================================================

# --- 工资 (Wages - 按工段分组) ---
KEY_WAGE_GROUP_CVN = 'wage_group_cvn'   # CVN工段时薪
KEY_WAGE_GROUP_CVA = 'wage_group_cva'   # CVA工段时薪
KEY_WAGE_GROUP_CVC = 'wage_group_cvc'   # CVC工段时薪
KEY_WAGE_GENERAL = 'wage_general'       # 普工/杂工时薪

# --- 能源与环保 (Energy & Environment) ---
KEY_COST_WASTE_WATER = 'cost_waste_water'  # 污水处理费 (元/釜)
KEY_COST_ELECTRICITY = 'cost_electricity'  # 电费 (元/度)
KEY_COST_WATER = 'cost_water'              # 水费 (元/吨)