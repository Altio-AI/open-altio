/* Home: the greeting, finding a drug (each found one with its pin), the pinned products or else those
   opened lately, and the release in a line. */

import { rolesWords } from './filters.js';
import { framed, repaintSide } from './frame.js';
import { picked } from './host.js';
import { icon } from './icons.js';
import { pinButton } from './products.js';
import { addressParts, drawn, go, productPath } from './router.js';
import { rulesNotice } from './rules/page.js';
import { api } from './server.js';
import { S, drugWords, keepProducts, learnTitles, listLength, onPins, pinned, productLabel, releaseEndYear, releaseSince } from './state.js';
import { day, esc, num, skeletonRows, tip } from './util.js';

// what a drug's count on Home covers: the roles a page opens with
const asRoles = () => `as ${rolesWords(drugWords().default_roles)}`;
const casesWords = (n) => `${num(n)} ${n === 1 ? 'case' : 'cases'} ${asRoles()}`;

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
}

function marked(text, q) {
  if (!q) return esc(text);
  const i = text.toLowerCase().indexOf(q.toLowerCase());
  if (i < 0) return esc(text);
  return `${esc(text.slice(0, i))}<mark class="search-mark">${esc(text.slice(i, i + q.length))}</mark>${esc(text.slice(i + q.length))}`;
}

function productRow(d, q = '') {
  const label = productLabel(d.name);
  // a spelling it is reported under that matched goes first, so ABILIFY finds aripiprazole plainly
  const names = [...d.reported].sort((a, b) => (q && b.toLowerCase().includes(q.toLowerCase())) - (q && a.toLowerCase().includes(q.toLowerCase())));
  return `<li class="result-row oa-result"><a class="result-open" href="${productPath(d.name)}">
    <span class="result-icon">${icon('folder')}</span>
    <span class="result-text">
      <span class="result-title">${marked(label, q)}${label !== d.title ? ` <span class="oa-faint">${marked(d.title, q)}</span>` : ''}</span>
      <span class="result-passage">${names.length ? `Reported as ${names.slice(0, listLength('names_on_page')).map((n) => marked(n, q)).join(', ')} · ` : ''}${casesWords(d.cases)}</span>
    </span></a>${pinButton(d.name)}</li>`;
}

// FDA's spelling with no ingredient: its own page
function spellingRow([name, n], q) {
  return `<li class="result-row oa-result"><a class="result-open" href="${productPath(name)}">
    <span class="result-icon">${icon('folder')}</span>
    <span class="result-text">
      <span class="result-title">${marked(name, q)}</span>
      <span class="result-passage">FDA's spelling with no ingredient · ${casesWords(n)}</span>
    </span></a>${pinButton(name)}</li>`;
}

// the products this person opened most lately, as many as Home has tiles
const everOpened = () => S.products.filter((p) => p.opened);
const lately = () => everOpened().sort((a, b) => b.opened - a.opened).slice(0, listLength('home_tiles'));
// Home's products: once anything is pinned, the pinned ones in the side panel's order; else those
// opened lately; else, for someone new, the most reported
const homeProducts = () => (pinned().length ? pinned() : lately());

function productsSection() {
  const kept = homeProducts();
  const head = pinned().length ? 'Pinned' : kept.length ? 'Opened lately' : `Most reported ${asRoles()}`;
  return `<h2 class="section-head">${head}</h2>
      <div class="oa-tiles" id="oa-home-list">${Array.from({ length: kept.length || listLength('home_tiles') }, () => `<div class="oa-tile panel">${skeletonRows(2)}</div>`).join('')}</div>
      ${!pinned().length && everOpened().length > kept.length ? `<p class="oa-note">The last ${kept.length} you opened; find any other above.</p>` : ''}`;
}

// a pin pressed or a pinned product moved: Home's products drawn again, the search left as it is
onPins(() => {
  const box = document.getElementById('oa-home-products');
  if (!box) return;
  box.innerHTML = productsSection();
  fillHome();
});

function homePage() {
  const r = S.release;
  return framed(`<main class="home oa-home">
    <h1 class="greeting">${greeting()}${S.me?.first_name ? `, ${esc(S.me.first_name)}` : ''}.</h1>
    <div class="oa-find">
      <div class="search-bar">
        <span class="search-icon">${icon('search')}</span>
        <input class="search-input" id="oa-find" type="search" autocomplete="off" spellcheck="false" placeholder="Find a drug by its ingredient or a name it is reported under" aria-label="Find a drug">
      </div>
      <ul class="result-list panel oa-find-results" id="oa-find-results" hidden></ul>
    </div>
    <section class="oa-home-section" id="oa-home-products">${productsSection()}</section>
    <section class="oa-home-section">
      <h2 class="section-head">This release</h2>
      <div class="panel oa-release-card">
        <p><strong>${num(r?.cases)} cases</strong> from ${r ? releaseSince() : ''}, ${num(r?.set_aside)} probable duplicates left out.${rulesNotice()}</p>
        <p class="oa-faint oa-release-kind">Mostly postmarketing, from FDA's FAERS and the older AERS${r?.built_at ? `<span class="oa-dot">·</span>Updated ${esc(day(r.built_at))}` : ''}</p>
        ${r?.meddra_older ? `<p class="oa-note oa-meddra-older">${esc(r.meddra_older)}</p>` : ''}
        <p class="oa-links"><a href="/all/overview">Look at all cases</a><a href="/release" data-tables-link ${S.showTables ? '' : 'hidden'}>Its tables, SQL and downloads</a></p>
      </div>
    </section>
  </main>`, 'home');
}

