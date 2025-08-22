import json
from json.decoder import JSONDecodeError
import logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import requests
from oanda import (
    get_datetime_now,
    get_account_balance,
    open_long_position,
    close_long_position,
    open_short_position,
    close_short_position,
    calculate_units,
)
from gspread_logging import log_trade  # Import the log_trade function
import os
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# Initialize FastAPI app
app = FastAPI()

# Load Discord webhook URL from file
try:
    with open("discord_webhook.json") as f:
        webhook_data = json.load(f)
        DISCORD_WEBHOOK_URL = webhook_data.get("url")
        if not DISCORD_WEBHOOK_URL:
            raise ValueError("Webhook URL is missing or empty")
except (FileNotFoundError, KeyError, JSONDecodeError, ValueError):
    DISCORD_WEBHOOK_URL = None
    logging.warning("Discord webhook URL not found or invalid — alerts will not be sent")

def send_discord_alert(message: str):
    """Send a message to the configured Discord webhook."""
    if not DISCORD_WEBHOOK_URL:
        logging.info("Discord webhook is not configured, skipping alert")
        return
    try:
        payload = {"content": message}
        r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
        r.raise_for_status()
    except Exception as e:
        logging.error(f"Failed to send Discord alert: {e}")

def fill_defaults(post_data: dict):
    try:
        instrument = post_data["instrument"]
        price = float(post_data["price"])
    except KeyError as e:
        logging.exception(f"Missing required parameter: {e}")
        raise HTTPException(status_code=400, detail=f"Missing required parameter: {e}")

    return {
        "instrument": instrument,
        "units": int(post_data.get("units", 500)),
        "price": price,
        "trailing_stop_loss_percent": float(post_data.get("trailing_stop_loss_percent", 0.01)),
        "take_profit_percent": float(post_data.get("take_profit_percent", 0.06)),
        "trading_type": post_data.get("trading_type", "practice"),
    }

def translate(post_data: dict):
    ticker = post_data.pop("ticker", None)
    if not ticker or len(ticker) != 6:
        raise HTTPException(status_code=400, detail="Invalid or missing ticker")
    post_data["instrument"] = f"{ticker[:3]}_{ticker[3:]}"
    return post_data

async def post_data_to_oanda_parameters(post_data: dict):
    """Translate and fill defaults, including dynamic unit calculation."""
    translated_data = translate(post_data)
    filled_data = fill_defaults(translated_data)

    # Calculate units and trade details dynamically using oanda.py
    try:
        trade_details = await calculate_units(
            instrument=filled_data["instrument"],
            price=filled_data["price"],
            stop_loss_price=float(post_data.get("stop_loss_price")),
            take_profit_price=float(post_data.get("take_profit_price")),
            risk_percent=1.0,  # 1% risk
            trading_type=filled_data["trading_type"],
        )
        filled_data.update(trade_details)  # Add trade details to filled_data
    except Exception as e:
        logging.exception(f"Error calculating trade details: {e}")
        raise HTTPException(status_code=400, detail=f"Error calculating trade details: {e}")

    return filled_data

class Log:
    def __init__(self):
        self.content = ""
    def __str__(self):
        return str(self.content)
    def add(self, message: str):
        if self.content:
            self.content += "\n"
        self.content += f"{get_datetime_now()}: {message}"

# Logging
logging.basicConfig(
    level=logging.INFO,  # Set the logging level
    format="%(asctime)s - %(levelname)s - %(message)s",  # Log format
    handlers=[
        logging.FileHandler("server.log"),  # Log to a file named 'server.log'
        logging.StreamHandler()  # Also log to the console
    ]
)

# Access tokens
try:
    with open("access_token.json") as f:
        access_token = json.load(f)
except FileNotFoundError:
    logging.error(
        "The file 'access_token.json' was not found. Please refer to the README.md "
        "for instructions on creating 'access_token.json' and 'credentials.json'."
    )
    raise SystemExit("Missing 'access_token.json'. Exiting.")
except JSONDecodeError as e:
    logging.error(
        f"Could not parse 'access_token.json': {e}. Please ensure the file is valid JSON."
    )
    raise SystemExit("Invalid 'access_token.json'. Exiting.")

# Hardcoded TradingView IPs
TRADINGVIEW_IPS = {
    "52.89.214.238",
    "34.212.75.30",
    "54.218.53.128",
    "52.32.178.7",
}

