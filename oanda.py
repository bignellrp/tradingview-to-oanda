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
        # Log the purpose of the API call
        logging.info(f"{loc}: [GET_ACCOUNTS_LIST] Making API call to {url}")

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
        # Log the purpose of the API call
        logging.info(f"{loc}: [GET_INSTRUMENTS_LIST] Making API call to {url}")

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

async def get_account_balance(trading_type: str = "practice") -> dict:  # Defaults to practice
    """
    Retrieve the account balance and leverage from OANDA.

    Args:
        trading_type (str): The trading type, either "practice" or "live".

    Returns:
        dict: A dictionary containing the account balance, leverage, and currency.
    """
    loc = "oanda.py:get_account_balance"

    try:
        credentials = get_credentials(trading_type)

        url = f"{get_base_url(trading_type)}/v3/accounts/{credentials['account_id']}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {credentials['api_key']}",
        }

        # Log the purpose of the API call
        logging.info(f"{loc}: [GET_ACCOUNT_BALANCE] Making API call to {url}")

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            account_data = response.json()

            # Debug log the full response for troubleshooting
            logging.debug(f"{loc}: API response: {json.dumps(account_data, indent=2)}")

            # Extract balance, leverage, and currency
            balance = float(account_data["account"]["balance"])
            margin_rate = float(account_data["account"]["marginRate"])  # Margin rate is in decimal format
            leverage = int(1 / margin_rate)  # Calculate leverage ratio (e.g., 1 / 0.03333333333333 = 30)
            currency = account_data["account"].get("currency")  # Safely retrieve currency

            if not currency:
                raise ValueError(f"{loc}: 'currency' field is missing in the API response.")

            return {
                "balance": balance,
                "leverage": leverage,
                "currency": currency,
            }
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
        # Check if any position is already open
        if await check_any_position_open(trading_type):
            raise ValueError(f"{loc}: A position is already open. Only one trade is allowed at a time.")

        # Calculate the number of units to trade
        trade_details = await calculate_units(
            instrument=instrument,
            price=price,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            risk_percent=risk_percent,
            trading_type=trading_type,
        )
        units = trade_details["units"]

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

        logging.info(f"{get_datetime_now()} - OPEN LONG POSITION:\n{json.dumps(payload, indent=2)}")
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
    """Open a short position on OANDA."""
    loc = "oanda.py:open_short_position"

    try:
        # Check if any position is already open
        if await check_any_position_open(trading_type):
            raise ValueError(f"{loc}: A position is already open. Only one trade is allowed at a time.")

        # Calculate the number of units to trade
        trade_details = await calculate_units(
            instrument=instrument,
            price=price,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            risk_percent=risk_percent,
            trading_type=trading_type,
        )
        units = -trade_details["units"]  # Negate only the units value for short positions

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
            logging.info(f"{get_datetime_now()} - OPEN SHORT POSITION:\n{json.dumps(payload, indent=2)}")
            logging.info(f"{loc}: Debug mode enabled. Order logged to server.log.")
            return {"status": "debug", "message": "Order logged to server.log"}

        logging.info(f"{get_datetime_now()} - OPEN SHORT POSITION:\n{json.dumps(payload, indent=2)}")
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
    stop_loss_price: float = None,
    take_profit_price: float = None,
    risk_percent: int = 100,
    trading_type: str = "practice",
) -> dict:
    """
    Calculate the number of units to trade based on risk management.

    Args:
        instrument (str): The trading instrument (e.g., "EUR_USD", "GBP_JPY").
        price (float): The entry price.
        stop_loss_price (float): The stop-loss price (optional).
        take_profit_price (float): The take-profit price (optional).
        risk_percent (int): The percentage of account balance to risk.
        trading_type (str): The trading type, either "practice" or "live".

    Returns:
        dict: A dictionary containing units, margin, pip value, trade value, reward, risk, and account balance.
    """
    loc = "oanda.py:calculate_units"

    try:
        # Retrieve account balance and leverage
        account_data = await get_account_balance(trading_type)
        account_balance = account_data["balance"]
        leverage = account_data["leverage"]
        account_currency = account_data["currency"]

        # Convert account balance to target currency if necessary
        quote_currency = instrument.split("_")[1]
        if quote_currency != account_currency:
            exchange_rate = await get_accountcurrency_exchange_rate(quote_currency, trading_type)
            account_balance_converted = account_balance * exchange_rate
        else:
            account_balance_converted = account_balance

        # Calculate risk amount (e.g., 1% of account balance)
        risk_amount = account_balance_converted * (risk_percent / 100)
        print(f"Risk Amount: {risk_amount}")

        # Determine pip value
        pip_value = 0.0001 if "JPY" not in instrument else 0.01

        # Calculate stop-loss distance in pips
        stop_loss_distance = abs(price - stop_loss_price) / pip_value if stop_loss_price else None
        take_profit_distance = abs(take_profit_price - price) / pip_value if take_profit_price else None
        
        print(f"Stop Loss Distance in Pips: {stop_loss_distance}")
        print(f"Take Profit Distance in Pips: {take_profit_distance}")

        # Calculate the number of units
        units = int(risk_amount / (stop_loss_distance * pip_value)) if stop_loss_distance else 0

        # Calculate margin (units / leverage)
        margin = (units * price) / leverage

        # Calculate trade value (units * price)
        trade_value = units * price

        # Calculate reward percentage (take-profit distance * pip value * units / account_balance_converted * 100) if take_profit_price is provided
        reward = take_profit_distance * pip_value * units / account_balance_converted * 100 if take_profit_price else None

        # Calculate risk percentage (stop-loss distance * pip value * units / account_balance_converted * 100) if stop_loss_price is provided
        risk = stop_loss_distance * pip_value * units / account_balance_converted * 100 if stop_loss_price else None

        pip_value_quote_currency = pip_value * units if quote_currency != account_currency else pip_value

        # Debug log intermediate values
        logging.debug(f"{loc}: Account Balance: {account_balance}")
        logging.debug(f"{loc}: Risk Amount: {risk_amount}")
        logging.debug(f"{loc}: Stop Loss Distance: {stop_loss_distance}")
        logging.debug(f"{loc}: Take Profit Distance: {take_profit_distance}")
        logging.debug(f"{loc}: Pip Value: {pip_value}")
        logging.debug(f"{loc}: Units: {units}")

        # Ensure units are positive
        if units <= 0:
            raise ValueError("Calculated units are zero or negative. Check stop-loss distance and account balance.")

        return {
            "units": units,
            "margin": margin,
            "pip_value": pip_value_quote_currency,
            "trade_value": trade_value,
            "reward": reward,
            "risk": risk,
            "account_balance_converted": account_balance_converted,  # Include converted account balance
            "account_balance_original": account_balance,  # Include original account balance
        }
    except Exception as e:
        logging.exception(f"{loc}: Could not calculate units: {e}")
        raise

