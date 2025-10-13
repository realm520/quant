# Research: XT 交易所统一 CLI 工具技术调研

**Feature**: 009-xt-perp-api | **Date**: 2025-10-12

## 1. Typer Framework Best Practices

### Decision: 使用 Typer 作为 CLI 框架
**Rationale**:
- **类型安全**: 基于 Python 类型注解自动生成参数验证和帮助文档
- **子命令组织**: 原生支持命令组（group）和子命令（command），符合 `cextools account balance` 的设计
- **与现有技术栈兼容**: 与 pydantic 深度集成，复用现有数据模型
- **易测试**: CLI 应用可以通过 `CliRunner` 进行单元测试

### 命令组织模式

**推荐结构**:
```python
import typer

app = typer.Typer()
account_app = typer.Typer()
market_app = typer.Typer()
order_app = typer.Typer()
leverage_app = typer.Typer()

app.add_typer(account_app, name="account")
app.add_typer(market_app, name="market")
app.add_typer(order_app, name="order")
app.add_typer(leverage_app, name="leverage")

@account_app.command("balance")
def account_balance(
    exchange_type: str = typer.Option(..., "--exchange-type", help="Exchange type: spot or perp")
):
    """Query account balance"""
    pass
```

**优势**:
- 清晰的模块化结构，每个命令组独立文件
- 自动生成层级帮助文档
- 支持全局参数和命令级参数

### 全局参数最佳实践

**推荐方式**: 使用 `typer.Context` 和回调函数
```python
@app.callback()
def main(
    ctx: typer.Context,
    debug: bool = typer.Option(False, "--debug", help="Enable debug mode"),
    output: str = typer.Option("table", "--output", help="Output format: table/json/csv"),
):
    """CEXTools - XT Exchange unified CLI tool"""
    ctx.ensure_object(dict)
    ctx.obj['debug'] = debug
    ctx.obj['output'] = output
```

**优势**:
- 全局参数在所有子命令中可用
- 通过 context 传递，避免全局变量
- 自动在帮助文档中显示

### 参数验证和错误处理

**推荐模式**:
```python
from enum import Enum

class ExchangeType(str, Enum):
    SPOT = "spot"
    PERP = "perp"

@account_app.command("balance")
def account_balance(
    exchange_type: ExchangeType = typer.Option(..., help="Exchange type"),
):
    # exchange_type 自动验证为 spot 或 perp
    pass
```

**错误处理**:
```python
try:
    # API 调用
    pass
except Exception as e:
    if ctx.obj.get('debug'):
        raise  # 调试模式显示完整堆栈
    else:
        typer.echo(f"Error: {str(e)}", err=True)
        raise typer.Exit(code=1)
```

### Alternatives Considered
- **Click**: Typer 的底层框架，但缺少类型安全和自动验证
- **argparse**: 标准库，但代码冗长且不支持类型注解
- **Fire**: Google 的库，过于自动化，难以控制参数验证逻辑

---

## 2. Rich Terminal UI Patterns

### Decision: 使用 Rich 进行终端渲染
**Rationale**:
- **表格渲染**: 强大的 Table 组件，自动处理宽度和对齐
- **颜色支持**: 内置主题和自定义颜色，支持盈亏标红/标绿
- **实时刷新**: Live 组件支持非阻塞刷新，适合 `watch` 命令
- **跨平台**: 自动检测终端能力，降级到纯文本

### Table 组件最佳实践

**基础表格**:
```python
from rich.console import Console
from rich.table import Table

console = Console()

def display_balance(balances: list[dict]):
    table = Table(title="Account Balance", show_header=True, header_style="bold magenta")
    table.add_column("Currency", style="cyan", width=12)
    table.add_column("Available", justify="right", style="green")
    table.add_column("Frozen", justify="right", style="yellow")
    table.add_column("Total", justify="right", style="white")

    for balance in balances:
        table.add_row(
            balance['currency'],
            f"{balance['available']:.8f}",
            f"{balance['frozen']:.8f}",
            f"{balance['total']:.8f}",
        )

    console.print(table)
```

