#!/usr/bin/env python3
"""
Single-file Web MIB Browser — pure reader/visualizer (no SNMP).
- Only dependency: Flask (pip install Flask)
- Parses textual MIBs (.mib/.txt) with a best-effort SMIv2 parser
- Browsable OID tree (numeric + symbolic segments)
- Full-text search on name / OID / type / description
  * Enum/bitfield rendering in Inspector (INTEGER {..} / BITS {..}), collapsible if long
  * Auto-load *.mib from script folder (and subfolders)
  * Sidebar shows folder structure (collapsible), with Uploads grouped separately
  * IMPORTS and MODULE-IDENTITY shown above the tree (not inside the tree)
"""
from __future__ import annotations

import re, json, html, tempfile
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

from flask import Flask, request, redirect, url_for, render_template_string, jsonify
from jinja2.loaders import DictLoader


app = Flask(__name__)

# ==========================
# Templates / Styles / JS
# ==========================
BASE_HTML = r"""
<!doctype html>
<html class="dark">
<head>
  <meta charset="utf-8" />
  <title>Web MIB Browser</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    :root { color-scheme: light dark; }
    html.dark { background:#111; color:#eee; }
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; margin: 0; font-size: var(--base-font,14px); }
    header {
      position: sticky; top: 0; z-index: 1000; background: #fff;
      padding: 12px 16px; border-bottom: 1px solid #ddd;
      display:flex; gap:12px; align-items:center; flex-wrap:wrap;
    }
    html.dark header { background:#111; border-color:#333; }
    h1 { font-size: 18px; margin: 0; white-space: nowrap; }

    /* Two-column layout */
    main { display: grid; grid-template-columns: 320px 1fr; align-items: start; }
    aside { padding: 12px; }
    section { padding: 12px; }

    .card { border: 1px solid #eee; border-radius: 10px; padding: 10px 12px; margin: 8px 0; }
    html.dark .card { border-color:#333; }
    .muted { color: #888; }
    html.dark .muted { color:#aaa; }
    input[type="text"], input[type="file"] { padding: 8px; border-radius: 8px; border:1px solid #ccc; }
    input[type="text"] { width: 80%; }
    .row { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
    .btn { padding: 6px 10px; border-radius: 8px; border:1px solid #bbb; background:#f7f7f7; cursor:pointer; color:#000; }
    html.dark .btn { background:#222; color:#eee; border-color:#555; }
    .btn:active { transform: translateY(1px); }
    form { margin: 0; }
    .kv { display:grid; grid-template-columns: 140px 1fr; gap:6px 10px; }
    pre { white-space: pre-wrap; }
    .small { font-size: 12px; }
    .grow { flex: 1 1 auto; min-width: 240px; }

    /* Tree visuals */
    .tree { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px; }
    .tree details { position: relative; margin-left: 14px; padding-left: 12px; }
    .tree details::before {
      content: ""; position: absolute; left: 4px; top: 0; bottom: 0; width: 1px;
      background: rgba(128,128,128,.25);
    }
    .tree summary { display:flex; align-items:center; gap:8px; cursor: pointer; list-style: none; }
    .tree summary::-webkit-details-marker { display:none; }

    /* Node chevron */
    .tree summary .tw { width: 10px; display:inline-block; transform: rotate(0deg); transition: transform .15s ease; opacity:.7; }
    details[open] > summary .tw { transform: rotate(90deg); opacity: .9; }

    /* Hover toolbar */
    .node-actions { margin-left:auto; display:none; gap:6px; }
    summary:hover .node-actions { display:flex; }
    .icon-btn { border:1px solid #ddd; border-radius: 6px; padding: 2px 6px; font-size:11px; background:#f7f7f7; cursor:pointer; color:#000; }
    html.dark .icon-btn { background:#222; color:#eee; border-color:#555; }

    /* Class badges */
    .badge { display:inline-block; padding:2px 8px; border-radius: 999px; font-size: 11px; border:1px solid transparent; }
    .badge.type  { background:#eef6ff; border-color:#cfe5ff; color:#000; }
    .badge.ident { background:#eefaf0; border-color:#caefda; color:#000;}
    .badge.note  { background:#fff6e5; border-color:#ffe3b5; color:#000;}

    /* Inspector panel (right side) */
    #inspector { position: static; border:1px solid #eee; border-radius: 10px; padding: 10px 12px; }
    html.dark #inspector { border-color:#333; }
    #inspector.pinned { position: sticky; top: 70px; }
    .breadcrumb { font-size:12px; color:#666; margin-bottom:8px; word-break:break-all; }
    html.dark .breadcrumb { color:#aaa; }

    /* Compact mode: hide in-tree detail cards */
    body.compact .tree .card { display:none; }
    /* Buttons reflect state via label */
    #compactBtn[data-mode="compact"]::after { content: "Verbose"; }
    #compactBtn[data-mode="verbose"]::after { content: "Compact"; }

    /* Enum table styles */
    .enum-table { border-collapse: collapse; font-size:12px; margin-top:6px; width:100%; }
    .enum-table th, .enum-table td { border:1px solid #ccc; padding:4px 6px; text-align:left; }
    html.dark .enum-table th, html.dark .enum-table td { border-color:#555; }
    .enum-wrap.enum-collapsed { max-height: 160px; overflow: hidden; position: relative; }
    .enum-wrap.enum-collapsed::after {
      content:""; position:absolute; left:0; right:0; bottom:0; height:30px;
      background: linear-gradient(transparent, rgba(255,255,255,.9));
    }
    html.dark .enum-wrap.enum-collapsed::after {
      background: linear-gradient(transparent, rgba(17,17,17,.95));
    }

    /* Sidebar folder tree */
    .fs-tree details { margin-left: 10px; }
    .fs-tree summary { cursor: pointer; }
    .fs-file { margin-left: 16px; }

    /* Sidebar collapse/expand */
    aside {
      transition: width 0.25s ease, min-width 0.25s ease;
      overflow: hidden;
    }
    aside.collapsed {
      width: 0 !important;
      min-width: 0 !important;
      padding: 0 !important;
      border: none;
    }
    aside.collapsed .fs-tree,
    aside.collapsed h3 {
      display: none;
    }

    /* Hover strip when collapsed */
    #sidebar-hover {
      position: absolute;
      top: 0;
      left: 0;
      bottom: 0;
      width: 12px;
      background: transparent;
      cursor: ew-resize;
      z-index: 2000;
    }
    #sidebar-hover:hover {
      background: rgba(128,128,128,0.1);
    }
    #sidebar-flyout {
      position: absolute;
      top: 0;
      left: 12px;
      bottom: 0;
      width: 280px;
      background: var(--flyout-bg, #fff);
      border-right: 1px solid #ddd;
      overflow-y: auto;
      display: none;
      z-index: 2001;
      padding: 10px;
    }
    html.dark #sidebar-flyout {
      --flyout-bg: #111;
      border-color: #333;
    }

    /* Sidebar collapse system */
    :root { --sidebar-width: 320px; --rail-width: 50px; }
    main { display: grid; grid-template-columns: var(--sidebar-width) 1fr; align-items: start; }

    /* When collapsed, sidebar width becomes a slim rail */
    body.sidebar-collapsed main { grid-template-columns: var(--rail-width) 1fr; }

    /* Sidebar itself scrollable */
    #sidebar { overflow: auto; }

    /* Hover rail  hidden normally, visible when collapsed */
    #sidebar-rail {
      position: fixed;
      top: 64px;            /* below the header */
      left: 0;
      bottom: 0;
      width: var(--rail-width, 12px);
      display: none;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      user-select: none;
      font-size: 10px;
      color: #888;
      border-right: 1px solid #ddd;
      background: inherit;
      z-index: 1100;
      background-color: #000;
      font-size: 25px;
    }
    html.dark #sidebar-rail { border-color:#333; color:#aaa; }
    body.sidebar-collapsed #sidebar-rail { display: flex; }

    /* Flyout panel (slides from left) */
    #sidebar-flyout {
      position: fixed;
      top: 64px;              /* below your header */
      left: 0;
      bottom: 0;
      width: min(420px, 85vw);
      background: inherit;
      border-right: 1px solid #ddd;
      box-shadow: 0 2px 20px rgba(0,0,0,.2);
      transform: translateX(-100%);
      opacity: 0;
      pointer-events: none;
      transition: transform .18s ease, opacity .18s ease;
      overflow: auto;
      padding: 10px 12px;
      z-index: 1200;
    }
    html.dark #sidebar-flyout { border-color:#333; box-shadow: 0 2px 20px rgba(0,0,0,.5); }

    #sidebar-flyout.open {
      transform: translateX(0);
      opacity: 1;
      pointer-events: auto;
    }


    #collapse-rail {
    font-size: 25px;
    cursor: pointer;
    }

    .icon-btn { padding: 1px 6px; line-height: 1.2; }

  </style>
</head>
<body>
<header>
  <h1>Web MIB Browser</h1>
  <div class="row">
    <form action="{{ url_for('upload') }}" method="post" enctype="multipart/form-data">
      <input type="file" name="files" multiple />
      <button class="btn" type="submit">Upload & Parse</button>
    </form>
    <form action="{{ url_for('clear_all') }}" method="post" onsubmit="return confirm('Clear all uploaded MIBs & cache?')">
      <button class="btn" type="submit">Clear</button>
    </form>
    <button class="btn" type="button" onclick="expandAll()">Expand All</button>
    <button id="compactBtn" class="btn" type="button" onclick="toggleCompact()" data-mode="verbose"></button>
    <button class="btn" type="button" onclick="resetSearch()">Reset Search</button>

  </div>
  <div class="row grow">
    <form onsubmit="doSearch(event)" class="grow">
      <input id="q" class="grow" type="text" placeholder="Search (name, OID, type, description) ..." />
    </form>
    <span class="small muted">Modules loaded: {{ modules|length }}</span>

  </div>
</header>

<main>
  <aside id="sidebar">
    <div class="row" style="justify-content: space-between; align-items:center;">
      <h3 class="muted">Loaded MIBs</h3>
      <div id="collapse-rail" title="Open MIBs panel" onclick="collapseSidebar()">◀️</div>

    </div>
    {% if not modules %}
      <p class="muted">No MIBs parsed yet. Upload your .mib files or drop them next to this script.</p>
    {% endif %}
    <div class="fs-tree">
      {{ modlist_html|safe }}
    </div>
  </aside>


  <!-- Flyout that shows the sidebar content on hover/intent -->
  <div id="sidebar-flyout" aria-hidden="true"></div>

  <!-- Hover strip (appears when collapsed) -->
  <div id="sidebar-hover" style="display:none;">
  </div>
  <div id="sidebar-flyout"></div>

  <section>
    {% block content %}{% endblock %}
  </section>
</main>
  <!-- Narrow rail visible only when collapsed -->
  <div id="sidebar-rail" title="Open MIBs panel">▶️</div>

<script>
// ---- helpers (GLOBAL) ----
window.escHtml = function(s){
  return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
};
window.escAttr = function(s){ return window.escHtml(String(s ?? '')); };

window.highlight = function (term, rootId) {
  const root = document.getElementById(rootId || 'content');
  if (!root || !term) return;

  // 1) Remove previous highlights (unwrap <mark> nodes)
  (function clearMarks(node){
    const marks = node.querySelectorAll('mark');
    marks.forEach(m => {
      const parent = m.parentNode;
      while (m.firstChild) parent.insertBefore(m.firstChild, m);
      parent.removeChild(m);
      parent.normalize(); // merge adjacent text nodes
    });
  })(root);

  // 2) Walk text nodes and wrap matches with <mark> (case-insensitive)
  const needle = term.toLowerCase();
  if (!needle) return;

  const walker = document.createTreeWalker(
    root,
    NodeFilter.SHOW_TEXT,
    {
      acceptNode: (n) => {
        // skip empty/whitespace, and skip inside SCRIPT/STYLE
        if (!n.nodeValue || !n.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
        const p = n.parentNode && n.parentNode.nodeName;
        if (p === 'SCRIPT' || p === 'STYLE') return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    }
  );

  const toProcess = [];
  while (walker.nextNode()) {
    const tn = walker.currentNode;
    // Only consider nodes that contain the term (case-insensitive)
    if (tn.nodeValue.toLowerCase().includes(needle)) toProcess.push(tn);
  }

  toProcess.forEach(tn => {
    let text = tn.nodeValue;
    let idx = 0;
    const frag = document.createDocumentFragment();

    while (true) {
      const hay = text.toLowerCase();
      const hit = hay.indexOf(needle, idx);
      if (hit === -1) {
        // append the rest
        frag.appendChild(document.createTextNode(text.slice(idx)));
        break;
      }
      // pre-hit text
      if (hit > idx) frag.appendChild(document.createTextNode(text.slice(idx, hit)));
      // matched piece
      const mark = document.createElement('mark');
      mark.textContent = text.slice(hit, hit + needle.length);
      frag.appendChild(mark);
      idx = hit + needle.length;
    }

    tn.parentNode.replaceChild(frag, tn);
  });
};

// Inspector utilities
window.setInspector = function({name='', oid='', sym_oid='', klass='', syntax='', desc='', path='', enums=[]}){
  const byId = id => document.getElementById(id);
  if(!byId('i_name')) return;

  byId('i_name').textContent   = name;
  byId('i_class').textContent  = klass;
  byId('i_syntax').textContent = syntax;

  // safe newlines
  byId('i_desc').innerHTML = (desc || '').replace(/\\n/g,'<br>');

  // breadcrumb shows numeric + (symbolic) if available
  let crumbTxt = oid;
  if (sym_oid && sym_oid !== oid) crumbTxt += " (" + sym_oid + ")";
  byId('crumb').textContent = crumbTxt;

  // OID line shows numeric + (symbolic) visually but keeps numeric in data-oid for copying
  const oidEl = byId('i_oid');
  oidEl.setAttribute('data-oid', oid || '');
  if (sym_oid && sym_oid !== oid) {
    oidEl.innerHTML = `${window.escHtml(oid)} <span class="muted">(${window.escHtml(sym_oid)})</span>`;
  } else {
    oidEl.textContent = oid;
  }

  // Enum/bitfield table
  let et = '';
  if (enums && enums.length){
    let rows = enums.map(([k,v]) => `<tr><td>${window.escHtml(k)}</td><td>${window.escHtml(v)}</td></tr>`).join('');
    et = `
      <div class="enum-wrap ${enums.length>8 ? 'enum-collapsed' : ''}" id="enumWrap">
        <table class="enum-table">
          <thead><tr><th>Name</th><th>Value</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
    if(enums.length>8){
      et += `<div style="margin-top:6px;"><button class="btn small" type="button" onclick="toggleEnum()">
                <span id="enumToggleLabel">Show more</span>
             </button></div>`;
    }
  }
  byId('i_enum').innerHTML = et;

  byId('inspector')?.scrollIntoView({ block:'nearest', behavior:'smooth' });
};

window.toggleEnum = function(){
  const ew = document.getElementById('enumWrap');
  const lab = document.getElementById('enumToggleLabel');
  if(!ew) return;
  ew.classList.toggle('enum-collapsed');
  if(lab){
    lab.textContent = ew.classList.contains('enum-collapsed') ? 'Show more' : 'Show less';
  }
};

window.inspectSearchResult = function(card){
  const d = card.dataset;
  window.setInspector({
    name:   d.name   || '',
    oid:    d.oid    || '',
    sym_oid:d.symOid || '',
    klass:  d.klass  || '',
    syntax: d.syntax || '',
    desc:   d.desc   || '',
    path:   d.path   || '',
    enums:  d.enums ? JSON.parse(d.enums) : []
  });
};

// Search
window.doSearch = async function(e){
  if(e){ e.preventDefault(); }
  const q = document.getElementById('q').value.trim();
  if(!q){ return; }

  const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
  const data = await res.json();

  const maincol   = document.getElementById('maincol');
  const container = maincol || document.getElementById('content');

  let html = `<h2>Search results for "<em>${window.escHtml(q)}</em>"</h2>`;
  if(data.results.length === 0){
    html += `<p class="muted">No matches.</p>`;
  } else {
    html += data.results.map(n => `
      <div class="card"
           role="button" tabindex="0"
           onclick="inspectSearchResult(this)"
           onkeydown="if(event.key==='Enter'||event.key===' '){inspectSearchResult(this)}"
           data-name="${window.escAttr(n.name || '(unnamed)')}"
           data-oid="${window.escAttr(n.oid || '')}"
           data-sym-oid="${window.escAttr(n.sym_oid || '')}"
           data-klass="${window.escAttr(n.klass || '')}"
           data-syntax="${window.escAttr(n.syntax || '')}"
           data-desc="${window.escAttr(n.description || '')}"
           data-path="${window.escAttr(n.oid || n.name || '')}"
           data-enums='${window.escAttr(JSON.stringify(n.enums || []))}'>
        <div class="row">
          <strong>${(n.name || '(unnamed)')}</strong>
          <span class="badge">${n.klass || ''}</span>
          <span class="badge">${n.syntax || ''}</span>
        </div>
        <div class="kv small">
          <div>Module</div><div>${n.module}</div>
          <div>OID</div><div>${n.oid || ''}${(n.sym_oid && n.sym_oid !== n.oid) ? ' <span class="muted">(' + window.escHtml(n.sym_oid) + ')</span>' : ''}</div>
        </div>
        </style
        <div style="margin-top:6px;">
          ${
            n.oid
              ? `<button class="btn small" type="button"
                        onclick="goToInTree('${window.escAttr(n.module)}','${window.escAttr(n.oid)}')">
                    Go to in tree
                </button>`
              : `<span class="muted small">(no OID – can’t jump)</span>`
          }
        </div>

      </div>
    `).join('');
  }
  container.innerHTML = html;
  window.highlight(q, container.id);
};

window.goToInTree = function(mod, oid){
  if(!mod) return;
  let url = `/module/${encodeURIComponent(mod)}`;
  if(oid && /^\d+(?:\.\d+)+$/.test(oid)) {
    url += `#${encodeURIComponent(oid)}`;
  }
  window.location = url;
};

// Misc UI
window.resetSearch = function(){
  const q = document.getElementById('q'); if(q){ q.value = ''; }
  const path = window.location.pathname || '';
  if(path.startsWith('/module/')){ window.location.reload(); } else { window.location = '/'; }
};

window.expandAll = function(){
  const tree = document.getElementById('tree'); if(!tree) return;
  tree.querySelectorAll('details').forEach(d => { d.open = true; });
};
window.collapseAll = function(){
  const tree = document.getElementById('tree'); if(!tree) return;
  tree.querySelectorAll('details').forEach(d => d.open = false);
};
window.expandToLevel = function(level){
  const tree = document.getElementById('tree'); if(!tree) return;
  window.collapseAll();
  tree.querySelectorAll('details').forEach(d => {
    const depth = (d.dataset.path || '').split('.').filter(Boolean).length;
    if(depth <= level){ d.open = true; }
  });
};

window.copyText = function(t){
  if(!t) return;
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(t).catch(()=>{});
  } else {
    const ta = document.createElement('textarea');
    ta.value = t; ta.style.position='fixed'; ta.style.opacity='0'; document.body.appendChild(ta);
    ta.focus(); ta.select(); try { document.execCommand('copy'); } catch(e){}
    document.body.removeChild(ta);
  }
};

window.expandChildren = function(ev, btn){
  ev.preventDefault(); ev.stopPropagation();
  const det = btn.closest('details');
  if(!det) return;
  det.open = true;
  det.querySelectorAll(':scope details').forEach(d => d.open = true);
};

window.toggleInspectorPin = function(btn){
  const insp = document.getElementById('inspector');
  if(!insp) return;
  insp.classList.toggle('pinned');
  btn.textContent = insp.classList.contains('pinned') ? 'Unpin' : 'Pin';
};

window.selectNode = function(ev, summaryEl){
  const det = summaryEl.closest('details'); if(!det) return;
  const d = det.dataset;
  window.setInspector({
    name:   d.name   || '',
    oid:    d.oid    || '',
    sym_oid:d.symoid || d.symOid || '',
    klass:  d.class  || '',
    syntax: d.syntax || '',
    desc:   d.desc   || '',
    path:   d.path   || '',
    enums:  d.enums ? JSON.parse(d.enums) : []
  });
};

/* Compact/Verbose  */
function applyCompactFromStorage(){
  const stored = localStorage.getItem('compact') === '1';
  document.body.classList.toggle('compact', stored);
  const btn = document.getElementById('compactBtn');
  if(btn) btn.setAttribute('data-mode', stored ? 'compact' : 'verbose');
}
window.toggleCompact = function(){
  const nowCompact = !document.body.classList.contains('compact');
  document.body.classList.toggle('compact', nowCompact);
  localStorage.setItem('compact', nowCompact ? '1' : '0');
  const btn = document.getElementById('compactBtn');
  if(btn) btn.setAttribute('data-mode', nowCompact ? 'compact' : 'verbose');
};

window.addEventListener('DOMContentLoaded', ()=>{
  const rail = document.getElementById('sidebar-rail');
  if (rail) {
    rail.addEventListener('click', ()=>{
      document.body.classList.remove('sidebar-collapsed');

    });
  }

  const collapseBtn = document.querySelector('.collapse-btn');
  if (collapseBtn) {
    collapseBtn.addEventListener('click', ()=>{
      document.body.classList.add('sidebar-collapsed');
    });
  }

  // restore last state (default = open)
  const state = localStorage.getItem('sidebar');
  if (state === 'collapsed') {
    document.body.classList.add('sidebar-collapsed');
  } else {
    document.body.classList.remove('sidebar-collapsed');
  }

  console.log('[MIB Browser] client script loaded');
});

// --- Sidebar collapse/expand logic ---
window.collapseSidebar = function(){
  const aside  = document.getElementById('sidebar');
  const rail   = document.getElementById('sidebar-rail');
  const flyout = document.getElementById('sidebar-flyout');

  // Switch layout
  document.body.classList.add('sidebar-collapsed');

  // Fill flyout with a copy of the sidebar content + an Expand button
  // NOTE: We take innerHTML (safe; same-origin content).
  const inner = aside.innerHTML;

};

window.expandSidebar = function(){
  const rail   = document.getElementById('sidebar-rail');
  const flyout = document.getElementById('sidebar-flyout');

  document.body.classList.remove('sidebar-collapsed');
  flyout.classList.remove('open');
  flyout.innerHTML = ''; // clear (optional)
};

// Hover/intent to open flyout when collapsed
(function initSidebarHover(){
  const rail   = document.getElementById('sidebar-rail');
  const flyout = document.getElementById('sidebar-flyout');
  if(!rail || !flyout) return;

  let hoverTimer = null;

  rail.addEventListener('mouseenter', ()=>{
    if (!document.body.classList.contains('sidebar-collapsed')) return;
    // small delay to avoid accidental flicker
    hoverTimer = setTimeout(()=> { flyout.classList.add('open'); }, 120);
  });
  rail.addEventListener('mouseleave', ()=>{
    if(hoverTimer){ clearTimeout(hoverTimer); hoverTimer = null; }
  });

  // Close if the mouse leaves the flyout
  flyout.addEventListener('mouseleave', ()=>{
    flyout.classList.remove('open');
  });

  // Also close on Escape
  document.addEventListener('keydown', (e)=>{
    if(e.key === 'Escape'){
      flyout.classList.remove('open');
    }
  });
})();

window.copyLink = function(oid){
  if(!oid) return;
  const base = location.href.split('#')[0];
  const url = `${base}#${encodeURIComponent(oid)}`;
  window.copyText(url);
};

function openParents(detailsEl){
  // open this branch and all ancestors
  let d = detailsEl;
  while(d && d.tagName === 'DETAILS'){
    d.open = true;
    d = d.parentElement?.closest('details');
  }
}

function selectByOid(oid){
  if(!oid) return false;
  const id = 'oid-' + oid;
  const det = document.getElementById(id) || document.querySelector(`[data-oid="${CSS.escape(oid)}"]`);
  if(!det) return false;
  openParents(det);
  det.scrollIntoView({block:'center', behavior:'smooth'});
  // also populate inspector from this node
  const sum = det.querySelector(':scope > summary');
  if(sum) window.selectNode(null, sum);
  return true;
}

// when user clicks a node, reflect in hash (if it has an OID)
const _origSelectNode = window.selectNode;
window.selectNode = function(ev, summaryEl){
  _origSelectNode(ev, summaryEl);
  const det = summaryEl?.closest('details');
  const oid = det?.dataset?.oid;
  if(oid && /^\d+(?:\.\d+)+$/.test(oid)){
    const newHash = '#' + oid;
    if(location.hash !== newHash){
      history.replaceState(null, '', newHash);
    }
  }
};

// on module page load, honor #<numeric OID>
window.addEventListener('DOMContentLoaded', ()=>{
  const m = (location.hash || '').match(/^#(\d+(?:\.\d+)+)$/);
  if(m){
    // tree may not be rendered yet? (it is, but be safe)
    setTimeout(()=>{ selectByOid(m[1]); }, 0);
  }
});

// also respond to hash changes while staying on the same page
window.addEventListener('hashchange', ()=>{
  const m = (location.hash || '').match(/^#(\d+(?:\.\d+)+)$/);
  if(m) selectByOid(m[1]);
});

</script>
</body>
</html>
"""

