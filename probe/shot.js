const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const b = await chromium.launch();
  const report = {};
  for (const [name, opts] of [['desktop', {viewport: {width: 1440, height: 900}, deviceScaleFactor: 1}], ['mobile', {viewport: {width: 390, height: 844}, deviceScaleFactor: 2, isMobile: true}]]) {
    const ctx = await b.newContext({...opts, userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36', locale: 'en-US'});
    const p = await ctx.newPage();
    for (const url of ['https://www.rickowens.eu/en/US', 'https://www.rickowens.eu/en/US/men/section/drkshdw']) {
      const tag = name + (url.includes('drkshdw') ? '-drkshdw' : '-home');
      try {
        await p.goto(url, {waitUntil: 'networkidle', timeout: 60000});
      } catch (e) { report[tag + '-err'] = String(e).slice(0, 200); }
      await p.waitForTimeout(3000);
      report[tag + '-url'] = p.url();
      await p.screenshot({path: `probe/${tag}.png`});
      await p.screenshot({path: `probe/${tag}-full.png`, fullPage: true}).catch(() => {});
      if (name === 'desktop') {
        report[tag + '-styles'] = await p.evaluate(() => {
          const pick = el => { if (!el) return null; const s = getComputedStyle(el); return {tag: el.tagName, cls: el.className && String(el.className).slice(0,80), text: (el.innerText||'').slice(0,60), font: s.fontFamily, size: s.fontSize, weight: s.fontWeight, ls: s.letterSpacing, tt: s.textTransform, color: s.color, bg: s.backgroundColor}; };
          const els = [...document.querySelectorAll('body, header, nav, nav a, h1, h2, h3, a, button, p, span, [class*=price], [class*=product] , [class*=title]')].slice(0, 400);
          const seen = new Set(), styles = [];
          for (const el of els) { const s = pick(el); const k = [s.font, s.size, s.weight, s.ls, s.tt, s.color, s.bg].join('|'); if (!seen.has(k)) { seen.add(k); styles.push(s); } }
          const fonts = [...document.fonts].map(f => f.family + ' ' + f.weight + ' ' + f.status);
          const sheets = []; for (const ss of document.styleSheets) { try { for (const r of ss.cssRules) if (r.cssText.startsWith('@font-face')) sheets.push(r.cssText.slice(0, 300)); } catch (e) { sheets.push('xorigin ' + ss.href); } }
          return {title: document.title, fonts: [...new Set(fonts)], fontFaces: sheets.slice(0, 20), styles: styles.slice(0, 60)};
        });
        fs.writeFileSync(`probe/${tag}.html`, (await p.content()).slice(0, 400000));
      }
    }
    await ctx.close();
  }
  fs.writeFileSync('probe/site.json', JSON.stringify(report, null, 1));
  await b.close();
})();
