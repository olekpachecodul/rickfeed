"""Temporary probe: harvest seller websites from archive-seller directories and
test each one for a Shopify Rick Owens collection."""
import json, re, sys, urllib.request, urllib.parse, concurrent.futures, collections, time
sys.path.insert(0, ".")
import rick_feed as rf
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
def get(url, raw=True, timeout=20):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            b = r.read(); return b.decode("utf-8", "replace") if raw else json.loads(b)
    except Exception as e:
        return None
log = []
def note(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); log.append(s)

SKIP = re.compile(r"kurb\.online|variousarchives|storageplatform|instagram|facebook|tiktok|twitter|x\.com|youtube|google|apple\.com|shopify|cdn|klaviyo|pinterest|linkedin|wa\.me|mailto|grailed|ebay|depop|etsy|vinted|threads\.net|discord|linktr|gstatic|cloudflare|jsdelivr|schema\.org|w3\.org|substack|medium\.com|stripe|paypal", re.I)
def external_domains(html):
    doms = set()
    for u in re.findall(r'href="(https?://[^"#?]+)', html or ""):
        d = urllib.parse.urlparse(u).netloc.lower().removeprefix("www.")
        if d and "." in d and not SKIP.search(d):
            doms.add(d)
    return doms

# 1) directory index pages -> seller pages
sellers = {}
for name, index_urls, pat in [
    ("kurb", [f"https://kurb.online/vendors?page={i}" for i in range(1, 30)] + ["https://kurb.online/vendors"], r'href="(/vendors/[a-z0-9\-]+)"'),
    ("various", ["https://variousarchives.com/stores", "https://variousarchives.com/sellers", "https://variousarchives.com/"], r'href="(/(?:stores|sellers|store|seller)/[a-z0-9\-]+)"'),
    ("storage", ["https://www.storageplatform.org/stores", "https://www.storageplatform.org/sellers", "https://www.storageplatform.org/"], r'href="(/(?:stores|sellers|store|seller|shop)/[A-Za-z0-9\-]+)"'),
]:
    found = set()
    base = "https://" + urllib.parse.urlparse(index_urls[0]).netloc
    for u in index_urls:
        html = get(u)
        if not html: continue
        new = set(re.findall(pat, html)) - found
        found |= new
        if name == "kurb" and not new and "page=" in u: break
    note(f"{name}: {len(found)} seller pages")
    for path in sorted(found):
        sellers[base + path] = name

# 2) seller pages -> their own websites
def seller_sites(url):
    return url, external_domains(get(url))
domains = collections.defaultdict(set)
with concurrent.futures.ThreadPoolExecutor(8) as pool:
    for url, doms in pool.map(seller_sites, sorted(sellers)):
        for d in doms:
            domains[d].add(url)
note(f"candidate domains: {len(domains)}")

# 3) test each domain: Shopify? Rick collection?
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
        if rick:
            avail = sum(1 for p in rick if any(v.get("available") for v in p.get("variants") or []))
            newest = max((p.get("published_at") or "" for p in ps), default="")[:10]
            best.append({"handle": h, "products": len(ps), "rick": len(rick), "avail": avail, "newest": newest})
    loc = ", ".join(x for x in [meta.get("city"), meta.get("province"), meta.get("country")] if x)
    return dom, {"name": meta.get("name"), "loc": loc, "currency": meta.get("currency"), "collections": best}
results = {}
with concurrent.futures.ThreadPoolExecutor(8) as pool:
    for dom, r in pool.map(test, sorted(domains)):
        if r is not None:
            results[dom] = dict(r, via=sorted(domains[dom])[:2])
hits = {d: r for d, r in results.items() if r["collections"]}
note(f"shopify: {len(results)}; with a Rick collection: {len(hits)}")
for d, r in sorted(hits.items(), key=lambda kv: -max(c["avail"] for c in kv[1]["collections"])):
    note(f"== {d} | {r['name']} | {r['loc']} | {r['currency']} | " + "; ".join(f"{c['handle']}: {c['rick']} rick, {c['avail']} avail, newest {c['newest']}" for c in r["collections"]))
json.dump({"hits": hits, "shopify_no_rick": sorted(set(results) - set(hits)), "non_shopify": sorted(set(domains) - set(results))}, open("probe/discover.json", "w"), indent=1)
open("probe/discover.txt", "w").write("\n".join(log))
