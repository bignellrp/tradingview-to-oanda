import pytest
from unittest.mock import AsyncMock, patch
from server import post_data_to_oanda_parameters

@pytest.mark.asyncio
async def test_post_data_to_oanda_parameters():
    # Mock input data
    post_data = {
        "action": "open_long",
        "ticker": "EURUSD",
        "price": "1.12345",
        "stop_loss_price": "1.12000",
        "take_profit_price": "1.13000",
    }

    # Mock the translate function
    mock_translate = AsyncMock(return_value={
        "instrument": "EUR_USD",
        "action": "open_long",
        "price": "1.12345",
        "stop_loss_price": "1.12000",
        "take_profit_price": "1.13000",
    })

    # Mock the calculate_units function
    mock_calculate_units = AsyncMock(return_value={
        "units": 1000,
        "margin": 33.33,
        "pip_value": 0.0001,
        "trade_value": 1123.45,
        "reward": 0.5,
        "risk": 0.3,
        "account_balance_converted": 100000.0,
        "account_balance_original": 100000.0,
    })

    # Patch the dependencies
    with patch("server.translate", mock_translate), patch("server.calculate_units", mock_calculate_units):
        # Call the function
        result = await post_data_to_oanda_parameters(post_data)

        # Assertions
        assert result["instrument"] == "EUR_USD"
        assert result["units"] == 1000
        assert result["margin"] == 33.33
        assert result["pip_value"] == 0.0001
        assert result["trade_value"] == 1123.45
        assert result["reward"] == 0.5
        assert result["risk"] == 0.3

        # Ensure mocks were called
        mock_translate.assert_called_once_with(post_data)
        mock_calculate_units.assert_called_once_with(
            instrument="EUR_USD",
            price=1.12345,
            stop_loss_price=1.12,
            take_profit_price=1.13,
            risk_percent=100,
            trading_type="practice",
        )