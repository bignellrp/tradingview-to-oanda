# TradingView to OANDA

## Summary
This is a bot which listens to TradingView alerts on a URL (i.e. webhook) and posts orders (and sets stop-losses, etc.) on OANDA through their API. It can be run on a linux vm or container but consider security, speed and resiliency as this bot deals with financial trading.

---

## Disclaimer
**Use this bot at your own risk.**  
Carefully monitor its activity, review the logs, and fully understand the code before using it with real funds. It is strongly recommended to run the bot in practice mode on a demo account for an extended period to ensure it behaves as expected. The author assumes no responsibility for any financial losses caused by the bot, whether due to bugs, trade execution failures, or flawed trading strategies.

---

## Key Features
- **Position Management**: Supports opening and closing long and short positions.
- **Dynamic Risk Management**: Automatically calculates position size (`units`) based on 1% of the account balance and the stop-loss distance.
- **Webhook Integration**: Listens for TradingView alerts and processes them in real-time.
- **Secure and Scalable**: Built with FastAPI for asynchronous processing and designed to run behind a reverse proxy (e.g., Nginx).

---

## Things to consider
* A `close_long` or `close_short` order will close all open positions for the given `instrument` on the respective side (long or short).
  * Note that if this signal is sent to OANDA when the markets are closed, it will be cancelled.
* An `open_long` or `open_short` order is handled as a limit order with a Good-Til-Date 15 minutes in the future.
  * That means that if it is sent when the markets are closed, it will most likely cancel (unless of course the markets open within those 15 minutes).

---

## Supported parameters
### Required parameters
* `action`: One of the following:
  * `open_long`: Open a long position.
  * `close_long`: Close all long positions for the given instrument.
  * `open_short`: Open a short position.
  * `close_short`: Close all short positions for the given instrument.
* `ticker`: A six-letter ticker without any separator (e.g., `EURUSD`).
* `price`: The price you want to buy or sell the instrument at (ignored for `close_long` and `close_short` actions).

### Optional parameters and their defaults
* `stop_loss_price`: The absolute price at which to set the stop-loss. Required for `open_long` and `open_short`.
* `take_profit_price`: The absolute price at which to set the take-profit. Required for `open_long` and `open_short`.
* `trading_type`: Either `live` or `practice`, used to select the respective API key and account ID from your `credentials.json` file. Defaults to `practice`.

### Ignored parameters
* `units`: The size of the position is calculated automatically based on 1% of the account balance and the stop-loss distance. If `units` is provided in the JSON payload, it will be ignored.

---

## Prerequisites
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Create the following configuration files:
   - **`credentials.json`**: Contains OANDA API keys and account IDs.
   - **`access_token.json`**: Contains the access tokens for webhook authentication.
   - **`discord_webhook.json`** (optional): For receiving bot notifications via Discord.

---

## Configuration

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

