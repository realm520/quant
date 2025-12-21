from datetime import datetime, timezone

timestamp = 1765760578237

print("=" * 80)
print("时间戳转换测试")
print("=" * 80)
print(f"原始时间戳（毫秒）: {timestamp}")
print()

# 方式1: 直接当作秒级（错误，会报错）
print("方式1: 直接当作秒级时间戳（错误）:")
try:
dt = datetime.fromtimestamp(timestamp, timezone.utc)
    print(f"  {dt}")
except ValueError as e:
    print(f"  ❌ 错误: {e}")
    print("  原因: timestamp 是毫秒级（13位数字），不能直接当作秒级使用")

print()

# 方式2: 除以 1000 当作毫秒级（正确）
print("方式2: 除以 1000 当作毫秒级时间戳（正确）:")
dt1 = datetime.fromtimestamp(timestamp / 1000.0, timezone.utc)
print(f"  {dt1}")
print(f"  时间戳（秒）: {timestamp / 1000.0}")

print()
print("=" * 80)
print("结论: XT 的 timestamp 是毫秒级，必须除以 1000 才能正确转换")
print("=" * 80)