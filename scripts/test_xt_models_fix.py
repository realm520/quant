#!/usr/bin/env python3
"""测试 XT REST 模型修复，验证没有重复表定义错误。"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def test_import():
    """测试导入"""
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
        return True
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_metadata():
    """测试 metadata"""
    print("\n" + "=" * 60)
    print("测试 2: 检查 metadata（应该只有 2 个表，不是 4 个）")
    print("=" * 60)
    
    from tri_arb.storage.xt_rest_models import Base as XTRestBase
    
    tables = list(XTRestBase.metadata.tables.keys())
    print(f"Metadata 中的表 ({len(tables)} 个): {sorted(tables)}")
    
    # 应该只有两个表
    expected_tables = {"xt_account_snapshot", "xt_position_snapshot"}
    actual_tables = set(tables)
    
    if actual_tables == expected_tables:
        print(f"✓ Metadata 中只有 {len(tables)} 个表（没有重复）")
        return True
    else:
        print(f"❌ Metadata 中应该有 {expected_tables}，但实际是 {actual_tables}")
        return False


def test_shared_tables():
    """测试共享表"""
    print("\n" + "=" * 60)
    print("测试 3: 检查共享表对象")
    print("=" * 60)
    
    from tri_arb.storage.xt_rest_models import (
        XTSpotBalance,
        XTPerpBalance,
        XTPerpPosition,
        XTRestPositionUpdate,
    )
    
    # 检查是否共享同一个表对象
    if XTSpotBalance.__table__ is XTPerpBalance.__table__:
        print("✓ XTSpotBalance 和 XTPerpBalance 共享同一个表对象")
    else:
        print("❌ XTSpotBalance 和 XTPerpBalance 没有共享表对象")
        return False
    
    if XTPerpPosition.__table__ is XTRestPositionUpdate.__table__:
        print("✓ XTPerpPosition 和 XTRestPositionUpdate 共享同一个表对象")
    else:
        print("❌ XTPerpPosition 和 XTRestPositionUpdate 没有共享表对象")
        return False
    
    return True


def test_table_names():
    """测试表名"""
    print("\n" + "=" * 60)
    print("测试 4: 检查表名")
    print("=" * 60)
    
    from tri_arb.storage.xt_rest_models import (
        XTSpotBalance,
        XTPerpBalance,
        XTPerpPosition,
        XTRestPositionUpdate,
    )
    
    print(f"XTSpotBalance.__tablename__ = {XTSpotBalance.__tablename__}")
    print(f"XTPerpBalance.__tablename__ = {XTPerpBalance.__tablename__}")
    print(f"XTPerpPosition.__tablename__ = {XTPerpPosition.__tablename__}")
    print(f"XTRestPositionUpdate.__tablename__ = {XTRestPositionUpdate.__tablename__}")
    
    if (XTSpotBalance.__tablename__ == "xt_account_snapshot" and
        XTPerpBalance.__tablename__ == "xt_account_snapshot" and
        XTPerpPosition.__tablename__ == "xt_position_snapshot" and
        XTRestPositionUpdate.__tablename__ == "xt_position_snapshot"):
        print("✓ 所有表名正确")
        return True
    else:
        print("❌ 表名不正确")
        return False


def test_database_manager():
    """测试 DatabaseManager 能否正常导入 metadata"""
    print("\n" + "=" * 60)
    print("测试 5: 检查 DatabaseManager 能否正常导入")
    print("=" * 60)
    
    try:
        from tri_arb.storage.database import DatabaseManager
        from tri_arb.storage.xt_rest_models import Base as XTRestBase
        
        # 检查 metadata 是否正常
        tables = list(XTRestBase.metadata.tables.keys())
        print(f"✓ DatabaseManager 可以正常访问 XTRestBase.metadata")
        print(f"  Metadata 中的表: {sorted(tables)}")
        return True
    except Exception as e:
        print(f"❌ DatabaseManager 导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("开始测试 XT REST 模型修复...\n")
    
    tests = [
        ("导入模型", test_import),
        ("检查 metadata", test_metadata),
        ("检查共享表", test_shared_tables),
        ("检查表名", test_table_names),
        ("检查 DatabaseManager", test_database_manager),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
                print(f"\n❌ 测试 '{name}' 失败")
        except Exception as e:
            print(f"\n❌ 测试 '{name}' 出错: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)
    
    if failed == 0:
        print("\n🎉 所有测试通过！修复成功，没有重复表定义错误。")
        print("\n现在可以运行 create_tables() 来创建表了。")
        sys.exit(0)
    else:
        print("\n❌ 有测试失败，请检查错误信息。")
        sys.exit(1)

