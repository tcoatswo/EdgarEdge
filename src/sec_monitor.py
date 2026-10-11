import calendar
import json
import os
import tempfile
import time
from pathlib import Path
import requests
import feedparser
import logging

class SECMonitor:
    def __init__(self, config):
        self.config = config
        self.symbols = config.get('symbols', [])
        self.user_agent = config.get('user_agent', 'AnonymousTrader no-reply@example.com')
        self.seen_ids = set()
        data_dir = Path(os.environ.get('EDGAREDGE_DATA_DIR') or Path(__file__).resolve().parents[1] / 'data')
        self.state_file = data_dir / 'edgar_edge_seen_ids.json'
        self.max_filing_age_seconds = int(config.get('max_filing_age_seconds', 600))

    def fetch_filings(self, symbol):
        url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={symbol}&type=&dateb=&owner=exclude&start=0&count=10&output=atom"
        headers = {'User-Agent': self.user_agent}
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                feed = feedparser.parse(response.content)
                if getattr(feed, 'bozo', False):
                    logging.error("Invalid SEC feed for %s", symbol)
                    return None
                return feed
            else:
                logging.error(f"SEC API returned {response.status_code} for {symbol}")
                return None
        except Exception as e:
            logging.error(f"Error fetching SEC filings for {symbol}: {e}")
            return None

    def _save_seen_ids(self):
        self.state_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile('w', dir=self.state_file.parent,
                                             prefix='.edgar-seen-', delete=False) as temp:
                temp_path = temp.name
                json.dump(sorted(self.seen_ids), temp)
                temp.flush()
                os.fsync(temp.fileno())
            os.replace(temp_path, self.state_file)
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    def establish_baseline(self):
        """Fetch every watchlist feed before any filing can trigger an order."""
        if not self.symbols:
            raise RuntimeError("No symbols configured")
        seen = set()
        if self.state_file.exists():
            try:
                saved = json.loads(self.state_file.read_text())
                if not isinstance(saved, list) or not all(isinstance(i, str) for i in saved):
                    raise ValueError("invalid seen ID state")
                seen.update(saved)
            except (OSError, ValueError) as exc:
                raise RuntimeError("Cannot load SEC filing state") from exc
        for symbol in self.symbols:
            feed = self.fetch_filings(symbol)
            if feed is None:
                raise RuntimeError(f"Cannot establish SEC baseline for {symbol}")
            seen.update(entry.id for entry in feed.entries if getattr(entry, 'id', None))
        self.seen_ids = seen
        self._save_seen_ids()

    def scan_for_new_filings(self, on_new_filing):
        for symbol in self.symbols:
            feed = self.fetch_filings(symbol)
            if feed is not None:
                for entry in feed.entries:
                    entry_id = getattr(entry, 'id', None)
                    if not entry_id or entry_id in self.seen_ids:
                        continue
                    self.seen_ids.add(entry_id)
                    # Persist first. If the process crashes while handling a
                    # filing, it must not replay a possible live order.
                    self._save_seen_ids()
                    published = getattr(entry, 'published_parsed', None) or getattr(entry, 'updated_parsed', None)
                    if not published:
                        logging.warning("Skipping filing without timestamp: %s", entry_id)
                        continue
                    age = time.time() - calendar.timegm(published)
                    if age < -300 or age > self.max_filing_age_seconds:
                        logging.warning("Skipping stale or future filing: %s", entry_id)
                        continue
                    logging.info("New filing detected for %s: %s", symbol, entry.title)
                    on_new_filing(symbol, entry)
