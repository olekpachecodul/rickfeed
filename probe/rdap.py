import json, urllib.request, subprocess
out = []
try:
    with urllib.request.urlopen("https://rdap.verisign.com/com/v1/domain/hengecorp.com", timeout=20) as r:
        d = json.loads(r.read())
    out.append("status: " + ", ".join(d.get("status", [])))
    for e in d.get("entities", []):
        if "registrar" in e.get("roles", []):
            v = e.get("vcardArray", [None, []])[1]
            out.append("registrar: " + ", ".join(x[3] for x in v if x[0] == "fn"))
            for l in e.get("links", []): out.append("registrar link: " + l.get("href", ""))
    for ev in d.get("events", []): out.append(f"{ev.get('eventAction')}: {ev.get('eventDate')}")
    out.append("nameservers: " + ", ".join(n.get("ldhName", "") for n in d.get("nameservers", [])))
except Exception as e:
    out.append(f"RDAP failed: {e}")
for t in ("NS", "MX", "A", "TXT"):
    r = subprocess.run(["dig", "+short", t, "hengecorp.com"], capture_output=True, text=True)
    out.append(f"dig {t}: " + " | ".join(r.stdout.split("\n")).strip(" |"))
open("probe/rdap.txt", "w").write("\n".join(out)); print("\n".join(out))
