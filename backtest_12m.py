import os, io, math, json, time, zipfile, requests
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

# Strategy is intentionally ONLY the uploaded scanner logic:
# close > EMA200, volume > 5x 20-bar volume MA, close > prior 20-bar high.
# Entry: signal candle close.
# Exit: TSL activates only after +1% profit; no loss-side stop.
# Once activated, trail = peak * 0.99. Otherwise force EOD exit.
# No TOP_INPLAY / ranking / score filter.

START = pd.Timestamp("2025-10-01", tz="Asia/Kolkata")
END   = pd.Timestamp("2026-09-30 23:59:59", tz="Asia/Kolkata")
OUT = "results"
os.makedirs(OUT, exist_ok=True)

REPOS = [
    ("2025", "ganeshbiyer/Nse_Historical_Data"),
    ("2026", "ganeshbiyer/Nse_Historical_Data_2026"),
]

def get_repo_files(repo):
    """Return {SYMBOL: fresh GitHub download URL} from the repo directory listing."""
    api=f"https://api.github.com/repos/{repo}/contents"
    r=requests.get(api, timeout=30, headers={"Accept":"application/vnd.github+json"})
    r.raise_for_status()
    data=r.json()
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected GitHub contents response for {repo}")
    return {x["name"][:-8]: x["download_url"] for x in data
            if x.get("type")=="file" and x.get("name","").endswith(".parquet") and x.get("download_url")}

def get_symbols():
    # Use the repository's Nifty-500 symbol list; fall back to parquet names.
    url="https://raw.githubusercontent.com/ganeshbiyer/Nse_Historical_Data/main/nifty500_symbols.csv"
    try:
        r=requests.get(url, timeout=30); r.raise_for_status()
        x=pd.read_csv(io.StringIO(r.text))
        col="Symbol" if "Symbol" in x.columns else x.columns[0]
        return sorted(set(x[col].astype(str).str.strip()))
    except Exception:
        return []

def load_one(symbol, file_urls):
    frames=[]
    for year, repo in REPOS:
        u=file_urls.get(year, {}).get(symbol)
        if not u: continue
        try:
            r=requests.get(u, timeout=90)
            r.raise_for_status()
            df=pd.read_parquet(io.BytesIO(r.content))
            frames.append(df)
        except Exception:
            continue
    if not frames: return None
    df=pd.concat(frames, ignore_index=True)
    df.columns=[str(c).lower() for c in df.columns]
    # Normalize common column names.
    ren={}
    for c in df.columns:
        if c in ("timestamp","datetime","date_time","date","time","ts"): ren[c]="ts"
        elif c in ("open","o"): ren[c]="o"
        elif c in ("high","h"): ren[c]="h"
        elif c in ("low","l"): ren[c]="l"
        elif c in ("close","c"): ren[c]="c"
        elif c in ("volume","v","vol"): ren[c]="v"
    df=df.rename(columns=ren)
    need={"ts","o","h","l","c","v"}
    if not need.issubset(df.columns):
        if isinstance(df.index, pd.MultiIndex) or df.index.name is not None:
            idx = df.reset_index()
            idx.columns = [str(x).lower() for x in idx.columns]
            df = idx
            ren = {}
            for col in df.columns:
                if col in ("timestamp","datetime","date_time","date","time","ts"): ren[col]="ts"
                elif col in ("open","o"): ren[col]="o"
                elif col in ("high","h"): ren[col]="h"
                elif col in ("low","l"): ren[col]="l"
                elif col in ("close","c"): ren[col]="c"
                elif col in ("volume","v","vol"): ren[col]="v"
            df = df.rename(columns=ren)
        if not need.issubset(df.columns):
            return None
    if not pd.api.types.is_datetime64_any_dtype(df.ts):
        df.ts=pd.to_datetime(df.ts, errors="coerce")
    if df.ts.dt.tz is None:
        df.ts=df.ts.dt.tz_localize("Asia/Kolkata", ambiguous="NaT", nonexistent="NaT")
    else:
        df.ts=df.ts.dt.tz_convert("Asia/Kolkata")
    df=df.dropna(subset=["ts","o","h","l","c","v"]).sort_values("ts")
    df=df[(df.ts>=START)&(df.ts<=END)]
    if df.empty: return None
    for c in ["o","h","l","c","v"]: df[c]=pd.to_numeric(df[c],errors="coerce")
    df=df.dropna(subset=["o","h","l","c","v"])
    return symbol,df

