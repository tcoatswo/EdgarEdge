import logging

class StrategyEngine:
    def __init__(self, config):
        self.config = config
        self.bullish_keywords = [k.lower() for k in config.get('keywords_bullish', [])]
        self.bearish_keywords = [k.lower() for k in config.get('keywords_bearish', [])]

    def analyze_filing(self, symbol, entry):
        title = entry.title.lower()
        summary = getattr(entry, 'summary', '').lower()
        content = title + " " + summary

        # Simple sentiment analysis based on keywords
        is_bullish = any(k in content for k in self.bullish_keywords)
        is_bearish = any(k in content for k in self.bearish_keywords)

        if is_bullish and not is_bearish:
            logging.info(f"[{symbol}] Bullish sentiment detected in filing: {entry.title}")
            return "BUY"
        elif is_bearish and not is_bullish:
            logging.info(f"[{symbol}] Bearish sentiment detected in filing: {entry.title}")
            return "SELL"
        
        logging.info(f"[{symbol}] Neutral/Mixed sentiment in filing: {entry.title}")
        return "HOLD"