# Load additional IPs from access-list.json if it exists
access_list_file = "access_list.json"
if os.path.exists(access_list_file):
    try:
        with open(access_list_file, "r") as f:
            additional_ips = json.load(f)
            if isinstance(additional_ips, list):
                TRADINGVIEW_IPS.update(additional_ips)
                logging.info(f"Loaded additional IPs from {access_list_file}: {additional_ips}")
            else:
                logging.warning(f"{access_list_file} does not contain a valid list of IPs.")
    except Exception as e:
        logging.error(f"Error loading {access_list_file}: {e}")

class RestrictAccessMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # Allow only the /webhook/{token} endpoint
        if not request.url.path.startswith("/webhook/"):
            return JSONResponse(
                content={"detail": "Access denied"},
                status_code=403
            )

        # Validate client IP
        client_ip = request.headers.get("X-Real-IP") or request.headers.get("X-Forwarded-For")
        if not client_ip or client_ip not in TRADINGVIEW_IPS:
            logging.warning(f"Unauthorized access attempt from IP: {client_ip}")
            return JSONResponse(
                content={"detail": "Forbidden: Unauthorized IP address"},
                status_code=403
            )

        return await call_next(request)

# Add the middleware to the FastAPI app
app.add_middleware(RestrictAccessMiddleware)

