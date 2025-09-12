#!/usr/bin/env python3
"""
Single-file Web MIB Browser — no PySMI/PySNMP compile needed.
- Only dependency: Flask (pip install Flask)
- Parses textual MIBs (.mib/.txt) directly with a best-effort SMIv2 parser
- Builds a browsable OID tree (supports numeric + symbolic segments)
- Full-text search on name / OID / type / description
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
BASE_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Web MIB Browser (no-compile)</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    :root { color-scheme: light dark; }
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; margin: 0; }
    header {
      position: sticky; top: 0; z-index: 1000; background: #fff;
      padding: 12px 16px; border-bottom: 1px solid #ddd;
      display:flex; gap:12px; align-items:center; flex-wrap:wrap;
    }
    @media (prefers-color-scheme: dark) { header { background: #111; } }
    h1 { font-size: 18px; margin: 0; white-space: nowrap; }

    /* Two-column layout */
    main { display: grid; grid-template-columns: 320px 1fr; align-items: start; }
    aside { padding: 12px; }
    section { padding: 12px; }

    .card { border: 1px solid #eee; border-radius: 10px; padding: 10px 12px; margin: 8px 0; }
    .muted { color: #666; }
    input[type="text"], input[type="file"] { padding: 8px; border-radius: 8px; border:1px solid #ccc; }
    input[type="text"] { width: 100%; }
    .row { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
    .btn { padding: 6px 10px; border-radius: 8px; border:1px solid #bbb; background:#f7f7f7; cursor:pointer; color:#000; }
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

    /* Class badges */
    .badge { display:inline-block; padding:2px 8px; border-radius: 999px; font-size: 11px; border:1px solid transparent; }
    .badge.type  { background:#eef6ff; border-color:#cfe5ff; color:#000; }
    .badge.ident { background:#eefaf0; border-color:#caefda; }
    .badge.note  { background:#fff6e5; border-color:#ffe3b5; }

    /* Inspector panel (right side) */
    #inspector { position: static; border:1px solid #eee; border-radius: 10px; padding: 10px 12px; }
    #inspector.pinned { position: sticky; top: 70px; }
    .breadcrumb { font-size:12px; color:#666; margin-bottom:8px; word-break:break-all; }
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
  <aside>
    <h3 class="muted">Modules</h3>
    {% if not modules %}
      <p class="muted">No MIBs parsed yet. Upload your .mib/.txt files.</p>
    {% endif %}
    <div>
      {% for m in modules %}
        <div class="card">
          <div class="row">
            <strong>{{ m }}</strong>
            <a class="badge" href="{{ url_for('module_view', module=m) }}">open</a>
          </div>
        </div>
      {% endfor %}
    </div>


  </aside>

  <section>
    {% block content %}{% endblock %}
  </section>
</main>

<script>
// ---- make helpers & actions GLOBAL (needed for inline handlers) ----
window.escHtml = function(s){
  return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
};
window.escAttr = function(s){ return window.escHtml(String(s ?? '')); };

window.highlight = function(term, rootId){
  const el = document.getElementById(rootId || 'content');
  if(!el || !term) return;
  const rx = new RegExp(`(${term.replace(/[.*+?^${}()|[\\]\\\\]/g,'\\\\$&')})`,'gi');
  el.querySelectorAll('.card, summary, .kv, .small').forEach(node=>{
    if(node.childElementCount === 0){
      node.innerHTML = node.textContent.replace(rx,'<mark>$1</mark>');
    }
  });
};

// Inspector utilities
window.setInspector = function({name='', oid='', klass='', syntax='', desc='', path=''}){
  const byId = id => document.getElementById(id);
  // If inspector is not present (home page), silently no-op
  if(!byId('i_name')) return;
  byId('i_name').textContent   = name;
  byId('i_oid').textContent    = oid;
  byId('i_class').textContent  = klass;
  byId('i_syntax').textContent = syntax;
  byId('i_desc').innerHTML     = (desc || '').replace(/\\n/g,'<br>');
  byId('crumb').textContent    = path;
  byId('inspector')?.scrollIntoView({ block:'nearest', behavior:'smooth' });
};
window.inspectSearchResult = function(card){
  const d = card.dataset;
  window.setInspector({
    name:  d.name,
    oid:   d.oid,
    klass: d.klass,
    syntax:d.syntax,
    desc:  d.desc,
    path:  d.path
  });
};

// Search
window.doSearch = async function(e){
  if(e){ e.preventDefault(); }
  const q = document.getElementById('q').value.trim();
  if(!q){ return; }

  const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
  const data = await res.json();

  // Prefer main column on module page; fallback to #content (home)
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
           data-klass="${window.escAttr(n.klass || '')}"
           data-syntax="${window.escAttr(n.syntax || '')}"
           data-desc="${window.escAttr(n.description || '')}"
           data-path="${window.escAttr(n.oid || n.name || '')}">
        <div class="row">
          <strong>${(n.name || '(unnamed)')}</strong>
          <span class="badge">${n.klass || ''}</span>
          <span class="badge">${n.syntax || ''}</span>
        </div>
        <div class="kv small">
          <div>Module</div><div>${n.module}</div>
          <div>OID</div><div>${n.oid || ''}</div>
        </div>
        <div class="small muted">${(n.description || '').replace(/\\n/g,'<br>')}</div>
      </div>
    `).join('');
  }
  container.innerHTML = html;
  window.highlight(q, container.id);
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
  window.setInspector({
    name:   det.dataset.name  || '',
    oid:    det.dataset.oid   || '',
    klass:  det.dataset.class || '',
    syntax: det.dataset.syntax|| '',
    desc:   det.dataset.desc  || '',
    path:   det.dataset.path  || ''
  });
};

console.log('[MIB Browser] client script loaded');
</script>
</body>
</html>
"""

