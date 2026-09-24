from __future__ import annotations

import json, os, time, threading, requests
from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import StringIO, BytesIO
import gzip
import pandas as pd

IST = ZoneInfo('Asia/Kolkata')
API = 'https://api.upstox.com'
HFT = 'https://api-hft.upstox.com'
STATE_FILE = os.path.join(os.path.dirname(__file__), 'upstox_6x_state.json')

# LOCKED 6x BACKTEST RULES — do not change without an explicit strategy change.
VOLUME_MULTIPLIER = 6.0
EMA_PERIOD = 200
BREAKOUT_PERIOD = 20
VOLUME_MA_PERIOD = 20
TSL_ACTIVATION = 0.01
TSL_TRAIL = 0.01
MAX_POSITIONS_DEFAULT = 25

_lock = threading.RLock()
_engine = None


def _now():
    return datetime.now(IST)


def _headers(token):
    return {'Accept':'application/json','Content-Type':'application/json','Authorization':f'Bearer {token}'}


def _get(url, token, params=None, timeout=20):
    r = requests.get(url, headers=_headers(token), params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _post(url, token, payload, timeout=20):
    r = requests.post(url, headers=_headers(token), json=payload, timeout=timeout)
    if r.status_code >= 400:
        raise RuntimeError(f'HTTP {r.status_code}: {r.text[:400]}')
    return r.json()


def _load_state():
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {'date':str(_now().date()), 'events':[], 'trades':[], 'positions':{}, 'equity':None}


def _save_state(state):
    tmp = STATE_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False)
    os.replace(tmp, STATE_FILE)


def _nifty500():
    r = requests.get('https://en.wikipedia.org/wiki/NIFTY_500', headers={'User-Agent':'Mozilla/5.0'}, timeout=25)
    r.raise_for_status()
    tables = pd.read_html(StringIO(r.text))
    t = max(tables, key=lambda x:x.shape[0])
    candidates=[]
    for c in t.columns:
        vals=set(t[c].astype(str).str.upper().head(30))
        if {'RELIANCE','TCS','INFY'}.intersection(vals):
            candidates=t[c].astype(str).str.strip().str.upper().tolist(); break
    if not candidates:
        candidates=t.iloc[:,2].astype(str).str.strip().str.upper().tolist()
    return sorted({x for x in candidates if x.isascii() and any(ch.isalpha() for ch in x) and x not in {'SYMBOL','NAN'}})


def _instrument_map(symbols):
    u='https://assets.upstox.com/market-quote/instruments/exchange/complete.csv.gz'
    r=requests.get(u, timeout=60); r.raise_for_status()
    df=pd.read_csv(gzip.open(BytesIO(r.content),'rt'), low_memory=False)
    df=df[(df['exchange']=='NSE_EQ') & (df['instrument_type'].isin(['EQ','EQUITY']))]
    df['tradingsymbol']=df['tradingsymbol'].astype(str).str.upper().str.strip()
    df=df[df['tradingsymbol'].isin(symbols)].drop_duplicates('tradingsymbol')
    return {str(r.tradingsymbol):str(r.instrument_key) for r in df.itertuples()}


def _candles(key, token, start_date=None, end_date=None):
    if start_date and end_date:
        url=f"{API}/v3/historical-candle/{requests.utils.quote(key,safe='')}/minutes/1/{end_date}/{start_date}"
    else:
        url=f"{API}/v3/historical-candle/intraday/{requests.utils.quote(key,safe='')}/minutes/1"
    try:
        data=_get(url, token, timeout=30).get('data',{}).get('candles',[])
    except Exception:
        return pd.DataFrame(columns=['ts','o','h','l','c','v'])
    rows=[]
    for x in data:
        if len(x)>=6: rows.append([pd.to_datetime(x[0]),float(x[1]),float(x[2]),float(x[3]),float(x[4]),float(x[5])])
    if not rows: return pd.DataFrame(columns=['ts','o','h','l','c','v'])
    df=pd.DataFrame(rows,columns=['ts','o','h','l','c','v']).sort_values('ts').drop_duplicates('ts')
    return df.tail(500).reset_index(drop=True)


def _indicators(df):
    if len(df)<BREAKOUT_PERIOD+1: return None
    c=df.c
    ema=c.ewm(span=EMA_PERIOD, adjust=False).mean()
    vol_ma=df.v.rolling(VOLUME_MA_PERIOD).mean()
    prior_high=df.h.shift(1).rolling(BREAKOUT_PERIOD).max()
    return float(ema.iloc[-1]), float(vol_ma.iloc[-1]), float(prior_high.iloc[-1])


