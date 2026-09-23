import io, os, requests
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

TOTAL=5_000_000.0; SLOT=200_000.0; MAXP=25
START=pd.Timestamp('2024-10-01',tz='Asia/Kolkata'); END=pd.Timestamp('2025-09-30 23:59:59',tz='Asia/Kolkata')
REPO='ganeshbiyer/Nse_Historical_Data'; OUT='results_correction_2024_25'; os.makedirs(OUT,exist_ok=True)

def files():
 r=requests.get(f'https://api.github.com/repos/{REPO}/contents',timeout=30); r.raise_for_status()
 return {x['name'][:-8]:x['download_url'] for x in r.json() if x.get('type')=='file' and x.get('name','').endswith('.parquet') and x.get('download_url')}

def load(item):
 s,u=item
 try:
  r=requests.get(u,timeout=90); r.raise_for_status(); d=pd.read_parquet(io.BytesIO(r.content)); d.columns=[str(c).lower() for c in d.columns]
  ren={}
  for c in d.columns:
   if c in ('timestamp','datetime','date_time','date','time','ts'): ren[c]='ts'
   elif c in ('open','o'): ren[c]='o'
   elif c in ('high','h'): ren[c]='h'
   elif c in ('low','l'): ren[c]='l'
   elif c in ('close','c'): ren[c]='c'
   elif c in ('volume','v','vol'): ren[c]='v'
  d=d.rename(columns=ren)
  if not {'ts','o','h','l','c','v'}.issubset(d.columns): return None
  d.ts=pd.to_datetime(d.ts,errors='coerce')
  if d.ts.dt.tz is None: d.ts=d.ts.dt.tz_localize('Asia/Kolkata',ambiguous='NaT',nonexistent='NaT')
  else: d.ts=d.ts.dt.tz_convert('Asia/Kolkata')
  d=d.dropna(subset=['ts','o','h','l','c','v']).sort_values('ts'); d=d[(d.ts>=START)&(d.ts<=END)]
  if d.empty:return None
  for c in ['o','h','l','c','v']: d[c]=pd.to_numeric(d[c],errors='coerce')
  d=d.dropna(subset=['o','h','l','c','v'])
  d['ema200']=d.c.ewm(span=200,adjust=False).mean(); d['vma20']=d.v.rolling(20).mean(); d['prior20h']=d.h.shift(1).rolling(20).max()
  d['signal']=(d.c>d.ema200)&(d.v>5*d.vma20)&(d.c>d.prior20h)
  pos=None; out=[]
  for x in d.itertuples(index=False):
   if pos:
    if not pos['active']:
     if x.h>=pos['entry']*1.01: pos['active']=True; pos['peak']=max(pos['entry']*1.01,float(x.h))
    else:
     pos['peak']=max(pos['peak'],float(x.h)); stop=pos['peak']*.99
     if x.l<=stop: out.append([s,pos['entry_ts'],pos['entry'],x.ts,stop]); pos=None; continue
   if pos is None and bool(x.signal): pos={'entry_ts':x.ts,'entry':float(x.c),'active':False,'peak':float(x.c)}
  return out
 except Exception as e:
  print('ERROR',s,type(e).__name__,e); return None

def main():
 fs=files(); print('Found',len(fs),'symbols')
 alltr=[]
 with ThreadPoolExecutor(max_workers=16) as ex:
  futs=[ex.submit(load,x) for x in fs.items()]
  for i,f in enumerate(as_completed(futs),1):
   z=f.result()
   if z: alltr.extend(z)
   if i%25==0: print('Processed',i,'/',len(futs))
 if not alltr: raise RuntimeError('No trades')
 cols=['symbol','entry_ts','entry','exit_ts','exit']; raw=pd.DataFrame(alltr,columns=cols).sort_values(['entry_ts','symbol']).reset_index(drop=True)
 accepted=[]; opens=[]
 for r in raw.itertuples(index=False):
  opens=[x for x in opens if x.exit_ts>r.entry_ts]
  if len(opens)<MAXP: accepted.append(r); opens.append(r)
 t=pd.DataFrame(accepted,columns=cols); t['pnl_pct']=(t.exit/t.entry-1)*100; t['pnl_rupees']=SLOT*(t.exit/t.entry-1); t['month']=t.entry_ts.dt.strftime('%Y-%m'); t.to_csv(f'{OUT}/trades.csv',index=False)
 m=t.groupby('month').agg(trades=('symbol','size'),winners=('pnl_pct',lambda x:(x>0).sum()),losers=('pnl_pct',lambda x:(x<=0).sum()),pnl_rupees=('pnl_rupees','sum')).reset_index(); m['win_pct']=m.winners/m.trades*100; m.to_csv(f'{OUT}/monthly.csv',index=False)
 eq=TOTAL+t.sort_values(['exit_ts','symbol']).pnl_rupees.cumsum(); final=float(eq.iloc[-1]);
 summary=pd.DataFrame([{'period':'2024-10-01 to 2025-09-30','starting_capital':TOTAL,'position_capital':SLOT,'max_concurrent_positions':MAXP,'final_equity':final,'net_profit':final-TOTAL,'return_pct':(final/TOTAL-1)*100,'trades':len(t),'winners':int((t.pnl_pct>0).sum()),'losers':int((t.pnl_pct<=0).sum()),'win_pct':(t.pnl_pct>0).mean()*100,'tsl_exits':len(t),'eod_exits':0}]); summary.to_csv(f'{OUT}/summary.csv',index=False); print('\nMONTHLY\n',m.to_string(index=False),'\n\nSUMMARY\n',summary.to_string(index=False))
if __name__=='__main__': main()
