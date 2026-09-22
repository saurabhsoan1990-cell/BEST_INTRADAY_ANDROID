#!/usr/bin/env python3
import os, time, gzip, hashlib, json
from io import BytesIO, StringIO
from datetime import date, timedelta, datetime, time as dtime
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TOKEN = os.environ["UPSTOX_ACCESS_TOKEN"].strip()
CAPITAL = float(os.getenv("DO_CAPITAL", "200000"))
FOCUS_DATE = os.getenv("FOCUS_DATE", "").strip()
MAX_PICKS = None  # unlimited signals; every qualifying stock can trigger
MIN_SCORE = 0.0  # diagnostic run: log the full raw score distribution
NIFTY_KEY = "NSE_INDEX|Nifty 50"
IST = "Asia/Kolkata"
OUT = "backtest_results"
os.makedirs(OUT, exist_ok=True)

S = requests.Session()
S.mount("https://", HTTPAdapter(max_retries=Retry(total=3, backoff_factor=.5, status_forcelist=(429,500,502,503,504))))
S.headers.update({"Accept":"application/json","Authorization":f"Bearer {TOKEN}","User-Agent":"BEST-INTRADAY-backtest/1.0"})
last_req = 0.0
def get(url, timeout=45):
    global last_req
    wait = .10 - (time.time()-last_req)
    if wait > 0: time.sleep(wait)
    r = S.get(url, timeout=timeout)
    last_req = time.time()
    if r.status_code == 429:
        time.sleep(2)
        r = S.get(url, timeout=timeout)
    r.raise_for_status()
    return r

def candles(raw):
    if not raw: return pd.DataFrame(columns=["ts","o","h","l","c","v","oi"])
    df=pd.DataFrame(raw,columns=["ts","o","h","l","c","v","oi"])
    df["ts"]=pd.to_datetime(df["ts"],utc=True).dt.tz_convert(IST)
    for c in ["o","h","l","c","v","oi"]: df[c]=pd.to_numeric(df[c],errors="coerce")
    return df.sort_values("ts").reset_index(drop=True)

def historical(key, unit, interval, to_d, from_d):
    url=f"https://api.upstox.com/v3/historical-candle/{quote(key,safe='')}/{unit}/{interval}/{to_d}/{from_d}"
    try: return candles(get(url).json().get("data",{}).get("candles",[]))
    except Exception: return pd.DataFrame()

def nifty500():
    r=requests.get("https://en.wikipedia.org/wiki/NIFTY_500",headers={"User-Agent":"Mozilla/5.0"},timeout=30)
    r.raise_for_status()
    tables=pd.read_html(StringIO(r.text))
    t=max(tables,key=lambda x:x.shape[0])
    col=t.columns[2]
    for c in t.columns:
        vals=t[c].astype(str).str.upper().head(30).tolist()
        if any(x in vals for x in ("RELIANCE","TCS","INFY","HDFCBANK")): col=c; break
    return sorted({x.strip().upper() for x in t[col].astype(str) if x.isascii() and any(ch.isalpha() for ch in x)})

def instrument_map(symbols):
    r=get("https://assets.upstox.com/market-quote/instruments/exchange/complete.csv.gz",timeout=90)
    m=pd.read_csv(gzip.open(BytesIO(r.content),"rt"),low_memory=False)
    eq=m[(m.exchange=="NSE_EQ") & (m.instrument_type.isin(["EQ","EQUITY"]))]
    eq=eq[eq.tradingsymbol.isin(symbols)].drop_duplicates("tradingsymbol")
    return eq.set_index("tradingsymbol").instrument_key.to_dict()

def tr(df):
    p=df.c.shift(1)
    return pd.concat([(df.h-df.l).abs(),(df.h-p).abs(),(df.l-p).abs()],axis=1).max(axis=1)

