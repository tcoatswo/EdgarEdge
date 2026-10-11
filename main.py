import logging
import time
import json
import sys
import hashlib
from src.sec_monitor import SECMonitor
from src.strategy import StrategyEngine
from src.executor import OrderExecutor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def load_config():
    with open('config.json', 'r') as f:
        return json.load(f)

def main():
    config = load_config()
    logging.info("Starting SEC EDGAR Automated Trader...")
    
    monitor = SECMonitor(config)
    try:
        monitor.establish_baseline()
    except (OSError, RuntimeError) as exc:
        logging.error("Trading disabled: %s", exc)
        raise SystemExit(1) from exc
    logging.info("Baseline established. Monitoring %s existing filings.", len(monitor.seen_ids))

    strategy = StrategyEngine(config)
    executor = OrderExecutor(config)

    def on_new_filing(symbol, entry):
        action, reason = strategy.analyze_filing(symbol, entry)
        if action in ["BUY", "SELL"]:
            quantity = config.get('order_quantity', 100)
            if config.get('exchange') == 'robinhood':
                filing_code = hashlib.sha256(str(entry.id).encode()).hexdigest()[:12]
                approval = f"APPROVE {action} {symbol} {filing_code}"
                executor.send_telegram(f"Live signal requires manual approval: {action} {quantity} {symbol}; filing {entry.id}")
                if not sys.stdin.isatty():
                    logging.warning("Live signal skipped: no interactive terminal for approval")
                    return
                logging.warning("Review filing title %r and SEC link %r", entry.title, getattr(entry, 'link', ''))
                try:
                    entered = input(f"Type '{approval}' to place {action} order: ")
                except EOFError:
                    return
                if entered != approval:
                    logging.info("Live order declined")
                    return
            executor.execute(symbol, action, reason, quantity=quantity,
                             approved=config.get('exchange') == 'robinhood')

    poll_interval = config.get('polling_interval_seconds', 10)
    logging.info(f"Polling SEC every {poll_interval} seconds...")

    try:
        while True:
            monitor.scan_for_new_filings(on_new_filing)
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        logging.info("Bot stopped by user.")

if __name__ == "__main__":
    main()
