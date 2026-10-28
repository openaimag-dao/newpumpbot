"""Hourly closed-candle spot pump scanner."""
import logging
import os
import signal
import time
from datetime import datetime, timezone
from html import escape

import ccxt
import requests
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pumpbot")
RUNNING = True
EXCHANGES = ("binance", "bybit", "kucoin", "coinbase", "upbit")
QUOTES = {"USDT", "USD", "KRW"}
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
THRESHOLD = float(os.getenv("PUMP_THRESHOLD", "5"))
TOP_N = max(1, int(os.getenv("TOP_N", "10")))
INTERVAL = max(60, int(os.getenv("SCAN_INTERVAL_SECONDS", "3600")))
TIMEOUT_MS = max(1000, int(os.getenv("REQUEST_TIMEOUT_MS", "15000")))
DELAY = max(0, int(os.getenv("CANDLE_DELAY_SECONDS", "90")))


def stop(*_args):
    global RUNNING
    RUNNING = False


def retry(fn, attempts=3):
    for i in range(attempts):
        try:
            return fn()
        except (ccxt.NetworkError, ccxt.ExchangeNotAvailable, ccxt.RequestTimeout) as exc:
            if i == attempts - 1:
                raise
            log.warning("Retry %d: %s", i + 1, exc)
            time.sleep(2 ** (i + 1))


def send(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    for start in range(0, len(message), 3800):
        part = message[start:start + 3800]
        for attempt in range(3):
            try:
                response = requests.post(
                    url, json={"chat_id": CHAT_ID, "text": part, "parse_mode": "HTML"},
                    timeout=20,
                )
                response.raise_for_status()
                if not response.json().get("ok"):
                    raise RuntimeError("Telegram rejected message")
                break
            except (requests.RequestException, ValueError, RuntimeError):
                if attempt == 2:
                    raise
                time.sleep(2 ** (attempt + 1))


def scan(exchange_id, hour_ms):
    exchange = getattr(ccxt, exchange_id)({
        "enableRateLimit": True, "timeout": TIMEOUT_MS,
        "options": {"defaultType": "spot"},
    })
    try:
        markets = retry(exchange.load_markets)
        symbols = [
            symbol for symbol, market in markets.items()
            if market.get("spot") and market.get("active", True)
            and market.get("quote") in QUOTES
            and market.get("base") and not market.get("contract")
        ]
        if not exchange.has.get("fetchOHLCV"):
            raise RuntimeError("Exchange does not support OHLCV")
        matches = []
        failed = 0
        # Fetch a window around the last completed UTC hour.
        for symbol in symbols:
            if not RUNNING:
                break
            try:
                candles = retry(lambda s=symbol: exchange.fetch_ohlcv(
                    s, timeframe="1h", since=hour_ms - 3600000, limit=4
                ), attempts=2)
                candle = next((c for c in candles if int(c[0]) == hour_ms), None)
                if not candle or not candle[1] or not candle[4]:
                    continue
                pct = (float(candle[4]) / float(candle[1]) - 1) * 100
                if pct > THRESHOLD:
                    matches.append((symbol, pct))
            except (ccxt.BaseError, ValueError, TypeError) as exc:
                failed += 1
                log.debug("%s %s: %s", exchange_id, symbol, exc)
        matches.sort(key=lambda item: item[1], reverse=True)
        log.info("%s: checked %s pairs; %s errors; %s pumps",
                 exchange_id, len(symbols), failed, len(matches))
        return matches[:TOP_N], failed, len(symbols)
    finally:
        exchange.close()


def report(hour_ms):
    start = datetime.fromtimestamp(hour_ms / 1000, timezone.utc)
    end = datetime.fromtimestamp((hour_ms + 3600000) / 1000, timezone.utc)
    lines = [
        "🚀 <b>Crypto Pump Scanner — Spot</b>",
        f"🕒 {start:%d.%m.%Y %H:%M}–{end:%H:%M} UTC",
        f"📈 Порог: более {THRESHOLD:g}% за час",
    ]
    for exchange_id in EXCHANGES:
        lines.append(f"\n<b>{exchange_id.upper()}</b>")
        try:
            pumps, errors, total = scan(exchange_id, hour_ms)
            if pumps:
                for i, (symbol, pct) in enumerate(pumps, 1):
                    lines.append(f"{i}. {escape(symbol)}: +{pct:.2f}%")
            else:
                lines.append("Пампов выше порога не обнаружено")
            if errors:
                lines.append(f"⚠️ Ошибки пар: {errors}/{total}; данные неполные")
        except Exception as exc:
            log.exception("Exchange %s failed", exchange_id)
            lines.append(f"⚠️ Не удалось проверить биржу: {escape(str(exc)[:120])}")
    return "\n".join(lines)


def main():
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
    if THRESHOLD < 0:
        raise ValueError("PUMP_THRESHOLD must be nonnegative")
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    last_hour = None
    log.info("Pump scanner started")
    while RUNNING:
        now = time.time()
        hour_ms = (int(now // 3600) - 1) * 3600000
        ready_at = hour_ms / 1000 + 3600 + DELAY
        if now >= ready_at and hour_ms != last_hour:
            message = report(hour_ms)
            try:
                send(message)
                last_hour = hour_ms
            except Exception:
                log.exception("Telegram delivery failed; will retry")
        time.sleep(min(30, INTERVAL, max(1, ready_at - time.time())))


if __name__ == "__main__":
    main()
