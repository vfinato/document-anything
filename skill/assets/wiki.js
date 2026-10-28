(function () {
  var I18N = window.WIKI_I18N || {};
  var root = document.documentElement;
  var store = {
    get: function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set: function (k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  };

  /* ---------- theme ---------- */
  var saved = store.get('wiki-theme');
  if (saved === 'dark' || saved === 'light') root.setAttribute('data-theme', saved);
  function isDark() {
    var t = root.getAttribute('data-theme');
    if (t) return t === 'dark';
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  }

  /* ---------- mermaid (CDN; without it the diagram source stays readable) ---------- */
  var diagrams = Array.prototype.slice.call(document.querySelectorAll('pre.mermaid'));
  diagrams.forEach(function (d) { d.setAttribute('data-src', d.textContent); });
  function renderDiagrams() {
    if (!window.mermaid || !diagrams.length) return;
    diagrams.forEach(function (d) {
      d.removeAttribute('data-processed');
      d.innerHTML = '';
      d.textContent = d.getAttribute('data-src');
    });
    try {
      window.mermaid.initialize({ startOnLoad: false, theme: isDark() ? 'dark' : 'default', securityLevel: 'strict',
        flowchart: { htmlLabels: true, curve: 'basis' }, sequence: { useMaxWidth: true } });
      window.mermaid.run({ nodes: diagrams });
    } catch (e) { /* keep the source text visible */ }
  }
  renderDiagrams();

  document.getElementById('themeBtn').addEventListener('click', function () {
    var next = isDark() ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    store.set('wiki-theme', next);
    renderDiagrams();
  });

  /* ---------- view filter (overview / detail) ---------- */
  var parts = document.querySelectorAll('.part');
  var viewBtns = document.querySelectorAll('.seg button');
  function applyView(v) {
    viewBtns.forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-view') === v)); });
    parts.forEach(function (p) {
      var kind = p.getAttribute('data-part');
      var show = v === 'all' || kind === v || (kind !== 'overview' && kind !== 'detail');
      p.classList.toggle('hidden-by-filter', !show);
    });
    syncToc();
    store.set('wiki-view', v);
  }
  viewBtns.forEach(function (b) { b.addEventListener('click', function () { applyView(b.getAttribute('data-view')); }); });

  /* ---------- table of contents ---------- */
  var tocLinks = Array.prototype.slice.call(document.querySelectorAll('nav.toc a'));
  function targetOf(a) { return document.getElementById(decodeURIComponent(a.getAttribute('href').slice(1))); }
  function syncToc() {
    tocLinks.forEach(function (a) {
      var target = targetOf(a);
      var hidden = !target || target.closest('.hidden-by-filter, .search-empty');
      a.parentElement.classList.toggle('hidden', !!hidden);
    });
  }
  var headings = tocLinks.map(targetOf).filter(Boolean);
  if ('IntersectionObserver' in window) {
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) {
          tocLinks.forEach(function (a) { a.classList.toggle('active', targetOf(a) === en.target); });
        }
      });
    }, { rootMargin: '0px 0px -75% 0px' });
    headings.forEach(function (h) { obs.observe(h); });
  }

  /* ---------- expand / collapse ---------- */
  function setAll(open) { document.querySelectorAll('details').forEach(function (d) { d.open = open; }); }
  document.getElementById('expandAll').addEventListener('click', function () { setAll(true); });
  document.getElementById('collapseAll').addEventListener('click', function () { setAll(false); });
  window.addEventListener('beforeprint', function () { setAll(true); });

  /* ---------- copy buttons on code blocks ---------- */
  document.querySelectorAll('pre > code').forEach(function (code) {
    var btn = document.createElement('button');
    btn.className = 'btn copy';
    btn.type = 'button';
    btn.textContent = I18N.copy || 'Copy';
    btn.addEventListener('click', function () {
      var done = function () { btn.textContent = I18N.copied || 'Copied'; setTimeout(function () { btn.textContent = I18N.copy || 'Copy'; }, 1400); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(code.textContent).then(done, function () {});
    });
    code.parentNode.appendChild(btn);
  });

  /* ---------- search ---------- */
  var q = document.getElementById('q');
  var info = document.getElementById('searchInfo');
  var sections = Array.prototype.slice.call(document.querySelectorAll('section.sec'));
  var marks = [];
  function clearMarks() {
    marks.forEach(function (m) {
      var p = m.parentNode; if (!p) return;
      p.replaceChild(document.createTextNode(m.textContent), m); p.normalize();
    });
    marks = [];
  }
  function highlight(node, term) {
    var walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) {
        if (!n.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
        var tag = n.parentNode && n.parentNode.nodeName;
        if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'MARK' || tag === 'BUTTON') return NodeFilter.FILTER_REJECT;
        if (n.parentNode.closest && n.parentNode.closest('.diagram')) return NodeFilter.FILTER_REJECT;
        return n.nodeValue.toLowerCase().indexOf(term) >= 0 ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
      }
    });
    var list = []; while (walker.nextNode()) list.push(walker.currentNode);
    list.forEach(function (t) {
      var val = t.nodeValue, low = val.toLowerCase(), i = 0, idx, frag = document.createDocumentFragment();
      while ((idx = low.indexOf(term, i)) >= 0) {
        frag.appendChild(document.createTextNode(val.slice(i, idx)));
        var m = document.createElement('mark'); m.textContent = val.slice(idx, idx + term.length);
        frag.appendChild(m); marks.push(m); i = idx + term.length;
      }
      frag.appendChild(document.createTextNode(val.slice(i)));
      t.parentNode.replaceChild(frag, t);
    });
  }
  function openAncestors(el) {
    var d = el.closest('details'); while (d) { d.open = true; d = d.parentElement && d.parentElement.closest('details'); }
  }
  var timer;
  q.addEventListener('input', function () {
    clearTimeout(timer);
    timer = setTimeout(function () {
      clearMarks();
      var term = q.value.trim().toLowerCase();
      if (term.length < 2) {
        sections.forEach(function (s) { s.classList.remove('hidden-by-filter'); });
        parts.forEach(function (p) { p.classList.remove('search-empty'); });
        info.textContent = ''; syncToc(); return;
      }
      var hits = 0;
      sections.forEach(function (s) {
        var match = s.textContent.toLowerCase().indexOf(term) >= 0;
        s.classList.toggle('hidden-by-filter', !match);
        if (match) { hits++; highlight(s, term); }
      });
      parts.forEach(function (p) {
        var own = p.querySelectorAll('section.sec');
        var none = own.length > 0 && !p.querySelector('section.sec:not(.hidden-by-filter)');
        p.classList.toggle('search-empty', none);
      });
      marks.forEach(openAncestors);
      info.textContent = hits
        ? (I18N.found || '{s} section(s) · {n} match(es)').replace('{s}', hits).replace('{n}', marks.length)
        : (I18N.notFound || 'Nothing found');
      syncToc();
      if (marks[0]) marks[0].scrollIntoView({ block: 'center' });
    }, 220);
  });

  /* ---------- mobile navigation and back-to-top ---------- */
  document.getElementById('navToggle').addEventListener('click', function () { document.body.classList.toggle('nav-open'); });
  tocLinks.forEach(function (a) { a.addEventListener('click', function () { document.body.classList.remove('nav-open'); }); });
  var toTop = document.getElementById('toTop');
  window.addEventListener('scroll', function () { toTop.classList.toggle('show', window.scrollY > 800); }, { passive: true });
  toTop.addEventListener('click', function () { window.scrollTo({ top: 0 }); });

  /* ---------- open <details> when navigating to an anchor inside it ---------- */
  function openTarget() {
    var id = decodeURIComponent(location.hash.slice(1)); if (!id) return;
    var el = document.getElementById(id); if (el) openAncestors(el);
  }
  window.addEventListener('hashchange', openTarget); openTarget();

  var v = store.get('wiki-view'); applyView(v === 'overview' || v === 'detail' ? v : 'all');
})();