HOME_HTML = r"""
{% extends "base.html" %}
{% block content %}
  <div id="content">
    <h2>Welcome</h2>
    <p>Upload one or more MIB source files (.mib, .txt). We parse them directly and render a browsable tree.</p>
    {% if modules %}
      <p class="muted">Pick a module on the left to view its tree.</p>
    {% endif %}
  </div>
{% endblock %}
"""

MODULE_HTML = r"""
{% extends "base.html" %}
{% block content %}
  <!-- On module pages, #content becomes a 2-col grid: left main column + right inspector -->
  <div id="content" style="display:grid; grid-template-columns: 2fr 1fr; gap:16px;">
    <div id="maincol">
      <h2>{{ module }}</h2>

      {% if imports or module_identity %}
      <details class="card" open>
        <summary><strong>Imports &amp; Module Identity</strong></summary>

        {% if imports %}
          <h4 style="margin:8px 0 4px;">Imports</h4>
          <div class="small">
            {% for mod, syms in imports.items() %}
              <div style="margin:4px 0;">
                <strong>
                  {% if mod in modules %}
                    <a href="{{ url_for('module_view', module=mod) }}">{{ mod }}</a>
                  {% else %}
                    {{ mod }} <i>(modules not loaded)</i>
                  {% endif %}
                </strong>
                <div class="muted">
                  {{ syms|join(', ') }}
                </div>
              </div>
            {% endfor %}
          </div>
        {% endif %}

        {% if module_identity %}
          <h4 style="margin:12px 0 4px;">Module Identity: {{ module_identity.name }}</h4>
          <div class="kv small">
            <div>LAST-UPDATED</div>
            <div>{{ module_identity.last_updated }}</div>

            <div>ORGANIZATION</div>
            <div style="white-space:pre-wrap;">{{ module_identity.organization }}</div>

            <div>CONTACT-INFO</div>
            <div style="white-space:pre-wrap;">{{ module_identity.contact_info }}</div>

            <div>DESCRIPTION</div>
            <div style="white-space:pre-wrap;">{{ module_identity.description }}</div>

            {% if module_identity.revisions %}
            <div>REVISIONS</div>
            <div>{{ module_identity.revisions | join(', ') }}</div>
            {% endif %}
          </div>
        {% endif %}
        {% if defines_list %}
        <h4 style="margin:12px 0 4px;">Defines</h4>
        <div class="small">
          <div class="muted">Symbols provided by {{ module }}:</div>
          <div style="line-height:1.7;">
            {# show as inline chips #}
            {% for sym in defines_list %}
              <span class="badge" style="margin:2px 4px 2px 0;">{{ sym }}</span>
            {% endfor %}
          </div>
        </div>
      {% endif %}

      {% if used_by %}
        <h4 style="margin:12px 0 4px;">Used by</h4>
        <div class="small">
          {% for importer, syms in used_by.items()|sort %}
            <div style="margin:6px 0;">
              {% if importer in modules %}
                <a href="{{ url_for('module_view', module=importer) }}"><strong>{{ importer }}</strong></a>
              {% else %}
                <strong>{{ importer }}</strong>
              {% endif %}
              {% if syms %}
                <div class="muted">{{ syms|sort|join(', ') }}</div>
              {% endif %}
            </div>
          {% endfor %}
        </div>
{% endif %}
      </details>
      {% endif %}

      {% if not nodes %}
        <p class="muted">No nodes found in this module.</p>
      {% else %}
        <div class="tree" id="tree">
          {{ tree_html|safe }}
        </div>
      {% endif %}
    </div>
    <div>
      <div id="inspector" class="pinned">
          <div class="row" style="justify-content: space-between; align-items:center; margin-bottom:6px;">
            <strong class="small muted">Inspector</strong>
            <button class="icon-btn" type="button" onclick="toggleInspectorPin(this)" title="Pin/unpin inspector">Unpin</button>
          </div>
        <div class="breadcrumb" id="crumb"></div>
        <div class="kv small">
          <div>Name</div><div id="i_name" class="mono"></div>
          <div>OID</div><div id="i_oid" class="mono" data-oid=""></div>
          <div>Class</div><div id="i_class"></div>
          <div>Syntax</div><div id="i_syntax"></div>
          <div>Module</div><div id="i_module">{{ module }}</div>
        </div>
        <div class="small muted" id="i_desc" style="margin-top:8px;"></div>
        <!-- enum/bitfield pretty table -->
        <div id="i_enum" style="margin-top:8px;"></div>

        <div style="margin-top:8px;">
          <button class="btn" type="button"
                  onclick="copyText(document.getElementById('i_oid').dataset.oid)">
            Copy OID
          </button>
          <button class="btn" type="button"
                  onclick="copyLink(document.getElementById('i_oid').dataset.oid)">
            Copy link
          </button>
          <button class="btn" type="button"
                  onclick="copyText(document.getElementById('i_name').textContent)">
            Copy name
          </button>
        </div>
        <div style="margin-top:12px;" class="small muted">Expand:
          <button class="icon-btn" type="button" onclick="expandToLevel(1)">L1</button>
          <button class="icon-btn" type="button" onclick="expandToLevel(2)">L2</button>
          <button class="icon-btn" type="button" onclick="expandToLevel(3)">L3</button>
          <button class="icon-btn" type="button" onclick="expandToLevel(99)">All</button>
          <button class="icon-btn" type="button" onclick="collapseAll()">Collapse</button>
        </div>
      </div>
    </div>
  </div>
{% endblock %}
"""

