import pytest
from oanda import calculate_units

@pytest.mark.asyncio
async def test_calculate_units_live_exchange_rate():
    # Mock dependencies
    async def mock_get_account_balance(trading_type):
        return {"balance": 100000.0844, "leverage": 30, "currency": "GBP"}

    # Replace only the get_account_balance dependency
    calculate_units.__globals__["get_account_balance"] = mock_get_account_balance

    # Test inputs
    instrument = "EUR_USD"
    price = 0.64902
    stop_loss_price = 0.64772
    take_profit_price = 0.65162
    risk_percent = 1.0
    trading_type = "practice"

    # Call the function (live API call for exchange rate)
    result = await calculate_units(
        instrument=instrument,
        price=price,
        stop_loss_price=stop_loss_price,
        take_profit_price=take_profit_price,
        risk_percent=risk_percent,
        trading_type=trading_type,
    )

    # Print the result for debugging
    print("Test Result:", result)

    # Assertions
    assert result["units"] > 0
    assert result["account_balance_original"] == 100000.0844