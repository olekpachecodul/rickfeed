"""Temporary probe: harvest seller websites from STORAGE (storageplatform.org,
whose robots.txt allows AI agents on these pages) and test each for a Shopify
Rick Owens collection. Polite: sequential, 1s apart, no query-string URLs."""
import json, re, sys, time, urllib.request, urllib.parse, concurrent.futures, collections
sys.path.insert(0, ".")
import rick_feed as rf
UA = {"User-Agent": "Mozilla/5.0 (compatible; RickFeedShopFinder/1.0; Claude-assisted; personal project)"}
def get(url, raw=True):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
            b = r.read(); return b.decode("utf-8", "replace") if raw else json.loads(b)
    except Exception:
        return None
log = []
def note(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); log.append(s)
SKIP = re.compile(r"storageplatform|cloudfront|clerk\.|instagram|facebook|tiktok|twitter|x\.com|youtube|google|apple\.com|shopify|cdn|klaviyo|pinterest|linkedin|wa\.me|grailed|ebay|depop|etsy|vinted|threads\.(net|com)|discord|linktr|gstatic|cloudflare|jsdelivr|schema\.org|w3\.org|substack|medium\.com|stripe|paypal|vercel|sentry|posthog|nextjs|react|github|fonts\.|stores\.jp$", re.I)

sm = get("https://www.storageplatform.org/sitemap.xml") or ""
stores = sorted(set(u for u in re.findall(r"<loc>(https://www\.storageplatform\.org/store/[^<?]+)</loc>", sm)))
note(f"STORAGE store pages in sitemap: {len(stores)}")
domains = collections.defaultdict(set)
for i, u in enumerate(stores):
    html = get(u) or ""
    for link in re.findall(r'https?://[A-Za-z0-9.\-]+\.[a-z]{2,}(?=[/"\\\s<\']|$)', html):
        d = urllib.parse.urlparse(link).netloc.lower().removeprefix("www.")
        if d and not SKIP.search(d):
            domains[d].add(u.rsplit("/", 1)[-1])
    time.sleep(1)
note(f"candidate domains: {len(domains)}")

GUESS = ["rick-owens", "rickowens", "rick-owens-1", "rick-owens-drkshdw", "drkshdw"]
def test(dom):
    root = f"https://{dom}"
    pj = get(root + "/products.json?limit=1", raw=False)
    if not isinstance(pj, dict) or "products" not in pj:
        return dom, None
    meta = get(root + "/meta.json", raw=False) or {}
    cols = (get(root + "/collections.json?limit=250", raw=False) or {}).get("collections") or []
    handles = [c["handle"] for c in cols if re.search(r"rick|owens|drk", c["handle"] + " " + c["title"], re.I)]
    handles += [h for h in GUESS if h not in handles]
    best = []
    for h in handles[:8]:
        r = get(f"{root}/collections/{h}/products.json?limit=250", raw=False)
        ps = (r or {}).get("products") or []
        rick = [p for p in ps if rf.RICK.search(p.get("title", "") + " " + p.get("vendor", ""))]
        if rick and not any(b["rick"] == len(rick) and b["products"] == len(ps) for b in best):
            avail = sum(1 for p in rick if any(v.get("available") for v in p.get("variants") or []))
            best.append({"handle": h, "products": len(ps), "rick": len(rick), "avail": avail,
                         "newest": max((p.get("published_at") or "" for p in ps), default="")[:10]})
    loc = ", ".join(x for x in [meta.get("city"), meta.get("province"), meta.get("country")] if x)
    return dom, {"name": meta.get("name"), "loc": loc, "currency": meta.get("currency"), "collections": best}
results = {}
with concurrent.futures.ThreadPoolExecutor(6) as pool:
    for dom, r in pool.map(test, sorted(domains)):
        if r is not None:
            results[dom] = dict(r, storage=sorted(domains[dom])[:2])
hits = {d: r for d, r in results.items() if r["collections"]}
note(f"shopify: {len(results)}; with a Rick collection: {len(hits)}")
for d, r in sorted(hits.items(), key=lambda kv: -max(c["avail"] for c in kv[1]["collections"])):
    note(f"== {d} | {r['name']} | {r['loc']} | {r['currency']} | " + "; ".join(f"{c['handle']}: {c['rick']} rick, {c['avail']} avail, newest {c['newest']}" for c in r["collections"]))
note("shopify, no Rick collection: " + ", ".join(sorted(set(results) - set(hits))))
json.dump({"hits": hits, "all_domains": sorted(domains)}, open("probe/discover.json", "w"), indent=1)
open("probe/discover.txt", "w").write("\n".join(log))
