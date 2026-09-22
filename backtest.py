#!/usr/bin/env python3
import os,time,gzip,json
from io import BytesIO,StringIO
from datetime import date,timedelta
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor,as_completed
import pandas as pd,requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TOKEN=os.environ["UPSTOX_ACCESS_TOKEN"].strip(); CAPITAL=float(os.getenv("DO_CAPITAL","200000"))
FOCUS_DATE=os.getenv("FOCUS_DATE","").strip(); IST="Asia/Kolkata"; OUT="backtest_results"; os.makedirs(OUT,exist_ok=True)
S=requests.Session(); S.mount("https://",HTTPAdapter(max_retries=Retry(total=3,backoff_factor=.5,status_forcelist=(429,500,502,503,504))))
S.headers.update({"Accept":"application/json","Authorization":f"Bearer {TOKEN}","User-Agent":"BEST-INTRADAY-RSI/1.0"}); last_req=0
def get(u,t=60):
 global last_req
 w=.1-(time.time()-last_req)
 if w>0: time.sleep(w)
 r=S.get(u,timeout=t); last_req=time.time()
 if r.status_code==429: time.sleep(2); r=S.get(u,timeout=t)
 r.raise_for_status(); return r
def candles(raw):
 if not raw:return pd.DataFrame(columns=["ts","o","h","l","c","v","oi"])
 d=pd.DataFrame(raw,columns=["ts","o","h","l","c","v","oi"]); d.ts=pd.to_datetime(d.ts,utc=True).dt.tz_convert(IST)
 for c in ["o","h","l","c","v","oi"]: d[c]=pd.to_numeric(d[c],errors="coerce")
 return d.sort_values("ts").reset_index(drop=True)
def historical(key,unit,interval,to_d,from_d):
 try:return candles(get(f"https://api.upstox.com/v3/historical-candle/{quote(key,safe='')}/{unit}/{interval}/{to_d}/{from_d}").json().get("data",{}).get("candles",[]))
 except Exception:return pd.DataFrame()
def nifty500():
 r=requests.get("https://en.wikipedia.org/wiki/NIFTY_500",headers={"User-Agent":"Mozilla/5.0"},timeout=30); r.raise_for_status()
 t=max(pd.read_html(StringIO(r.text)),key=lambda x:x.shape[0]); col=t.columns[2]
 for c in t.columns:
  if any(x in t[c].astype(str).str.upper().head(30).tolist() for x in ["RELIANCE","TCS","INFY","HDFCBANK"]): col=c; break
 return sorted({x.strip().upper() for x in t[col].astype(str) if x.isascii() and any(ch.isalpha() for ch in x)})
def instrument_map(symbols):
 r=get("https://assets.upstox.com/market-quote/instruments/exchange/complete.csv.gz",90); m=pd.read_csv(gzip.open(BytesIO(r.content),"rt"),low_memory=False)
 q=m[(m.exchange=="NSE_EQ")&m.instrument_type.isin(["EQ","EQUITY"])]; q=q[q.tradingsymbol.isin(symbols)].drop_duplicates("tradingsymbol")
 return q.set_index("tradingsymbol").instrument_key.to_dict()
def rsi(s,p=14):
 d=s.diff(); g=d.clip(lower=0); l=-d.clip(upper=0); ag=g.ewm(alpha=1/p,adjust=False,min_periods=p).mean(); al=l.ewm(alpha=1/p,adjust=False,min_periods=p).mean()
 x=100-100/(1+ag/al.replace(0,float("nan"))); return x.where(al!=0,100.0)
def daily_ok(d,day):
 x=d[d.ts.dt.date<day].copy()
 if len(x)<20:return False,None,None
 x["r"]=rsi(x.c); a,b=x.iloc[-2],x.iloc[-1]
 if pd.isna(a.r) or pd.isna(b.r):return False,None,None
 return bool(a.r<=30 and b.r>30),float(a.r),float(b.r)
def signal15(i,day):
 x=i[i.ts.dt.date==day].copy()
 if len(x)<20:return None
 x["r"]=rsi(x.c); x=x.dropna().reset_index(drop=True)
 for k in range(1,len(x)):
  cur,prev=float(x.r.iloc[k]),float(x.r.iloc[k-1]); recent=x.r.iloc[max(0,k-3):k]
  if len(recent) and float(recent.min())<=30 and prev<=30 and cur>30 and cur>prev:
   return {"ts":x.ts.iloc[k],"entry":float(x.c.iloc[k]),"rsi":cur,"touch":float(recent.min())}
 return None
