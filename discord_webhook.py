import json
import logging
import httpx  # Use httpx for asynchronous HTTP requests
import aiofiles  # Use aiofiles for asynchronous file I/O
from json.decoder import JSONDecodeError

# Load Discord webhook URL from file asynchronously
async def load_discord_webhook():
    """Load the Discord webhook URL from discord_webhook.json asynchronously."""
    try:
        async with aiofiles.open("discord_webhook.json", mode="r") as f:
            webhook_data = json.loads(await f.read())
            webhook_url = webhook_data.get("url")
            if not webhook_url:
                raise ValueError("Webhook URL is missing or empty")
            return webhook_url
    except (FileNotFoundError, KeyError, JSONDecodeError, ValueError):
        logging.warning("Discord webhook URL not found or invalid — alerts will not be sent")
        return None

# Send Discord alert asynchronously
async def send_discord_alert(message: str):
    """Send a message to the configured Discord webhook asynchronously."""
    webhook_url = await load_discord_webhook()  # Use the async version of load_discord_webhook
    if not webhook_url:
        logging.info("Discord webhook is not configured, logging locally instead")
        logging.info(f"Discord alert (local): {message}")
        return
    try:
        payload = {"content": message}
        async with httpx.AsyncClient() as client:
            response = await client.post(webhook_url, json=payload, timeout=5)
            response.raise_for_status()
            logging.info("Discord alert sent successfully")
    except httpx.RequestError as e:
        logging.error(f"Failed to send Discord alert: {e}")