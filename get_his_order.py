import time
import hmac
import hashlib
import requests
from urllib.parse import urlencode

API_KEY = "b633f68d-89e4-418f-862e-7ca6014e61aa"
API_SECRET = "73c94dfe4418e2360b005fdf6fad32da5a9799d3"

BASE_URL = "https://fapi.xt.com"


def generate_signature(method: str, path: str, params: dict = None, body: dict = None, timestamp: str = None):
    """生成 XT API v2 签名（使用新的签名方式）
    
    新接口签名算法（参考 xt_perp.py）：
    1. 构建 signkey: "xt-validate-appkey={appkey}&xt-validate-timestamp={timestamp}#{path}#{message}"
    2. 如果有 params: message = "key1=value1&key2=value2" (按 key 排序)
    3. 如果有 body: message = JSON 字符串
    4. 如果没有 params 和 body: message = 空字符串
    5. 对 signkey 进行 HMAC-SHA256 签名
    """
    timestamp_value = timestamp or str(int(time.time() * 1000))
    
    # 构建 message 部分
    if body is not None:
        # JSON body
        import json
        message = json.dumps(body, separators=(',', ':'), ensure_ascii=False)
    elif params is not None and len(params) > 0:
        # Form-urlencoded params - 按 key 排序
        sorted_params = dict(sorted(params.items(), key=lambda e: e[0]))
        message = "&".join([f"{k}={v}" for k, v in sorted_params.items()])
    else:
        # 没有 params 或 body
        message = ""
    
    # 构建 signkey（注意格式：appkey&timestamp#path#message）
    signkey = f"xt-validate-appkey={API_KEY}&xt-validate-timestamp={timestamp_value}#{path}#{message}"
    
    # 生成 HMAC-SHA256 签名
    signature = hmac.new(
        API_SECRET.encode("utf-8"),
        signkey.encode("utf-8"),
        digestmod=hashlib.sha256
    ).hexdigest()
    
    return signature, timestamp_value


def xt_get(path, params=None, verbose=True):
    """使用 XT API v2 签名方式请求"""
    if params is None:
        params = {}
    
    # 生成签名和时间戳
    signature, timestamp = generate_signature("GET", path, params=params)
    
    # 构建 headers（新接口使用 xt-validate-* 格式）
    headers = {
        "Content-Type": "application/json",
        "validate-signversion": "2",
        "xt-validate-appkey": API_KEY,
        "xt-validate-timestamp": timestamp,
        "xt-validate-signature": signature,
        "xt-validate-algorithms": "HmacSHA256",
    }
    
    url = BASE_URL + path
    if verbose:
        print("REQUEST:", url)
        print("PARAMS:", params)
    
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        if verbose:
            print("STATUS:", resp.status_code)
        
        if resp.status_code == 200:
            try:
                return resp.json()
            except Exception as e:
                print(f"JSON 解析错误: {e}")
                return None
        else:
            if verbose:
                print(f"请求失败: {resp.status_code}")
                print("RAW TEXT:", resp.text[:500])
            return None
    except requests.exceptions.ConnectionError as e:
        print(f"连接错误: {e}")
        print("提示: 可能是网络不通或 iptables 规则阻止了连接")
        return None
    except Exception as e:
        print(f"请求异常: {e}")
        return None


