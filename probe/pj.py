"""Temporary probe: why do products.json lookups fail now?"""
import sys, time, json, urllib.request, urllib.error
sys.path.insert(0, ".")
import rick_feed as rf
out = []
for shop in rf.SHOPS[:8] + rf.SHOPS[-3:]:
    feed = shop["feed"][0] if isinstance(shop["feed"], list) else shop["feed"]
    url = feed[:-5] + "/products.json?limit=250&page=1"
    for ua in (rf.USER_AGENT, "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"):
        t = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=25) as r:
                b = r.read(); code = r.status; ctype = r.headers.get("content-type")
            try: n = len(json.loads(b).get("products") or [])
            except Exception: n = "not json: " + b[:120].decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            code, ctype, n = e.code, e.headers.get("content-type"), e.read()[:160].decode("utf-8", "replace")
        except Exception as e:
            code, ctype, n = "ERR", "", str(e)[:120]
        line = f"{shop['name']:<18} {'rf-UA' if ua == rf.USER_AGENT else 'browserUA'} {code} {ctype} {round(time.time()-t,1)}s -> {n}"
        print(line, flush=True); out.append(line)
# and the real code path, once
got, err = rf.fetch_one(rf.SHOPS[4], rf.SHOPS[4]["feed"])
d = rf.fetch_details(rf.SHOPS[4]["feed"], {k for it in got for k in rf.product_keys(it)})
out.append(f"fetch_details Sui Generis: {len(d)} keys; atom items {len(got)}")
print(out[-1])
open("probe/pj.txt", "w").write("\n".join(out))
