import pytest
from oanda import get_accountcurrency_exchange_rate

@pytest.mark.asyncio
async def test_get_accountcurrency_exchange_rate():
    # Test inputs
    quote_currency = "USD"  # Replace with a valid quote currency (e.g., "EUR", "GBP", etc.)
    trading_type = "practice"  # Use "practice" to avoid affecting live accounts

    # Call the function
    exchange_rate = await get_accountcurrency_exchange_rate(quote_currency, trading_type)

    # Print the result for debugging
    print(f"Exchange rate for GBP/{quote_currency}: {exchange_rate}")

    # Assertions
    assert exchange_rate > 0, "Exchange rate should be greater than 0"