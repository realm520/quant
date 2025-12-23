#!/usr/bin/env python3
"""
验证 CSV 文件中盈亏计算的正确性
"""

import csv
from decimal import Decimal


def verify_row(row_data):
    """验证单行数据的计算是否正确"""
    # 解析数据
    open_left_long_qty = Decimal(row_data['open_left_long_qty'])
    open_left_short_qty = Decimal(row_data['open_left_short_qty'])
    open_left_long_value = Decimal(row_data['open_left_long_value'])
    open_left_short_value = Decimal(row_data['open_left_short_value'])
    
    daily_sum_buy_qty = Decimal(row_data['daily_sum_buy_qty'])
    daily_sum_sell_qty = Decimal(row_data['daily_sum_sell_qty'])
    daily_sum_buy_value = Decimal(row_data['daily_sum_buy_value'])
    daily_sum_sell_value = Decimal(row_data['daily_sum_sell_value'])
    
    long_qty = Decimal(row_data['long_qty'])
    short_qty = Decimal(row_data['short_qty'])
    long_value = Decimal(row_data['long_value'])
    short_value = Decimal(row_data['short_value'])
    
    avg_buy_prz = Decimal(row_data['avg_buy_prz'])
    avg_sell_prz = Decimal(row_data['avg_sell_prz'])
    matched_qty = Decimal(row_data['matched_qty'])
    
    daily_realized_pnl = Decimal(row_data['daily_realized_pnl'])
    cumulative_realized_pnl = Decimal(row_data['cumulative_realized_pnl'])
    
    left_long_qty = Decimal(row_data['left_long_qty'])
    left_short_qty = Decimal(row_data['left_short_qty'])
    left_long_value = Decimal(row_data['left_long_value'])
    left_short_value = Decimal(row_data['left_short_value'])
    
    close_prz = Decimal(row_data['close_prz'])
    unrealized_pnl = Decimal(row_data['unrealized_pnl'])
    daily_pnl = Decimal(row_data['daily_pnl'])
    cumulative_pnl = Decimal(row_data['cumulative_pnl'])
    
    timestamp = row_data['timestamp']
    symbol = row_data['symbol']
    
    print(f"\n验证 {symbol} - {timestamp}")
    print("=" * 80)
    
    errors = []
    warnings = []
    
    # 1. 验证 avg_buy_prz = long_value / long_qty
    if long_qty > 0:
        expected_avg_buy_prz = long_value / long_qty
        diff = abs(expected_avg_buy_prz - avg_buy_prz)
        if diff > Decimal("0.00000001"):
            errors.append(f"avg_buy_prz 计算错误: 期望 {expected_avg_buy_prz:.10f}, 实际 {avg_buy_prz:.10f}, 差异 {diff:.10f}")
        else:
            print(f"✓ avg_buy_prz = {avg_buy_prz:.10f} (long_value / long_qty = {long_value} / {long_qty})")
    else:
        if avg_buy_prz != 0:
            errors.append(f"avg_buy_prz 应该为 0，但实际为 {avg_buy_prz}")
    
    # 2. 验证 avg_sell_prz = short_value / short_qty
    if short_qty > 0:
        expected_avg_sell_prz = short_value / short_qty
        diff = abs(expected_avg_sell_prz - avg_sell_prz)
        if diff > Decimal("0.00000001"):
            errors.append(f"avg_sell_prz 计算错误: 期望 {expected_avg_sell_prz:.10f}, 实际 {avg_sell_prz:.10f}, 差异 {diff:.10f}")
        else:
            print(f"✓ avg_sell_prz = {avg_sell_prz:.10f} (short_value / short_qty = {short_value} / {short_qty})")
    else:
        if avg_sell_prz != 0:
            errors.append(f"avg_sell_prz 应该为 0，但实际为 {avg_sell_prz}")
    
    # 3. 验证 matched_qty = min(long_qty, short_qty)
    expected_matched_qty = min(long_qty, short_qty)
    if matched_qty != expected_matched_qty:
        errors.append(f"matched_qty 计算错误: 期望 {expected_matched_qty}, 实际 {matched_qty}")
    else:
        print(f"✓ matched_qty = {matched_qty} (min({long_qty}, {short_qty}))")
    
    # 4. 验证 daily_realized_pnl = matched_qty * (avg_sell_prz - avg_buy_prz)
    if matched_qty > 0 and avg_sell_prz > 0 and avg_buy_prz > 0:
        expected_daily_realized_pnl = matched_qty * (avg_sell_prz - avg_buy_prz)
        diff = abs(expected_daily_realized_pnl - daily_realized_pnl)
        if diff > Decimal("0.0001"):
            errors.append(f"daily_realized_pnl 计算错误: 期望 {expected_daily_realized_pnl:.10f}, 实际 {daily_realized_pnl:.10f}, 差异 {diff:.10f}")
        else:
            print(f"✓ daily_realized_pnl = {daily_realized_pnl:.10f} (matched_qty * (avg_sell_prz - avg_buy_prz) = {matched_qty} * ({avg_sell_prz} - {avg_buy_prz}))")
    
    # 5. 验证 left_long_qty = long_qty - matched_qty
    expected_left_long_qty = long_qty - matched_qty
    if abs(left_long_qty - expected_left_long_qty) > Decimal("0.0001"):
        errors.append(f"left_long_qty 计算错误: 期望 {expected_left_long_qty}, 实际 {left_long_qty}")
    else:
        print(f"✓ left_long_qty = {left_long_qty} (long_qty - matched_qty = {long_qty} - {matched_qty})")
    
    # 6. 验证 left_short_qty = short_qty - matched_qty
    expected_left_short_qty = short_qty - matched_qty
    if abs(left_short_qty - expected_left_short_qty) > Decimal("0.0001"):
        errors.append(f"left_short_qty 计算错误: 期望 {expected_left_short_qty}, 实际 {left_short_qty}")
    else:
        print(f"✓ left_short_qty = {left_short_qty} (short_qty - matched_qty = {short_qty} - {matched_qty})")
    
    # 7. 验证 left_long_value = left_long_qty * avg_buy_prz
    if left_long_qty > 0:
        expected_left_long_value = left_long_qty * avg_buy_prz
        diff = abs(expected_left_long_value - left_long_value)
        if diff > Decimal("0.0001"):
            errors.append(f"left_long_value 计算错误: 期望 {expected_left_long_value:.10f}, 实际 {left_long_value:.10f}, 差异 {diff:.10f}")
        else:
            print(f"✓ left_long_value = {left_long_value:.10f} (left_long_qty * avg_buy_prz = {left_long_qty} * {avg_buy_prz})")
    else:
        if left_long_value != 0:
            warnings.append(f"left_long_value 应该为 0，但实际为 {left_long_value}")
    
    # 8. 验证 left_short_value = left_short_qty * avg_sell_prz
    if left_short_qty > 0:
        expected_left_short_value = left_short_qty * avg_sell_prz
        diff = abs(expected_left_short_value - left_short_value)
        if diff > Decimal("0.0001"):
            errors.append(f"left_short_value 计算错误: 期望 {expected_left_short_value:.10f}, 实际 {left_short_value:.10f}, 差异 {diff:.10f}")
        else:
            print(f"✓ left_short_value = {left_short_value:.10f} (left_short_qty * avg_sell_prz = {left_short_qty} * {avg_sell_prz})")
    else:
        if left_short_value != 0:
            warnings.append(f"left_short_value 应该为 0，但实际为 {left_short_value}")
    
    # 9. 验证 unrealized_pnl = left_long_qty * (close_prz - avg_buy_prz) + left_short_qty * (avg_sell_prz - close_prz)
    if close_prz > 0:
        expected_unrealized_pnl = (
            left_long_qty * (close_prz - avg_buy_prz) +
            left_short_qty * (avg_sell_prz - close_prz)
        )
        diff = abs(expected_unrealized_pnl - unrealized_pnl)
        if diff > Decimal("0.0001"):
            errors.append(f"unrealized_pnl 计算错误: 期望 {expected_unrealized_pnl:.10f}, 实际 {unrealized_pnl:.10f}, 差异 {diff:.10f}")
            print(f"详细计算:")
            print(f"  left_long_qty * (close_prz - avg_buy_prz) = {left_long_qty} * ({close_prz} - {avg_buy_prz}) = {left_long_qty * (close_prz - avg_buy_prz):.10f}")
            print(f"  left_short_qty * (avg_sell_prz - close_prz) = {left_short_qty} * ({avg_sell_prz} - {close_prz}) = {left_short_qty * (avg_sell_prz - close_prz):.10f}")
            print(f"  总和 = {expected_unrealized_pnl:.10f}")
        else:
            print(f"✓ unrealized_pnl = {unrealized_pnl:.10f}")
    
    # 10. 验证 daily_pnl = daily_realized_pnl + unrealized_pnl
    expected_daily_pnl = daily_realized_pnl + unrealized_pnl
    diff = abs(expected_daily_pnl - daily_pnl)
    if diff > Decimal("0.0001"):
        errors.append(f"daily_pnl 计算错误: 期望 {expected_daily_pnl:.10f}, 实际 {daily_pnl:.10f}, 差异 {diff:.10f}")
    else:
        print(f"✓ daily_pnl = {daily_pnl:.10f} (daily_realized_pnl + unrealized_pnl = {daily_realized_pnl} + {unrealized_pnl})")
    
    # 11. 验证 cumulative_pnl = cumulative_realized_pnl + unrealized_pnl
    expected_cumulative_pnl = cumulative_realized_pnl + unrealized_pnl
    diff = abs(expected_cumulative_pnl - cumulative_pnl)
    if diff > Decimal("0.0001"):
        errors.append(f"cumulative_pnl 计算错误: 期望 {expected_cumulative_pnl:.10f}, 实际 {cumulative_pnl:.10f}, 差异 {diff:.10f}")
    else:
        print(f"✓ cumulative_pnl = {cumulative_pnl:.10f} (cumulative_realized_pnl + unrealized_pnl = {cumulative_realized_pnl} + {unrealized_pnl})")
    
    # 显示结果
    if errors:
        print(f"\n发现 {len(errors)} 个错误:")
        for error in errors:
            print(f"  ✗ {error}")
    
    if warnings:
        print(f"\n发现 {len(warnings)} 个警告:")
        for warning in warnings:
            print(f"  ⚠ {warning}")
    
    if not errors and not warnings:
        print(f"\n✓ 所有计算都正确！")
    
    return len(errors) == 0


def main():
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python3 verify_pnl_calculation.py <csv_file>")
        return
    
    csv_file = sys.argv[1]
    
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    print(f"读取了 {len(rows)} 行数据")
    
    all_correct = True
    for i, row in enumerate(rows, 1):
        if not row.get('timestamp'):  # 跳过空行
            continue
        print(f"\n第 {i} 行:")
        if not verify_row(row):
            all_correct = False
    
    if all_correct:
        print(f"\n✓ 所有行的计算都正确！")
    else:
        print(f"\n✗ 发现计算错误，请检查上述错误信息")


if __name__ == "__main__":
    main()
