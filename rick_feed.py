#!/usr/bin/env python3
"""
Rick Feed: one page of the newest Rick Owens listings from resale shops (mostly US).

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
import threading
import time
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
    {"name": "Crybynoon Archive", "city": "Pasadena, MD",           "feed": "https://crybynoon.com/collections/rick-owens.atom",              "link": "https://crybynoon.com/collections/rick-owens"},
    # Outside the US. Prices are converted to USD on the page (original shown alongside).
    {"name": "VSP Consignment",   "city": "Calgary, Canada",        "feed": "https://vspconsignment.com/collections/rick-owens.atom",         "link": "https://vspconsignment.com/en-us/collections/rick-owens"},
    {"name": "DRIEW",             "city": "Toronto, Canada",        "feed": "https://driewgarments.com/collections/rick-owens.atom",          "link": "https://driewgarments.com/collections/rick-owens"},
    {"name": "Throat",            "city": "Toronto, Canada",        "feed": ["https://shopthroat.com/collections/rick-owens.atom",
                                                                              "https://shopthroat.com/collections/rick-owens-drkshdw.atom"],  "link": "https://shopthroat.com/collections/rick-owens"},
    {"name": "Archive Factory",   "city": "Tokyo, Japan",           "feed": "https://archive-factory.com/collections/rick-owens.atom",        "link": "https://archive-factory.com/collections/rick-owens"},
    {"name": "Elevated Archives", "city": "Padua, Italy",           "feed": "https://elevated-archives.com/collections/rick-owens.atom",      "link": "https://elevated-archives.com/collections/rick-owens"},
    {"name": "Sunday Nightmare",  "city": "Bangkok, Thailand",      "feed": "https://sundaynightmare.com/collections/rick-owens.atom",        "link": "https://sundaynightmare.com/collections/rick-owens"},
    {"name": "DolceVitaHub",      "city": "Paris area, France",     "feed": "https://dolcevitahub.com/collections/rick-owens.atom",           "link": "https://dolcevitahub.com/collections/rick-owens"},
    {"name": "Nationalbunker",    "city": "Switzerland",            "feed": "https://nationalbunker.store/collections/rick-owens-1.atom",     "link": "https://nationalbunker.store/collections/rick-owens-1"},
]

# DRKSHDW is Rick Owens' diffusion line and is often listed without "Rick Owens"
# anywhere, so it counts on its own (title or vendor), as do common misspellings.
DRK = re.compile(r"drk\s*shdw|drk\s*shadow|drksdhw|drkshw|dark\s*shadow", re.I)
LILIES = re.compile(r"\blilies\b", re.I)
RICK = re.compile(r"rick\s*owens|" + DRK.pattern, re.I)


# ---------------------------------------------------------------------------
# Brand. Rick Owens is the default; the sister feeds (Kiko Kostadinov, Helmut
# Lang, ...) live in their own repos and pass --brand brand.json, which can set
# any of these keys plus "shops". See README.
# ---------------------------------------------------------------------------
BRAND = {
    "id": "rick-feed",
    "title": "Rick Feed",
    "url": "https://rick.hengecorp.com",      # where this feed is published (site switcher, refused-lookup fallback)
    "name": "Rick Owens",                     # default line label
    "match": RICK.pattern,                    # what counts as this brand (title or vendor)
    "lines": [["DRKSHDW", DRK.pattern], ["Lilies", LILIES.pattern]],  # first match wins
    "strip": r"(?:rick\s*owens\s*)?(?:(?:drk\s*shdw|drkshdw|lilies)\s*)?",  # repeated prefix dropped from card titles
    "strict": False,                          # True: drop non-matching items from every feed, not just brand_only ones
    "theme": "rick",                          # themes/<theme>.css
    "fonts": "https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600&display=swap",
    "theme_color": ["#E5E5E5", "#000000"],
    "placeholder": "Search: geobasket, bela, 48, leather",
    "labels": {},                             # optional UI wording, e.g. {"Category": "区分 Category"}
}
BRAND_RE = RICK

# The family of feeds, for the site switcher at the top of every page.
SITES = [
    ("rick-feed", "Rick Owens", "https://rick.hengecorp.com"),
    ("kiko-feed", "Kiko Kostadinov", "https://kiko.hengecorp.com"),
    ("lang-feed", "Helmut Lang", "https://lang.hengecorp.com"),
    ("rafcalvin-feed", "205W39NYC", "https://rafcalvin.hengecorp.com"),
    ("soshiotsuki-feed", "Soshiotsuki", "https://soshiotsuki.hengecorp.com"),
]
LINE_RES = [(label, re.compile(pat, re.I)) for label, pat in BRAND["lines"]]


def load_brand(path):
    """Apply a sister feed's brand.json: brand settings plus its own SHOPS."""
    global BRAND_RE, LINE_RES, SHOPS
    cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    SHOPS = cfg.pop("shops", SHOPS)
    BRAND.update(cfg)
    BRAND_RE = re.compile(BRAND["match"], re.I)
    LINE_RES = [(label, re.compile(pat, re.I)) for label, pat in BRAND.get("lines", [])]


