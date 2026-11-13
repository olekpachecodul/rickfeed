# Ballhog

The newest secondhand listings for a handful of designers, gathered from resale shops, one page per designer.

**Live at https://ballhog.hengecorp.com**: [Rick Owens](https://ballhog.hengecorp.com/rick/) ·
[Kiko Kostadinov](https://ballhog.hengecorp.com/kiko/) · [Helmut Lang](https://ballhog.hengecorp.com/lang/) ·
[205W39NYC](https://ballhog.hengecorp.com/rafcalvin/) · [Soshiotsuki](https://ballhog.hengecorp.com/soshiotsuki/).
Each page has an RSS feed at `/<designer>/feed.xml`.

GitHub checks every shop up to every 15 minutes and republishes the site. GitHub skips some scheduled runs when it's busy,
so gaps can be longer; each page shows the time of the last check.

## How it's put together

- `ballhog.py`: reads every shop once per check, sorts each piece to the designers it belongs to, and builds the site.
- `shops.json`: every shop, once. For each designer (by slug) it lists the shop's collections to read.
  `"filter"` marks collections that mix designers (only pieces named as the designer are kept).
  Collections named after a designer (e.g. `/collections/helmut-lang`) are also found automatically each day.
- `brands.json`: every designer: `slug` (its page is `/<slug>/`), title, what counts as that designer (`match`, title or vendor),
  `lines` (e.g. DRKSHDW), `strict` (filter every shop, used for 205W39NYC), the look and wording.
- `themes/base.css` is the shared layout; `themes/<theme>.css` gives each designer its look.
- `data/state.json`: what's already been seen, per designer (created and updated automatically).

## Adding a shop

Add an entry to `shops.json`:

```json
{"name": "Shop Name", "city": "City", "root": "https://shop.com", "collections": {"rick": ["rick-owens"], "lang": ["helmut-lang"]}}
```

The handle is the last part of the shop's collection address (`https://shop.com/collections/HANDLE`). Only Shopify shops work.
A shop with a designer collection the list doesn't name is still picked up by the daily discovery.

## Adding a designer

Add an entry to `brands.json` (copy an existing one, give it a new `slug`, `name`, `match` and `theme`) and a `themes/<theme>.css`
(an empty file gives the base look). Its page appears at `/<slug>/` on the next check and in the switcher on every page.
Shops that already carry it are found by the daily discovery; add the rest to `shops.json`.

## What counts as Rick Owens

Anything with "Rick Owens" or DRKSHDW in the title or the shop's brand field, including DRKSHDW pieces that never mention Rick Owens.
Listings are labelled Rick Owens, DRKSHDW or Lilies, and the line menu filters by line.

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
