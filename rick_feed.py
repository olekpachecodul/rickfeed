#!/usr/bin/env python3
"""
Rick Feed: one page of the newest Rick Owens listings from US resale shops.

Run it, and it downloads each shop's product feed, keeps the Rick Owens
pieces, and opens rick-owens-feed.html in your browser. Run it again later
and anything that showed up in between is marked NEW; price cuts are marked too.

Needs Python 3.8+ and nothing else.
Windows: double-click "Run Rick Feed.bat".  Mac/Linux: python3 rick_feed.py
Add --no-open to skip opening the browser (useful for scheduled runs).
"""

import concurrent.futures
import datetime as dt
import html
import json
import re
import ssl
import sys
import urllib.error
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
from pathlib import Path

# ---------------------------------------------------------------------------
# Shops. To add one: copy a line, change the name, city, feed and link.
# For a Shopify shop the feed is usually  https://SHOP/collections/HANDLE.atom
# where HANDLE is the last part of its Rick Owens page address.
# "rick_only": True keeps only Rick Owens / DRKSHDW items (use it for
# feeds that carry a whole store's new arrivals).
# ---------------------------------------------------------------------------
SHOPS = [
    {"name": "Luke's",            "city": "New York + Los Angeles", "feed": "https://lukes.store/collections/rick-owens.atom",                "link": "https://lukes.store/collections/vendors?q=Rick%20Owens"},
    {"name": "Marco Sqrd",        "city": "Chicago",                "feed": "https://marcosqrd.com/collections/rick-owens_smart.atom",        "link": "https://marcosqrd.com/collections/rick-owens_smart"},
    {"name": "Final Blow",        "city": "Chicago",                "feed": "https://www.finalblowchicago.com/collections/all.atom",          "link": "https://www.finalblowchicago.com/search?type=product&q=rick+owens", "rick_only": True},
    {"name": "Tokio 7",           "city": "New York",               "feed": "https://tokio7ny.com/collections/all.atom",                      "link": "https://tokio7ny.com/search?type=product&q=rick+owens",           "rick_only": True},
    {"name": "Sui Generis",       "city": "San Francisco",          "feed": "https://suigenerisconsignment.com/collections/rick-owens.atom",  "link": "https://suigenerisconsignment.com/collections/rick-owens"},
    {"name": "Sadō Room",         "city": "Seattle",                "feed": "https://sadoroom.com/collections/rick-owens.atom",               "link": "https://sadoroom.com/collections/rick-owens"},
    {"name": "Archive On Waters", "city": "Seattle",                "feed": "https://archiveonwaters.store/collections/rick-owens-1.atom",    "link": "https://archiveonwaters.store/collections/rick-owens-1"},
    {"name": "Shop Status",       "city": "Philadelphia + DC",      "feed": "https://shopstatus.store/collections/rick-owens-1.atom",         "link": "https://shopstatus.store/collections/rick-owens-1"},
    {"name": "Luxury Box ATL",    "city": "Atlanta",                "feed": "https://luxuryboxatl.com/collections/rick-owens.atom",           "link": "https://luxuryboxatl.com/collections/rick-owens"},
    {"name": "Groupie",           "city": "Los Angeles",            "feed": "https://groupie.store/collections/rick-owens.atom",              "link": "https://groupie.store/collections/rick-owens"},
    {"name": "Archived",          "city": "Los Angeles",            "feed": "https://archived.co/collections/rick-owens.atom",                "link": "https://archived.co/collections/rick-owens"},
    {"name": "Justin Reed",       "city": "Los Angeles + New York", "feed": "https://justinreed.com/collections/rick-owens.atom",             "link": "https://justinreed.com/collections/rick-owens"},
    {"name": "Midtown Archive",   "city": "Online",                 "feed": "https://midtownarchive.com/collections/rick-owens.atom",         "link": "https://midtownarchive.com/collections/rick-owens"},
    {"name": "Descry Archive",    "city": "By appointment",         "feed": "https://www.descryarchive.com/collections/rick-owens.atom",      "link": "https://www.descryarchive.com/collections/rick-owens"},
    # Added Nov 8, 2026
    {"name": "2nd Street",        "city": "60+ US stores",          "feed": "https://ec.2ndstreetusa.com/collections/rick-raf.atom",          "link": "https://ec.2ndstreetusa.com/collections/rick-raf",               "rick_only": True},
    {"name": "Resurrection",      "city": "West Hollywood",         "feed": "https://resurrectionvintage.com/collections/rick-owens.atom",    "link": "https://resurrectionvintage.com/collections/rick-owens",         "rick_only": True},
    {"name": "Pilgrim",           "city": "New York",               "feed": "https://pilgrimnyc.com/collections/45rpm.atom",                  "link": "https://pilgrimnyc.com/collections/45rpm",                       "rick_only": True},
    {"name": "Michael's",         "city": "New York",               "feed": "https://michaelsconsignment.com/collections/rick-owens.atom",    "link": "https://michaelsconsignment.com/collections/rick-owens"},
    {"name": "Graceful Misfits",  "city": "Online",                 "feed": ["https://gracefulmisfits.com/collections/mainline.atom",
                                                                              "https://gracefulmisfits.com/collections/drkshdw.atom"],         "link": "https://gracefulmisfits.com/"},
]