def get_all_orders(symbol, start_time, end_time, limit=100, verbose=False):
    """获取指定时间范围内的所有订单（支持分页）
    
    使用时间戳分页：每次使用上一页最后一条订单的时间戳作为下一页的 startTime
    """
    all_orders = []
    has_next = True
    current_start_time = start_time
    page = 0
    
    print(f"开始获取订单（分页查询）...")
    
    while has_next:
        page += 1
        params = {
            "symbol": symbol,
            "limit": limit,
            "startTime": current_start_time,
            "endTime": end_time,
        }
        
        if verbose:
            print(f"\n请求第 {page} 页...")
            import time as time_module
            start_str = time_module.strftime('%H:%M:%S', time_module.localtime(current_start_time/1000))
            end_str = time_module.strftime('%H:%M:%S', time_module.localtime(end_time/1000))
            print(f"  时间范围: {start_str} 至 {end_str}")
        
        data = xt_get("/future/trade/v1/order/list-history", params, verbose=verbose)
        
        if not data or data.get("returnCode") != 0:
            error = data.get("error", {}) if data else {}
            error_msg = error.get("msg", "未知错误") if isinstance(error, dict) else str(error)
            print(f"❌ 请求失败: {error_msg}")
            if "timeout" in error_msg.lower() or "504" in error_msg:
                print("⚠️  API 超时，可能需要缩小时间范围或稍后重试")
            break
        
        result = data.get("result", {})
        items = result.get("items", [])
        
        if not items:
            if verbose:
                print("  本页无数据")
            break
        
        all_orders.extend(items)
        has_next = result.get("hasNext", False)
        
        if verbose:
            print(f"  ✅ 本页获取 {len(items)} 条，累计 {len(all_orders):,} 条")
            if has_next:
                print(f"  ➡️  还有更多数据，继续查询...")
        
        # 使用最后一条订单的时间戳作为下一页的起始时间
        # 注意：需要 +1 毫秒以避免重复获取同一条订单
        if items and has_next:
            last_order_time = items[-1].get("createdTime", 0)
            if last_order_time:
                current_start_time = last_order_time + 1
            else:
                # 如果没有时间戳，可能无法继续分页
                print("⚠️  最后一条订单没有时间戳，无法继续分页")
                break
        else:
            break
        
        # 避免无限循环
        if len(all_orders) > 10000:
            print(f"⚠️  订单数量超过 10000 条，停止查询")
            break
        
        # 添加小延迟，避免请求过快
        import time as time_module
        time_module.sleep(0.1)
    
    return all_orders


def analyze_orders(orders):
    """统计和分析订单数据"""
    if not orders:
        print("没有订单数据")
        return
    
    total = len(orders)
    
    # 统计状态分布
    status_count = {}
    side_count = {}
    position_side_count = {}
    
    # 统计成交情况
    filled_count = 0
    canceled_count = 0
    new_count = 0
    total_filled_qty = 0
    total_orig_qty = 0
    
    # 时间范围
    min_time = None
    max_time = None
    
    for order in orders:
        # 状态统计
        state = order.get("state", "UNKNOWN")
        status_count[state] = status_count.get(state, 0) + 1
        
        # 方向统计
        order_side = order.get("orderSide", "UNKNOWN")
        side_count[order_side] = side_count.get(order_side, 0) + 1
        
        # 多空统计
        position_side = order.get("positionSide", "UNKNOWN")
        position_side_count[position_side] = position_side_count.get(position_side, 0) + 1
        
        # 成交统计
        # XT API 可能的状态: NEW, FILLED, PARTIALLY_FILLED, CANCELED, PARTIALLY_CANCELED, EXPIRED
        if state == "FILLED":
            filled_count += 1
        elif state in ["CANCELED", "PARTIALLY_CANCELED"] or "CANCEL" in state.upper():
            canceled_count += 1
        elif state == "NEW":
            new_count += 1
        elif state == "PARTIALLY_FILLED":
            # 部分成交的订单也计入已成交
            filled_count += 1
        
        # 数量统计
        orig_qty = float(order.get("origQty", 0) or 0)
        executed_qty = float(order.get("executedQty", 0) or 0)
        total_orig_qty += orig_qty
        total_filled_qty += executed_qty
        
        # 时间范围
        created_time = order.get("createdTime", 0)
        if created_time:
            if min_time is None or created_time < min_time:
                min_time = created_time
            if max_time is None or created_time > max_time:
                max_time = created_time
    
    # 打印统计信息
    print("\n" + "="*60)
    print("📊 订单统计报告")
    print("="*60)
    print(f"\n📈 总体统计:")
    print(f"  总订单数: {total:,} 条")
    if min_time and max_time:
        import time
        min_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(min_time/1000))
        max_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(max_time/1000))
        duration_seconds = (max_time - min_time) / 1000
        duration_minutes = duration_seconds / 60
        print(f"  时间范围: {min_str} 至 {max_str}")
        print(f"  时长: {duration_minutes:.1f} 分钟 ({duration_seconds:.0f} 秒)")
    
    print(f"\n📋 状态分布:")
    for status, count in sorted(status_count.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / total * 100) if total > 0 else 0
        print(f"  {status:20s}: {count:6,} 条 ({percentage:5.1f}%)")
    
    print(f"\n🔄 成交情况:")
    if total > 0:
        print(f"  已成交订单: {filled_count:,} 条 ({filled_count/total*100:.1f}%)")
        print(f"  已取消订单: {canceled_count:,} 条 ({canceled_count/total*100:.1f}%)")
        print(f"  新订单: {new_count:,} 条 ({new_count/total*100:.1f}%)")
        
        # 显示其他状态
        other_count = total - filled_count - canceled_count - new_count
        if other_count > 0:
            print(f"  其他状态: {other_count:,} 条 ({other_count/total*100:.1f}%)")
    else:
        print("  无订单数据")
    
    print(f"\n📊 方向统计:")
    for side, count in sorted(side_count.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / total * 100) if total > 0 else 0
        print(f"  {side:10s}: {count:6,} 条 ({percentage:5.1f}%)")
    
    print(f"\n⚖️  多空统计:")
    for pos_side, count in sorted(position_side_count.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / total * 100) if total > 0 else 0
        print(f"  {pos_side:10s}: {count:6,} 条 ({percentage:5.1f}%)")
    
    print(f"\n💹 数量统计:")
    print(f"  总订单数量: {total_orig_qty:,.2f}")
    print(f"  总成交数量: {total_filled_qty:,.2f}")
    if total_orig_qty > 0:
        fill_rate = total_filled_qty / total_orig_qty * 100
        print(f"  成交率: {fill_rate:.2f}%")
    
    print("="*60)


