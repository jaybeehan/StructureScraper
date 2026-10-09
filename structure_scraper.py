"""Structure Scraper - browser-based port of MatlabOriginal/StructureScraperGUI.m

Run via run.bat. Starts a local web server (stdlib only), opens the browser,
and lets you drag and drop Vision protocol *.xml files (or folders) onto the page.
"""
import json
import os
import re
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = "v2026-10-09_web"
PROTOCOL_DIR = r"\\nsfsvc100.healthy.bewell.ca\AHS_MedPhys_NVarData$\ProgramData\Vision\templates\protocol"

STRUCT_RE = re.compile(r"<Structure(?=\s|>)[\s\S]*?</Structure>")
PREVIEW_RE = re.compile(r'<Preview[\s\S]*?ID="([^"]+)"')
OPEN_TAG_RE = re.compile(r"^<Structure[^>]*>")


def extract_attr(block, name):
    tag = OPEN_TAG_RE.match(block)
    if not tag:
        return ""
    m = re.search(name + r'="([^"]*)"', tag.group(0))
    return m.group(1) if m else ""


def pretty_xml_fragment(xml, indent_spaces=2):
    s = xml.replace("\r\n", "\n").replace("\r", "\n")
    if not s:
        return ""
    s = re.sub(r">\s*<", ">\n<", s)
    indent = 0
    out = []
    for part in s.split("\n"):
        line = part.strip()
        if not line:
            continue
        is_close = line.startswith("</")
        is_decl = line.startswith("<?") or line.startswith("<!")
        is_self = line.endswith("/>") or (not is_close and "</" in line)
        if is_close:
            indent = max(indent - 1, 0)
        out.append(" " * (indent_spaces * indent) + line)
        if line.startswith("<") and not is_close and not is_decl and not is_self:
            indent += 1
    return "\n".join(out)


