import subprocess, sys, re
R=sys.argv[1]
BASE="584b406ad8707dab1ccf1c77e209f870ade234f4"
def sh(*a, **k): return subprocess.run(a, cwd=R, capture_output=True, text=True, **k)
def edit(path, old, new, count=1):
    p=f"{R}/{path}"; t=open(p,encoding="utf-8").read()
    assert t.count(old)>=1, (path, old[:60]); open(p,"w",encoding="utf-8").write(t.replace(old,new,count))
MUTS = {
 "R1 drop END-is-ancestor-of-tip check": lambda: edit("tests/v2_scope_chain/sc_helpers.py",
     '            if r["end"] is not None and not ancestor(r["end"], tip):', '            if False:'),
 "R2 drop START-is-ancestor-of-END check": lambda: edit("tests/v2_scope_chain/sc_helpers.py",
     '            if not ancestor(r["start"], stop):', '            if False:'),
 "R5 b17 module docstring changed": lambda: edit("tests/v2_history_ops/test_b17_scope.py",
     'existing file other than the two allowed ones differs', 'existing file other than the allowed ones differs'),
 "R6 d5_08 extra top-level function": lambda: edit("tests/v2_history_diagnose/test_d5_08_scope.py",
     '\ndef git_show_at_end(path):', '\ndef extra_helper():\n    return None\n\n\ndef git_show_at_end(path):'),
 "R9 discovery narrowed (skips adopt)": lambda: edit("tests/v2_scope_chain/sc_helpers.py",
     '        if not (path.endswith(".py") and os.path.basename(path).startswith("test_")):',
     '        if "adopt" in path or not (path.endswith(".py") and os.path.basename(path).startswith("test_")):'),
 "R10 r3_07 FilesChanged keeps an extra no-op line": lambda: edit("tests/v2_history_restart/test_r3_07_scope.py",
     '        out = self.git("diff", "--name-status", START, END)\n', '        out = self.git("diff", "--name-status", START, END)\n        _unused = 0\n'),
 "R11 git_show_at_end ignores git failure->reads worktree": lambda: edit("tests/v2_history_ops/test_b17_scope.py",
     '    return out.stdout\n', '    return out.stdout or open(os.path.join(ROOT, path), encoding="utf-8").read()\n'),
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
