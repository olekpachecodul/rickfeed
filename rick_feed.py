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
    {"name": "Luxury Box ATL",    "city": "Atlanta",                "feed": ["https://luxuryboxatl.com/collections/rick-owens.atom",
                                                                              "https://luxuryboxatl.com/collections/rick-owens-drkshdw.atom"], "link": "https://luxuryboxatl.com/collections/rick-owens"},
    {"name": "Groupie",           "city": "Los Angeles",            "feed": "https://groupie.store/collections/rick-owens.atom",              "link": "https://groupie.store/collections/rick-owens"},
    {"name": "Archived",          "city": "Los Angeles",            "feed": "https://archived.co/collections/rick-owens.atom",                "link": "https://archived.co/collections/rick-owens"},
    {"name": "Justin Reed",       "city": "Los Angeles + New York", "feed": ["https://justinreed.com/collections/rick-owens.atom",
                                                                              "https://justinreed.com/collections/rick-owens-drkshdw.atom"],   "link": "https://justinreed.com/collections/rick-owens"},
    {"name": "Midtown Archive",   "city": "Online",                 "feed": "https://midtownarchive.com/collections/rick-owens.atom",         "link": "https://midtownarchive.com/collections/rick-owens"},
    {"name": "Descry Archive",    "city": "By appointment",         "feed": "https://www.descryarchive.com/collections/rick-owens.atom",      "link": "https://www.descryarchive.com/collections/rick-owens"},
    # Added Nov 8, 2026
    {"name": "2nd Street",        "city": "60+ US stores",          "feed": "https://ec.2ndstreetusa.com/collections/rick-raf.atom",          "link": "https://ec.2ndstreetusa.com/collections/rick-raf",               "rick_only": True},
    {"name": "Resurrection",      "city": "West Hollywood",         "feed": "https://resurrectionvintage.com/collections/rick-owens.atom",    "link": "https://resurrectionvintage.com/collections/rick-owens",         "rick_only": True},
    {"name": "Pilgrim",           "city": "New York",               "feed": "https://pilgrimnyc.com/collections/45rpm.atom",                  "link": "https://pilgrimnyc.com/collections/45rpm",                       "rick_only": True},
    {"name": "Michael's",         "city": "New York",               "feed": "https://michaelsconsignment.com/collections/rick-owens.atom",    "link": "https://michaelsconsignment.com/collections/rick-owens"},
    {"name": "Graceful Misfits",  "city": "Online",                 "feed": ["https://gracefulmisfits.com/collections/mainline.atom",
                                                                              "https://gracefulmisfits.com/collections/drkshdw.atom"],         "link": "https://gracefulmisfits.com/"},
    # Added Nov 12, 2026
    {"name": "Street Commerce",   "city": "Charlotte",              "feed": "https://streetcommerce.shop/collections/rick-owens.atom",        "link": "https://streetcommerce.shop/collections/rick-owens"},
    {"name": "LUXE MIA",          "city": "Miami",                  "feed": "https://luxemia.net/collections/rick-owens-2.atom",              "link": "https://luxemia.net/collections/rick-owens-2"},
    {"name": "Performa",          "city": "Atlanta",                "feed": "https://performaatlanta.com/collections/rick-owens.atom",        "link": "https://performaatlanta.com/collections/rick-owens"},
]

# DRKSHDW is Rick Owens' diffusion line and is often listed without "Rick Owens"
# anywhere, so it counts on its own (title or vendor), as do common misspellings.
DRK = re.compile(r"drk\s*shdw|drk\s*shadow|drksdhw|drkshw|dark\s*shadow", re.I)
LILIES = re.compile(r"\blilies\b", re.I)
RICK = re.compile(r"rick\s*owens|" + DRK.pattern, re.I)


def line_of(title, vendor):
    """Which Rick Owens line a listing belongs to, for the card label and filter."""
    text = f"{title} {vendor}"
    if DRK.search(text):
        return "DRKSHDW"
    if LILIES.search(text) and RICK.search(text):
        return "Lilies"
    return "Rick Owens"
