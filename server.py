from copy import copy
import json
from json.decoder import JSONDecodeError
import logging
import ipaddress
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
import requests
from oanda import buy_order, sell_order, get_datetime_now

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

def post_data_to_oanda_parameters(post_data: dict):
    translated_data = translate(post_data)
    return fill_defaults(translated_data)

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
logging.basicConfig(level=logging.INFO)

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

# Allowed IPs
TRADINGVIEW_IPS = {"52.89.214.238", "34.212.75.30", "54.218.53.128", "52.32.178.7", "127.0.0.1", "::1"}
TRADINGVIEW_NETS = {ipaddress.ip_network("192.168.0.0/24")}

def ip_filter(remote_ip: str):
    try:
        ip_obj = ipaddress.ip_address(remote_ip)
    except ValueError:
        raise HTTPException(status_code=403, detail="403 Forbidden: Invalid IP")
    if remote_ip not in TRADINGVIEW_IPS and not any(ip_obj in net for net in TRADINGVIEW_NETS):
        raise HTTPException(status_code=403, detail="403 Forbidden: IP not allowed")

@app.post("/webhook/{token}")
async def webhook(token: str, request: Request):
    if token not in access_token:
        raise HTTPException(status_code=403, detail="403 Forbidden: Invalid token")

    remote_ip = request.client.host
    ip_filter(remote_ip)

    local_log = Log()

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

    # Translate & fill defaults
    try:
        oanda_parameters = post_data_to_oanda_parameters(copy(post_data))
    except Exception as e:
        msg = f"Could not translate data: {e}"
        logging.exception(msg)
        local_log.add(msg)
        send_discord_alert(f"❌ TradingView Data Error:\n```\n{msg}\n```")
        raise HTTPException(status_code=400, detail=str(local_log))

    local_log.add(f"OANDA parameters:\n{json.dumps(oanda_parameters, indent=2)}")

    # Place order
    try:
        if post_data["action"] == "buy":
            order_response = buy_order(**oanda_parameters)
            alert_msg = f"✅ Placed BUY order: {oanda_parameters['units']} {oanda_parameters['instrument']}"
        elif post_data["action"] == "sell":
            order_response = sell_order(**oanda_parameters)
            alert_msg = f"✅ Placed SELL order: {oanda_parameters['instrument']}"
        else:
            raise ValueError("Action must be 'buy' or 'sell'")
    except Exception as e:
        msg = f"Error sending order to OANDA: {e}"
        logging.exception(msg)
        local_log.add(msg)
        send_discord_alert(f"❌ OANDA Order Error:\n```\n{msg}\n```")
        raise HTTPException(status_code=500, detail=str(local_log))

    local_log.add("Order sent successfully")
    send_discord_alert(alert_msg)

    return JSONResponse(content={"log": str(local_log)}, status_code=200)