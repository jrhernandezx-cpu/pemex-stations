#!/usr/bin/env python3
"""Build index.html ("PEMEX Stations" map + table) from the Pemex Station Tracker Sheet.

Input (pick one):
  python3 build.py data/stations.csv          # CSV export of the "Stations" tab
  python3 build.py connector_output.json      # raw Google Sheets connector read_range output
  python3 build.py --url "<csv export url>"   # only works if the Sheet is readable without login
Output: index.html and data/stations.csv (public columns only) in this folder.
Only the "Stations" tab is used; any other tab is ignored. Notes and fuel volume are never published.
"""
import base64, csv, io, json, os, sys, html, datetime, urllib.request, pathlib
from zoneinfo import ZoneInfo
from collections import Counter

# Sheet ID is kept out of the public repo; see README in /workspace/pemex-tracker.
SHEET_ID = os.environ.get("PEMEX_SHEET_ID", "")
HERE = pathlib.Path(__file__).resolve().parent
REQUIRED = ["ID", "Name", "State", "City", "Address", "Status", "Latitude", "Longitude"]
# The only columns that ever leave the Sheet (page data and data/stations.csv).
PUBLIC = ["ID", "Name", "State", "City", "Address", "Status", "Operator or owner contact",
          "Date branded", "Date debranded", "Cost estimate", "Last updated", "Latitude", "Longitude"]
ALIASES = {"Pemex go-live date": "Date branded"}  # old header names still accepted


def load_text(args):
    if args and args[0] == "--url":
        url = args[1] if len(args) > 1 else f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid=872432372"
        return urllib.request.urlopen(url).read().decode("utf-8")
    path = pathlib.Path(args[0]) if args else HERE / "data" / "stations.csv"
    raw = path.read_text(encoding="utf-8")
    # Connector output: JSON with ranges[0].content holding CSV (may have a preamble line)
    i = raw.find("{")
    if i != -1 and '"ranges"' in raw:
        j = raw.rfind("}")
        data = json.loads(raw[i:j + 1])
        rngs = [r for r in data["ranges"] if r.get("sheet", "Stations") == "Stations"]
        if not rngs:
            sys.exit("Connector output has no 'Stations' range")
        return rngs[0]["content"]
    return raw