# ---------------------------------------------------------------------------
# Category and colour. Shops label things inconsistently, so these are worked
# out from the shop's product type, the colour option, variant names and the
# title. First matching category wins, so the order below matters.
# ---------------------------------------------------------------------------
CATEGORIES = [
    ("Footwear", r"shoes?|sneakers?|(?<!boot)boots?(?!\s*-?cut)|geobaskets?|geos|ramones?|dunks?|sandals?|slides?|creepers?|loafers?|mules?"
                 r"|bozo|tractor|runners?|vans|converse|turbo\s*drk|trainers?|slippers?|kiss\s*boots?|mega\s*bumper|lunar|footwear|derby|sneaks|quad\s*sole"),
    ("Bags & accessories", r"bags?|tote|pouch|backpack|wallet|belt|hats?|caps?|beanie|scarf|gloves?|sunglasses|eyewear|glasses|socks?"
                 r"|ring|necklace|bracelet|earrings?|jewel(?:le)?ry|keychain|accessor(?:y|ies)|mask|candle|cushion|blanket"),
    ("Outerwear", r"jackets?|jkt|coats?|parkas?|bombers?|blazers?|trench|outershirt|vest|gilet|liner|anorak|windbreaker|puffer|mac|cape|peacoat|outerwear|shearling|fishtail|trenchcoat|overcoat|raincoat|topcoat|overshirt"),
    ("Bottoms", r"pants?|trousers?|jeans|shorts|cargos?|sweatpants|sweats|joggers?|leggings?|bootcuts?|skirts?|bela|creatch|creach|detroit|pods?|bolan|tyrone|astaires|berlin\s*cut|kilt|selvedge|bottoms"),
    ("Dresses", r"dress(?:es)?|gown|jumpsuit|overall"),
    ("Tops", r"t-?shirts?|tees?|tops?|tank|shirts?|hoodies?|hooded|sweaters?|sweatshirts?|knit|cardigan|pullover|crewneck|turtleneck|jumper|polo|long\s*sleeve|blouse|tunic|fleece|knitwear"),
]
assert {c for c, _ in CATEGORIES} == {"Outerwear", "Tops", "Bottoms", "Dresses", "Footwear", "Bags & accessories"}  # keep the page's chip list in step
CATEGORY_RE = [(name, re.compile(r"\b(?:" + pat + r")\b", re.I)) for name, pat in CATEGORIES]

COLOURS = [  # (name, swatch, words). Rick's own names map onto plain colours.
    ("Black",  "#111111", r"black|blk|noir|jet|onyx|nero|ink"),
    ("White",  "#F4F2EC", r"white|milk|cream|ivory|natural|pearl|chalk|oyster|ecru|off[\s-]?white|bone|optic|egg\s*shell|eggshell|wht|crm"),
    ("Grey",   "#8E8C88", r"gr[ae]y|dust|charcoal|smoke|slate|ash|silver|steel|concrete|cement|pelican|fog|graphite|metal|stone|gry"),
    ("Brown",  "#7A5A43", r"brown|beige|tan|camel|mushroom|sand|khaki|tobacco|toffee|bark|taupe|mud|coffee|mocha|nude|caramel|chocolate|earth|dune|biscuit|walnut|brn"),
    ("Green",  "#5C6B4A", r"green|olive|moss|forest|military|army|sage|mint|lime|grn"),
    ("Blue",   "#3F5A7A", r"blue|navy|indigo|denim\s*blue|cobalt|sky|teal|turquoise|petrol|blu"),
    ("Red",    "#9C2E2E", r"red|burgundy|bordeaux|cherry|wine|maroon|oxblood|rust|cardinal|scarlet|pink|fuchsia|rose|blush|magenta|amethyst\s*red"),
    ("Purple", "#6A4C7A", r"purple|lilac|grape|violet|lavender|plum|amethyst|orchid|mauve"),
    ("Yellow", "#D2A93C", r"yellow|mustard|gold|lemon|orange|amber|ochre|saffron|tangerine|honey"),
]
COLOUR_RE = [(name, re.compile(r"\b(?:" + pat + r")\b", re.I)) for name, _, pat in COLOURS]


def category_of(product_type, title):
    for text in (product_type, title):  # the shop's own type is the better clue when it's specific
        for name, rx in CATEGORY_RE:
            if text and rx.search(text):
                return name
    return "Other"


def colours_of(*texts):
    text = " ".join(t for t in texts if t)
    return [name for name, rx in COLOUR_RE if rx.search(text)]


PRICE_DROP_DAYS = 7          # how long a price cut stays flagged
FORGET_AFTER_DAYS = 60       # drop items from memory once unseen this long
AVAIL_MAX_PAGES = 4          # pages of products.json read per feed to spot sold items
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
            "line": line_of(title, vendor),
            "colour_hint": " ".join(" ".join((vt or "").split(" / ")[:-1]) for vt in vtitles),
            "sold": False,
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


PID_RE = re.compile(r"/products/(\d+)\s*$")
HANDLE_RE = re.compile(r"/products/([^/?#]+)")


def product_keys(item):
    """Ways to match a feed item against products.json: numeric id and handle."""
    keys = []
    m = PID_RE.search(item["id"])
    if m:
        keys.append(m.group(1))
    m = HANDLE_RE.search(item["link"])
    if m:
        keys.append(m.group(1))
    return keys