app.jinja_loader = DictLoader({
    "base.html": BASE_HTML,
    "home.html": HOME_HTML,
    "module.html": MODULE_HTML,
})

# ==========================
# Storage
# ==========================
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = Path(tempfile.gettempdir()) / "web_mib_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

def _purge_dir(d: Path):
  try:
    for p in d.iterdir():
      if p.is_file():
        try: p.unlink()
        except Exception: pass
  except Exception:
    pass

# Start clean uploads (auto-discovery is separate)
_purge_dir(UPLOAD_DIR)

# { moduleName: {"doc": {"moduleName":..., "nodes": {...}, "meta": {...}}, "raw": <text>} }
COMPILED: Dict[str, Dict[str, Any]] = {}
# Map moduleName -> display path (relative to BASE_DIR or "Uploads/<file>")
MOD_TO_PATH: Dict[str, str] = {}
# Reverse import index: { target_module: { importer_module: [symbols...] } }
IMPORTED_BY: Dict[str, Dict[str, List[str]]] = {}
# What symbols each module defines (names we can import): { module: set(names) }
MODULE_EXPORTS: Dict[str, set] = {}

# ==========================
# Parser (best-effort SMIv2)
# ==========================
BASE_OIDS: Dict[str, str] = {
    # Top-level
    "ccitt": "0",
    "iso": "1",
    "joint-iso-ccitt": "2",

    # Under iso(1).org(3)
    "org": "1.3",

    # Under iso.org(3).dod(6)
    "dod": "1.3.6",
    "internet": "1.3.6.1",

    # Standard subtrees
    "directory": "1.3.6.1.1",
    "mgmt": "1.3.6.1.2",
    "mib-2": "1.3.6.1.2.1",
    "experimental": "1.3.6.1.3",
    "private": "1.3.6.1.4",
    "enterprises": "1.3.6.1.4.1",

    # SNMPv2
    "security": "1.3.6.1.5",
    "snmpV2": "1.3.6.1.6",
    "snmpDomains": "1.3.6.1.6.1",
    "snmpProxys": "1.3.6.1.6.2",
    "snmpModules": "1.3.6.1.6.3",
}