def line_of(title, vendor):
    """Which line (e.g. DRKSHDW) a listing belongs to, for the card label and filter."""
    text = f"{title} {vendor}"
    for label, rx in LINE_RES:
        if rx.search(text):
            return label
    return BRAND["name"]
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
OLD_STOCK_DAYS = 3           # first seen but listed longer ago than this: old stock, not NEW
DETAIL_RETRIES = (2, 6, 15)  # seconds to wait before each retry when Shopify refuses products.json
# Shopify rate-limits by IP across all its shops, so once one shop has refused
# after every retry, the rest of the run tries each lookup once and moves on.
SHOPIFY_REFUSING = threading.Event()
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
        if not wanted(shop, title, vendor):
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


def fetch_details(feed_url):
    """The .atom feed lists only a collection's newest 25 pieces and doesn't say
    what's sold, so also read the same collection's products.json (up to
    AVAIL_MAX_PAGES x 250 products). Returns ({product id or handle: {"available",
    "type", "colours"}}, [raw products], error). Items it can't find count as
    for sale and are classified from the feed alone."""
    if not feed_url.endswith(".atom"):
        return {}, [], None
    base = feed_url[:-len(".atom")] + "/products.json?limit=250&page="
    details, everything = {}, []
    for page in range(1, AVAIL_MAX_PAGES + 1):
        products, error = None, None
        for wait in (0,) + (() if SHOPIFY_REFUSING.is_set() else DETAIL_RETRIES):  # Shopify sometimes refuses these from cloud servers
            time.sleep(wait)
            try:
                products = json.loads(fetch_bytes(base + str(page))).get("products") or []
                break
            except urllib.error.HTTPError as e:
                error = f"error {e.code}"
                if e.code not in (403, 429, 430) and e.code < 500:
                    break
            except Exception as e:
                error = str(e)[:80] or e.__class__.__name__
        if products is None:
            if error and error.startswith("error 4"):
                SHOPIFY_REFUSING.set()
            return details, everything, (error if page == 1 else None)
        everything += products
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
        if len(products) < 250:
            break
    return details, everything, None


def wanted(shop, title, vendor):
    """brand_only shops (and strict brands) keep only this brand's pieces."""
    if shop.get("rick_only") or shop.get("brand_only") or BRAND.get("strict"):
        return bool(BRAND_RE.search(title) or BRAND_RE.search(vendor))
    return True


_CURRENCY = {}
def shop_currency(root):
    """A Shopify shop's own currency (products.json prices don't say)."""
    if root not in _CURRENCY:
        try:
            _CURRENCY[root] = json.loads(fetch_bytes(root + "/meta.json")).get("currency") or "USD"
        except Exception:
            _CURRENCY[root] = "USD"
    return _CURRENCY[root]


