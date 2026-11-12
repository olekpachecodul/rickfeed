"""Temporary probe: the real main() (parallel) with products.json logging."""
import sys, json, threading, collections
sys.path.insert(0, ".")
import rick_feed as rf
orig = rf.fetch_bytes; log = []; lock = threading.Lock()
def logged(url):
    try:
        b = orig(url)
        if "products.json" in url:
            with lock: log.append(("OK", url, ""))
        return b
    except Exception as e:
        if "products.json" in url:
            with lock: log.append(("FAIL", url, f"{type(e).__name__}: {getattr(e, 'code', '')} {e}"[:160]))
        raise
rf.fetch_bytes = logged
sys.argv = ["x", "--site", "/tmp/site", "--state", "/tmp/state.json"]
import io, contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rf.main()
c = collections.Counter(s for s, _, _ in log)
reasons = collections.Counter(r for s, _, r in log if s == "FAIL")
txt = buf.getvalue() + f"\nproducts.json: {dict(c)}\nfailure reasons: {reasons.most_common(5)}\n" + "\n".join(f"{s} {u} {r}" for s, u, r in log[:40])
open("probe/pj.txt", "w").write(txt); print(txt)
