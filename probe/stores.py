"""Temporary probe: which candidate shops have a usable Rick Owens feed?"""
import json, re, sys, urllib.request, collections
sys.path.insert(0, ".")
import rick_feed as rf

CANDIDATES = """archivevintage.com thearchivela.net sundaynightmare.com dusty-archive.com crybynoon.com 269archive.com
nationalbunker.store murderarchive.store endyma.com coup-de-grace.net armaniwells.com otherpeoplesclothes.shop
dolcevitahub.com archivist.store gunmetalarchive.com recessla.com gentlemensresale.com guild3.com archivesf.com
tarnishedarchive.com 6ixarchive.com rentonarchives.com""".split()
GUESS = ["rick-owens", "rickowens", "rick-owens-1", "rick-owens-drkshdw", "drkshdw", "rick-owens-mainline", "rick", "rick-owens-archive"]

UA = {"User-Agent": rf.USER_AGENT, "Accept": "application/json"}
def get(url, raw=False):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25) as r:
            b = r.read(); return b if raw else json.loads(b)
    except Exception as e:
        return {"_error": str(e)[:100]}

def describe(root, h, title=""):
    prods = []
    for page in (1, 2, 3, 4):
        r = get(f"{root}/collections/{h}/products.json?limit=250&page={page}")
        if "_error" in r: return None
        ps = r.get("products") or []
        prods += ps
        if len(ps) < 250: break
    rick = [p for p in prods if rf.RICK.search(p.get("title", "")) or rf.RICK.search(p.get("vendor", ""))]
    avail = [p for p in rick if any(v.get("available") for v in p.get("variants") or [])]
    atom = get(f"{root}/collections/{h}.atom", raw=True)
    try:
        items = rf.parse_feed({"name": root, "city": ""}, atom) if isinstance(atom, bytes) else []
    except Exception:
        items = []
    return {"handle": h, "title": title, "products": len(prods), "rick": len(rick), "rick_available": len(avail),
            "newest": max((p.get("published_at") or "" for p in prods), default="")[:10], "atom_items": len(items),
            "vendors": collections.Counter(p.get("vendor") for p in prods).most_common(3)}

out = {}
for dom in CANDIDATES:
    root = f"https://{dom}"
    meta = get(root + "/meta.json")
    rec = {"meta": {k: meta.get(k) for k in ("name", "city", "province", "country", "currency")}}
    pj = get(root + "/products.json?limit=1")
    rec["shopify"] = isinstance(pj, dict) and "products" in pj
    if not rec["shopify"]:
        rec["error"] = pj.get("_error"); out[dom] = rec; print(dom, json.dumps(rec)); continue
    cols = []
    for page in (1, 2, 3, 4):
        c = get(f"{root}/collections.json?limit=250&page={page}")
        got = c.get("collections") or []
        cols += got
        if len(got) < 250: break
    rel = [(c["handle"], c["title"]) for c in cols if re.search(r"rick|owens|drk", c["handle"] + " " + c["title"], re.I)]
    seen = {h for h, _ in rel}
    rel += [(h, "(guessed)") for h in GUESS if h not in seen]
    rec["collections"] = [d for d in (describe(root, h, t) for h, t in rel[:10]) if d and d["products"]]
    s = get(f"{root}/search/suggest.json?q=rick%20owens&resources[type]=product&resources[limit]=10")
    hits = ((s.get("resources") or {}).get("results") or {}).get("products") or []
    rec["search_rick_hits"] = sum(1 for p in hits if rf.RICK.search(p.get("title", "") + " " + p.get("vendor", "")))
    atom = get(f"{root}/collections/all.atom", raw=True)
    try:
        rec["all_atom_rick"] = len(rf.parse_feed({"name": dom, "city": "", "rick_only": True}, atom)) if isinstance(atom, bytes) else 0
    except Exception:
        rec["all_atom_rick"] = 0
    out[dom] = rec
    print(dom, json.dumps(rec)[:700], flush=True)
json.dump(out, open("probe/stores.json", "w"), indent=1)