RE_HEADER = re.compile(r"^\s*([A-Za-z][A-Za-z0-9\-._]*)\s+DEFINITIONS\s*::=\s*BEGIN", re.M)
RE_LINE_COMMENT = re.compile(r"--[^\n]*")
RE_QUOTED = re.compile(r'"([^"]*)"')
RE_OID_ASSIGN = re.compile(r"(?m)^\s*(?P<name>[A-Za-z][\w\-]*)\s+OBJECT\s+IDENTIFIER\s*::=\s*\{(?P<body>[^}]*)\}")
RE_OBJTYPE = re.compile(r"(?ms)^\s*(?P<name>[A-Za-z][\w\-]*)\s+OBJECT-TYPE\s+(?P<body>.*?)::=\s*\{(?P<parent>[^}]*)\}")
RE_OBJIDENTITY = re.compile(r"(?ms)^\s*(?P<name>[A-Za-z][\w\-]*)\s+OBJECT-IDENTITY\s+(?P<body>.*?)::=\s*\{(?P<parent>[^}]*)\}")
RE_NOTIFICATION = re.compile(r"(?ms)^\s*(?P<name>[A-Za-z][\w\-]*)\s+NOTIFICATION-TYPE\s+(?P<body>.*?)::=\s*\{(?P<parent>[^}]*)\}")

