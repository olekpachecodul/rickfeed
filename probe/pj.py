"""Temporary probe: run the real fetch path with logging around products.json."""
import sys, json, traceback
sys.path.insert(0, ".")
import rick_feed as rf
orig_fetch = rf.fetch_bytes
log = []
def logged(url):
    try:
        b = orig_fetch(url)
        if "products.json" in url:
            try: n = len(json.loads(b).get("products") or [])
            except Exception as e: n = f"bad json {e}"
            log.append(f"OK   {url} -> {n}")
        return b
    except Exception as e:
        if "products.json" in url: log.append(f"FAIL {url} -> {type(e).__name__}: {e}")
        raise
rf.fetch_bytes = logged
lines = []
for shop in rf.SHOPS:
    s, items, err = rf.fetch_shop(shop)
    lines.append(f"{shop['name']:<18} items {len(items)} sold {sum(i['sold'] for i in items)} colours {sum(1 for i in items if i['colours'])} err {err}")
    print(lines[-1], flush=True)
open("probe/pj.txt", "w").write("\n".join(lines + [""] + log))
