# 重建 position_metrics 数据

## 用途

用于修复 `avg_sell_prz` 计算错误导致的数据问题。会重新计算所有零点快照和当前时刻的实时数据。

## 使用方法

### 1. 重建所有数据（推荐）

删除所有现有数据并重新计算：

```bash
python3 scripts/rebuild_position_metrics.py \
  --account-id account_008 \
  --exchange xt
```

### 2. 只重建特定交易对

```bash
python3 scripts/rebuild_position_metrics.py \
  --account-id account_008 \
  --exchange xt \
  --symbol rave_usdt
```

### 3. 保留现有数据（只重建缺失的数据）

```bash
python3 scripts/rebuild_position_metrics.py \
  --account-id account_008 \
  --exchange xt \
  --keep-existing
```

## 注意事项

1. **数据删除**：默认会删除所有现有数据，请确保已备份（如果需要）

2. **实时数据**：
   - 脚本会重新计算所有零点快照
   - 当前时刻的实时数据会立即重新计算
   - 历史实时数据（非零点快照）会在下次调度时自动使用正确的公式重新计算

3. **Grafana 图表**：
   - 零点快照修复后，Grafana 图表会立即显示正确数据
   - 历史实时数据需要等待调度器运行后才会更新

4. **调度器**：
   - 修复后，调度器会继续使用正确的公式计算新数据
   - 历史数据会在每次调度时逐步修复

## 执行流程

1. 删除现有数据（如果 `--keep-existing` 未指定）
2. 重建所有零点快照（使用正确的 `avg_sell_prz` 公式）
3. 重新计算当前时刻的实时数据
4. 提交所有更改到数据库

## 示例输出

```
正在删除现有的 position_metrics 数据...
已删除 1234 条记录
正在重建零点快照...
零点快照重建完成
正在重新计算当前时刻的实时数据...
当前时刻的实时数据已重新计算

数据重建完成！
✅ 所有零点快照已使用正确的公式重新计算
✅ 当前时刻的实时数据已重新计算

注意：
  - 历史实时数据（非零点快照）会在下次调度时自动使用正确的公式重新计算
  - 或者您可以等待调度器运行，它会自动修复所有数据
```
