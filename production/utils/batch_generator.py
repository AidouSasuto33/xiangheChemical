import datetime

def generate_batch_number(model_class, prefix):
    """
    通用批号生成器
    格式：PREFIX-YYYYMMDD-NN (如 CVN-CU-20260201-01)

    Args:
        model_class: 具体的模型类（用于查库寻找最大的流水号）
        prefix: 批号前缀（如 'CVN-CU', 'CVN-JING'）

    Returns:
        str: 新生成的批号
    """
    today_str = datetime.date.today().strftime('%Y%m%d')
    full_prefix = f"{prefix}-{today_str}"

    # 查找当天最大的流水号
    # 注意：这里假设所有模型都有 batch_no 这个字段
    last_record = model_class.objects.filter(batch_no__startswith=full_prefix).order_by('batch_no').last()

    if last_record:
        try:
            # 取最后两位数字，加 1
            last_seq = int(last_record.batch_no.split('-')[-1])
            new_seq = last_seq + 1
        except ValueError:
            new_seq = 1
    else:
        new_seq = 1

    return f"{full_prefix}-{new_seq:02d}"