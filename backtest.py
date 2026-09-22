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
MAX_PICKS = 2
MIN_SCORE = 50.0
TOP_INPLAY = 20
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

def rvol(sess,hist):
    if sess.empty: return None
    last_t=sess.ts.iloc[-1].time()
    today=float(sess.v.sum())
    vals=[]
    for h in hist:
        x=h[h.ts.dt.time<=last_t]
        if not x.empty and x.v.sum()>0: vals.append(float(x.v.sum()))
    if len(vals)<10: return None
    base=float(pd.Series(vals).median())
    return today/base if base else None

def vwap(df):
    tp=(df.h+df.l+df.c)/3
    return float((tp*df.v).sum()/df.v.sum()) if df.v.sum()>0 else float(df.c.iloc[-1])

def pack(feat, daydf, hist, day):
    s=session_day(daydf,day)
    if len(s)<5: return None
    rv=rvol(s,hist)
    if rv is None: return None
    px=float(s.c.iloc[-1]); vw=vwap(s); chg=(px/feat["prev"]-1)*100
    if px<50 or px>20000 or chg>=3.5: return None
    orbars=s[(s.ts.dt.time>=dtime(9,15))&(s.ts.dt.time<dtime(9,30))]
    if len(orbars)<2: return None
    oh=float(orbars.h.max()); ol=float(orbars.l.min())
    if px<vw or px<oh or float(s.c.iloc[-2])>oh: return None
    if not (float(s.c.iloc[-2])<=oh<px): return None
    dh,dl=float(s.h.max()),float(s.l.min())
    loc=(px-dl)/max(dh-dl,.01)
    if loc<.55: return None
    if float(s.c.tail(4).iloc[-1])<float(s.c.tail(4).iloc[0]): return None
    ext=(px-vw)/feat["atr"]
    if ext>1.6: return None
    strong=dl>=feat["prev"]*.995
    return {"feat":feat,"sess":s,"px":px,"vw":vw,"chg":chg,"rvol":rv,"or_h":oh,"or_l":ol,"day_l":dl,"day_h":dh}

def score(p,rank,n5):
    f=p["feat"]; px=p["px"]; vw=p["vw"]; chg=p["chg"]
    sc=max(0,22-rank)
    if f["stack"]: sc+=8
    sc+=min(12,max(0,(f["rs"]-50)*.3))
    if len(n5)>=2:
        ni=(float(n5.c.iloc[-1])/float(n5.c.iloc[0])-1)*100
        si=(px/float(p["sess"].c.iloc[0])-1)*100
        irs=si-ni
        if irs>.30: sc+=6
        elif irs<-.30: sc-=4
    sc+=10
    if p["day_l"]>=f["prev"]*.995: sc+=8
    loc=(px-p["day_l"])/max(p["day_h"]-p["day_l"],.01)
    if loc>=.8: sc+=8
    if .3<=chg<=2.2: sc+=10
    elif -.3<=chg<.3: sc+=6
    ext=(px-vw)/f["atr"]
    if .15<=ext<=.9: sc+=6
    if sc<MIN_SCORE: return None
    orw=p["or_h"]-p["or_l"]
    t1=min(px+orw,px*1.012); t2=min(px+1.5*orw,px*1.018)
    band=max(p["or_l"],min(vw,(p["day_l"]+vw)/2))
    return {"sym":f["sym"],"entry":px,"score":round(sc,1),"rvol":p["rvol"],"t1":t1,"t2":t2,"band":band}

def simulate(pick, future, entry_ts):
    # Conservative bar execution: stop/band first, then targets. If target and stop
    # occur in the same 5-min bar, count the adverse exit first.
    entry=pick["entry"]; t1=pick["t1"]; t2=pick["t2"]; band=pick["band"]
    for _,b in future.iterrows():
        ts=b.ts
        if ts.time()>dtime(15,10): return float(b.c)-entry, "3:10"
        if b.l<=band: return band-entry, "band"
        if b.h>=t2: return t2-entry, "T2"
        if b.h>=t1: return t1-entry, "T1"
        # 20 minutes = four 5-min bars
        if ts >= entry_ts + pd.Timedelta(minutes=20):
            return float(b.c)-entry, "20m"
    return float(future.c.iloc[-1])-entry, "EOD"

def main():
    today=date.today()
    end=today-timedelta(days=1)
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
    trades=[]
    for day in days:
        if day.weekday()>=5: continue
        feats=[f for f in data_feats.get(day,[]) if f["above"] and f["rs"]>=50]
        packs=[]
        for f in feats:
            i=data[f["sym"]][1]
            hist=[i[i.ts.dt.date==x].copy() for x in sorted(set(i.ts.dt.date)) if x<day]
            hist=[x for x in hist if len(x)>=50][-20:]
            p=pack(f,i,hist,day)
            if p: packs.append(p)
        packs.sort(key=lambda x:x["rvol"],reverse=True)
        n5=session_day(nifty5,day)
        scored=[]
        for rank,p in enumerate(packs[:TOP_INPLAY],1):
            q=score(p,rank,n5)
            if q: scored.append(q)
        scored=sorted(scored,key=lambda x:x["score"],reverse=True)[:MAX_PICKS]
        for q in scored:
            s=data[q["sym"]][1]; fut=s[(s.ts.dt.date==day)&(s.ts>=(s.ts[s.ts.dt.time>=dtime(9,30)].iloc[0] if not s[s.ts.dt.time>=dtime(9,30)].empty else s.ts.iloc[0]))]
            if fut.empty: continue
            entry_ts=fut.ts.iloc[0]
            pnl,reason=simulate(q,fut.iloc[1:],entry_ts)
            qty=max(1,int(CAPITAL//q["entry"]))
            gross=pnl*qty
            # Approximate retail cash-equity costs; exact broker plan can be substituted later.
            turnover=(q["entry"]+q["entry"]+pnl)*qty
            charges=max(0.0,turnover*0.00035)
            net=gross-charges
            trades.append({"date":str(day),"symbol":q["sym"],"entry":q["entry"],"exit":q["entry"]+pnl,
                           "qty":qty,"gross_pnl":gross,"charges_est":charges,"net_pnl":net,
                           "score":q["score"],"rvol":q["rvol"],"reason":reason})
    df=pd.DataFrame(trades)
    df.to_csv(f"{OUT}/trades.csv",index=False)
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
    with open(f"{OUT}/summary.json","w") as f: json.dump(summary,f,indent=2)
    print(json.dumps(summary,indent=2))
if __name__=="__main__": main()
