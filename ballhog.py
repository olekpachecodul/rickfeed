#!/usr/bin/env python3
"""
Ballhog: the newest secondhand listings for a handful of designers (Rick Owens,
Kiko Kostadinov, Helmut Lang, 205W39NYC, Soshiotsuki), gathered from resale shops.

Every shop in shops.json is read once per check; each piece is sorted to the
designers in brands.json it belongs to, and each designer gets a page at
/<slug>/ plus a home page listing them all. Run it again later and anything that
showed up in between is marked NEW; price cuts are marked too.

Needs Python 3.8+ and nothing else.
  python3 ballhog.py                      build ./site and open it in your browser
  python3 ballhog.py --site DIR --state F (what the GitHub workflow runs)
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
import urllib.parse
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
from pathlib import Path

# ---------------------------------------------------------------------------
# Shops and designers live in two files next to this one:
#   shops.json  - every shop once: name, city, Shopify root address, and per designer
#                 slug the collections to read. "filter" lists collections that mix
#                 designers (only pieces named as the designer are kept). Collections
#                 named after a designer are also found automatically each day.
#   brands.json - every designer: slug (its page is /<slug>/), title, what counts as
#                 it ("match", title or vendor), lines, look (themes/<theme>.css), etc.
# ---------------------------------------------------------------------------
SITE_URL = "https://ballhog.hengecorp.com"
HERE = Path(__file__).resolve().parent
SHOPS = json.loads((HERE / "shops.json").read_text(encoding="utf-8"))
BRANDS = json.loads((HERE / "brands.json").read_text(encoding="utf-8"))
for _b in BRANDS:
    _b["re"] = re.compile(_b["match"], re.I)
    _b["line_res"] = [(label, re.compile(pat, re.I)) for label, pat in _b.get("lines", [])]
    _b["exclude_re"] = re.compile(_b["exclude"], re.I) if _b.get("exclude") else None
SLUGS = {b["slug"] for b in BRANDS}
PUBLICATIONS = json.loads((HERE / "publications.json").read_text(encoding="utf-8"))
for _b in BRANDS:
    _n = _b.get("news") or {}
    _b["news_q"] = _n.get("q") or f'"{_b["name"]}"'
    _b["news_re"] = re.compile(_n["require"], re.I) if _n.get("require") else _b["re"]
    _b["news_ex"] = re.compile(_n["exclude"], re.I) if _n.get("exclude") else None
DISCOVER_EVERY_DAYS = 1
MAX_DISCOVERED = 5        # extra collections found per designer per shop, at most
SHOP_GAP = 0.4            # seconds between requests to the same shop, to stay under Shopify's limits


def is_brand(brand, title, vendor):
    return bool(brand["re"].search(title or "") or brand["re"].search(vendor or "")) and not excluded(brand, title, vendor)


def excluded(brand, title, vendor):
    """Pieces that name the designer but belong on another page (e.g. Raf Simons' Calvin Klein)."""
    rx = brand.get("exclude_re")
    return bool(rx and (rx.search(title or "") or rx.search(vendor or "")))


def line_of(brand, title, vendor):
    """Which line (e.g. DRKSHDW) a listing belongs to, for the card label and filter."""
    text = f"{title} {vendor}"
    for label, rx in brand["line_res"]:
        if rx.search(text):
            return label
    return brand["name"]


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
USER_AGENT = "Mozilla/5.0 (compatible; Ballhog/1.0; personal feed reader)"

STATE_FILE = HERE / "ballhog_state.json"

NS = {"a": "http://www.w3.org/2005/Atom", "s": "http://jadedpixel.com/-/spec/shopify"}
IMG_RE = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.I)
SIZE_PATTERNS = [
    re.compile(r"\((?:size\s*)?([0-9]{1,2}(?:\.5)?|XXS|XS|S|M|L|XL|XXL|OS|O/S|One Size)\)\s*$", re.I),
    re.compile(r"\b(?:size|sz)\.?\s*([0-9]{1,2}(?:\.5)?|XXS|XS|S|M|L|XL|XXL|small|medium|large|x-?large|OS)\b", re.I),
]


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


_HOST_LOCKS, _HOST_LAST = {}, {}
_HOSTS_LOCK = threading.Lock()


def fetch_bytes(url):
    # One request at a time per shop, a short gap apart: many designers now share each shop.
    host = urllib.parse.urlsplit(url).netloc
    with _HOSTS_LOCK:
        lock = _HOST_LOCKS.setdefault(host, threading.Lock())
    with lock:
        wait = _HOST_LAST.get(host, 0) + SHOP_GAP - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        try:
            return _fetch(url)
        finally:
            _HOST_LAST[host] = time.monotonic()


def _fetch(url):
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
            "vendor": vendor,
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


_META = {}
def shop_meta(root):
    """A Shopify shop's own details (currency, city, country), read once per check."""
    if root not in _META:
        try:
            _META[root] = json.loads(fetch_bytes(root + "/meta.json"))
        except Exception:
            _META[root] = {}
    return _META[root]


def shop_currency(root):
    """A Shopify shop's own currency (products.json prices don't say)."""
    return shop_meta(root).get("currency") or "USD"


def shop_place(root):
    """Where a shop is, from its own Shopify details, for shops.json entries that leave "city" empty."""
    m = shop_meta(root)
    return ", ".join(x for x in (m.get("city"), m.get("country")) if x) or "Online"


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
            "vendor": vendor,
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


def discover(shop):
    """Collections whose handle or title names a designer, e.g. /collections/helmut-lang."""
    found, cols = {}, []
    for page in (1, 2, 3):
        try:
            got = json.loads(fetch_bytes(f"{shop['root']}/collections.json?limit=250&page={page}")).get("collections") or []
        except Exception:
            return None
        cols += got
        if len(got) < 250:
            break
    for c in cols:
        text = c.get("handle", "").replace("-", " ").replace("_", " ") + " " + (c.get("title") or "")
        for b in BRANDS:
            if b["re"].search(text):
                found.setdefault(b["slug"], []).append(c["handle"])
    return found


