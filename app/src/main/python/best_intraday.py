#!/usr/bin/env python3
"""
BEST_INTRADAY.py
================
Intraday stock picker — Nifty / F&O liquid names.

Yeh “saare YouTube indicators ek file” nahi hai.
Woh approach tere 325-trade log mein haar chuka.

Isme sirf woh rules hain jo:
  - O’Neil / Minervini / Qullamaggie / Aziz / Indian F&O desks
    KE SAATH overlap karte hain
  - AUR tere apex_trades.csv (Jun–Sep 2026, 325 trades, −38R)
    se toot-ke nikle

Tera log kya sikhaya
--------------------
  * Roz 5–6 naam = loss engine. Max 2.
  * T1 ~2.2R door → 325 mein se 1 baar laga. Bekaar target.
  * Beech mein trade +0.28R tak gaya, EOD tak −0.12R.
    Matlab pakde rehna maar-ta hai.
  * Din ka #1 score wala sabse zyada palta.
  * 14:00 ke baad ke naye naam kamzor.
  * Banks-heavy list ne kaata.

Isliye script:
  500 nahi, liquid universe
  har cycle MAX 2 (0/1 bhi allowed)
  target 0.6–0.8% (~Rs 1200–1600 on Rs 2L) — 2R nahi
  nikalne ke 3 rule print — broker SL optional
  14:15 ke baad naya naam nahi
  pehle se +3.5% bhaag chuka skip

Chalana
-------
  pip install pandas requests python-dateutil lxml
  export UPSTOX_ACCESS_TOKEN='...'   # optional for options; cash chal jata
  export DO_CAPITAL=200000
  python3 BEST_INTRADAY.py

  Historical same-time RVOL is cached in ./rvol_cache/ once per symbol/day.
"""

from __future__ import annotations

import hashlib
import os
import sys
import time
import gzip
import json
from io import BytesIO, StringIO
from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from urllib.parse import quote

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

IST = ZoneInfo("Asia/Kolkata")
ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN", "").strip()
CAPITAL = float(os.getenv("DO_CAPITAL", "200000"))
CYCLE_SEC = int(os.getenv("DO_CYCLE_SEC", "600"))
WORKERS = int(os.getenv("DO_WORKERS", "5"))
MIN_SCORE = float(os.getenv("DO_MIN_SCORE", "50"))
MAX_PICKS = 2
TOP_INPLAY = int(os.getenv("DO_TOP_INPLAY", "20"))
BATCH = 40

NIFTY_KEY = "NSE_INDEX|Nifty 50"
VIX_KEY = "NSE_INDEX|India VIX"
START = dtime(9, 20)
NO_NEW = dtime(14, 15)
END = dtime(15, 20)

STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "best_intraday_state.json")
RVOL_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rvol_cache")

req_lock = Lock()
last_req = 0.0
GAP = 0.08


def now() -> datetime:
    return datetime.now(IST)


def session() -> requests.Session:
    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=Retry(total=2, backoff_factor=0.4, status_forcelist=(429, 502, 503))))
    h = {"Accept": "application/json", "User-Agent": "best-intraday/3.0"}
    if ACCESS_TOKEN:
        h["Authorization"] = f"Bearer {ACCESS_TOKEN}"
    s.headers.update(h)
    return s


S = session()


def get(url: str, **kw):
    global last_req
    with req_lock:
        w = GAP - (time.time() - last_req)
        if w > 0:
            time.sleep(w)
        last_req = time.time()
    return S.get(url, timeout=kw.pop("timeout", 16), **kw)


def say(*a):
    print(*a, flush=True)


