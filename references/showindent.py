import sys
f=sys.argv[1]
for i,l in enumerate(open(f,encoding="utf-8"),1):
    s=l.rstrip("\n")
    lead=len(s)-len(s.lstrip(" "))
    print(f"{i:3d} L{lead:2d} | {s.strip()[:60]}")
