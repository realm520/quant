"""
Unit tests for MonitorConfig validation.

Tests all validation rules for configuration parameters.
"""

import pytest
from pydantic import ValidationError

from tri_arb.arbitrage.config import MonitorConfig


class TestMonitorConfigValidation:
    """Test MonitorConfig validation rules."""
    
    def test_valid_config_creation(self):
        """Valid configuration should be created successfully."""
        config = MonitorConfig(
            min_profit_threshold=0.5,
            fee_rate_per_trade=0.1,
            base_currency_whitelist=["USDT", "BTC"],
            refresh_interval_seconds=10,
            run_mode="once"
        )
        
        assert config.min_profit_threshold == 0.5
        assert config.fee_rate_per_trade == 0.1
        assert config.base_currency_whitelist == ["USDT", "BTC"]
        assert config.refresh_interval_seconds == 10
        assert config.run_mode == "once"
    
    def test_default_values(self):
        """Default values should be applied correctly."""
        config = MonitorConfig()
        
        assert config.min_profit_threshold == 0.5
        assert config.fee_rate_per_trade == 0.1
        assert config.base_currency_whitelist == []
        assert config.refresh_interval_seconds == 10
        assert config.run_mode == "once"
    
    def test_invalid_profit_threshold_negative(self):
        """Negative profit threshold should raise ValidationError."""
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            MonitorConfig(min_profit_threshold=-1.0)
    
    def test_invalid_profit_threshold_too_high(self):
        """Profit threshold > 100 should raise ValidationError."""
        with pytest.raises(ValidationError, match="less than or equal to 100"):
            MonitorConfig(min_profit_threshold=150.0)
    
    def test_profit_threshold_boundary_values(self):
        """Boundary values 0 and 100 should be accepted."""
        config_min = MonitorConfig(min_profit_threshold=0.0)
        assert config_min.min_profit_threshold == 0.0
        
        config_max = MonitorConfig(min_profit_threshold=100.0)
        assert config_max.min_profit_threshold == 100.0
    
    def test_invalid_fee_rate_negative(self):
        """Negative fee rate should raise ValidationError."""
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            MonitorConfig(fee_rate_per_trade=-0.1)
    
    def test_invalid_fee_rate_too_high(self):
        """Fee rate > 10 should raise ValidationError."""
        with pytest.raises(ValidationError, match="less than or equal to 10"):
            MonitorConfig(fee_rate_per_trade=15.0)
    
    def test_fee_rate_boundary_values(self):
        """Boundary values 0 and 10 should be accepted."""
        config_min = MonitorConfig(fee_rate_per_trade=0.0)
        assert config_min.fee_rate_per_trade == 0.0
        
        config_max = MonitorConfig(fee_rate_per_trade=10.0)
        assert config_max.fee_rate_per_trade == 10.0
    
    def test_invalid_run_mode(self):
        """Invalid run mode should raise ValidationError."""
        with pytest.raises(ValidationError, match="run_mode"):
            MonitorConfig(run_mode="invalid_mode")
    
    def test_valid_run_modes(self):
        """Valid run modes 'once' and 'realtime' should be accepted."""
        config_once = MonitorConfig(run_mode="once")
        assert config_once.run_mode == "once"
        
        config_realtime = MonitorConfig(run_mode="realtime")
        assert config_realtime.run_mode == "realtime"
    
    def test_invalid_refresh_interval_too_low(self):
        """Refresh interval < 1 should raise ValidationError."""
        with pytest.raises(ValidationError, match="greater than or equal to 1"):
            MonitorConfig(refresh_interval_seconds=0)
    
    def test_invalid_refresh_interval_too_high(self):
        """Refresh interval > 3600 should raise ValidationError."""
        with pytest.raises(ValidationError, match="less than or equal to 3600"):
            MonitorConfig(refresh_interval_seconds=5000)
    
    def test_refresh_interval_boundary_values(self):
        """Boundary values 1 and 3600 should be accepted."""
        config_min = MonitorConfig(refresh_interval_seconds=1)
        assert config_min.refresh_interval_seconds == 1
        
        config_max = MonitorConfig(refresh_interval_seconds=3600)
        assert config_max.refresh_interval_seconds == 3600
    
    def test_invalid_currency_not_uppercase(self):
        """Lowercase currency in whitelist should raise ValidationError."""
        with pytest.raises(ValidationError, match="uppercase"):
            MonitorConfig(base_currency_whitelist=["usdt"])
    
    def test_invalid_currency_with_numbers(self):
        """Currency with numbers should raise ValidationError."""
        with pytest.raises(ValidationError, match="uppercase"):
            MonitorConfig(base_currency_whitelist=["BTC1"])
    
    def test_valid_currency_whitelist(self):
        """Valid uppercase currencies should be accepted."""
        config = MonitorConfig(base_currency_whitelist=["USDT", "BTC", "ETH"])
        assert config.base_currency_whitelist == ["USDT", "BTC", "ETH"]
    
    def test_empty_currency_whitelist(self):
        """Empty whitelist should be accepted (means all currencies)."""
        config = MonitorConfig(base_currency_whitelist=[])
        assert config.base_currency_whitelist == []
    
    def test_config_immutability(self):
        """Config should be immutable (frozen)."""
        config = MonitorConfig()
        
        with pytest.raises(ValidationError):
            config.min_profit_threshold = 10.0