async def get_accountcurrency_exchange_rate(quote_currency: str, trading_type: str = "practice") -> float:
    """
    Retrieve the midpoint exchange rate for ACCOUNT_CURRENCY/QUOTE using OANDA's Pricing API.

    Args:
        quote_currency (str): The quote currency (e.g., "JPY" from "USD_JPY").
        trading_type (str): The trading type, either "practice" or "live".

    Returns:
        float: The midpoint exchange rate for ACCOUNT_CURRENCY/QUOTE.
    """
    loc = "oanda.py:get_accountcurrency_exchange_rate"

    try:
        # Retrieve account currency from get_account_balance
        account_data = await get_account_balance(trading_type)
        account_currency = account_data["currency"]

        # Construct the instrument (e.g., USD_JPY or GBP_JPY)
        instrument = f"{account_currency}_{quote_currency}"

        # Retrieve credentials
        credentials = get_credentials(trading_type)

        # OANDA Pricing API URL
        url = f"{get_base_url(trading_type)}/v3/accounts/{credentials['account_id']}/pricing"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {credentials['api_key']}",
        }
        params = {
            "instruments": instrument  # e.g., "USD_JPY" or "GBP_JPY"
        }

        # Log the purpose of the API call
        logging.info(f"{loc}: [GET_EXCHANGE_RATE] Making API call to {url} with params {params}")

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
        logging.exception(f"{loc}: Could not retrieve exchange rate for {account_currency}/{quote_currency}: {e}")
        raise

async def get_open_positions(trading_type: str = "practice") -> dict:
    """
    Retrieve all open positions for the account.

    Args:
        trading_type (str): The trading type, either "practice" or "live".

    Returns:
        dict: A dictionary containing all open positions.
    """
    loc = "oanda.py:get_open_positions"

    try:
        credentials = get_credentials(trading_type)

        url = f"{get_base_url(trading_type)}/v3/accounts/{credentials['account_id']}/openPositions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {credentials['api_key']}",
        }

        # Log the purpose of the API call
        logging.info(f"{loc}: [GET_OPEN_POSITIONS] Making API call to {url}")

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            positions_data = response.json()

            # Debug log the positions data
            logging.debug(f"{loc}: Open positions response: {json.dumps(positions_data, indent=2)}")

            return positions_data
    except Exception as e:
        logging.exception(f"{loc}: Could not retrieve open positions: {e}")
        raise

async def check_position_open(instrument: str, trading_type: str = "practice") -> bool:
    """
    Check if a position is already open for the given instrument.

    Args:
        instrument (str): The trading instrument (e.g., "EUR_USD").
        trading_type (str): The trading type, either "practice" or "live".

    Returns:
        bool: True if a position is open for the instrument, False otherwise.
    """
    loc = "oanda.py:check_position_open"

    try:
        positions_data = await get_open_positions(trading_type)

        # Check if the instrument exists in the open positions
        for position in positions_data.get("positions", []):
            if position["instrument"] == instrument:
                logging.info(f"{loc}: Position already open for instrument: {instrument}")
                return True

        return False
    except Exception as e:
        logging.exception(f"{loc}: Could not check if position is open: {e}")
        raise

async def check_any_position_open(trading_type: str = "practice") -> bool:
    """
    Check if any position is already open for the account.

    Args:
        trading_type (str): The trading type, either "practice" or "live".

    Returns:
        bool: True if any position is open, False otherwise.
    """
    loc = "oanda.py:check_any_position_open"

    try:
        positions_data = await get_open_positions(trading_type)

        # Check if there are any open positions
        if positions_data.get("positions"):
            logging.info(f"{loc}: A position is already open.")
            return True

        return False
    except Exception as e:
        logging.exception(f"{loc}: Could not check if any position is open: {e}")
        raise
