from django.db import transaction
from django.core.exceptions import ObjectDoesNotExist
from ..models.inventory import Inventory
from ..models.audit import InventoryLog


def handle_inventory_action(user, inventory_id, action_type, amount_or_quantity, note=""):
    """
    处理库存的核心业务逻辑 (三个按钮的幕后推手)

    :param user: 操作人 (request.user)
    :param inventory_id: 库存项 ID
    :param action_type: 'purchase'(购入), 'sale'(销售), 'correction'(盘点修正)
    :param amount_or_quantity:
           - 对于购入/销售: 代表变动量 (Change Amount)
           - 对于盘点: 代表盘点后的真实库存 (Real Quantity)
    :param note: 备注
    """
    try:
        # 2. 根据动作类型计算
        amount = float(amount_or_quantity)
        
        # 全局校验：数量不能为负数
        if amount < 0:
            return False, "数量不能为负数"

        with transaction.atomic():
            # 1. 锁定该行库存，防止并发修改 (select_for_update)
            inv = Inventory.objects.select_for_update().get(pk=inventory_id)

            old_quantity = inv.quantity
            change_amount = 0

            if action_type == 'purchase':
                # 购入：增加
                change_amount = amount
                inv.quantity += change_amount

            elif action_type == 'sale':
                # 销售校验：库存不足
                if inv.quantity < amount:
                    return False, "库存不足，无法扣减"

                # 销售：减少 (注意 amount 应该是正数，我们这里减去它)
                change_amount = -amount
                inv.quantity += change_amount

            elif action_type == 'correction':
                # 盘点：用户输入的是“现在的真实数量”，我们需要反推差值
                # 差值 = 真实值 - 账面值
                real_quantity = amount
                change_amount = real_quantity - old_quantity
                inv.quantity = real_quantity

            # 3. 保存库存
            inv.save()

            # 4. 写审计日志 (Audit)
            InventoryLog.objects.create(
                inventory=inv,
                action_type=action_type,
                change_amount=change_amount,
                quantity_after=inv.quantity,
                operator=user,
                note=note
            )

            return True, "操作成功"

    except ObjectDoesNotExist:
        return False, "找不到该物料"
    except ValueError:
        return False, "无效的数量格式"
    except Exception as e:
        return False, f"系统错误: {str(e)}"