import os
import re


def count_lines(file_path, ext):
    """
    计算单个文件的总行数与真实行数（去注释和空行）
    """
    total_lines = 0
    real_lines = 0

    # 针对不同语言的单行注释正则
    # js/css: // 或 /* */
    # py: #
    # html:
    comment_patterns = {
    '.js': r'(//.*)|(/\*.*?\*/)',
    '.css': r'/\*.*?\*/',
    '.py': r'#.*',
    '.html': r''
    }

    pattern = comment_patterns.get(ext, "")

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            # 移除最后一行后的纯空行（如果存在）
            while lines and not lines[-1].strip():
                lines.pop()

            total_lines = len(lines)

            for line in lines:
                clean_line = line.strip()
                # 1. 排除空行
                if not clean_line:
                    continue

                # 2. 排除纯注释行
                if pattern:
                    # 将匹配到的注释内容替换为空，看是否还有实质内容
                    line_no_comment = re.sub(pattern, '', clean_line).strip()
                    if not line_no_comment:
                        continue

                real_lines += 1
    except Exception as e:
        print(f"无法读取文件 {file_path}: {e}")

    return total_lines, real_lines


def main():
    target_exts = {'.js', '.css', '.html', '.py'}
    exclude_suffixes = {'.min.js', '.min.css'}

    stats = {ext: {'total': 0, 'real': 0} for ext in target_exts}

    root_dir = os.getcwd()

    for root, dirs, files in os.walk(root_dir):
        # 排除常见的隐藏文件夹或依赖文件夹
        if any(part.startswith('.') or part == 'node_modules' for part in root.split(os.sep)):
            continue

        for file in files:
            file_path = os.path.join(root, file)

            # 过滤逻辑
            if any(file.endswith(sfx) for sfx in exclude_suffixes):
                continue

            ext = os.path.splitext(file)[1]
            if ext in target_exts:
                t, r = count_lines(file_path, ext)
                stats[ext]['total'] += t
                stats[ext]['real'] += r

    # 打印结果
    print(f"{'后缀':<10} | {'总行数(含备注/空行)':<15} | {'真实代码行数':<15}")
    print("-" * 50)

    grand_total = 0
    grand_real = 0

    for ext in sorted(target_exts):
        t = stats[ext]['total']
        r = stats[ext]['real']
        grand_total += t
        grand_real += r
        print(f"{ext:<10} | {t:<18} | {r:<15}")

    print("-" * 50)
    print(f"{'合计':<10} | {grand_total:<18} | {grand_real:<15}")


if __name__ == "__main__":
    main()