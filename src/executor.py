import logging
import requests
import datetime
import robin_stocks.robinhood as r

class OrderExecutor:
    def __init__(self, config):
        self.config = config
        self.exchange = config.get('exchange', 'paper_trading')
        self.telegram_token = config.get('telegram_bot_token', '')
        self.telegram_chat = config.get('telegram_chat_id', '')
        self.trailing_stop_pct = config.get('trailing_stop_percentage', 5.0)
        
        if self.exchange == "robinhood":
            user = self.config.get('robinhood_user')
            password = self.config.get('robinhood_pass')
            
            if not user or not password or user == "YOUR_ROBINHOOD_EMAIL":
                logging.error("Robinhood credentials not set in config.json")
                return
                
            logging.info("Logging into Robinhood...")
            try:
                r.login(user, password)
                logging.info("Robinhood login successful.")
            except Exception as e:
                logging.error(f"Robinhood login failed: {e}")

    def send_telegram(self, message):
        if not self.telegram_token or not self.telegram_chat:
            return
        
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        payload = {"chat_id": self.telegram_chat, "text": message}
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            logging.error(f"Telegram alert failed: {e}")

    def is_regular_hours(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        ny_time = now.astimezone(datetime.timezone(datetime.timedelta(hours=-4))) # Simplistic EST check, sufficient for rough checks
        # Mon-Fri, 9:30 AM to 4:00 PM EST
        if ny_time.weekday() > 4:
            return False
        
        time_int = ny_time.hour * 100 + ny_time.minute
        if 930 <= time_int < 1600:
            return True
        return False

    def get_latest_price(self, symbol):
        try:
            quote = r.stocks.get_latest_price(symbol)
            return float(quote[0])
        except Exception:
            return None

    def execute(self, symbol, action, reason, quantity=100):
        if action == "HOLD":
            return
            
        msg = f"🚨 {action} SIGNAL: {quantity} shares of {symbol} \nReason: {reason}"
        logging.info(msg)
        self.send_telegram(msg)
            
        if self.exchange == "paper_trading":
            return
            
        if self.exchange == "robinhood":
            try:
                regular_hours = self.is_regular_hours()
                
                if action == "BUY":
                    if regular_hours:
                        res = r.orders.order_buy_market(symbol, quantity)
                        logging.info(f"Robinhood Market Buy Response: {res}")
                        self.send_telegram(f"✅ Market Buy Placed for {symbol}.")
                    else:
                        price = self.get_latest_price(symbol)
                        if not price:
                            logging.error("Could not fetch price for After-Hours limit order.")
                            return
                        # Place extended hours limit order slightly above current price to ensure fill
                        limit_price = round(price * 1.01, 2)
                        res = r.orders.order_buy_limit(symbol, quantity, limit_price, timeInForce='gfd', extendedHours=True)
                        logging.info(f"Robinhood Ext-Hours Limit Buy Response: {res}")
                        self.send_telegram(f"🌙 After-Hours Limit Buy Placed for {symbol} at ${limit_price}.")

                    # Auto Trailing Stop
                    if self.trailing_stop_pct > 0:
                        logging.info(f"Placing {self.trailing_stop_pct}% trailing stop loss for {symbol}...")
                        ts_res = r.orders.order_sell_trailing_stop(
                            symbol, quantity, self.trailing_stop_pct, trailType='percentage', timeInForce='gtc'
                        )
                        logging.info(f"Trailing Stop Response: {ts_res}")
                        self.send_telegram(f"🛡️ Placed {self.trailing_stop_pct}% trailing stop loss for {symbol}.")

                elif action == "SELL":
                    if regular_hours:
                        res = r.orders.order_sell_market(symbol, quantity)
                        logging.info(f"Robinhood Market Sell Response: {res}")
                        self.send_telegram(f"✅ Market Sell Placed for {symbol}.")
                    else:
                        price = self.get_latest_price(symbol)
                        if not price:
                            return
                        limit_price = round(price * 0.99, 2)
                        res = r.orders.order_sell_limit(symbol, quantity, limit_price, timeInForce='gfd', extendedHours=True)
                        logging.info(f"Robinhood Ext-Hours Limit Sell Response: {res}")
                        self.send_telegram(f"🌙 After-Hours Limit Sell Placed for {symbol} at ${limit_price}.")
                        
            except Exception as e:
                err = f"❌ Robinhood order failed: {e}"
                logging.error(err)
                self.send_telegram(err)
