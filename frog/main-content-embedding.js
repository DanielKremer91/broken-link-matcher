// Main Content -> OpenAI Embedding (mit Chunking), Vorlage für Screaming Frog
//
// Grundlage: das Snippet von ONE Beyond Search für Fressnapf, verallgemeinert.
// Jede Website ist anders gebaut. Die Vorlage findet den Hauptinhalt auf vielen
// Seiten von selbst; für eine bestimmte Website trägst du unten bei
// CONTENT_ROOT_SELECTOR und EXTRA_EXCLUDE_SELECTOR eigene Selektoren ein.
//
// Screaming Frog: Konfiguration > Eigene > Eigenes JavaScript > Hinzufügen, Typ
// "Extraktion" (englisch: Configuration > Custom > Custom JavaScript > Add, Type
// "Extraction"). Als Name "Embeddings <Kunde>" eintragen. Dafür muss das Rendering
// auf JavaScript stehen: Konfiguration > Spider > Rendering > JavaScript.
//
// Ablauf:
// 1. Hauptinhalt extrahieren: H1 plus Inhaltsbereich, ohne Navigation, Header,
//    Footer, Seitenleisten, Formulare, Banner, Teaser und Bilder.
// 2. Text an Absatz- und Satzgrenzen in Chunks teilen (sicher unter dem
//    Token-Limit von text-embedding-3-small).
// 3. Alle Chunks in EINEM Request an OpenAI schicken.
// 4. Chunk-Vektoren längengewichtet mitteln und L2-normalisieren.
// 5. Vektor als kommaseparierten String über seoSpider.data() zurückgeben.

// ---------- Einstellungen ----------

const OPENAI_API_KEY = ''; // <-- Schlüssel erst im Frog-Editor eintragen, nicht in dieser Datei im Repo

// Muss exakt zu "embedding.model" in monitor.config.json passen, sonst passen
// die Vektoren nicht zu den Vektoren der toten Wettbewerberseiten.
const MODEL = 'text-embedding-3-small';

// Deutsch: ca. 1 Token je 3 bis 4 Zeichen. 6.000 Zeichen bleiben weit unter 8.191 Tokens.
const MAX_CHUNK_CHARS = 6000;

// Optional: CSS-Selektor des Inhaltsbereichs dieser Website, z. B. '.article-body'.
// Leer lassen = automatische Suche (main, article, role=main, textreichster Block).
const CONTENT_ROOT_SELECTOR = '';

// Optional: zusätzliche Bereiche, die nie Hauptinhalt sind, z. B. '.promo-box, .author-card'.
const EXTRA_EXCLUDE_SELECTOR = '';

// Vorschau: true gibt statt des Embeddings den extrahierten Text zurück. So siehst du
// in Screaming Frog nach einem kurzen Testcrawl, was eingebettet würde, ohne
// OpenAI-Kosten. Vor dem Speichern der Konfiguration wieder auf false stellen.
const PREVIEW_TEXT = false;

// Ab einer Überschrift mit diesem Anfang beginnt der Seitenabschluss (Teaser, Themenlisten).
const END_HEADING = /^(weitere beiträge|weitere artikel|weitere themen|ähnliche artikel|das könnte (dich|sie) auch interessieren|mehr zum thema|passende artikel|related (posts|articles)|you might also like|read more)/i;

// ---------- 1. Hauptinhalt ----------

const BASE_EXCLUDE = [
  'script', 'style', 'noscript', 'template', 'iframe', 'svg', 'canvas', 'button',
  'input', 'select', 'textarea', 'form', 'nav', 'header', 'footer', 'aside',
  'img', 'picture', 'figure', 'figcaption', 'video', 'audio', 'dialog',
  '[role="navigation"]', '[role="banner"]', '[role="contentinfo"]',
  '[role="complementary"]', '[role="search"]', '[role="dialog"]',
  '[aria-hidden="true"]', '[hidden]',
  '[class*="breadcrumb"]', '[class*="cookie"]', '[id*="cookie"]', '[class*="consent"]',
  '[class*="newsletter"]', '[class*="share"]', '[class*="social"]', '[class*="related"]',
  '[class*="comment"]', '[class*="table-of-contents"]', '.toc', '#toc'
].join(',');
const EXCLUDE_SELECTOR = EXTRA_EXCLUDE_SELECTOR ? BASE_EXCLUDE + ',' + EXTRA_EXCLUDE_SELECTOR : BASE_EXCLUDE;