**自适应宽度**:
```python
# Rich 自动计算列宽，无需手动指定
table.add_column("Symbol", no_wrap=True)  # 固定不换行
table.add_column("Price", justify="right", width=15)  # 固定宽度
table.add_column("Description")  # 自适应剩余空间
```

**颜色主题**:
```python
def format_pnl(pnl: Decimal) -> str:
    """根据盈亏正负显示颜色"""
    if pnl > 0:
        return f"[green]+{pnl:.2f}[/green]"
    elif pnl < 0:
        return f"[red]{pnl:.2f}[/red]"
    else:
        return f"[white]{pnl:.2f}[/white]"

table.add_row(
    symbol,
    format_pnl(position.unrealized_pnl),
    format_pnl(position.roe * 100) + "%",
)
```

### 实时刷新模式 (watch 命令)

**推荐实现**:
```python
from rich.live import Live
import asyncio

async def watch_ticker(symbol: str, interval: int):
    with Live(refresh_per_second=4) as live:
        while True:
            # 获取最新价格
            ticker = await exchange.get_ticker(symbol)

            # 更新表格
            table = create_ticker_table(ticker)
            live.update(table)

            # 等待指定间隔
            await asyncio.sleep(interval)
```

**优势**:
- 非阻塞刷新，不闪烁
- 支持 Ctrl+C 优雅退出
- 自动处理终端大小变化

### 多种输出格式切换

**架构设计**:
```python
# formatters/base.py
from abc import ABC, abstractmethod

class Formatter(ABC):
    @abstractmethod
    def format(self, data: list[dict]) -> str:
        pass

# formatters/table.py
class TableFormatter(Formatter):
    def format(self, data: list[dict]) -> str:
        # Rich Table 渲染
        pass

# formatters/json.py
class JSONFormatter(Formatter):
    def format(self, data: list[dict]) -> str:
        return json.dumps(data, indent=2, default=str)

# formatters/csv.py
class CSVFormatter(Formatter):
    def format(self, data: list[dict]) -> str:
        # CSV 格式化
        pass

# 使用 factory 模式
def get_formatter(output: str) -> Formatter:
    return {
        'table': TableFormatter(),
        'json': JSONFormatter(),
        'csv': CSVFormatter(),
    }[output]
```

### Alternatives Considered
- **tabulate**: 简单表格库，但缺少颜色和实时刷新
- **blessed**: 终端库，但过于底层，需要手动处理太多细节
- **直接打印**: 无法处理复杂格式和颜色，用户体验差

---

## 3. CLI Testing Strategies

### Decision: Typer CliRunner + pytest
**Rationale**:
- **CliRunner**: Typer 内置测试工具，模拟命令行输入
- **stdout/stderr 捕获**: 自动捕获输出，便于断言
- **Exit code 验证**: 验证命令成功/失败状态
- **与 pytest 集成**: 复用现有测试框架和 fixtures

### Contract Testing 模式

**测试结构**:
```python
from typer.testing import CliRunner
from tri_arb.cli.main import app

runner = CliRunner()

def test_account_balance_requires_exchange_type():
    """测试 account balance 命令必须提供 --exchange-type"""
    result = runner.invoke(app, ["account", "balance"])

    assert result.exit_code != 0
    assert "--exchange-type" in result.stdout or "exchange-type" in result.stdout.lower()

def test_account_balance_spot_success():
    """测试现货余额查询成功场景"""
    result = runner.invoke(app, ["account", "balance", "--exchange-type", "spot"])

    assert result.exit_code == 0
    assert "Currency" in result.stdout  # 表格标题
    assert "Available" in result.stdout

def test_order_place_perp_requires_position_side():
    """测试永续合约下单必须指定 position-side"""
    result = runner.invoke(app, [
        "order", "place",
        "--exchange-type", "perp",
        "--symbol", "BTC/USDT",
        "--side", "BUY",
        "--quantity", "0.01",
    ])

    assert result.exit_code != 0
    assert "position-side" in result.stdout.lower()
```