def daily_feat(sym,d,nifty,asof):
    d=d[d.ts.dt.date < asof].copy()
    n=nifty[nifty.ts.dt.date < asof].copy()
    if len(d)<60 or len(n)<60: return None
    c=d.c; nc=n.c
    ema20=c.ewm(span=20,adjust=False).mean().iloc[-1]
    ema50=c.ewm(span=50,adjust=False).mean().iloc[-1]
    px=float(c.iloc[-1]); atr=float(tr(d).rolling(14).mean().iloc[-1] or 0)
    if atr<=0: return None
    sret=float(c.iloc[-1]/c.iloc[-21]-1); nret=float(nc.iloc[-1]/nc.iloc[-21]-1)
    return {"sym":sym,"prev":px,"ema20":float(ema20),"ema50":float(ema50),"atr":atr,
            "rs_raw":sret-nret,"above":px>ema20 and px>ema50,"stack":ema20>ema50}

def attach_rs(rows):
    rows=sorted(rows,key=lambda x:x["rs_raw"])
    n=max(len(rows)-1,1)
    for i,r in enumerate(rows): r["rs"]=100*i/n
    return rows

def session_day(df,day):
    return df[df.ts.dt.date==day].copy()

def rvol_at(sess, hist, last_t):
    if sess.empty: return None
    today=float(sess[sess.ts.dt.time<=last_t].v.sum())
    vals=[]
    for h in hist:
        x=h[h.ts.dt.time<=last_t]
        if not x.empty and x.v.sum()>0: vals.append(float(x.v.sum()))
    if len(vals)<10: return None
    base=float(pd.Series(vals).median())
    return today/base if base else None

def vwap(df):
    if df.empty: return None
    tp=(df.h+df.l+df.c)/3
    return float((tp*df.v).sum()/df.v.sum()) if df.v.sum()>0 else float(df.c.iloc[-1])

def signal_pack(feat, daydf, hist, day, nifty5_day):
    s=session_day(daydf,day)
    if len(s)<5: return None
    orbars=s[(s.ts.dt.time>=dtime(9,15))&(s.ts.dt.time<dtime(9,30))]
    if len(orbars)<2: return None
    oh=float(orbars.h.max()); ol=float(orbars.l.min())
    prev_close=feat["prev"]

    # Find the first genuine breakout after the ORB using only candles available
    # at that moment. No full-day high/low/VWAP/volume is used for the signal.
    for idx in range(1,len(s)):
        bar=s.iloc[idx]
        if bar.ts.time()<dtime(9,30): continue
        prefix=s.iloc[:idx+1]
        prior=s.iloc[idx-1]
        px=float(bar.c)
        vw=vwap(prefix)
        rv=rvol_at(prefix,hist,bar.ts.time())
        if rv is None or vw is None: continue
        chg=(px/prev_close-1)*100
        if px<50 or px>20000 or chg>=3.5: continue
        if px<vw or px<oh: continue
        if float(prior.c)>oh or px<=oh: continue
        if not (float(prior.c)<=oh<px): continue

        dh=float(prefix.h.max()); dl=float(prefix.l.min())
        loc=(px-dl)/max(dh-dl,.01)
        if loc<.55: continue
        if float(prefix.c.tail(4).iloc[-1])<float(prefix.c.tail(4).iloc[0]): continue
        ext=(px-vw)/feat["atr"]
        if ext>1.6: continue

        ni_start=float(nifty5_day.c.iloc[0]) if not nifty5_day.empty else 0
        ncut=nifty5_day[nifty5_day.ts<=bar.ts]
        ni=float(ncut.c.iloc[-1]) if not ncut.empty else ni_start
        ni_pct=(ni/ni_start-1)*100 if ni_start else 0
        si=(px/float(prefix.c.iloc[0])-1)*100
        irs=si-ni_pct
        strong=dl>=prev_close*.995
        return {"feat":feat,"sess":prefix,"px":px,"vw":vw,"chg":chg,"rvol":rv,
                "or_h":oh,"or_l":ol,"day_l":dl,"day_h":dh,"signal_ts":bar.ts,
                "loc":loc,"ext":ext,"irs":irs,"strong":strong}
    return None

