"""Temporary probe: which candidate shops have a usable Rick Owens feed?"""
import json, re, sys, urllib.request, collections
sys.path.insert(0, ".")
import rick_feed as rf

CANDIDATES = """tarnishedarchive.com archivesf.com streetcommerce.shop elevated-archives.com luxemia.net performaatlanta.com
consignmentbrooklyn.com crisconsignment.com shopwasteland.com archive-factory.com zoofashions.com vspconsignment.com
shopthroat.com driewgarments.com variousarchives.com procellvintage.com jamesveloria.com shoptrafficla.com""".split()

UA = {"User-Agent": rf.USER_AGENT, "Accept": "application/json"}
def get(url, raw=False):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25) as r:
            b = r.read(); return b if raw else json.loads(b)
    except Exception as e:
        return {"_error": str(e)[:100]}

out = {}
for dom in CANDIDATES:
    root = f"https://{dom}"
    meta = get(root + "/meta.json")
    rec = {"meta": {k: meta.get(k) for k in ("name", "city", "province", "country", "currency", "_error")}}
    pj = get(root + "/products.json?limit=1")
    rec["shopify"] = isinstance(pj, dict) and "products" in pj
    if not rec["shopify"]:
        rec["error"] = pj.get("_error") if isinstance(pj, dict) else "?"
        out[dom] = rec; print(dom, json.dumps(rec)); continue
    cols = []
    for page in (1, 2, 3, 4):
        c = get(f"{root}/collections.json?limit=250&page={page}")
        got = c.get("collections") or []
        cols += got
        if len(got) < 250: break
    rel = [c for c in cols if re.search(r"rick|owens|drk", c["handle"] + " " + c["title"], re.I)]
    rec["collections"] = []
    for c in rel[:6]:
        h = c["handle"]; prods = []
        for page in (1, 2, 3, 4):
            r = get(f"{root}/collections/{h}/products.json?limit=250&page={page}")
            ps = r.get("products") or []
            prods += ps
            if len(ps) < 250: break
        rick = [p for p in prods if rf.RICK.search(p.get("title", "")) or rf.RICK.search(p.get("vendor", ""))]
        avail = [p for p in rick if any(v.get("available") for v in p.get("variants") or [])]
        newest = max((p.get("published_at") or "" for p in prods), default="")
        atom = get(f"{root}/collections/{h}.atom", raw=True)
        try:
            items = rf.parse_feed({"name": dom, "city": ""}, atom) if isinstance(atom, bytes) else []
            atom_ok = isinstance(atom, bytes)
        except Exception as e:
            items, atom_ok = [], str(e)[:80]
        rec["collections"].append({"handle": h, "title": c["title"], "products": len(prods), "rick": len(rick),
                                   "rick_available": len(avail), "newest": newest[:10], "atom_ok": atom_ok,
                                   "atom_items": len(items), "atom_rick": sum(1 for i in items if rf.RICK.search(i["title"])),
                                   "vendors": collections.Counter(p.get("vendor") for p in prods).most_common(4)})
    if not rel:  # fall back: how much Rick does the shop have at all?
        s = get(f"{root}/search/suggest.json?q=rick%20owens&resources[type]=product&resources[limit]=10")
        hits = ((s.get("resources") or {}).get("results") or {}).get("products") or []
        rec["search_rick_hits"] = sum(1 for p in hits if rf.RICK.search(p.get("title", "") + " " + p.get("vendor", "")))
        atom = get(f"{root}/collections/all.atom", raw=True)
        try:
            items = rf.parse_feed({"name": dom, "city": "", "rick_only": True}, atom) if isinstance(atom, bytes) else []
        except Exception:
            items = []
        rec["all_atom_rick"] = len(items)
    out[dom] = rec
    print(dom, json.dumps(rec)[:900], flush=True)
json.dump(out, open("probe/stores.json", "w"), indent=1)
