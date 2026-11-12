import urllib.request
UA = {"User-Agent": "Mozilla/5.0"}
out = []
for u in ["https://kurb.online/robots.txt", "https://variousarchives.com/robots.txt", "https://www.storageplatform.org/robots.txt"]:
    with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=20) as r:
        out.append("##### " + u + "\n" + r.read().decode())
open("probe/diag.txt", "w").write("\n".join(out))