def items_from_products(shop, feed_url, products, atom_items):
    """Listings for products.json entries the .atom feed didn't include, shaped
    exactly like parse_feed's so the rest of the pipeline treats them the same."""
    root = re.match(r"https?://[^/]+", feed_url).group(0)
    known = {k for it in atom_items for k in product_keys(it)}
    m = atom_items and re.match(r"(.*/products/)\d+\s*$", atom_items[0]["id"])
    id_prefix = m.group(1) if m else root + "/products/"   # same ids as the feed uses, so saved state lines up
    currency = atom_items[0]["currency"] if atom_items else shop_currency(root)
    out = []
    for p in products:
        pid, handle = str(p.get("id", "")), p.get("handle") or ""
        if not pid or pid in known or handle in known:
            continue
        title = html.unescape((p.get("title") or "").strip())
        vendor = (p.get("vendor") or "").strip()
        if not wanted(shop, title, vendor):
            continue
        variants = p.get("variants") or []
        vtitles = [v.get("title") or "" for v in variants]
        prices = []
        for v in variants:
            try:
                prices.append(float(v.get("price")))
            except (TypeError, ValueError):
                pass
        images = p.get("images") or []
        out.append({
            "id": id_prefix + pid,
            "shop": shop["name"],
            "city": shop["city"],
            "title": title,
            "link": f"{root}/products/{handle}",
            "published": p.get("published_at") or p.get("created_at") or "",
            "image": sized_image(images[0].get("src", "")) if images else "",
            "price": min(prices) if prices else None,
            "currency": currency,
            "size": guess_size(title, vtitles),
            "type": (p.get("product_type") or "").strip(),
            "line": line_of(title, vendor),
            "colour_hint": " ".join(" ".join(vt.split(" / ")[:-1]) for vt in vtitles),
            "sold": False,
        })
    return out


def enrich(it, d):
    """Sold flag, category and colours, from products.json details when found."""
    d = d or {}
    it["sold"] = d.get("available") is False
    it["category"] = category_of(d.get("type") or it.get("type"), it["title"])
    it["colours"] = colours_of(d.get("colours"), it.pop("colour_hint", ""), it["title"])


def fetch_shop(shop):
    feeds = shop["feed"] if isinstance(shop["feed"], list) else [shop["feed"]]
    items, errors, seen_ids, lookup_errors = [], [], set(), []
    for url in feeds:
        got, err = fetch_one(shop, url)
        details, products, lookup_err = fetch_details(url)
        if lookup_err:
            lookup_errors.append(lookup_err)
            if err:   # neither source answered for this feed
                errors.append(err)
                continue
        elif products:
            err = None   # the full product list is enough even if the .atom feed failed
            got = got + items_from_products(shop, url, products, got)
        if err:
            errors.append(err)
        for it in got:
            found = [details[k] for k in product_keys(it) if k in details]
            enrich(it, found[0] if found else None)
            it["_lookup_failed"] = bool(lookup_err)
        for it in got:
            if it["id"] not in seen_ids:
                seen_ids.add(it["id"])
                items.append(it)
    error = errors[0] if errors and len(errors) == len(feeds) else None
    shop = dict(shop, lookup_error=lookup_errors[0] if lookup_errors else None)
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


# Rough fallback (units per US dollar) if no exchange-rate service answers and
# no earlier rates were saved. Only used to place foreign prices in the USD filter.
FALLBACK_RATES = {"USD": 1.0, "CAD": 1.38, "EUR": 0.92, "GBP": 0.78, "JPY": 150.0, "AUD": 1.52, "CHF": 0.80}
RATE_SOURCES = [
    "https://api.frankfurter.dev/v1/latest?base=USD",
    "https://api.frankfurter.app/latest?from=USD",
    "https://open.er-api.com/v6/latest/USD",
]


