import subprocess, sys, re
R=sys.argv[1]
BASE="00094cc84287cbea977f6c94bfa8126ea2ea7daa"
def sh(*a, **k): return subprocess.run(a, cwd=R, capture_output=True, text=True, **k)
def edit(path, old, new, count=1):
    p=f"{R}/{path}"; t=open(p,encoding="utf-8").read()
    assert t.count(old)>=1, (path, old[:60]); open(p,"w",encoding="utf-8").write(t.replace(old,new,count))
MUTS = {
 "R1 drop END-is-ancestor-of-tip check": lambda: edit("tests/v2_scope_chain/sc_helpers.py",
     '            if r["end"] is not None and not ancestor(r["end"], tip):', '            if False:'),
 "R2 drop START-is-ancestor-of-END check": lambda: edit("tests/v2_scope_chain/sc_helpers.py",
     '            if not ancestor(r["start"], stop):', '            if False:'),
 "R3 sc_02 reads sc_03 REV again": lambda: edit("tests/v2_scope_chain/test_sc_02_chain.py",
     'TIP = "HEAD" ', 'from test_sc_03_scope import REV as TIP  # noqa\nTIP = TIP '),
 "R4 sc_02 tip is a fixed old commit": lambda: edit("tests/v2_scope_chain/test_sc_02_chain.py",
     'TIP = "HEAD" ', 'TIP = "dda7eb706637adc5f6dd37513e4b6ca360fde2ba" '),
 "R5 sc_02 drops every-range-on-chain check": lambda: edit("tests/v2_scope_chain/test_sc_02_chain.py",
     '        self.assertEqual(len(walked), len(self.rows))', '        pass'),
 "R6 judge accepts two open ranges": lambda: edit("tests/v2_scope_chain/sc_helpers.py",
     '    if len(opens) > 1:', '    if len(opens) > 2:'),
}
for name, f in MUTS.items():
    sh("git","checkout","-q","-f",BASE); sh("git","clean","-qfdx")
    try: f()
    except AssertionError as e: print(name, "SETUP-FAIL", e); continue
    sh("git","commit","-qam",name)
    out=sh(sys.executable,"-B","-m","unittest","discover","-s","tests/v2_scope_chain","-p","test_sc_*.py", env={"PYTHONDONTWRITEBYTECODE":"1","PATH":"/usr/bin:/bin"})
    fails=re.findall(r"^(?:FAIL|ERROR): (\S+) \((\S+)\)", out.stderr, re.M)
    print(f"{name}: {'DETECTED' if fails else 'SURVIVED'} {out.stderr.strip().splitlines()[-1]} {[f[0] for f in fails][:3]}")
sh("git","checkout","-q","-f",BASE)
