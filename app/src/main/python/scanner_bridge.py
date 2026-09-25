import json
import threading
import upstox_6x_live

_LOCK = threading.RLock()


def start_engine(api_key, access_token, live=False, total_capital=5000000.0, position_capital=200000.0):
    with _LOCK:
        upstox_6x_live.start_engine(access_token, bool(live), float(total_capital), float(position_capital))
        return json.dumps({'ok': True, 'live': bool(live), 'total_capital': float(total_capital), 'position_capital': float(position_capital), 'volume_multiple': 6.0})


def stop_engine():
    with _LOCK:
        upstox_6x_live.stop_engine()
    return json.dumps({'ok': True})


def snapshot():
    with _LOCK:
        base = json.loads(upstox_6x_live.snapshot())
        engine = getattr(upstox_6x_live, '_engine', None)
        results = []
        if engine is not None:
            try:
                for key, df in list(engine.frames.items()):
                    if df is None or len(df) < upstox_6x_live.BREAKOUT_PERIOD + 1:
                        continue
                    sym = engine.symbol_by_key.get(key, key)
                    row = df.iloc[-1]
                    ind = upstox_6x_live._indicators(df)
                    if not ind:
                        continue
                    ema, vol_ma, prior_high = ind
                    price = float(row['c'])
                    volume = float(row['v'])
                    vol_multiple = (volume / vol_ma) if vol_ma and vol_ma > 0 else 0.0
                    above_ema = price > ema
                    breakout = price > prior_high
                    volume_ok = volume >= upstox_6x_live.VOLUME_MULTIPLIER * vol_ma if vol_ma else False
                    signal = above_ema and breakout and volume_ok
                    results.append({
                        'symbol': sym, 'price': price, 'volume': volume,
                        'volume_multiple': vol_multiple, 'ema200': float(ema),
                        'prior_high': float(prior_high), 'above_ema200': above_ema,
                        'breakout': breakout, 'volume_ok': volume_ok, 'signal': signal,
                        'updated': str(row['ts'])
                    })
            except Exception as e:
                base.setdefault('events', []).insert(0, {'type': 'ERROR', 'text': 'scan snapshot: ' + str(e)})
        results.sort(key=lambda x: (x['signal'], x['volume_multiple']), reverse=True)
        base['scan_results'] = results
        base['stocks_scanned'] = len(results)
        base['signals'] = [x for x in results if x['signal']]
        return json.dumps(base)