@app.post("/webhook/{token}")
async def webhook(token: str, request: Request):
    if token not in access_token:
        raise HTTPException(status_code=403, detail="403 Forbidden: Invalid token")

    local_log = Log()

    # Extract client IP from headers
    client_ip = request.headers.get("X-Real-IP") or request.headers.get("X-Forwarded-For")
    if not client_ip:
        logging.error("Client IP is missing from headers.")
        raise HTTPException(status_code=400, detail="Client IP is missing from headers.")

    # Validate client IP
    if client_ip not in TRADINGVIEW_IPS:
        logging.warning(f"Unauthorized access attempt from IP: {client_ip}")
        raise HTTPException(status_code=403, detail="Forbidden: Unauthorized IP address.")

    logging.info(f"Authorized request from IP: {client_ip}")
    local_log.add(f"Client IP: {client_ip}")

    # Load JSON
    try:
        post_data = await request.json()
        if not post_data:
            raise JSONDecodeError("Empty JSON body", "", 0)
    except JSONDecodeError as e:
        msg = f"Invalid JSON: {e}"
        logging.exception(msg)
        local_log.add(msg)
        send_discord_alert(f"❌ TradingView Webhook Error:\n```\n{msg}\n```")
        raise HTTPException(status_code=400, detail=str(local_log))

    local_log.add(f"Received valid JSON:\n{json.dumps(post_data, indent=2)}")

    # Extract and verify ID
    id_number = post_data.get("id")
    if not id_number:
        msg = "Missing 'id' in JSON payload."
        logging.error(msg)
        local_log.add(msg)
        raise HTTPException(status_code=400, detail=msg)

    local_log.add(f"ID number: {id_number}")

    # Translate & fill defaults
    try:
        oanda_parameters = await post_data_to_oanda_parameters(post_data)
    except Exception as e:
        msg = f"Could not translate data: {e}"
        logging.exception(msg)
        local_log.add(msg)
        send_discord_alert(f"❌ TradingView Data Error:\n```\n{msg}\n```")
        raise HTTPException(status_code=400, detail=str(local_log))

    local_log.add(f"OANDA parameters:\n{json.dumps(oanda_parameters, indent=2)}")

    # Calculate units and trade details
    try:
        trade_details = await calculate_units(
            instrument=oanda_parameters["instrument"],
            price=oanda_parameters["price"],
            stop_loss_price=post_data["stop_loss_price"],
            take_profit_price=post_data["take_profit_price"],
            risk_percent=1.0,
            trading_type=oanda_parameters["trading_type"],
        )
        oanda_parameters["units"] = trade_details["units"]
    except Exception as e:
        msg = f"Error calculating trade details: {e}"
        logging.exception(msg)
        local_log.add(msg)
        raise HTTPException(status_code=400, detail=str(local_log))

    local_log.add(f"Trade details:\n{json.dumps(trade_details, indent=2)}")

    # Place order
    try:
        if post_data["action"] == "open_long":
            order_response = await open_long_position(
                instrument=oanda_parameters["instrument"],
                price=oanda_parameters["price"],
                stop_loss_price=post_data["stop_loss_price"],
                take_profit_price=post_data["take_profit_price"],
                trading_type=oanda_parameters["trading_type"],
            )
            alert_msg = f"✅ Opened LONG position for {oanda_parameters['instrument']}"
            log_trade(
                action="open_long",
                instrument=oanda_parameters["instrument"],
                price=oanda_parameters["price"],
                stop_loss_price=post_data["stop_loss_price"],
                take_profit_price=post_data["take_profit_price"],
                units=oanda_parameters["units"],
                trading_type=oanda_parameters["trading_type"],
                status="success",
                account_balance=await get_account_balance(oanda_parameters["trading_type"]),
                id_number=id_number,
                margin_gbp=trade_details["margin_gbp"],
                pip_value_gbp=trade_details["pip_value_gbp"],
                trade_value_gbp=trade_details["trade_value_gbp"],
                reward_gbp=trade_details["reward_gbp"],
                risk_gbp=trade_details["risk_gbp"],
            )
        elif post_data["action"] == "close_long":
            order_response = await close_long_position(
                oanda_parameters["instrument"],
                oanda_parameters["trading_type"]
            )
            alert_msg = f"✅ Closed LONG position for {oanda_parameters['instrument']}"
            log_trade(
                action="close_long",
                instrument=oanda_parameters["instrument"],
                price=None,
                stop_loss_price=None,
                take_profit_price=None,
                units=None,
                trading_type=oanda_parameters["trading_type"],
                status="success",
                account_balance=await get_account_balance(oanda_parameters["trading_type"]),
                id_number=id_number,
            )
        elif post_data["action"] == "open_short":
            order_response = await open_short_position(
                instrument=oanda_parameters["instrument"],
                price=oanda_parameters["price"],
                stop_loss_price=post_data["stop_loss_price"],
                take_profit_price=post_data["take_profit_price"],
                trading_type=oanda_parameters["trading_type"],
            )
            alert_msg = f"✅ Opened SHORT position for {oanda_parameters['instrument']}"
            log_trade(
                action="open_short",
                instrument=oanda_parameters["instrument"],
                price=oanda_parameters["price"],
                stop_loss_price=post_data["stop_loss_price"],
                take_profit_price=post_data["take_profit_price"],
                units=oanda_parameters["units"],
                trading_type=oanda_parameters["trading_type"],
                status="success",
                account_balance=await get_account_balance(oanda_parameters["trading_type"]),
                id_number=id_number,
                margin_gbp=trade_details["margin_gbp"],
                pip_value_gbp=trade_details["pip_value_gbp"],
                trade_value_gbp=trade_details["trade_value_gbp"],
                reward_gbp=trade_details["reward_gbp"],
                risk_gbp=trade_details["risk_gbp"],
            )
        elif post_data["action"] == "close_short":
            order_response = await close_short_position(
                oanda_parameters["instrument"],
                oanda_parameters["trading_type"]
            )
            alert_msg = f"✅ Closed SHORT position for {oanda_parameters['instrument']}"
            log_trade(
                action="close_short",
                instrument=oanda_parameters["instrument"],
                price=None,
                stop_loss_price=None,
                take_profit_price=None,
                units=None,
                trading_type=oanda_parameters["trading_type"],
                status="success",
                account_balance=await get_account_balance(oanda_parameters["trading_type"]),
                id_number=id_number,
            )
        else:
            raise ValueError("Action must be 'open_long', 'close_long', 'open_short' or 'close_short'")
    except Exception as e:
        msg = f"Error sending order to OANDA: {e}"
        logging.exception(msg)
        local_log.add(msg)
        send_discord_alert(f"❌ OANDA Order Error:\n```\n{msg}\n```")
        log_trade(
            action=post_data["action"],
            instrument=oanda_parameters.get("instrument"),
            price=oanda_parameters.get("price"),
            stop_loss_price=post_data.get("stop_loss_price"),
            take_profit_price=post_data.get("take_profit_price"),
            units=oanda_parameters.get("units"),
            trading_type=oanda_parameters.get("trading_type"),
            status="error",
            account_balance=None,  # Log None if an error occurs
            id_number=id_number,
            margin_gbp=trade_details["margin_gbp"],
            pip_value_gbp=trade_details["pip_value_gbp"],
            trade_value_gbp=trade_details["trade_value_gbp"],
            reward_gbp=trade_details["reward_gbp"],
            risk_gbp=trade_details["risk_gbp"],
        )
        raise HTTPException(status_code=500, detail=str(local_log))

    local_log.add("Order sent successfully")
    send_discord_alert(alert_msg)

    # Return the response
    return JSONResponse(content={"log": str(local_log)}, status_code=200)