# NEW: imports + module-identity
RE_IMPORTS = re.compile(r"(?ms)IMPORTS\s+(.*?)\s*;", re.S)

RE_IMPORTS_BLOCK = re.compile(r"\bIMPORTS\b(.*?);", re.S)
RE_MODULE_IDENTITY = re.compile(r"(?ms)^\s*(?P<name>[A-Za-z][\w\-]*)\s+MODULE-IDENTITY\s+(?P<body>.*?)::=\s*\{(?P<parent>[^\}]*)\}")
RE_TEXTUAL_CONVENTION = re.compile(r"(?ms)^\s*(?P<name>[A-Za-z][\w\-]*)\s*::=\s*TEXTUAL-CONVENTION\s*(?P<body>.*?)(?=^\s*[A-Za-z][\w\-]*\s*::=|\Z)")

# SMIv1/SMIv2 macro blocks
RE_SEQUENCE = re.compile(r"(?ms)^\s*(?P<name>[A-Za-z][\w\-]*)\s*::=\s*SEQUENCE\s*\{(?P<body>[^}]*)\}")
RE_OBJECT_GROUP = re.compile(r"(?ms)^\s*(?P<name>[A-Za-z][\w\-]*)\s+OBJECT-GROUP\s+(?P<body>.*?)::=\s*\{(?P<parent>[^}]*)\}")
RE_MODULE_COMPLIANCE = re.compile(r"(?ms)^\s*(?P<name>[A-Za-z][\w\-]*)\s+MODULE-COMPLIANCE\s+(?P<body>.*?)::=\s*\{(?P<parent>[^}]*)\}")
RE_AGENT_CAPS = re.compile(r"(?ms)^\s*(?P<name>[A-Za-z][\w\-]*)\s+AGENT-CAPABILITIES\s+(?P<body>.*?)::=\s*\{(?P<parent>[^}]*)\}")


def parse_imports_block(src: str) -> Dict[str, List[str]]:
    """
    Parse the IMPORTS section into a dict: { from_module: [symbols...] }.
    """
    m = RE_IMPORTS_BLOCK.search(src)
    if not m:
        return {}
    block = m.group(1)

    # Normalize whitespace and newlines (keep readable downstream)
    text = " ".join(line.strip() for line in block.splitlines())

    # Split into chunks like "sym1, sym2 FROM MOD"
    # We walk left-to-right capturing "(symbols) FROM (module)"
    out: Dict[str, List[str]] = {}
    # Use a loop to find each FROM segment and the preceding symbols
    pos = 0
    while True:
        fm = re.search(r"\bFROM\s+([A-Za-z][\w\-]*)", text[pos:])
        if not fm:
            break
        mod = fm.group(1)
        start = pos
        end = pos + fm.start()
        syms_chunk = text[start:end].strip().strip(",")
        # Split syms by commas
        syms = [s.strip() for s in syms_chunk.split(",") if s.strip()]
        out.setdefault(mod, [])
        out[mod].extend(syms)
        pos = pos + fm.end()
    # Clean symbol names (strip trailing comments/garbage)
    for k, v in out.items():
        cleaned = []
        for s in v:
            # keep only identifier-like tokens
            m_id = re.match(r"^[A-Za-z][A-Za-z0-9\-]*$", s)
            if m_id:
                cleaned.append(m_id.group(0))
        out[k] = cleaned
    return out

def _extract_first_quoted(body: str, key: str) -> str:
    m = re.search(rf"\b{key}\b\s+\"(.*?)\"", body, re.S)
    return (m.group(1) if m else "").strip()

def parse_module_identity(src: str) -> Optional[Dict[str, Any]]:
    """
    Return a structured dict for MODULE-IDENTITY or None:
    {
      "name": str,
      "last_updated": str,
      "organization": str,
      "contact_info": str,
      "description": str,
      "revisions": ["YYYYMMDDHHMMZ", ...]  # in order of appearance
    }
    """
    m = RE_MODULE_IDENTITY.search(src)
    if not m:
        return None
    name = m.group("name")
    body = m.group("body")

    last_updated = _extract_first_quoted(body, "LAST-UPDATED")
    organization = _extract_first_quoted(body, "ORGANIZATION")
    contact_info = _extract_first_quoted(body, "CONTACT-INFO")
    description  = _extract_first_quoted(body, "DESCRIPTION")

    # Collect all REVISION "..." occurrences in order
    revisions = [s.strip() for s in re.findall(r'\bREVISION\s+"(.*?)"', body, re.S)]

    return {
        "name": name,
        "last_updated": last_updated,
        "organization": organization,
        "contact_info": contact_info,
        "description": description,
        "revisions": revisions,
    }

def strip_comments(text: str) -> str:
    out, last = [], 0
    for m in RE_QUOTED.finditer(text):
        segment = text[last:m.start()]
        segment = RE_LINE_COMMENT.sub("", segment)
        out.append(segment); out.append(text[m.start():m.end()])
        last = m.end()
    tail = RE_LINE_COMMENT.sub("", text[last:])
    out.append(tail)
    return "".join(out)

def find_module_name(text: str) -> Optional[str]:
    m = RE_HEADER.search(text)
    return m.group(1) if m else None

def _parse_arc_token(tok: str) -> Tuple[str, Optional[int]]:
    tok = tok.strip()
    if not tok: return ("", None)
    if re.fullmatch(r"\d+(?:\.\d+)+", tok): return (tok, None)
    if tok.isdigit(): return (tok, None)
    m = re.match(r"([A-Za-z][\w\-]*)\s*\(\s*(\d+)\s*\)", tok)
    if m: return (m.group(1), int(m.group(2)))
    if re.match(r"^[A-Za-z][\w\-]*$", tok): return (tok, None)
    return (tok, None)

def _resolve_braced_oid(body: str, sym2oid: Dict[str, str]) -> str:
    parts = [p for p in body.replace("\n", " ").split() if p]
    if not parts:
        return ""
    tokens = []
    for p in parts:
        for t in p.split(","):
            t = t.strip()
            if t:
                tokens.append(t)

    path: List[str] = []
    parent_tok, _ = _parse_arc_token(tokens[0])

    if re.fullmatch(r"\d+(?:\.\d+)+", parent_tok):
        path = parent_tok.split(".")
    elif parent_tok.isdigit():
        path = [parent_tok]
    else:
        base = sym2oid.get(parent_tok) or BASE_OIDS.get(parent_tok)
        path = base.split(".") if base else [parent_tok]

    for tok in tokens[1:]:
        name, num = _parse_arc_token(tok)
        if name.isdigit():
            path.append(name)
        elif re.fullmatch(r"\d+(?:\.\d+)+", name):
            path.extend(name.split("."))
        elif num is not None:
            path.append(str(num))
        else:
            path.append(name)
    return ".".join([str(x) for x in path if str(x) != ""])

def _extract_field(block: str, key: str) -> str:
    m = re.search(rf"\b{key}\b\s+(.*?)(?:\n[A-Z\-]+\b|::=|\Z)", block, re.S)
    if not m:
        return ""
    val = m.group(1).strip()
    if key == "DESCRIPTION":
        mq = re.search(r'"(.*?)"', val, re.S)
        if mq:
            return mq.group(1).strip()
    return " ".join(val.split())

def _extract_list_in_braces(body: str, key: str) -> List[str]:
    m = re.search(rf"\b{key}\b\s*\{{(.*?)\}}", body, re.S)
    if not m: return []
    items = [s.strip() for s in m.group(1).split(",") if s.strip()]
    # only identifiers
    return [re.match(r"[A-Za-z][\w\-]*", s).group(0) for s in items if re.match(r"[A-Za-z][\w\-]*", s)]

ENUM_SET_RE = re.compile(r"\{([^}]*)\}", re.S)

def _extract_enums_from_syntax(syntax: str) -> List[Tuple[str, str]]:
    if not syntax:
        return []
    m = ENUM_SET_RE.search(syntax)
    if not m:
        return []
    body = m.group(1)
    out: List[Tuple[str, str]] = []
    for item in body.split(","):
        item = item.strip()
        mm = re.match(r"([A-Za-z][A-Za-z0-9\-_]*)\s*\(\s*([0-9]+)\s*\)$", item)
        if not mm:
            mm = re.match(r"([A-Za-z][A-Za-z0-9\-_]*)\s*\(\s*([0-9]+)\s*\)", item)
        if mm:
            out.append((mm.group(1), mm.group(2)))
    return out

