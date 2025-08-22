import datetime
import json
import logging
import os
import aiofiles  # For asynchronous file I/O
import httpx  # For asynchronous HTTP requests

# Enable debug mode to log requests instead of sending them to OANDA
DEBUG_MODE = True

def get_datetime_offset(offset_minutes: int = 15) -> str:
    """Get the current UTC time offset by a given number of minutes in RFC3339 format."""
    now = datetime.datetime.utcnow()
    now_plus_offset = now + datetime.timedelta(minutes=offset_minutes)
    return f"{now_plus_offset.isoformat('T')}Z"

def get_datetime_now() -> str:
    """Get the current UTC time in RFC3339 format."""
    now = datetime.datetime.utcnow()
    return f"{now.isoformat('T')}Z"

def get_credentials(trading_type: str) -> dict:
    """Retrieve OANDA API credentials for the given trading type."""
    loc = "oanda.py:get_credentials"

    try:
        with open("credentials.json") as credentials_json:
            credentials = json.load(credentials_json)[f"oanda_{trading_type}"]
    except Exception as e:
        logging.exception(f"{loc}: Could not read {trading_type} credentials from credentials.json: {e}")
        raise

    return credentials

def get_base_url(trading_type: str) -> str:
    """Get the base URL for the OANDA API based on the trading type."""
    return f"https://api-fx{'trade' if trading_type == 'live' else 'practice'}.oanda.com"

async def get_accounts(trading_type: str = "practice") -> httpx.Response:
    """Retrieve OANDA accounts for the given trading type."""
    loc = "oanda.py:get_accounts"

    try:
        credentials = get_credentials(trading_type)

        url = f"{get_base_url(trading_type)}/v3/accounts"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {credentials['api_key']}",
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response
    except Exception as e:
        logging.exception(f"{loc}: Could not get {trading_type} accounts from the OANDA API: {e}")
        raise

async def get_instruments(trading_type: str = "practice") -> dict:
    """Retrieve OANDA instruments for the given trading type."""
    loc = "oanda.py:get_instruments"

    try:
        credentials = get_credentials(trading_type)

        url = f"{get_base_url(trading_type)}/v3/accounts/{credentials['account_id']}/instruments"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {credentials['api_key']}",
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logging.exception(f"{loc}: Could not get {trading_type} instruments from the OANDA API: {e}")
        raise

async def get_price_precision(instrument: str, trading_type: str = "practice") -> int:
    """Get the price precision for a given instrument."""
    price_precisions = await get_price_precisions(trading_type)
    return price_precisions[instrument]

async def get_price_precisions(trading_type: str = "practice") -> dict:
    """Retrieve or generate price precisions for instruments."""
    price_precisions_file = "price_precisions.json"

    if os.path.isfile(price_precisions_file):
        price_precisions = await load_price_precisions(price_precisions_file)
    else:
        price_precisions = await save_price_precisions(price_precisions_file, trading_type)

    return price_precisions

async def save_price_precisions(price_precisions_file: str, trading_type: str = "practice") -> dict:
    """Save price precisions for instruments to a file."""
    instruments = await get_instruments(trading_type)

    price_precisions = {instrument["name"]: instrument["displayPrecision"] for instrument in instruments["instruments"]}

    async with aiofiles.open(price_precisions_file, "w") as price_precisions_json:
        await price_precisions_json.write(json.dumps(price_precisions, indent=2, sort_keys=True))

    return price_precisions

async def load_price_precisions(price_precisions_file: str) -> dict:
    """Load price precisions for instruments from a file."""
    async with aiofiles.open(price_precisions_file, "r") as price_precisions_json:
        content = await price_precisions_json.read()
        return json.loads(content)

async def get_account_balance(trading_type: str = "practice") -> float:
    """Retrieve the account balance from OANDA."""
    loc = "oanda.py:get_account_balance"

    try:
        credentials = get_credentials(trading_type)

        url = f"{get_base_url(trading_type)}/v3/accounts/{credentials['account_id']}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {credentials['api_key']}",
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            account_data = response.json()
            return float(account_data["account"]["balance"])
    except Exception as e:
        logging.exception(f"{loc}: Could not retrieve account balance: {e}")
        raise

