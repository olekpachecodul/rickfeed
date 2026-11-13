# Rick Feed

The newest secondhand Rick Owens listings from resale shops (mostly US, plus a few in Canada, Europe and Asia), in one page.

**Live at https://rick.hengecorp.com** (feed: https://rick.hengecorp.com/feed.xml)

GitHub checks every shop up to every 15 minutes and republishes the page. GitHub skips some scheduled runs when it's busy, so gaps can be longer; the page shows the time of the last check.

- `rick_feed.py`: checks the shops and builds the page. The shop list is at the top.
- `.github/workflows/rick-feed.yml`: the hourly schedule.
- `data/state.json`: what's already been seen. It's created and updated automatically.

## What counts as Rick Owens

Anything with "Rick Owens" or DRKSHDW in the title or the shop's brand field, including DRKSHDW pieces that never mention Rick Owens.
Each listing is labelled Rick Owens, DRKSHDW or Lilies, and the "All lines" menu filters by line.
Some shops keep DRKSHDW in a separate collection; those shops list two feeds in `SHOPS`. Most shops keep both on one page and need only one.

## Filters

FILTERS opens category, colour and price. Picking several categories or colours shows any of them.
Category and colour are worked out from each shop's product type, its colour option and the title, so the odd piece lands in the wrong place or has no colour.
Rick's colour names are mapped to plain ones (Milk and Pearl are White, Dust is Grey; "Black Milk" counts as both). The word lists are in `CATEGORIES` and `COLOURS` in `rick_feed.py`.

## Adding or removing a shop

Open `rick_feed.py` on GitHub, click the pencil icon, and edit the `SHOPS` list.
For a Shopify shop the feed address is the shop's Rick Owens page address with `.atom` on the end.
Commit the change and the site rebuilds within a minute.

## When a shop refuses the sold/colour lookup

Sold status, colour and category come from each shop's `products.json`, which Shopify occasionally refuses from GitHub's servers.
The check retries a few times, and if it still fails it keeps what it knew from the last good check. The Actions log says "lookup refused" when that happens.

## Prices outside the US

Shops in Canada, Europe and Switzerland price in their own currency, and the page shows that price as-is with a currency tag (CAD, EUR, CHF).
The price filter and sorting use an approximate US dollar figure behind the scenes so those pieces land in the right range; rates come from a free
exchange-rate service each check, with the last good rates saved in `data/state.json`. Shipping and import duties aren't included.

## The web address

`rick.hengecorp.com` is a CNAME to `olekpachecodul.github.io`, set as DNS only (grey cloud) in Cloudflare, where the domain was registered through iCloud.
The custom domain itself is set in Settings → Pages. The bare `hengecorp.com` keeps Cloudflare's landing page and the iCloud Mail records.

## Running it now

Actions tab → Rick Feed → Run workflow.

## On your phone

Open the site and use "Add to Home Screen". NEW tags mean added since you last opened the page on that device.
"Hide sold" (on by default) hides pieces a shop has marked sold out; untick it to see them greyed out. The choice is remembered on each device.
`feed.xml` on the same site (it never includes sold pieces) is a combined feed you can add to a feed reader if you want notifications.
