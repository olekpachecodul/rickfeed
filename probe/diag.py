import re, urllib.request, gzip
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
out = []
def get(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=20) as r:
            b = r.read()
            if b[:2] == b"\x1f\x8b": b = gzip.decompress(b)
            return r.status, r.headers.get("content-type"), b.decode("utf-8", "replace")
    except Exception as e:
        return "ERR", str(e)[:80], ""
for u in ["https://kurb.online/vendors", "https://kurb.online/sitemap.xml", "https://kurb.online/robots.txt", "https://kurb.online/products.json?limit=1",
          "https://variousarchives.com/sitemap.xml", "https://variousarchives.com/robots.txt", "https://variousarchives.com/designers/rick-owens",
          "https://www.storageplatform.org/sitemap.xml", "https://www.storageplatform.org/robots.txt", "https://www.storageplatform.org/designer/rick-owens"]:
    s, ct, body = get(u)
    links = sorted(set(re.findall(r"https?://[^\s\"<>']+", body)))
    out.append(f"## {u} -> {s} {ct} len={len(body)}")
    out.append("   sitemaps/sample: " + " | ".join([l for l in links if "sitemap" in l][:8] or links[:8]))
    out.append("   vendor-ish: " + " | ".join(sorted(set(re.findall(r"/(?:vendors|stores|sellers|store|seller|shop)/[A-Za-z0-9\-_]+", body)))[:15]))
    out.append("   head: " + re.sub(r"\s+", " ", body[:300]))
open("probe/diag.txt", "w").write("\n".join(out)); print("\n".join(out))
