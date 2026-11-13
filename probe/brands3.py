"""Temporary probe: new candidate shops for the four sister feeds (polite, sequential)."""
import json, re, sys, time, urllib.request, urllib.error, urllib.parse, collections
sys.path.insert(0, ".")
import rick_feed as rf
BRANDS = {
  "kiko": (r"kiko\s*kostadinov", ["kiko-kostadinov", "kikokostadinov", "kiko"]),
  "lang": (r"helmut\s*lang", ["helmut-lang", "helmut-lang-archive", "helmut-lang-vintage", "helmutlang"]),
  "rafcalvin": (r"205\s*w\s*39|calvin\s*klein\s*205|raf\s*simons?\s*(?:x\s*|for\s*)?calvin|calvin\s*klein\s*(?:by\s*)?raf",
                ["calvin-klein-205w39nyc", "205w39nyc", "calvin-klein", "raf-simons", "raf-simons-archive", "raf-simons-calvin-klein"]),
  "soshi": (r"soshi\s*otsuki", ["soshiotsuki", "soshi-otsuki"]),
}
CANDIDATES = """https://backyardarchive.us https://archivereloaded.com https://www.sunnyarkives.com https://www.hlorenzo.com
https://shop.davidcasavantarchive.com https://www.archivethreads.ca https://archivestore.jp https://iruse.jp https://www.playful-dc.com
https://recentestudio.com https://marustorelondon.com https://palette-art-alive.jp https://endyma.com https://driewgarments.com
https://suigenerisconsignment.com https://archive-factory.com""".split()
UA = {"User-Agent": rf.USER_AGENT, "Accept": "application/json"}
ERR = collections.Counter()
def get(url):
    for wait in (0.8, 20, 45):
        time.sleep(wait)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            ERR[e.code] += 1
            if e.code not in (429, 430, 503): return None
        except Exception as e:
            ERR[type(e).__name__] += 1; return None
    return None
lines = []
def note(s): print(s, flush=True); lines.append(s); open("probe/brands3.txt", "w").write("\n".join(lines))
for root in CANDIDATES:
    meta = get(root + "/meta.json") or {}
    pj = get(root + "/products.json?limit=1")
    if not isinstance(pj, dict) or "products" not in pj:
        note(f"-- {root}: not Shopify / not reachable"); continue
    loc = ", ".join(x for x in [meta.get("city"), meta.get("province"), meta.get("country")] if x)
    note(f"== {root} | {meta.get('name')} | {loc} | {meta.get('currency')}")
    cols = []
    for page in (1, 2, 3):
        got = (get(f"{root}/collections.json?limit=250&page={page}") or {}).get("collections") or []
        cols += got
        if len(got) < 250: break
    for b, (pat, guesses) in BRANDS.items():
        rx = re.compile(pat, re.I)
        handles = [c["handle"] for c in cols if rx.search(c["handle"].replace("-", " ") + " " + c["title"]) or (b == "rafcalvin" and re.search(r"raf|calvin|205", c["handle"] + " " + c["title"], re.I))]
        handles += [h for h in guesses if h not in handles]
        found = []
        for h in handles[:10]:
            ps = []
            for page in (1, 2, 3, 4):
                got = (get(f"{root}/collections/{h}/products.json?limit=250&page={page}") or {}).get("products") or []
                ps += got
                if len(got) < 250: break
            hit = [p for p in ps if rx.search(p.get("title", "") + " " + p.get("vendor", ""))]
            if hit and not any(f[1] == len(hit) and f[2] == len(ps) for f in found):
                avail = sum(1 for p in hit if any(v.get("available") for v in p.get("variants") or []))
                newest = max((p.get("published_at") or "" for p in hit), default="")[:10]
                found.append((h, len(hit), len(ps), avail, newest))
        if found:
            note(f"     {b:<10} " + "; ".join(f"{h}: {n}/{t} brand, {a} avail, newest {nw}" for h, n, t, a, nw in found))
note(f"errors: {dict(ERR)}")
