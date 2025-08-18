# TradingView to OANDA

## Summary
I'm setting up a bot which listens to TradingView alerts on a URL (i.e. webhook) and posts orders (and sets stop-losses, etc.) on OANDA through their API

## Things to consider
* A sell order isn't actually handled as a sell order, but as closing all open positions for the given `instrument`.
  * Note that if this signal is sent to OANDA when the markets are closed, it will be cancelled.
* A buy order is handled as a limit order with a Good-Til-Date 15 minutes in the future.
  * That means that if it is sent when the markets are closed, it will most likely cancel (unless of course the markets open within those 15 minutes)

## Supported parameters
### Required parameters
* `action` either `buy` or `sell`
* `ticker` a six-letter ticker without any separator (e.g. `EURUSD`)
* `close` the price you want to buy the instrument at (ignored for sells, see [Things to consider](#things-to-consider))
### Optional parameters and their defaults
* `units` the size of the position to open as a positive integer, in the currency of the instrument (e.g. in Euros for "EURUSD" or gold for "XAUEUR"). Defaults to `500`
* `trailing_stop_loss_percent` the percentage points below `close` on which to start the trailing stop loss as a positive decimal. (E.g. to set it 5% below, enter `0.05`.) Defaults to `0.01`, i.e. 1%. See [OANDA's documentation on trailing stops](https://www1.oanda.com/forex-trading/learn/capital-management/stop-loss) for more information.
* `take_profit_percent` the percentage points above `close` to set the take profit at as a positive decimal. When the market reaches this point, the position is automatically closed. Defaults to `0.06`, i.e. 6%
* `trading_type` either `live` or `practice`, used to select the respective API key and account ID from your `credentials.json` file. Defaults to `practice`
Any other parameters will not be handled, but are sent along. That means you will see them in your server logs.

## Prerequisites
* `pip install -r requirements.txt`
* Oanda `credentials.json` file
* Access token `access_token.json
* Optional: Discord webhook for messages `discord_webhook.json`

## Credentials

```json
{
  "oanda_practice": {
    "api_key": "<YOUR PRACTICE ACCOUNT API KEY>",
    "account_id": "<YOUR PRACTICE ACCOUNT ID>"
  },
  "oanda_live": {
    "api_key": "<YOUR LIVE ACCOUNT API KEY>",
    "account_id": "<YOUR LIVE ACCOUNT ID>"
  }
}
```

## Authentication
The webhook is only available on `/webhook/<ACCESS_TOKEN>` where `<ACCESS_TOKEN>` is one of the items in the JSON list in `access_token.json`. Create that file with the following contents:

```json
[
  "<ACCESS_TOKEN>"
]
```

Make sure to replace `<ACCESS_TOKEN>` with an access token of your choice (e.g. [have DuckDuckGo generate one for you](https://duckduckgo.com/?q=password+64))

Note that these are the only valid endpoints. The server won't tell you anything if you're trying to reach it somewhere else.

## Messages
Create a [discord webhook](https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks) to receive messages from trading-bot

```json
{
  "url": "<DISCORD_WEBHOOK>"
}
```

## Access List
The bot has been hardcoded with the [TradingView public ips](https://www.tradingview.com/support/solutions/43000529348-about-webhooks/)
To add additional Ips for testing create the following access_list.json

```json
[
    "<YOUR_PUBLIC_IP>"
]
```

## Run the server
Server has been converted to use fast-api for async support, security and speed.
To run the server use uvicorn:

(Remove the --reload in production, its used in development to autoreload after code changes)

```
uvicorn server:app --host 0.0.0.0 --port 8080 --reload
```

## Optional: Run Uvicorn as a Service on Ubuntu
To ensure your FastAPI application runs continuously and starts automatically on system boot, you can configure it as a systemd service.

Create a Systemd Service File
Create a new service file for your application:

```
sudo vi /etc/systemd/system/tradingview-to-oanda.service
```

```
[Unit]
Description=FastAPI application for TradingView to OANDA
After=network.target

[Service]
User=<YOUR_USER>
Group=<YOUR_GROUP>
WorkingDirectory=/home/<YOUR_USER>/tradingview-to-oanda
ExecStart=/home/<YOUR_USER>/tradingview-to-oanda/venv/bin/uvicorn server:app --host 0.0.0.0 --port 8080
Environment="PYTHONUNBUFFERED=1"
Restart=always
StandardOutput=append:/home/<YOUR_USER>/tradingview-to-oanda/server.log
StandardError=append:/home/<YOUR_USER>/tradingview-to-oanda/server.log

[Install]
WantedBy=multi-user.target
```

Reload the daemon and start the service.

```
sudo systemctl daemon-reload
sudo systemctl start tradingview-to-oanda
sudo systemctl enable tradingview-to-oanda
sudo systemctl status tradingview-to-oanda
sudo journalctl -u tradingview-to-oanda
```


## Add alerts to TradingView
1. Add an alert to whatever condition you want, for example [a custom-built `study`](https://www.tradingview.com/pine-script-docs/en/v4/annotations/Alert_conditions.html)
1. Check the __Webhook URL__ box and paste the URL of your PythonAnywhere webhook including access token
1. Make sure that the __Message__ is a valid JSON containing at least:
  ```json
  {"action":"buy","ticker":"{{ticker}}","close":{{close}}}
  ```
  Note:
  * The server is built in such a way that what TradingView sends as `{{ticker}}` is translated to what OANDA expects as `instrument` and `close` is translated to `price`
  * If you want to sell every position you have for this ticker, use "`sell`" as `action`
