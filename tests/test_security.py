import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.executor import OrderExecutor
from src.sec_monitor import SECMonitor
from src.strategy import StrategyEngine


class SecurityTests(unittest.TestCase):
    def test_default_state_path_stays_inside_repository(self):
        with patch.dict(os.environ, {'EDGAREDGE_DATA_DIR': ''}):
            monitor = SECMonitor({'symbols': ['TEST']})
        self.assertEqual(monitor.state_file, ROOT / 'data' / 'edgar_edge_seen_ids.json')

    def test_model_reply_must_be_exact_and_never_falls_back_to_keywords(self):
        config = {'llm_api_key': 'test-key', 'keywords_bullish': ['approval']}
        engine = StrategyEngine(config)
        response = SimpleNamespace(status_code=200, json=lambda: {
            'candidates': [{'content': {'parts': [{'text': 'BEARISH, not BULLISH'}]}}]
        })
        with patch('src.strategy.requests.post', return_value=response) as post:
            action, _ = engine.analyze_filing('TEST', SimpleNamespace(title='approval', summary=''))
        self.assertEqual(action, 'HOLD')
        self.assertNotIn('key=', post.call_args.args[0])
        self.assertEqual(post.call_args.kwargs['headers']['x-goog-api-key'], 'test-key')

    def test_baseline_fails_closed_and_seen_ids_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {'symbols': ['TEST'], 'max_filing_age_seconds': 600}
            monitor = SECMonitor(config)
            monitor.state_file = Path(directory) / 'seen.json'
            with patch.object(monitor, 'fetch_filings', return_value=None):
                with self.assertRaises(RuntimeError):
                    monitor.establish_baseline()
            self.assertFalse(monitor.state_file.exists())

            old = SimpleNamespace(id='old', title='old', published_parsed=time.gmtime())
            with patch.object(monitor, 'fetch_filings', return_value=SimpleNamespace(entries=[old])):
                monitor.establish_baseline()
            self.assertEqual(json.loads(monitor.state_file.read_text()), ['old'])

            fresh = SimpleNamespace(id='new', title='new', published_parsed=time.gmtime())
            called = []
            with patch.object(monitor, 'fetch_filings', return_value=SimpleNamespace(entries=[old, fresh])):
                monitor.scan_for_new_filings(lambda symbol, entry: called.append(entry.id))
            self.assertEqual(called, ['new'])
            self.assertEqual(json.loads(monitor.state_file.read_text()), ['new', 'old'])

            restarted = SECMonitor(config)
            restarted.state_file = monitor.state_file
            with patch.object(restarted, 'fetch_filings', return_value=SimpleNamespace(entries=[old, fresh])):
                restarted.establish_baseline()
                restarted.scan_for_new_filings(lambda symbol, entry: called.append(entry.id))
            self.assertEqual(called, ['new'])

    def test_baseline_requires_every_symbol(self):
        with tempfile.TemporaryDirectory() as directory:
            monitor = SECMonitor({'symbols': ['GOOD', 'BAD']})
            monitor.state_file = Path(directory) / 'seen.json'
            good = SimpleNamespace(entries=[SimpleNamespace(id='old')])
            with patch.object(monitor, 'fetch_filings', side_effect=[good, None]):
                with self.assertRaises(RuntimeError):
                    monitor.establish_baseline()
            self.assertFalse(monitor.state_file.exists())

    def test_live_buy_waits_for_fill_before_protective_stop(self):
        config = {'exchange': 'robinhood', 'robinhood_user': 'user', 'robinhood_pass': 'pass',
                  'symbols': ['TEST'], 'max_order_notional': 1000}
        with patch('src.executor.r.login', return_value={'access_token': 'token'}):
            executor = OrderExecutor(config)
        with patch.object(executor, 'get_latest_price', return_value=5), \
             patch.object(executor, 'is_regular_hours', return_value=True), \
             patch.object(executor, 'send_telegram'), \
             patch('src.executor.r.account.build_holdings', return_value={}), \
             patch('src.executor.r.orders.order_buy_limit', return_value={'id': 'buy1', 'state': 'queued'}) as buy, \
             patch('src.executor.r.orders.get_stock_order_info', side_effect=[
                 {'state': 'filled', 'cumulative_quantity': '2'},
                 {'state': 'confirmed'}]) as info, \
             patch('src.executor.r.orders.order_sell_trailing_stop', return_value={'id': 'stop1', 'state': 'queued'}) as stop:
            self.assertFalse(executor.execute('TEST', 'BUY', 'test', quantity=2))
            buy.assert_not_called()
            self.assertTrue(executor.execute('TEST', 'BUY', 'test', quantity=2, approved=True))
            self.assertEqual(buy.call_args.args, ('TEST', 2, 5.05))
            self.assertEqual(info.call_args_list[0].args, ('buy1',))
            self.assertEqual(stop.call_args.args[:2], ('TEST', 2))

    def test_rejected_order_never_gets_a_stop_or_success(self):
        config = {'exchange': 'robinhood', 'robinhood_user': 'user', 'robinhood_pass': 'pass',
                  'symbols': ['TEST']}
        with patch('src.executor.r.login', return_value={'access_token': 'token'}):
            executor = OrderExecutor(config)
        with patch.object(executor, 'get_latest_price', return_value=5), \
             patch.object(executor, 'is_regular_hours', return_value=True), \
             patch.object(executor, 'send_telegram'), \
             patch('src.executor.r.account.build_holdings', return_value={}), \
             patch('src.executor.r.orders.order_buy_limit', return_value={'detail': 'rejected'}), \
             patch('src.executor.r.orders.order_sell_trailing_stop') as stop:
            self.assertFalse(executor.execute('TEST', 'BUY', 'test', quantity=2, approved=True))
            self.assertTrue(executor.halted)
            stop.assert_not_called()

    def test_partial_fill_is_stopped_only_after_cancellation(self):
        config = {'exchange': 'robinhood', 'robinhood_user': 'user', 'robinhood_pass': 'pass',
                  'symbols': ['TEST'], 'order_fill_timeout_seconds': 0}
        with patch('src.executor.r.login', return_value={'access_token': 'token'}):
            executor = OrderExecutor(config)
        events = []
        def cancel(order_id):
            events.append(('cancel', order_id))
        def stop(symbol, quantity, percentage, **kwargs):
            events.append(('stop', quantity))
            return {'id': 'stop1', 'state': 'queued'}
        with patch.object(executor, 'get_latest_price', return_value=5), \
             patch.object(executor, 'is_regular_hours', return_value=True), \
             patch.object(executor, 'send_telegram'), \
             patch('src.executor.r.account.build_holdings', return_value={}), \
             patch('src.executor.r.orders.order_buy_limit', return_value={'id': 'buy1', 'state': 'queued'}), \
             patch('src.executor.r.orders.get_stock_order_info', side_effect=[
                 {'state': 'queued', 'cumulative_quantity': '1'},
                 {'state': 'cancelled', 'cumulative_quantity': '1'},
                 {'state': 'confirmed'}]), \
             patch('src.executor.r.orders.cancel_stock_order', side_effect=cancel), \
             patch('src.executor.r.orders.order_sell_trailing_stop', side_effect=stop), \
             patch('src.executor.time.sleep'):
            self.assertTrue(executor.execute('TEST', 'BUY', 'test', quantity=2, approved=True))
        self.assertEqual(events, [('cancel', 'buy1'), ('stop', 1)])

if __name__ == '__main__':
    unittest.main()