def crawl_shop(job):
    """Read every collection this shop has for any designer, once. Returns the
    listings per collection (not yet sorted to designers) and any problems."""
    shop, handles = job
    if not shop.get("city"):
        shop["city"] = shop_place(shop["root"])
    by_handle, errors, lookup_errors = {}, {}, {}
    for h in handles:
        url = f"{shop['root']}/collections/{h}.atom"
        got, err = fetch_one(shop, url)
        details, products, lookup_err = fetch_details(url)
        if lookup_err:
            lookup_errors[h] = lookup_err
            if err:   # neither source answered for this collection
                errors[h] = err
                continue
        elif products:
            err = None   # the full product list is enough even if the .atom feed failed
            got = got + items_from_products(shop, url, products, got)
        if err:
            errors[h] = err
        for it in got:
            found = [details[k] for k in product_keys(it) if k in details]
            enrich(it, found[0] if found else None)
            it["_lookup_failed"] = bool(lookup_err)
        by_handle[h] = got
    return shop, by_handle, errors, lookup_errors


def brand_listings(brand, shop, plan, crawled):
    """This designer's listings at one shop, from the collections planned for it."""
    by_handle, errors, lookup_errors = crawled
    handles, filtered = plan
    items, seen = [], set()
    for h in handles:
        for it in by_handle.get(h, []):
            if it["id"] in seen:
                continue
            if (h in filtered or brand.get("strict")) and not is_brand(brand, it["title"], it.get("vendor")):
                continue
            if excluded(brand, it["title"], it.get("vendor")):
                continue
            seen.add(it["id"])
            x = dict(it)
            x["line"] = line_of(brand, x["title"], x.get("vendor", ""))
            items.append(x)
    failed = [errors[h] for h in handles if h in errors]
    error = failed[0] if failed and len(failed) == len(handles) else None
    refused = next((lookup_errors[h] for h in handles if h in lookup_errors), None)
    return items, error, refused


# ---------------------------------------------------------------------------
# Articles: Google News searched per designer, plus fashion publications' RSS
# feeds kept only where a piece names the designer. Read hourly; kept in
# data/articles.json so a missed hour loses nothing.
# ---------------------------------------------------------------------------
ARTICLES_EVERY_MINUTES = 55
ARTICLES_KEEP_DAYS = 400
ARTICLES_MAX = 150           # per designer
ARTICLES_RULES = 4           # bump when the matching rules change, to re-read straight away
TAG_RE = re.compile(r"<[^>]+>")
# Results that are shops or reference pages, not articles.
NOT_ARTICLES = re.compile(r"\b(?:lyst|ebay|farfetch|vestiaire|the\s*realreal|mercari|poshmark|depop|stockx|goat|"
                          r"mytheresa|net-a-porter|mr\s*porter|matches(?:fashion)?|nordstrom|saks|neiman|end\.?\s*clothing|amazon|etsy|"
                          r"britannica|wikipedia|fandom|pinterest|instagram|tiktok|youtube|facebook|reddit)\b", re.I)
# Shopping-deal posts ("up to 60% off at Macy's") aren't articles either.
DEALS = re.compile(r"\d+\s*%\s*off\b|\bcoupons?\b|promo\s*codes?|\bon\s+sale\b|\bsale\s+(?:on|at)\b|black\s*friday|cyber\s*monday|"
                   r"prime\s*day|\b(?:best|top|early)\s+(?:\w+\s+){0,2}deals\b|\bdeals?\s+(?:on|at)\b", re.I)


def lenient_xml(raw):
    """Some feeds arrive with a byte-order mark, leading blank lines, bare ampersands
    or control characters; tidy those so the feed still parses."""
    text = raw.decode("utf-8", "replace").lstrip("\ufeff \r\n\t")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = re.sub(r"&(?!(?:[a-zA-Z][a-zA-Z0-9]*|#[0-9]+|#x[0-9a-fA-F]+);)", "&amp;", text)
    # HTML-only entities (&nbsp;, &rsquo; ...) aren't XML: turn them into numeric references
    from html.entities import name2codepoint
    text = re.sub(r"&([a-zA-Z][a-zA-Z0-9]*);", lambda m: m.group(0) if m.group(1) in ("amp", "lt", "gt", "quot", "apos")
                  else (f"&#{name2codepoint[m.group(1)]};" if m.group(1) in name2codepoint else f"&amp;{m.group(1)};"), text)
    return ET.fromstring(text.encode("utf-8"))


def feed_entries(raw):
    """(title, link, published ISO, summary text, source name) from RSS 2.0 or Atom."""
    import email.utils
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        root = lenient_xml(raw)
    out = []
    for it in root.iter():
        tag = it.tag.rsplit("}", 1)[-1]
        if tag not in ("item", "entry"):
            continue
        get = lambda name: next((c for c in it if c.tag.rsplit("}", 1)[-1] == name), None)
        title = html.unescape(TAG_RE.sub("", (get("title").text or "") if get("title") is not None else "")).strip()
        link_el = get("link")
        link = ((link_el.get("href") or link_el.text or "") if link_el is not None else "").strip()
        when = None
        for name in ("pubDate", "published", "updated", "date"):
            el = get(name)
            if el is not None and (el.text or "").strip():
                try:
                    when = email.utils.parsedate_to_datetime(el.text.strip())
                except Exception:
                    when = parse_time(el.text.strip())
                if when:
                    break
        summ = get("description") if get("description") is not None else get("summary")
        text = html.unescape(TAG_RE.sub(" ", (summ.text or "") if summ is not None else ""))
        src = get("source")
        source = (src.text or "").strip() if src is not None else ""
        if title and link.startswith("http"):
            if when and when.tzinfo is None:
                when = when.replace(tzinfo=dt.timezone.utc)
            out.append((title, link, when.astimezone(dt.timezone.utc).isoformat(timespec="seconds") if when else "", text, source))
    return out


def article_key(title):
    return re.sub(r"[^a-z0-9]+", "", title.lower())[:80]


def about(brand, text):
    return (bool(brand["news_re"].search(text)) and not (brand["news_ex"] and brand["news_ex"].search(text))
            and not DEALS.search(text))