### CLI 输出断言方式

**推荐模式**:
```python
def test_balance_output_format():
    result = runner.invoke(app, ["account", "balance", "--exchange-type", "spot"])

    # 检查表格结构
    assert "Currency" in result.stdout
    assert "Available" in result.stdout
    assert "Frozen" in result.stdout

    # 检查数值格式（8位小数）
    import re
    assert re.search(r"\d+\.\d{8}", result.stdout)

def test_json_output_format():
    result = runner.invoke(app, ["account", "balance", "--exchange-type", "spot", "--output", "json"])

    import json
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert 'currency' in data[0]
    assert 'available' in data[0]
```

### Mock 外部依赖最佳实践

**推荐方式**: pytest fixtures + unittest.mock
```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.fixture
def mock_xt_spot_exchange():
    """Mock XTSpotExchange"""
    with patch('tri_arb.cli.utils.exchange_factory.XTSpotExchange') as mock:
        exchange = AsyncMock()
        exchange.get_balance.return_value = {
            'USDT': {'available': Decimal('1000.00'), 'frozen': Decimal('0.00')},
            'BTC': {'available': Decimal('0.05'), 'frozen': Decimal('0.01')},
        }
        mock.return_value = exchange
        yield exchange

def test_account_balance_with_mock(mock_xt_spot_exchange):
    result = runner.invoke(app, ["account", "balance", "--exchange-type", "spot"])

    # 验证 mock 被调用
    mock_xt_spot_exchange.get_balance.assert_called_once()

    # 验证输出
    assert "USDT" in result.stdout
    assert "1000.00" in result.stdout
```

### Alternatives Considered
- **直接调用函数**: 绕过 CLI 层，无法测试参数解析和输出格式
- **subprocess**: 真实子进程调用，速度慢且难以 mock
- **手动字符串匹配**: 脆弱，表格格式变化会导致测试失败

---

## 4. Exchange Type Routing

### Decision: Factory Pattern + Enum Validation
**Rationale**:
- **类型安全**: 使用 Enum 限制 exchange-type 为 spot/perp
- **单一职责**: factory 负责实例化，commands 负责业务逻辑
- **易扩展**: 未来添加新交易类型（如 options）只需修改 factory
- **可测试**: factory 和 commands 可独立测试

### Exchange Factory 设计

**实现**:
```python
# cli/utils/exchange_factory.py
from enum import Enum
from tri_arb.exchanges.xt_spot import XTSpotExchange
from tri_arb.exchanges.xt_perp import XTPerpExchange

class ExchangeType(str, Enum):
    SPOT = "spot"
    PERP = "perp"

def create_exchange(exchange_type: ExchangeType, api_key: str = None, api_secret: str = None):
    """根据 exchange-type 创建对应的 exchange 实例

    Args:
        exchange_type: 交易类型 (spot 或 perp)
        api_key: API 密钥（可选，默认从环境变量读取）
        api_secret: API 密钥（可选，默认从环境变量读取）

    Returns:
        XTSpotExchange 或 XTPerpExchange 实例

    Raises:
        ValueError: 如果 exchange_type 无效或 API 凭证缺失
    """
    import os

    if exchange_type == ExchangeType.SPOT:
        key = api_key or os.getenv('XT_API_KEY')
        secret = api_secret or os.getenv('XT_API_SECRET')

        if not key or not secret:
            raise ValueError(
                "现货交易需要配置 XT_API_KEY 和 XT_API_SECRET 环境变量\n"
                "或使用 --api-key 和 --api-secret 参数"
            )

        return XTSpotExchange(api_key=key, api_secret=secret)

    elif exchange_type == ExchangeType.PERP:
        key = api_key or os.getenv('XT_PERP_API_KEY')
        secret = api_secret or os.getenv('XT_PERP_API_SECRET')

        if not key or not secret:
            raise ValueError(
                "永续合约交易需要配置 XT_PERP_API_KEY 和 XT_PERP_API_SECRET 环境变量\n"
                "或使用 --api-key 和 --api-secret 参数"
            )

        return XTPerpExchange(api_key=key, api_secret=secret)

    else:
        raise ValueError(f"不支持的交易类型: {exchange_type}")
```

