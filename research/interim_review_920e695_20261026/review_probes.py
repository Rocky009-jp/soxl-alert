"""Four focused offline review paths for pinned candidate 920e695; not the 95-test suite."""
import argparse, contextlib, io, json, sys, types
from pathlib import Path
sys.dont_write_bytecode = True
ap=argparse.ArgumentParser()
ap.add_argument("--source-dir", required=True)
ap.add_argument("--site-packages")
ap.add_argument("--output")
args=ap.parse_args()
sys.path.insert(0,str(Path(args.source_dir).resolve()))
if args.site_packages:
    sys.path.insert(0,str(Path(args.site_packages).resolve()))
calls=[]
def fake_post(url, **kwargs):
    calls.append(kwargs)
    return types.SimpleNamespace(status_code=204)
sys.modules["requests"]=types.SimpleNamespace(post=fake_post)
import pandas as pd
import numpy as np
import main, soxl_checks
idx=pd.bdate_range(end="2026-10-23",periods=260)
prices=np.linspace(100,200,260)
prices[-12:]=np.linspace(prices[-13],prices[-13]*.93,12)
spy=np.full(260,100.); ief=np.full(260,100.)
spy[-21:]=np.linspace(100,98,21); ief[-21:]=np.linspace(100,101,21)
base=pd.DataFrame({"SOXX":prices,"SOXL":prices*.3,"SPY":spy,"IEF":ief},index=idx)
open_=base*.995
env={"DISCORD_WEBHOOK_URL":"https://invalid.example/SYNTHETIC",
     "TARGET_SESSION_DATE":"2026-10-23","SHEETS_ENABLED":"true",
     "GCP_CREDENTIALS":"SYNTHETIC_CREDENTIAL","SPREADSHEET_ID":"SYNTHETIC_SHEET"}
real_judge=soxl_checks.technical_conditions
observations=[]
for name in ["valid_control","old_negative","latest_missing","invalid_target"]:
    c=base.copy(); e=env.copy(); writes=[]; judged=[]; calls.clear()
    if name=="old_negative": c.iloc[0,0]=-1e9
    if name=="latest_missing": c.iloc[-1,0]=float("nan")
    if name=="invalid_target": e["TARGET_SESSION_DATE"]="SYNTHETIC_BAD_DATE"
    def judge(ind):
        judged.append(1)
        return real_judge(ind)
    soxl_checks.technical_conditions=judge
    log=io.StringIO()
    with contextlib.redirect_stdout(log):
        exit_code=main.run(env=e,fetch=lambda:(c,open_),write_row=lambda *a:writes.append(1),post=fake_post)
    body=calls[0]["json"]["content"]
    label="対象日未確定" if name=="invalid_target" else "2026/10/23"
    observed={"path":name,"exit":exit_code,"notifications":len(calls),"judgements":len(judged),
              "sheet_writes":len(writes),"redirects_disabled":calls[0].get("allow_redirects") is False,
              "target_in_message":label in body,"target_in_notify_log":label in log.getvalue()}
    assert exit_code==(0 if name=="valid_control" else 1)
    assert len(calls)==1 and calls[0].get("allow_redirects") is False
    assert len(judged)==(1 if name=="valid_control" else 0)
    assert len(writes)==(1 if name=="valid_control" else 0)
    assert label in body and label in log.getvalue()
    assert "SYNTHETIC_BAD_DATE" not in body+log.getvalue()
    observations.append(observed)
result={"source_commit":"920e69571cf4feda09f3f2f560e96fcb9cb09d50",
        "environment":{"python":sys.version.split()[0],"pandas":pd.__version__,"numpy":np.__version__,
                       "requests":"stub"},
        "external_data_or_notification_calls":0,"paths":observations,
        "not_executed":["original 95-test suite","real Requests redirects","YAML/bash curl reporter","Python 3.10 runtime"]}
if args.output:
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps(result,ensure_ascii=False))