const BLOCK_TAGS = new Set([
  'P', 'DIV', 'LI', 'UL', 'OL', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'TABLE',
  'TR', 'BLOCKQUOTE', 'DT', 'DD', 'SECTION', 'ARTICLE', 'BR'
]);
const HEADINGS = new Set(['H2', 'H3', 'H4']);
// Eigene Elemente (Web Components) mit diesen Namen sind Seitenrahmen, z. B. <c-navigation>.
const CUSTOM_BOILERPLATE = /(NAV|MENU|FOOTER|HEADER|COOKIE|CONSENT|TOAST|BANNER)/;
// Container, die überwiegend aus Links bestehen (Menüs, Footer, Teaserlisten), werden übersprungen.
const LINK_CONTAINERS = new Set(['DIV', 'SECTION', 'UL', 'OL', 'TABLE', 'ASIDE']);
const MAX_LINK_DENSITY = 0.6;

function clean(s) {
  return s.replace(/\u00a0/g, ' ').replace(/[ \t\r\f\v]+/g, ' ').trim();
}

function textLength(el) {
  return clean(el.textContent || '').length;
}

function linkDensity(el) {
  const len = textLength(el);
  if (!len) return 0;
  let links = 0;
  for (const a of el.querySelectorAll('a')) links += textLength(a);
  return links / len;
}

function isBoilerplate(node) {
  if (node.matches(EXCLUDE_SELECTOR)) return true;
  const custom = node.tagName.includes('-');
  if (custom && CUSTOM_BOILERPLATE.test(node.tagName)) return true;
  if ((LINK_CONTAINERS.has(node.tagName) || custom) && textLength(node) >= 20
      && linkDensity(node) > MAX_LINK_DENSITY) return true;
  return false;
}

// Element -> Textzeilen. Blockelemente erzeugen Zeilenumbrüche, Links werden zu
// ihrem Ankertext, Tabellenzellen werden mit " | " getrennt. Stoppt am Seitenabschluss.
function blockText(root) {
  const out = [];
  let line = '';
  let stopped = false;
  const flush = () => { const t = clean(line); if (t) out.push(t); line = ''; };
  (function walk(node) {
    if (stopped) return;
    if (node.nodeType === 3) { line += node.nodeValue; return; }
    if (node.nodeType !== 1) return;
    if (isBoilerplate(node)) return;
    if (HEADINGS.has(node.tagName) && END_HEADING.test(clean(node.textContent))) { stopped = true; return; }
    const isBlock = BLOCK_TAGS.has(node.tagName) || node.tagName.includes('-');
    if (isBlock) flush();
    if (node.tagName === 'LI') line += '- ';
    for (const child of node.childNodes) {
      walk(child);
      if (child.nodeType === 1 && (child.tagName === 'TD' || child.tagName === 'TH')) line += ' | ';
    }
    if (isBlock) flush();
  })(root);
  flush();
  return out.map(l => l.replace(/\s*\|\s*$/, ''));
}

// Inhaltsbereich finden: eigener Selektor, dann article, dann main, sonst die ganze
// Seite. Seitenrahmen und Linklisten filtert blockText() in jedem Fall heraus.
function findContentRoot() {
  if (CONTENT_ROOT_SELECTOR) {
    const custom = document.querySelector(CONTENT_ROOT_SELECTOR);
    if (custom) return custom;
  }
  const articles = Array.from(document.querySelectorAll('main article, article'))
    .filter(a => !a.closest(EXCLUDE_SELECTOR));
  if (articles.length) return articles.sort((a, b) => textLength(b) - textLength(a))[0];
  return document.querySelector('main, [role="main"]') || document.body;
}

