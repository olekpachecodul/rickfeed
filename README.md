# Rick Feed

The newest secondhand Rick Owens listings from US resale shops, in one page.
GitHub checks every shop once an hour and republishes the page.

- `rick_feed.py`: checks the shops and builds the page. The shop list is at the top.
- `.github/workflows/rick-feed.yml`: the hourly schedule.
- `data/state.json`: what's already been seen. It's created and updated automatically.

## What counts as Rick Owens

Anything with "Rick Owens" or DRKSHDW in the title or the shop's brand field, including DRKSHDW pieces that never mention Rick Owens.
Each listing is labelled Rick Owens, DRKSHDW or Lilies, and the "All lines" menu filters by line.
Some shops keep DRKSHDW in a separate collection; those shops list two feeds in `SHOPS` (Luke's-style shops with one combined page need only one).

## Adding or removing a shop

Open `rick_feed.py` on GitHub, click the pencil icon, and edit the `SHOPS` list.
For a Shopify shop the feed address is the shop's Rick Owens page address with `.atom` on the end.
Commit the change and the site rebuilds within a minute.

## Running it now

Actions tab → Rick Feed → Run workflow.

## On your phone

Open the site and use "Add to Home Screen". NEW tags mean added since you last opened the page on that device.
"Hide sold" (on by default) hides pieces a shop has marked sold out; untick it to see them greyed out. The choice is remembered on each device.
`feed.xml` on the same site (it never includes sold pieces) is a combined feed you can add to a feed reader if you want notifications.