Make sure to replace `<ACCESS_TOKEN>` with an access token of your choice (e.g. [have DuckDuckGo generate one for you](https://duckduckgo.com/?q=password+64)).

Note that these are the only valid endpoints. The server won't respond to requests made to other endpoints.

---

### Discord Notifications (Optional)
To receive notifications via Discord, create a [Discord webhook](https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks) to receive messages from the trading bot:

```json
{
  "url": "<DISCORD_WEBHOOK>"
}
```

---

## Access List
The bot has been hardcoded with the [TradingView public IPs](https://www.tradingview.com/support/solutions/43000529348-about-webhooks/).
To add additional IPs for testing, create the following `access_list.json` file:

```json
[
    "<YOUR_PUBLIC_IP>"
]
```

---

## Running the Server

### Development Mode
To run the server in development mode with auto-reloading enabled:
```bash
uvicorn server:app --host 0.0.0.0 --port 8080 --reload
```

### Production Mode
For production, remove the `--reload` flag and consider running Uvicorn as a systemd service for reliability.

#### Example Systemd Service Configuration
Create a service file at `/etc/systemd/system/tradingview-to-oanda.service`:

```ini
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

Reload the daemon and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl start tradingview-to-oanda
sudo systemctl enable tradingview-to-oanda
```

---

## TradingView Alerts

### Adding Alerts
1. Create an alert in TradingView for your desired condition.
2. Enable the **Webhook URL** option and paste the webhook URL, including the access token.
3. Use a valid JSON message in the alert, such as:

   ```json
   {
     "action": "open_long",
     "ticker": "{{ticker}}",
     "price": {{close}},
     "stop_loss_price": 1.12000,
     "take_profit_price": 1.13000
   }
   ```

---

## Example Alerts

### Open a Long Position
To open a long position, the JSON payload should include the following parameters:

```json
{
  "action": "open_long",
  "ticker": "EURUSD",
  "price": 1.12345,
  "stop_loss_price": 1.12000,
  "take_profit_price": 1.13000,
  "trading_type": "practice"
}
```

---

### Close a Long Position
To close all long positions for a specific instrument, the JSON payload should include:

```json
{
  "action": "close_long",
  "ticker": "EURUSD",
  "trading_type": "practice"
}
```

---

### Open a Short Position
To open a short position, the JSON payload should include the following parameters:

```json
{
  "action": "open_short",
  "ticker": "EURUSD",
  "price": 1.12345,
  "stop_loss_price": 1.12600,
  "take_profit_price": 1.12000,
  "trading_type": "practice"
}
```

---

### Close a Short Position
To close all short positions for a specific instrument, the JSON payload should include:

```json
{
  "action": "close_short",
  "ticker": "EURUSD",
  "trading_type": "practice"
}
```

---

## Units Calculation
The size of the position (`units`) is calculated automatically based on 1% of the account balance and the stop-loss distance. This ensures consistent risk management. 

If the `units` field is provided in the JSON payload, it will be ignored, and the dynamically calculated value will be used instead.

---

## Optional: Use with Pine Script in TradingView
This bot can be integrated with a Pine Script strategy in TradingView to automate trade execution. The Pine Script should include a **Trade Management** section that generates alerts with correctly formatted JSON payloads for placing trades.

### Steps to Set Up Alerts
1. Reference your Pine Script strategy in TradingView.
2. Create alerts for your desired conditions (e.g., crossover of indicators).
3. Leave the alert body empty, as the Pine Script will generate the JSON payload dynamically.

### Example Pine Script Alert
The following Pine Script snippet demonstrates how to generate alerts with the correct JSON payload:

```pine
//@version=5
strategy("Daily Trade Strategy", overlay=true)

// Example alert for opening a long position
if (longCondition)
    alert('{"action":"open_long","ticker":"' + syminfo.ticker + '","price":' + str.tostring(close) +
          ',"stop_loss_price":' + str.tostring(stopLoss) +
          ',"take_profit_price":' + str.tostring(takeProfit) +
          ',"trading_type":"practice"}', alert.freq_once_per_bar_close)
```

### Backtesting Results
This strategy was backtested in TradingView in August 2025 over 365 days, resulting in:
- **556 trades**
- **35.25% profitable trades**
- **1.305 profit factor**

### Important Note
Always test the bot with a **practice account** before using it with real funds to ensure it behaves as expected.

---

## Optional: Logging Trades to Google Sheets

The bot supports logging trades to a Google Spreadsheet using the Google Sheets API. This feature is optional. If the required `service_account.json` file is missing, the bot will automatically log trades to `server.log` instead.

### Steps to Set Up Google Sheets Logging

1. **Enable the Google Sheets API**:
   - Go to the [Google Cloud Console](https://console.cloud.google.com/).
   - Create a new project (or use an existing one).
   - Navigate to **APIs & Services > Library**.
   - Search for **Google Sheets API** and **Google Drive API**, and enable both for your project.

2. **Create a Service Account**:
   - Go to **APIs & Services > Credentials**.
   - Click **Create Credentials > Service Account**.
   - Provide a name for the service account and click **Create and Continue**.
   - Assign the role **Editor** (or higher) to the service account and click **Done**.

3. **Download the Service Account Key**:
   - After creating the service account, go to the **Keys** section.
   - Click **Add Key > Create New Key** and select **JSON**.
   - Download the JSON key file and save it as `service_account.json` in the root directory of your project.

4. **Share the Spreadsheet with the Service Account**:
   - Create a new Google Spreadsheet (e.g., `Trading Log`) or use an existing one.
   - Share the spreadsheet with the service account email (found in the `client_email` field of the `service_account.json` file).
   - Grant **Editor** access to the service account.

5. **Configure the Spreadsheet in the Bot**:
   - Open the `gspread.py` file.
   - Update the `SPREADSHEET_NAME` and `WORKSHEET_NAME` variables to match your spreadsheet and worksheet names:
     ```python
     SPREADSHEET_NAME = "Trading Log"  # Replace with your spreadsheet name
     WORKSHEET_NAME = "Trades"  # Replace with your worksheet name
     ```

6. **Set Up the Worksheet**:
   - Add the following headers to the first row of the worksheet:
     - `Timestamp`
     - `Action`
     - `Instrument`
     - `Price`
     - `Stop Loss Price`
     - `Take Profit Price`
     - `Units`
     - `Trading Type`
     - `Status`
     - `Account Balance`

### How It Works
- If the `service_account.json` file is present and correctly configured, the bot will log each trade to the specified Google Spreadsheet.
- If the `service_account.json` file is missing, the bot will log trades to `server.log` instead. This ensures that no trade information is lost.

### Account Balance Logging
The bot retrieves the current account balance from OANDA and logs it alongside each trade. This provides a clear record of the account's financial state at the time of each trade.

### Example Log Entry in Google Sheets
| Timestamp           | Action      | Instrument | Price   | Stop Loss Price | Take Profit Price | Units | Trading Type | Status   | Account Balance |
|---------------------|-------------|------------|---------|-----------------|-------------------|-------|--------------|----------|-----------------|
| 2025-08-21 12:34:56 | open_long   | EUR_USD    | 1.12345 | 1.12000         | 1.13000           | 1000  | practice     | success  | 100000.50       |

---

Let me know if you need further clarification