async def open_long_position(
    instrument: str,
    price: float,
    stop_loss_price: float,
    take_profit_price: float,
    risk_percent: float = 1.0,
    trading_type: str = "practice",
) -> dict:
    """Open a long position on OANDA."""
    loc = "oanda.py:open_long_position"

    try:
        # Calculate the number of units to trade
        units = await calculate_units(
            instrument=instrument,
            price=price,
            stop_loss_price=stop_loss_price,
            risk_percent=risk_percent,
            trading_type=trading_type,
        )

        credentials = get_credentials(trading_type)
        price_decimals = await get_price_precision(instrument, trading_type)

        url = f"{get_base_url(trading_type)}/v3/accounts/{credentials['account_id']}/orders"

        payload = {
            "order": {
                "type": "MARKET",
                "positionFill": "DEFAULT",
                "instrument": instrument,
                "units": f"{units}",
                "stopLossOnFill": {
                    "price": f"{stop_loss_price:.{price_decimals}f}",
                },
                "takeProfitOnFill": {
                    "price": f"{take_profit_price:.{price_decimals}f}",
                },
            }
        }

        if DEBUG_MODE:
            logging.info(f"{get_datetime_now()} - OPEN LONG POSITION:\n{json.dumps(payload, indent=2)}")
            logging.info(f"{loc}: Debug mode enabled. Order logged to server.log.")
            return {"status": "debug", "message": "Order logged to server.log"}

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {credentials['api_key']}",
                },
                json=payload,
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logging.exception(f"{loc}: Could not open long position: {e}")
        raise

async def close_long_position(instrument: str, trading_type: str = "practice") -> dict:
    """Close a long position on OANDA."""
    loc = "oanda.py:close_long_position"

    try:
        credentials = get_credentials(trading_type)

        url = f"{get_base_url(trading_type)}/v3/accounts/{credentials['account_id']}/positions/{instrument}/close"

        payload = {
            "longUnits": "ALL",
        }

        if DEBUG_MODE:
            logging.info(f"{get_datetime_now()} - CLOSE LONG POSITION:\n{json.dumps(payload, indent=2)}")
            logging.info(f"{loc}: Debug mode enabled. Order logged to server.log.")
            return {"status": "debug", "message": "Order logged to server.log"}

        async with httpx.AsyncClient() as client:
            response = await client.put(
                url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {credentials['api_key']}",
                },
                json=payload,
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logging.exception(f"{loc}: Could not close long position: {e}")
        raise

async def open_short_position(
    instrument: str,
    price: float,
    stop_loss_price: float,
    take_profit_price: float,
    risk_percent: float = 1.0,
    trading_type: str = "practice",
) -> dict:
    """
    Open a short position on OANDA.

    Args:
        instrument (str): The trading instrument (e.g., "EUR_USD", "GBP_JPY").
        price (float): The entry price.
        stop_loss_price (float): The stop-loss price.
        take_profit_price (float): The take-profit price.
        risk_percent (float): The percentage of account balance to risk.
        trading_type (str): The trading type, either "practice" or "live".

    Returns:
        dict: The response from the OANDA API.
    """
    loc = "oanda.py:open_short_position"

    try:
        # Calculate the number of units to trade (negative for short positions)
        units = -await calculate_units(
            instrument=instrument,
            price=price,
            stop_loss_price=stop_loss_price,
            risk_percent=risk_percent,
            trading_type=trading_type,
        )

        # Retrieve credentials and price precision
        credentials = get_credentials(trading_type)
        price_decimals = await get_price_precision(instrument, trading_type)

        # Construct the API URL
        url = f"{get_base_url(trading_type)}/v3/accounts/{credentials['account_id']}/orders"

        # Construct the payload for the API request
        payload = {
            "order": {
                "type": "MARKET",
                "positionFill": "DEFAULT",
                "instrument": instrument,
                "units": f"{units}",
                "stopLossOnFill": {
                    "price": f"{stop_loss_price:.{price_decimals}f}",
                },
                "takeProfitOnFill": {
                    "price": f"{take_profit_price:.{price_decimals}f}",
                },
            }
        }

        # Debug mode: Log the payload instead of sending the request
        if DEBUG_MODE:
            logging.info(f"{get_datetime_now()} - OPEN SHORT POSITION:\n{json.dumps(payload, indent=2)}")
            logging.info(f"{loc}: Debug mode enabled. Order logged to server.log.")
            return {"status": "debug", "message": "Order logged to server.log"}

        # Send the API request
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {credentials['api_key']}",
                },
                json=payload,
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logging.exception(f"{loc}: Could not open short position: {e}")
        raise

async def close_short_position(instrument: str, trading_type: str = "practice") -> dict:
    """Close a short position on OANDA."""
    loc = "oanda.py:close_short_position"

    try:
        credentials = get_credentials(trading_type)

        url = f"{get_base_url(trading_type)}/v3/accounts/{credentials['account_id']}/positions/{instrument}/close"

        payload = {
            "shortUnits": "ALL",
        }

        if DEBUG_MODE:
            logging.info(f"{get_datetime_now()} - CLOSE SHORT POSITION:\n{json.dumps(payload, indent=2)}")
            logging.info(f"{loc}: Debug mode enabled. Order logged to server.log.")
            return {"status": "debug", "message": "Order logged to server.log"}

        async with httpx.AsyncClient() as client:
            response = await client.put(
                url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {credentials['api_key']}",
                },
                json=payload,
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logging.exception(f"{loc}: Could not close short position: {e}")
        raise