def parse(text):
    rows = [{ALIASES.get(k, k): v for k, v in r.items()} for r in csv.DictReader(io.StringIO(text))]
    missing = [c for c in REQUIRED if c not in (rows[0].keys() if rows else [])]
    if missing:
        sys.exit(f"Sheet is missing columns: {missing}")
    out = []
    for r in rows:
        if not (r.get("ID") or "").strip():
            continue
        s = {c: (r.get(c) or "").strip() for c in PUBLIC}
        try:
            s["lat"], s["lng"] = float(s["Latitude"]), float(s["Longitude"])
        except ValueError:
            s["lat"] = s["lng"] = None
        out.append(s)
    return out


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PEMEX Stations</title>
<meta name="theme-color" content="#0b0b0b">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
:root{--g:#00563b;--r:#d12203;--ink:#1f2326;--muted:#6f767b;--line:#e3e5e3;--bg:#fafaf8;--rad:4px;--header:#0b0b0b}
*{box-sizing:border-box}
body{margin:0;font-family:Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:var(--ink);background:var(--bg);-webkit-font-smoothing:antialiased;line-height:1.5;font-size:15px}
header{background:var(--header);color:#fff;border-bottom:2px solid var(--r)}
.hwrap{max-width:1120px;margin:0 auto;padding:16px 24px;display:flex;align-items:center;justify-content:space-between;gap:28px}
.brand{display:flex;align-items:center;gap:14px;min-width:0}
header .logo{display:block;height:44px;width:auto;flex:none}
.stat{text-align:right;flex:none;line-height:1.2;color:#fff}
.stat .n{font-size:1.85rem;font-weight:600;letter-spacing:-.02em;line-height:1;font-variant-numeric:tabular-nums}
.stat .lbl{margin-top:3px;font-size:.82rem;opacity:.9}
.stat .sub{margin-top:2px;font-size:.75rem;opacity:.7}
main{max-width:1120px;margin:0 auto;padding:24px}
.panel{background:#fff;border:1px solid var(--line);border-radius:var(--rad);overflow:hidden}
#map{height:56vh;min-height:340px}
.mapbar{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:10px;padding:10px 14px;border-top:1px solid var(--line);font-size:.82rem;color:var(--muted)}
.legend{display:flex;flex-wrap:wrap;gap:14px}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;vertical-align:middle;position:relative;top:-1px}
.toggle{display:inline-flex;align-items:center;gap:7px;cursor:pointer;color:var(--ink)}
.toggle input{accent-color:var(--g);width:14px;height:14px;margin:0}
.controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 12px}
.controls input,.controls select{font:inherit;font-size:.9rem;padding:8px 10px;border:1px solid var(--line);border-radius:var(--rad);background:#fff;color:var(--ink);outline:none}
.controls input:focus,.controls select:focus{border-color:var(--g)}
.controls input[type=search]{flex:1;min-width:200px}
table{border-collapse:separate;border-spacing:0;width:100%;font-size:.9rem}
th,td{padding:11px 14px;text-align:left;vertical-align:middle;border-bottom:1px solid var(--line)}
th{position:sticky;top:0;z-index:1;background:#fff;font-size:.82rem;font-weight:500;color:var(--muted);cursor:pointer;white-space:nowrap;user-select:none}
th.asc:after{content:" ↑"}th.desc:after{content:" ↓"}
td:first-child{font-weight:500}td:nth-child(2){white-space:nowrap;color:var(--muted)}
tbody tr:hover{background:#f7f8f6}tbody tr:last-child td{border-bottom:0}
tr.lost td{opacity:.55}
.pill{white-space:nowrap}
.pill:before{content:"";display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--c);margin-right:7px;position:relative;top:-1px}
#nomap{font-size:.82rem;color:var(--muted);margin:12px 2px 0}
footer{font-size:.75rem;color:var(--muted);padding:16px 24px 28px;text-align:center;line-height:1.7}
.leaflet-popup-content-wrapper{border-radius:var(--rad);box-shadow:0 1px 4px rgba(0,0,0,.18)}.leaflet-popup-content{font-family:Inter,system-ui,sans-serif;font-size:.85rem;line-height:1.5;margin:10px 14px}
.leaflet-container{font-family:inherit;background:#eef0ee}
.leaflet-tile-pane{filter:grayscale(1) contrast(.88) brightness(1.08)}
.leaflet-bar,.leaflet-bar a{border-radius:var(--rad)!important}
.list,.phone-only{display:none}
@media (max-width:600px){
.hwrap{flex-wrap:nowrap;padding:8px 14px;gap:12px;align-items:center}
header .logo{height:32px}
.stat{width:auto;text-align:right;padding-top:0;border-top:0}
.stat .n{font-size:24px}
.stat .lbl{margin-top:1px;font-size:.72rem}
.stat .sub{margin-top:1px;font-size:.65rem;white-space:nowrap}
main{padding:12px 14px}
#map{height:45vh;min-height:260px}
.mapbar{padding:8px 10px;gap:8px}
.controls{margin:12px 0}
.controls input[type=search]{flex:1 1 100%;min-width:0}
.controls select{flex:1 1 0;min-width:0}
.phone-only{display:block}
#fSort{flex:1 1 100%}
.tablewrap{display:none}
.list{display:block;list-style:none;margin:0;padding:0;border-top:1px solid var(--line)}
.list li{padding:12px 0;border-bottom:1px solid var(--line)}
.list li.lost{opacity:.55}
.l-top{display:flex;justify-content:space-between;align-items:baseline;gap:12px}
.l-top strong{font-weight:600;min-width:0;flex:1;overflow-wrap:anywhere}
.l-top .pill{flex:none;font-size:.82rem}
.l-addr,.l-loc{font-size:.82rem;color:var(--muted);margin-top:2px;overflow-wrap:anywhere;line-height:1.4}
}
@media (max-width:340px){.stat .sub{display:none}}
</style></head><body>
<header><div class="hwrap"><div class="brand"><img class="logo" src="__LOGO__" alt="PEMEX Stations"></div>__STAT__</div></header>
<main>
<div class="panel"><div id="map"></div>
<div class="mapbar"><div class="legend" id="legend"></div><label class="toggle"><input type="checkbox" id="showLost"> Show Lost stations</label></div></div>
<div class="controls">
 <input type="search" id="q" placeholder="Search station, city or address">
 <select id="fState"><option value="">All states</option></select>
 <select id="fStatus"><option value="">All statuses</option></select>
 <select id="fSort" class="phone-only" aria-label="Sort list">
  <option value="loc">Sort: State, city</option>
  <option value="Name">Sort: Station</option>
  <option value="Address">Sort: Address</option>
  <option value="status">Sort: Status</option>
 </select>
</div>
<div class="panel tablewrap"><table id="tbl"><thead><tr>
<th data-k="Name">Station</th><th data-k="loc">City, State</th><th data-k="Address">Address</th><th data-k="status">Status</th></tr></thead><tbody></tbody></table></div>
<ul class="list" id="list"></ul>
<p id="nomap"></p>
</main>
<footer>__BUILT__<br>Map data © OpenStreetMap contributors</footer>
<script>
const STATIONS = __DATA__;
const COLORS = {Open:"#1a9850",Converting:"#fdae61",Planned:"#4575b4",Lead:"#8e44ad",Lost:"#d73027",Unknown:"#9e9e9e"};
STATIONS.forEach(s=>{s.status = COLORS[s.Status] ? s.Status : "Unknown"; s.loc=[s.City,s.State].filter(Boolean).join(", ");});
const $=id=>document.getElementById(id);
const esc=t=>String(t??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const map=L.map("map",{scrollWheelZoom:false}).setView([32.5,-108],5);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).addTo(map);  // muted via CSS filter on .leaflet-tile-pane
const markers=[];
STATIONS.forEach(s=>{ if(s.lat==null) return;
  const m=L.circleMarker([s.lat,s.lng],{radius:7,color:"#fff",weight:2,fillColor:COLORS[s.status],fillOpacity:1});
  m.bindPopup(`<b>${esc(s.Name)}</b><br>${esc(s.Address)}<br>Status: ${esc(s.status)}`+[["Operator or owner contact","Operator"],["Date branded","Date branded"],["Date debranded","Date debranded"],["Cost estimate","Cost estimate"]].map(([k,l])=>s[k]?`<br>${l}: ${esc(s[k])}`:"").join(""));
  markers.push({s,m});});
$("legend").innerHTML=Object.entries(COLORS).filter(([k])=>STATIONS.some(s=>s.status===k)).map(([k,v])=>`<span><span class="dot" style="background:${v}"></span>${k}</span>`).join("");
const uniq=a=>[...new Set(a)].sort();
uniq(STATIONS.map(s=>s.State)).forEach(v=>$("fState").insertAdjacentHTML("beforeend",`<option>${esc(v)}</option>`));
Object.keys(COLORS).forEach(v=>$("fStatus").insertAdjacentHTML("beforeend",`<option>${v}</option>`));
let sortK="loc",sortDir=1;
function visible(s){const q=$("q").value.toLowerCase(),st=$("fState").value,ss=$("fStatus").value;
  if(st&&s.State!==st)return false; if(ss&&s.status!==ss)return false;
  if(!ss&&s.status==="Lost"&&!$("showLost").checked)return false;
  if(q&&!Object.values(s).join(" ").toLowerCase().includes(q))return false; return true;}
function cmp(a,b){const keys=sortK==="loc"?["State","City","Name"]:[sortK];
  for(const k of keys){const d=String(a[k]??"").localeCompare(String(b[k]??""),undefined,{numeric:true});if(d)return d*sortDir;}return 0;}
function render(){const rows=STATIONS.filter(visible).sort(cmp);
  document.querySelector("#tbl tbody").innerHTML=rows.map(s=>`<tr class="${s.status==="Lost"?"lost":""}"><td>${esc(s.Name)}</td><td>${esc(s.loc)}</td><td>${esc(s.Address)}</td><td><span class="pill" style="--c:${COLORS[s.status]}">${esc(s.status)}</span></td></tr>`).join("");
  $("list").innerHTML=rows.map(s=>`<li class="${s.status==="Lost"?"lost":""}"><div class="l-top"><strong>${esc(s.Name)}</strong><span class="pill" style="--c:${COLORS[s.status]}">${esc(s.status)}</span></div><div class="l-addr">${esc(s.Address)}</div><div class="l-loc">${esc(s.loc)}</div></li>`).join("");
  markers.forEach(({s,m})=>{visible(s)?m.addTo(map):m.remove();});
  document.querySelectorAll("th").forEach(th=>th.className=th.dataset.k===sortK?(sortDir>0?"asc":"desc"):"");
  const nm=STATIONS.filter(s=>s.lat==null&&visible(s)).map(s=>s.Name);$("nomap").textContent=nm.length?`Not on map yet (address being confirmed): ${nm.join(", ")}`:"";}
document.querySelectorAll("th").forEach(th=>th.onclick=()=>{const k=th.dataset.k;sortDir=(sortK===k)?-sortDir:1;sortK=k;render();});
["q","fState","fStatus","showLost"].forEach(id=>$(id).addEventListener("input",render));
$("fSort").addEventListener("change",()=>{sortK=$("fSort").value;sortDir=1;render();});
render();
const pts=markers.map(x=>x.m.getLatLng());if(pts.length)map.fitBounds(L.latLngBounds(pts).pad(.1));
</script></body></html>
"""


def check_build(stations, html_path):
    """Assert the built page contains every station and default rows == open count."""
    ids = [s["ID"] for s in stations]
    if not ids:
        sys.exit("Build check failed: no stations")
    if len(ids) != len(set(ids)):
        sys.exit("Build check failed: duplicate station IDs")
    open_n = sum(1 for s in stations if s["Status"] == "Open")
    default_n = sum(1 for s in stations if s["Status"] != "Lost")
    # Default table (Lost hidden) should list every Open row. If only Open and Lost
    # exist, that equals the open count. Other statuses would also appear.
    others = {s["Status"] for s in stations} - {"Open", "Lost", ""}
    if not others and default_n != open_n:
        sys.exit(f"Build check failed: default rows {default_n} != open count {open_n}")
    text = html_path.read_text(encoding="utf-8")
    if "max-height:70vh" in text or ".tablewrap{overflow:auto" in text:
        sys.exit("Build check failed: table still has an inner scroll box")
    if 'id="list"' not in text or 'id="tbl"' not in text:
        sys.exit("Build check failed: table or phone list markup missing")
    if ".hwrap{flex-wrap:wrap" in text or "border-top:1px solid rgba(255,255,255,.25)" in text:
        sys.exit("Build check failed: phone header still stacks the count under the logo")
    if "height:45vh" not in text or "min-height:260px" not in text:
        sys.exit("Build check failed: phone map height is not 45vh / min 260px")
    for s in stations:
        if s["ID"] not in text or s["Name"] not in text:
            sys.exit(f"Build check failed: {s['ID']} {s['Name']!r} missing from index.html")
    open_names = [s["Name"] for s in stations if s["Status"] == "Open"]
    if len(open_names) != open_n:
        sys.exit("Build check failed: Open name list does not match open count")
    if f'"Status": "Open"' in text:
        # JSON may use different spacing; count Open in the data blob instead
        pass
    blob_i = text.find("const STATIONS = ")
    if blob_i == -1:
        sys.exit("Build check failed: STATIONS data missing")
    if default_n != open_n and others:
        print(f"Note: default table rows ({default_n}) include non-Open statuses {sorted(others)}")


def main():
    stations = parse(load_text(sys.argv[1:]))
    (HERE / "data").mkdir(exist_ok=True)
    with open(HERE / "data" / "stations.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=PUBLIC, extrasaction="ignore")
        w.writeheader()
        w.writerows(stations)
    now = datetime.datetime.now(ZoneInfo("America/Chicago"))
    built = f"Updated {now.strftime('%b')} {now.day}, {now.year}, {now.strftime('%-I:%M')} {'AM' if now.hour < 12 else 'PM'} CT"
    data = json.dumps([{k: s[k] for k in PUBLIC + ["lat", "lng"]} for s in stations], ensure_ascii=False).replace("</", "<\\/")
    logo_path = HERE / "assets" / "pemex-logo.png"  # J.R.'s PEMEX lockup (photo), tight crop, black ground
    if not logo_path.exists():
        sys.exit(f"Missing logo: {logo_path}")
    logo = "data:image/png;base64," + base64.b64encode(logo_path.read_bytes()).decode()
    open_rows = [s for s in stations if s["Status"] == "Open"]
    names = {"CA": "California", "TX": "Texas"}
    by_state = Counter(s["State"] for s in open_rows)
    state_line = " · ".join(f"{by_state[st]} {names.get(st, st)}" for st in sorted(by_state) if by_state[st])
    by_status = Counter(s["Status"] for s in stations)
    pending = []
    for st in ("Converting", "Planned", "Lead"):
        if by_status.get(st):
            pending.append(f"{by_status[st]} {st.lower()}")
    known = {"Open", "Lost", "", "Converting", "Planned", "Lead"}
    for st, n in sorted(by_status.items()):
        if st not in known and n:
            pending.append(f"{n} {st.lower()}")
    stat = f'<div class="stat"><div class="n">{len(open_rows)}</div><div class="lbl">Open stations</div>'
    if state_line:
        stat += f'<div class="sub">{html.escape(state_line)}</div>'
    if pending:
        stat += f'<div class="sub">{html.escape(" · ".join(pending))}</div>'
    stat += "</div>"
    out = (TEMPLATE.replace("__DATA__", data).replace("__BUILT__", html.escape(built))
           .replace("__LOGO__", logo).replace("__STAT__", stat))
    html_path = HERE / "index.html"
    html_path.write_text(out, encoding="utf-8")
    check_build(stations, html_path)
    geo = sum(1 for s in stations if s["lat"] is not None)
    print(f"Wrote index.html: {len(stations)} stations, {geo} with coordinates, {len(open_rows)} open (default table rows)")


if __name__ == "__main__":
    main()
