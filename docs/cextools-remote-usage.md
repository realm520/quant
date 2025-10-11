# CEX Tools - 远程直接运行指南

## 🚀 直接从 GitHub 运行（无需安装）

### uvx 正确用法

```bash
# ✅ 正确：使用 git+ 前缀并指定分支
uvx --from git+https://github.com/realm520/quant.git@006-api-xt cextools --help

# 查看 BTC 价格
uvx --from git+https://github.com/realm520/quant.git@006-api-xt cextools market ticker BTC/USDT

# 查看订单簿
uvx --from git+https://github.com/realm520/quant.git@006-api-xt cextools market orderbook ETH/USDT --depth 20

# 或使用 main 分支（如果已合并）
uvx --from git+https://github.com/realm520/quant.git@main cextools --help
```

### 为什么需要 `git+` 前缀和分支？

- ❌ `uvx --from https://github.com/...` - uvx 会当作 PyPI 包名
- ✅ `uvx --from git+https://github.com/...` - uvx 识别为 Git 仓库
- ✅ `uvx --from git+https://github.com/...@branch` - 指定分支/标签/提交

### 分支说明

- `@006-api-xt` - cextools 功能分支（最新功能）
- `@main` - 主分支（稳定版本，功能合并后使用）
- `@v1.0.0` - 特定版本标签（如果有发布）

## 📝 常用命令示例

### 1. 查看帮助
```bash
uvx --from git+https://github.com/realm520/quant.git@006-api-xt cextools --help
uvx --from git+https://github.com/realm520/quant.git@006-api-xt cextools market --help
```

### 2. 获取实时价格
```bash
# BTC 价格
uvx --from git+https://github.com/realm520/quant.git@006-api-xt cextools market ticker BTC/USDT

# ETH 价格
uvx --from git+https://github.com/realm520/quant.git@006-api-xt cextools market ticker ETH/USDT

# 多个币种
uvx --from git+https://github.com/realm520/quant.git@006-api-xt cextools market ticker SOL/USDT
```

### 3. 获取订单簿深度
```bash
# 默认 20 档
uvx --from git+https://github.com/realm520/quant.git@006-api-xt cextools market orderbook BTC/USDT

# 50 档深度
uvx --from git+https://github.com/realm520/quant.git@006-api-xt cextools market orderbook BTC/USDT --depth 50

# 100 档深度
uvx --from git+https://github.com/realm520/quant.git@006-api-xt cextools market orderbook ETH/USDT --depth 100
```

### 4. 启用详细日志
```bash
uvx --from git+https://github.com/realm520/quant.git@006-api-xt cextools --verbose market ticker BTC/USDT
```

### 5. 指定交易所
```bash
# 默认 XT 交易所
uvx --from git+https://github.com/realm520/quant.git@006-api-xt cextools market ticker BTC/USDT

# 显式指定 XT
uvx --from git+https://github.com/realm520/quant.git@006-api-xt cextools --exchange xt market ticker BTC/USDT
```

## 🔧 创建 Shell Alias（简化命令）

为了避免每次输入长命令，可以创建别名：

### Bash/Zsh
```bash
# 添加到 ~/.bashrc 或 ~/.zshrc
alias cextools='uvx --from git+https://github.com/realm520/quant.git@006-api-xt cextools'

# 重新加载配置
source ~/.bashrc  # 或 source ~/.zshrc

# 现在可以直接使用
cextools market ticker BTC/USDT
cextools market orderbook ETH/USDT --depth 50
```

### Fish Shell
```fish
# 添加到 ~/.config/fish/config.fish
alias cextools='uvx --from git+https://github.com/realm520/quant.git@006-api-xt cextools'

# 现在可以直接使用
cextools market ticker BTC/USDT
```

## 🎯 使用场景

### 场景 1: 快速查价格（无需安装）
```bash
# 临时查询，不想安装
uvx --from git+https://github.com/realm520/quant.git cextools market ticker BTC/USDT
```

### 场景 2: 脚本集成
```bash
#!/bin/bash
# price_check.sh

BTC_PRICE=$(uvx --from git+https://github.com/realm520/quant.git \
  cextools market ticker BTC/USDT | grep "Mid Price" | awk '{print $4}')

echo "BTC Price: $BTC_PRICE"
```

### 场景 3: Cron 定时任务
```bash
# 每小时查询一次 BTC 价格
0 * * * * uvx --from git+https://github.com/realm520/quant.git cextools market ticker BTC/USDT >> /tmp/btc_prices.log
```

## ⚡ 性能优化

### 首次运行慢？

uvx 首次运行时需要：
1. 从 GitHub 克隆代码
2. 构建 Python 包
3. 创建虚拟环境

**解决方案**：uvx 会缓存环境，后续运行会快很多

### 清除缓存
```bash
# 如果遇到问题，清除 uvx 缓存
uv cache clean

# 重新运行
uvx --from git+https://github.com/realm520/quant.git cextools --help
```

## 🆚 对比：uvx vs 本地安装

| 特性 | uvx 远程运行 | 本地安装 |
|------|-------------|----------|
| 安装时间 | 首次慢，后续快 | 一次安装 |
| 磁盘占用 | 自动清理 | 需要虚拟环境 |
| 更新 | 自动使用最新版 | 需要手动更新 |
| 命令长度 | 长（需要 --from） | 短（直接 cextools） |
| 适用场景 | 临时使用、脚本 | 频繁使用、开发 |

## 📌 常见错误

### 错误 1: "An executable named `cextool` is not provided"
```bash
# ❌ 错误：命令名拼写错误
uvx --from git+https://github.com/realm520/quant.git cextool --help

# ✅ 正确：是 cextools（带 s）
uvx --from git+https://github.com/realm520/quant.git cextools --help
```

### 错误 2: "package `tri-arb` not found"
```bash
# ❌ 错误：缺少 git+ 前缀
uvx --from https://github.com/realm520/quant.git cextools --help

# ✅ 正确：添加 git+ 前缀
uvx --from git+https://github.com/realm520/quant.git cextools --help
```

### 错误 3: "Trading pair not found"
```bash
# ❌ 错误：符号格式错误
uvx --from git+https://github.com/realm520/quant.git cextools market ticker btc_usdt

# ✅ 正确：使用大写和斜杠
uvx --from git+https://github.com/realm520/quant.git cextools market ticker BTC/USDT
```

## 📚 更多信息

- 项目仓库: https://github.com/realm520/quant
- XT Exchange API: https://doc.xt.com
- UV 文档: https://docs.astral.sh/uv/