class Engine:
    def __init__(self, token, live, total, position):
        self.token=token; self.live=bool(live); self.total=float(total); self.position=float(position)
        self.max_positions=max(1,int(self.total//self.position))
        self.running=False; self.stop_evt=threading.Event(); self.thread=None
        self.state=_load_state(); self.state['date']=str(_now().date())
        self.frames={}; self.keys={}; self.symbol_by_key={}; self.last_candle={}; self.positions=self.state.get('positions',{}) or {}
        self.events=self.state.get('events',[]) or []; self.trades=self.state.get('trades',[]) or []
        self.streamer=None; self.lock=threading.RLock()

    def event(self, typ, sym='', price=None, text=''):
        e={'time':_now().isoformat(timespec='seconds'),'type':typ,'sym':sym}
        if price is not None: e['price']=float(price)
        if text: e['text']=text
        with self.lock:
            self.events.insert(0,e); self.events=self.events[:200]
            self.state['events']=self.events; self.state['positions']=self.positions; self.state['trades']=self.trades
            _save_state(self.state)

    def warmup_symbol(self, sym, key):
        # Two recent calendar days provide >200 one-minute bars for normal NSE sessions.
        end=_now().date()-timedelta(days=1); start=end-timedelta(days=4)
        df=_candles(key,self.token,start,end)
        if len(df)>=100: self.frames[key]=df.tail(300)

    def warmup(self):
        syms=_nifty500(); self.event('INFO',text=f'Loading Nifty 500 universe ({len(syms)})')
        mp=_instrument_map(syms)
        self.keys=mp; self.symbol_by_key={v:k for k,v in mp.items()}
        with ThreadPoolExecutor(max_workers=12) as ex:
            futs=[ex.submit(self.warmup_symbol,s,k) for s,k in mp.items()]
            for i,f in enumerate(as_completed(futs),1):
                try:f.result()
                except Exception:pass
                if i%50==0:self.event('INFO',text=f'Warmup {i}/{len(futs)}')
        self.event('INFO',text=f'Warmup ready: {len(self.frames)} symbols')

    def _feed_candle(self, key, candle):
        if len(candle)<6:return
        ts=pd.to_datetime(candle[0]); row={'ts':ts,'o':float(candle[1]),'h':float(candle[2]),'l':float(candle[3]),'c':float(candle[4]),'v':float(candle[5])}
        last=self.last_candle.get(key)
        if last==str(ts):
            df=self.frames.get(key)
            if df is not None and len(df):
                self.frames[key].iloc[-1]=[row[x] for x in ['ts','o','h','l','c','v']]
            return
        if last is None:
            self.last_candle[key]=str(ts); return
        self.last_candle[key]=str(ts)
        df=self.frames.get(key,pd.DataFrame(columns=['ts','o','h','l','c','v']))
        self.frames[key]=pd.concat([df,pd.DataFrame([row])],ignore_index=True).drop_duplicates('ts').tail(300).reset_index(drop=True)
        self.process_completed(key,row)

    def process_completed(self,key,r):
        sym=self.symbol_by_key.get(key,key)
        df=self.frames.get(key)
        if df is None or len(df)<EMA_PERIOD: return
        with self.lock:
            pos=self.positions.get(sym)
        if pos:
            if not pos['active']:
                if r['h']>=pos['entry']*(1+TSL_ACTIVATION):
                    pos['active']=True; pos['peak']=max(pos['entry']*(1+TSL_ACTIVATION),r['h'])
                    self.positions[sym]=pos; self.event('TSL_ON',sym,pos['entry'])
            else:
                pos['peak']=max(pos['peak'],r['h']); stop=pos['peak']*(1-TSL_TRAIL); pos['stop']=stop
                self.positions[sym]=pos
                if r['l']<=stop:
                    self.sell(sym,key,pos,stop,'TSL')
                    return
        if sym in self.positions: return
        if len(self.positions)>=self.max_positions:return
        ind=_indicators(df)
        if not ind:return
        ema,vol_ma,prior_high=ind
        signal=(r['c']>ema) and (r['v']>=VOLUME_MULTIPLIER*vol_ma) and (r['c']>prior_high)
        if signal:self.buy(sym,key,r['c'])

    def buy(self,sym,key,signal_price):
        qty=max(1,int(self.position//signal_price));
        if qty<=0:return
        fill=signal_price; order_id='MANUAL'
        if self.live:
            payload={'quantity':qty,'product':'D','validity':'DAY','price':0,'tag':'BEST6X','instrument_token':key,'order_type':'MARKET','transaction_type':'BUY','disclosed_quantity':0,'trigger_price':0,'is_amo':False,'slice':True,'market_protection':-1}
            try:
                res=_post(f'{HFT}/v3/order/place',self.token,payload); order_id=str(res.get('data',{}).get('order_id',''))
            except Exception as e:
                self.event('ERROR',sym,text=f'BUY failed: {e}'); return
        pos={'symbol':sym,'key':key,'qty':qty,'entry':fill,'signal_price':signal_price,'entry_time':_now().isoformat(timespec='seconds'),'active':False,'peak':fill,'stop':None,'buy_order_id':order_id}
        with self.lock:self.positions[sym]=pos
        self.event('BUY',sym,fill,f'qty={qty} order={order_id}')

    def sell(self,sym,key,pos,stop,reason):
        qty=int(pos['qty']); fill=stop; order_id='MANUAL'
        if self.live:
            payload={'quantity':qty,'product':'D','validity':'DAY','price':0,'tag':'BEST6XTSL','instrument_token':key,'order_type':'MARKET','transaction_type':'SELL','disclosed_quantity':0,'trigger_price':0,'is_amo':False,'slice':True,'market_protection':-1}
            try:
                res=_post(f'{HFT}/v3/order/place',self.token,payload); order_id=str(res.get('data',{}).get('order_id',''))
            except Exception as e:
                self.event('ERROR',sym,text=f'SELL failed: {e}'); return
        pnl=(fill-float(pos['entry']))*qty
        trade={'symbol':sym,'entry_time':pos['entry_time'],'entry':pos['entry'],'exit_time':_now().isoformat(timespec='seconds'),'exit':fill,'qty':qty,'pnl':pnl,'pnl_pct':(fill/pos['entry']-1)*100,'reason':reason,'buy_order_id':pos.get('buy_order_id'),'sell_order_id':order_id}
        with self.lock:
            self.trades.insert(0,trade); self.trades=self.trades[:1000]; self.positions.pop(sym,None)
        self.event('SELL',sym,fill,f'{reason} pnl={pnl:.2f}')

    def on_message(self,message):
        try:
            feeds=message.get('feeds',{}) if isinstance(message,dict) else {}
            for key,obj in feeds.items():
                # SDK json output can nest the full feed under ff/fullFeed/marketFF.
                def walk(x):
                    if isinstance(x,dict):
                        if 'marketOHLC' in x and isinstance(x['marketOHLC'],dict):
                            for c in x['marketOHLC'].get('ohlc',[]):
                                if c.get('interval') in ('I1','1m'):
                                    self._feed_candle(key,[c.get('ts'),c.get('open'),c.get('high'),c.get('low'),c.get('close'),c.get('vol',0)])
                        for v in x.values(): walk(v)
                    elif isinstance(x,list):
                        for v in x: walk(v)
                walk(obj)
        except Exception as e:self.event('ERROR',text=f'feed parse: {e}')

    def start_stream(self):
        import upstox_client
        cfg=upstox_client.Configuration(); cfg.access_token=self.token
        self.streamer=upstox_client.MarketDataStreamerV3(upstox_client.ApiClient(cfg),list(self.keys.values()),'full')
        self.streamer.on('message',self.on_message)
        self.streamer.on('error',lambda e:self.event('ERROR',text=f'feed error: {e}'))
        self.streamer.connect()

    def start(self):
        if self.running:return
        self.running=True
        self.thread=threading.Thread(target=self._run,name='best6x',daemon=True); self.thread.start()

    def _run(self):
        try:
            self.warmup()
            if self.stop_evt.is_set():return
            self.start_stream(); self.event('INFO',text=f'LIVE={self.live} • 6x • {self.max_positions} slots')
            while not self.stop_evt.wait(5): pass
        except Exception as e:self.event('ERROR',text=str(e))
        finally:
            self.running=False
            try:
                if self.streamer:self.streamer.disconnect()
            except Exception:pass

    def stop(self):
        self.stop_evt.set(); self.running=False
        try:
            if self.streamer:self.streamer.disconnect()
        except Exception:pass
        _save_state(self.state)

    def snapshot(self):
        funds={}
        if self.token:
            try: funds=_get(f'{API}/v3/user/get-funds-and-margin',self.token).get('data',{})
            except Exception: funds={}
        return {'running':self.running,'live':self.live,'strategy':'6x EMA200 + prior20 high + 20-bar volume MA; +1% activation; 1% TSL; no EOD exit','total_capital':self.total,'position_capital':self.position,'max_positions':self.max_positions,'positions':list(self.positions.values()),'trades':self.trades,'events':self.events,'funds':funds,'last_update':_now().isoformat(timespec='seconds')}


def start_engine(token,live,total,position):
    global _engine
    with _lock:
        if _engine is not None:_engine.stop()
        _engine=Engine(token,live,total,position); _engine.start()

def stop_engine():
    global _engine
    with _lock:
        if _engine:_engine.stop()
        _engine=None

def snapshot():
    with _lock:
        return json.dumps(_engine.snapshot() if _engine else {'running':False,'live':False,'strategy':'6x','positions':[],'trades':_load_state().get('trades',[]),'events':_load_state().get('events',[]),'funds':{}})
