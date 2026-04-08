import logging
import requests
import json

class StrategyEngine:
    def __init__(self, config):
        self.config = config
        self.bullish_keywords = [k.lower() for k in config.get('keywords_bullish', [])]
        self.bearish_keywords = [k.lower() for k in config.get('keywords_bearish', [])]
        self.llm_key = config.get('llm_api_key', '')

    def analyze_with_llm(self, text):
        if not self.llm_key:
            return None
        
        # Using Google Gemini API for fast reasoning
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.llm_key}"
        headers = {'Content-Type': 'application/json'}
        prompt = (
            "You are a hedge fund trading algorithm. Analyze this SEC filing summary. "
            "Reply with exactly one word: BULLISH, BEARISH, or NEUTRAL. "
            f"Filing Summary: {text}"
        )
        data = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        
        try:
            resp = requests.post(url, headers=headers, json=data, timeout=5)
            if resp.status_code == 200:
                result = resp.json()
                reply = result['candidates'][0]['content']['parts'][0]['text'].strip().upper()
                if "BULLISH" in reply: return "BUY"
                if "BEARISH" in reply: return "SELL"
                return "HOLD"
        except Exception as e:
            logging.error(f"LLM analysis failed: {e}")
        
        return None

    def analyze_filing(self, symbol, entry):
        title = entry.title
        summary = getattr(entry, 'summary', '')
        content = f"{title}\n{summary}"

        if self.llm_key:
            logging.info(f"[{symbol}] Sending filing to LLM for sentiment analysis...")
            action = self.analyze_with_llm(content)
            if action:
                return action, "LLM Sentiment Analysis"

        # Fallback to keywords
        content_lower = content.lower()
        is_bullish = any(k in content_lower for k in self.bullish_keywords)
        is_bearish = any(k in content_lower for k in self.bearish_keywords)

        if is_bullish and not is_bearish:
            return "BUY", "Keyword match (Bullish)"
        elif is_bearish and not is_bullish:
            return "SELL", "Keyword match (Bearish)"
        
        return "HOLD", "Neutral"
