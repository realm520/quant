#!/usr/bin/env python3
"""验证币安断线重连修复是否正确应用.

这个脚本通过静态分析验证代码修复，不需要实际运行WebSocket连接。
"""

import ast
import inspect
from pathlib import Path


def check_return_type_annotations():
    """检查保存方法是否有返回值类型注解."""
    file_path = Path("/Users/oliver/work/quant/src/tri_arb/services/binance_user_stream.py")
    content = file_path.read_text()
    tree = ast.parse(content)

    methods_to_check = ['_save_order_with_dedup', '_save_trade_with_dedup']
    results = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            if node.name in methods_to_check:
                # 检查是否有返回类型注解
                has_return_type = node.returns is not None
                results[node.name] = has_return_type

                # 检查是否有return语句
                has_return_stmt = any(
                    isinstance(n, ast.Return) and n.value is not None
                    for n in ast.walk(node)
                )
                results[f"{node.name}_has_return"] = has_return_stmt

    return results


def check_connection_update_position():
    """检查连接状态更新是否在正确位置."""
    file_path = Path("/Users/oliver/work/quant/src/tri_arb/services/binance_user_stream.py")
    content = file_path.read_text()

    # 查找关键代码片段
    websocket_connect_line = None
    update_status_line = None

    lines = content.split('\n')
    for i, line in enumerate(lines, 1):
        if 'websockets.connect(self.ws_url)' in line:
            websocket_connect_line = i
        if 'WebSocket connected successfully' in line:
            # 查找之后的update_connection_status调用
            for j in range(i, min(i+10, len(lines))):
                if 'update_connection_status(is_connected=True)' in lines[j]:
                    update_status_line = j + 1
                    break
            break

    return {
        'websocket_connect_line': websocket_connect_line,
        'update_status_line': update_status_line,
        'update_after_connect': update_status_line and websocket_connect_line and update_status_line > websocket_connect_line
    }


def check_logging_improvements():
    """检查日志改进是否应用."""
    file_path = Path("/Users/oliver/work/quant/src/tri_arb/services/binance_user_stream.py")
    content = file_path.read_text()

    checks = {
        'has_recovery_reason': 'recovery_reason' in content,
        'has_gap_minutes': 'gap_minutes' in content,
        'has_duplicate_stats': 'duplicate_orders_skipped' in content,
        'has_detailed_warning': 'First time running (no historical data)' in content,
    }

    return checks


def check_active_symbols_fallback():
    """检查活跃交易对识别是否有7天回退."""
    file_path = Path("/Users/oliver/work/quant/src/tri_arb/services/binance_user_stream.py")
    content = file_path.read_text()

    checks = {
        'has_7day_fallback': 'timedelta(days=7)' in content,
        'has_24hour_check': 'timedelta(hours=24)' in content,
        'has_extended_search_log': 'extending search to 7 days' in content,
    }

    return checks


def print_result(check_name: str, result: dict):
    """打印检查结果."""
    print(f"\n{'='*80}")
    print(f"🔍 {check_name}")
    print('='*80)

    all_passed = all(v for v in result.values() if isinstance(v, bool))

    for key, value in result.items():
        if isinstance(value, bool):
            status = "✅" if value else "❌"
            print(f"  {status} {key}: {value}")
        else:
            print(f"  ℹ️  {key}: {value}")

    print()
    return all_passed


def main():
    """运行所有验证检查."""
    print("\n" + "="*80)
    print("🧪 验证币安断线重连修复")
    print("="*80)
    print()
    print("这个脚本验证代码修复是否正确应用（不需要实际运行WebSocket）")
    print()

    all_checks_passed = True

    # 检查1: 返回值类型注解
    result1 = check_return_type_annotations()
    passed1 = print_result("检查1: 保存方法返回值类型注解", result1)
    all_checks_passed = all_checks_passed and passed1

    # 检查2: 连接状态更新位置
    result2 = check_connection_update_position()
    passed2 = print_result("检查2: 连接状态更新位置", result2)
    all_checks_passed = all_checks_passed and passed2

    # 检查3: 日志改进
    result3 = check_logging_improvements()
    passed3 = print_result("检查3: 日志改进", result3)
    all_checks_passed = all_checks_passed and passed3

    # 检查4: 活跃交易对回退
    result4 = check_active_symbols_fallback()
    passed4 = print_result("检查4: 活跃交易对7天回退", result4)
    all_checks_passed = all_checks_passed and passed4

    # 总结
    print("="*80)
    if all_checks_passed:
        print("✅ 所有修复验证通过！")
        print()
        print("📝 修复内容:")
        print("  1. ✅ _save_order_with_dedup 和 _save_trade_with_dedup 有返回值")
        print("  2. ✅ 连接状态更新在 WebSocket 连接成功之后")
        print("  3. ✅ 日志包含恢复原因、断线时长、去重统计")
        print("  4. ✅ 活跃交易对识别支持7天回退")
    else:
        print("❌ 部分检查失败，请检查上述详情")
    print("="*80)
    print()

    # 显示关键代码片段
    if passed2:
        result2_info = check_connection_update_position()
        print("📍 连接状态更新位置:")
        print(f"   WebSocket连接: 第 {result2_info['websocket_connect_line']} 行")
        print(f"   状态更新: 第 {result2_info['update_status_line']} 行")
        print(f"   ✅ 状态更新在连接之后")
        print()

    print("💡 下一步建议:")
    print("  1. 运行实际测试: uv run python scripts/test_binance_reconnection.py")
    print("  2. 查看修复文档: cat BINANCE_RECONNECTION_FIXES.md")
    print("  3. 在测试环境验证断线重连功能")
    print()


if __name__ == "__main__":
    main()
