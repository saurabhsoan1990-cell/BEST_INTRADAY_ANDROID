import os, io, requests
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

CAPITAL = 5000000.0
START = pd.Timestamp("2025-10-01", tz="Asia/Kolkata")
END = pd.Timestamp("2026-09-30 23:59:59", tz="Asia/Kolkata")
OUT = "results"
os.makedirs(OUT, exist_ok=True)
REPOS = [("2025", "ganeshbiyer/Nse_Historical_Data"), ("2026", "ganeshbiyer/Nse_Historical_Data_2026")]

TSL_ACTIVATION = 0.01
TSL_TRAIL = 0.01


def get_repo_files(repo):
    api = f"https://api.github.com/repos/{repo}/contents"
    r = requests.get(api, timeout=30, headers={"Accept": "application/vnd.github+json"})
    r.raise_for_status()
    data = r.json()
    return {x["name"][:-8]: x["download_url"] for x in data if x.get("type") == "file" and x.get("name", "").endswith(".parquet") and x.get("download_url")}


def load_one(symbol, file_urls):
    frames = []
    for year, repo in REPOS:
        u = file_urls.get(year, {}).get(symbol)
        if not u:
            continue
        try:
            r = requests.get(u, timeout=90)
            r.raise_for_status()
            frames.append(pd.read_parquet(io.BytesIO(r.content)))
        except Exception:
            continue
    if not frames:
        return None
    df = pd.concat(frames, ignore_index=True)
    df.columns = [str(c).lower() for c in df.columns]
    ren = {}
    for c in df.columns:
        if c in ("timestamp", "datetime", "date_time", "date", "time", "ts"): ren[c] = "ts"
        elif c in ("open", "o"): ren[c] = "o"
        elif c in ("high", "h"): ren[c] = "h"
        elif c in ("low", "l"): ren[c] = "l"
        elif c in ("close", "c"): ren[c] = "c"
        elif c in ("volume", "v", "vol"): ren[c] = "v"
    df = df.rename(columns=ren)
    need = {"ts", "o", "h", "l", "c", "v"}
    if not need.issubset(df.columns):
        df = df.reset_index()
        df.columns = [str(x).lower() for x in df.columns]
        ren = {}
        for c in df.columns:
            if c in ("timestamp", "datetime", "date_time", "date", "time", "ts"): ren[c] = "ts"
            elif c in ("open", "o"): ren[c] = "o"
            elif c in ("high", "h"): ren[c] = "h"
            elif c in ("low", "l"): ren[c] = "l"
            elif c in ("close", "c"): ren[c] = "c"
            elif c in ("volume", "v", "vol"): ren[c] = "v"
        df = df.rename(columns=ren)
        if not need.issubset(df.columns):
            return None
    if not pd.api.types.is_datetime64_any_dtype(df.ts):
        df.ts = pd.to_datetime(df.ts, errors="coerce")
    if df.ts.dt.tz is None:
        df.ts = df.ts.dt.tz_localize("Asia/Kolkata", ambiguous="NaT", nonexistent="NaT")
    else:
        df.ts = df.ts.dt.tz_convert("Asia/Kolkata")
    df = df.dropna(subset=["ts", "o", "h", "l", "c", "v"]).sort_values("ts")
    df = df[(df.ts >= START) & (df.ts <= END)]
    if df.empty:
        return None
    for c in ["o", "h", "l", "c", "v"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return symbol, df.dropna(subset=["o", "h", "l", "c", "v"])


def backtest_symbol(symbol, df):
    df = df.copy()
    df["ema200"] = df.c.ewm(span=200, adjust=False).mean()
    df["vol_ma20"] = df.v.rolling(20).mean()
    df["prior20h"] = df.h.shift(1).rolling(20).max()
    df["signal"] = (df.c > df.ema200) & (df.v > 5.0 * df.vol_ma20) & (df.c > df.prior20h)
    trades = []
    pos = None
    for r in df.itertuples(index=False):
        if pos is not None:
            if not pos["active"]:
                if r.h >= pos["entry"] * (1 + TSL_ACTIVATION):
                    pos["active"] = True
                    pos["peak"] = max(pos["entry"] * (1 + TSL_ACTIVATION), float(r.h))
            else:
                pos["peak"] = max(pos["peak"], float(r.h))
                stop = pos["peak"] * (1 - TSL_TRAIL)
                if r.l <= stop:
                    trades.append([symbol, pos["entry_ts"], pos["entry"], r.ts, stop, "TSL"])
                    pos = None
                    continue
        if pos is None and bool(r.signal):
            pos = {"entry_ts": r.ts, "entry": float(r.c), "active": False, "peak": float(r.c)}
    return trades


def main():
    os.makedirs(OUT, exist_ok=True)
    file_urls = {year: get_repo_files(repo) for year, repo in REPOS}
    syms = sorted(set(file_urls["2025"]) | set(file_urls["2026"]))
    print(f"Found {len(syms)} parquet symbols")
    candidates = []
    with ThreadPoolExecutor(max_workers=16) as ex:
        futs = {ex.submit(load_one, s, file_urls): s for s in syms}
        for i, f in enumerate(as_completed(futs), 1):
            try:
                z = f.result()
                if z:
                    candidates.extend(backtest_symbol(*z))
            except Exception as e:
                print(f"ERROR {futs[f]}: {type(e).__name__}: {e}")
            if i % 25 == 0:
                print(f"Processed {i}/{len(futs)} symbols")
    if not candidates:
        raise RuntimeError("No trades/data loaded")
    cols = ["symbol", "entry_ts", "entry", "exit_ts", "exit", "reason"]
    raw = pd.DataFrame(candidates, columns=cols)
    raw.entry_ts = pd.to_datetime(raw.entry_ts)
    raw.exit_ts = pd.to_datetime(raw.exit_ts)
    raw = raw.sort_values(["entry_ts", "symbol"]).reset_index(drop=True)
    accepted = []
    capital_free_at = START
    for r in raw.itertuples(index=False):
        if r.entry_ts >= capital_free_at:
            accepted.append(r)
            capital_free_at = r.exit_ts
    t = pd.DataFrame(accepted, columns=cols)
    if t.empty:
        raise RuntimeError("No accepted trades after ₹50 lakh capital constraint")
    t["pnl_pct"] = (t.exit / t.entry - 1) * 100
    t["capital"] = CAPITAL
    t["pnl_rupees"] = CAPITAL * (t.exit / t.entry - 1)
    t["capital_after"] = CAPITAL + t.pnl_rupees
    t["month"] = t.entry_ts.dt.strftime("%Y-%m")
    os.makedirs(OUT, exist_ok=True)
    t.to_csv(f"{OUT}/trades.csv", index=False)
    m = t.groupby("month").agg(trades=("symbol", "size"), tsl_exits=("reason", lambda x: (x == "TSL").sum()), winners=("pnl_pct", lambda x: (x > 0).sum()), losers=("pnl_pct", lambda x: (x <= 0).sum()), pnl_pct=("pnl_pct", "sum"), avg_trade_pct=("pnl_pct", "mean"), pnl_rupees=("pnl_rupees", "sum")).reset_index()
    m["win_pct"] = m.winners / m.trades * 100
    m.to_csv(f"{OUT}/monthly.csv", index=False)
    equity = CAPITAL
    rows = []
    for r in t.itertuples(index=False):
        equity *= r.exit / r.entry
        rows.append([r.exit_ts, r.symbol, equity])
    eq = pd.DataFrame(rows, columns=["ts", "symbol", "equity"])
    eq.to_csv(f"{OUT}/equity_curve.csv", index=False)
    final = float(eq.iloc[-1].equity)
    summary = pd.DataFrame([{"starting_capital": CAPITAL, "final_equity": final, "net_profit": final - CAPITAL, "return_pct": (final / CAPITAL - 1) * 100, "trades": len(t), "winners": int((t.pnl_pct > 0).sum()), "losers": int((t.pnl_pct <= 0).sum()), "win_pct": (t.pnl_pct > 0).mean() * 100, "avg_trade_pct": t.pnl_pct.mean(), "tsl_exits": int((t.reason == "TSL").sum()), "eod_exits": 0, "strategy": "EMA200 + volume > 5x 20-bar volume MA + close > prior 20-bar high; 1% activation; 1% TSL; no EOD exit"}])
    summary.to_csv(f"{OUT}/summary.csv", index=False)
    print("\nMONTHLY RESULT\n", m.to_string(index=False), "\n\nSUMMARY\n", summary.to_string(index=False))


if __name__ == "__main__":
    main()
