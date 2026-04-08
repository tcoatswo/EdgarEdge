import logging

class OrderExecutor:
    def __init__(self, config):
        self.config = config
        self.exchange = config.get('exchange', 'paper_trading')

    def execute(self, symbol, action, quantity=100):
        if action == "HOLD":
            return
            
        if self.exchange == "paper_trading":
            logging.info(f"PAPER TRADE EXECUTED: {action} {quantity} shares of {symbol}")
        else:
            # Here you would integrate with a real broker API (e.g. Robinhood, Alpaca, Interactive Brokers)
            logging.info(f"LIVE TRADE ATTEMPTED: {action} {quantity} shares of {symbol} on {self.exchange}")