def score(p):
    f=p["feat"]; px=p["px"]; vw=p["vw"]; chg=p["chg"]
    sc=0  # rank-neutral: each qualifying stock is evaluated independently
    if f["stack"]: sc+=8
    sc+=min(12,max(0,(f["rs"]-50)*.3))
    if p["irs"]>.30: sc+=6
    elif p["irs"]<-.30: sc-=4
    sc+=10
    if p["strong"]: sc+=8
    if p["loc"]>=.8: sc+=8
    if .3<=chg<=2.2: sc+=10
    elif -.3<=chg<.3: sc+=6
    if .15<=p["ext"]<=.9: sc+=6
    if sc<MIN_SCORE: return None
    orw=p["or_h"]-p["or_l"]
    t1=min(px+orw,px*1.012); t2=min(px+1.5*orw,px*1.018)
    band=max(p["or_l"],min(vw,(p["day_l"]+vw)/2))
    return {"sym":f["sym"],"entry":px,"score":round(sc,1),"rvol":p["rvol"],
            "t1":t1,"t2":t2,"band":band,"signal_ts":p["signal_ts"]}

def simulate(pick, future, entry_ts):
    entry=pick["entry"]; t1=pick["t1"]; t2=pick["t2"]; band=pick["band"]
    for _,b in future.iterrows():
        ts=b.ts
        # Exit only by target or stop-loss. No 20-minute/time-based exit.
        if b.l<=band: return band-entry, "SL", ts
        if b.h>=t2: return t2-entry, "T2", ts
        if b.h>=t1: return t1-entry, "T1", ts
    # If neither target nor SL is hit by session end, close at EOD.
    return float(future.c.iloc[-1])-entry, "EOD", future.ts.iloc[-1]