def fetch_details(feed_url, wanted):
    """The .atom feed doesn't say what's sold and has little else to go on, so
    ask the same collection's products.json. Returns {product id or handle:
    {"available", "type", "colours"}}. Anything it can't find is left out;
    those items count as for sale and are classified from the feed alone."""
    if not feed_url.endswith(".atom"):
        return {}
    base = feed_url[:-len(".atom")] + "/products.json?limit=250&page="
    details, remaining = {}, set(wanted)
    for page in range(1, AVAIL_MAX_PAGES + 1):
        try:
            products = json.loads(fetch_bytes(base + str(page))).get("products") or []
        except Exception:
            break
        for p in products:
            colour_opts = [i for i, o in enumerate(p.get("options") or [])
                           if re.match(r"colou?r", str(o.get("name", "")), re.I)]
            colour_words = []
            for v in p.get("variants") or []:
                colour_words += [str(v.get(f"option{i + 1}") or "") for i in colour_opts]
            tags = p.get("tags") or []
            if isinstance(tags, str):
                tags = tags.split(",")
            colour_words += [t.split(":", 1)[-1] for t in tags if re.match(r"\s*colou?r\s*[:_-]", t, re.I)]
            d = {"available": any(v.get("available") for v in p.get("variants") or []),
                 "type": p.get("product_type") or "",
                 "colours": " ".join(colour_words)}
            for k in (str(p.get("id", "")), p.get("handle") or ""):
                if k:
                    details[k] = d
                    remaining.discard(k)
        if len(products) < 250 or not remaining:
            break
    return details


def enrich(it, d):
    """Sold flag, category and colours, from products.json details when found."""
    d = d or {}
    it["sold"] = d.get("available") is False
    it["category"] = category_of(d.get("type") or it.get("type"), it["title"])
    it["colours"] = colours_of(d.get("colours"), it.pop("colour_hint", ""), it["title"])


def fetch_shop(shop):
    feeds = shop["feed"] if isinstance(shop["feed"], list) else [shop["feed"]]
    items, errors, seen_ids = [], [], set()
    for url in feeds:
        got, err = fetch_one(shop, url)
        if err:
            errors.append(err)
        details = fetch_details(url, {k for it in got for k in product_keys(it)}) if got else {}
        for it in got:
            found = [details[k] for k in product_keys(it) if k in details]
            enrich(it, found[0] if found else None)
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
    newest = sorted((i for i in items if not i.get("sold")), key=lambda i: i["first_seen"], reverse=True)[:60]
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
            sold = sum(1 for i in items if i.get("sold"))
            status = f"{len(items)} items, {sold} sold" if err is None else f"skipped: {err}"
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
            "first_run": first_run, "shops": shops_out, "items": all_items,
            "categories": ["Outerwear", "Tops", "Bottoms", "Dresses", "Footwear", "Bags & accessories", "Other"], "colours": [[n, sw] for n, sw, _ in COLOURS]}
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(PAGE.replace("__DATA__", payload), encoding="utf-8")
    if site_mode:
        (out_file.parent / "feed.xml").write_text(build_atom(all_items, run_iso), encoding="utf-8")
        (out_file.parent / ".nojekyll").write_text("", encoding="utf-8")

    new_count = sum(1 for i in all_items if i.get("is_new"))
    failed = [s["name"] for s in shops_out if s["error"]]
    print(f"\n{len(all_items)} Rick Owens listings" + ("" if first_run else f", {new_count} new since last run") + ".")
    cats = {}
    for i in all_items:
        cats[i.get("category", "Other")] = cats.get(i.get("category", "Other"), 0) + 1
    print("By category: " + ", ".join(f"{k} {v}" for k, v in sorted(cats.items(), key=lambda kv: -kv[1]))
          + f". No colour found for {sum(1 for i in all_items if not i.get('colours'))}.")
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
<meta name="theme-color" content="#E5E5E5" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#000000" media="(prefers-color-scheme: dark)">
<title>Rick Feed</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600&display=swap">
<style>
/* Gallery-quiet: flat studio grey, black type, tiny tracked capitals, product shots floating on the page. */
:root{
  --bg:#E5E5E5; --ink:#000000; --muted:#666666; --soft:#8A8A8A; --line:#C9C9C9;
  --tag-ink:#FFFFFF; --ph:#E5E5E5; --blend:multiply; --fit:contain;
  --f:"Montserrat","Gotham","Helvetica Neue",Arial,sans-serif;
  --track:.08em; --gut:40px;
}
@media (prefers-color-scheme: dark){:root{
  --bg:#000000; --ink:#FFFFFF; --muted:#8A8A8A; --soft:#5C5C5C; --line:#262626;
  --tag-ink:#000000; --ph:#111111; --blend:normal; --fit:cover;
  color-scheme:dark;
}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:400 11px/1.6 var(--f);letter-spacing:var(--track);text-transform:uppercase;-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}
button,input,select{font:inherit;letter-spacing:inherit;text-transform:inherit;color:inherit}
.wrap{max-width:1680px;margin:0 auto;padding:0 max(var(--gut),env(safe-area-inset-left)) 0 max(var(--gut),env(safe-area-inset-right))}

