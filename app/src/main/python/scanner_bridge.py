import json
import threading
import upstox_6x_live

_LOCK = threading.RLock()


def start_engine(api_key, access_token, live=False, total_capital=5000000.0, position_capital=200000.0):
    # api_key is intentionally ignored: Upstox order/data APIs authenticate with the access token.
    with _LOCK:
        upstox_6x_live.start_engine(access_token, bool(live), float(total_capital), float(position_capital))
        return json.dumps({'ok':True,'live':bool(live),'total_capital':float(total_capital),'position_capital':float(position_capital),'volume_multiple':6.0})


def stop_engine():
    with _LOCK:
        upstox_6x_live.stop_engine()
    return json.dumps({'ok':True})


def snapshot():
    with _LOCK:
        return upstox_6x_live.snapshot()