RICK = re.compile(r"rick\s*owens|drk\s*shdw|drksdhw|drkshw", re.I)
PRICE_DROP_DAYS = 7          # how long a price cut stays flagged
FORGET_AFTER_DAYS = 60       # drop items from memory once unseen this long
USER_AGENT = "Mozilla/5.0 (compatible; RickFeed/1.0; personal feed reader)"

HERE = Path(__file__).resolve().parent
STATE_FILE = HERE / "rick_feed_state.json"
OUT_FILE = HERE / "rick-owens-feed.html"

NS = {"a": "http://www.w3.org/2005/Atom", "s": "http://jadedpixel.com/-/spec/shopify"}
IMG_RE = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.I)
SIZE_PATTERNS = [
    re.compile(r"\((?:size\s*)?([0-9]{1,2}(?:\.5)?|XXS|XS|S|M|L|XL|XXL|OS|O/S|One Size)\)\s*$", re.I),
    re.compile(r"\b(?:size|sz)\.?\s*([0-9]{1,2}(?:\.5)?|XXS|XS|S|M|L|XL|XXL|small|medium|large|x-?large|OS)\b", re.I),
]


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


def fetch_bytes(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/atom+xml, application/xml;q=0.9, */*;q=0.5"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()


def sized_image(url):
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    if "cdn.shopify.com" in url or "/cdn/shop/" in url:
        url += ("&" if "?" in url else "?") + "width=600"
    return url


def guess_size(title, variant_titles):
    sizes = []
    for vt in variant_titles:
        vt = (vt or "").strip()
        if not vt or vt.lower() == "default title":
            continue
        last = vt.split(" / ")[-1].strip()
        if last and last.lower() not in ("used", "new", "black", "default title") and len(last) <= 12:
            sizes.append(last)
    if sizes:
        seen = []
        for s in sizes:
            if s not in seen:
                seen.append(s)
        return ", ".join(seen[:4])
    for pat in SIZE_PATTERNS:
        m = pat.search(title or "")
        if m:
            return m.group(1).upper() if len(m.group(1)) <= 3 else m.group(1).title()
    return ""


def parse_feed(shop, raw):
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        root = None
    if root is None or root.tag != "{http://www.w3.org/2005/Atom}feed":
        snippet = raw[:300].decode("utf-8", "replace").lower()
        if "<html" in snippet or "<!doctype" in snippet:
            raise RuntimeError("the shop sent a web page instead of its feed (it may be blocking automated requests)")
        raise RuntimeError("the feed couldn't be read")
    items = []
    for e in root.findall("a:entry", NS):
        title = (e.findtext("a:title", "", NS) or "").strip()
        vendor = (e.findtext("s:vendor", "", NS) or "").strip()
        if shop.get("rick_only") and not (RICK.search(title) or RICK.search(vendor)):
            continue
        link = ""
        for l in e.findall("a:link", NS):
            if l.get("rel", "alternate") == "alternate":
                link = l.get("href", "")
                break
        summary = e.findtext("a:summary", "", NS) or ""
        m = IMG_RE.search(summary)
        prices, currency, vtitles = [], "USD", []
        for v in e.findall("s:variant", NS):
            vtitles.append(v.findtext("a:title", "", NS))
            p = v.find("s:price", NS)
            if p is not None and (p.text or "").strip():
                try:
                    prices.append(float(p.text.strip()))
                    currency = p.get("currency", currency)
                except ValueError:
                    pass
        items.append({
            "id": (e.findtext("a:id", "", NS) or link).strip(),
            "shop": shop["name"],
            "city": shop["city"],
            "title": html.unescape(title),
            "link": link,
            "published": (e.findtext("a:published", "", NS) or e.findtext("a:updated", "", NS) or "").strip(),
            "image": sized_image(html.unescape(m.group(1))) if m else "",
            "price": min(prices) if prices else None,
            "currency": currency,
            "size": guess_size(title, vtitles),
            "type": (e.findtext("s:type", "", NS) or "").strip(),
        })
    return items


def fetch_one(shop, url):
    try:
        return parse_feed(shop, fetch_bytes(url)), None
    except urllib.error.HTTPError as e:
        return [], f"the shop answered with error {e.code}"
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        if isinstance(reason, ssl.SSLError) or "CERTIFICATE" in str(reason).upper():
            return [], "secure connection failed (on a Mac, run 'Install Certificates.command' from your Python folder)"
        return [], f"couldn't connect ({reason})"
    except Exception as e:  # keep going whatever one shop does
        return [], str(e) or e.__class__.__name__


def fetch_shop(shop):
    feeds = shop["feed"] if isinstance(shop["feed"], list) else [shop["feed"]]
    items, errors, seen_ids = [], [], set()
    for url in feeds:
        got, err = fetch_one(shop, url)
        if err:
            errors.append(err)
        for it in got:
            if it["id"] not in seen_ids:
                seen_ids.add(it["id"])
                items.append(it)
    error = errors[0] if errors and len(errors) == len(feeds) else None
    return shop, items, error


def load_state(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"items": {}}


def arg_value(flag):
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


def parse_time(s):
    try:
        t = dt.datetime.fromisoformat((s or "").replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def build_atom(items, generated):
    newest = sorted(items, key=lambda i: i["first_seen"], reverse=True)[:60]
    esc = lambda s: html.escape(str(s or ""), quote=True)
    parts = ['<?xml version="1.0" encoding="utf-8"?>',
             '<feed xmlns="http://www.w3.org/2005/Atom">',
             f"<title>Rick Feed</title><id>urn:rick-feed</id><updated>{esc(generated)}</updated>"]
    for i in newest:
        price = f"${i['price']:,.0f}" if i.get("price") is not None else ""
        label = " · ".join(x for x in [price, i.get("size"), i["shop"]] if x)
        body = (f'<p><img src="{esc(i["image"])}" width="300"></p>' if i.get("image") else "") + f"<p>{esc(label)}</p>"
        parts.append(f'<entry><id>urn:rick-feed:{esc(i["shop"])}:{esc(i["id"])}</id>'
                     f'<title>{esc(i["title"])} ({esc(label)})</title>'
                     f'<link href="{esc(i["link"])}"/><updated>{esc(i["first_seen"])}</updated>'
                     f'<content type="html">{esc(body)}</content></entry>')
    parts.append("</feed>")
    return "\n".join(parts)


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    site_dir = arg_value("--site")
    state_file = Path(arg_value("--state") or STATE_FILE)
    site_mode = site_dir is not None
    out_file = Path(site_dir) / "index.html" if site_mode else OUT_FILE
    open_browser = not site_mode and "--no-open" not in sys.argv

    run_at = now_utc()
    run_iso = run_at.isoformat(timespec="seconds")
    today = run_at.date().isoformat()
    state = load_state(state_file)
    memory = state.get("items", {})
    known_shops = {k.split("|", 1)[0] for k in memory}   # shops checked on an earlier run
    prev_run = state.get("last_run")
    first_run = prev_run is None
    run_no = int(state.get("run_no", 0)) + 1

    print(f"Checking {len(SHOPS)} shops…")
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for shop, items, err in pool.map(fetch_shop, SHOPS):
            status = f"{len(items)} items" if err is None else f"skipped: {err}"
            print(f"  {shop['name']:<18} {status}")
            results.append((shop, items, err))

    all_items, shops_out = [], []
    for shop, items, err in results:
        shops_out.append({"name": shop["name"], "city": shop["city"], "link": shop["link"], "count": len(items), "error": err})
        seeding = shop["name"] not in known_shops   # first time we see this shop
        for it in items:
            key = shop["name"] + "|" + it["id"]
            mem = memory.get(key)
            if mem is None:
                first = run_iso
                if seeding:  # new shop: date its items by when the shop listed them
                    pub = parse_time(it["published"])
                    if pub and pub < run_at:
                        first = pub.astimezone(dt.timezone.utc).isoformat(timespec="seconds")
                mem = {"first_seen": first, "first_run": 0 if seeding else run_no, "price": it["price"]}
                memory[key] = mem
            else:
                old = mem.get("price")
                if it["price"] is not None and old is not None and it["price"] < old - 0.005:
                    mem["drop_from"] = old
                    mem["drop_at"] = run_iso
                mem["price"] = it["price"]
            mem["last_seen"] = today
            it["first_seen"] = mem["first_seen"]
            it["is_new"] = (not first_run) and mem.get("first_run") == run_no
            drop_at = parse_time(mem.get("drop_at"))
            if drop_at and (run_at - drop_at).days < PRICE_DROP_DAYS and mem.get("drop_from"):
                it["drop_from"] = mem["drop_from"]
            all_items.append(it)

    cutoff = (run_at - dt.timedelta(days=FORGET_AFTER_DAYS)).date().isoformat()
    memory = {k: v for k, v in memory.items() if str(v.get("last_seen", today))[:10] >= cutoff}
    new_state = {"items": memory} if site_mode else {"last_run": run_iso, "run_no": run_no, "items": memory}
    text = json.dumps(new_state, indent=1, sort_keys=True)
    old_text = state_file.read_text(encoding="utf-8") if state_file.exists() else ""
    if text != old_text:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(text, encoding="utf-8")

    data = {"mode": "site" if site_mode else "local", "generated": run_iso, "previous": prev_run,
            "first_run": first_run, "shops": shops_out, "items": all_items}
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(PAGE.replace("__DATA__", payload), encoding="utf-8")
    if site_mode:
        (out_file.parent / "feed.xml").write_text(build_atom(all_items, run_iso), encoding="utf-8")
        (out_file.parent / ".nojekyll").write_text("", encoding="utf-8")

    new_count = sum(1 for i in all_items if i.get("is_new"))
    failed = [s["name"] for s in shops_out if s["error"]]
    print(f"\n{len(all_items)} Rick Owens listings" + ("" if first_run else f", {new_count} new since last run") + ".")
    if failed:
        print("Couldn't reach: " + ", ".join(failed))
    print(f"Saved {out_file}")
    if open_browser:
        webbrowser.open(out_file.resolve().as_uri())


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>Rick Feed</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;700&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
/* Layout: a dense contact sheet of listings under a slim filter bar. Concrete greys, dust, and one oxidised accent. */
:root{
  --bg:#ECEAE6; --panel:#F7F6F3; --ink:#161615; --muted:#6B6863; --line:#D6D2CB; --chip:#E2DFD9;
  --accent:#8C3B1F; --on-accent:#FFFFFF; --new:#161615; --on-new:#F7F6F3; --drop:#2F6B3F; --ph:#D9D5CE;
  --f-display:"Barlow Condensed","Arial Narrow",Arial,sans-serif;
  --f-body:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
  --f-mono:"IBM Plex Mono",ui-monospace,Consolas,monospace;
}
@media (prefers-color-scheme: dark){:root{
  --bg:#121211; --panel:#1B1B1A; --ink:#ECEAE6; --muted:#9A968F; --line:#2D2C2A; --chip:#262523;
  --accent:#D9774F; --on-accent:#121211; --new:#ECEAE6; --on-new:#121211; --drop:#6FBF84; --ph:#232220;
  color-scheme:dark;
}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 var(--f-body);-webkit-font-smoothing:antialiased}
a{color:inherit}
.wrap{max-width:1400px;margin:0 auto;padding:0 max(16px,env(safe-area-inset-left)) 0 max(16px,env(safe-area-inset-right))}
header{padding:28px 0 8px}
h1{font-family:var(--f-display);font-weight:700;font-size:44px;line-height:1;letter-spacing:.02em;text-transform:uppercase;margin:0}
.meta{color:var(--muted);margin-top:8px;font-size:13px}
.meta b{color:var(--ink);font-weight:600}
.notice{margin-top:12px;padding:10px 12px;border:1px solid var(--line);background:var(--panel);font-size:13px;max-width:80ch}
.bar{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line);padding:12px 0;display:flex;flex-wrap:wrap;gap:8px 10px;align-items:center}
.bar input[type=search],.bar select{font:inherit;color:inherit;background:var(--panel);border:1px solid var(--line);padding:7px 10px;border-radius:3px}
.bar input[type=search]{flex:1 1 220px;min-width:0}
.tog{display:inline-flex;align-items:center;gap:6px;padding:6px 10px;border:1px solid var(--line);border-radius:3px;background:var(--panel);cursor:pointer;user-select:none;font-size:13px}
.tog input{margin:0;accent-color:var(--accent)}
.count{margin-left:auto;color:var(--muted);font-size:13px;font-family:var(--f-mono)}
.shops{display:flex;flex-wrap:wrap;gap:6px;padding:10px 0 4px}
.shop{font:inherit;font-size:12.5px;border:1px solid var(--line);background:var(--chip);color:var(--ink);padding:4px 10px;border-radius:999px;cursor:pointer}
.shop[aria-pressed=false]{background:transparent;color:var(--muted);text-decoration:line-through}
.shop .n{font-family:var(--f-mono);color:var(--muted);margin-left:4px}
.shop.err{border-style:dashed}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:18px 14px;padding:16px 0 48px}
.card{display:flex;flex-direction:column;text-decoration:none;min-width:0}
.ph{position:relative;aspect-ratio:4/5;background:var(--ph);overflow:hidden}
.ph img{position:relative;z-index:1;width:100%;height:100%;object-fit:cover;display:block;transition:transform .25s}
.card:hover .ph img{transform:scale(1.03)}
.ph .noimg{position:absolute;inset:0;display:grid;place-items:center;font-family:var(--f-display);text-transform:uppercase;color:var(--muted);letter-spacing:.06em}
.badges{position:absolute;z-index:2;left:6px;top:6px;display:flex;gap:4px;flex-wrap:wrap}
.b{font-family:var(--f-display);font-weight:700;font-size:13px;letter-spacing:.06em;text-transform:uppercase;padding:2px 7px;line-height:1.3}
.b.new{background:var(--new);color:var(--on-new)}
.b.drop{background:var(--drop);color:var(--on-new)}
.t{margin-top:8px;font-size:13.5px;line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.row{display:flex;justify-content:space-between;gap:8px;align-items:baseline;margin-top:4px}
.price{font-family:var(--f-mono);font-weight:500;font-size:14px}
.price s{color:var(--muted);font-weight:400;margin-left:4px;font-size:12px}
.size{font-family:var(--f-mono);font-size:12px;color:var(--muted);white-space:nowrap}
.src{font-size:12px;color:var(--muted);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.empty{padding:40px 0;color:var(--muted)}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
@media (prefers-reduced-motion:reduce){.ph img{transition:none}}
@media (max-width:520px){.grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:14px 10px}h1{font-size:36px}}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Rick Feed</h1>
    <div class="meta" id="meta"></div>
    <div class="notice" id="notice" hidden></div>
  </header>
  <div class="bar">
    <input type="search" id="q" placeholder="Search: geobasket, bela, 48, leather…" aria-label="Search listings">
    <select id="sort" aria-label="Sort">
      <option value="new">Newest listed</option>
      <option value="seen">Newest found</option>
      <option value="low">Price: low to high</option>
      <option value="high">Price: high to low</option>
    </select>
    <label class="tog"><input type="checkbox" id="onlyNew"> <span id="newLabel">New since last run</span></label>
    <label class="tog"><input type="checkbox" id="onlyDrop"> Price cuts</label>
    <button type="button" class="tog" id="markSeen" hidden>Mark all seen</button>
    <span class="count" id="count"></span>
  </div>
  <div class="shops" id="shops"></div>
  <main class="grid" id="grid"></main>
</div>
<script>
const DATA = __DATA__;
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const money = (n, cur) => n == null ? "" : new Intl.NumberFormat("en-US", {style:"currency", currency: cur || "USD", maximumFractionDigits: n % 1 ? 2 : 0}).format(n);
function ago(iso){
  if (!iso) return "";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 3600) return Math.max(1, Math.round(s / 60)) + "m ago";
  if (s < 86400) return Math.round(s / 3600) + "h ago";
  const d = Math.round(s / 86400);
  return d < 60 ? d + "d ago" : new Date(iso).toLocaleDateString("en-US", {month:"short", day:"numeric", year:"numeric"});
}
const SITE = DATA.mode === "site";
const fmt = (iso, o) => new Date(iso).toLocaleString("en-US", o);
const SHORT = {month:"short", day:"numeric", hour:"numeric", minute:"2-digit"};
let baseline = null;
function applyBaseline(){ DATA.items.forEach(i => { i.is_new = new Date(i.first_seen) > new Date(baseline); }); }
if (SITE) {
  // Hosted version: NEW means "added since you last opened this page in this browser".
  let sess = null, last = null;
  try { sess = sessionStorage.getItem("rf-baseline"); last = localStorage.getItem("rf-last-visit"); } catch (e) {}
  baseline = sess || last || new Date(Date.now() - 2 * 86400000).toISOString();
  try { sessionStorage.setItem("rf-baseline", baseline); localStorage.setItem("rf-last-visit", new Date().toISOString()); } catch (e) {}
  applyBaseline();
  $("#newLabel").textContent = "New since your last visit";
  $("#markSeen").hidden = false;
  $("#sort").value = "seen";
}
const off = new Set();
const when = fmt(DATA.generated, {weekday:"short", month:"short", day:"numeric", hour:"numeric", minute:"2-digit"});
const okShops = DATA.shops.filter(s => !s.error).length;
function renderMeta(){
  const newCount = DATA.items.filter(i => i.is_new).length;
  let since = "";
  if (SITE) since = ` · <b>${newCount} new</b> since ${esc(fmt(baseline, SHORT))}`;
  else if (!DATA.first_run) since = ` · <b>${newCount} new</b> since ${esc(fmt(DATA.previous, SHORT))}`;
  $("#meta").innerHTML = `${SITE ? "Checked every hour · last check" : "Updated"} <b>${esc(when)}</b> · ${DATA.items.length} listings from ${okShops} shops` + since;
}
renderMeta();
const failed = DATA.shops.filter(s => s.error);
const notes = [];
if (DATA.first_run && !SITE) notes.push("First run. From now on, anything that appears between runs gets a NEW tag.");
if (failed.length) notes.push("Couldn't reach " + failed.map(s => `<a href="${esc(s.link)}" target="_blank" rel="noopener">${esc(s.name)}</a> (${esc(s.error)})`).join("; ") + ". Their links still work.");
if (notes.length) { $("#notice").innerHTML = notes.join("<br>"); $("#notice").hidden = false; }
if (!SITE && !DATA.first_run && DATA.items.some(i => i.is_new)) $("#onlyNew").checked = true;
$("#markSeen").addEventListener("click", () => {
  baseline = new Date().toISOString();
  try { sessionStorage.setItem("rf-baseline", baseline); localStorage.setItem("rf-last-visit", baseline); } catch (e) {}
  applyBaseline(); renderMeta(); render();
});

