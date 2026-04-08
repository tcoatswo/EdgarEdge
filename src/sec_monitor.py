import time
import requests
import feedparser
import logging

class SECMonitor:
    def __init__(self, config):
        self.config = config
        self.symbols = config.get('symbols', [])
        self.user_agent = config.get('user_agent', 'AnonymousTrader no-reply@example.com')
        self.seen_ids = set()

    def fetch_filings(self, symbol):
        url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={symbol}&type=&dateb=&owner=exclude&start=0&count=10&output=atom"
        headers = {'User-Agent': self.user_agent}
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                return feedparser.parse(response.content)
            else:
                logging.error(f"SEC API returned {response.status_code} for {symbol}")
                return None
        except Exception as e:
            logging.error(f"Error fetching SEC filings for {symbol}: {e}")
            return None

    def scan_for_new_filings(self, on_new_filing):
        for symbol in self.symbols:
            feed = self.fetch_filings(symbol)
            if feed and feed.entries:
                for entry in feed.entries:
                    if entry.id not in self.seen_ids:
                        self.seen_ids.add(entry.id)
                        logging.info(f"New filing detected for {symbol}: {entry.title}")
                        on_new_filing(symbol, entry)