def backtest_symbol(symbol,df):
    # EMA and rolling volume/high are causal: signal at current close uses prior 20 highs.
    df=df.copy()
    df["ema200"]=df["c"].ewm(span=200,adjust=False).mean()
    df["vol_ma20"]=df["v"].rolling(20).mean()
    df["prior20h"]=df["h"].shift(1).rolling(20).max()
    df["signal"]=(df["c"]>df["ema200"])&(df["v"]>5.0*df["vol_ma20"])&(df["c"]>df["prior20h"])
    trades=[]
    pos=None
    cur_day=None
    rows=df.itertuples(index=False)
    for r in rows:
        day=r.ts.date()
        if cur_day is not None and day!=cur_day and pos is not None:
            # force prior-day EOD at last processed price
            trades.append([symbol,pos["entry_ts"],pos["entry"],r.ts-pd.Timedelta(minutes=1),pos["last"],"EOD"])
            pos=None
        cur_day=day
        # Manage existing position first.
        if pos is not None:
            pos["last"]=r.c
            if not pos["active"]:
                if r.h >= pos["entry"]*1.01:
                    pos["active"]=True
                    pos["peak"]=max(pos["entry"]*1.01,r.h)
                    # Do not stop on the same candle that activates; subsequent bars trail.
            else:
                pos["peak"]=max(pos["peak"],r.h)
                stop=pos["peak"]*0.99
                if r.l <= stop:
                    trades.append([symbol,pos["entry_ts"],pos["entry"],r.ts,stop,"TSL"])
                    pos=None
                    continue
        # One position per stock; enter on signal close.
        if pos is None and bool(r.signal):
            pos={"entry_ts":r.ts,"entry":float(r.c),"active":False,"peak":float(r.c),"last":float(r.c)}
    if pos is not None:
        # EOD final bar
        trades.append([symbol,pos["entry_ts"],pos["entry"],df.iloc[-1].ts,pos["last"],"EOD"])
    return trades

def main():
    file_urls={year:get_repo_files(repo) for year,repo in REPOS}
    syms=sorted(set(file_urls["2025"]) | set(file_urls["2026"]))
    print(f"Found {len(syms)} parquet symbols")
    all_trades=[]
    with ThreadPoolExecutor(max_workers=16) as ex:
        futs={ex.submit(load_one,s,file_urls):s for s in syms}
        for i,f in enumerate(as_completed(futs),1):
            try:
                z=f.result()
                if z:
                    all_trades.extend(backtest_symbol(*z))
            except Exception as e:
                print(f"ERROR {futs[f]}: {type(e).__name__}: {e}")
            if i%25==0: print(f"Processed {i}/{len(futs)} symbols")
    cols=["symbol","entry_ts","entry","exit_ts","exit","reason"]
    t=pd.DataFrame(all_trades,columns=cols)
    if t.empty:
        raise RuntimeError("No trades/data loaded")
    t["entry_ts"]=pd.to_datetime(t.entry_ts)
    t["exit_ts"]=pd.to_datetime(t.exit_ts)
    t["pnl_pct"]=(t.exit/t.entry-1)*100
    t["month"]=t.entry_ts.dt.strftime("%Y-%m")
    # Approximate rupee P&L per ₹1 lakh notional, useful for comparable month-wise output.
    t["pnl_per_lakh"]=t.pnl_pct*1000
    t.to_csv(f"{OUT}/trades.csv",index=False)
    m=t.groupby("month").agg(
        trades=("symbol","size"),
        tsl_exits=("reason",lambda x:(x=="TSL").sum()),
        eod_exits=("reason",lambda x:(x=="EOD").sum()),
        winners=("pnl_pct",lambda x:(x>0).sum()),
        losers=("pnl_pct",lambda x:(x<=0).sum()),
        pnl_pct=("pnl_pct","sum"),
        avg_trade_pct=("pnl_pct","mean"),
    ).reset_index()
    m["win_pct"]=m.winners/m.trades*100
    m.to_csv(f"{OUT}/monthly.csv",index=False)
    summary=pd.DataFrame([{
        "trades":len(t),
        "winners":int((t.pnl_pct>0).sum()),
        "losers":int((t.pnl_pct<=0).sum()),
        "win_pct":(t.pnl_pct>0).mean()*100,
        "total_pnl_pct":t.pnl_pct.sum(),
        "avg_trade_pct":t.pnl_pct.mean(),
        "tsl_exits":int((t.reason=="TSL").sum()),
        "eod_exits":int((t.reason=="EOD").sum()),
    }])
    summary.to_csv(f"{OUT}/summary.csv",index=False)
    print("\nMONTHLY RESULT\n")
    print(m.to_string(index=False))
    print("\nSUMMARY\n")
    print(summary.to_string(index=False))

if __name__=="__main__":
    main()
