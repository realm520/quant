#!/usr/bin/env python3
"""测试 XT REST 模型，确保没有重复表定义错误。"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def test_model_imports():
    """测试模型导入"""
    print("=" * 60)
    print("测试 1: 导入模型")
    print("=" * 60)
    
    try:
        from tri_arb.storage.xt_rest_models import (
            XTSpotBalance,
            XTPerpBalance,
            XTPerpPosition,
            XTRestPositionUpdate,
            Base as XTRestBase
        )
        print("✓ 成功导入所有模型")
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


def test_table_names():
    """测试表名"""
    print("\n" + "=" * 60)
    print("测试 2: 检查表名")
    print("=" * 60)
    
    from tri_arb.storage.xt_rest_models import (
        XTSpotBalance,
        XTPerpBalance,
        XTPerpPosition,
        XTRestPositionUpdate,
    )
    
    assert XTSpotBalance.__tablename__ == "xt_account_snapshot", \
        f"XTSpotBalance 表名错误: {XTSpotBalance.__tablename__}"
    print(f"✓ XTSpotBalance 表名: {XTSpotBalance.__tablename__}")
    
    assert XTPerpBalance.__tablename__ == "xt_account_snapshot", \
        f"XTPerpBalance 表名错误: {XTPerpBalance.__tablename__}"
    print(f"✓ XTPerpBalance 表名: {XTPerpBalance.__tablename__}")
    
    assert XTPerpPosition.__tablename__ == "xt_position_snapshot", \
        f"XTPerpPosition 表名错误: {XTPerpPosition.__tablename__}"
    print(f"✓ XTPerpPosition 表名: {XTPerpPosition.__tablename__}")
    
    assert XTRestPositionUpdate.__tablename__ == "xt_position_snapshot", \
        f"XTRestPositionUpdate 表名错误: {XTRestPositionUpdate.__tablename__}"
    print(f"✓ XTRestPositionUpdate 表名: {XTRestPositionUpdate.__tablename__}")
    
    return True


def test_shared_tables():
    """测试共享表"""
    print("\n" + "=" * 60)
    print("测试 3: 检查共享表")
    print("=" * 60)
    
    from tri_arb.storage.xt_rest_models import (
        XTSpotBalance,
        XTPerpBalance,
        XTPerpPosition,
        XTRestPositionUpdate,
    )
    
    # 检查是否共享同一个表对象
    assert XTSpotBalance.__table__ is XTPerpBalance.__table__, \
        "XTSpotBalance 和 XTPerpBalance 应该共享同一个表对象"
    print("✓ XTSpotBalance 和 XTPerpBalance 共享同一个表对象")
    
    assert XTPerpPosition.__table__ is XTRestPositionUpdate.__table__, \
        "XTPerpPosition 和 XTRestPositionUpdate 应该共享同一个表对象"
    print("✓ XTPerpPosition 和 XTRestPositionUpdate 共享同一个表对象")
    
    return True


def test_metadata():
    """测试 metadata"""
    print("\n" + "=" * 60)
    print("测试 4: 检查 metadata")
    print("=" * 60)
    
    from tri_arb.storage.xt_rest_models import Base as XTRestBase
    
    tables = list(XTRestBase.metadata.tables.keys())
    print(f"Metadata 中的表: {sorted(tables)}")
    
    # 应该只有两个表（不是四个）
    expected_tables = {"xt_account_snapshot", "xt_position_snapshot"}
    actual_tables = set(tables)
    
    assert actual_tables == expected_tables, \
        f"Metadata 中应该有且仅有 {expected_tables}，但实际是 {actual_tables}"
    print(f"✓ Metadata 中只有 {len(tables)} 个表（没有重复）")
    
    return True


def test_column_access():
    """测试列访问"""
    print("\n" + "=" * 60)
    print("测试 5: 检查列访问")
    print("=" * 60)
    
    from tri_arb.storage.xt_rest_models import (
        XTSpotBalance,
        XTPerpBalance,
        XTPerpPosition,
        XTRestPositionUpdate,
    )
    
    # 检查 XTSpotBalance 的列
    spot_cols = set(c.name for c in XTSpotBalance.__table__.columns)
    print(f"XTSpotBalance 列: {sorted(spot_cols)}")
    
    # 检查 XTPerpBalance 的列（应该和 XTSpotBalance 相同）
    perp_cols = set(c.name for c in XTPerpBalance.__table__.columns)
    print(f"XTPerpBalance 列: {sorted(perp_cols)}")
    
    assert spot_cols == perp_cols, \
        f"XTSpotBalance 和 XTPerpBalance 的列应该相同"
    print("✓ XTSpotBalance 和 XTPerpBalance 的列相同")
    
    # 检查 XTPerpPosition 的列
    position_cols = set(c.name for c in XTPerpPosition.__table__.columns)
    print(f"XTPerpPosition 列: {sorted(position_cols)}")
    
    # 检查 XTRestPositionUpdate 的列（应该和 XTPerpPosition 相同）
    rest_position_cols = set(c.name for c in XTRestPositionUpdate.__table__.columns)
    print(f"XTRestPositionUpdate 列: {sorted(rest_position_cols)}")
    
    assert position_cols == rest_position_cols, \
        f"XTPerpPosition 和 XTRestPositionUpdate 的列应该相同"
    print("✓ XTPerpPosition 和 XTRestPositionUpdate 的列相同")
    
    return True


def test_model_instantiation():
    """测试模型实例化"""
    print("\n" + "=" * 60)
    print("测试 6: 检查模型实例化")
    print("=" * 60)
    
    from tri_arb.storage.xt_rest_models import (
        XTSpotBalance,
        XTPerpBalance,
        XTPerpPosition,
        XTRestPositionUpdate,
    )
    from datetime import datetime
    from decimal import Decimal
    
    # 测试 XTSpotBalance
    try:
        spot = XTSpotBalance(
            exchange_type='spot',
            query_time=datetime.utcnow(),
            query_type='test',
            account_id='test_account',
            asset='USDT',
            free=Decimal('100'),
            locked=Decimal('0'),
            total=Decimal('100'),
        )
        print("✓ XTSpotBalance 可以实例化")
    except Exception as e:
        print(f"❌ XTSpotBalance 实例化失败: {e}")
        return False
    
    # 测试 XTPerpBalance
    try:
        perp = XTPerpBalance(
            exchange_type='perp',
            query_time=datetime.utcnow(),
            query_type='test',
            account_id='test_account',
            asset='USDT',
            free=Decimal('100'),
            locked=Decimal('0'),
            total=Decimal('100'),
            unrealized_pnl=Decimal('10'),
        )
        print("✓ XTPerpBalance 可以实例化")
    except Exception as e:
        print(f"❌ XTPerpBalance 实例化失败: {e}")
        return False
    
    # 测试 XTPerpPosition
    try:
        position = XTPerpPosition(
            query_time=datetime.utcnow(),
            query_type='test',
            account_id='test_account',
            symbol='BTC/USDT',
            position_side='LONG',
            position_amount=Decimal('1'),
        )
        print("✓ XTPerpPosition 可以实例化")
    except Exception as e:
        print(f"❌ XTPerpPosition 实例化失败: {e}")
        return False
    
    # 测试 XTRestPositionUpdate
    try:
        rest_position = XTRestPositionUpdate(
            query_time=datetime.utcnow(),
            query_type='test',
            account_id='test_account',
            symbol='BTC/USDT',
            position_side='LONG',
            position_amount=Decimal('1'),
        )
        print("✓ XTRestPositionUpdate 可以实例化")
    except Exception as e:
        print(f"❌ XTRestPositionUpdate 实例化失败: {e}")
        return False
    
    return True


if __name__ == "__main__":
    print("开始测试 XT REST 模型...\n")
    
    tests = [
        test_model_imports,
        test_table_names,
        test_shared_tables,
        test_metadata,
        test_column_access,
        test_model_instantiation,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"\n❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)
    
    if failed == 0:
        print("\n🎉 所有测试通过！")
        sys.exit(0)
    else:
        print("\n❌ 有测试失败")
        sys.exit(1)

