import ast, re, subprocess, sys
ROOT=sys.argv[1]; A="b626c98"; C="584b406"
FROZEN={"test_b17_scope.py":["FilesChanged"],"test_r3_07_scope.py":["FilesChanged"],
"test_r4_09_scope.py":["FilesChanged","B17_REMOVED","B17_ADDED","B17_HUNKS","R307_REMOVED","R307_ADDED","R307_HUNKS"],
"test_d5_08_scope.py":["FilesChanged","PINNED"],"test_a5_08_scope.py":["FilesChanged","git","current_text"]}
ADDED=["END","git_show_at_end"]
paths=subprocess.run(["git","-C",ROOT,"diff","--name-only",A,C,"--","tests/v2_history*"],capture_output=True,text=True).stdout.split()
for p in paths:
    base=p.rsplit("/",1)[1]
    def spans(rev,names):
        t=ast.parse(subprocess.run(["git","-C",ROOT,"show",f"{rev}:{p}"],capture_output=True,text=True).stdout); out=[]
        for n in t.body:
            nm=getattr(n,"name",None) or (n.targets[0].id if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) else None)
            if isinstance(n,ast.Import) and [a.name for a in n.names]==["io"]: nm="io"
            if nm in names: out.append((min([n.lineno]+[d.lineno for d in getattr(n,'decorator_list',[])]),n.end_lineno))
        return out
    sa=spans(A,FROZEN[base]); sc=spans(C,FROZEN[base]+ADDED+["io"])
    d=subprocess.run(["git","-C",ROOT,"diff","-U0",A,C,"--",p],capture_output=True,text=True).stdout
    bad=[]
    for m in re.finditer(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@",d,re.M):
        a1,ac,c1,cc=int(m[1]),int(m[2] or 1) if m[2]!="0" else 0,int(m[3]),int(m[4] or 1) if m[4]!="0" else 0
        for ln in range(a1,a1+ac):
            if not any(x<=ln<=y for x,y in sa): bad.append(("A",ln))
        for ln in range(c1,c1+cc):
            if not any(x<=ln<=y for x,y in sc): bad.append(("C",ln))
    cl=subprocess.run(["git","-C",ROOT,"show",f"{C}:{p}"],capture_output=True,text=True).stdout.splitlines()
    print(p, "outside-span changed lines:", [(s,l,cl[l-1] if s=="C" else "") for s,l in bad])