### 参数验证模式

**命令级验证**:
```python
# cli/commands/leverage.py
from tri_arb.cli.utils.exchange_factory import ExchangeType

@leverage_app.command("set")
def leverage_set(
    exchange_type: ExchangeType = typer.Option(...),
    symbol: str = typer.Option(...),
    leverage: int = typer.Option(..., min=1, max=125),
):
    """设置杠杆倍数（仅永续合约）"""

    # 验证只有 perp 支持杠杆
    if exchange_type != ExchangeType.PERP:
        typer.echo(
            "Error: leverage 命令仅适用于永续合约（perp），现货交易不支持杠杆",
            err=True
        )
        raise typer.Exit(code=1)

    # 正常执行
    exchange = create_exchange(exchange_type)
    # ...
```

**可选参数默认值**:
```python
@market_app.command("ticker")
def market_ticker(
    exchange_type: ExchangeType = typer.Option(ExchangeType.SPOT, help="默认查询现货市场"),
    symbol: str = typer.Option(None, help="不指定则显示所有交易对"),
):
    """查询市场价格"""
    # market 命令默认使用 spot
    pass
```

### 错误提示友好性

**推荐方式**:
```python
def validate_perp_order_params(position_side: str = None):
    """验证永续合约订单参数"""
    if not position_side:
        typer.echo(
            "Error: 永续合约下单需要指定 --position-side (LONG 或 SHORT)\n\n"
            "示例:\n"
            "  cextools order place --exchange-type perp --symbol BTC/USDT \\\n"
            "    --side BUY --position-side LONG --quantity 0.01\n",
            err=True
        )
        raise typer.Exit(code=1)
```

**错误消息设计原则**:
- 明确指出问题（"缺少 --position-side"）
- 提供解决方案（"需要指定 LONG 或 SHORT"）
- 给出示例（完整命令示例）
- 使用 `err=True` 输出到 stderr

### Alternatives Considered
- **if-else 判断**: 在每个命令中重复判断 exchange-type，代码冗余
- **继承 BaseExchange**: 增加复杂度，且现有 XTSpotExchange/XTPerpExchange 已完成
- **配置文件**: 过度设计，用户只需环境变量即可

---

## Summary

### Key Decisions
1. **CLI Framework**: Typer（类型安全 + 子命令组织 + 与 pydantic 集成）
2. **Terminal UI**: Rich（强大的表格 + 颜色 + 实时刷新）
3. **Testing**: CliRunner + pytest + AsyncMock（完整的 CLI 测试覆盖）
4. **Routing**: Factory Pattern + Enum（类型安全的 exchange-type 路由）

### Implementation Principles
- **类型安全优先**: 使用 Enum 和类型注解避免运行时错误
- **关注点分离**: factory 负责实例化，commands 负责业务逻辑，formatters 负责输出
- **用户体验**: 友好的错误提示 + 清晰的表格展示 + 多种输出格式
- **可测试性**: 每层都可独立测试，mock 外部依赖

### Next Steps (Phase 1)
根据以上研究结果，进入 Phase 1 设计阶段：
1. 提取数据模型 → data-model.md
2. 生成 API contracts → /contracts/*.py
3. 编写用户快速上手指南 → quickstart.md
4. 更新 CLAUDE.md

---
**Research Complete** ✓ | **Ready for Phase 1** ✓