def simulate(i,day,sig):
 pre=i[i.ts<=sig["ts"]].c; fut=i[(i.ts.dt.date==day)&(i.ts>sig["ts"])].copy()
 if fut.empty:return None
 rr=rsi(pd.concat([pre,fut.c],ignore_index=True)).iloc[-len(fut):].to_numpy()
 for z,(idx,b) in enumerate(fut.iterrows()):
  if rr[z]>=70:return float(b.c),"RSI70",b.ts
 return float(fut.c.iloc[-1]),"EOD",fut.ts.iloc[-1]
def main():
 end=date.fromisoformat(FOCUS_DATE) if FOCUS_DATE else date.today()-timedelta(days=1); start=end-timedelta(days=31); ds=end-timedelta(days=180)
 print(f"RSI BACKTEST {start} -> {end}"); syms=nifty500(); mp=instrument_map(syms); data={}
 def load(item):
  s,k=item; return s,historical(k,"days","1",end,ds),historical(k,"minutes","15",end,start)
 with ThreadPoolExecutor(max_workers=8) as ex:
  fs=[ex.submit(load,x) for x in mp.items()]
  for n,f in enumerate(as_completed(fs),1):
   try:
    s,d,i=f.result()
    if not d.empty and not i.empty:data[s]=(d,i)
   except Exception:pass
   if n%50==0:print("loaded",n)
 days=sorted({z for _,(_,i) in data.items() for z in i.ts.dt.date}); days=[end] if FOCUS_DATE and end in days else days
 trades=[]; signals=[]; cross=0
 for day in days:
  if day.weekday()>=5:continue
  for s,(d,i) in data.items():
   ok,dr0,dr1=daily_ok(d,day)
   if not ok:continue
   cross+=1; sig=signal15(i,day)
   if not sig:continue
   signals.append({"date":str(day),"symbol":s,"signal_time":sig["ts"].strftime("%H:%M:%S"),"daily_rsi_prev":dr0,"daily_rsi":dr1,"15m_touch_rsi":sig["touch"],"15m_signal_rsi":sig["rsi"],"entry":sig["entry"]})
   out=simulate(i,day,sig)
   if not out:continue
   ex,reason,xt=out; qty=max(1,int(CAPITAL//sig["entry"])); gross=(ex-sig["entry"])*qty; charges=(sig["entry"]+ex)*qty*.00035; net=gross-charges
   trades.append({"date":str(day),"symbol":s,"signal_time":sig["ts"].strftime("%H:%M:%S"),"exit_time":xt.strftime("%H:%M:%S"),"entry":sig["entry"],"exit":ex,"qty":qty,"gross_pnl":gross,"charges_est":charges,"net_pnl":net,"daily_rsi_prev":dr0,"daily_rsi":dr1,"15m_touch_rsi":sig["touch"],"15m_signal_rsi":sig["rsi"],"reason":reason})
 df=pd.DataFrame(trades); pd.DataFrame(signals).to_csv(f"{OUT}/signals.csv",index=False); df.to_csv(f"{OUT}/trades.csv",index=False)
 if df.empty: summary={"period":f"{start} to {end}","daily_cross_events":cross,"signals":len(signals),"trades":0}
 else:
  w=df[df.net_pnl>0].net_pnl; l=df[df.net_pnl<=0].net_pnl; eq=df.net_pnl.cumsum(); dd=eq-eq.cummax()
  summary={"period":f"{start} to {end}","daily_cross_events":cross,"signals":len(signals),"trades":len(df),"wins":int((df.net_pnl>0).sum()),"win_rate_pct":round(100*(df.net_pnl>0).mean(),2),"gross_pnl":round(df.gross_pnl.sum(),2),"estimated_charges":round(df.charges_est.sum(),2),"net_pnl":round(df.net_pnl.sum(),2),"avg_trade":round(df.net_pnl.mean(),2),"profit_factor":round(w.sum()/abs(l.sum()),3) if l.sum()<0 else None,"max_drawdown":round(dd.min(),2),"best_trade":round(df.net_pnl.max(),2),"worst_trade":round(df.net_pnl.min(),2),"rsi70_exits":int((df.reason=="RSI70").sum()),"eod_exits":int((df.reason=="EOD").sum())}
 summary["rules"]={"daily":"14 RSI: previous <=30 and latest >30 on completed daily candles","15m_entry":"recent 3 bars touched <=30, then RSI crosses above 30","target":"15m RSI >=70","stop":"none specified; EOD fallback"}
 with open(f"{OUT}/summary.json","w") as f:json.dump(summary,f,indent=2)
 print(json.dumps(summary,indent=2))
if __name__=="__main__":main()
