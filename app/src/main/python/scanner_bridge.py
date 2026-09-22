import json
import os
import traceback

import best_intraday as scanner


def scan_once(capital, access_token):
    """
    Android bridge:
    runs exactly one scanner cycle and returns JSON.
    """
    try:
        scanner.CAPITAL = float(capital)
        scanner.ACCESS_TOKEN = str(access_token or "").strip()
        scanner.S = scanner.session()

        # APK assets are read-only. Put state/cache under Chaquopy's writable HOME.
        home = os.environ.get("HOME", ".")
        app_dir = os.path.join(home, "best_intraday")
        os.makedirs(app_dir, exist_ok=True)
        scanner.STATE = os.path.join(app_dir, "best_intraday_state.json")
        scanner.RVOL_CACHE_DIR = os.path.join(app_dir, "rvol_cache")

        syms = scanner.nifty500()
        mapping = scanner.instrument_map(syms)
        if len(mapping) < 50:
            return json.dumps({
                "ok": False,
                "error": "Upstox instrument map returned fewer than 50 symbols."
            })

        picks = scanner.cycle(mapping) or []
        result = {
            "ok": True,
            "regime": "UNKNOWN",
            "picks": picks,
        }

        # cycle() already writes state; use its returned picks for the UI.
        try:
            state_path = scanner.STATE
            if os.path.exists(state_path):
                with open(state_path, "r", encoding="utf-8") as fh:
                    state = json.load(fh)
                result["regime"] = state.get("regime", "UNKNOWN")
        except Exception:
            pass

        return json.dumps(result, default=str)

    except Exception as exc:
        return json.dumps({
            "ok": False,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        })
