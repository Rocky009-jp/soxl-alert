"""Independent freeze audit (reviewer). Reads git only."""
import ast, difflib, io, re, subprocess, sys, tokenize
ROOT = sys.argv[1]
A, C = "b626c98af5f01bc94e7b41d86aadde9663695eb9", "584b406ad8707dab1ccf1c77e209f870ade234f4"
FILES = {
 "tests/v2_history_ops/test_b17_scope.py": ("b328844fdeda235cf95bf7851ba9e3d7d55aa7bb", ["FilesChanged"]),
 "tests/v2_history_restart/test_r3_07_scope.py": ("d82a5ced64658c2e736b82b1a2f1925636055417", ["FilesChanged"]),
 "tests/v2_history_restore/test_r4_09_scope.py": ("ac219801d290ebb59b720f37a086103b6e1251c9", ["FilesChanged","B17_REMOVED","B17_ADDED","B17_HUNKS","R307_REMOVED","R307_ADDED","R307_HUNKS"]),
 "tests/v2_history_diagnose/test_d5_08_scope.py": ("c8ba08f15ea28248a9fe7924f32ce136fc16d5e6", ["FilesChanged","PINNED"]),
 "tests/v2_history_adopt/test_a5_08_scope.py": ("b626c98af5f01bc94e7b41d86aadde9663695eb9", ["FilesChanged","git","current_text"]),
}
def show(rev, p):
    return subprocess.run(["git","-C",ROOT,"show",f"{rev}:{p}"],capture_output=True,check=True).stdout.decode("utf-8")
def nodes(text):
    t = ast.parse(text); L = text.splitlines(keepends=True); out = []
    for n in t.body:
        if isinstance(n,(ast.FunctionDef,ast.ClassDef)): name=n.name
        elif isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name): name=n.targets[0].id
        elif isinstance(n,(ast.Import,ast.ImportFrom)): name="import:"+ast.unparse(n)
        else: name="other:"+ast.unparse(n)[:40]
        start=min([n.lineno]+[d.lineno for d in getattr(n,"decorator_list",[])])
        out.append((name,start,n.end_lineno))
    return out, L
def seg(text, name):
    ns,L=nodes(text)
    for nm,a,b in ns:
        if nm==name: return "".join(L[a-1:b])
    return None
def code_head_tokens(src):
    toks=list(tokenize.generate_tokens(io.StringIO(src).readline))
    return [t for t in toks if t.type==tokenize.STRING and t.string in ('"HEAD"',"'HEAD'")]
RULES=[
 ("head", lambda r: r.replace('"HEAD"', "END")),
 ("hash", lambda r: r.replace('"hash-object", path', '"rev-parse", END + ":" + path')),
 ("open", lambda r: re.sub(r'open\(os\.path\.join\(ROOT, (.+?)\), encoding="utf-8"\)', r'io.StringIO(git_show_at_end(\1))', r)),
]
ok=True
for p,(E,frozen) in FILES.items():
    a,e,c = show(A,p),show(E,p),show(C,p)
    na,_=nodes(a); nc,_=nodes(c)
    names_a=[n for n,_,_ in na]; names_c=[n for n,_,_ in nc]
    added=[n for n in names_c if n not in names_a]; removed=[n for n in names_a if n not in names_c]
    print("==",p); print(" added top-level:",added," removed:",removed)
    if sorted(added)!=sorted(["END","import:import io","git_show_at_end"]) or removed: ok=False; print(" !! top-level set")
    if [n for n in names_c if n not in added]!=names_a: ok=False; print(" !! order")
    # non-frozen segments identical to A
    for n in names_a:
        if n in frozen: continue
        if seg(a,n)!=seg(c,n): ok=False; print(" !! non-frozen differs:",n)
    # gaps (comments/blank lines between nodes): reconstruct
    # frozen: compare E segment vs C segment
    nrem=nadd=0
    for n in frozen:
        se,sc=seg(e,n),seg(c,n)
        if se is None: ok=False; print(" !! frozen missing at END",n); continue
        le,lc=se.splitlines(),sc.splitlines()
        sm=difflib.SequenceMatcher(a=le,b=lc,autojunk=False)
        for tag,i1,i2,j1,j2 in sm.get_opcodes():
            if tag=="equal": continue
            rem,addl=le[i1:i2],lc[j1:j2]; nrem+=len(rem); nadd+=len(addl)
            # setUp insertion
            if tag=="insert" and [x.strip() for x in addl] in (['if probe.returncode == 0:','probe = self.git("cat-file", "-e", END + "^{commit}")'],['if probe.returncode == 0:','probe = git("cat-file", "-e", END + "^{commit}")']):
                continue
            if tag=="replace" and len(rem)==len(addl):
                for r,x in zip(rem,addl):
                    if not any(f(r)==x for _,f in RULES): ok=False; print(" !! unexplained:",repr(r),"->",repr(x))
                continue
            if tag=="replace" and len(rem)==1 and "os.listdir" in rem[0]:
                print("  listdir rule:",rem,"->",addl); continue
            ok=False; print(" !! opcode",tag,rem,addl)
        # residual code HEAD / worktree reads in frozen part
        try:
            src = sc if not sc.startswith(" ") else sc
            heads=code_head_tokens(sc)
        except Exception as ex:
            heads=None
        bad=[w for w in ("hash-object","os.listdir","os.walk","open(") if w in "\n".join(l for l in lc if not l.strip().startswith(("'",'"')))]
        print(f"  {n}: code-HEAD tokens={len(heads) if heads is not None else '?'} worktree-words={bad}")
        if heads: ok=False
    print(f"  replaced lines: -{nrem} +{nadd}")
    # outside frozen: any HEAD/hash-object/open of ROOT?
    for n,a_,b_ in nc:
        if n in frozen or n in ("END","git_show_at_end"): continue
        s=seg(c,n)
        if '"HEAD"' in s or "hash-object" in s: print("  note: non-frozen",n,"mentions HEAD/hash-object")
print("ALL_OK" if ok else "PROBLEMS")