def parse_mib_text(text: str) -> Dict[str, Any]:
    src = strip_comments(text)
    module = find_module_name(src) or "(unknown-module)"

    # ---- META: IMPORTS + MODULE-IDENTITY ----
    meta: Dict[str, Any] = {"imports_text": "", "identity": {}}

    mi = RE_IMPORTS.search(src)
    if mi:
        # keep the cleaned IMPORTS block for display
        imports_block = mi.group(1).strip()
        # compact whitespace for nicer rendering
        imports_block = re.sub(r"\s+\n", "\n", imports_block)
        meta["imports_text"] = imports_block

    im = RE_MODULE_IDENTITY.search(src)
    if im:
        ident_name, ident_body = im.group(1), im.group(2)
        lastupd = _extract_field(ident_body, "LAST-UPDATED")
        org      = _extract_field(ident_body, "ORGANIZATION")
        contact  = _extract_field(ident_body, "CONTACT-INFO")
        desc     = _extract_field(ident_body, "DESCRIPTION")
        revs     = re.findall(r'REVISION\s+"([^"]+)"', ident_body)
        meta["identity"] = {
            "name": ident_name,
            "last_updated": lastupd,
            "organization": org,
            "contact": contact,
            "description": desc,
            "revisions": revs,
        }

    # ---- Nodes ----
    sym2oid: Dict[str, str] = {}
    for m in RE_OID_ASSIGN.finditer(src):
        name = m.group("name"); body = m.group("body")
        oid = _resolve_braced_oid(body, sym2oid)
        if oid: sym2oid[name] = oid

    nodes: Dict[str, Dict[str, Any]] = {}
    def add_node(name: str, parent_body: str, klass: str, syntax: str, description: str):
        oid = _resolve_braced_oid(parent_body, sym2oid)

        # symbolic display like "sysOREntry 4" -> "sysOREntry.4"
        sym_disp = re.sub(r"\s+", " ", (parent_body or "").strip()).replace(","," ").strip()
        sym_oid = ".".join([t for t in sym_disp.split(" ") if t])

        enums = _extract_enums_from_syntax(syntax)
        nodes[name] = {
            "name": name,
            "oid": oid,
            "sym_oid": sym_oid,
            "klass": klass,
            "syntax": syntax,
            "description": description.strip(),
            "enums": enums
        }
        if oid and re.fullmatch(r"\d+(?:\.\d+)+", oid):
            sym2oid[name] = oid

    for m in RE_OBJIDENTITY.finditer(src):
        name = m.group("name"); body = m.group("body"); parent = m.group("parent")
        desc = _extract_field(body, "DESCRIPTION")
        add_node(name, parent, "OBJECT-IDENTITY", "", desc)

    for m in RE_OBJTYPE.finditer(src):
        name = m.group("name"); body = m.group("body"); parent = m.group("parent")
        syntax = _extract_field(body, "SYNTAX")
        desc = _extract_field(body, "DESCRIPTION")
        add_node(name, parent, "OBJECT-TYPE", syntax, desc)

    for m in RE_NOTIFICATION.finditer(src):
        name = m.group("name"); body = m.group("body"); parent = m.group("parent")
        desc = _extract_field(body, "DESCRIPTION")
        add_node(name, parent, "NOTIFICATION-TYPE", "", desc)

    for name, oid in sym2oid.items():
      nodes.setdefault(
          name,
          {"name": name, "oid": oid, "sym_oid": "", "klass": "OBJECT IDENTIFIER", "syntax": "", "description": "", "enums": []}
      )

    # Also include bare OBJECT IDENTIFIER assignments as plain nodes
    for name, oid in sym2oid.items():
        nodes.setdefault(
            name,
            {
                "name": name, "oid": oid, "sym_oid": "", "klass": "OBJECT IDENTIFIER",
                "syntax": "", "description": "", "enums": []
            }
        )
    
    # --- TEXTUAL-CONVENTIONs (no OIDs) ---
    for m in RE_TEXTUAL_CONVENTION.finditer(src):
        name  = m.group("name")
        body  = m.group("body")

        status = _extract_field(body, "STATUS")
        disp   = _extract_field(body, "DISPLAY-HINT") or _extract_field(body, "DISPLAY-HINT")  # keep as-is if absent
        desc   = _extract_field(body, "DESCRIPTION")
        syntax = _extract_field(body, "SYNTAX")

        # Show display-hint alongside the syntax for visibility
        syntax_show = syntax if not disp else f'{syntax}  [DISPLAY-HINT "{disp}"]'

        # No parent OID body (these don't live in the OID tree); add as no-oid nodes
        add_node(
            name=name,
            parent_body="",                      # forces "(no-oid)" bucket
            klass=f"TEXTUAL-CONVENTION{(' ('+status+')' if status else '')}",
            syntax=syntax_show,
            description=desc,
        )
      # --- SEQUENCE (structure-only, no OID) ---
    for m in RE_SEQUENCE.finditer(src):
        name = m.group("name")
        body = m.group("body").strip()
        # Show members, one per line
        members = [ln.strip().rstrip(',') for ln in body.splitlines() if ln.strip()]
        desc = "\n".join(members)
        add_node(
            name=name,
            parent_body="",
            klass="SEQUENCE",
            syntax="SEQUENCE {...}",
            description=desc
        )

    # --- OBJECT-GROUP (has parent OID) ---
    for m in RE_OBJECT_GROUP.finditer(src):
        name = m.group("name"); body = m.group("body"); parent = m.group("parent")
        status = _extract_field(body, "STATUS")
        desc   = _extract_field(body, "DESCRIPTION")
        objs   = _extract_list_in_braces(body, "OBJECTS")
        syntax = f"OBJECTS {{ {', '.join(objs)} }}"
        add_node(
            name=name,
            parent_body=parent,
            klass=f"OBJECT-GROUP{(' ('+status+')' if status else '')}",
            syntax=syntax,
            description=desc
        )

    # --- MODULE-COMPLIANCE (has parent OID) ---
    for m in RE_MODULE_COMPLIANCE.finditer(src):
        name = m.group("name"); body = m.group("body"); parent = m.group("parent")
        status = _extract_field(body, "STATUS")
        desc   = _extract_field(body, "DESCRIPTION")
        mand   = _extract_list_in_braces(body, "MANDATORY-GROUPS")
        # Optional/variation OBJECT clauses are complex; capture their names roughly:
        opt_groups = _extract_list_in_braces(body, "GROUP")  # catches simple GROUP { x }
        syntax = "MANDATORY-GROUPS { " + ", ".join(mand) + " }"
        if opt_groups:
            syntax += f" ; GROUP {', '.join(opt_groups)}"
        add_node(
            name=name,
            parent_body=parent,
            klass=f"MODULE-COMPLIANCE{(' ('+status+')' if status else '')}",
            syntax=syntax,
            description=desc
        )

    # --- AGENT-CAPABILITIES (has parent OID) ---
    for m in RE_AGENT_CAPS.finditer(src):
        name = m.group("name"); body = m.group("body"); parent = m.group("parent")
        status = _extract_field(body, "STATUS")
        desc   = _extract_field(body, "DESCRIPTION")
        prod   = _extract_field(body, "PRODUCT-RELEASE")
        supports = [s.strip() for s in re.findall(r"\bSUPPORTS\s+([A-Za-z][\w\-]*)", body)]
        syntax = "; ".join(filter(None, [
            f"PRODUCT-RELEASE \"{prod}\"" if prod else "",
            f"SUPPORTS {', '.join(supports)}" if supports else ""
        ]))
        add_node(
            name=name,
            parent_body=parent,
            klass=f"AGENT-CAPABILITIES{(' ('+status+')' if status else '')}",
            syntax=syntax,
            description=desc
        )

    # NEW: parse IMPORTS and MODULE-IDENTITY (pretty/structured)
    imports_dict = parse_imports_block(src) or {}
    module_ident = parse_module_identity(src)



    return {
        "moduleName": module,
        "nodes": nodes,
        "imports": imports_dict,
        "moduleIdentity": module_ident,
         "meta": meta
    }