// a product's tile: its name, the names it is reported under, its cases and serious cases,
// its cases by year, and when it was opened; fixed in size, so filling it in moves nothing. Its pin
// sits beside the link, top right, shown on hover, on a touch screen and once pinned.
function ago(ms) {
  if (!ms) return '';
  const min = Math.round((Date.now() - ms) / 60000);
  if (min < 1) return 'Opened just now';
  if (min < 60) return `Opened ${min} minute${min === 1 ? '' : 's'} ago`;
  const h = Math.round(min / 60);
  if (h < 24) return `Opened ${h} hour${h === 1 ? '' : 's'} ago`;
  const d = Math.round(h / 24);
  return d === 1 ? 'Opened yesterday' : `Opened ${d} days ago`;
}

function spark(years) {
  const list = (years || []).filter((y) => y[0] != null);
  if (!list.length) return '<span class="oa-spark"></span>';
  const first = list[0][0], by = Object.fromEntries(list), max = Math.max(...list.map((y) => y[1]));
  const bars = [];
  const last = releaseEndYear();
  for (let y = first; y <= last; y++) bars.push(`<i style="--h:${((by[y] || 0) / max).toFixed(3)}"></i>`);
  return `<span class="oa-spark" role="img" aria-label="Cases by year received, ${first} to ${last}" ${tip(`Cases by the year FDA first received them, ${first} to ${last}`)}>${bars.join('')}</span>`;
}

function productTile(d, opened) {
  const label = productLabel(d.name);
  return `<div class="oa-tile-slot"><a class="oa-tile panel" href="${productPath(d.name)}" data-tile="${esc(d.name)}">
    <span class="oa-tile-name">${esc(label)}</span>
    <span class="oa-tile-names">${label !== d.title ? `${esc(d.title)}${d.reported.length ? ' · ' : ''}` : ''}${d.reported.length ? `Reported as ${esc(d.reported.slice(0, listLength('names_on_page')).join(', '))}` : esc(d.about || '')}</span>
    <span class="oa-tile-stats" data-tile-stats><strong>${num(d.cases)}</strong> ${d.cases === 1 ? 'case' : 'cases'} ${asRoles()}</span>
    <span class="oa-tile-foot"><span data-tile-spark><span class="oa-spark"></span></span><span class="oa-faint">${esc(ago(opened))}</span></span>
  </a>${pinButton(d.name)}</div>`;
}

// a kept product under an older name (FDA's active ingredient) is kept under its drug's name from now on
function keepUnder(kept, d) {
  if (!kept || (kept.name === d.name && kept.title === d.title)) return;
  const other = kept.name !== d.name && S.products.find((p) => p.name === d.name);
  if (other) { other.pinned ||= kept.pinned; S.products = S.products.filter((p) => p !== kept); } else Object.assign(kept, { name: d.name, title: d.title });
  keepProducts();
  repaintSide();
}

async function fillHome() {
  const list = document.getElementById('oa-home-list');
  if (!list) return;
  const opened = homeProducts();
  const rows = opened.length
    ? (await Promise.all(opened.map((p) => api(`/api/product?product=${encodeURIComponent(p.name)}`).catch(() => null))))
    : (await api('/api/products')).drugs.slice(0, listLength('home_tiles'));
  if (document.getElementById('oa-home-list') !== list) return;
  const shown = rows.map((d, i) => [d, opened[i]]).filter(([d]) => d);
  learnTitles(shown.map(([d]) => d));
  shown.forEach(([d, kept]) => keepUnder(kept, d));
  list.innerHTML = shown.map(([d, kept]) => productTile(d, kept?.opened)).join('');
  // the same question the product page asks first, so opening a tile finds it ready
  for (const [d] of shown) {
    api(`/api/summary?product=${encodeURIComponent(d.name)}`).then((sum) => {
      const tile = list.querySelector(`[data-tile="${CSS.escape(d.name)}"]`);
      if (!tile) return;
      tile.querySelector('[data-tile-stats]').innerHTML = `<strong>${num(sum.cases)}</strong> cases <span class="oa-dot">·</span> ${num(sum.serious)} serious`;
      tile.querySelector('[data-tile-spark]').innerHTML = spark(sum.years);
    }).catch(() => {});
  }
}

let findTimer = 0;
function wireFind() {
  const input = document.getElementById('oa-find');
  const out = document.getElementById('oa-find-results');
  if (!input) return;
  input.addEventListener('input', () => {
    clearTimeout(findTimer);
    findTimer = setTimeout(async () => {
      const q = input.value.trim();
      if (!q) { out.hidden = true; return; }
      const found = await api(`/api/products?q=${encodeURIComponent(q)}`);
      if (input.value.trim() !== q) return;
      learnTitles(found.drugs);
      const spelled = found.unmapped.length ? `<li class="menu-heading oa-result-head">With no ingredient: FDA's own spellings</li>${found.unmapped.map((x) => spellingRow(x, q)).join('')}` : '';
      out.innerHTML = found.drugs.length || spelled ? found.drugs.map((d) => productRow(d, q)).join('') + spelled : `<li class="result-none">FDA names no drug "${esc(q)}".</li>`;
      out.hidden = false;
    }, 120);
  });
  // the product a result opens, picked from what was typed
  const pick = (a) => picked('products', input.value, { picked: addressParts(a.getAttribute('href'))?.[1] || '' });
  out.addEventListener('click', (e) => { const a = e.target.closest('a.result-open'); if (a) pick(a); });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { const a = out.querySelector('a.result-open'); if (a) { pick(a); go(a.getAttribute('href')); } }
    if (e.key === 'Escape') { out.hidden = true; }
  });
}

drawn('home', (r, app) => { app.innerHTML = homePage(); wireFind(); fillHome(); });