def usd_rates(needed, saved):
    """Units of each currency per US dollar: today's from a free service (ECB
    data), else the last ones saved in state, else the rough fallback."""
    needed = set(needed) - {"USD"}
    if not needed:
        return {"USD": 1.0}, "none needed"
    for url in RATE_SOURCES:
        try:
            rates = json.loads(fetch_bytes(url)).get("rates") or {}
            if needed <= set(rates):
                return dict({c: float(rates[c]) for c in needed}, USD=1.0), url.split("/")[2]
        except Exception:
            continue
    if saved and needed <= set(saved):
        return dict(saved, USD=1.0), "last saved rates"
    return dict(FALLBACK_RATES), "built-in rough rates"


def build_atom(items, generated):
    newest = sorted((i for i in items if not i.get("sold")), key=lambda i: i["first_seen"], reverse=True)[:60]
    esc = lambda s: html.escape(str(s or ""), quote=True)
    parts = ['<?xml version="1.0" encoding="utf-8"?>',
             '<feed xmlns="http://www.w3.org/2005/Atom">',
             f"<title>{esc(BRAND['title'])}</title><id>urn:{esc(BRAND['id'])}</id><updated>{esc(generated)}</updated>"]
    for i in newest:
        cur = i.get("currency") or "USD"
        price = (f"${i['price']:,.0f}" if cur == "USD" else f"{i['price']:,.0f} {cur}") if i.get("price") is not None else ""
        label = " · ".join(x for x in [price, i.get("size"), i["shop"]] if x)
        body = (f'<p><img src="{esc(i["image"])}" width="300"></p>' if i.get("image") else "") + f"<p>{esc(label)}</p>"
        parts.append(f'<entry><id>urn:{esc(BRAND["id"])}:{esc(i["shop"])}:{esc(i["id"])}</id>'
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
    if arg_value("--brand"):
        load_brand(arg_value("--brand"))
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
            if err is None and shop.get("lookup_error"):
                status += f" (sold/colour lookup refused: {shop['lookup_error']}; using last known)"
            print(f"  {shop['name']:<18} {status}")
            results.append((shop, items, err))

    # Shopify sometimes refuses the full product list; rather than shrinking that shop
    # to its newest 25 for this check, reuse its listings from the last published data.json.
    refused = {shop["name"] for shop, items, err in results if shop.get("lookup_error")}
    if refused and site_mode and BRAND.get("url"):
        try:
            prev = json.loads(fetch_bytes(BRAND["url"].rstrip("/") + "/data.json")).get("items", [])
            for shop, items, err in results:
                if shop["name"] in refused:
                    have = {it["id"] for it in items}
                    carried = [dict(it) for it in prev if it.get("shop") == shop["name"] and it.get("id") not in have]
                    for it in carried:
                        it["_lookup_failed"] = True
                    items.extend(carried)
                    if carried:
                        print(f"  {shop['name']}: reused {len(carried)} listings from the last published check")
        except Exception as e:
            print(f"  (couldn't load the last published listings: {str(e)[:80]})")

    all_items, shops_out = [], []
    for shop, items, err in results:
        shops_out.append({"name": shop["name"], "city": shop["city"], "link": shop["link"], "count": len(items), "error": err})
        seeding = shop["name"] not in known_shops   # first time we see this shop
        for it in items:
            key = shop["name"] + "|" + it["id"]
            mem = memory.get(key)
            if mem is None:
                first, old_stock = run_iso, seeding
                pub = parse_time(it["published"])
                # A piece the shop listed days ago is old stock we're only now seeing (a new shop,
                # or a deeper product list), not a new arrival: date it by its listing, no NEW tag.
                if pub and pub < run_at and (seeding or run_at - pub > dt.timedelta(days=OLD_STOCK_DAYS)):
                    first, old_stock = pub.astimezone(dt.timezone.utc).isoformat(timespec="seconds"), True
                mem = {"first_seen": first, "first_run": 0 if old_stock else run_no, "price": it["price"]}
                memory[key] = mem
            else:
                old = mem.get("price")
                if it["price"] is not None and old is not None and it["price"] < old - 0.005:
                    mem["drop_from"] = old
                    mem["drop_at"] = run_iso
                mem["price"] = it["price"]
            mem["last_seen"] = today
            if it.pop("_lookup_failed", False):
                # products.json was refused this run: keep what we knew last time
                # rather than showing everything as unsold and uncoloured.
                for f in ("sold", "category", "colours"):
                    if f in mem:
                        it[f] = mem[f]
            else:
                mem["sold"], mem["category"], mem["colours"] = it["sold"], it["category"], it["colours"]
            it["first_seen"] = mem["first_seen"]
            it["is_new"] = (not first_run) and mem.get("first_run") == run_no
            drop_at = parse_time(mem.get("drop_at"))
            if drop_at and (run_at - drop_at).days < PRICE_DROP_DAYS and mem.get("drop_from"):
                it["drop_from"] = mem["drop_from"]
            all_items.append(it)

    rates, rate_source = usd_rates({i.get("currency") or "USD" for i in all_items}, state.get("rates"))
    for i in all_items:
        r = rates.get(i.get("currency") or "USD") or FALLBACK_RATES.get(i.get("currency"))
        i["price_usd"] = round(i["price"] / r, 2) if i.get("price") is not None and r else None
    if rate_source not in ("none needed", "last saved rates", "built-in rough rates"):
        state["rates"] = {c: v for c, v in rates.items() if c != "USD"}

    cutoff = (run_at - dt.timedelta(days=FORGET_AFTER_DAYS)).date().isoformat()
    memory = {k: v for k, v in memory.items() if str(v.get("last_seen", today))[:10] >= cutoff}
    new_state = {"items": memory} if site_mode else {"last_run": run_iso, "run_no": run_no, "items": memory}
    if state.get("rates"):
        new_state["rates"] = state["rates"]
    text = json.dumps(new_state, indent=1, sort_keys=True)
    old_text = state_file.read_text(encoding="utf-8") if state_file.exists() else ""
    if text != old_text:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(text, encoding="utf-8")

    data = {"mode": "site" if site_mode else "local", "generated": run_iso, "previous": prev_run,
            "first_run": first_run, "shops": shops_out, "items": all_items,
            "categories": ["Outerwear", "Tops", "Bottoms", "Dresses", "Footwear", "Bags & accessories", "Other"], "brand": {"name": BRAND["name"], "strip": BRAND["strip"], "price_style": BRAND.get("price_style", "symbol")}, "colours": [[n, sw] for n, sw, _ in COLOURS]}
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(render_page(payload), encoding="utf-8")
    if site_mode:
        (out_file.parent / "feed.xml").write_text(build_atom(all_items, run_iso), encoding="utf-8")
        (out_file.parent / "data.json").write_text(json.dumps({"generated": run_iso, "items": all_items}, ensure_ascii=False), encoding="utf-8")
        (out_file.parent / ".nojekyll").write_text("", encoding="utf-8")

    new_count = sum(1 for i in all_items if i.get("is_new"))
    failed = [s["name"] for s in shops_out if s["error"]]
    print(f"\n{len(all_items)} {BRAND['name']} listings" + ("" if first_run else f", {new_count} new since last run") + ".")
    cats = {}
    for i in all_items:
        cats[i.get("category", "Other")] = cats.get(i.get("category", "Other"), 0) + 1
    print("By category: " + ", ".join(f"{k} {v}" for k, v in sorted(cats.items(), key=lambda kv: -kv[1]))
          + f". No colour found for {sum(1 for i in all_items if not i.get('colours'))}.")
    foreign = sorted({i["currency"] for i in all_items if i.get("currency") not in (None, "USD")})
    if foreign:
        print("Exchange rates (" + rate_source + "): " + ", ".join(f"1 USD = {rates[c]:g} {c}" for c in foreign if c in rates) + ".")
    if failed:
        print("Couldn't reach: " + ", ".join(failed))
    print(f"Saved {out_file}")
    if open_browser:
        webbrowser.open(out_file.resolve().as_uri())


def render_page(payload):
    esc = lambda x: html.escape(str(x), quote=True)
    labels = BRAND.get("labels") or {}
    lines = BRAND.get("lines") or []
    options = "".join(f'\n      <option value="{esc(l)}">{esc(labels.get(l, l))}</option>' for l in [BRAND["name"]] + [l for l, _ in lines])
    page = PAGE
    for word, text in labels.items():   # optional wording per brand, on marked labels only
        page = page.replace(f">{word}<", f">{text}<")
    css = "\n".join((HERE / "themes" / f"{t}.css").read_text(encoding="utf-8") for t in ("base", BRAND["theme"]))
    if not BRAND.get("fonts"):   # system fonts only: drop the font links
        page = re.sub(r'<link rel="(?:preconnect|stylesheet)" href="(?:https://fonts\.[^"]*|__FONTS__)"[^>]*>\n', "", page)
    return (page.replace("__THEME__", css)
                .replace("__TITLE__", esc(BRAND["title"]))
                .replace("__FONTS__", esc(BRAND["fonts"]))
                .replace("__TC_LIGHT__", esc(BRAND["theme_color"][0])).replace("__TC_DARK__", esc(BRAND["theme_color"][1]))
                .replace("__PLACEHOLDER__", esc(BRAND["placeholder"]))
                .replace("__LINE_HIDDEN__", "" if lines else " hidden")
                .replace("__LINE_OPTIONS__", options)
                .replace("__SITES__", sites_nav())
                .replace("__DATA__", payload))


def sites_nav():
    esc = lambda x: html.escape(str(x), quote=True)
    links = "".join(
        f'<a href="{esc(url)}/"{" aria-current=\"page\"" if sid == BRAND["id"] else ""}>{esc(name)}</a>'
        for sid, name, url in SITES)
    return f'<nav class="sites" aria-label="Designer feeds">{links}</nav>'


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<meta name="theme-color" content="__TC_LIGHT__" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="__TC_DARK__" media="(prefers-color-scheme: dark)">
<title>__TITLE__</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="__FONTS__">
<style>
__THEME__
</style>
</head>
<body>
<div class="wrap">
  __SITES__
  <header>
    <h1 class="mark">__TITLE__</h1>
    <span class="count" id="count"></span>
  </header>
  <div class="crumbs" id="meta"></div>
  <div class="notice" id="notice" hidden></div>
  <div class="bar">
    <input type="search" id="q" autocomplete="off" placeholder="__PLACEHOLDER__" aria-label="Search listings">
    <span class="sel"__LINE_HIDDEN__><select id="line" autocomplete="off" aria-label="Line">
      <option value="">All lines</option>__LINE_OPTIONS__
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
const usd = i => i.price_usd ?? i.price;
const foreign = i => i.currency && i.currency !== "USD";
// Prices show in the shop's own currency; non-USD ones get a currency tag so they stand out.
// (The price filter and sorting use an approximate USD figure behind the scenes.)
const priceHtml = i => DATA.brand.price_style === "code"
  ? (i.price == null ? "" : `${new Intl.NumberFormat("en-US", {maximumFractionDigits: i.price % 1 ? 2 : 0}).format(i.price)} ${esc(i.currency || "USD")}`)
  : money(i.price, i.currency) + (foreign(i) ? `<span class="cur">${esc(i.currency)}</span>` : "");
function ago(iso){
  if (!iso) return "";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 3600) return Math.max(1, Math.round(s / 60)) + " min ago";
  if (s < 86400) return Math.round(s / 3600) + " hr ago";
  const d = Math.round(s / 86400);
  return d < 60 ? d + (d === 1 ? " day ago" : " days ago") : new Date(iso).toLocaleDateString("en-US", {month:"short", day:"numeric", year:"numeric"});
}
// The line label already sits above the title, so drop a repeated "Rick Owens DRKSHDW" prefix.
const PREFIX = new RegExp("^\\s*(?:(?:pre-?owned|new|used)\\s+)?" + DATA.brand.strip + "(?:[-–—:\\/|]\\s*)?", "i");
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
  $("#foot").innerHTML = '<a href="feed.xml">Feed (RSS)</a><span>Prices are in each shop\'s own currency; non-US dollar prices are tagged (CAD, EUR, CHF)</span>';
}
DATA.items.forEach(i => { i.line = i.line || DATA.brand.name; i.display = cleanTitle(i.title); });
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
  const parts = [`${SITE ? "Last check" : "Updated"} <b>${esc(when)}</b>`, `${DATA.items.length} listings`, `${okShops} shops`];
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
    && (pmin == null || (usd(i) != null && usd(i) >= pmin))
    && (pmax == null || (usd(i) != null && usd(i) <= pmax))
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
  if (sort === "low") list.sort((a, b) => (usd(a) ?? 1e12) - (usd(b) ?? 1e12));
  if (sort === "high") list.sort((a, b) => (usd(b) ?? -1) - (usd(a) ?? -1));
  $("#count").textContent = list.length + " shown";
  const pool = DATA.items.filter(i => !off.has(i.shop) && inLine(i));
  $("#newN").textContent = pool.filter(i => i.is_new && forSale(i)).length;
  $("#dropN").textContent = pool.filter(i => i.drop_from && forSale(i)).length;
  $("#soldN").textContent = pool.filter(i => i.sold).length;
  if (!list.length) {
    current = []; shown = 0; sentinel.remove();
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
  current = list; shown = 0;
  $("#grid").innerHTML = "";
  more();
}
// Big feeds have thousands of listings: draw them in batches as the page scrolls.
const BATCH = 96;
let current = [], shown = 0;
const sentinel = document.createElement("div"); sentinel.className = "more"; sentinel.setAttribute("aria-hidden", "true");
function more(){
  if (shown >= current.length) { sentinel.remove(); return; }
  $("#grid").insertAdjacentHTML("beforeend", current.slice(shown, shown + BATCH).map(card).join(""));
  shown += BATCH;
  if (shown < current.length) $("#grid").after(sentinel); else sentinel.remove();
}
if ("IntersectionObserver" in window) new IntersectionObserver(es => { if (es.some(e => e.isIntersecting)) more(); }, {rootMargin: "1200px"}).observe(sentinel);
function card(i){ return `
    <a class="card${i.sold ? " sold" : ""}" href="${esc(i.link)}" target="_blank" rel="noopener">
      <div class="ph${i.image ? "" : " noi"}">
        ${i.image ? `<img src="${esc(i.image)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.parentElement.classList.add('noi');this.remove()">` : ""}
        <span class="noimg">${esc(i.shop)}</span>
        <div class="badges">${i.is_new ? '<span class="b new">New</span>' : ""}${i.drop_from && !i.sold ? '<span class="b drop">Price cut</span>' : ""}${i.sold ? '<span class="b sold">Sold</span>' : ""}</div>
      </div>
      <div class="line">${esc(i.line)}</div>
      <div class="t">${esc(i.display)}</div>
      <div class="price">${priceHtml(i)}${i.drop_from ? `<s>${money(i.drop_from, i.currency)}</s>` : ""}</div>
      <div class="row"><span class="go">${esc(i.shop)} +</span><span class="size">${i.size ? "Size " + esc(i.size) : ""}</span></div>
      <div class="src">${esc(i.city)} / ${ago(i.published)}</div>
    </a>`;
}
render();
// On a phone the switcher scrolls sideways; bring this site's entry into view.
try { const cur = $(".sites [aria-current]"), nav = $(".sites"); if (cur && nav.scrollWidth > nav.clientWidth) nav.scrollLeft = cur.offsetLeft - (nav.clientWidth - cur.offsetWidth) / 2; } catch (e) {}
</script>
</body>
</html>
"""

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
