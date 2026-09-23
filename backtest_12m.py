import os, io, math, json, time, zipfile, requests
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

# Strategy is intentionally ONLY the uploaded scanner logic:
# close > EMA200, volume > 5x 20-bar volume MA, close > prior 20-bar high.
# Entry: signal candle close.
# Exit: TSL activates only after +1% profit; no loss-side stop.
# Once activated, trail = peak * 0.99. No EOD exit; position remains open until TSL.
# No TOP_INPLAY / ranking / score filter.

# Capital model: one ₹2,00,000 position at a time.
# After an exit frees capital, the next chronological signal can enter.
CAPITAL = 200000.0

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