def gather_articles(saved, run_at, run_iso):
    """Add any new articles to saved ({slug: {key: article}}); returns a log line per source."""
    jobs = [("news", b) for b in BRANDS] + [("pub", p) for p in PUBLICATIONS]

    def read(job):
        kind, x = job
        url = (f"https://news.google.com/rss/search?q={urllib.parse.quote(x['news_q'])}&hl=en-US&gl=US&ceid=US:en"
               if kind == "news" else x["feed"])
        try:
            return job, feed_entries(fetch_bytes(url)), None
        except Exception as e:
            return job, [], (f"error {e.code}" if isinstance(e, urllib.error.HTTPError) else (str(e)[:60] or e.__class__.__name__))

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(read, jobs))
    oldest_for = {b["slug"]: (run_at - dt.timedelta(days=b.get("news", {}).get("keep_days", ARTICLES_KEEP_DAYS))).isoformat() for b in BRANDS}
    oldest = min(oldest_for.values())
    log, added, status = [], 0, {}
    for (kind, x), entries, err in results:
        found = 0
        for title, link, published, text, source in entries:
            if published and published < oldest:
                continue
            if kind == "news":
                # Google News titles end in " - Source"
                if source and title.endswith(" - " + source):
                    title = title[: -len(source) - 3].strip()
                targets = [x] if about(x, title) and not NOT_ARTICLES.search(source + " " + link) else []
            else:
                source = x["name"]
                targets = [b for b in BRANDS if about(b, title) or about(b, text[:600])]
            if DEALS.search(title):
                targets = []
            for b in targets:
                if published and published < oldest_for[b["slug"]]:
                    continue
                bucket = saved.setdefault(b["slug"], {})
                k = article_key(title)
                have = bucket.get(k)
                if have is None:
                    bucket[k] = {"title": title, "url": link, "source": source or "News",
                                 "published": published or run_iso, "first_seen": run_iso}
                    found += 1
                elif kind == "pub" and "news.google." in have["url"]:
                    have["url"] = link          # prefer the publication's own link
        added += found
        status[x["name"] if kind == "pub" else "News: " + x["name"]] = err or f"{len(entries)} read, {found} new"
        if err or kind == "pub":
            log.append(f"  {(x['name'] if kind == 'pub' else 'News: ' + x['name']):<28} {err or f'{len(entries)} read, {found} new'}")
    for slug, bucket in saved.items():
        keep = sorted(bucket.items(), key=lambda kv: kv[1]["published"], reverse=True)
        ex = next((b["news_ex"] for b in BRANDS if b["slug"] == slug), None)
        saved[slug] = dict([kv for kv in keep if kv[1]["published"] >= oldest_for.get(slug, oldest)
                            and not NOT_ARTICLES.search(kv[1]["source"] + " " + kv[1]["url"])
                            and not DEALS.search(kv[1]["title"]) and not (ex and ex.search(kv[1]["title"]))][:ARTICLES_MAX])
    return added, log, status


def load_state(path):
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        state = {"items": {}}
    if state.get("version") != 2:
        # Before Ballhog each designer had its own state ("shop|id" keys); the Rick one is
        # this file, the others were copied to data/legacy/<slug>.json. Merge them once.
        items = {}
        for k, v in state.get("items", {}).items():
            items[k if k.split("|", 1)[0] in SLUGS else "rick|" + k] = v
        for f in sorted((path.parent / "legacy").glob("*.json")):
            try:
                for k, v in json.loads(f.read_text(encoding="utf-8")).get("items", {}).items():
                    items.setdefault(f.stem + "|" + k, v)
                print(f"Merged earlier history for {f.stem}")
            except Exception as e:
                print(f"Couldn't merge {f.name}: {e}")
        state = {**state, "items": items, "version": 2}
    return state


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


