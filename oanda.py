import datetime
import json
import logging
import os.path
import httpx  # Replaced requests with httpx for async support

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

def get_price_precision(instrument: str, trading_type: str = "practice") -> int:
    """Get the price precision for a given instrument."""
    price_precisions = get_price_precisions(trading_type)
    return price_precisions[instrument]

def get_price_precisions(trading_type: str = "practice") -> dict:
    """Retrieve or generate price precisions for instruments."""
    price_precisions_file = "price_precisions.json"

    if os.path.isfile(price_precisions_file):
        price_precisions = load_price_precisions(price_precisions_file)
    else:
        price_precisions = save_price_precisions(price_precisions_file, trading_type)

    return price_precisions

def save_price_precisions(price_precisions_file: str, trading_type: str = "practice") -> dict:
    """Save price precisions for instruments to a file."""
    instruments = get_instruments(trading_type)

    price_precisions = {instrument["name"]: instrument["displayPrecision"] for instrument in instruments["instruments"]}

    with open(price_precisions_file, "w") as price_precisions_json:
        json.dump(price_precisions, price_precisions_json, indent=2, sort_keys=True)

    return price_precisions

def load_price_precisions(price_precisions_file: str) -> dict:
    """Load price precisions for instruments from a file."""
    with open(price_precisions_file) as price_precisions_json:
        return json.load(price_precisions_json)

async def buy_order(
    instrument: str,
    price: float,
    stop_loss_price: float,
    risk_percent: float = 1.0,  # Risk as a percentage of account balance
    trading_type: str = "practice",
    **kwargs
) -> dict:
    """Place a buy order on OANDA with dynamic unit calculation."""
    loc = "oanda.py:buy_order"

    try:
        # Retrieve account balance
        account_balance = await get_account_balance(trading_type)

        # Calculate risk amount (1% of account balance)
        risk_amount = account_balance * (risk_percent / 100)

        # Calculate stop-loss distance
        stop_loss_distance = abs(price - stop_loss_price)

        # Get pip value and calculate units
        pip_value = 0.0001  # Default pip value for most forex pairs
        if "JPY" in instrument:  # Adjust pip value for JPY pairs
            pip_value = 0.01

        # Calculate the number of units to trade
        units = int(risk_amount / (stop_loss_distance / pip_value))

        # Ensure units are positive
        if units <= 0:
            raise ValueError("Calculated units are zero or negative. Check stop-loss distance and account balance.")

        credentials = get_credentials(trading_type)
        price_decimals = get_price_precision(instrument, trading_type)

        url = f"{get_base_url(trading_type)}/v3/accounts/{credentials['account_id']}/orders"

        payload = {
            "order": {
                "type": "LIMIT",
                "positionFill": "DEFAULT",
                "timeInForce": "GTD",
                "gtdTime": get_datetime_offset(15),
                "instrument": instrument,
                "units": f"{units}",
                "price": f"{price:.{price_decimals}f}",
                "stopLossOnFill": {
                    "price": f"{stop_loss_price:.{price_decimals}f}",
                },
            }
        }

        if DEBUG_MODE:
            logging.info(f"{get_datetime_now()} - BUY ORDER:\n{json.dumps(payload, indent=2)}")
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
        logging.exception(f"{loc}: Could not send the buy order to OANDA: {e}")
        raise

async def sell_order(instrument: str, trading_type: str, **kwargs) -> dict:
    """Close a position on OANDA."""
    loc = "oanda.py:sell_order"

    try:
        credentials = get_credentials(trading_type)

        url = f"{get_base_url(trading_type)}/v3/accounts/{credentials['account_id']}/positions/{instrument}/close"

        payload = {
            "longUnits": "ALL",
        }

        if DEBUG_MODE:
            # Log the payload to the centralized server.log
            logging.info(f"{get_datetime_now()} - SELL ORDER:\n{json.dumps(payload, indent=2)}")
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
        logging.exception(f"{loc}: Could not send the sell order to OANDA: {e}")
        raise

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

if __name__ == "__main__":
    # Set logging parameters
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("server.log"),
            logging.StreamHandler()
        ]
    )
    loc = "oanda.py"

    # Uncomment this bit to write all instruments and their price
    # precision—for the given trading type—to price_precisions.json, or
    # load them from that file if it exists
    # logging.info("{}: {}".format(loc, json.dumps(
    #     get_price_precisions(), indent=2, sort_keys=True)))

    # Uncomment this bit to send a buy order to OANDA
    order_response = buy_order(
        instrument="XAU_EUR",
        units=1, # i.e. 1 unit (bar?) of gold
        price=1486.891,
        trailing_stop_loss_percent=0.03, # as positive decimal
        take_profit_percent=0.06, # as positive decimal
        trading_type="practice"
    )

    logging.info("{}: {}".format(
        loc, json.dumps(order_response, indent=2, sort_keys=True)))
