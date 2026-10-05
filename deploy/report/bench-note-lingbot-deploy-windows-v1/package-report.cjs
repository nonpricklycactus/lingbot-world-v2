'use strict';
// 面板几何 QA + preview.html —— 与已获批的 v5 报告同一套检查，按本期源尺寸调整
const fs = require('fs'), path = require('path'), crypto = require('crypto');
const root = path.resolve(__dirname, '../../..');
const tools = path.join(root, 'tools/benchnote/lib');
const { mdToBlocks } = require(path.join(tools, 'blocks.cjs'));
const { parseFrontMatter, stripFrontMatter, resolveTheme } = require(path.join(tools, 'profile.cjs'));
const { pageHtml } = require(path.join(tools, 'theme.cjs'));
const { resolveBrowser, resolvePlaywright } = require(path.join(tools, 'env.cjs'));
const { chromium } = require(resolvePlaywright());
const source = path.join(__dirname, '../bench-note-lingbot-deploy-windows-v1.zh.md');
const hash = (p) => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
// 本期原图是 1920x1080 的录屏抽帧；越界判据按这个尺寸
const SRC_W = 1920, SRC_H = 1080;

(async () => {
  const md = fs.readFileSync(source, 'utf8');
  const theme = resolveTheme({ frontMatter: parseFrontMatter(md).data });
  const blocks = mdToBlocks(stripFrontMatter(md), root).filter((b) => !b.includes('class="pagemark"'));
  const manifest = JSON.parse(fs.readFileSync(path.join(__dirname, 'manifest.json'), 'utf8'));
  const plan = JSON.parse(fs.readFileSync(path.join(__dirname, 'page-plan.json'), 'utf8'));
  if (blocks.length !== manifest.pages.length || blocks.length !== plan.pages.length) throw new Error('Page count drift');
  const browser = await chromium.launch({ executablePath: resolveBrowser(), headless: true });
  const page = await browser.newPage({ viewport: { width: 1080, height: 1440 } });
  const rows = [], errors = [];
  for (let i = 0; i < blocks.length; i++) {
    await page.setContent(pageHtml({ body: blocks[i], theme }).replace('__PG__', String(i + 1).padStart(2, '0') + ' / ' + String(blocks.length).padStart(2, '0')), { waitUntil: 'load' });
    await page.evaluate(async () => { await document.fonts.ready; await Promise.all([...document.images].map((im) => im.decode())); });
    const geometry = await page.evaluate(() => {
      const main = document.querySelector('main'), outer = main.firstElementChild, panel = outer.querySelector('.report-panel') || outer;
      const r = panel.getBoundingClientRect(), mr = main.getBoundingClientRect(), overflow = [];
      for (const el of panel.querySelectorAll('*')) {
        if (el.tagName === 'STYLE' || getComputedStyle(el).display === 'none') continue;
        const b = el.getBoundingClientRect(); if (!b.width || !b.height) continue;
        if (b.left < r.left - 1 || b.right > r.right + 1 || b.top < r.top - 1 || b.bottom > r.bottom + 1)
          overflow.push({ tag: el.tagName, class: String(el.className).slice(0, 60), text: (el.textContent || '').trim().slice(0, 60), left: Math.round(b.left), right: Math.round(b.right), bottom: Math.round(b.bottom), panel_bottom: Math.round(r.bottom) });
      }
      return {
        width: Math.round(r.width), height: Math.round(r.height), bottom: Math.round(r.bottom), main_bottom: Math.round(mr.bottom),
        scroll_height: panel.scrollHeight, client_height: panel.clientHeight, overflow,
        images: [...document.images].map((im) => ({ loaded: im.complete && im.naturalWidth > 0, w: im.naturalWidth, h: im.naturalHeight, src: im.getAttribute('src') })),
      };
    });
    for (const im of geometry.images) if (!im.loaded) errors.push('page ' + (i + 1) + ' image failed: ' + im.src);
    if (geometry.overflow.length) errors.push('page ' + (i + 1) + ' internal overflow ' + geometry.overflow.length);
    if (geometry.bottom > geometry.main_bottom + 1 || geometry.scroll_height > geometry.client_height + 1) errors.push('page ' + (i + 1) + ' panel overflow');
    rows.push({ page: i + 1, title: plan.pages[i].title, ...geometry });
  }
  await browser.close();
  const qa = {
    schema_version: 1, source_sha256: hash(source), source_content_hash: manifest.source.content_hash, layout_hash: manifest.layout_hash,
    checked_pages: rows.length, source_frame_size: [SRC_W, SRC_H], rows, errors, pass: errors.length === 0,
    scope: 'DOM bounds and image decoding for the 1080x1440 pages. Fact binding and human visual review are separate.',
  };
  fs.mkdirSync(path.join(__dirname, 'qa'), { recursive: true });
  fs.writeFileSync(path.join(__dirname, 'qa/geometry.json'), JSON.stringify(qa, null, 2) + '\n');
  console.log(JSON.stringify({ checked_pages: rows.length, errors, details: rows.filter((r) => r.overflow.length) }));
  if (errors.length) { process.exitCode = 2; return; }
  if (process.argv.includes('--inspect-only')) return;
  const sheet = '*{box-sizing:border-box}body{margin:0;background:#ece7de;color:#2b2b2b;font:16px/1.6 "Microsoft YaHei",sans-serif}.bar{position:sticky;top:0;z-index:10;background:#faf7f0;border-bottom:1px solid #ded7c8;padding:12px 22px;display:flex;flex-wrap:wrap;gap:20px;justify-content:space-between;align-items:center}a{color:#8e3b2f}.pages{max-width:1080px;margin:auto}.pages figure{margin:22px 0;scroll-margin-top:100px}.pages img{width:100%;height:auto;display:block;box-shadow:0 3px 15px #bbb7af}.pages figcaption{padding:10px 16px;background:#faf7f0;color:#665f56}.sources{max-width:1080px;margin:25px auto;padding:24px;background:#faf7f0}@media(max-width:640px){.bar{font-size:13px;gap:8px;padding:10px}.pages figure{margin:12px 0}}';
  const gallery = plan.pages.map((p, i) => '<figure id="page-' + (i + 1) + '"><a href="page-' + String(i + 1).padStart(2, '0') + '.png"><img loading="lazy" src="page-' + String(i + 1).padStart(2, '0') + '.png" alt="' + esc(p.title) + '"></a><figcaption>' + String(i + 1).padStart(2, '0') + ' / ' + plan.pages.length + ' · ' + esc(p.title) + '</figcaption></figure>').join('\n');
  fs.writeFileSync(path.join(__dirname, 'preview.html'),
    '<!doctype html><html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' +
    '<title>LingBot-World 1.3B 部署（候审）</title><style>' + sheet + '</style></head><body><div class="bar">' +
    '<strong>LingBot-World 1.3B · Windows 原生部署 · 候审</strong><span><a href="lingbot-deploy-windows.zh.pdf">PDF</a> · ' +
    '<a href="asset-sources.json">素材出处</a> · <a href="README.md">来源与复现</a></span></div><div class="pages">' + gallery + '</div>' +
    '<div class="sources">本篇 ' + plan.pages.length + ' 页，事实源为本机实测手册、原始录屏与补丁验证记录；模型输出规格与 SHA-256 由本机复核。等待用户审核后才据它写录音稿。</div></body></html>');
})();