def print_canceled_orders(orders):
    """打印所有 CANCELED 订单的详细信息"""
    canceled_orders = [o for o in orders if o.get("state", "").upper() in ["CANCELED", "PARTIALLY_CANCELED"] or "CANCEL" in o.get("state", "").upper()]
    
    if not canceled_orders:
        print("\n⚠️  未找到 CANCELED 订单")
        return
    
    # 分类统计
    fully_canceled = [o for o in canceled_orders if o.get("state") == "CANCELED"]
    partially_canceled = [o for o in canceled_orders if o.get("state") == "PARTIALLY_CANCELED"]
    platform_revoked = [o for o in canceled_orders if o.get("desc", "").lower() == "platform_revocation"]
    user_revoked = [o for o in canceled_orders if o.get("desc", "").lower() == "user_revocation"]
    
    print("\n" + "="*100)
    print(f"📋 CANCELED 订单详情（共 {len(canceled_orders):,} 条）")
    print("="*100)
    print(f"\n📊 取消订单分类统计:")
    print(f"  - 完全取消 (CANCELED): {len(fully_canceled):,} 条")
    print(f"  - 部分取消 (PARTIALLY_CANCELED): {len(partially_canceled):,} 条")
    print(f"  - 平台撤销 (platform_revocation): {len(platform_revoked):,} 条")
    print(f"  - 用户撤销 (user_revocation): {len(user_revoked):,} 条")
    print()
    
    import time as time_module
    for i, order in enumerate(canceled_orders, 1):
        order_id = order.get("orderId", "N/A")
        symbol = order.get("symbol", "N/A")
        state = order.get("state", "N/A")
        order_side = order.get("orderSide", "N/A")
        position_side = order.get("positionSide", "N/A")
        order_type = order.get("orderType", "N/A")
        orig_qty = str(order.get("origQty", "0") or "0")
        executed_qty = str(order.get("executedQty", "0") or "0")
        canceled_qty = str(order.get("canceledQty", "0") or "0")  # 取消数量
        price = str(order.get("price", "0") or "0")
        avg_price = str(order.get("avgPrice", "0") or "0")
        created_time = order.get("createdTime", 0)
        updated_time = order.get("updatedTime", 0)
        
        created_str = time_module.strftime('%Y-%m-%d %H:%M:%S', time_module.localtime(created_time/1000)) if created_time else "N/A"
        updated_str = time_module.strftime('%Y-%m-%d %H:%M:%S', time_module.localtime(updated_time/1000)) if updated_time else "N/A"
        
        desc = order.get("desc", "") or ""  # 取消原因
        system_cancel = order.get("systemCancel", False)  # 是否系统取消
        
        # 计算剩余数量（原始 - 已成交）
        try:
            orig_num = float(orig_qty) if orig_qty != "N/A" else 0
            exec_num = float(executed_qty) if executed_qty != "N/A" else 0
            remaining = orig_num - exec_num
        except:
            remaining = 0
        
        print(f"\n[{i:4d}] 订单ID: {order_id}")
        print(f"      交易对: {symbol:15s} | 状态: {state:20s}")
        print(f"      方向: {order_side:4s} {position_side:6s} | 类型: {order_type:10s}")
        print(f"      数量: 原始={orig_qty:>10s} | 已成交={executed_qty:>10s} | 剩余={remaining:>10.2f}")
        print(f"      价格: 委托价={price:>10s} | 成交均价={avg_price:>10s}")
        print(f"      时间: 创建={created_str} | 更新={updated_str}")
        if desc:
            cancel_reason = "平台撤销" if "platform" in desc.lower() else "用户撤销" if "user" in desc.lower() else desc
            print(f"      取消原因: {cancel_reason}")
        if system_cancel:
            print(f"      ⚠️  系统取消")
        print("-" * 100)
    
    print(f"\n✅ 共显示 {len(canceled_orders):,} 条 CANCELED 订单")