// Kurze Metazeilen wie Datum oder Lesedauer gehören nicht zum Inhalt.
const META_LINE = /^(©|\(c\)|copyright|\d{1,2}\.\s?\d{1,2}\.\s?\d{2,4}|\d{4}-\d{2}-\d{2}|lesedauer|lesezeit|reading time|\d+\s*min(\.|uten)?\b)|cookie/i;

function extractMainContent() {
  const lines = [];
  const h1 = document.querySelector('h1');
  const h1Text = h1 ? clean(h1.textContent) : '';
  if (h1Text) lines.push(h1Text);
  for (const line of blockText(findContentRoot())) {
    if (line === h1Text) continue; // H1 steht schon vorne
    if (line.length < 80 && META_LINE.test(line)) continue;
    lines.push(line);
  }
  // Direkt aufeinanderfolgende Duplikate entfernen
  return lines.filter((l, i) => l !== lines[i - 1]);
}

// ---------- 2. Chunking ----------

function splitLong(text) {
  // Einzelner Absatz zu lang: an Satzgrenzen teilen, notfalls hart schneiden
  const sentences = text.match(/[^.!?]+[.!?]+["“”)]*\s*|[^.!?]+$/g) || [text];
  const parts = [];
  let cur = '';
  for (let s of sentences) {
    while (s.length > MAX_CHUNK_CHARS) {
      if (cur) { parts.push(cur.trim()); cur = ''; }
      parts.push(s.slice(0, MAX_CHUNK_CHARS));
      s = s.slice(MAX_CHUNK_CHARS);
    }
    if ((cur + s).length > MAX_CHUNK_CHARS) { parts.push(cur.trim()); cur = ''; }
    cur += s;
  }
  if (cur.trim()) parts.push(cur.trim());
  return parts;
}

function chunkLines(lines) {
  const chunks = [];
  let cur = '';
  for (const line of lines) {
    const pieces = line.length > MAX_CHUNK_CHARS ? splitLong(line) : [line];
    for (const p of pieces) {
      if (cur && (cur.length + 1 + p.length) > MAX_CHUNK_CHARS) {
        chunks.push(cur);
        cur = '';
      }
      cur = cur ? cur + '\n' + p : p;
    }
  }
  if (cur) chunks.push(cur);
  return chunks;
}

// ---------- 3. bis 5. Embedding ----------

function averageEmbeddings(vectors, weights) {
  const dim = vectors[0].length;
  const avg = new Array(dim).fill(0);
  const total = weights.reduce((a, b) => a + b, 0);
  vectors.forEach((v, i) => {
    const w = weights[i] / total;
    for (let d = 0; d < dim; d++) avg[d] += v[d] * w;
  });
  const norm = Math.sqrt(avg.reduce((a, x) => a + x * x, 0)) || 1;
  return avg.map(x => x / norm);
}

function getEmbedding() {
  const chunks = chunkLines(extractMainContent());
  if (!chunks.length) return Promise.reject(new Error('Kein Hauptinhalt gefunden'));

  return fetch('https://api.openai.com/v1/embeddings', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer ' + OPENAI_API_KEY
    },
    body: JSON.stringify({ model: MODEL, input: chunks, encoding_format: 'float' })
  })
    .then(response => {
      if (!response.ok) {
        return response.text().then(text => { throw new Error(text); });
      }
      return response.json();
    })
    .then(data => {
      const vectors = data.data
        .sort((a, b) => a.index - b.index)
        .map(d => d.embedding);
      if (vectors.length === 1) return vectors[0].toString();
      return averageEmbeddings(vectors, chunks.map(c => c.length)).toString();
    });
}

if (PREVIEW_TEXT) {
  return seoSpider.data(extractMainContent().join('\n'));
}

return getEmbedding()
  .then(embedding => seoSpider.data(embedding))
  .catch(error => seoSpider.error(error));
