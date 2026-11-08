const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const b = await chromium.launch(); const report = {};
  for (const [name, opts] of [['desktop', {viewport: {width: 1440, height: 900}, deviceScaleFactor: 1}], ['mobile', {viewport: {width: 390, height: 844}, deviceScaleFactor: 2, isMobile: true}]]) {
    const ctx = await b.newContext({...opts, userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36', locale: 'en-US'});
    const p = await ctx.newPage();
    try { await p.goto('https://www.rickowens.eu/en-us/collections/men-drkshdw', {waitUntil: 'networkidle', timeout: 60000}); } catch (e) { report[name + '-err'] = String(e).slice(0, 200); }
    await p.waitForTimeout(2500);
    for (const sel of ['.iubenda-cs-reject-btn', 'button:has-text("Reject all")', '.ro-country-selector__close-button']) { try { await p.click(sel, {timeout: 2000}); } catch (e) {} }
    await p.evaluate(() => document.querySelectorAll('#iubenda-cs-banner, [id*=iubenda], #acsb, .acsb-trigger').forEach(e => e.remove()));
    await p.waitForTimeout(1000);
    await p.screenshot({path: `probe/grid-${name}.png`});
    await p.mouse.wheel(0, 900); await p.waitForTimeout(1500);
    await p.screenshot({path: `probe/grid-${name}-2.png`});
    if (name === 'desktop') {
      report.cards = await p.evaluate(() => {
        const pick = el => { if (!el) return null; const s = getComputedStyle(el); const r = el.getBoundingClientRect(); return {tag: el.tagName, cls: String(el.className).slice(0,100), text: (el.innerText||'').slice(0,80), font: s.fontFamily, size: s.fontSize, ls: s.letterSpacing, tt: s.textTransform, color: s.color, bg: s.backgroundColor, lh: s.lineHeight, ta: s.textAlign, w: Math.round(r.width), h: Math.round(r.height), x: Math.round(r.x)}; };
        const link = document.querySelector('a[href*="/products/"]');
        let card = link; for (let i = 0; i < 4 && card && card.parentElement; i++) card = card.parentElement;
        const grid = card && card.parentElement;
        const gs = grid ? getComputedStyle(grid) : {};
        return {grid: grid && {cls: String(grid.className).slice(0,150), display: gs.display, cols: gs.gridTemplateColumns, gap: gs.gap, pad: gs.padding},
                card: card && [...card.querySelectorAll('*')].slice(0, 40).map(pick).filter(x => x.text || x.tag === 'IMG'),
                img: (() => { const i = document.querySelector('a[href*="/products/"] img'); return i && {w: i.getBoundingClientRect().width, h: i.getBoundingClientRect().height, fit: getComputedStyle(i).objectFit, bg: getComputedStyle(i.parentElement).backgroundColor}; })(),
                h1: pick(document.querySelector('h1')), filters: [...document.querySelectorAll('button, select, label')].slice(0, 30).map(pick).filter(x => x.text).slice(0, 12)};
      });
    }
    await ctx.close();
  }
  fs.writeFileSync('probe/grid.json', JSON.stringify(report, null, 1)); await b.close();
})();
