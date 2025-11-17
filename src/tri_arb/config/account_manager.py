"""账号配置管理器.

从 JSON 文件加载账号配置，支持多账号管理。
"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class AccountConfig:
    """账号配置."""
    
    account_id: str
    name: str
    exchange: str
    api_key: str
    api_secret: str
    enabled: bool = True
    channels: list[str] = None  # account, position, order, trade
    metrics_config: Optional[Dict[str, Any]] = None
    lark_webhook: Optional[str] = None
    lark_secret: Optional[str] = None
    passphrase: Optional[str] = None  # OKX 交易所需要
    
    def __post_init__(self):
        if self.channels is None:
            self.channels = ["account", "position"]


class AccountManager:
    """账号配置管理器."""
    
    def __init__(self, config_path: str | Path):
        """初始化账号管理器.
        
        Args:
            config_path: JSON 配置文件路径
        """
        self.config_path = Path(config_path)
        self.accounts: Dict[str, AccountConfig] = {}
        self.global_settings: Dict[str, Any] = {}
        self._load_config()
    
    def _load_config(self):
        """加载配置文件."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")
        
        with open(self.config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 加载全局设置
        self.global_settings = data.get("global_settings", {})
        
        # 处理环境变量替换
        database_url = self.global_settings.get("database_url", "")
        if database_url.startswith("${") and database_url.endswith("}"):
            env_var = database_url[2:-1]
            self.global_settings["database_url"] = os.getenv(env_var, "")
        
        # 加载账号配置
        accounts_data = data.get("accounts", {})
        for account_id, account_data in accounts_data.items():
            try:
                config = AccountConfig(
                    account_id=account_id,
                    name=account_data.get("name", account_id),
                    exchange=account_data.get("exchange", "xt"),
                    api_key=account_data.get("api_key", ""),
                    api_secret=account_data.get("api_secret", ""),
                    enabled=account_data.get("enabled", True),
                    channels=account_data.get("channels", ["account", "position"]),
                    metrics_config=account_data.get("metrics_config"),
                    lark_webhook=account_data.get("lark_webhook"),
                    lark_secret=account_data.get("lark_secret"),
                    passphrase=account_data.get("passphrase"),  # OKX 交易所需要
                )
                
                # 验证交易所名称（支持: xt, binance, okx, gate）
                supported_exchanges = ["xt", "binance", "okx", "gate"]
                if config.exchange.lower() not in supported_exchanges:
                    logger.warning(f"账号 {account_id} 使用不支持的交易所: {config.exchange}，支持的交易所: {', '.join(supported_exchanges)}")
                    continue
                
                if not config.api_key or not config.api_secret:
                    logger.warning(f"账号 {account_id} 缺少 API 凭证")
                    continue
                
                self.accounts[account_id] = config
                logger.info(f"加载账号配置: {account_id} ({config.name})")
            except Exception as e:
                logger.error(f"加载账号 {account_id} 配置失败: {e}", exc_info=True)
        
        logger.info(f"共加载 {len(self.accounts)} 个账号配置")
    
    def get_account(self, account_id: str) -> Optional[AccountConfig]:
        """获取账号配置."""
        return self.accounts.get(account_id)
    
    def get_enabled_accounts(self) -> list[AccountConfig]:
        """获取所有启用的账号."""
        return [acc for acc in self.accounts.values() if acc.enabled]
    
    def get_all_accounts(self) -> list[AccountConfig]:
        """获取所有账号."""
        return list(self.accounts.values())
    
    def reload(self):
        """重新加载配置."""
        self.accounts.clear()
        self._load_config()

