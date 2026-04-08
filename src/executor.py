import logging
import robin_stocks.robinhood as r

class OrderExecutor:
    def __init__(self, config):
        self.config = config
        self.exchange = config.get('exchange', 'paper_trading')
        
        if self.exchange == "robinhood":
            user = self.config.get('robinhood_user')
            password = self.config.get('robinhood_pass')
            
            if not user or not password or user == "YOUR_ROBINHOOD_EMAIL":
                logging.error("Robinhood credentials not set in config.json")
                return
                
            logging.info("Logging into Robinhood...")
            try:
                # This will prompt for SMS/MFA code on the first run.
                # After the first successful login, the token is cached.
                r.login(user, password)
                logging.info("Robinhood login successful.")
            except Exception as e:
                logging.error(f"Robinhood login failed: {e}")

    def execute(self, symbol, action, quantity=100):
        if action == "HOLD":
            return
            
        if self.exchange == "paper_trading":
            logging.info(f"PAPER TRADE EXECUTED: {action} {quantity} shares of {symbol}")
            return
            
        if self.exchange == "robinhood":
            logging.info(f"LIVE TRADE ATTEMPTED: {action} {quantity} shares of {symbol} on Robinhood")
            try:
                if action == "BUY":
                    # For sub-$3 stocks, Robinhood often prefers Limit orders, 
                    # but we will try a market order first for speed, or you can switch to limit.
                    res = r.orders.order_buy_market(symbol, quantity)
                    logging.info(f"Robinhood Buy Response: {res}")
                elif action == "SELL":
                    res = r.orders.order_sell_market(symbol, quantity)
                    logging.info(f"Robinhood Sell Response: {res}")
            except Exception as e:
                logging.error(f"Robinhood order failed: {e}")
