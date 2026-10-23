"""Check the current RSI formula on a synthetic missing final close."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--phase0-root", type=Path,
                    default=Path(__file__).resolve().parents[1] / "phase0_20261023")
args = parser.parse_args()
if (args.phase0_root / "site_packages").exists():
    sys.path.insert(0, str(args.phase0_root / "site_packages"))
spec = importlib.util.spec_from_file_location("phase0_reproduction", args.phase0_root / "reproduce_current.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
import pandas as pd

prices = module.fixture()["Close"]["SOXX"]
prices.iloc[-1] = float("nan")
delta = prices.diff()
up = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
down = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
rsi = 100 - 100 / (1 + up / down)
assert pd.isna(prices.iloc[-1])
assert rsi.iloc[-1] == rsi.iloc[-2]
result = {"fixture": "synthetic; not original production payload",
          "pandas": pd.__version__, "last_date": str(prices.index[-1].date()),
          "last_valid_close_date": str(prices.last_valid_index().date()),
          "rsi_last": float(rsi.iloc[-1]), "rsi_previous": float(rsi.iloc[-2]),
          "equal": True, "network_calls": 0,
          "interpretation": "The current ewm formula retains the previous RSI on a missing final close."}
(Path(__file__).resolve().parent / "rsi_nan_check.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result))