def test_history_orders():
    """测试获取历史订单并统计"""
    # 获取最近1小时的订单，避免查询时间过长导致超时
    import time as time_module
    end_time = int(time_module.time() * 1000)  # 当前时间（毫秒）
    start_time = end_time - (60 * 60 * 1000)  # 1小时前（毫秒）
    
    symbol = "trump_usdt"  # 注意：XT API 使用小写和下划线
    
    print(f"查询参数:")
    print(f"  - symbol: {symbol}")
    print(f"  - startTime: {start_time} ({time_module.strftime('%Y-%m-%d %H:%M:%S', time_module.localtime(start_time/1000))})")
    print(f"  - endTime: {end_time} ({time_module.strftime('%Y-%m-%d %H:%M:%S', time_module.localtime(end_time/1000))})")
    print(f"  - 查询范围: 最近1小时")
    print()
    
    # 获取所有订单（分页）
    all_orders = get_all_orders(symbol, start_time, end_time, limit=100, verbose=True)
    
    if not all_orders:
        print("\n❌ 未获取到订单数据")
        return
    
    print(f"\n✅ 成功获取所有订单，共 {len(all_orders):,} 条")
    
    # 统计和分析
    analyze_orders(all_orders)
    
    # 专门显示 CANCELED 订单
    print_canceled_orders(all_orders)
    
    # 显示部分订单详情
    print(f"\n📝 最新订单示例（前10条）:")
    import time as time_module
    for i, order in enumerate(all_orders[:10], 1):
        order_id = order.get("orderId", "N/A")
        state = order.get("state", "N/A")
        order_side = order.get("orderSide", "N/A")
        position_side = order.get("positionSide", "N/A")
        orig_qty = order.get("origQty", "N/A")
        executed_qty = order.get("executedQty", "N/A")
        price = order.get("price", "N/A")
        created_time = order.get("createdTime", 0)
        time_str = time_module.strftime('%Y-%m-%d %H:%M:%S', time_module.localtime(created_time/1000)) if created_time else "N/A"
        
        print(f"  [{i:2d}] {order_id} | {order_side:4s} {position_side:6s} | {orig_qty:>8s} @ {price:>8s} | 成交: {executed_qty:>8s} | {state:20s} | {time_str}")


if __name__ == "__main__":
    test_history_orders()