HOME_HTML = """
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

MODULE_HTML = """
{% extends "base.html" %}
{% block content %}
  <!-- On module pages, #content becomes a 2-col grid: left main column + right inspector -->
  <div id="content" style="display:grid; grid-template-columns: 2fr 1fr; gap:16px;">
    <div id="maincol">
      <h2>{{ module }}</h2>
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
          <div>OID</div><div id="i_oid" class="mono"></div>
          <div>Class</div><div id="i_class"></div>
          <div>Syntax</div><div id="i_syntax"></div>
          <div>Module</div><div id="i_module">{{ module }}</div>
        </div>
        <div class="small muted" id="i_desc" style="margin-top:8px;"></div>
        <div style="margin-top:8px;">
          <button class="btn" type="button" onclick="copyText(document.getElementById('i_oid').textContent)">Copy OID</button>
          <button class="btn" type="button" onclick="copyText(document.getElementById('i_name').textContent)">Copy name</button>
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

# Start clean
_purge_dir(UPLOAD_DIR)

# { moduleName: {"doc": {"moduleName":..., "nodes": {...}}, "raw": <text>} }
COMPILED: Dict[str, Dict[str, Any]] = {}

# ==========================
# Parser (best-effort SMIv2)
# ==========================
BASE_OIDS: Dict[str, str] = {
    "ccitt": "0", "iso": "1", "joint-iso-ccitt": "2", "org": "1.3",
    "dod": "1.3.6", "internet": "1.3.6.1", "directory": "1.3.6.1.1",
    "mgmt": "1.3.6.1.2", "mib-2": "1.3.6.1.2.1", "experimental": "1.3.6.1.3",
    "private": "1.3.6.1.4", "enterprises": "1.3.6.1.4.1", "snmpV2": "1.3.6.1.6",
}

RE_HEADER       = re.compile(r"^\s*([A-Za-z][A-Za-z0-9\-._]*)\s+DEFINITIONS\s*::=\s*BEGIN", re.M)
RE_LINE_COMMENT = re.compile(r"--[^\n]*")
RE_QUOTED       = re.compile(r'"([^"]*)"')
RE_OID_ASSIGN   = re.compile(r"(?m)^\s*(?P<name>[A-Za-z][\w\-]*)\s+OBJECT\s+IDENTIFIER\s*::=\s*\{(?P<body>[^}]*)\}")
RE_OBJTYPE      = re.compile(r"(?ms)^\s*(?P<name>[A-Za-z][\w\-]*)\s+OBJECT-TYPE\s+(?P<body>.*?)::=\s*\{(?P<parent>[^}]*)\}")
RE_OBJIDENTITY  = re.compile(r"(?ms)^\s*(?P<name>[A-Za-z][\w\-]*)\s+OBJECT-IDENTITY\s+(?P<body>.*?)::=\s*\{(?P<parent>[^}]*)\}")
RE_NOTIFICATION = re.compile(r"(?ms)^\s*(?P<name>[A-Za-z][\w\-]*)\s+NOTIFICATION-TYPE\s+(?P<body>.*?)::=\s*\{(?P<parent>[^}]*)\}")

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
    """
    Resolve `{ parent arcs... }` into a dotted OID.
    - Uses BASE_OIDS and sym2oid for known names
    - Keeps symbolic segments if numeric parents are unknown
    """
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

    # Parent may be dotted numeric, pure number, known base, or known symbol
    if re.fullmatch(r"\d+(?:\.\d+)+", parent_tok):
        path = parent_tok.split(".")
    elif parent_tok.isdigit():
        path = [parent_tok]
    else:
        base = sym2oid.get(parent_tok) or BASE_OIDS.get(parent_tok)
        path = base.split(".") if base else [parent_tok]

    # Remaining arcs
    for tok in tokens[1:]:
        name, num = _parse_arc_token(tok)
        if name.isdigit():
            path.append(name)
        elif re.fullmatch(r"\d+(?:\.\d+)+", name):
            path.extend(name.split("."))
        elif num is not None:
            path.append(str(num))   # name(number) → append number
        else:
            path.append(name)       # unknown symbol → keep symbolic
    return ".".join([str(x) for x in path if str(x) != ""])