# ==========================
# Folder tree (for sidebar)
# ==========================
def _insert_to_tree(tree: dict, parts: List[str], module_name: str, relfile: str):
    cur = tree
    for d in parts:
        cur = cur.setdefault("_dirs", {}).setdefault(d, {})
    cur.setdefault("_mods", []).append((module_name, relfile))

def build_sidebar_tree(mod_to_path: Dict[str, str]) -> dict:
    tree: dict = {}
    for mod, rel in sorted(mod_to_path.items(), key=lambda kv: kv[1].lower()):
        rel_path = Path(rel)
        parts = list(rel_path.parent.parts)
        _insert_to_tree(tree, parts, mod, rel)
    return tree

def render_sidebar_html(tree: dict, prefix: str = "") -> str:
    def module_card(mod: str, relfile: str) -> str:
        safe_mod = html.escape(mod)
        safe_rel = html.escape(relfile)
        is_upload = relfile.startswith("Uploads/")
        confirm_msg = (
            f"Remove {mod}? " + ("This will delete the uploaded file." if is_upload else "(session unload)")
        )
        # Escape for HTML attribute/JS string
        confirm_attr = html.escape(confirm_msg, quote=True)
        return f"""
<div class="fs-file card small" title="{safe_rel}">
  <div class="row" style="align-items:center;">
    <strong>{safe_mod}</strong>
    <a class="badge" href="{url_for('module_view', module=mod)}">open</a>
    <form action="{url_for('remove_module', module=mod)}"
          method="post" style="margin-left:auto;"
          onsubmit="return confirm('{confirm_attr}')">
      <button class="icon-btn" title="Remove {safe_mod}" type="submit">✖</button>
    </form>
  </div>
  <div class="small muted">{safe_rel}</div>
</div>
"""

    def _dir_block(name: str, node: dict) -> str:
        subdirs = node.get("_dirs", {})
        mods = node.get("_mods", [])
        inner = ""
        # render subdirectories
        for sd_name, sd in sorted(subdirs.items(), key=lambda kv: kv[0].lower()):
            inner += _dir_block(sd_name, sd)
        # render module cards in this directory
        for mod, relfile in sorted(mods, key=lambda x: x[0].lower()):
            inner += module_card(mod, relfile)

        opened = " open" if prefix == "" else ""
        safe_name = html.escape(name)
        return f"""<details{opened}><summary><strong>{safe_name}</strong></summary>{inner}</details>"""

    html_out = ""
    # modules at the root
    root_mods = tree.get("_mods", [])
    for mod, relfile in sorted(root_mods, key=lambda x: x[0].lower()):
        html_out += module_card(mod, relfile)
    # top-level directories
    for top_name, node in sorted(tree.get("_dirs", {}).items(), key=lambda kv: kv[0].lower()):
        html_out += _dir_block(top_name, node)
    return html_out