header{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:22px 0 10px}
.mark{font-weight:500;font-size:13px;letter-spacing:.32em;margin:0}
.count{color:var(--ink);white-space:nowrap}
.crumbs{font-size:9px;line-height:1.5;color:var(--muted);display:flex;flex-wrap:wrap;gap:2px 0}
.crumbs > span:not(:last-child)::after{content:"/";margin:0 7px;color:var(--soft)}
.crumbs b{font-weight:400;color:var(--ink)}
.notice{margin-top:12px;font-size:9px;color:var(--muted);max-width:110ch}
.notice a{color:var(--ink);text-decoration:underline;text-underline-offset:2px}

.bar{position:sticky;top:0;z-index:5;background:var(--bg);margin-top:18px;padding:12px 0;display:flex;flex-wrap:wrap;align-items:center;gap:10px 22px;border-bottom:1px solid var(--line)}
.bar input[type=search]{flex:1 1 220px;min-width:0;background:transparent;border:0;border-bottom:1px solid var(--ink);border-radius:0;padding:6px 0;outline:0;-webkit-appearance:none}
.bar input[type=search]::placeholder{color:var(--soft)}
.bar input[type=search]:focus-visible{border-bottom-width:2px;padding-bottom:5px}
.sel{position:relative;display:inline-flex;align-items:center}
.sel select{-webkit-appearance:none;appearance:none;background:transparent;border:0;border-radius:0;padding:6px 16px 6px 0;cursor:pointer}
.sel::after{content:"";position:absolute;right:2px;top:50%;width:5px;height:5px;border-right:1px solid currentColor;border-bottom:1px solid currentColor;transform:translateY(-70%) rotate(45deg);pointer-events:none}
.sel option{text-transform:none;background:var(--bg);color:var(--ink)}
.togs{display:flex;flex-wrap:wrap;gap:8px}
.tog{position:relative;display:inline-flex;align-items:center;height:30px;padding:0 12px;border:1px solid var(--soft);color:var(--muted);cursor:pointer;user-select:none;background:transparent;white-space:nowrap}
.tog input{position:absolute;opacity:0;width:1px;height:1px;pointer-events:none}
.tn{margin-left:6px;opacity:.6}
.grid > .empty{grid-column:1/-1;display:flex;flex-wrap:wrap;align-items:center;gap:12px 18px;margin:0}
.tog:has(input:checked){background:var(--ink);border-color:var(--ink);color:var(--tag-ink)}
.tog:has(input:focus-visible){outline:1px solid var(--ink);outline-offset:3px}
button.tog{border-color:var(--soft)}
button.tog:hover,.tog:hover{color:var(--ink);border-color:var(--ink)}
.tog:has(input:checked):hover{color:var(--tag-ink)}

.filters{display:grid;grid-template-columns:minmax(0,3fr) minmax(0,3fr) minmax(0,2fr);gap:20px 40px;padding:18px 0 20px;border-bottom:1px solid var(--line)}
.filters[hidden]{display:none}
.fg h2{margin:0 0 10px;font-size:9px;font-weight:500;letter-spacing:.14em;color:var(--muted)}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{display:inline-flex;align-items:center;gap:7px;height:28px;padding:0 10px;border:1px solid var(--line);background:transparent;cursor:pointer;font-size:10px;white-space:nowrap}
.chip .tn{margin-left:0}
.chip[aria-pressed=true]{background:var(--ink);border-color:var(--ink);color:var(--tag-ink)}
.chip:hover{border-color:var(--ink)}
.chip.zero:not([aria-pressed=true]){color:var(--soft)}
.sw{width:10px;height:10px;flex:none;box-shadow:inset 0 0 0 1px rgba(128,128,128,.45)}
.price-in{display:flex;align-items:center;gap:10px}
.price-in label{display:flex;align-items:center;gap:6px;flex:1 1 0;min-width:0;border-bottom:1px solid var(--ink);padding:5px 0}
.price-in input{width:100%;min-width:0;background:transparent;border:0;outline:0;padding:0}
.price-in input::placeholder{color:var(--soft)}
.price-in label:focus-within{border-bottom-width:2px;padding-bottom:4px}
.presets{margin-top:10px}
.clear{margin-top:14px;background:none;border:0;padding:0;cursor:pointer;color:var(--muted);text-decoration:underline;text-underline-offset:3px;font-size:9px}
.clear:hover{color:var(--ink)}
#filtersBtn[aria-expanded=true],#filtersBtn.on{background:var(--ink);border-color:var(--ink);color:var(--tag-ink)}
@media (max-width:900px){.filters{grid-template-columns:1fr;gap:22px}}
.shops{display:flex;flex-wrap:wrap;gap:6px 18px;padding:14px 0 6px}
.shop{border:0;background:none;padding:2px 0;cursor:pointer;font-size:10px;color:var(--ink)}
.shop .n{color:var(--soft);margin-left:5px}
.shop[aria-pressed=false]{color:var(--soft);text-decoration:line-through}
.shop.err .n{color:var(--muted)}
.shop:hover{text-decoration:underline;text-underline-offset:3px}