def main():
    today=date.today()
    end=(date.fromisoformat(FOCUS_DATE) if FOCUS_DATE else today-timedelta(days=1))
    # Always fetch a normal intraday window; when focused, process only the requested day.
    start=end-timedelta(days=31)
    daily_start=end-timedelta(days=140)
    print(f"BACKTEST {start} -> {end}")
    syms=nifty500()
    mp=instrument_map(syms)
    print("universe",len(mp))
    nifty=historical(NIFTY_KEY,"days","1",end,daily_start)
    nifty5=historical(NIFTY_KEY,"minutes","5",end,start)
    if nifty.empty or nifty5.empty: raise RuntimeError("Nifty historical data unavailable")
    data={}
    def load(item):
        sym,key=item
        d=historical(key,"days","1",end,daily_start)
        i=historical(key,"minutes","5",end,start)
        return sym,d,i
    with ThreadPoolExecutor(max_workers=8) as ex:
        fs=[ex.submit(load,x) for x in mp.items()]
        for j,f in enumerate(as_completed(fs),1):
            try:
                sym,d,i=f.result()
                if not d.empty and not i.empty: data[sym]=(d,i)
            except Exception: pass
            if j%50==0: print("loaded",j)
    data_feats={day: attach_rs([f for f in (daily_feat(sym,d,nifty,day) for sym,(d,i) in data.items()) if f]) for day in sorted(set(nifty5.ts.dt.date))}
    days=sorted(set(nifty5.ts.dt.date))
    if FOCUS_DATE:
        days=[end] if end in days else []
    trades=[]
    signal_log=[]
    score_buckets={"<50":0,"50-59":0,"60-69":0,"70-79":0,"80+":0}
    for day in days:
        if day.weekday()>=5: continue
        feats=[f for f in data_feats.get(day,[]) if f["above"] and f["rs"]>=50]
        packs=[]
        n5=session_day(nifty5,day)
        for f in feats:
            i=data[f["sym"]][1]
            hist=[i[i.ts.dt.date==x].copy() for x in sorted(set(i.ts.dt.date)) if x<day]
            hist=[x for x in hist if len(x)>=50][-20:]
            p=signal_pack(f,i,hist,day,n5)
            if p: packs.append(p)
        # No TOP_INPLAY filter and no rank-based scoring: every qualifying stock
        # is evaluated independently, regardless of scan order or RVOL rank.
        scored=[]
        for p in packs:
            q=score(p)
            if q:
                if q["score"] < 50: score_buckets["<50"] += 1
                elif q["score"] < 60: score_buckets["50-59"] += 1
                elif q["score"] < 70: score_buckets["60-69"] += 1
                elif q["score"] < 80: score_buckets["70-79"] += 1
                else: score_buckets["80+"] += 1
                scored.append(q)
        scored=sorted(scored,key=lambda x:x["score"],reverse=True)
        selected={q["sym"] for q in scored}  # no daily top-N cap
        for q in scored:
            signal_log.append({"date":str(day),"signal_time":q["signal_ts"].strftime("%H:%M:%S"),"symbol":q["sym"],"score":q["score"],"rvol":q["rvol"],"selected":q["sym"] in selected})
        # Do not truncate: every scored qualifying signal is tradable.
        for q in scored:
            s=data[q["sym"]][1]
            fut=s[(s.ts.dt.date==day)&(s.ts>q["signal_ts"])]
            if fut.empty: continue
            entry_ts=q["signal_ts"]
            pnl,reason,exit_ts=simulate(q,fut,entry_ts)
            qty=max(1,int(CAPITAL//q["entry"]))
            gross=pnl*qty
            # Approximate retail cash-equity costs; exact broker plan can be substituted later.
            turnover=(q["entry"]+q["entry"]+pnl)*qty
            charges=max(0.0,turnover*0.00035)
            net=gross-charges
            trades.append({"date":str(day),"signal_time":q["signal_ts"].strftime("%H:%M:%S"),"exit_time":exit_ts.strftime("%H:%M:%S"),"symbol":q["sym"],"entry":q["entry"],"exit":q["entry"]+pnl,
                           "qty":qty,"gross_pnl":gross,"charges_est":charges,"net_pnl":net,
                           "score":q["score"],"rvol":q["rvol"],"reason":reason})
    df=pd.DataFrame(trades)
    df.to_csv(f"{OUT}/trades.csv",index=False)
    pd.DataFrame(signal_log).to_csv(f"{OUT}/signals.csv",index=False)
    if df.empty:
        summary={"trades":0}
    else:
        wins=df[df.net_pnl>0].net_pnl
        losses=df[df.net_pnl<=0].net_pnl
        eq=df.net_pnl.cumsum()
        dd=eq-eq.cummax()
        summary={"period":f"{start} to {end}","trades":int(len(df)),"wins":int((df.net_pnl>0).sum()),
                 "win_rate_pct":round(100*(df.net_pnl>0).mean(),2),
                 "gross_pnl":round(df.gross_pnl.sum(),2),"estimated_charges":round(df.charges_est.sum(),2),
                 "net_pnl":round(df.net_pnl.sum(),2),"avg_trade":round(df.net_pnl.mean(),2),
                 "profit_factor":round(wins.sum()/abs(losses.sum()),3) if losses.sum()<0 else None,
                 "max_drawdown":round(dd.min(),2),"best_trade":round(df.net_pnl.max(),2),
                 "worst_trade":round(df.net_pnl.min(),2),"max_consecutive_losses":0}
        streak=best=0
        for x in df.net_pnl:
            if x<=0: streak+=1; best=max(best,streak)
            else: streak=0
        summary["max_consecutive_losses"]=best
    summary["score_buckets"]=score_buckets
    with open(f"{OUT}/summary.json","w") as f: json.dump(summary,f,indent=2)
    print(json.dumps(summary,indent=2))
if __name__=="__main__": main()
