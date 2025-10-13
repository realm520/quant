"""Unit tests for CLI exchange factory."""

import os
import pytest
from unittest.mock import patch

from tri_arb.cli.utils.exchange_factory import ExchangeType, create_exchange
from tri_arb.exchanges.xt_spot import XTSpotExchange
from tri_arb.exchanges.xt_perp import XTPerpExchange


class TestExchangeType:
    """Test ExchangeType enum."""
    
    def test_exchange_type_values(self):
        """Test that ExchangeType has correct values."""
        assert ExchangeType.SPOT.value == "spot"
        assert ExchangeType.PERP.value == "perp"
    
    def test_exchange_type_from_string(self):
        """Test that ExchangeType can be created from string."""
        assert ExchangeType("spot") == ExchangeType.SPOT
        assert ExchangeType("perp") == ExchangeType.PERP


class TestCreateExchangeSpot:
    """Test create_exchange for spot trading."""
    
    def test_create_spot_with_explicit_credentials(self):
        """Test creating spot exchange with explicit API credentials."""
        exchange = create_exchange(
            ExchangeType.SPOT,
            api_key="test_key",
            api_secret="test_secret"
        )
        
        assert isinstance(exchange, XTSpotExchange)
        assert exchange.api_key == "test_key"
        assert exchange.api_secret == "test_secret"
    
    @patch.dict(os.environ, {
        "XT_API_KEY": "env_spot_key",
        "XT_API_SECRET": "env_spot_secret"
    })
    def test_create_spot_from_environment(self):
        """Test creating spot exchange from environment variables."""
        exchange = create_exchange(ExchangeType.SPOT)
        
        assert isinstance(exchange, XTSpotExchange)
        assert exchange.api_key == "env_spot_key"
        assert exchange.api_secret == "env_spot_secret"
    
    @patch.dict(os.environ, {
        "XT_API_KEY": "env_spot_key",
        "XT_API_SECRET": "env_spot_secret"
    })
    def test_create_spot_explicit_overrides_environment(self):
        """Test that explicit credentials override environment variables."""
        exchange = create_exchange(
            ExchangeType.SPOT,
            api_key="explicit_key",
            api_secret="explicit_secret"
        )
        
        assert isinstance(exchange, XTSpotExchange)
        assert exchange.api_key == "explicit_key"
        assert exchange.api_secret == "explicit_secret"
    
    @patch.dict(os.environ, {}, clear=True)
    def test_create_spot_missing_api_key(self):
        """Test error when XT_API_KEY is missing."""
        with pytest.raises(ValueError, match="现货交易需要配置 XT_API_KEY 和 XT_API_SECRET"):
            create_exchange(ExchangeType.SPOT)
    
    @patch.dict(os.environ, {"XT_API_KEY": "key_only"}, clear=True)
    def test_create_spot_missing_api_secret(self):
        """Test error when XT_API_SECRET is missing."""
        with pytest.raises(ValueError, match="现货交易需要配置 XT_API_KEY 和 XT_API_SECRET"):
            create_exchange(ExchangeType.SPOT)


class TestCreateExchangePerp:
    """Test create_exchange for perpetual futures trading."""
    
    def test_create_perp_with_explicit_credentials(self):
        """Test creating perp exchange with explicit API credentials."""
        exchange = create_exchange(
            ExchangeType.PERP,
            api_key="test_perp_key",
            api_secret="test_perp_secret"
        )
        
        # XTPerpExchange stores credentials as private attributes
        assert isinstance(exchange, XTPerpExchange)
        assert exchange._api_key == "test_perp_key"
        assert exchange._api_secret == "test_perp_secret"
    
    @patch.dict(os.environ, {
        "XT_PERP_API_KEY": "env_perp_key",
        "XT_PERP_API_SECRET": "env_perp_secret"
    })
    def test_create_perp_from_environment(self):
        """Test creating perp exchange from environment variables."""
        exchange = create_exchange(ExchangeType.PERP)
        
        assert isinstance(exchange, XTPerpExchange)
        assert exchange._api_key == "env_perp_key"
        assert exchange._api_secret == "env_perp_secret"
    
    @patch.dict(os.environ, {
        "XT_PERP_API_KEY": "env_perp_key",
        "XT_PERP_API_SECRET": "env_perp_secret"
    })
    def test_create_perp_explicit_overrides_environment(self):
        """Test that explicit credentials override environment variables."""
        exchange = create_exchange(
            ExchangeType.PERP,
            api_key="explicit_perp_key",
            api_secret="explicit_perp_secret"
        )
        
        assert isinstance(exchange, XTPerpExchange)
        assert exchange._api_key == "explicit_perp_key"
        assert exchange._api_secret == "explicit_perp_secret"
    
    @patch.dict(os.environ, {}, clear=True)
    def test_create_perp_missing_api_key(self):
        """Test error when XT_PERP_API_KEY is missing."""
        with pytest.raises(ValueError, match="永续合约交易需要配置 XT_PERP_API_KEY 和 XT_PERP_API_SECRET"):
            create_exchange(ExchangeType.PERP)
    
    @patch.dict(os.environ, {"XT_PERP_API_KEY": "key_only"}, clear=True)
    def test_create_perp_missing_api_secret(self):
        """Test error when XT_PERP_API_SECRET is missing."""
        with pytest.raises(ValueError, match="永续合约交易需要配置 XT_PERP_API_KEY 和 XT_PERP_API_SECRET"):
            create_exchange(ExchangeType.PERP)


class TestCreateExchangeSeparateCredentials:
    """Test that spot and perp use separate credentials."""
    
    @patch.dict(os.environ, {
        "XT_API_KEY": "spot_key",
        "XT_API_SECRET": "spot_secret",
        "XT_PERP_API_KEY": "perp_key",
        "XT_PERP_API_SECRET": "perp_secret"
    })
    def test_spot_uses_spot_credentials(self):
        """Test that spot exchange uses XT_API_KEY/XT_API_SECRET."""
        exchange = create_exchange(ExchangeType.SPOT)
        
        assert isinstance(exchange, XTSpotExchange)
        assert exchange.api_key == "spot_key"
        assert exchange.api_secret == "spot_secret"
    
    @patch.dict(os.environ, {
        "XT_API_KEY": "spot_key",
        "XT_API_SECRET": "spot_secret",
        "XT_PERP_API_KEY": "perp_key",
        "XT_PERP_API_SECRET": "perp_secret"
    })
    def test_perp_uses_perp_credentials(self):
        """Test that perp exchange uses XT_PERP_API_KEY/XT_PERP_API_SECRET."""
        exchange = create_exchange(ExchangeType.PERP)
        
        assert isinstance(exchange, XTPerpExchange)
        assert exchange._api_key == "perp_key"
        assert exchange._api_secret == "perp_secret"
    
    @patch.dict(os.environ, {
        "XT_API_KEY": "spot_key",
        "XT_API_SECRET": "spot_secret"
    })
    def test_perp_cannot_use_spot_credentials(self):
        """Test that perp exchange cannot fall back to spot credentials."""
        with pytest.raises(ValueError, match="永续合约交易需要配置 XT_PERP_API_KEY 和 XT_PERP_API_SECRET"):
            create_exchange(ExchangeType.PERP)
