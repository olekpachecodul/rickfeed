"""Temporary probe: does each shop carry DRKSHDW, and does our feed catch it?"""
import json, re, sys, urllib.request, urllib.parse
sys.path.insert(0, ".")
import rick_feed as rf

UA = {"User-Agent": rf.USER_AGENT, "Accept": "application/json"}
def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"_error": str(e)[:120]}

DRK = re.compile(r"drk\s*shdw|dark\s*shadow|drksdhw|drkshw", re.I)
out = {}
for shop in rf.SHOPS:
    feeds = shop["feed"] if isinstance(shop["feed"], list) else [shop["feed"]]
    root = re.match(r"https://[^/]+", feeds[0]).group(0)
    rec = {"feeds": feeds, "rick_only": bool(shop.get("rick_only"))}
    # what the current feed(s) give us
    caught = []
    for f in feeds:
        try:
            caught += rf.parse_feed(shop, rf.fetch_bytes(f))
        except Exception as e:
            rec.setdefault("feed_errors", []).append(str(e)[:100])
    rec["caught"] = len(caught)
    rec["caught_drk"] = [i["title"] for i in caught if DRK.search(i["title"])]
    # collections whose handle/title look relevant
    cols = []
    for page in (1, 2, 3):
        c = get(f"{root}/collections.json?limit=250&page={page}")
        got = c.get("collections") or []
        cols += got
        if len(got) < 250: break
    rec["collections_relevant"] = [(c["handle"], c["title"], c.get("products_count")) for c in cols
                                   if re.search(r"drk|shadow|rick|owens|lilies|hun", c["handle"] + " " + c["title"], re.I)]
    # store search for DRKSHDW
    found = {}
    for q in ("drkshdw", "dark shadow", "drk shdw"):
        s = get(f"{root}/search/suggest.json?" + urllib.parse.urlencode({"q": q, "resources[type]": "product", "resources[limit]": 10}))
        for p in ((s.get("resources") or {}).get("results") or {}).get("products") or []:
            found[p.get("handle")] = {"title": p.get("title"), "vendor": p.get("vendor"), "type": p.get("type"), "available": p.get("available")}
        if "_error" in s: rec["search_error"] = s["_error"]
    rec["search_drk"] = found
    # are those search hits in the collection we read?
    handles = set()
    for f in feeds:
        if f.endswith(".atom"):
            for page in (1, 2, 3, 4):
                pj = get(f[:-5] + f"/products.json?limit=250&page={page}")
                ps = pj.get("products") or []
                handles |= {p["handle"] for p in ps}
                rec.setdefault("collection_vendors", {})
                for p in ps:
                    rec["collection_vendors"][p.get("vendor")] = rec["collection_vendors"].get(p.get("vendor"), 0) + 1
                if len(ps) < 250: break
    rec["search_drk_in_our_collection"] = {h: h in handles for h in found}
    out[shop["name"]] = rec
    print(shop["name"], json.dumps(rec)[:600], flush=True)
json.dump(out, open("probe/shops.json", "w"), indent=1)
