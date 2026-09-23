import json
import threading
import traceback

import kite_live

_ENGINE = None
_LOCK = threading.RLock()


def start_engine(api_key, access_token, live=False):
    global _ENGINE
    with _LOCK:
        if _ENGINE is not None:
            try:
                _ENGINE.stop()
            except Exception:
                pass
        _ENGINE = kite_live.LiveEngine(api_key, access_token, live=bool(live))
        count = _ENGINE.load_nse_instruments()
        _ENGINE.start()
        return json.dumps({"ok": True, "symbols": count, "live": bool(live)})


def stop_engine():
    global _ENGINE
    with _LOCK:
        if _ENGINE is not None:
            _ENGINE.stop()
        return json.dumps({"ok": True})


def snapshot():
    with _LOCK:
        if _ENGINE is None:
            return json.dumps({"ok": True, "running": False, "positions": {}, "events": []})
        out = _ENGINE.snapshot()
        out["ok"] = True
        return json.dumps(out, default=str)


def status():
    try:
        return snapshot()
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc), "traceback": traceback.format_exc()})
