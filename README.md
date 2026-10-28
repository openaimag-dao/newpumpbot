# Crypto Pump Scanner

Telegram alerts for spot pairs on Binance, Bybit, KuCoin, Coinbase and Upbit, using public ccxt market data.

## How it works
At each UTC hour plus a 90-second buffer, the worker reads the **last closed 1h OHLCV candle** for spot pairs quoted in USDT, USD or KRW. The percentage change is `(close/open - 1) * 100`. It sends the top gainers above the threshold for each exchange, or a no-pumps summary. Results are not investment advice.

**Limitations:** Scanning every symbol sequentially across five exchanges can exceed one hour; exchange restrictions, rate limits and unavailable candles can make results incomplete. For production-scale coverage use bounded concurrency, caching and a persistent cursor. This worker runs continuously and may require a paid Render plan.

## Telegram setup
1. Message [@BotFather](https://t.me/BotFather), send `/newbot`, and copy the bot token.
2. Start a chat with the new bot. Retrieve your numeric chat ID using `https://api.telegram.org/bot<TOKEN>/getUpdates` after messaging it, or a trusted Telegram ID helper.
3. Never commit tokens or your `.env` file to GitHub.

## Local run
```bash
python -m venv .venv
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN="your-token"
export TELEGRAM_CHAT_ID="your-chat-id"
export PUMP_THRESHOLD="5"
python bot.py
```
On Windows PowerShell use `$env:TELEGRAM_BOT_TOKEN="..."` etc.

## Render GitHub integration
1. Connect your GitHub account at [Render](https://dashboard.render.com/).
2. Choose **New > Blueprint**, select `openaimag-dao/newpumpbot` and deploy `render.yaml`.
3. Enter secret environment values `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`; `PUMP_THRESHOLD` defaults to `5`.
4. Check worker logs. Optionally set `TOP_N=10`, `REQUEST_TIMEOUT_MS=15000`, `CANDLE_DELAY_SECONDS=90`.

## Render API alternative
With `RENDER_API_KEY` in your shell, the service API is `POST https://api.render.com/v1/services`. The request must specify your connected repository, owner, worker runtime, build/start commands and plan according to the current [Render API documentation](https://api-docs.render.com/reference/create-service). Keep credentials out of command history and source control. Blueprint deployment is recommended because `render.yaml` is already included.

## Troubleshooting
If Binance is unavailable from the Render region, the report shows a per-exchange failure; other exchanges are still attempted. A failed Telegram send is retried, and the report is not marked sent until delivery succeeds.
