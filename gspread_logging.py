import gspread
from datetime import datetime
import logging

# Google Sheets configuration
SPREADSHEET_NAME = "TradingBot 2025"  # Replace with the name of your spreadsheet
WORKSHEET_NAME = "Trades"  # Replace with the name of your worksheet

# Path to your service account JSON key file
SERVICE_ACCOUNT_FILE = "service_account.json"  # Replace with the path to your JSON key file

def get_google_sheet():
    """Authenticate and return the Google Sheet."""
    try:
        # Authenticate using the service account JSON key file
        client = gspread.service_account(filename=SERVICE_ACCOUNT_FILE)

        # Open the spreadsheet
        spreadsheet = client.open(SPREADSHEET_NAME)

        # Open the worksheet
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)

        return worksheet
    except FileNotFoundError:
        logging.warning(f"Service account file '{SERVICE_ACCOUNT_FILE}' not found. Falling back to local logging.")
        return None
    except Exception as e:
        logging.error(f"Error accessing Google Sheet: {e}")
        return None

def log_trade(action, instrument, price, stop_loss_price, take_profit_price, units, trading_type, status, account_balance=None, id_number=None, margin=None, pip_value=None, trade_value=None, reward=None, risk=None):
    """Log a trade to the Google Spreadsheet or fallback to local logging."""
    try:
        # Get the worksheet
        worksheet = get_google_sheet()

        # Prepare the trade data
        trade_data = [
            datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),  # Timestamp (UTC)
            action,  # Action (e.g., open_long, close_short)
            instrument,  # Instrument (e.g., EUR_USD)
            price,  # Entry price
            stop_loss_price,  # Stop-loss price
            take_profit_price,  # Take-profit price
            units,  # Number of units
            trading_type,  # Trading type (e.g., practice or live)
            status,  # Status (e.g., success or error)
            account_balance,  # Account balance
            id_number,  # ID number
            margin,  # Margin
            pip_value,  # Pip value
            trade_value,  # Trade value
            reward,  # Reward
            risk,  # Risk
        ]

        if worksheet:
            # Append the trade data to the worksheet
            worksheet.append_row(trade_data)
            logging.info("Trade logged successfully to Google Sheets.")
        else:
            # Fallback to logging in server.log
            logging.info(f"Trade logged locally: {trade_data}")
    except Exception as e:
        logging.error(f"Error logging trade: {e}")