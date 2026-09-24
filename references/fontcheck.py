import matplotlib.font_manager as fm
import os
dirs=["C:/Windows/Fonts"]
cands=["msyh.ttc","msyh.ttf","simhei.ttf","simsun.ttc","simsun.ttf","yahei.ttf","NotoSansCJK-Regular.ttc","NotoSansSC-Regular.otf"]
print("--- existing CJK font files ---")
for d in dirs:
    for c in cands:
        p=os.path.join(d,c)
        if os.path.exists(p):
            print("FOUND", p)
print("--- matplotlib known font families containing common CJK names ---")
fams=set(f.name for f in fm.fontManager.ttflist)
for kw in ["YaHei","SimHei","SimSun","Noto","Hei","Song","Microsoft"]:
    hits=[x for x in fams if kw.lower() in x.lower()]
    if hits:
        print(kw, "->", sorted(hits)[:6])
