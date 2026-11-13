"""Temporary probe: what brands do the Rick shops sell besides Rick Owens? (polite, sequential)"""
import json, re, sys, time, urllib.request, urllib.error, collections
sys.path.insert(0, ".")
import rick_feed as rf
UA = {"User-Agent": rf.USER_AGENT, "Accept": "application/json"}
def get(url):
    for wait in (0.8, 20, 45):
        time.sleep(wait)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code not in (429, 430, 503): return None
        except Exception:
            return None
    return None
GENERIC = re.compile(r"^(all|new|sale|frontpage|home|featured|men|mens|women|womens|shoes|footwear|outerwear|tops|bottoms|pants|jackets|accessories|bags|jewelry|archive|vintage|sold|best|shop|clothing|denim|knitwear|shirts|t-shirts|tees|hats|sneakers|boots|under|gift|staff|in.?store|online|everything|available|latest|just in|new arrivals|coming soon|hidden|draft)\b", re.I)
out = {}
for s in rf.SHOPS:
    feed = s["feed"][0] if isinstance(s["feed"], list) else s["feed"]
    root = re.match(r"https://[^/]+", feed).group(0)
    vendors = collections.Counter(); n = 0
    for page in (1, 2, 3, 4):
        ps = (get(f"{root}/products.json?limit=250&page={page}") or {}).get("products") or []
        n += len(ps)
        vendors.update((p.get("vendor") or "").strip() for p in ps)
        if len(ps) < 250: break
    cols = []
    for page in (1, 2):
        got = (get(f"{root}/collections.json?limit=250&page={page}") or {}).get("collections") or []
        cols += got
        if len(got) < 250: break
    brandcols = sorted(((c.get("products_count") or 0, c["title"].strip()) for c in cols if not GENERIC.search(c["title"].strip())), reverse=True)
    out[s["name"]] = {"products_read": n, "vendors": vendors.most_common(40), "collections": brandcols[:60]}
    print(s["name"], n, vendors.most_common(8), flush=True)
json.dump(out, open("probe/mix.json", "w"), indent=1, ensure_ascii=False)
