"""Temporary probe: sweep US + Canadian metros on OpenStreetMap (Overpass API)
for second-hand / vintage / consignment clothing shops with a website, then test
each website for a Shopify Rick Owens collection."""
import json, re, sys, time, urllib.request, urllib.parse, concurrent.futures, collections
sys.path.insert(0, ".")
import rick_feed as rf
UA = {"User-Agent": "RickFeedShopFinder/1.0 (personal project; Claude-assisted)"}
METROS = {  # name: (lat, lon, radius km)
 "New York": (40.73, -73.99, 35), "Los Angeles": (34.05, -118.30, 45), "Chicago": (41.88, -87.66, 35), "Dallas": (32.85, -96.85, 40),
 "Houston": (29.76, -95.40, 40), "Washington DC": (38.90, -77.04, 30), "Philadelphia": (39.95, -75.16, 30), "Miami": (25.80, -80.21, 35),
 "Atlanta": (33.77, -84.39, 35), "Boston": (42.36, -71.08, 30), "Phoenix": (33.47, -112.05, 40), "San Francisco": (37.77, -122.42, 25),
 "Oakland/East Bay": (37.83, -122.25, 20), "San Jose": (37.33, -121.89, 25), "Seattle": (47.61, -122.33, 30), "Detroit": (42.35, -83.10, 35),
 "Minneapolis": (44.97, -93.25, 30), "San Diego": (32.75, -117.15, 30), "Tampa": (27.96, -82.50, 30), "Denver": (39.74, -104.98, 30),
 "Baltimore": (39.30, -76.61, 25), "St. Louis": (38.63, -90.24, 30), "Orlando": (28.54, -81.38, 30), "Charlotte": (35.23, -80.84, 30),
 "San Antonio": (29.45, -98.50, 30), "Portland": (45.52, -122.66, 30), "Sacramento": (38.58, -121.47, 25), "Pittsburgh": (40.44, -79.99, 25),
 "Austin": (30.28, -97.74, 30), "Las Vegas": (36.15, -115.17, 30), "Cincinnati": (39.12, -84.50, 25), "Kansas City": (39.08, -94.58, 30),
 "Columbus": (39.98, -83.00, 25), "Indianapolis": (39.77, -86.16, 25), "Cleveland": (41.48, -81.70, 25), "Nashville": (36.16, -86.78, 30),
 "Virginia Beach/Norfolk": (36.85, -76.20, 30), "Providence": (41.82, -71.42, 20), "Milwaukee": (43.05, -87.93, 25), "Jacksonville": (30.33, -81.66, 30),
 "Raleigh/Durham": (35.85, -78.75, 35), "Memphis": (35.13, -90.00, 25), "Richmond": (37.54, -77.45, 25), "New Orleans": (29.96, -90.08, 25),
 "Louisville": (38.24, -85.74, 25), "Salt Lake City": (40.74, -111.88, 30), "Hartford/New Haven": (41.55, -72.80, 40), "Buffalo": (42.89, -78.85, 25),
 "Birmingham": (33.52, -86.80, 25), "Honolulu": (21.31, -157.84, 20), "Albuquerque": (35.10, -106.62, 25), "Tucson": (32.22, -110.95, 25),
 "Toronto": (43.68, -79.40, 40), "Montreal": (45.51, -73.59, 30), "Vancouver": (49.26, -123.11, 30), "Calgary": (51.04, -114.07, 25),
 "Edmonton": (53.54, -113.50, 25), "Ottawa": (45.41, -75.70, 25), "Winnipeg": (49.89, -97.14, 20), "Quebec City": (46.81, -71.22, 20),
 "Hamilton": (43.25, -79.87, 20), "Victoria": (48.43, -123.36, 15),
}
CHAINS = re.compile(r"goodwill|salvation army|savers|value village|plato|uptown cheapskate|crossroads|buffalo exchange|clothes mentor|once upon a child|st\.? vincent|habitat|thrift ?town|out of the closet|america'?s thrift|red white|deseret|amvets|vinnies|platos|winmark|purple heart|arc thrift|twice as nice|kid to kid", re.I)
log = []
def note(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); log.append(s)
    open("probe/cities.txt", "w").write("\n".join(log))   # keep progress even if the job is cut short
START = time.time()

ENDPOINTS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter", "https://overpass.private.coffee/api/interpreter"]
def overpass(lat, lon, r):
    q = f"""[out:json][timeout:50];
(
  nwr(around:{r*1000},{lat},{lon})["shop"="second_hand"];
  nwr(around:{r*1000},{lat},{lon})["shop"~"^(clothes|boutique|fashion|shoes)$"]["second_hand"~"^(yes|only)$"];
);
out tags;"""
    for ep in ENDPOINTS:
        try:
            data = urllib.parse.urlencode({"data": q}).encode()
            with urllib.request.urlopen(urllib.request.Request(ep, data=data, headers=UA), timeout=60) as r:
                return json.loads(r.read()).get("elements", [])
        except Exception as e:
            note(f"   {ep.split('/')[2]} failed: {str(e)[:60]}")
    return None

