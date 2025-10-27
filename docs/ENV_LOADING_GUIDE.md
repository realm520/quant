# 环境变量加载指南

## 🔧 问题解决

您遇到的 `source .env` 无法加载环境变量的问题是因为bash默认不会自动导出 `.env` 文件中的变量。

## ✅ 解决方案

### 方法1: 使用提供的脚本（推荐）

```bash
# 进入项目目录
cd /home/w_zy/crypto/xt/quant

# 加载环境变量
source load_env.sh
# 或者
./load_env.sh
```

### 方法2: 手动加载

```bash
# 进入项目目录
cd /home/w_zy/crypto/xt/quant

# 手动加载环境变量
set -a && source .env && set +a
```

### 方法3: 使用函数（永久解决方案）

```bash
# 将函数添加到您的 shell 配置文件
echo 'source /home/w_zy/crypto/xt/quant/env_functions.sh' >> ~/.bashrc
# 或者对于 zsh
echo 'source /home/w_zy/crypto/xt/quant/env_functions.sh' >> ~/.zshrc

# 重新加载配置
source ~/.bashrc  # 或 source ~/.zshrc

# 现在可以使用函数
load_env
# 或者
env_load
```

## 🚀 验证环境变量

加载后，验证环境变量是否正确设置：

```bash
echo "BINANCE_API_KEY: $BINANCE_API_KEY"
echo "OKX_API_KEY: $OKX_API_KEY"
echo "GATE_API_KEY: $GATE_API_KEY"
echo "XT_API_KEY: $XT_API_KEY"
echo "DATABASE_URL: $DATABASE_URL"
```

## 📋 支持的所有交易所

### Binance（币安）
- `BINANCE_API_KEY`: API密钥
- `BINANCE_API_SECRET`: API密钥

### OKX
- `OKX_API_KEY`: API密钥
- `OKX_API_SECRET`: API密钥
- `OKX_PASSPHRASE`: API密码短语

### Gate.io
- `GATE_API_KEY`: API密钥
- `GATE_API_SECRET`: API密钥

### XT
- `XT_API_KEY`: API密钥（现货和永续合约共用）
- `XT_API_SECRET`: API密钥（现货和永续合约共用）

### 数据库配置
- `DATABASE_URL`: PostgreSQL数据库连接URL

## 🎯 下一步

环境变量加载成功后，您可以：

### WebSocket订阅
```bash
# 币安WebSocket订阅
python -m tri_arb.cli.main subscribe user-stream -x binance

# OKX WebSocket订阅
python -m tri_arb.cli.main subscribe user-stream -x okx

# Gate.io WebSocket订阅
python -m tri_arb.cli.main subscribe user-stream -x gate

# XT WebSocket订阅
python -m tri_arb.cli.main subscribe user-stream -x xt
```

### REST API查询
```bash
# 查询账户余额
cextools account balance -x binance  # 币安
cextools account balance -x okx      # OKX
cextools account balance -x gate     # Gate.io
cextools account balance -x xt        # XT

# 查询持仓
cextools account positions -x binance
cextools account positions -x okx
cextools account positions -x gate
cextools account positions -x xt

# 查询订单
cextools account orders -x binance
cextools account orders -x okx
cextools account orders -x gate
cextools account orders -x xt
```

## 💡 提示

- 每次打开新的终端窗口时，都需要重新加载环境变量
- 建议将 `source load_env.sh` 添加到您的 shell 配置文件中
- 确保 `.env` 文件不被提交到版本控制系统（已添加到 `.gitignore`）
- XT交易所的现货和永续合约使用同一个API密钥

## 🔒 安全注意事项

- 不要将 `.env` 文件提交到Git仓库
- 定期轮换API密钥
- 在生产环境中使用更安全的环境变量管理方式
- 为不同交易所设置不同的API密钥权限

