import datetime
import logging
import math
import time
from zoneinfo import ZoneInfo

import requests
import robin_stocks.robinhood as r


ACCEPTED_STATES = {'queued', 'confirmed', 'unconfirmed', 'partially_filled', 'filled'}
TERMINAL_STATES = {'filled', 'cancelled', 'canceled', 'failed', 'rejected', 'expired'}


class OrderExecutor:
    def __init__(self, config):
        self.config = config
        self.exchange = config.get('exchange', 'paper_trading')
        self.telegram_token = config.get('telegram_bot_token', '')
        self.telegram_chat = config.get('telegram_chat_id', '')
        self.trailing_stop_pct = float(config.get('trailing_stop_percentage', 5.0))
        self.max_order_shares = int(config.get('max_order_shares', 100))
        self.max_order_notional = float(config.get('max_order_notional', 1000))
        self.max_position_shares = int(config.get('max_position_shares', 100))
        self.fill_timeout = max(0, float(config.get('order_fill_timeout_seconds', 30)))
        if (self.max_order_shares <= 0 or self.max_position_shares <= 0
                or not math.isfinite(self.max_order_notional) or self.max_order_notional <= 0
                or not math.isfinite(self.trailing_stop_pct)
                or not 0 <= self.trailing_stop_pct < 100):
            raise ValueError('invalid live trading risk limits')
        self.ready = self.exchange == 'paper_trading'
        self.halted = False

        if self.exchange == 'robinhood':
            user = config.get('robinhood_user')
            password = config.get('robinhood_pass')
            if not user or not password or user == 'YOUR_ROBINHOOD_EMAIL':
                logging.error('Robinhood credentials not set in config.json')
                return
            try:
                login = r.login(user, password)
                self.ready = isinstance(login, dict) and bool(login.get('access_token'))
                if not self.ready:
                    logging.error('Robinhood login was not confirmed')
            except Exception:
                logging.error('Robinhood login failed')

    def send_telegram(self, message):
        if not self.telegram_token or not self.telegram_chat:
            return
        url = f'https://api.telegram.org/bot{self.telegram_token}/sendMessage'
        try:
            response = requests.post(url, json={'chat_id': self.telegram_chat, 'text': message}, timeout=5)
            response.raise_for_status()
        except Exception:
            # Request exceptions may contain the URL, which embeds the bot token.
            logging.error('Telegram alert failed')

    def is_regular_hours(self):
        now = datetime.datetime.now(ZoneInfo('America/New_York'))
        if now.weekday() > 4:
            return False
        return 930 <= now.hour * 100 + now.minute < 1600

    def get_latest_price(self, symbol):
        try:
            quotes = r.stocks.get_quotes(symbol)
            if quotes and quotes[0]:
                q = quotes[0]
                price = q.get('last_extended_hours_trade_price') or q.get('last_trade_price') or q.get('ask_price')
                if price:
                    value = float(price)
                    if math.isfinite(value) and value > 0:
                        return value
            quote = r.stocks.get_latest_price(symbol)
            value = float(quote[0])
            return value if math.isfinite(value) and value > 0 else None
        except Exception:
            return None

    def _check_limits(self, symbol, action, quantity, price):
        if symbol not in self.config.get('symbols', []):
            raise ValueError('symbol is not on the configured watchlist')
        if type(quantity) is not int or quantity <= 0 or quantity > self.max_order_shares:
            raise ValueError('order quantity exceeds the configured share limit')
        if not price or not math.isfinite(price) or price * quantity > self.max_order_notional:
            raise ValueError('order notional exceeds the configured dollar limit')
        holdings = r.account.build_holdings()
        if not isinstance(holdings, dict):
            raise ValueError('could not verify current holdings')
        held = float(holdings.get(symbol, {}).get('quantity', 0))
        if not math.isfinite(held) or held < 0:
            raise ValueError('invalid current holdings')
        if action == 'BUY' and held + quantity > self.max_position_shares:
            raise ValueError('order exceeds the configured position limit')
        if action == 'SELL' and held < quantity:
            raise ValueError('order exceeds available holdings')

    @staticmethod
    def _order_id(response):
        if not isinstance(response, dict) or not response.get('id'):
            raise ValueError('broker did not return an order ID')
        if str(response.get('state', '')).lower() not in ACCEPTED_STATES:
            raise ValueError('broker did not accept the order')
        return response['id']

    @staticmethod
    def _filled_quantity(info, requested):
        if not isinstance(info, dict):
            raise ValueError('broker order status is unavailable')
        state = str(info.get('state', '')).lower()
        raw = info.get('cumulative_quantity')
        if raw is None and state == 'filled':
            raw = info.get('quantity')
        filled = float(raw or 0)
        if not math.isfinite(filled) or filled < 0 or filled > requested:
            raise ValueError('broker reported an invalid filled quantity')
        if state == 'filled' and filled == 0:
            raise ValueError('broker reported a fill without a quantity')
        return state, filled

    def _wait_for_order(self, order_id, requested):
        """Return final filled shares, cancelling an order that does not settle."""
        deadline = time.monotonic() + self.fill_timeout
        cancel_requested = False
        while True:
            info = r.orders.get_stock_order_info(order_id)
            state, filled = self._filled_quantity(info, requested)
            if state in TERMINAL_STATES:
                return filled
            if time.monotonic() >= deadline:
                if cancel_requested:
                    raise ValueError('broker did not confirm order cancellation')
                r.orders.cancel_stock_order(order_id)
                cancel_requested = True
                deadline = time.monotonic() + 10
            time.sleep(1)

    def execute(self, symbol, action, reason, quantity=100, approved=False):
        if action not in ('BUY', 'SELL'):
            return False
        if self.exchange == 'paper_trading':
            logging.info('PAPER %s %s shares of %s: %s', action, quantity, symbol, reason)
            return True
        if self.exchange != 'robinhood' or not self.ready or self.halted or not approved:
            logging.error('Live order blocked: approval or broker readiness is missing')
            return False

        try:
            price = self.get_latest_price(symbol)
            self._check_limits(symbol, action, quantity, price)
            regular_hours = self.is_regular_hours()
            if action == 'BUY':
                limit_price = round(price * 1.01, 2)
                if limit_price * quantity > self.max_order_notional:
                    raise ValueError('buy limit price exceeds the configured dollar limit')
                if regular_hours:
                    response = r.orders.order_buy_limit(
                        symbol, quantity, limit_price, timeInForce='gfd')
                else:
                    response = r.orders.order_buy_limit(
                        symbol, quantity, limit_price,
                        timeInForce='gfd', extendedHours=True)
            elif regular_hours:
                response = r.orders.order_sell_market(symbol, quantity)
            else:
                response = r.orders.order_sell_limit(
                    symbol, quantity, round(price * 0.99, 2),
                    timeInForce='gfd', extendedHours=True)

            order_id = self._order_id(response)
            logging.info('Broker accepted %s order %s for %s', action, order_id, symbol)
            filled = self._wait_for_order(order_id, quantity)
            if filled <= 0:
                self.send_telegram(f'{action} order {order_id} for {symbol} ended with no fill.')
                return False
            self.send_telegram(f'{action} order {order_id} filled {filled} shares of {symbol}.')

            if action == 'BUY' and self.trailing_stop_pct > 0:
                stop_quantity = int(filled) if filled.is_integer() else filled
                stop = r.orders.order_sell_trailing_stop(
                    symbol, stop_quantity, self.trailing_stop_pct,
                    trailType='percentage', timeInForce='gtc')
                stop_id = self._order_id(stop)
                stop_info = r.orders.get_stock_order_info(stop_id)
                if not isinstance(stop_info, dict) or str(stop_info.get('state', '')).lower() not in ACCEPTED_STATES:
                    raise ValueError('broker did not confirm protective stop')
                self.send_telegram(f'Protective stop {stop_id} accepted for {filled} shares of {symbol}.')
            return True
        except Exception:
            # A rejected or uncertain stop after a fill requires manual action.
            self.halted = True
            logging.error('Live trading halted for %s; inspect broker orders and protective stops', symbol)
            self.send_telegram(f'CRITICAL: trading halted for {symbol}; check broker orders and protective stops manually.')
            return False