def build_atom(brand, items, generated):
    newest = sorted((i for i in items if not i.get("sold")), key=lambda i: i["first_seen"], reverse=True)[:60]
    esc = lambda s: html.escape(str(s or ""), quote=True)
    fid = f"{brand['slug']}-feed"
    parts = ['<?xml version="1.0" encoding="utf-8"?>',
             '<feed xmlns="http://www.w3.org/2005/Atom">',
             f"<title>{esc(brand['title'])} · Ballhog</title><id>urn:{fid}</id><updated>{esc(generated)}</updated>"]
    for i in newest:
        cur = i.get("currency") or "USD"
        price = (f"${i['price']:,.0f}" if cur == "USD" else f"{i['price']:,.0f} {cur}") if i.get("price") is not None else ""
        label = " · ".join(x for x in [price, i.get("size"), i["shop"]] if x)
        body = (f'<p><img src="{esc(i["image"])}" width="300"></p>' if i.get("image") else "") + f"<p>{esc(label)}</p>"
        parts.append(f'<entry><id>urn:{fid}:{esc(i["shop"])}:{esc(i["id"])}</id>'
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
    site_mode = arg_value("--site") is not None
    site_dir = Path(arg_value("--site") or (HERE / "site"))
    state_file = Path(arg_value("--state") or STATE_FILE)
    open_browser = not site_mode and "--no-open" not in sys.argv

    run_at = now_utc()
    run_iso = run_at.isoformat(timespec="seconds")
    today = run_at.date().isoformat()
    state = load_state(state_file)
    memory = state.get("items", {})
    known = {tuple(k.split("|", 2)[:2]) for k in memory}   # (designer, shop) pairs seen before
    prev_run = state.get("last_run")
    first_run = prev_run is None
    run_no = int(state.get("run_no", 0)) + 1

    # 1. Which collections to read at each shop: the listed ones plus any named after a
    #    designer (re-discovered once a day; a failed discovery keeps the last result).
    discovered = state.setdefault("discovered", {})
    # Look again once a day, or straight away when a designer has been added since the last look.
    stale = [shop for shop in SHOPS
             if discovered.get(shop["name"], {}).get("date", "") < (run_at - dt.timedelta(days=DISCOVER_EVERY_DAYS)).date().isoformat()
             or set(discovered.get(shop["name"], {}).get("slugs", [])) != SLUGS]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for shop, found in zip(stale, pool.map(discover, stale)):
            if found is not None:
                discovered[shop["name"]] = {"date": today, "found": found, "slugs": sorted(SLUGS)}
    discovered = {k: v for k, v in discovered.items() if k in {s["name"] for s in SHOPS}}
    plans, jobs = {}, []
    for shop in SHOPS:
        found = discovered.get(shop["name"], {}).get("found", {})
        plans[shop["name"]] = {}
        handles = []
        everything = shop.get("everything", [])   # e.g. "all": the whole shop, read for every designer
        for b in BRANDS:
            listed = shop.get("collections", {}).get(b["slug"], [])
            listed = listed + [h for h in everything if h not in listed]
            extra = [h for h in found.get(b["slug"], []) if h not in listed][:MAX_DISCOVERED]
            if listed or extra:
                plans[shop["name"]][b["slug"]] = (listed + extra, set(shop.get("filter", [])) | set(extra) | set(everything))
                handles += [h for h in listed + extra if h not in handles]
        jobs.append((shop, handles))

    # 2. Read every shop once.
    print(f"Checking {len(SHOPS)} shops…")
    crawled = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for shop, by_handle, errors, lookup_errors in pool.map(crawl_shop, jobs):
            crawled[shop["name"]] = (by_handle, errors, lookup_errors)
            n = len({it["id"] for its in by_handle.values() for it in its})
            status = f"{n} pieces from {len(by_handle)} collections" if by_handle else f"skipped: {next(iter(errors.values()), 'nothing to read')}"
            if lookup_errors:
                status += f" (product list refused: {next(iter(lookup_errors.values()))}; using last known)"
            print(f"  {shop['name']:<22} {status}")

    # Articles, at most hourly.
    articles_file = state_file.parent / "articles.json"
    try:
        articles = json.loads(articles_file.read_text(encoding="utf-8"))
    except Exception:
        articles = {"checked": "", "by_designer": {}}
    if (articles.get("checked", "") < (run_at - dt.timedelta(minutes=ARTICLES_EVERY_MINUTES)).isoformat()
            or set(articles.get("slugs", [])) != SLUGS or articles.get("rules") != ARTICLES_RULES):
        # hourly, or straight away for a new designer or new matching rules
        added, art_log, articles["sources"] = gather_articles(articles.setdefault("by_designer", {}), run_at, run_iso)
        articles["checked"], articles["slugs"], articles["rules"] = run_iso, sorted(SLUGS), ARTICLES_RULES
        print(f"\nArticles: {added} new." + ("\n" + "\n".join(art_log) if art_log else ""))
        text = json.dumps(articles, indent=1, sort_keys=True, ensure_ascii=False)
        articles_file.parent.mkdir(parents=True, exist_ok=True)
        articles_file.write_text(text, encoding="utf-8")

    # 3. Each designer: sort the pieces, update its history, build its page.
    all_currencies, built = set(), []
    pages = []
    for brand in BRANDS:
        slug = brand["slug"]
        results = []
        for shop in SHOPS:
            plan = plans[shop["name"]].get(slug)
            if plan:
                items, error, refused = brand_listings(brand, shop, plan, crawled[shop["name"]])
                results.append((shop, plan, items, error, refused))
        # Shopify sometimes refuses a full product list; rather than shrinking that shop to
        # its newest 25 for this check, reuse its listings from the last published data.json.
        if site_mode and any(r[4] for r in results):
            try:
                prev = json.loads(fetch_bytes(f"{SITE_URL}/{slug}/data.json")).get("items", [])
                for shop, plan, items, error, refused in results:
                    if refused:
                        have = {it["id"] for it in items}
                        carried = [dict(it, _lookup_failed=True) for it in prev if it.get("shop") == shop["name"] and it.get("id") not in have]
                        items.extend(carried)
                        if carried:
                            print(f"  {brand['name']} / {shop['name']}: reused {len(carried)} listings from the last published check")
            except Exception as e:
                print(f"  ({brand['name']}: couldn't load the last published listings: {str(e)[:80]})")
        all_items, shops_out = [], []
        for shop, plan, items, error, refused in results:
            handles, filtered = plan
            link = (f"{shop['root']}/search?type=product&q={urllib.parse.quote_plus(brand['name'])}" if handles[0] in filtered
                    else f"{shop['root']}/collections/{handles[0]}")
            shops_out.append({"name": shop["name"], "city": shop["city"], "link": shop.get("link", {}).get(slug, link) if isinstance(shop.get("link"), dict) else link,
                              "count": len(items), "error": error})
            seeding = (slug, shop["name"]) not in known   # first time this designer is read at this shop
            for it in items:
                key = f"{slug}|{shop['name']}|{it['id']}"
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
                it.pop("vendor", None)
                it["first_seen"] = mem["first_seen"]
                it["is_new"] = (not first_run) and mem.get("first_run") == run_no
                drop_at = parse_time(mem.get("drop_at"))
                if drop_at and (run_at - drop_at).days < PRICE_DROP_DAYS and mem.get("drop_from"):
                    it["drop_from"] = mem["drop_from"]
                all_items.append(it)
        all_currencies |= {i.get("currency") or "USD" for i in all_items}
        pages.append((brand, all_items, shops_out))

    rates, rate_source = usd_rates(all_currencies, state.get("rates"))
    if rate_source not in ("none needed", "last saved rates", "built-in rough rates"):
        state["rates"] = {c: v for c, v in rates.items() if c != "USD"}

    for brand, all_items, shops_out in pages:
        slug = brand["slug"]
        for i in all_items:
            r = rates.get(i.get("currency") or "USD") or FALLBACK_RATES.get(i.get("currency"))
            i["price_usd"] = round(i["price"] / r, 2) if i.get("price") is not None and r else None
        data = {"mode": "site" if site_mode else "local", "generated": run_iso, "previous": prev_run,
                "first_run": first_run, "shops": shops_out, "items": all_items,
                "categories": ["Outerwear", "Tops", "Bottoms", "Dresses", "Footwear", "Bags & accessories", "Other"],
                "brand": {"slug": slug, "name": brand["name"], "strip": brand["strip"], "price_style": brand.get("price_style", "symbol")},
                "articles": sorted(articles.get("by_designer", {}).get(slug, {}).values(), key=lambda a: a["published"], reverse=True),
                "colours": [[n, sw] for n, sw, _ in COLOURS]}
        payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
        out = site_dir / slug
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(render_page(brand, payload), encoding="utf-8")
        (out / "feed.xml").write_text(build_atom(brand, all_items, run_iso), encoding="utf-8")
        (out / "data.json").write_text(json.dumps({"generated": run_iso, "items": all_items}, ensure_ascii=False), encoding="utf-8")
        for_sale = sum(1 for i in all_items if not i.get("sold"))
        new_count = sum(1 for i in all_items if i.get("is_new"))
        failed = [s["name"] for s in shops_out if s["error"]]
        built.append({"slug": slug, "name": brand["name"], "title": brand["title"], "listings": len(all_items),
                      "for_sale": for_sale, "shops": sum(1 for s in shops_out if not s["error"])})
        cats = {}
        for i in all_items:
            cats[i.get("category", "Other")] = cats.get(i.get("category", "Other"), 0) + 1
        print(f"\n{brand['name']}: {len(all_items)} listings ({for_sale} for sale) from {len(shops_out)} shops"
              + ("" if first_run else f", {new_count} new since last run") + ". By category: "
              + ", ".join(f"{k} {v}" for k, v in sorted(cats.items(), key=lambda kv: -kv[1]))
              + f". No colour found for {sum(1 for i in all_items if not i.get('colours'))}."
              + (f" Couldn't reach: {', '.join(failed)}." if failed else ""))
    (site_dir / "index.html").write_text(render_home(built, run_iso), encoding="utf-8")
    (site_dir / ".nojekyll").write_text("", encoding="utf-8")
    foreign = sorted(c for c in all_currencies if c != "USD")
    if foreign:
        print("\nExchange rates (" + rate_source + "): " + ", ".join(f"1 USD = {rates[c]:g} {c}" for c in foreign if c in rates) + ".")

    cutoff = (run_at - dt.timedelta(days=FORGET_AFTER_DAYS)).date().isoformat()
    memory = {k: v for k, v in memory.items() if str(v.get("last_seen", today))[:10] >= cutoff}
    new_state = {"version": 2, "items": memory, "discovered": discovered}
    if not site_mode:
        new_state.update(last_run=run_iso, run_no=run_no)
    if state.get("rates"):
        new_state["rates"] = state["rates"]
    text = json.dumps(new_state, indent=1, sort_keys=True, ensure_ascii=False)
    old_text = state_file.read_text(encoding="utf-8") if state_file.exists() else ""
    if text != old_text:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(text, encoding="utf-8")
    print(f"Saved {site_dir}")
    if open_browser:
        webbrowser.open((site_dir / "index.html").resolve().as_uri())


def render_page(brand, payload):
    esc = lambda x: html.escape(str(x), quote=True)
    labels = brand.get("labels") or {}
    lines = brand.get("lines") or []
    options = "".join(f'\n      <option value="{esc(l)}">{esc(labels.get(l, l))}</option>' for l in [brand["name"]] + [l for l, _ in lines])
    page = PAGE
    for word, text in labels.items():   # optional wording per designer, on marked labels only
        page = page.replace(f">{word}<", f">{text}<")
    css = "\n".join((HERE / "themes" / f"{t}.css").read_text(encoding="utf-8") for t in ("base", brand["theme"]))
    if not brand.get("fonts"):   # system fonts only: drop the font links
        page = re.sub(r'<link rel="(?:preconnect|stylesheet)" href="(?:https://fonts\.[^"]*|__FONTS__)"[^>]*>\n', "", page)
    return (page.replace("__THEME__", css)
                .replace("__DOCTITLE__", esc(f"{brand['title']} · Ballhog"))
                .replace("__TITLE__", esc(brand["title"]))
                .replace("__FONTS__", esc(brand.get("fonts", "")))
                .replace("__TC_LIGHT__", esc(brand["theme_color"][0])).replace("__TC_DARK__", esc(brand["theme_color"][1]))
                .replace("__PLACEHOLDER__", esc(brand["placeholder"]))
                .replace("__LINE_HIDDEN__", "" if lines else " hidden")
                .replace("__LINE_OPTIONS__", options)
                .replace("__SITES__", sites_nav(brand["slug"]))
                .replace("__DATA__", payload))


def sites_nav(current):
    """Links to every designer page (relative, so it works on any domain)."""
    esc = lambda x: html.escape(str(x), quote=True)
    links = '<a href="../" class="home">Ballhog</a>' + "".join(
        f'<a href="../{esc(b["slug"])}/"{' aria-current="page"' if b["slug"] == current else ""}>{esc(b.get("short", b["name"]))}</a>'
        for b in BRANDS)
    return f'<nav class="sites" aria-label="Designers">{links}</nav>'


def render_home(built, run_iso):
    esc = lambda x: html.escape(str(x), quote=True)
    rows = "".join(
        f'<li style="--i:{n}"><a href="{esc(b["slug"])}/"><span class="n">{esc(b["name"])}</span>'
        f'<span class="c"><b>{b["for_sale"]:,}</b> / {b["shops"]}</span></a></li>' for n, b in enumerate(built))
    total = sum(b["for_sale"] for b in built)
    return (HOME.replace("__ROWS__", rows).replace("__WHEN__", esc(run_iso))
                .replace("__TOTAL__", f"{total:,}").replace("__SHOPS__", str(len(SHOPS))))


HOME = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex">
<meta name="theme-color" content="#F2F1EC" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0B0B0B" media="(prefers-color-scheme: dark)">
<title>Ballhog</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;800&family=JetBrains+Mono:wght@400&display=swap">
<style>
:root{--bg:#F2F1EC;--ink:#0E0E0E;--muted:#6B6A66;--rule:rgba(14,14,14,.16);--f:"Inter Tight","Helvetica Neue",Arial,sans-serif;--m:"JetBrains Mono",Menlo,monospace}
@media (prefers-color-scheme: dark){:root{--bg:#0B0B0B;--ink:#ECEAE4;--muted:#8E8C86;--rule:rgba(236,234,228,.16);color-scheme:dark}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:400 14px/1.4 var(--f);-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}
#henge{position:fixed;inset:0;width:100%;height:100%;display:block;z-index:-1}
.pad{padding-left:max(20px,env(safe-area-inset-left),3vw);padding-right:max(20px,env(safe-area-inset-right),3vw)}
/* the splash: wordmark, one line, the drawing behind */
.splash{position:relative;min-height:100svh;display:grid;grid-template-rows:auto 1fr auto;padding-top:max(18px,env(safe-area-inset-top),2.4vw);padding-bottom:28px;pointer-events:none}
.top{display:flex;justify-content:space-between;gap:16px;font:400 11px/1.4 var(--m);letter-spacing:.04em;text-transform:uppercase}
.top a{pointer-events:auto}
h1{margin:0;align-self:start;font-weight:800;font-size:clamp(64px,19.5vw,330px);line-height:.8;letter-spacing:-.065em;margin-left:-.04em;padding-top:.06em;mix-blend-mode:difference;color:#fff;
  animation:rise 1.1s cubic-bezier(.2,.7,.1,1) both}
.foot{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;mix-blend-mode:difference;color:#fff}
.foot p{margin:0;max-width:34ch;font-size:clamp(15px,1.5vw,20px);line-height:1.25;letter-spacing:-.01em}
.cue{font:400 11px/1.4 var(--m);text-transform:uppercase;letter-spacing:.04em;pointer-events:auto;display:flex;align-items:center;gap:10px;white-space:nowrap}
.cue::after{content:"";width:1px;height:28px;background:currentColor;animation:drip 2.2s ease-in-out infinite}
/* the index */
.index{position:relative;padding-bottom:max(48px,env(safe-area-inset-bottom))}
.index header{display:flex;justify-content:space-between;gap:16px;padding:18px 0 12px;font:400 11px/1.4 var(--m);text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid var(--ink)}
ol{list-style:none;margin:0 -16px;padding:0;counter-reset:d}
li{counter-increment:d;animation:rise .9s cubic-bezier(.2,.7,.1,1) both;animation-delay:calc(var(--i) * 40ms + .2s)}
li a{position:relative;display:grid;grid-template-columns:3.2em 1fr auto;align-items:baseline;gap:12px;padding:14px 16px 12px;border-bottom:1px solid var(--rule);
  backdrop-filter:blur(10px) saturate(.6);-webkit-backdrop-filter:blur(10px) saturate(.6);background:color-mix(in srgb,var(--bg) 55%,transparent);transition:color .25s}
li a::before{content:counter(d,decimal-leading-zero);font:400 11px/1 var(--m);color:var(--muted)}
li a::after{content:"";position:absolute;inset:0;background:var(--ink);transform:scaleY(0);transform-origin:bottom;transition:transform .35s cubic-bezier(.2,.7,.1,1);z-index:-1}
li a:hover,li a:focus-visible{color:var(--bg);outline:0}
li a:hover::after,li a:focus-visible::after{transform:scaleY(1)}
li a:hover::before,li a:focus-visible::before{color:var(--bg)}
.n{font-weight:500;font-size:clamp(26px,4.6vw,64px);line-height:1;letter-spacing:-.045em}
.c{font:400 11px/1.4 var(--m);text-transform:uppercase;letter-spacing:.04em;text-align:right;white-space:nowrap}
.c b{font-weight:400;font-size:clamp(13px,1.4vw,17px)}
.index footer{display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px 20px;padding-top:16px;font:400 11px/1.4 var(--m);text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
@keyframes rise{from{opacity:0;transform:translateY(24px)}to{opacity:1;transform:none}}
@keyframes drip{0%,100%{transform:scaleY(.25);transform-origin:top}50%{transform:scaleY(1);transform-origin:top}}
@media (prefers-reduced-motion:reduce){h1,li,.cue::after{animation:none}li a::after{transition:none}}
@media (max-width:640px){
  li a{grid-template-columns:2.4em 1fr;row-gap:4px}
  .c{grid-column:2;text-align:left}
  .top span:last-child{display:none}
}
</style>
</head>
<body>
<canvas id="henge" aria-hidden="true"></canvas>
<section class="splash pad">
  <div class="top"><span>Ballhog / secondhand designer, live</span><span>__SHOPS__ shops &middot; checked every 15 min</span></div>
  <h1>Ballhog</h1>
  <div class="foot">
    <p>Every new secondhand piece from the resale shops worth checking, gathered by designer.</p>
    <a class="cue" href="#index">__TOTAL__ for sale</a>
  </div>
</section>
<section class="index pad" id="index">
  <header><span>Designers</span><span>For sale / shops</span></header>
  <ol>__ROWS__</ol>
  <footer><span>Last check <time datetime="__WHEN__" id="when">__WHEN__</time></span><span>hengecorp</span></footer>
</section>
<script>
try{const t=document.getElementById("when");t.textContent=new Date(t.dateTime).toLocaleString("en-US",{weekday:"short",month:"short",day:"numeric",hour:"numeric",minute:"2-digit"});}catch(e){}
/* A henge drawn in crayon: a ring of trilithons in 3D, outlined with grainy
   jittered strokes that are redrawn a dozen times a second (line boil) while
   the camera circles. Still for anyone who prefers reduced motion. */
(function(){
  const cv = document.getElementById("henge"), ctx = cv.getContext && cv.getContext("2d");
  if (!ctx) return;
  const still = matchMedia("(prefers-reduced-motion: reduce)");
  const darkQ = matchMedia("(prefers-color-scheme: dark)");
  let W = 0, H = 0, D = 1, grain = null, ink = "", paper = "";
  let seed = 1;
  const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  // --- the stones: boxes [cx, cy, cz, width, height, depth, yaw], chunky, in a ring
  const boxes = [];
  const R = 9, layout = "TSTFTsTS";
  (function build(){
    let s = 11; const r = () => (s = (s * 16807) % 2147483647) / 2147483647;
    for (let i = 0; i < layout.length; i++){
      const a = i / layout.length * Math.PI * 2 + .2, k = layout[i];
      const x = Math.cos(a) * R, z = Math.sin(a) * R, yaw = -a + Math.PI / 2 + (r() - .5) * .16;
      const tx = -Math.sin(a), tz = Math.cos(a);
      if (k === "T"){
        const h = 3.4 + r() * .6, gap = .35, w = 1.9 + r() * .3, d = 1.6;
        for (const side of [-1, 1]) boxes.push([x + tx * side * (w + gap) / 2, h / 2, z + tz * side * (w + gap) / 2, w, h, d, yaw + (r() - .5) * .1]);
        boxes.push([x, h + .55, z, 2 * w + gap + .3, 1.1, d + .1, yaw + (r() - .5) * .08]);
      } else if (k === "S" || k === "s"){
        const h = k === "S" ? 3.2 + r() * .6 : 1.7 + r() * .4;
        boxes.push([x, h / 2, z, 1.9, h, 1.5, yaw + (r() - .5) * .25]);
      } else if (k === "F"){   // a fallen lintel
        boxes.push([x * .9, .55, z * .9, 4.2, 1.1, 1.6, yaw + .45]);
      }
    }
  })();
  function corners(b){
    const [cx, cy, cz, w, h, d, yaw] = b, c = Math.cos(yaw), s = Math.sin(yaw), out = [];
    for (const [ux, uy, uz] of [[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],[-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]]){
      const lx = ux * w / 2, lz = uz * d / 2;
      out.push([cx + lx * c - lz * s, cy + uy * h / 2, cz + lx * s + lz * c]);
    }
    return out;
  }
  const FACES = [[0,1,2,3],[4,5,6,7],[0,3,7,4],[1,2,6,5],[3,2,6,7],[0,1,5,4]];
  const TOP = 4;
  const boxCorners = boxes.map(corners);
  function setup(){
    D = Math.min(2, window.devicePixelRatio || 1);
    W = cv.clientWidth; H = cv.clientHeight;
    cv.width = Math.round(W * D); cv.height = Math.round(H * D);
    const cs = getComputedStyle(document.documentElement);
    ink = cs.getPropertyValue("--ink").trim() || "#0E0E0E"; paper = cs.getPropertyValue("--bg").trim() || "#F2F1EC";
    // crayon grain: ink with random gaps, used as the stroke pattern
    const g = document.createElement("canvas"); g.width = g.height = 128;
    const gx = g.getContext("2d"), img = gx.createImageData(128, 128);
    const hex = ink.replace("#", ""), rr = parseInt(hex.slice(0,2),16), gg = parseInt(hex.slice(2,4),16), bb = parseInt(hex.slice(4,6),16);
    for (let i = 0; i < img.data.length; i += 4){
      const v = Math.random();
      img.data[i] = rr; img.data[i+1] = gg; img.data[i+2] = bb; img.data[i+3] = v < .1 ? 0 : v < .2 ? 120 : 235 + v * 20;
    }
    gx.putImageData(img, 0, 0);
    grain = ctx.createPattern(g, "repeat");
  }
  let mx = 0, my = 0, tmx = 0, tmy = 0;
  addEventListener("pointermove", e => { tmx = e.clientX / W - .5; tmy = e.clientY / H - .5; }, {passive: true});
  function draw(t){
    seed = 1 + Math.floor(t / 83) % 997;   // a new hand every ~83 ms
    mx += (tmx - mx) * .08; my += (tmy - my) * .08;
    const narrow = W < 700;
    const phi = t / 1000 * 0.03 + mx * .45 + 1.9;            // slow orbit, nudged by the pointer
    const dist = 29, camY = 13 - my * 5;
    const cam = [Math.cos(phi) * dist, camY, Math.sin(phi) * dist], tgt = [0, 1.2, 0];
    let fx = tgt[0] - cam[0], fy = tgt[1] - cam[1], fz = tgt[2] - cam[2]; const fl = Math.hypot(fx, fy, fz); fx /= fl; fy /= fl; fz /= fl;
    let rx = -fz, rz = fx; const rl = Math.hypot(rx, rz); rx /= rl; rz /= rl;
    const ux = -(rz * fy), uy = rz * fx - rx * fz, uz = rx * fy;
    const focal = narrow ? W * 1.3 : Math.min(W * .95, H * 1.75);
    const ox = narrow ? W * .5 : W * .6, oy = narrow ? H * .56 : H * .57;
    const proj = p => { const dx = p[0]-cam[0], dy = p[1]-cam[1], dz = p[2]-cam[2];
      const z = dx*fx + dy*fy + dz*fz; return [ox + (dx*rx + dz*rz) / z * focal, oy - (dx*ux + dy*uy + dz*uz) / z * focal]; };
    ctx.setTransform(D, 0, 0, D, 0, 0);
    ctx.fillStyle = paper; ctx.fillRect(0, 0, W, H);
    ctx.lineJoin = ctx.lineCap = "round";
    const lw = Math.max(3.2, Math.min(8, Math.min(W, H * 1.4) * .0055));
    const order = boxes.map((b, i) => [i, Math.hypot(b[0]-cam[0], b[1]-cam[1], b[2]-cam[2])]).sort((a, b) => b[1] - a[1]);
    for (const [i] of order){
      const C = boxCorners[i], b = boxes[i], faces = [];
      for (let f = 0; f < 6; f++){
        const F = FACES[f].map(k => C[k]);
        const fc = [0,1,2].map(k => (F[0][k] + F[1][k] + F[2][k] + F[3][k]) / 4);
        const n = [fc[0]-b[0], fc[1]-b[1], fc[2]-b[2]];   // outward, since the face sits off the box's centre
        if (n[0]*(cam[0]-fc[0]) + n[1]*(cam[1]-fc[1]) + n[2]*(cam[2]-fc[2]) > 0) faces.push([f, F.map(proj)]);
      }
      // paper first, so nearer stones hide the ones behind
      ctx.fillStyle = paper; ctx.beginPath();
      for (const [, q] of faces){ const r = soft(q, 0); ctx.moveTo(r[0][0], r[0][1]); for (const p of r) ctx.lineTo(p[0], p[1]); ctx.closePath(); }
      ctx.fill();
      for (const [f, q] of faces){
        rough(q, lw * (f === TOP ? 1.25 : 1));
        if (f === TOP) scribble(q, lw);
      }
    }
  }
  // round a quad's corners (Chaikin), the way worn stone and a blunt crayon both do
  function soft(q, jit){
    let pts = [];
    for (let e = 0; e < 4; e++){
      const a = q[e], b = q[(e + 1) % 4], n = Math.max(3, Math.round(Math.hypot(b[0]-a[0], b[1]-a[1]) / 9));
      for (let s = 0; s < n; s++){ const t = s / n; pts.push([a[0] + (b[0]-a[0]) * t + (rnd()-.5) * jit, a[1] + (b[1]-a[1]) * t + (rnd()-.5) * jit]); }
    }
    for (let it = 0; it < 2; it++){
      const out = [];
      for (let k = 0; k < pts.length; k++){ const p = pts[k], n = pts[(k + 1) % pts.length];
        out.push([p[0]*.75 + n[0]*.25, p[1]*.75 + n[1]*.25], [p[0]*.25 + n[0]*.75, p[1]*.25 + n[1]*.75]); }
      pts = out;
    }
    return pts;
  }
  function rough(q, lw){
    ctx.strokeStyle = grain;
    for (let pass = 0; pass < 3; pass++){
      const pts = soft(q, lw * .55), o = [(rnd()-.5) * lw * .5, (rnd()-.5) * lw * .5];
      ctx.lineWidth = lw * (pass ? .6 : 1) * (.85 + rnd() * .3);
      ctx.beginPath();
      // start somewhere along the outline and run a little past the start, like a hand that doesn't lift
      const st = Math.floor(rnd() * pts.length), extra = Math.floor(pts.length * (.04 + rnd() * .06));
      for (let k = 0; k <= pts.length + extra; k++){
        const p = pts[(st + k) % pts.length];
        k ? ctx.lineTo(p[0] + o[0], p[1] + o[1]) : ctx.moveTo(p[0] + o[0], p[1] + o[1]);
      }
      ctx.stroke();
    }
  }
  function scribble(q, lw){   // loose crayon hatching on the tops of the stones
    ctx.strokeStyle = grain; ctx.lineWidth = lw * .6; ctx.globalAlpha = .9;
    ctx.beginPath();
    const n = 4 + Math.floor(rnd() * 5);
    for (let k = 0; k < n; k++){
      const t1 = .1 + rnd() * .8, t2 = .1 + rnd() * .8;
      const a = [q[0][0] + (q[1][0]-q[0][0]) * t1, q[0][1] + (q[1][1]-q[0][1]) * t1];
      const b = [q[3][0] + (q[2][0]-q[3][0]) * t2, q[3][1] + (q[2][1]-q[3][1]) * t2];
      ctx.moveTo(a[0] + (rnd()-.5)*4, a[1] + (rnd()-.5)*4); ctx.lineTo(b[0] + (rnd()-.5)*4, b[1] + (rnd()-.5)*4);
    }
    ctx.stroke(); ctx.globalAlpha = 1;
  }
  let last = -1e9, raf = 0;
  function loop(t){
    raf = requestAnimationFrame(loop);
    if (t - last < 83) return;   // ~12 frames a second: a hand-drawn cadence
    last = t; draw(t);
  }
  function start(){
    cancelAnimationFrame(raf); setup();
    if (still.matches) draw(0); else raf = requestAnimationFrame(loop);
  }
  addEventListener("resize", () => { setup(); if (still.matches) draw(0); });
  (darkQ.addEventListener ? darkQ.addEventListener("change", start) : darkQ.addListener(start));
  (still.addEventListener ? still.addEventListener("change", start) : still.addListener(start));
  start();
})();
</script>
</body>
</html>
"""


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<meta name="theme-color" content="__TC_LIGHT__" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="__TC_DARK__" media="(prefers-color-scheme: dark)">
<title>__DOCTITLE__</title>
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
  <nav class="views" aria-label="View"><a href="./" id="vPieces" aria-current="page">Pieces</a><a href="#articles" id="vArticles">Articles<span class="tn" id="artN"></span></a></nav>
  <div id="pieces">
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
  </div>
  <section class="articles" id="articles" hidden aria-label="Articles"></section>
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
  // Every designer shares one web address now, so "last visit" is kept per designer.
  const K = ":" + DATA.brand.slug;
  try { sess = sessionStorage.getItem("rf-baseline" + K); last = localStorage.getItem("rf-last-visit" + K)
        || (DATA.brand.slug === "rick" ? localStorage.getItem("rf-last-visit") : null); } catch (e) {}
  baseline = sess || last || new Date(Date.now() - 2 * 86400000).toISOString();
  try { sessionStorage.setItem("rf-baseline" + K, baseline); localStorage.setItem("rf-last-visit" + K, new Date().toISOString()); } catch (e) {}
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
  try { sessionStorage.setItem("rf-baseline:" + DATA.brand.slug, baseline); localStorage.setItem("rf-last-visit:" + DATA.brand.slug, baseline); } catch (e) {}
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
// Articles: a second view of the same page, at #articles.
const ARTS = DATA.articles || [];
$("#artN").textContent = ARTS.length || "";
function renderArticles(){
  const isNew = a => baseline && new Date(a.first_seen) > new Date(baseline) && new Date(a.published) > new Date(baseline) - 7 * 86400000;
  $("#articles").innerHTML = ARTS.length
    ? `<ol class="arts">${ARTS.map(a => `<li><a href="${esc(a.url)}" target="_blank" rel="noopener">`
        + `<span class="am"><span class="src">${esc(a.source)}</span><time datetime="${esc(a.published)}">${esc(ago(a.published))}</time>${isNew(a) ? '<span class="b new">New</span>' : ""}</span>`
        + `<span class="at">${esc(a.title)}</span></a></li>`).join("")}</ol>`
      + `<p class="artnote">From Google News and fashion publications' feeds, checked hourly. Each link opens the original article.</p>`
    : `<p class="empty">No articles yet. They're gathered hourly from Google News and fashion publications.</p>`;
}
function showView(){
  const arts = location.hash === "#articles";
  $("#pieces").hidden = arts; $("#articles").hidden = !arts;
  $("#count").hidden = arts;
  if (arts) { $("#vArticles").setAttribute("aria-current", "page"); $("#vPieces").removeAttribute("aria-current"); if (!$("#articles").firstChild) renderArticles(); }
  else { $("#vPieces").setAttribute("aria-current", "page"); $("#vArticles").removeAttribute("aria-current"); }
}
$("#vPieces").addEventListener("click", e => { e.preventDefault(); if (location.hash) { history.pushState(null, "", location.pathname + location.search); showView(); } });
addEventListener("hashchange", showView);
addEventListener("popstate", showView);
showView();
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