$("#shops").innerHTML = DATA.shops.map(s => `<button type="button" class="shop${s.error ? " err" : ""}" aria-pressed="true" data-s="${esc(s.name)}" title="${esc(s.city)}">${esc(s.name)}<span class="n">${s.error ? "!" : s.count}</span></button>`).join("");
$("#shops").addEventListener("click", e => {
  const b = e.target.closest(".shop"); if (!b) return;
  const name = b.dataset.s;
  if (e.altKey || e.metaKey) { DATA.shops.forEach(s => s.name === name ? off.delete(s.name) : off.add(s.name)); }
  else if (off.has(name)) off.delete(name); else off.add(name);
  document.querySelectorAll(".shop").forEach(x => x.setAttribute("aria-pressed", off.has(x.dataset.s) ? "false" : "true"));
  render();
});
["#q", "#sort", "#onlyNew", "#onlyDrop"].forEach(id => $(id).addEventListener("input", render));

function render(){
  const q = $("#q").value.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const onlyNew = $("#onlyNew").checked, onlyDrop = $("#onlyDrop").checked, sort = $("#sort").value;
  let list = DATA.items.filter(i => !off.has(i.shop)
    && (!onlyNew || i.is_new) && (!onlyDrop || i.drop_from)
    && q.every(w => (i.title + " " + i.shop + " " + i.city + " " + i.size + " " + i.type).toLowerCase().includes(w)));
  const t = s => s ? new Date(s).getTime() : 0;
  if (sort === "new") list.sort((a, b) => t(b.published) - t(a.published));
  if (sort === "seen") list.sort((a, b) => t(b.first_seen) - t(a.first_seen) || t(b.published) - t(a.published));
  if (sort === "low") list.sort((a, b) => (a.price ?? 1e12) - (b.price ?? 1e12));
  if (sort === "high") list.sort((a, b) => (b.price ?? -1) - (a.price ?? -1));
  $("#count").textContent = list.length + " shown";
  if (!list.length) {
    $("#grid").innerHTML = `<p class="empty">${onlyNew ? (SITE ? "Nothing new since your last visit." : "Nothing new since the last run.") : "No listings match."}</p>`;
    return;
  }
  $("#grid").innerHTML = list.map(i => `
    <a class="card" href="${esc(i.link)}" target="_blank" rel="noopener">
      <div class="ph">
        ${i.image ? `<img src="${esc(i.image)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">` : ""}
        <span class="noimg">${esc(i.shop)}</span>
        <div class="badges">${i.is_new ? '<span class="b new">New</span>' : ""}${i.drop_from ? '<span class="b drop">Price cut</span>' : ""}</div>
      </div>
      <div class="t">${esc(i.title)}</div>
      <div class="row"><span class="price">${money(i.price, i.currency)}${i.drop_from ? `<s>${money(i.drop_from, i.currency)}</s>` : ""}</span><span class="size">${esc(i.size)}</span></div>
      <div class="src">${esc(i.shop)} · ${esc(i.city)} · ${ago(i.published)}</div>
    </a>`).join("");
}
render();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