.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:64px 24px;padding:36px 0 96px}
.card{display:flex;flex-direction:column;min-width:0}
.ph{position:relative;aspect-ratio:3/4;background:var(--ph);overflow:hidden}
.ph img{position:relative;z-index:1;width:100%;height:100%;object-fit:var(--fit);mix-blend-mode:var(--blend);display:block;transition:opacity .2s}
.card:hover .ph img{opacity:.86}
.noimg{position:absolute;inset:0;display:none;place-items:center;color:var(--soft);font-size:10px}
.ph.noi .noimg{display:grid}
.badges{position:absolute;z-index:2;left:0;top:0;display:flex;gap:4px;flex-wrap:wrap}
.b{font-size:9px;font-weight:500;letter-spacing:.12em;padding:4px 7px;line-height:1.2}
.b.new{background:var(--ink);color:var(--tag-ink)}
.b.drop{background:var(--bg);color:var(--ink);box-shadow:inset 0 0 0 1px var(--ink)}
.b.sold{background:var(--soft);color:#FFFFFF}
.line{margin-top:16px;font-weight:500}
.t{color:var(--ink);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.price{margin-top:14px;font-weight:500}
.price s{color:var(--soft);font-weight:400;margin-left:8px}
.row{display:flex;justify-content:space-between;gap:12px;margin-top:12px;font-weight:500}
.row .go{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.row .size{white-space:nowrap;color:var(--ink)}
.card:hover .go{text-decoration:underline;text-underline-offset:3px}
.src{font-size:9px;color:var(--muted);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.card.sold .ph img{opacity:.45;filter:grayscale(1)}
.card.sold .price{color:var(--soft);text-decoration:line-through}
.empty{padding:48px 0;color:var(--muted)}
footer{padding:0 0 48px;font-size:9px;color:var(--muted);display:flex;flex-wrap:wrap;gap:4px 24px}
footer a:hover{color:var(--ink)}
:focus-visible{outline:1px solid var(--ink);outline-offset:3px}
@media (prefers-reduced-motion:reduce){.ph img{transition:none}}
@media (max-width:900px){:root{--gut:16px}.grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:48px 16px;padding-top:28px}}
@media (max-width:520px){.bar{gap:10px 16px}.bar input[type=search]{flex-basis:100%}.tog{height:28px;padding:0 10px}
  .shops{flex-wrap:nowrap;overflow-x:auto;scrollbar-width:none;margin:0 calc(-1 * var(--gut));padding:14px var(--gut) 8px}.shops::-webkit-scrollbar{display:none}.shop{flex:none}}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1 class="mark">Rick Feed</h1>
    <span class="count" id="count"></span>
  </header>
  <div class="crumbs" id="meta"></div>
  <div class="notice" id="notice" hidden></div>
  <div class="bar">
    <input type="search" id="q" autocomplete="off" placeholder="Search: geobasket, bela, 48, leather" aria-label="Search listings">
    <span class="sel"><select id="line" autocomplete="off" aria-label="Line">
      <option value="">All lines</option>
      <option value="Rick Owens">Rick Owens</option>
      <option value="DRKSHDW">DRKSHDW</option>
      <option value="Lilies">Lilies</option>
    </select></span>
    <span class="sel"><select id="sort" autocomplete="off" aria-label="Sort">
      <option value="new">Newest listed</option>
      <option value="seen">Newest found</option>
      <option value="low">Price: low to high</option>
      <option value="high">Price: high to low</option>
    </select></span>
    <div class="togs">
      <button type="button" class="tog" id="filtersBtn" aria-expanded="false" aria-controls="filters">Filters<span class="tn" id="fN"></span></button>
      <label class="tog"><input type="checkbox" id="onlyNew" autocomplete="off"><span id="newLabel">New since last run</span><span class="tn" id="newN"></span></label>
      <label class="tog"><input type="checkbox" id="onlyDrop" autocomplete="off">Price cuts<span class="tn" id="dropN"></span></label>
      <label class="tog"><input type="checkbox" id="hideSold" autocomplete="off" checked>Hide sold<span class="tn" id="soldN"></span></label>
      <button type="button" class="tog" id="markSeen" hidden>Mark all seen</button>
    </div>
  </div>
  <section class="filters" id="filters" hidden aria-label="Filters">
    <div class="fg"><h2>Category</h2><div class="chips" id="cats"></div></div>
    <div class="fg"><h2>Colour</h2><div class="chips" id="cols"></div></div>
    <div class="fg"><h2>Price (USD)</h2>
      <div class="price-in">
        <label>$<input id="pmin" type="text" inputmode="numeric" autocomplete="off" placeholder="Min" aria-label="Minimum price"></label>
        <span aria-hidden="true">&ndash;</span>
        <label>$<input id="pmax" type="text" inputmode="numeric" autocomplete="off" placeholder="Max" aria-label="Maximum price"></label>
      </div>
      <div class="chips presets" id="presets">
        <button type="button" class="chip" data-min="" data-max="250">Under $250</button>
        <button type="button" class="chip" data-min="250" data-max="500">$250&ndash;500</button>
        <button type="button" class="chip" data-min="500" data-max="1000">$500&ndash;1k</button>
        <button type="button" class="chip" data-min="1000" data-max="2000">$1k&ndash;2k</button>
        <button type="button" class="chip" data-min="2000" data-max="">$2k+</button>
      </div>
      <button type="button" class="clear" id="clearFilters">Clear filters</button>
    </div>
  </section>
  <div class="shops" id="shops"></div>
  <main class="grid" id="grid"></main>
  <footer id="foot"></footer>
</div>
<script>
const DATA = __DATA__;
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const money = (n, cur) => n == null ? "" : new Intl.NumberFormat("en-US", {style:"currency", currency: cur || "USD", maximumFractionDigits: n % 1 ? 2 : 0}).format(n);
function ago(iso){
  if (!iso) return "";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 3600) return Math.max(1, Math.round(s / 60)) + " min ago";
  if (s < 86400) return Math.round(s / 3600) + " hr ago";
  const d = Math.round(s / 86400);
  return d < 60 ? d + (d === 1 ? " day ago" : " days ago") : new Date(iso).toLocaleDateString("en-US", {month:"short", day:"numeric", year:"numeric"});
}
// The line label already sits above the title, so drop a repeated "Rick Owens DRKSHDW" prefix.
const PREFIX = /^\s*(?:(?:pre-?owned|new|used)\s+)?(?:rick\s*owens\s*)?(?:(?:drk\s*shdw|drkshdw|lilies)\s*)?(?:[-–—:\/|]\s*)?/i;
const cleanTitle = t => { const c = String(t || "").replace(PREFIX, "").trim(); return c.length > 2 ? c : t; };
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
  $("#newLabel").textContent = "New since last visit";
  $("#markSeen").hidden = false;
  $("#sort").value = "seen";
  $("#foot").innerHTML = '<a href="feed.xml">Feed (RSS)</a><span>Prices in USD as listed by each shop</span>';
}
DATA.items.forEach(i => { i.line = i.line || "Rick Owens"; i.display = cleanTitle(i.title); });
$("#q").value = ""; $("#onlyNew").checked = false; $("#onlyDrop").checked = false; $("#line").value = "";
const off = new Set();
const when = fmt(DATA.generated, {weekday:"short", month:"short", day:"numeric", hour:"numeric", minute:"2-digit"});
const okShops = DATA.shops.filter(s => !s.error).length;
try { $("#hideSold").checked = localStorage.getItem("rf-hide-sold") !== "0"; } catch (e) {}
try { const l = localStorage.getItem("rf-line"); if (l !== null && [...$("#line").options].some(o => o.value === l)) $("#line").value = l; } catch (e) {}
$("#hideSold").addEventListener("input", () => {
  try { localStorage.setItem("rf-hide-sold", $("#hideSold").checked ? "1" : "0"); } catch (e) {}
  renderMeta();
});
$("#line").addEventListener("input", () => { try { localStorage.setItem("rf-line", $("#line").value); } catch (e) {} });
const forSale = i => !$("#hideSold").checked || !i.sold;
function renderMeta(){
  const newCount = DATA.items.filter(i => i.is_new && forSale(i)).length;
  const parts = [SITE ? "Checked hourly" : "Updated", `Last check <b>${esc(when)}</b>`, `${DATA.items.length} listings`, `${okShops} shops`];
  if (SITE) parts.push(`<b>${newCount} new</b> since ${esc(fmt(baseline, SHORT))}`);
  else if (!DATA.first_run) parts.push(`<b>${newCount} new</b> since ${esc(fmt(DATA.previous, SHORT))}`);
  $("#meta").innerHTML = parts.map(p => `<span>${p}</span>`).join("");
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

$("#shops").innerHTML = DATA.shops.map(s => `<button type="button" class="shop${s.error ? " err" : ""}" aria-pressed="true" data-s="${esc(s.name)}" title="${esc(s.city)}${s.error ? " (couldn't reach this shop)" : ""}">${esc(s.name)}<span class="n">${s.error ? "!" : s.count}</span></button>`).join("");
$("#shops").addEventListener("click", e => {
  const b = e.target.closest(".shop"); if (!b) return;
  const name = b.dataset.s;
  if (e.altKey || e.metaKey) { DATA.shops.forEach(s => s.name === name ? off.delete(s.name) : off.add(s.name)); }
  else if (off.has(name)) off.delete(name); else off.add(name);
  document.querySelectorAll(".shop").forEach(x => x.setAttribute("aria-pressed", off.has(x.dataset.s) ? "false" : "true"));
  render();
});
["#q", "#sort", "#line", "#onlyNew", "#onlyDrop", "#hideSold", "#pmin", "#pmax"].forEach(id => $(id).addEventListener("input", render));

// Category / colour / price filters. Several categories or colours = any of them.
const cats = new Set(), cols = new Set();
const CATS = DATA.categories || [], COLS = DATA.colours || [];
DATA.items.forEach(i => { i.category = i.category || "Other"; i.colours = i.colours || []; });
$("#pmin").value = ""; $("#pmax").value = "";
$("#cats").innerHTML = CATS.map(c => `<button type="button" class="chip" aria-pressed="false" data-v="${esc(c)}">${esc(c)}<span class="tn"></span></button>`).join("");
$("#cols").innerHTML = COLS.map(([c, sw]) => `<button type="button" class="chip" aria-pressed="false" data-v="${esc(c)}"><span class="sw" style="background:${esc(sw)}"></span>${esc(c)}<span class="tn"></span></button>`).join("");
const toggleIn = (set, el) => { const v = el.dataset.v; set.has(v) ? set.delete(v) : set.add(v); el.setAttribute("aria-pressed", set.has(v)); render(); };
$("#cats").addEventListener("click", e => { const b = e.target.closest(".chip"); if (b) toggleIn(cats, b); });
$("#cols").addEventListener("click", e => { const b = e.target.closest(".chip"); if (b) toggleIn(cols, b); });
$("#presets").addEventListener("click", e => {
  const b = e.target.closest(".chip"); if (!b) return;
  const same = $("#pmin").value === b.dataset.min && $("#pmax").value === b.dataset.max;
  $("#pmin").value = same ? "" : b.dataset.min; $("#pmax").value = same ? "" : b.dataset.max; render();
});
$("#filtersBtn").addEventListener("click", () => {
  const open = $("#filters").hidden; $("#filters").hidden = !open; $("#filtersBtn").setAttribute("aria-expanded", open);
});
function clearFilters(){
  cats.clear(); cols.clear(); $("#pmin").value = ""; $("#pmax").value = "";
  document.querySelectorAll("#cats .chip, #cols .chip").forEach(b => b.setAttribute("aria-pressed", "false"));
}
$("#clearFilters").addEventListener("click", () => { clearFilters(); render(); });
const num = v => { const n = parseFloat(String(v).replace(/[^0-9.]/g, "")); return isFinite(n) ? n : null; };

function render(){
  const q = $("#q").value.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const onlyNew = $("#onlyNew").checked, onlyDrop = $("#onlyDrop").checked, sort = $("#sort").value, line = $("#line").value;
  const inLine = i => !line || i.line === line;
  document.querySelectorAll(".shop:not(.err) .n").forEach(n => {
    const name = n.parentElement.dataset.s;
    n.textContent = DATA.items.filter(i => i.shop === name && forSale(i) && inLine(i)).length;
  });
  const pmin = num($("#pmin").value), pmax = num($("#pmax").value);
  const passes = (i, skip) => !off.has(i.shop) && forSale(i) && inLine(i)
    && (!onlyNew || i.is_new) && (!onlyDrop || i.drop_from)
    && (skip === "cat" || !cats.size || cats.has(i.category))
    && (skip === "col" || !cols.size || i.colours.some(c => cols.has(c)))
    && (pmin == null || (i.price != null && i.price >= pmin))
    && (pmax == null || (i.price != null && i.price <= pmax))
    && q.every(w => (i.title + " " + i.line + " " + i.shop + " " + i.city + " " + i.size + " " + i.type + " " + i.category + " " + i.colours.join(" ")).toLowerCase().includes(w));
  let list = DATA.items.filter(i => passes(i));
  const facet = (sel, skip, has) => document.querySelectorAll(sel + " .chip").forEach(b => {
    const n = DATA.items.filter(i => passes(i, skip) && has(i, b.dataset.v)).length;
    b.querySelector(".tn").textContent = n; b.classList.toggle("zero", n === 0);
  });
  facet("#cats", "cat", (i, v) => i.category === v);
  facet("#cols", "col", (i, v) => i.colours.includes(v));
  document.querySelectorAll("#presets .chip").forEach(b => b.setAttribute("aria-pressed", $("#pmin").value === b.dataset.min && $("#pmax").value === b.dataset.max && (b.dataset.min || b.dataset.max) ? "true" : "false"));
  const active = cats.size + cols.size + (pmin != null || pmax != null ? 1 : 0);
  $("#fN").textContent = active || "";
  $("#filtersBtn").classList.toggle("on", active > 0);
  const t = s => s ? new Date(s).getTime() : 0;
  if (sort === "new") list.sort((a, b) => t(b.published) - t(a.published));
  if (sort === "seen") list.sort((a, b) => t(b.first_seen) - t(a.first_seen) || t(b.published) - t(a.published));
  if (sort === "low") list.sort((a, b) => (a.price ?? 1e12) - (b.price ?? 1e12));
  if (sort === "high") list.sort((a, b) => (b.price ?? -1) - (a.price ?? -1));
  $("#count").textContent = list.length + " shown";
  const pool = DATA.items.filter(i => !off.has(i.shop) && inLine(i));
  $("#newN").textContent = pool.filter(i => i.is_new && forSale(i)).length;
  $("#dropN").textContent = pool.filter(i => i.drop_from && forSale(i)).length;
  $("#soldN").textContent = pool.filter(i => i.sold).length;
  if (!list.length) {
    const why = [];
    if (onlyDrop) why.push("Price cuts is on");
    if (onlyNew) why.push(SITE ? "New since last visit is on" : "New since last run is on");
    if (line) why.push("showing " + line + " only");
    if (q.length) why.push("searching for \u201c" + $("#q").value.trim() + "\u201d");
    if (off.size) why.push(off.size + (off.size === 1 ? " shop" : " shops") + " switched off");
    if (cats.size) why.push("category: " + [...cats].join(" or "));
    if (cols.size) why.push("colour: " + [...cols].join(" or "));
    if (pmin != null || pmax != null) why.push("price " + (pmin != null ? "from $" + pmin : "") + (pmin != null && pmax != null ? " " : "") + (pmax != null ? "up to $" + pmax : ""));
    const msg = onlyDrop && !DATA.items.some(i => i.drop_from) ? "No price cuts yet." : onlyNew && !DATA.items.some(i => i.is_new) ? (SITE ? "Nothing new since your last visit." : "Nothing new since the last run.") : "No listings match.";
    $("#grid").innerHTML = `<p class="empty"><span>${esc(msg)}${why.length ? " " + esc(why.join(", ")) + "." : ""}</span>${why.length ? '<button type="button" class="tog" id="reset">Show everything</button>' : ""}</p>`;
    const r = $("#reset");
    if (r) r.addEventListener("click", () => {
      $("#q").value = ""; $("#onlyNew").checked = false; $("#onlyDrop").checked = false; $("#line").value = "";
      try { localStorage.setItem("rf-line", ""); } catch (e) {}
      off.clear(); document.querySelectorAll(".shop").forEach(x => x.setAttribute("aria-pressed", "true"));
      clearFilters();
      render();
    });
    return;
  }
  $("#grid").innerHTML = list.map(i => `
    <a class="card${i.sold ? " sold" : ""}" href="${esc(i.link)}" target="_blank" rel="noopener">
      <div class="ph${i.image ? "" : " noi"}">
        ${i.image ? `<img src="${esc(i.image)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.parentElement.classList.add('noi');this.remove()">` : ""}
        <span class="noimg">${esc(i.shop)}</span>
        <div class="badges">${i.is_new ? '<span class="b new">New</span>' : ""}${i.drop_from && !i.sold ? '<span class="b drop">Price cut</span>' : ""}${i.sold ? '<span class="b sold">Sold</span>' : ""}</div>
      </div>
      <div class="line">${esc(i.line)}</div>
      <div class="t">${esc(i.display)}</div>
      <div class="price">${money(i.price, i.currency)}${i.drop_from ? `<s>${money(i.drop_from, i.currency)}</s>` : ""}</div>
      <div class="row"><span class="go">${esc(i.shop)} +</span><span class="size">${i.size ? "Size " + esc(i.size) : ""}</span></div>
      <div class="src">${esc(i.city)} / ${ago(i.published)}</div>
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