async def calculate_units(
    instrument: str,
    price: float,
    stop_loss_price: float,
    take_profit_price: float,
    risk_percent: float,
    trading_type: str = "practice",
    leverage: int = 50,  # Default leverage
) -> dict:
    """
    Calculate the number of units to trade based on risk management.

    Args:
        instrument (str): The trading instrument (e.g., "EUR_USD", "GBP_JPY").
        price (float): The entry price.
        stop_loss_price (float): The stop-loss price.
        take_profit_price (float): The take-profit price.
        risk_percent (float): The percentage of account balance to risk.
        trading_type (str): The trading type, either "practice" or "live".
        leverage (int): The leverage ratio (default is 50:1).

    Returns:
        dict: A dictionary containing units, margin, pip value, trade value, reward, and risk.
    """
    loc = "oanda.py:calculate_units"

    try:
        # Retrieve account balance
        account_balance = await get_account_balance(trading_type)

        # Calculate risk amount (e.g., 1% of account balance)
        risk_amount_gbp = account_balance * (risk_percent / 100)

        # Calculate stop-loss distance
        stop_loss_distance = abs(price - stop_loss_price)

        # Determine pip value
        pip_value = 0.0001 if "JPY" not in instrument else 0.01

        # Get the quote currency from the instrument (e.g., "USD" from "EUR_USD")
        quote_currency = instrument.split("_")[1]

        # Get the exchange rate for GBP/QUOTE
        exchange_rate = await get_gbp_exchange_rate(quote_currency, trading_type)

        # Adjust pip value for GBP
        if "JPY" in instrument:
            pip_value_in_gbp = pip_value * exchange_rate
        else:
            pip_value_in_gbp = pip_value / exchange_rate

        # Calculate the number of units
        units = int(risk_amount_gbp / (stop_loss_distance / pip_value_in_gbp))

        # Calculate margin (units / leverage)
        margin_gbp = (units * price) / leverage

        # Calculate trade value (units * price)
        trade_value_gbp = units * price

        # Calculate reward (take-profit distance * pip value * units)
        reward_gbp = abs(take_profit_price - price) * pip_value_in_gbp * units

        # Calculate risk (stop-loss distance * pip value * units)
        risk_gbp = stop_loss_distance * pip_value_in_gbp * units

        # Ensure units are positive
        if units <= 0:
            raise ValueError("Calculated units are zero or negative. Check stop-loss distance and account balance.")

        return {
            "units": units,
            "margin_gbp": margin_gbp,
            "pip_value_gbp": pip_value_in_gbp,
            "trade_value_gbp": trade_value_gbp,
            "reward_gbp": reward_gbp,
            "risk_gbp": risk_gbp,
        }
    except Exception as e:
        logging.exception(f"{loc}: Could not calculate units: {e}")
        raise

async def get_gbp_exchange_rate(quote_currency: str, trading_type: str = "practice") -> float:
    """
    Retrieve the midpoint exchange rate for GBP/QUOTE using OANDA's Pricing API.

    Args:
        quote_currency (str): The quote currency (e.g., "JPY" from "GBP_JPY").
        trading_type (str): The trading type, either "practice" or "live".

    Returns:
        float: The midpoint exchange rate for GBP/QUOTE.

    Raises:
        ValueError: If the instrument is not found in the pricing data.
        Exception: If there is an error retrieving the exchange rate.
    """
    loc = "oanda.py:get_gbp_exchange_rate"

    try:
        # Construct the instrument (e.g., GBP_JPY)
        instrument = f"GBP_{quote_currency}"

        # Retrieve credentials
        credentials = get_credentials(trading_type)

        # OANDA Pricing API URL
        url = f"{get_base_url(trading_type)}/v3/accounts/{credentials['account_id']}/pricing"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {credentials['api_key']}",
        }
        params = {
            "instruments": instrument  # e.g., "GBP_JPY"
        }

        # Make the API request
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            pricing_data = response.json()

            # Extract the midpoint price (average of bid and ask)
            prices = pricing_data["prices"]
            for price_data in prices:
                if price_data["instrument"] == instrument:
                    bid = float(price_data["bids"][0]["price"])
                    ask = float(price_data["asks"][0]["price"])
                    midpoint = (bid + ask) / 2
                    return midpoint

            # If the instrument is not found in the response
            raise ValueError(f"Instrument {instrument} not found in pricing data.")
    except Exception as e:
        logging.exception(f"{loc}: Could not retrieve exchange rate for GBP/{quote_currency}: {e}")
        raise
