"""Pinned ad83f9b review probes. Synthetic input only; no live endpoints."""
import argparse, contextlib, io, json, os, shutil, subprocess, sys, types
from pathlib import Path

sys.dont_write_bytecode = True
parser = argparse.ArgumentParser()
parser.add_argument("--source-dir", required=True, help="Checkout/export of pinned candidate ad83f9b")
parser.add_argument("--site-packages", help="Optional local pandas/numpy dependency directory")
parser.add_argument("--output", help="Optional JSON result path")
args = parser.parse_args()
BASE = Path(args.source_dir).resolve()
sys.path.insert(0, str(BASE))
if args.site_packages:
    sys.path.insert(0, str(Path(args.site_packages).resolve()))
calls = []
def fake_post(url, **kwargs):
    calls.append(kwargs)
    return types.SimpleNamespace(status_code=204)
sys.modules["requests"] = types.SimpleNamespace(post=fake_post)
import pandas as pd
import numpy as np
import main, soxl_checks, soxl_notify

idx = pd.bdate_range(end="2026-10-23", periods=260)
base = np.linspace(100,200,260)
base[-12:] = np.linspace(base[-13], base[-13]*0.93,12)
spy=np.full(260,100.0); ief=np.full(260,100.0)
spy[-21:]=np.linspace(100,98,21); ief[-21:]=np.linspace(100,101,21)
close=pd.DataFrame({"SOXX":base,"SOXL":base*.3,"SPY":spy,"IEF":ief},index=idx)
open_=close*.995
target=pd.Timestamp("2026-10-23")
env={"DISCORD_WEBHOOK_URL":"https://invalid.example/SYNTHETIC",
     "TARGET_SESSION_DATE":"2026-10-23","SHEETS_ENABLED":"false"}
checks=[]
with contextlib.redirect_stdout(io.StringIO()):
    valid=main.run(env=env,fetch=lambda:(close,open_),post=fake_post)
checks.append({"name":"valid_control","exit":valid,"post_count":len(calls)})
assert valid==0 and len(calls)==1
checks.append({"name":"request_options","allow_redirects_present":"allow_redirects" in calls[0],
               "timeout":list(calls[0]["timeout"])})
original=soxl_checks.validate_and_compute(close,open_,target)
bad=close.copy()
bad.iloc[0,bad.columns.get_loc("SOXX")]=-1e9
changed=soxl_checks.validate_and_compute(bad,open_,target)
checks.append({"name":"negative_old_rsi_input","old_input":-1e9,"accepted":True,
              "control_rsi":original.rsi,"bad_rsi":changed.rsi,
              "control_conditions":bool(soxl_checks.technical_conditions(original)["all"]),
              "bad_conditions":bool(soxl_checks.technical_conditions(changed)["all"])})
calls.clear()
missing=close.copy(); missing.iloc[-1,0]=float("nan")
log=io.StringIO()
with contextlib.redirect_stdout(log):
    failure=main.run(env=env,fetch=lambda:(missing,open_),post=fake_post)
body=calls[0]["json"]["content"]
checks.append({"name":"invalid_latest_control","exit":failure,"post_count":len(calls),
              "target_in_message":("2026-10-23" in body or "2026/10/23" in body),
              "target_in_log":("2026-10-23" in log.getvalue() or "2026/10/23" in log.getvalue())})
assert failure==1 and len(calls)==1
curl = shutil.which("curl")
if curl:
    version = subprocess.run([curl, "--version"], capture_output=True, text=True, timeout=5).stdout.splitlines()[0]
    malformed = "http://127.0.0.1:1/[SYNTHETIC_WEBHOOK_TOKEN"
    report = subprocess.run([curl, "-sS", "-o", os.devnull, "-w", "%{http_code}",
                             "--max-time", "2", malformed],
                            capture_output=True, text=True, timeout=5)
    checks.append({"name":"curl_malformed_url_log", "curl_version":version,
                   "exit":report.returncode,
                   "synthetic_token_in_stderr":"SYNTHETIC_WEBHOOK_TOKEN" in report.stderr})
else:
    checks.append({"name":"curl_malformed_url_log", "status":"not run; curl unavailable"})
result={"source_commit":"ad83f9bf47c43f713e7cafb738f3de1bbb42705a",
        "environment":{"python":sys.version.split()[0],"pandas":pd.__version__,"numpy":np.__version__,
                       "requests":"stub; real redirects NOT executed"},
        "external_network_calls":0,"checks":checks}
if args.output:
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps(result,ensure_ascii=False))
