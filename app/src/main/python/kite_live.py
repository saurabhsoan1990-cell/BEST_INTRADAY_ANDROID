import csv
import io
import json
import os
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta

import requests

try:
    from kiteconnect import KiteConnect, KiteTicker
except Exception:
    KiteConnect = None
    KiteTicker = None

TOTAL_CAPITAL = 5_000_000.0
POSITION_CAPITAL = 200_000.0
MAX_POSITIONS = 25
VOLUME_MULTIPLE = 5.0
TSL_ACTIVATION = 0.01
TSL_TRAIL = 0.01
NSE_INSTRUMENTS_URL = "https://api.kite.trade/instruments/NSE"

class LiveEngine:
    def __init__(self, api_key, access_token, live=False):
        if KiteConnect is None or KiteTicker is None:
            raise RuntimeError("kiteconnect package is not installed")
        self.api_key = api_key.strip()
        self.access_token = access_token.strip()
        self.live = bool(live)
        self.kite = KiteConnect(api_key=self.api_key)
        self.kite.set_access_token(self.access_token)
        self.lock = threading.RLock()
        self.instruments = {}
        self.token_to_symbol = {}
        self.bars = defaultdict(lambda: deque(maxlen=260))
        self.current = {}
        self.last_cum_volume = {}
        self.positions = {}
        self.last_signal = {}
        self.running = False
        self.warming = False
        self.ticker = None
        self.events = deque(maxlen=200)
        home = os.environ.get("HOME", ".")
        self.state_path = os.path.join(home, "best_intraday", "kite_live_state.json")
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        self._load_state()

    def _log(self, typ, **kwargs):
        e = {"type": typ, "time": datetime.now().isoformat(timespec="seconds")}
        e.update(kwargs)
        self.events.appendleft(e)

    def _save_state(self):
        data = {"positions": self.positions, "last_signal": self.last_signal}
        tmp = self.state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, self.state_path)

    def _load_state(self):
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.positions = data.get("positions", {})
            self.last_signal = data.get("last_signal", {})
        except Exception:
            self.positions = {}
            self.last_signal = {}

    def load_nse_instruments(self):
        r = requests.get(NSE_INSTRUMENTS_URL, timeout=30)
        r.raise_for_status()
        rows = csv.DictReader(io.StringIO(r.text))
        for x in rows:
            if x.get("segment") != "NSE" or x.get("instrument_type") != "EQ":
                continue
            sym = x["tradingsymbol"]
            token = int(x["instrument_token"])
            self.instruments[sym] = {"token": token, "symbol": sym}
            self.token_to_symbol[token] = sym
        if len(self.instruments) < 100:
            raise RuntimeError("NSE instrument list did not load correctly")
        return len(self.instruments)

    def warmup(self):
        self.warming = True
        self._log("STATUS", message="Warming up 1-minute history; this can take a few minutes")
        end = datetime.now()
        start = end - timedelta(days=5)
        tokens = list(self.token_to_symbol.items())
        for i, (token, sym) in enumerate(tokens, 1):
            try:
                data = self.kite.historical_data(token, start, end, "minute", continuous=False, oi=False)
                q = self.bars[sym]
                for b in data[-260:]:
                    ts = b["date"]
                    if isinstance(ts, str):
                        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    q.append({"ts": ts.replace(second=0, microsecond=0), "o": float(b["open"]), "h": float(b["high"]), "l": float(b["low"]), "c": float(b["close"]), "v": float(b["volume"])})
            except Exception as exc:
                self._log("ERROR", message=f"Warmup failed {sym}: {exc}")
            time.sleep(0.34)
            if i % 50 == 0:
                self._log("STATUS", message=f"Warmup {i}/{len(tokens)} symbols")
        self.warming = False
        self._log("STATUS", message="Warmup complete")

    def _minute_key(self, ts):
        return ts.replace(second=0, microsecond=0)

    def _finalize_bar(self, sym, bar):
        self.bars[sym].append(bar)
        self.current.pop(sym, None)
        self.evaluate_completed_bar(sym)

    def on_ticks(self, ws, ticks):
        with self.lock:
            for tick in ticks:
                token = int(tick.get("instrument_token", 0))
                sym = self.token_to_symbol.get(token)
                if not sym:
                    continue
                ts = tick.get("exchange_timestamp") or datetime.now()
                minute = self._minute_key(ts)
                price = float(tick.get("last_price") or 0)
                cumulative = float(tick.get("volume_traded") or 0)
                cur = self.current.get(sym)
                if cur is None or cur["ts"] != minute:
                    if cur is not None:
                        self._finalize_bar(sym, cur)
                    prev_cumulative = self.last_cum_volume.get(token, cumulative)
                    self.last_cum_volume[token] = cumulative
                    delta = max(0.0, cumulative - prev_cumulative)
                    self.current[sym] = {"ts": minute, "o": price, "h": price, "l": price, "c": price, "v": delta}
                else:
                    prev_cumulative = self.last_cum_volume.get(token, cumulative)
                    delta = max(0.0, cumulative - prev_cumulative)
                    cur["h"] = max(cur["h"], price)
                    cur["l"] = min(cur["l"], price)
                    cur["c"] = price
                    cur["v"] = max(cur["v"], delta)
                self._check_position(sym, price)

    def _signal(self, sym):
        q = self.bars[sym]
        if len(q) < 220:
            return False, None
        closes = [b["c"] for b in q]
        highs = [b["h"] for b in q]
        vols = [b["v"] for b in q]
        ema = closes[0]
        alpha = 2.0 / 201.0
        for x in closes[1:]:
            ema = alpha * x + (1 - alpha) * ema
        prior20_high = max(highs[-21:-1])
        avg20 = sum(vols[-21:-1]) / 20.0
        last = q[-1]
        ok = last["c"] > ema and last["v"] >= VOLUME_MULTIPLE * avg20 and last["c"] > prior20_high
        return ok, {"ema200": ema, "vol20": avg20, "close": last["c"], "volume": last["v"], "prior20_high": prior20_high}

    def _check_position(self, sym, price):
        p = self.positions.get(sym)
        if not p:
            return
        if not p.get("active", False):
            if price >= p["entry"] * (1 + TSL_ACTIVATION):
                p["active"] = True
                p["peak"] = price
                self._save_state()
        else:
            p["peak"] = max(p.get("peak", price), price)
            stop = p["peak"] * (1 - TSL_TRAIL)
            if price <= stop:
                self._exit(sym, price, "TSL")

    def _order(self, sym, side, qty):
        if not self.live:
            return "PAPER"
        return self.kite.place_order(
            variety=self.kite.VARIETY_REGULAR,
            exchange=self.kite.EXCHANGE_NSE,
            tradingsymbol=sym,
            transaction_type=side,
            quantity=int(qty),
            product=self.kite.PRODUCT_CNC,
            order_type=self.kite.ORDER_TYPE_MARKET,
            market_protection=5,
            tag="BESTINTRADAY",
        )

    def _enter(self, sym, price, meta):
        if len(self.positions) >= MAX_POSITIONS or sym in self.positions:
            return
        qty = int(POSITION_CAPITAL // price)
        if qty <= 0:
            return
        oid = self._order(sym, self.kite.TRANSACTION_TYPE_BUY, qty)
        self.positions[sym] = {"entry": price, "qty": qty, "peak": price, "active": False, "order_id": oid, "entered": datetime.now().isoformat()}
        self._save_state()
        self._log("BUY", sym=sym, price=price, qty=qty, order=oid)

    def _exit(self, sym, price, reason):
        p = self.positions.get(sym)
        if not p:
            return
        oid = self._order(sym, self.kite.TRANSACTION_TYPE_SELL, p["qty"])
        pnl = (price - p["entry"]) * p["qty"]
        self._log("SELL", sym=sym, price=price, qty=p["qty"], pnl=pnl, reason=reason, order=oid)
        self.positions.pop(sym, None)
        self._save_state()

    def evaluate_completed_bar(self, sym):
        if len(self.positions) >= MAX_POSITIONS:
            return
        ok, meta = self._signal(sym)
        if not ok:
            return
        bar_ts = self.bars[sym][-1]["ts"].isoformat()
        if self.last_signal.get(sym) == bar_ts:
            return
        self.last_signal[sym] = bar_ts
        self._save_state()
        self._enter(sym, meta["close"], meta)

    def start(self):
        self.load_nse_instruments()
        self.warmup()
        tokens = list(self.token_to_symbol.keys())
        self.ticker = KiteTicker(self.api_key, self.access_token, reconnect=True, reconnect_max_tries=50, reconnect_max_delay=10)
        def on_connect(ws, response):
            ws.subscribe(tokens)
            ws.set_mode(ws.MODE_FULL, tokens)
            self._log("STATUS", message=f"Connected; streaming {len(tokens)} NSE equities")
        def on_close(ws, code, reason):
            self._log("STATUS", message=f"WebSocket closed: {code} {reason}")
        def on_error(ws, code, reason):
            self._log("ERROR", message=f"WebSocket error: {code} {reason}")
        self.ticker.on_ticks = self.on_ticks
        self.ticker.on_connect = on_connect
        self.ticker.on_close = on_close
        self.ticker.on_error = on_error
        self.running = True
        self.ticker.connect(threaded=True)

    def stop(self):
        self.running = False
        if self.ticker:
            try:
                self.ticker.close()
            except Exception:
                pass

    def snapshot(self):
        with self.lock:
            return {"running": self.running, "warming": self.warming, "live": self.live, "positions": self.positions.copy(), "events": list(self.events), "symbols": len(self.instruments)}
