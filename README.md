# Ballhog

The newest secondhand listings for a run of designers, gathered from resale shops, one page per designer.

**Live at https://ballhog.hengecorp.com**. The home page is a splash (a crayon henge, drawn live, circling slowly; drag it to spin it) over an index of
every designer. It holds still for devices set to reduce motion; its Animate / Pause button overrides that and is remembered. Each designer has a page at `/<slug>/` (slugs in `brands.json`: `rick`, `kiko`, `lang`, `rafcalvin`, `soshiotsuki`,
`cdg`, `margiela`, `undercover`, `gaultier`, `yohji`, `raf`, `issey`, `numbernine`, `ann`, `bbs`, `ccp`, `guidi`, `ralph`, `balenciaga`, `julius`)
and an RSS feed at `/<slug>/feed.xml`.

GitHub checks every shop up to every 15 minutes and republishes the site. GitHub skips some scheduled runs when it's busy,
so gaps can be longer; each page shows the time of the last check.

## How it's put together

- `ballhog.py`: reads every shop once per check, sorts each piece to the designers it belongs to, and builds the site.
- `shops.json`: every shop, once. For each designer (by slug) it lists the shop's collections to read.
  `"filter"` marks collections that mix designers (only pieces named as the designer are kept).
  `"everything"` names a whole-shop collection (usually `all`) that's read once and sorted to every designer.
  Where a shop lists nothing for a designer, its two largest collections named after that designer (e.g. `/collections/helmut-lang`) are found automatically each day,
  and straight away when a designer is added.
- `brands.json`: every designer: `slug` (its page is `/<slug>/`), title, what counts as that designer (`match`, title or vendor),
  `lines` (e.g. DRKSHDW, Junya Watanabe under Comme des Garçons), `exclude` (pieces that belong on another page, e.g. Raf Simons'
  Calvin Klein work), `strict` (filter every shop, used for 205W39NYC), the look and wording.
- `publications.json`: fashion publications whose RSS feeds are read hourly for articles (Google News is searched per designer too). `data/articles.json` → `sources` shows how each answered on the last read.
- Every designer page has a top bar: the henge mark and Ballhog (home) on the left, and a menu of every designer on the right, with a finder.
- `themes/base.css` is the shared layout; `themes/<theme>.css` gives each designer its look.
- `data/state.json`: what's already been seen, per designer (created and updated automatically).
- `data/last_check.json`: the last check's request count, time taken, and any shops that asked us to slow down (Shopify answers 429).

## Adding a shop

Add an entry to `shops.json`:

```json
{"name": "Shop Name", "city": "City", "root": "https://shop.com", "collections": {"rick": ["rick-owens"], "lang": ["helmut-lang"]}}
```

The handle is the last part of the shop's collection address (`https://shop.com/collections/HANDLE`). Only Shopify shops work.
A shop with a designer collection the list doesn't name is still picked up by the daily discovery.

## Adding a designer

Add an entry to `brands.json` (copy an existing one, give it a new `slug`, `name`, `match` and `theme`) and a `themes/<theme>.css`
(an empty file gives the base look). Its page appears at `/<slug>/` on the next check, and in the designers menu and on the home page.
Every shop is searched for it on the next check; add any shop that sells it without a collection named after it to `shops.json`.
Requests to each shop are spaced out (`SHOP_GAP`), so a check takes a little longer as designers are added.

## What counts as Rick Owens

Anything with "Rick Owens" or DRKSHDW in the title or the shop's brand field, including DRKSHDW pieces that never mention Rick Owens.
Listings are labelled Rick Owens, DRKSHDW or Lilies, and the line menu filters by line.

## Articles

Each designer page has an Articles view (`/<slug>/#articles`): news and features about the designer, newest first, each linking to the
original. Once an hour Google News is searched per designer (`news.q` in `brands.json`) and every feed in `publications.json` is read;
a publication's piece is kept for every designer it names. Names that mean other things ("Undercover" police stories, "CCP", Guidi as a
surname) use a stricter headline rule (`news.require`, `news.exclude`). Articles are kept in `data/articles.json`, up to 150 per designer
from the last 400 days (`news.keep_days` changes that: 205W39NYC, a 2017-18 label, keeps ten years). Shop and encyclopedia results (Lyst, Farfetch, Britannica...) and shopping-deal posts ("60% off", Black Friday) are dropped. `data/articles.json` also records how each source answered on the last read.

## Filters

FILTERS opens category, colour and price. Picking several categories or colours shows any of them.
Category and colour are worked out from each shop's product type, its colour option and the title, so the odd piece lands in the wrong place or has no colour.
Rick's colour names are mapped to plain ones (Milk and Pearl are White, Dust is Grey; "Black Milk" counts as both).

## How listings are gathered

Each collection is read two ways: its `.atom` feed (the newest 25 pieces) and its `products.json` (up to 1,000 pieces,
which also gives sold status, type and colour). A piece seen for the first time that the shop listed more than 3 days earlier
is old stock, so it's dated by its listing and doesn't get a NEW tag.
Each page also publishes `data.json`; if Shopify refuses a shop's product list during a check, that shop's listings from the last
published check are reused so the page doesn't shrink. Sold status, category and colour are remembered the same way.

## Prices outside the US

Shops outside the US price in their own currency; the page shows that price as-is with a currency tag (CAD, EUR, CHF, JPY).
The price filter and sorting use an approximate US dollar figure behind the scenes, with rates from a free exchange-rate service each check.
Shipping and import duties aren't included.

## The web address

`ballhog.hengecorp.com` is a CNAME to `olekpachecodul.github.io`, set as DNS only (grey cloud) in Cloudflare, where the domain was
registered through iCloud. The custom domain itself is set in Settings → Pages. The old per-designer addresses
(`rick.`, `kiko.`, `lang.`, `rafcalvin.`, `soshiotsuki.hengecorp.com`) redirect to `ballhog.hengecorp.com/<designer>/` with a Cloudflare redirect rule.

## Running it now

Actions tab → Ballhog → Run workflow. Locally: `python3 ballhog.py` builds `./site` and opens it.