shops = {}   # domain -> {names, metros}
counts = {}
for metro, (lat, lon, r) in METROS.items():
    if time.time() - START > 20 * 60:
        note("harvest time limit reached; stopping at " + metro); break
    els = overpass(lat, lon, r)
    if els is None:
        note(f"{metro}: Overpass failed"); continue
    n_site = 0
    for e in els:
        t = e.get("tags", {})
        name = t.get("name", "")
        site = t.get("website") or t.get("contact:website") or t.get("url") or ""
        if not site or CHAINS.search(name + " " + t.get("brand", "")):
            continue
        if not site.startswith("http"): site = "https://" + site
        dom = urllib.parse.urlparse(site).netloc.lower().removeprefix("www.")
        if not dom or re.search(r"facebook|instagram|google|yelp|linktr|etsy|ebay|depop|squarespace\.com$|wix\.com$", dom): continue
        rec = shops.setdefault(dom, {"names": set(), "metros": set()})
        rec["names"].add(name); rec["metros"].add(metro); n_site += 1
    counts[metro] = (len(els), n_site)
    note(f"{metro}: {len(els)} shops on OSM, {n_site} with a usable website")
    time.sleep(3)
note(f"TOTAL unique shop websites: {len(shops)}")

GUESS = ["rick-owens", "rickowens", "rick-owens-1", "rick-owens-drkshdw", "drkshdw"]
def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": rf.USER_AGENT, "Accept": "application/json"}), timeout=10) as r:
            return json.loads(r.read())
    except Exception:
        return None
def test(dom):
    root = f"https://{dom}"
    pj = get(root + "/products.json?limit=1")
    if not isinstance(pj, dict) or "products" not in pj:
        return dom, None
    meta = get(root + "/meta.json") or {}
    cols = (get(root + "/collections.json?limit=250") or {}).get("collections") or []
    handles = [c["handle"] for c in cols if re.search(r"rick|owens|drk", c["handle"] + " " + c["title"], re.I)]
    handles += [h for h in GUESS if h not in handles]
    best = []
    for h in handles[:8]:
        ps = ((get(f"{root}/collections/{h}/products.json?limit=250") or {}).get("products")) or []
        rick = [p for p in ps if rf.RICK.search(p.get("title", "") + " " + p.get("vendor", ""))]
        if rick and not any(b["rick"] == len(rick) and b["products"] == len(ps) for b in best):
            best.append({"handle": h, "products": len(ps), "rick": len(rick),
                         "avail": sum(1 for p in rick if any(v.get("available") for v in p.get("variants") or [])),
                         "newest": max((p.get("published_at") or "" for p in ps), default="")[:10]})
    s = get(f"{root}/search/suggest.json?q=rick%20owens&resources[type]=product&resources[limit]=10") or {}
    hits = ((s.get("resources") or {}).get("results") or {}).get("products") or []
    return dom, {"name": meta.get("name"), "city": meta.get("city"), "country": meta.get("country"), "currency": meta.get("currency"),
                 "collections": best, "rick_search_hits": sum(1 for p in hits if rf.RICK.search(p.get("title", "") + " " + p.get("vendor", "")))}
results = {}
TEST_START = time.time()
pool = concurrent.futures.ThreadPoolExecutor(8)
futs = {pool.submit(test, d): d for d in sorted(shops)}
done = 0
try:
    for f in concurrent.futures.as_completed(futs, timeout=20 * 60):
        dom, r = f.result()
        done += 1
        if r is not None:
            results[dom] = dict(r, osm_names=sorted(shops[dom]["names"])[:2], metros=sorted(shops[dom]["metros"]))
            if r["collections"]:
                note(f"   found: {dom} {[(c['handle'], c['rick'], c['avail']) for c in r['collections']]}")
        if done % 100 == 0:
            note(f"   tested {done}/{len(futs)}; Shopify so far {len(results)}")
except concurrent.futures.TimeoutError:
    note(f"test time limit reached after {done}/{len(futs)} sites")
pool.shutdown(wait=False, cancel_futures=True)
hits = {d: r for d, r in results.items() if r["collections"]}
some_rick = {d: r for d, r in results.items() if not r["collections"] and r["rick_search_hits"]}
note(f"Shopify sites: {len(results)}; with a Rick collection: {len(hits)}; Rick in stock but no collection: {len(some_rick)}")
for d, r in sorted(hits.items(), key=lambda kv: -max(c["avail"] for c in kv[1]["collections"])):
    note(f"== {d} | {r['name']} | {r['city']}, {r['country']} | {r['currency']} | metros {r['metros']} | " +
         "; ".join(f"{c['handle']}: {c['rick']} rick, {c['avail']} avail, newest {c['newest']}" for c in r["collections"]))
for d, r in sorted(some_rick.items(), key=lambda kv: -kv[1]["rick_search_hits"]):
    note(f"-- {d} | {r['name']} | {r['city']} | rick search hits {r['rick_search_hits']}")
json.dump({"counts": counts, "hits": hits, "some_rick": some_rick, "shopify_total": len(results), "domains": sorted(shops)},
          open("probe/cities.json", "w"), indent=1, default=list)
open("probe/cities.txt", "w").write("\n".join(log))
