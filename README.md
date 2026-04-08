# SEC EDGAR Automated Trader

An event-driven algorithmic trading bot that monitors the US SEC EDGAR database for real-time company filings (8-K, S-3, 10-Q, etc.) and executes trades based on basic keyword sentiment analysis (e.g. FDA approval vs. massive dilution). 

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure `config.json`:
- Ensure `user_agent` is set to your actual Name/Email (The SEC blocks generic/anonymous bot requests).
- Add the `symbols` you want to track.
- Adjust `keywords_bullish` and `keywords_bearish`.

3. Run the bot:
```bash
python main.py
```

## How It Works
- **src/sec_monitor.py**: Polls the SEC EDGAR Atom RSS feed for the configured ticker symbols.
- **src/strategy.py**: A simple NLP engine that looks for bearish (e.g. "S-3", "Offering") or bullish (e.g. "FDA Approval") terms in the filing titles/summaries.
- **src/executor.py**: Executes the trade. Currently defaults to `paper_trading`.

## Disclaimer
This is for educational purposes. Automated trading based on SEC filings is highly risky.