# ==========================
# Tree render helpers
# ==========================
def build_tree(nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
    root: Dict[str, Any] = {}
    for n in nodes:
        oid = (n.get("oid") or "").strip()
        if not oid:
            root.setdefault("(no-oid)", {"__children__": {}, "__node__": None})
            b = root["(no-oid)"]; b["__node__"] = b.get("__node__") or n
            continue
        parts = [p for p in oid.split(".") if p]
        cur = root
        for i, seg in enumerate(parts):
            cur.setdefault(seg, {"__children__": {}, "__node__": None})
            if i == len(parts) - 1:
                cur[seg]["__node__"] = n
            cur = cur[seg]["__children__"]
    return root

def render_tree(tree: Dict[str, Any]) -> str:
    import html as _html

    def _sort_key(k: str):
        try:
            return (0, int(k))
        except Exception:
            return (1, k.lower())

    def _badge(klass: str) -> str:
        if not klass: return ""
        k = klass.upper()
        if "OBJECT-TYPE" in k:       return '<span class="badge type">OBJECT-TYPE</span>'
        if "OBJECT-IDENTITY" in k:   return '<span class="badge ident">OBJECT-IDENTITY</span>'
        if "NOTIFICATION" in k:      return '<span class="badge note">NOTIFICATION</span>'
        if "TEXTUAL-CONVENTION" in k:return '<span class="badge type">TEXTUAL-CONVENTION</span>'
        if "OBJECT IDENTIFIER" in k: return '<span class="badge">OID</span>'
        if "OBJECT-GROUP" in k:         return '<span class="badge type">OBJECT-GROUP</span>'
        if "MODULE-COMPLIANCE" in k:    return '<span class="badge type">MODULE-COMPLIANCE</span>'
        if "AGENT-CAPABILITIES" in k:   return '<span class="badge type">AGENT-CAPABILITIES</span>'
        if "SEQUENCE" in k:             return '<span class="badge ident">SEQUENCE</span>'
        return f'<span class="badge">{_html.escape(klass)}</span>'

    def _icon(klass: str) -> str:
        if not klass: return ""
        k = klass.upper()
        if "OBJECT-TYPE" in k:
            return '<svg width="12" height="12" viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="12" fill="none" stroke="currentColor"/></svg>'
        if "OBJECT-IDENTITY" in k:
            return '<svg width="12" height="12" viewBox="0 0 24 24"><circle cx="12" cy="12" r="5" fill="none" stroke="currentColor"/></svg>'
        if "NOTIFICATION" in k:
            return '<svg width="12" height="12" viewBox="0 0 24 24"><path d="M12 3v18M3 12h18" fill="none" stroke="currentColor"/></svg>'
        if "TEXTUAL-CONVENTION" in k:
            return '<svg width="12" height="12" viewBox="0 0 24 24"><path d="M4 6h16M4 12h16M4 18h10" fill="none" stroke="currentColor"/></svg>'
        return ""

    def _node_html(nodeDict: Dict[str, Any], label: str, path: str) -> str:
        n     = nodeDict.get("__node__")
        kids  = nodeDict.get("__children__", {})
        name  = (n and n.get("name")) or ""
        klass = (n and n.get("klass")) or ""
        syntax= (n and n.get("syntax")) or ""
        desc  = (n and n.get("description")) or ""
        oid   = (n and n.get("oid")) or ""
        sym_oid = (n and n.get("sym_oid")) or ""
        enums = (n and n.get("enums")) or []
        title = name or label

        inner = "".join(
            _node_html(v, k, f"{path}.{k}" if path else k)
            for k, v in sorted(kids.items(), key=lambda kv: _sort_key(kv[0]))
        )

        if not n:
            return f"""
<details data-path="{_html.escape(path or label, quote=True)}">
  <summary class="node" onclick="selectNode(event,this)">
    <span class="tw">▶️</span>
    <strong>{_html.escape(title)}</strong>
    <span class="badge">branch</span>
  </summary>
  {inner}
</details>
"""

        data_name  = _html.escape(title, quote=True)
        data_klass = _html.escape(klass or "", quote=True)
        data_syn   = _html.escape(syntax or "", quote=True)
        data_desc  = _html.escape(desc or "", quote=True)
        data_oid   = _html.escape(oid or "", quote=True)
        data_path  = _html.escape(path or label, quote=True)
        data_enums = _html.escape(json.dumps(enums), quote=True)
        data_sym   = _html.escape(sym_oid or "", quote=True)

        desc_html = f"<div class='small muted'>{_html.escape(desc).replace('\\n','<br>')}</div>" if desc else ""

        anchor_id = f'oid-{_html.escape(oid)}' if oid and re.fullmatch(r"\d+(?:\.\d+)+", oid) else ""

        return f"""
<details id="{anchor_id}" data-oid="{data_oid}" data-sym-oid="{data_sym}" data-name="{data_name}" data-klass="{data_klass}" data-syntax="{data_syn}" data-desc="{data_desc}" data-path="{data_path}" data-enums="{data_enums}">
  <summary class="node" onclick="selectNode(event,this)">
    <span class="tw">▶️</span>
    {_icon(klass)}
    <strong>{_html.escape(title)}</strong>
    {_badge(klass)}
    <span class="node-actions">
      <button class="icon-btn" type="button" onclick="expandChildren(event,this)">Expand</button>
      <button class="icon-btn" type="button" onclick="event.preventDefault(); event.stopPropagation(); copyText('{data_oid}')">Copy OID</button>
      <button class="icon-btn" type="button" onclick="event.preventDefault(); event.stopPropagation(); copyLink('{data_oid}')">Copy link</button>
      <button class="icon-btn" type="button" onclick="event.preventDefault(); event.stopPropagation(); copyText('{data_name}')">Copy name</button>
    </span>
  </summary>
  <div class="card small" onclick="selectNode(event,this)">
    <div class="kv">
      <div>OID</div>
      <div>{_html.escape(oid)}{(' <span class=\"muted\">(' + _html.escape(sym_oid) + ')</span>') if (sym_oid and sym_oid != oid) else ''}</div>
      <div>Class</div><div>{_html.escape(klass)}</div>
      <div>Syntax</div><div>{_html.escape(syntax)}</div>
    </div>
    {desc_html}
  </div>
  {inner}
</details>
"""

    return "".join(
        _node_html(v, k, k) for k, v in sorted(tree.items(), key=lambda kv: _sort_key(kv[0]))
    )

def flatten_nodes(mod_name: str, doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(doc, dict): return out
    node_map = doc.get("nodes") or {}
    for key, val in node_map.items():
        if not isinstance(val, dict): continue
        out.append({
          "module": mod_name,
          "name": val.get("name") or key,
          "oid": val.get("oid"),
          "sym_oid": val.get("sym_oid") or "",
          "klass": val.get("klass"),
          "syntax": val.get("syntax") or "",
          "description": (val.get("description") or "").strip(),
          "enums": val.get("enums") or []
      })
    def _oid_key(n):
        parts = []
        if n["oid"]:
            for p in str(n["oid"]).split("."):
                try: parts.append(int(p))
                except Exception: parts.append(10**9)
        return parts or [10**9]
    out.sort(key=lambda n: (_oid_key(n), n["name"] or ""))
    return out

# ==========================
# Discovery + Parse & Store
# ==========================
def discover_mib_files() -> List[Path]:
    files: List[Path] = []
    for p in BASE_DIR.rglob("*.mib"):
        try:
            if str(p).startswith(str(UPLOAD_DIR)):
                continue
            files.append(p)
        except Exception:
            pass
    return files

def parse_sources() -> List[str]:
    COMPILED.clear()
    MOD_TO_PATH.clear()

    discovered = discover_mib_files()
    for p in discovered:
        try:
            txt = p.read_text(errors="ignore")
        except Exception:
            continue
        doc = parse_mib_text(txt)
        mod = doc.get("moduleName") or p.stem
        COMPILED[mod] = {"doc": doc, "raw": txt}
        rel = str(p.relative_to(BASE_DIR))
        MOD_TO_PATH[mod] = rel

    for p in UPLOAD_DIR.iterdir():
        if not p.is_file():
            continue
        try:
            txt = p.read_text(errors="ignore")
        except Exception:
            continue
        doc = parse_mib_text(txt)
        mod = doc.get("moduleName") or p.stem
        COMPILED[mod] = {"doc": doc, "raw": txt}
        MOD_TO_PATH[mod] = f"Uploads/{p.name}"

    MODULE_EXPORTS.clear()
    for mod, entry in COMPILED.items():
        doc = entry["doc"]
        names = set()
        names.update((doc.get("nodes") or {}).keys())
        # textual conventions
        # We didn’t store TCs separately; they’re also in nodes thanks to the TC parser.
        # SEQUENCE names added too.
        MODULE_EXPORTS[mod] = names

    # Build reverse import index
    IMPORTED_BY.clear()
    for importer, entry in COMPILED.items():
        imps = (entry["doc"].get("imports") or {})
        for from_mod, syms in imps.items():
            if not syms: continue
            IMPORTED_BY.setdefault(from_mod, {}).setdefault(importer, [])
            # Only keep symbols that the exporter actually defines (nice UX)
            defined = MODULE_EXPORTS.get(from_mod, set())
            take = [s for s in syms if (s in defined) or not defined]  # if unknown, still show
            IMPORTED_BY[from_mod][importer].extend(take)

    mods = sorted(COMPILED.keys())
    print(f"[MIB Browser] Parsed modules: {mods or 'NONE'} (auto={len(discovered)} uploads={len(list(UPLOAD_DIR.iterdir()))})")
    return mods

def build_modlist_html() -> str:
    tree = build_sidebar_tree(MOD_TO_PATH)
    uploads: List[Tuple[str,str]] = [(m, rel) for m, rel in MOD_TO_PATH.items() if rel.startswith("Uploads/")]
    html_parts: List[str] = []
    main_tree_html = render_sidebar_html(tree)
    if main_tree_html.strip():
        html_parts.append(main_tree_html)
    if uploads:
        up_tree: dict = {"_mods": [], "_dirs": {}}
        for m, rel in uploads:
            _insert_to_tree(up_tree, ["Uploads"], m, rel)
        html_parts.append(render_sidebar_html(up_tree))
    return "\n".join(html_parts) or "<p class='muted'>No MIBs found.</p>"

# ==========================
# Search
# ==========================
def search_all(term: str) -> List[Dict[str, Any]]:
    term = (term or "").strip().lower()
    if not term: return []
    hits: List[Dict[str, Any]] = []
    for mod, entry in COMPILED.items():
        for n in flatten_nodes(mod, entry["doc"]):
            hay = " ".join([
              n.get("module",""), n.get("name",""),
              str(n.get("oid","") or ""),
              n.get("sym_oid","") or "",
              n.get("klass","") or "",
              n.get("syntax","") or "",
              n.get("description","") or ""
          ]).lower()
            if term in hay:
                hits.append(n)
            if len(hits) >= 200:
                break
    return hits

# ==========================
# Routes
# ==========================
@app.route("/")
def index():
    return render_template_string(
        app.jinja_loader.get_source(app.jinja_env, "home.html")[0],
        modules=sorted(COMPILED.keys()),
        modlist_html=build_modlist_html()
    )

@app.route("/module/<module>")
def module_view(module: str):
    entry = COMPILED.get(module)
    if not entry:
        return redirect(url_for("index"))
    nodes = flatten_nodes(module, entry["doc"])
    tree = build_tree(nodes)
    tree_html = render_tree(tree)
    used_by = IMPORTED_BY.get(module, {})
    defines_list = sorted(MODULE_EXPORTS.get(module, set()))
    return render_template_string(
        app.jinja_loader.get_source(app.jinja_env, "module.html")[0],
        module=module,
        nodes=nodes,
        tree_html=tree_html,
        modules=sorted(COMPILED.keys()),
        modlist_html=build_modlist_html(),
        imports=entry["doc"].get("imports", {}),
        module_identity=entry["doc"].get("moduleIdentity"),
        used_by=used_by,
        defines_list=defines_list,
    )

@app.route("/upload", methods=["POST"])
def upload():
    files = request.files.getlist("files")
    if files:
        for f in files:
            if not f.filename:
                continue
            dest = UPLOAD_DIR / Path(f.filename).name
            f.save(dest)
        parse_sources()
    return redirect(url_for("index"))

@app.route("/remove/<module>", methods=["POST"])
def remove_module(module: str):
    rel = MOD_TO_PATH.get(module)
    if not rel:
        return redirect(url_for("index"))

    # If it's an uploaded file, delete it from disk and fully re-parse sources.
    if rel.startswith("Uploads/"):
        try:
            (UPLOAD_DIR / rel.split("/", 1)[1]).unlink(missing_ok=True)
        except Exception:
            pass
        parse_sources()  # rebuild everything from disk
        return redirect(url_for("index"))

    # Otherwise (auto-discovered on disk), just unload for this session.
    # Don’t call parse_sources(), or it will re-discover it.
    COMPILED.pop(module, None)
    MOD_TO_PATH.pop(module, None)

    # Rebuild in-memory indexes (exports / imported-by) after removal.
    MODULE_EXPORTS.clear()
    for mod, entry in COMPILED.items():
        names = set((entry["doc"].get("nodes") or {}).keys())
        MODULE_EXPORTS[mod] = names

    IMPORTED_BY.clear()
    for importer, entry in COMPILED.items():
        imps = (entry["doc"].get("imports") or {})
        for from_mod, syms in imps.items():
            if not syms:
                continue
            IMPORTED_BY.setdefault(from_mod, {}).setdefault(importer, [])
            defined = MODULE_EXPORTS.get(from_mod, set())
            take = [s for s in syms if (s in defined) or not defined]
            IMPORTED_BY[from_mod][importer].extend(take)

    return redirect(url_for("index"))


@app.route("/clear", methods=["POST"])
def clear_all():
    _purge_dir(UPLOAD_DIR)
    parse_sources()
    return """
    <script>
      localStorage.clear();
      window.location = "/";
    </script>
    """

@app.route("/api/search")
def api_search():
    q = request.args.get("q","")
    hits = search_all(q)
    return jsonify({"results": hits})


# ==========================
# Main
# ==========================
if __name__ == "__main__":
    parse_sources()
    app.run(host="0.0.0.0", port=8000, debug=True)