def _extract_field(block: str, key: str) -> str:
    # Find e.g. SYNTAX / STATUS / DESCRIPTION inside an OBJECT-* body.
    # Stop at the next ALL-CAPS token on a new line, or '::=', or end-of-string.
    m = re.search(rf"\b{key}\b\s+(.*?)(?:\n[A-Z\-]+\b|::=|\Z)", block, re.S)
    if not m:
        return ""
    val = m.group(1).strip()
    if key == "DESCRIPTION":
        # take the first quoted chunk, multi-line safe
        mq = re.search(r'"(.*?)"', val, re.S)
        if mq:
            return mq.group(1).strip()
    return " ".join(val.split())

def parse_mib_text(text: str) -> Dict[str, Any]:
    src = strip_comments(text)
    module = find_module_name(src) or "(unknown-module)"

    sym2oid: Dict[str, str] = {}
    for m in RE_OID_ASSIGN.finditer(src):
        name = m.group("name"); body = m.group("body")
        oid = _resolve_braced_oid(body, sym2oid)
        if oid: sym2oid[name] = oid

    nodes: Dict[str, Dict[str, Any]] = {}
    def add_node(name: str, parent_body: str, klass: str, syntax: str, description: str):
        oid = _resolve_braced_oid(parent_body, sym2oid)
        nodes[name] = {"name": name, "oid": oid, "klass": klass, "syntax": syntax, "description": description.strip()}

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
        nodes.setdefault(name, {"name": name, "oid": oid, "klass": "OBJECT IDENTIFIER", "syntax": "", "description": ""})

    return {"moduleName": module, "nodes": nodes}

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
        if not klass:
            return ""
        k = klass.upper()
        if "OBJECT-TYPE" in k:       return '<span class="badge type">OBJECT-TYPE</span>'
        if "OBJECT-IDENTITY" in k:   return '<span class="badge ident">OBJECT-IDENTITY</span>'
        if "NOTIFICATION" in k:      return '<span class="badge note">NOTIFICATION</span>'
        if "OBJECT IDENTIFIER" in k: return '<span class="badge">OID</span>'
        return f'<span class="badge">{_html.escape(klass)}</span>'

    def _icon(klass: str) -> str:
        if not klass:
            return ""
        k = klass.upper()
        if "OBJECT-TYPE" in k:
            return '<svg width="12" height="12" viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="12" fill="none" stroke="currentColor"/></svg>'
        if "OBJECT-IDENTITY" in k:
            return '<svg width="12" height="12" viewBox="0 0 24 24"><circle cx="12" cy="12" r="5" fill="none" stroke="currentColor"/></svg>'
        if "NOTIFICATION" in k:
            return '<svg width="12" height="12" viewBox="0 0 24 24"><path d="M12 3v18M3 12h18" fill="none" stroke="currentColor"/></svg>'
        return ""

    def _node_html(nodeDict: Dict[str, Any], label: str, path: str) -> str:
        n     = nodeDict.get("__node__")
        kids  = nodeDict.get("__children__", {})
        name  = (n and n.get("name")) or ""              # real name only if a node exists
        klass = (n and n.get("klass")) or ""
        syntax= (n and n.get("syntax")) or ""
        desc  = (n and n.get("description")) or ""
        oid   = (n and n.get("oid")) or ""
        title = name or label                             # show numeric/symbolic arc when no node

        # Render children first (so we can decide markup knowing kids exist)
        inner = "".join(
            _node_html(v, k, f"{path}.{k}" if path else k)
            for k, v in sorted(kids.items(), key=lambda kv: _sort_key(kv[0]))
        )

        if not n:
            # BRANCH-ONLY NODE (no MIB object bound here) -> compact row, no details card
            return f"""
<details data-path="{_html.escape(path or label, quote=True)}">
  <summary class="node" onclick="selectNode(event,this)">
    <span class="tw">▶</span>
    <strong>{_html.escape(title)}</strong>
    <span class="badge">branch</span>
  </summary>
  {inner}
</details>
"""

        # REAL NODE (has data) -> full card + actions, description, etc.
        data_name = _html.escape(title, quote=True)
        data_class= _html.escape(klass or "", quote=True)
        data_syn  = _html.escape(syntax or "", quote=True)
        data_desc = _html.escape(desc or "", quote=True)
        data_oid  = _html.escape(oid or "", quote=True)
        data_path = _html.escape(path or label, quote=True)

        desc_html = f"<div class='small muted'>{_html.escape(desc).replace('\\n','<br>')}</div>" if desc else ""

        return f"""
<details data-oid="{data_oid}" data-name="{data_name}" data-class="{data_class}" data-syntax="{data_syn}" data-desc="{data_desc}" data-path="{data_path}">
  <summary class="node" onclick="selectNode(event,this)">
    <span class="tw">▶</span>
    {_icon(klass)}
    <strong>{_html.escape(title)}</strong>
    {_badge(klass)}
    <span class="node-actions">
      <button class="icon-btn" type="button" onclick="expandChildren(event,this)">Expand</button>
      <button class="icon-btn" type="button" onclick="event.preventDefault(); event.stopPropagation(); copyText('{data_oid}')">Copy OID</button>
      <button class="icon-btn" type="button" onclick="event.preventDefault(); event.stopPropagation(); copyText('{data_name}')">Copy name</button>
    </span>
  </summary>
  <div class="card small" onclick="selectNode(event,this)">
    <div class="kv">
      <div>OID</div><div>{_html.escape(oid)}</div>
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
            "klass": val.get("klass"),
            "syntax": val.get("syntax") or "",
            "description": (val.get("description") or "").strip()
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
# Parse & Store
# ==========================
UPLOAD_DIR = Path(tempfile.gettempdir()) / "web_mib_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

def _purge_dir(d: Path):
    try:
        for p in d.iterdir():
            if p.is_file():
                try: p.unlink()
                except Exception: pass
    except Exception: pass

_purge_dir(UPLOAD_DIR)

COMPILED: Dict[str, Dict[str, Any]] = {}

def parse_all_mibs() -> List[str]:
    COMPILED.clear()
    src_files = [p for p in UPLOAD_DIR.iterdir() if p.is_file()]
    mods: List[str] = []
    for p in src_files:
        try:
            txt = p.read_text(errors="ignore")
        except Exception:
            continue
        doc = parse_mib_text(txt)
        mod = doc.get("moduleName") or p.stem
        COMPILED[mod] = {"doc": doc, "raw": txt}
        mods.append(mod)
    mods = sorted(set(mods))
    print(f"[MIB Browser] Parsed modules: {mods or 'NONE'} (files={len(src_files)})")
    return mods

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
        modules=sorted(COMPILED.keys())
    )

@app.route("/module/<module>")
def module_view(module: str):
    entry = COMPILED.get(module)
    if not entry:
        return redirect(url_for("index"))
    nodes = flatten_nodes(module, entry["doc"])
    tree = build_tree(nodes)
    tree_html = render_tree(tree)
    return render_template_string(
        app.jinja_loader.get_source(app.jinja_env, "module.html")[0],
        module=module,
        nodes=nodes,
        tree_html=tree_html,
        modules=sorted(COMPILED.keys())
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
        parse_all_mibs()
    return redirect(url_for("index"))

@app.route("/clear", methods=["POST"])
def clear_all():
    COMPILED.clear()
    _purge_dir(UPLOAD_DIR)
    return redirect(url_for("index"))

@app.route("/api/search")
def api_search():
    q = request.args.get("q","")
    hits = search_all(q)
    return jsonify({"results": hits})


# ==========================
# Main
# ==========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
