import logging
import time
import json
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
    strategy = StrategyEngine(config)
    executor = OrderExecutor(config)

    # Initialize seen_ids so we don't trade on old filings on boot
    logging.info("Fetching initial baseline of filings...")
    for symbol in config.get('symbols', []):
        feed = monitor.fetch_filings(symbol)
        if feed and feed.entries:
            for entry in feed.entries:
                monitor.seen_ids.add(entry.id)
    logging.info(f"Baseline established. Monitoring {len(monitor.seen_ids)} existing filings.")

    def on_new_filing(symbol, entry):
        action = strategy.analyze_filing(symbol, entry)
        if action in ["BUY", "SELL"]:
            executor.execute(symbol, action, quantity=100)

    try:
        while True:
            monitor.scan_for_new_filings(on_new_filing)
            time.sleep(15 * 60) # Scan every 15 minutes to respect SEC rate limits (max 10 requests per second across all bots)
    except KeyboardInterrupt:
        logging.info("Bot stopped by user.")

if __name__ == "__main__":
    main()