# ---------------------------------------------------------------------------
# Universe: Nifty 500 ∩ jo Upstox pe equity hai, phir sirf liquid
# ---------------------------------------------------------------------------
def nifty500() -> list[str]:
    r = requests.get(
        "https://en.wikipedia.org/wiki/NIFTY_500",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=25,
    )
    r.raise_for_status()
    tables = pd.read_html(StringIO(r.text))
    t = max(tables, key=lambda x: x.shape[0])
    if str(t.iloc[0, 2]).lower() in {"symbol", "ticker"}:
        t = t.iloc[1:]
    col = t.columns[2]
    for c in t.columns:
        sample = t[c].astype(str).str.upper().head(20).tolist()
        if any(x in sample for x in ("RELIANCE", "TCS", "INFY", "HDFCBANK")):
            col = c
            break
    return sorted(
        {
            s
            for s in t[col].astype(str).str.strip().str.upper()
            if s.isascii() and any(ch.isalpha() for ch in s) and s not in {"SYMBOL", "NAN"}
        }
    )


def instrument_map(symbols: list[str]) -> dict[str, str]:
    r = get("https://assets.upstox.com/market-quote/instruments/exchange/complete.csv.gz", timeout=60)
    r.raise_for_status()
    m = pd.read_csv(gzip.open(BytesIO(r.content), "rt"), low_memory=False)
    eq = m[(m["exchange"] == "NSE_EQ") & (m["instrument_type"].isin(["EQ", "EQUITY"]))].copy()
    eq["tradingsymbol"] = eq["tradingsymbol"].astype(str).str.strip()
    eq = eq[eq["tradingsymbol"].isin(symbols)]
    return eq.drop_duplicates("tradingsymbol").set_index("tradingsymbol")["instrument_key"].to_dict()


