"""Temporary probe: which known shops carry Kiko Kostadinov, Helmut Lang,
Calvin Klein 205W39NYC and Soshiotsuki, and in which collection?"""
import json, re, sys, urllib.request, urllib.error, concurrent.futures, collections
sys.path.insert(0, ".")
import rick_feed as rf
BRANDS = {
  "kiko": (r"kiko\s*kostadinov", ["kiko-kostadinov", "kikokostadinov", "kiko-kostadinov-1", "kiko"]),
  "lang": (r"helmut\s*lang", ["helmut-lang", "helmutlang", "helmut-lang-1", "helmut-lang-archive", "helmut-lang-vintage"]),
  "rafcalvin": (r"205\s*w\s*39|calvin\s*klein\s*205|raf\s*simons?\s*(x\s*|for\s*)?calvin|calvin\s*klein\s*(by\s*)?raf", ["calvin-klein-205w39nyc", "205w39nyc", "calvin-klein", "raf-simons-calvin-klein", "calvin-klein-by-raf-simons", "raf-simons", "raf-simons-1", "raf-simons-archive", "calvin-klein-205w39nyc-by-raf-simons"]),
  "soshi": (r"soshi\s*otsuki", ["soshiotsuki", "soshi-otsuki"]),
}
EXTRA = ["https://archivesf.com", "https://269archive.com", "https://dusty-archive.com", "https://recessla.com", "https://endyma.com", "https://asprstore.com", "https://huibenshop.com", "https://soshiotsuki.store", "https://aww90s.com", "https://crybynoon.com", "https://sundaynightmare.com", "https://dolcevitahub.com", "https://nationalbunker.store"]
roots = []
for s in rf.SHOPS:
    f = s["feed"][0] if isinstance(s["feed"], list) else s["feed"]
    roots.append((s["name"], re.match(r"https://[^/]+", f).group(0)))
roots += [(r.split("//")[1], r) for r in EXTRA]
prev = json.load(open("probe/brands.json"))
roots = [(n, r) for n, r in roots if not any(prev.get(n, {}).get(b, {}).get("collections") or prev.get(n, {}).get(b, {}).get("search") for b in BRANDS)]
import time
ERR = collections.Counter()
UA = {"User-Agent": rf.USER_AGENT, "Accept": "application/json"}
def get(url):
    for wait in (0, 20, 45):
        time.sleep(wait or 0.7)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            ERR[e.code] += 1
            if e.code not in (429, 430, 503): return None
        except Exception as e:
            ERR[type(e).__name__] += 1; return None
    return None
def probe(item):
    name, root = item
    cols = []
    for page in (1, 2, 3):
        got = (get(f"{root}/collections.json?limit=250&page={page}") or {}).get("collections") or []
        cols += got
        if len(got) < 250: break
    res = {}
    for b, (pat, guesses) in BRANDS.items():
        rx = re.compile(pat, re.I)
        handles = [c["handle"] for c in cols if rx.search(c["handle"].replace("-", " ") + " " + c["title"]) or (b == "rafcalvin" and re.search(r"raf|calvin|205", c["handle"] + " " + c["title"], re.I))]
        handles += [h for h in guesses if h not in handles]
        found = []
        for h in handles[:12]:
            ps = []
            for page in (1, 2, 3, 4):
                got = (get(f"{root}/collections/{h}/products.json?limit=250&page={page}") or {}).get("products") or []
                ps += got
                if len(got) < 250: break
            hit = [p for p in ps if rx.search(p.get("title", "") + " " + p.get("vendor", ""))]
            if hit and not any(f["n"] == len(hit) and f["total"] == len(ps) for f in found):
                found.append({"handle": h, "total": len(ps), "n": len(hit),
                              "avail": sum(1 for p in hit if any(v.get("available") for v in p.get("variants") or [])),
                              "newest": max((p.get("published_at") or "" for p in hit), default="")[:10]})
        s = get(f"{root}/search/suggest.json?q={urllib.parse.quote(pat.split('|')[0].replace(chr(92)+'s*', ' ').replace(chr(92)+'s?', ''))}&resources[type]=product&resources[limit]=10") or {}
        hits = ((s.get("resources") or {}).get("results") or {}).get("products") or []
        res[b] = {"collections": found, "search": sum(1 for p in hits if rx.search(p.get("title", "") + " " + p.get("vendor", "")))}
    return name, root, res
import urllib.parse
out = {}
lines = []
with concurrent.futures.ThreadPoolExecutor(1) as pool:
    for name, root, res in pool.map(probe, roots):
        out[name] = {"root": root, **res}
for b in BRANDS:
    lines.append(f"===== {b}")
    for name, r in out.items():
        x = r[b]
        if x["collections"] or x["search"]:
            lines.append(f"  {name:<20} {r['root']:<38} search {x['search']:>2} | " + "; ".join(f"{c['handle']}: {c['n']}/{c['total']} brand, {c['avail']} avail, newest {c['newest']}" for c in x["collections"]))
lines.append(f"rechecked {len(roots)} shops; errors: {dict(ERR)}")
open("probe/brands2.txt", "w").write("\n".join(lines)); print("\n".join(lines))
json.dump(out, open("probe/brands2.json", "w"), indent=1)