def scrape(files):
    """files: list of {name, text}. Returns dict with structures and per-file stats."""
    structs, stats = [], []
    for f in files:
        txt = f.get("text", "")
        name = f.get("name", "")
        m = PREVIEW_RE.search(txt)
        preview_id = m.group(1) if m else ""
        blocks = STRUCT_RE.findall(txt)
        for i, block in enumerate(blocks, 1):
            structs.append({
                "id": extract_attr(block, "ID"),
                "name": extract_attr(block, "Name"),
                "previewID": preview_id,
                "file": name,
                "indexInFile": i,
                "pretty": pretty_xml_fragment(block),
            })
        stats.append({"file": name, "previewID": preview_id, "structures": len(blocks)})
    return {"structures": structs, "files": stats}


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Structure Scraper</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root { --bg:#f5f6f8; --fg:#1d2330; --muted:#667085; --card:#fff; --line:#d5d9e0; --accent:#2b6cb0; --accent-fg:#fff; --drop:#e8f1fb; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#14171d; --fg:#e6e8ec; --muted:#9aa3b2; --card:#1c2029; --line:#323846; --accent:#5b9bd5; --accent-fg:#0b1118; --drop:#1d2b3c; }
  }
  * { box-sizing:border-box; }
  body { margin:0; font:14px/1.4 "Segoe UI",system-ui,sans-serif; background:var(--bg); color:var(--fg); height:100vh; display:flex; flex-direction:column; padding:16px; gap:12px; }
  header { display:flex; flex-wrap:wrap; align-items:center; gap:12px; justify-content:space-between; }
  h1 { font-size:18px; margin:0; } h1 small { color:var(--muted); font-weight:normal; font-size:12px; }
  button, .btn { font:inherit; padding:6px 12px; border:1px solid var(--line); background:var(--card); color:var(--fg); border-radius:6px; cursor:pointer; }
  button.primary { background:var(--accent); color:var(--accent-fg); border-color:var(--accent); }
  button:disabled { opacity:.45; cursor:default; }
  #drop { border:2px dashed var(--line); border-radius:10px; padding:16px; text-align:center; background:var(--card); color:var(--muted); transition:.15s; }
  #drop.over { background:var(--drop); border-color:var(--accent); color:var(--fg); }
  .row { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
  input[type=text] { font:inherit; padding:6px 8px; border:1px solid var(--line); border-radius:6px; background:var(--card); color:var(--fg); width:320px; max-width:100%; }
  main { flex:1; min-height:0; display:grid; grid-template-columns:minmax(260px,1fr) minmax(300px,1.4fr); gap:12px; }
  @media (max-width:800px) { main { grid-template-columns:1fr; grid-auto-rows:minmax(200px,1fr); } }
  .pane { background:var(--card); border:1px solid var(--line); border-radius:8px; display:flex; flex-direction:column; min-height:0; }
  .pane h2 { font-size:13px; margin:0; padding:8px 12px; border-bottom:1px solid var(--line); color:var(--muted); font-weight:600; }
  #list { overflow:auto; flex:1; }
  .item { padding:5px 12px; cursor:pointer; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .item:hover { background:var(--drop); } .item.sel { background:var(--accent); color:var(--accent-fg); }
  #block { flex:1; margin:0; padding:10px 12px; overflow:auto; font:12.5px/1.45 Consolas,"Courier New",monospace; white-space:pre; }
  #status { color:var(--muted); font-size:12px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .unc { font:12px Consolas,monospace; color:var(--muted); }
</style></head>
<body>
<header>
  <h1>Structure Scraper <small>__VERSION__</small></h1>
  <div class="row">
    <span class="unc" id="unc"></span>
    <button id="openProto" title="Opens this folder in Windows Explorer">Open Vision protocol folder</button>
    <button id="copyPath">Copy path</button>
  </div>
</header>

<div id="drop">
  <strong>Drag &amp; drop</strong> Protocol *.xml files (or a folder) here, or
  <button id="pick" class="primary">Choose files…</button>
  <input type="file" id="fileInput" accept=".xml" multiple hidden>
</div>

<div class="row">
  <label>Search Structure ID (partial match):</label>
  <input type="text" id="q" autocomplete="off">
  <label><input type="checkbox" id="cs"> Case-sensitive</label>
</div>

<main>
  <section class="pane"><h2 id="listHdr">Matches</h2><div id="list"></div></section>
  <section class="pane">
    <h2 class="row" style="justify-content:space-between">
      <span>Selected &lt;Structure&gt; block (pretty)</span>
      <span class="row"><button id="copy" disabled>Copy</button><button id="save" disabled>Save…</button></span>
    </h2>
    <pre id="block"></pre>
  </section>
</main>
<div id="status">Status: idle</div>

<script>
const $ = id => document.getElementById(id);
const PROTO = __PROTO__;
let all = [], shown = [], sel = -1;
$('unc').textContent = PROTO;
const status = m => $('status').textContent = 'Status: ' + m;

// ---- file intake ----
async function readEntry(entry, out) {
  if (entry.isFile) {
    if (/\.xml$/i.test(entry.name)) {
      const file = await new Promise((ok, no) => entry.file(ok, no));
      out.push(file);
    }
  } else if (entry.isDirectory) {
    const rd = entry.createReader();
    let batch;
    do {
      batch = await new Promise((ok, no) => rd.readEntries(ok, no));
      for (const e of batch) await readEntry(e, out);
    } while (batch.length);
  }
}
const drop = $('drop');
['dragenter','dragover'].forEach(t => document.addEventListener(t, e => { e.preventDefault(); drop.classList.add('over'); }));
['dragleave','drop'].forEach(t => document.addEventListener(t, e => { e.preventDefault(); if (t==='drop' || !e.relatedTarget) drop.classList.remove('over'); }));
document.addEventListener('drop', async e => {
  const files = [];
  const items = [...(e.dataTransfer.items || [])];
  if (items.length && items[0].webkitGetAsEntry) {
    const entries = items.map(i => i.webkitGetAsEntry()).filter(Boolean);
    for (const en of entries) await readEntry(en, files);
  } else {
    files.push(...[...e.dataTransfer.files].filter(f => /\.xml$/i.test(f.name)));
  }
  load(files);
});
$('pick').onclick = () => $('fileInput').click();
$('fileInput').onchange = e => { load([...e.target.files]); e.target.value = ''; };

async function load(files) {
  if (!files.length) { status('no *.xml files found.'); return; }
  status('scraping ' + files.length + ' files...');
  const payload = [];
  for (const f of files) payload.push({ name: f.name, text: await f.text() });
  const r = await fetch('/api/scrape', { method:'POST', body: JSON.stringify({ files: payload }) });
  const d = await r.json();
  all = d.structures;
  $('q').value = '';
  filter();
  const withS = d.files.filter(f => f.structures).length;
  status(`scraped ${all.length} structures from ${withS} of ${d.files.length} files.`);
}

// ---- list / filter ----
function filter() {
  const q = $('q').value, cs = $('cs').checked;
  shown = !q ? all : all.filter(s => cs ? s.id.includes(q) : s.id.toLowerCase().includes(q.toLowerCase()));
  $('listHdr').textContent = `Matches (${shown.length})`;
  const list = $('list'); list.textContent = '';
  if (!shown.length) {
    const d = document.createElement('div'); d.className = 'item'; d.textContent = all.length ? '(no matches)' : '(drop files to begin)';
    list.append(d);
  }
  shown.forEach((s, i) => {
    const d = document.createElement('div'); d.className = 'item';
    d.textContent = s.id + ' - ' + (s.previewID || 'UNKNOWN_PREVIEW');
    d.title = s.file;
    d.onclick = () => select(i);
    list.append(d);
  });
  select(shown.length ? 0 : -1);
}
function select(i) {
  sel = i;
  [...$('list').children].forEach((c, k) => c.classList.toggle('sel', k === i));
  $('block').textContent = i >= 0 ? shown[i].pretty : '';
  $('copy').disabled = $('save').disabled = i < 0;
}
$('q').oninput = $('cs').onchange = filter;

// ---- copy / save ----
async function clip(text) {
  try { await navigator.clipboard.writeText(text); }
  catch { const t = document.createElement('textarea'); t.value = text; document.body.append(t); t.select(); document.execCommand('copy'); t.remove(); }
}
$('copy').onclick = async () => { await clip(shown[sel].pretty); status('copied selected block (pretty).'); };
$('save').onclick = () => {
  const s = shown[sel], safe = x => (x || 'NA').replace(/[^\w\-]+/g, '_');
  const name = `Structure_${safe(s.id)}_${safe(s.previewID)}_${all.indexOf(s) + 1}.xml`;
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([s.pretty], { type:'application/xml' }));
  a.download = name; a.click(); URL.revokeObjectURL(a.href);
  status('saved ' + name);
};

// ---- protocol folder ----
$('openProto').onclick = async () => {
  const r = await fetch('/api/open-protocol-folder', { method:'POST' });
  const d = await r.json();
  status(d.ok ? 'opened protocol folder in Explorer.' : 'could not open folder: ' + d.error);
};
$('copyPath').onclick = async () => { await clip(PROTO); status('copied protocol folder path.'); };

filter();
</script></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        data and self.wfile.write(data)

    def _local_origin_ok(self):
        # Guard against other web pages POSTing to this local server.
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        if not re.match(r"^(127\.0\.0\.1|localhost)(:\d+)?$", host):
            return False
        return origin is None or re.match(r"^http://(127\.0\.0\.1|localhost)(:\d+)?$", origin) is not None

    def do_GET(self):
        if self.path.split("?")[0] in ("/", "/index.html") and self._local_origin_ok():
            page = PAGE.replace("__VERSION__", VERSION).replace("__PROTO__", json.dumps(PROTOCOL_DIR))
            self._send(200, page, "text/html; charset=utf-8")
        else:
            self._send(404, "Not found", "text/plain")

    def do_POST(self):
        if not self._local_origin_ok():
            self._send(403, "Forbidden", "text/plain")
            return
        if self.path == "/api/scrape":
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n).decode("utf-8"))
            self._send(200, json.dumps(scrape(req.get("files", []))), "application/json")
        elif self.path == "/api/open-protocol-folder":
            try:
                os.startfile(PROTOCOL_DIR)  # Windows only; fixed path, no user input
                res = {"ok": True}
            except Exception as e:
                res = {"ok": False, "error": str(e)}
            self._send(200, json.dumps(res), "application/json")
        else:
            self._send(404, "Not found", "text/plain")


def main():
    port = 8765
    while True:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                break
        port += 1
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Structure Scraper {VERSION}\nRunning at {url}\nClose this window to stop.")
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
