# EdgarEdge: Algorithmic Event-Driven Trader

An event-driven algorithmic trading bot that monitors the US SEC EDGAR database for real-time company filings (8-K, S-3, 10-Q, etc.) and executes trades based on LLM sentiment analysis. Get ahead of the market by acting on material news (FDA approvals, secondary offerings) seconds after it hits the wire.

Built to support both **Paper Trading** (testing) and **Robinhood Live Trading**.

## Features
- **Direct SEC Polling:** Uses the SEC's raw Atom feeds to get filings immediately (bypassing delayed third-party news aggregators). Adjustable polling rate down to 10 seconds.
- **AI Sentiment Engine (Gemini / OpenAI):** Pipes filing summaries directly into an LLM to accurately determine if an event is bullish or bearish, eliminating false positives like "FDA Lifts Clinical Hold". (Falls back to keyword matching if no API key is provided).
- **Robinhood Integration:** Executes live trades via `robin_stocks` when a signal triggers.
- **Extended-Hours Support:** Automatically switches to Extended-Hours Limit orders if a filing drops before/after the market opens.
- **Auto-Trailing Stop Loss:** Optionally submits a trailing stop loss order immediately after buying to lock in profits.
- **Telegram Webhooks:** Pushes real-time alerts to your phone when a trade executes.
- **Paper Trading Mode:** Logs signals to the console without risking capital.

---

## Setup & Installation

1. **Clone the repository:**
```bash
git clone https://github.com/tcoatswo/EdgarEdge.git
cd EdgarEdge
```

2. **Install dependencies:**
```bash
pip install -r requirements.txt
```

3. **Configure the bot:**
Copy the example configuration file:
```bash
cp config.example.json config.json
```
Edit `config.json`:
- **`user_agent`**: You *must* set this to your actual Name/Email (e.g., `John Doe john@example.com`). The SEC blocks anonymous requests.
- **`symbols`**: Add the ticker symbols you want to monitor.
- **`exchange`**: Set to `"paper_trading"` for testing, or `"robinhood"` for live execution.

---

## Setting up Robinhood Live Trading

If you set `"exchange": "robinhood"`, you need to authenticate:

1. Add your Robinhood email and password to `config.json` (`robinhood_user` and `robinhood_pass`).
2. **The First Run (MFA):** Run the script manually in your terminal:
   ```bash
   python main.py
   ```
3. Robinhood will send an SMS code to your phone. The script will pause and ask you to enter the code in the terminal.
4. Once entered, your authentication token is cached securely on your machine (`~/.tokens`). You can now run the bot in the background without needing SMS codes again.

---

## How It Works under the Hood
- **`src/sec_monitor.py`**: Polls the SEC EDGAR Atom RSS feed for the configured ticker symbols. Respects the SEC rate limit (max 10 requests/sec).
- **`src/strategy.py`**: A simple NLP engine that looks for bearish (e.g., "S-3", "Offering", "Dilution") or bullish (e.g., "FDA Approval", "Fast Track") terms in the filing titles and summaries.
- **`src/executor.py`**: Catches the BUY/SELL signal and pushes the market order to the configured exchange.

## Disclaimer
This project is strictly for **educational purposes**. Automated trading based on SEC filings is highly risky. Market conditions change rapidly, and keyword-based parsing is not foolproof. Never trade with money you cannot afford to lose. The developers assume no responsibility for financial losses.