def candles(raw) -> pd.DataFrame:
    if not raw:
        return pd.DataFrame(columns=list("ts o h l c v oi".split()))
    df = pd.DataFrame(raw, columns=["ts", "o", "h", "l", "c", "v", "oi"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(IST)
    df = df.sort_values("ts").reset_index(drop=True)
    for c in "ohlcvoi":
        pass
    for c in ("o", "h", "l", "c", "v", "oi"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def fetch_daily(key: str) -> pd.DataFrame:
    to_d, fr = now().date(), now().date() - timedelta(days=120)
    url = f"https://api.upstox.com/v3/historical-candle/{quote(key, safe='')}/days/1/{to_d}/{fr}"
    res = get(url)
    if res.status_code != 200:
        return pd.DataFrame()
    return candles(res.json().get("data", {}).get("candles", []))


def fetch_5m(key: str) -> pd.DataFrame:
    url = f"https://api.upstox.com/v3/historical-candle/intraday/{quote(key, safe='')}/minutes/5"
    res = get(url)
    if res.status_code != 200:
        return pd.DataFrame()
    return candles(res.json().get("data", {}).get("candles", []))


def vwap(df: pd.DataFrame) -> float:
    tp = (df["h"] + df["l"] + df["c"]) / 3.0
    vol = df["v"].fillna(0.0)
    den = float(vol.sum())
    return float((tp * vol).sum() / den) if den else float(df["c"].iloc[-1])


def tr(df: pd.DataFrame) -> pd.Series:
    p = df["c"].shift(1)
    return pd.concat([(df["h"] - df["l"]).abs(), (df["h"] - p).abs(), (df["l"] - p).abs()], axis=1).max(axis=1)


# ---------------------------------------------------------------------------
# Score
# O’Neil: market + RS     Minervini: trend template-lite
# Aziz/Qullamaggie: in-play volume + location
# Tera log: kam naam, kam extension, subah-dopahar, jaldi target
# ---------------------------------------------------------------------------
def daily_feat(sym: str, d: pd.DataFrame, nifty: pd.DataFrame) -> dict | None:
    if d is None or len(d) < 60 or nifty is None or len(nifty) < 60:
        return None
    if d["ts"].iloc[-1].date() == now().date() and now().time() < dtime(15, 30):
        duse = d.iloc[:-1]
    else:
        duse = d
    if len(duse) < 60:
        return None
    c = duse["c"]
    ema20 = c.ewm(span=20, adjust=False).mean().iloc[-1]
    ema50 = c.ewm(span=50, adjust=False).mean().iloc[-1]
    px = float(c.iloc[-1])
    atr = float(tr(duse).rolling(14).mean().iloc[-1] or 0)
    adv = float(duse["v"].tail(20).mean())
    hi20 = float(duse["h"].tail(20).max())
    if atr <= 0 or adv <= 0:
        return None
    sret = float(c.iloc[-1] / c.iloc[-21] - 1) if len(c) > 21 else 0
    n = nifty
    if n["ts"].iloc[-1].date() == now().date() and now().time() < dtime(15, 30) and len(n) > 2:
        n = n.iloc[:-1]
    nret = float(n["c"].iloc[-1] / n["c"].iloc[-21] - 1) if len(n) > 21 else 0
    return {
        "sym": sym,
        "prev": px,
        "ema20": float(ema20),
        "ema50": float(ema50),
        "atr": atr,
        "adv": adv,
        "hi20": hi20,
        "rs_raw": sret - nret,
        "above": px > ema20 > 0 and px > ema50,
        "stack": ema20 > ema50,
    }


def attach_rs(rows: list[dict]) -> list[dict]:
    if not rows:
        return rows
    ordered = sorted(rows, key=lambda r: r["rs_raw"])
    n = max(len(ordered) - 1, 1)
    for i, r in enumerate(ordered):
        r["rs"] = 100.0 * i / n
    return rows


def session_today(intra: pd.DataFrame) -> pd.DataFrame:
    if intra is None or intra.empty:
        return pd.DataFrame()
    sess = intra[intra["ts"].dt.date == now().date()].copy()
    return sess if len(sess) >= 4 else intra.copy()


def orb_15(sess: pd.DataFrame) -> tuple[float, float] | None:
    """9:15–9:30 first three 5-min bars = 15-min opening range."""
    if sess.empty or "ts" not in sess.columns:
        return None
    t = sess["ts"].dt.time
    or_bars = sess[(t >= dtime(9, 15)) & (t < dtime(9, 30))]
    if len(or_bars) < 2:
        or_bars = sess.head(3)
    if or_bars.empty:
        return None
    return float(or_bars["h"].max()), float(or_bars["l"].min())


def _rvol_cache_path(key: str) -> str:
    """One historical RVOL cache file per instrument key per trading day."""
    os.makedirs(RVOL_CACHE_DIR, exist_ok=True)
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]
    return os.path.join(RVOL_CACHE_DIR, f"{now().date().isoformat()}_{digest}.pkl")


def _historical_intraday_volume(
    key: str,
    sessions: int = 20,
) -> list[pd.DataFrame]:
    """Fetch genuine historical 5-minute sessions, once per symbol per day.

    Upstox v3 date-range endpoint is limited to a 20-calendar-day window
    for this request. The result is persisted to disk so 10-minute scanner
    cycles do not repeatedly download the same historical data.
    """
    cache_path = _rvol_cache_path(key)

    try:
        if os.path.exists(cache_path):
            cached = pd.read_pickle(cache_path)
            if isinstance(cached, list) and len(cached) >= min(10, sessions):
                return cached[:sessions]
    except Exception:
        pass

    end_date = now().date() - timedelta(days=1)
    start_date = end_date - timedelta(days=20)
    url = (
        f"https://api.upstox.com/v3/historical-candle/"
        f"{quote(key, safe='')}/minutes/5/{end_date}/{start_date}"
    )

    try:
        res = get(url, timeout=30)
        if res.status_code != 200:
            return []

        raw = res.json().get("data", {}).get("candles", [])
        df = candles(raw)
        if df.empty:
            return []

        out = []
        for day in sorted(df["ts"].dt.date.unique(), reverse=True):
            s = df[df["ts"].dt.date == day].copy()
            # Normal NSE cash session has ~75 five-minute bars.
            if len(s) >= 50:
                out.append(s)
            if len(out) >= sessions:
                break

        # Cache only a genuinely useful history. Do not cache [] or a
        # partial history that would make the scanner silently degrade.
        if len(out) >= min(10, sessions):
            try:
                pd.to_pickle(out[:sessions], cache_path)
            except Exception:
                pass
            return out[:sessions]

        return []
    except Exception:
        return []


def _same_time_rvol(
    sess: pd.DataFrame,
    historical: list[pd.DataFrame] | None,
) -> float | None:
    """True same-time RVOL.

    Today's cumulative volume through the latest 5-min bar divided by the
    median cumulative volume through that exact clock time across historical
    sessions. Returns None when sufficient history is unavailable.
    """
    if sess.empty or not historical:
        return None

    last_t = sess["ts"].iloc[-1].time()
    today_vol = float(sess["v"].sum())
    if today_vol <= 0:
        return None

    hist_cum = []
    for h in historical:
        if h is None or h.empty:
            continue
        hs = h[h["ts"].dt.time <= last_t]
        if hs.empty:
            continue
        v = float(hs["v"].sum())
        if v > 0:
            hist_cum.append(v)

    # Require a meaningful sample; otherwise fail closed rather than
    # silently substituting a synthetic RVOL.
    if len(hist_cum) < 10:
        return None

    baseline = float(pd.Series(hist_cum).median())
    if baseline <= 0:
        return None
    return today_vol / baseline


def intra_pack(feat: dict, intra: pd.DataFrame, historical_intraday: list[pd.DataFrame] | None = None) -> dict | None:
    """Pehle raw pack — ranking ke baad score."""
    sess = session_today(intra)
    if len(sess) < 5:
        return None
    px = float(sess["c"].iloc[-1])
    if px < 50 or px > 20000:
        return None
    day_rvol = _same_time_rvol(sess, historical_intraday)
    if day_rvol is None:
        return None  # fail closed: no genuine same-time RVOL, no signal
    vw = vwap(sess)
    day_h, day_l = float(sess["h"].max()), float(sess["l"].min())
    chg = (px / feat["prev"] - 1) * 100
    rng = orb_15(sess)
    return {
        "feat": feat,
        "sess": sess,
        "px": px,
        "vw": vw,
        "day_h": day_h,
        "day_l": day_l,
        "chg": chg,
        "rvol": day_rvol,
        "or_h": rng[0] if rng else None,
        "or_l": rng[1] if rng else None,
    }


def score_pack(p: dict, rvol_rank: int, n5: pd.DataFrame | None = None) -> dict | None:
    feat, sess = p["feat"], p["sess"]
    px, vw, chg = p["px"], p["vw"], p["chg"]
    if chg >= 3.5:
        return None
    if px < vw:
        return None
    if p["or_h"] is None or px < p["or_h"]:
        return None  # must be above OR high
    # Fresh = previous 5-min close at/below OR high, this close above.
    prev_close = float(sess["c"].iloc[-2])
    if not (prev_close <= p["or_h"] < px):
        return None
    loc = (px - p["day_l"]) / max(p["day_h"] - p["day_l"], 0.01)
    if loc < 0.55:
        return None
    last = sess["c"].tail(4)
    if float(last.iloc[-1]) < float(last.iloc[0]):
        return None
    ext = (px - vw) / feat["atr"] if feat["atr"] else 0
    if ext > 1.6:
        return None
    # Manas Arora strong-start: gap hold (low didn't give back prev close)
    strong = p["day_l"] >= feat["prev"] * 0.995

    sc = 0.0
    why = []
    sc += max(0, 22 - rvol_rank)  # rank 1 = +21
    why.append(f"inplay#{rvol_rank}")
    why.append(f"rvol{p['rvol']:.2f}")
    if feat["stack"]:
        sc += 8
        why.append("trend")
    sc += min(12.0, max(0, feat["rs"] - 50) * 0.3)
    why.append(f"RS{feat['rs']:.0f}")
    # Same-day relative strength: stock should not merely look strong on a 20-day basis.
    n5 = n5 if n5 is not None else pd.DataFrame()
    if not n5.empty and len(n5) >= 2:
        n_intraday = (float(n5["c"].iloc[-1]) / float(n5["c"].iloc[0]) - 1) * 100
        stock_intraday = (px / float(sess["c"].iloc[0]) - 1) * 100
        intraday_rs = stock_intraday - n_intraday
        if intraday_rs > 0.30:
            sc += 6
            why.append(f"iRS{intraday_rs:+.2f}")
        elif intraday_rs < -0.30:
            sc -= 4
    sc += 10
    why.append("ORB+VWAP")
    if strong:
        sc += 8
        why.append("strong-start")
    if loc >= 0.8:
        sc += 8
        why.append("high")
    if 0.3 <= chg <= 2.2:
        sc += 10
        why.append("room")
    elif -0.3 <= chg < 0.3:
        sc += 6
        why.append("start")
    if 0.15 <= ext <= 0.9:
        sc += 6
    if sc < MIN_SCORE:
        return None
    qty = max(1, int(CAPITAL // px))
    # target = 1x opening-range (NSE ORB stack) capped ~1.2%
    or_w = (p["or_h"] - p["or_l"]) if p["or_h"] and p["or_l"] else px * 0.007
    t1 = round(min(px + or_w, px * 1.012), 2)
    t2 = round(min(px + 1.5 * or_w, px * 1.018), 2)
    band = round(max(p["or_l"], min(vw, (p["day_l"] + vw) / 2)), 2)
    return {
        "sym": feat["sym"],
        "px": round(px, 2),
        "chg": round(chg, 2),
        "rs": round(feat["rs"], 0),
        "vwap": round(vw, 2),
        "rvol": round(p["rvol"], 2),
        "rank": rvol_rank,
        "score": round(sc, 1),
        "why": ",".join(why),
        "qty": qty,
        "used": round(qty * px, 0),
        "t1": t1,
        "t2": t2,
        "band": band,
        "rs1500": round(CAPITAL * 0.0075, 0),
    }


def regime(nifty: pd.DataFrame) -> str:
    if nifty is None or len(nifty) < 30:
        return "UNKNOWN"
    d = nifty.copy()
    if d["ts"].iloc[-1].date() == now().date() and now().time() < dtime(15, 30):
        intra_n = fetch_5m(NIFTY_KEY)
        last_px = float(intra_n["c"].iloc[-1]) if not intra_n.empty else float(d["c"].iloc[-1])
        d = d.iloc[:-1]
    else:
        last_px = float(d["c"].iloc[-1])
    ema20 = d["c"].ewm(span=20, adjust=False).mean().iloc[-1]
    return "RISK_ON" if last_px >= float(ema20) else "RISK_OFF"


def print_picks(reg: str, rows: list[dict]):
    say("")
    say("#" * 90)
    say(f"  {now().strftime('%H:%M:%S')} IST   bazaar {reg}   naam {len(rows)}")
    say("#" * 90)
    if reg == "RISK_OFF":
        say("  Nifty EMA20 ke neeche. Sirf exceptional-score setup allowed; normal long skip.")
    if not rows:
        say("  Is cycle mein lene layak 0. Kachra mat kharid — yahi jeet hai.")
        say("#" * 90)
        return
    for i, r in enumerate(rows, 1):
        say(f"\n  {i}) {r['sym']}   Rs {r['px']}   {r['chg']:+.2f}%   RS {r['rs']:.0f}   score {r['score']}")
        say(f"     Share: {r['qty']}   (~Rs {r['used']:.0f})")
        say(f"     Pehla nikaal (0.7% ~ Rs {r['rs1500']:.0f}): {r['t1']}")
        say(f"     Doosra nikaal (1.2%): {r['t2']}")
        say(f"     Kyun: {r['why']}")
        say("     NIKAL:")
        say("       • 15–20 min mein upar nahi → nikal")
        say(f"       • 5-min BAND {r['band']} ke neeche band → nikal")
        say("       • 3:10 pe jo bacha → nikal")
        say("       • T1 laga to aadha nikal, baaki T2 / 3:10")
    say("\n" + "#" * 90)


def cycle(mapping: dict[str, str]):
    say(f"\n>>> {now().strftime('%H:%M:%S')}  {len(mapping)} naam scan")
    nifty = fetch_daily(NIFTY_KEY)
    reg = regime(nifty)
    say(f"    regime {reg}")

    feats = []
    items = list(mapping.items())

    def dwork(p):
        sym, key = p
        try:
            return daily_feat(sym, fetch_daily(key), nifty)
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for i, fut in enumerate(as_completed([ex.submit(dwork, p) for p in items]), 1):
            row = fut.result()
            if row:
                feats.append(row)
            if i % 80 == 0:
                say(f"    daily {i}/{len(items)}")

    feats = attach_rs(feats)
    short = [f for f in feats if f["above"] and f["rs"] >= 50]
    say(f"    daily survivors {len(short)}/{len(feats)}")

    packs = []

    # Current 5-minute data is refreshed every cycle.
    # Historical same-time RVOL data is disk-cached once per symbol per day.
    def iwork(f):
        try:
            key = mapping[f["sym"]]
            current = fetch_5m(key)
            historical = _historical_intraday_volume(key, sessions=20)
            return intra_pack(f, current, historical)
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for fut in as_completed([ex.submit(iwork, f) for f in short]):
            row = fut.result()
            if row:
                packs.append(row)

    packs.sort(key=lambda x: x["rvol"], reverse=True)
    inplay = packs[:TOP_INPLAY]
    say(f"    in-play top {len(inplay)} by TRUE same-time RVOL")
    say("    historical RVOL: disk-cached per symbol/day")
    if inplay:
        say("    RVOL leaders: " + ", ".join(f"{p['feat']['sym']} {p['rvol']:.2f}x" for p in inplay[:8]))

    n5 = session_today(fetch_5m(NIFTY_KEY))
    scored = []
    for i, p in enumerate(inplay, 1):
        row = score_pack(p, i, n5)
        if row:
            scored.append(row)

    scored.sort(key=lambda x: x["score"], reverse=True)
    picks = scored[:MAX_PICKS]
    if reg == "RISK_OFF":
        # Don't hard-zero every stock; require exceptional setups in a weak index regime.
        picks = [r for r in scored if r["score"] >= max(MIN_SCORE + 12, 62)][:MAX_PICKS]
    print_picks(reg, picks)
    try:
        with open(STATE, "w") as f:
            json.dump({"ts": now().isoformat(), "regime": reg, "picks": picks}, f, indent=2)
    except Exception:
        pass
    return picks


def main():
    say("BEST INTRADAY FINAL  |  paper-ready  |  true same-time RVOL  |  max 2")
    say(f"Capital Rs {CAPITAL:,.0f} | cycle {CYCLE_SEC//60} min | MIN_SCORE {MIN_SCORE}")
    try:
        syms = nifty500()
    except Exception as e:
        say("Nifty500 list fail", e)
        sys.exit(1)
    mapping = instrument_map(syms)
    say(f"map {len(mapping)}")
    if len(mapping) < 50:
        sys.exit(1)
    while True:
        t = now()
        if t.weekday() >= 5:
            time.sleep(120)
            continue
        if t.time() < START:
            say(f"wait 9:20  abhi {t.strftime('%H:%M:%S')}")
            time.sleep(20)
            continue
        if t.time() > END:
            say("band. kal.")
            time.sleep(60)
            continue
        t0 = time.time()
        try:
            if t.time() <= NO_NEW:
                cycle(mapping)
            else:
                say("14:15 ke baad naya naam nahi.")
                try:
                    old = json.load(open(STATE))
                    print_picks(old.get("regime", "?"), old.get("picks") or [])
                except Exception:
                    say("purana pick nahi")
        except Exception:
            import traceback
            traceback.print_exc()
        sleep = max(30, CYCLE_SEC - (time.time() - t0))
        say(f"agli cycle {sleep/60:.1f} min\n")
        time.sleep(sleep)


if __name__ == "__main__":
    main()
