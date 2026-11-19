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
<meta name="theme-color" content="#00563b">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
:root{--g:#00563b;--g2:#006847;--r:#ce1126;--ink:#1d2327;--muted:#6b747b;--line:#e8ebee;--bg:#f5f6f4;--card:#fff;--rad:14px;--sh:0 1px 2px rgba(16,24,40,.04),0 4px 14px rgba(16,24,40,.06)}
*{box-sizing:border-box}
body{margin:0;font-family:Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:var(--ink);background:var(--bg);-webkit-font-smoothing:antialiased;line-height:1.45}
header{background:linear-gradient(135deg,var(--g) 0%,var(--g2) 100%);color:#fff;border-bottom:3px solid var(--r)}
.hwrap{max-width:1200px;margin:0 auto;padding:22px 24px;display:flex;align-items:center;gap:18px}
header .logo{flex:none;width:60px;height:60px;background:#fff;border-radius:14px;padding:7px;display:flex;align-items:center;justify-content:center;box-shadow:0 2px 8px rgba(0,0,0,.18)}
header .logo img{width:100%;height:100%;object-fit:contain}
header h1{margin:0;font-size:1.75rem;font-weight:700;letter-spacing:.01em}
header small{display:block;margin-top:2px;font-size:.8rem;opacity:.8;letter-spacing:.02em}
main{max-width:1200px;margin:0 auto;padding:24px}
.panel{background:var(--card);border-radius:var(--rad);box-shadow:var(--sh);overflow:hidden}
#map{height:56vh;min-height:340px}
.mapbar{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:10px;padding:12px 16px;border-top:1px solid var(--line);font-size:.82rem;color:var(--muted)}
.legend{display:flex;flex-wrap:wrap;gap:14px}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;vertical-align:middle;box-shadow:0 0 0 2px #fff,0 0 0 3px rgba(0,0,0,.08)}
.toggle{display:inline-flex;align-items:center;gap:8px;cursor:pointer;color:var(--ink);font-weight:500}
.toggle input{accent-color:var(--g2);width:16px;height:16px}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:12px;margin:20px 0}
.card{background:var(--card);border-radius:12px;box-shadow:var(--sh);padding:14px 16px;border-top:3px solid var(--line)}
.card b{display:block;font-size:1.9rem;font-weight:700;line-height:1.1;letter-spacing:-.02em}
.card span{display:block;margin-top:4px;font-size:.68rem;font-weight:600;text-transform:uppercase;letter-spacing:.09em;color:var(--muted)}
.card.total{border-top-color:var(--g2)}
.controls{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:0 0 12px}
.controls input,.controls select{font:inherit;font-size:.92rem;padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:#fff;color:var(--ink);outline:none;transition:border-color .15s,box-shadow .15s}
.controls input:focus,.controls select:focus{border-color:var(--g2);box-shadow:0 0 0 3px rgba(0,104,71,.12)}
.controls input[type=search]{flex:1;min-width:200px}
.tablewrap{overflow:auto;max-height:70vh}
table{border-collapse:separate;border-spacing:0;width:100%;font-size:.9rem}
th,td{padding:12px 16px;text-align:left;vertical-align:middle;border-bottom:1px solid var(--line)}
th{position:sticky;top:0;z-index:1;background:#fafbfa;font-size:.7rem;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);cursor:pointer;white-space:nowrap;user-select:none}
th.asc:after{content:" ↑"}th.desc:after{content:" ↓"}
td:first-child{font-weight:600}td:nth-child(2){white-space:nowrap;color:var(--muted)}td:nth-child(3){color:#444}
tbody tr{transition:background .12s}tbody tr:hover{background:#f6faf8}tbody tr:last-child td{border-bottom:0}
tr.lost td{opacity:.55}
.pill{display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:999px;font-size:.75rem;font-weight:600;white-space:nowrap;color:var(--c);background:color-mix(in srgb,var(--c) 12%,#fff)}
.pill:before{content:"";width:6px;height:6px;border-radius:50%;background:var(--c)}
#nomap{font-size:.82rem;color:var(--muted);margin:12px 2px 0}
footer{font-size:.75rem;color:var(--muted);padding:8px 24px 28px;text-align:center}
.leaflet-popup-content-wrapper{border-radius:12px;box-shadow:var(--sh)}.leaflet-popup-content{font-family:Inter,system-ui,sans-serif;font-size:.85rem;line-height:1.5;margin:12px 16px}
.leaflet-container{font-family:inherit;background:#eef0ee}
.leaflet-tile-pane{filter:grayscale(1) contrast(.88) brightness(1.08)}
@media (max-width:600px){.hwrap{padding:16px;gap:12px}header .logo{width:46px;height:46px;border-radius:11px;padding:5px}header h1{font-size:1.3rem}header small{font-size:.72rem}
main{padding:14px}#map{height:44vh;min-height:280px}.cards{grid-template-columns:repeat(2,1fr);gap:10px;margin:14px 0}.card{padding:12px 14px}.card b{font-size:1.6rem}
th,td{padding:10px 12px}td:nth-child(3){min-width:180px}.controls select{flex:1}}
</style></head><body>
<header><div class="hwrap"><div class="logo"><img src="__LOGO__" alt="PEMEX eagle logo"></div><div><h1>PEMEX Stations</h1><small>Updated __BUILT__</small></div></div></header>
<main>
<div class="panel"><div id="map"></div>
<div class="mapbar"><div class="legend" id="legend"></div><label class="toggle"><input type="checkbox" id="showLost"> Show Lost stations</label></div></div>
<div class="cards" id="cards"></div>
<div class="controls">
 <input type="search" id="q" placeholder="Search station, city or address">
 <select id="fState"><option value="">All states</option></select>
 <select id="fStatus"><option value="">All statuses</option></select>
</div>
<div class="panel tablewrap"><table id="tbl"><thead><tr>
<th data-k="Name">Station</th><th data-k="loc">City, State</th><th data-k="Address">Address</th><th data-k="status">Status</th></tr></thead><tbody></tbody></table></div>
<p id="nomap"></p>
</main>
<footer>Map data © OpenStreetMap contributors</footer>
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
$("legend").innerHTML=Object.entries(COLORS).map(([k,v])=>`<span><span class="dot" style="background:${v}"></span>${k}</span>`).join("");
const uniq=a=>[...new Set(a)].sort();
uniq(STATIONS.map(s=>s.State)).forEach(v=>$("fState").insertAdjacentHTML("beforeend",`<option>${esc(v)}</option>`));
Object.keys(COLORS).forEach(v=>$("fStatus").insertAdjacentHTML("beforeend",`<option>${v}</option>`));
let sortK="loc",sortDir=1;
function visible(s){const q=$("q").value.toLowerCase(),st=$("fState").value,ss=$("fStatus").value;
  if(st&&s.State!==st)return false; if(ss&&s.status!==ss)return false;
  if(!ss&&s.status==="Lost"&&!$("showLost").checked)return false;
  if(q&&!Object.values(s).join(" ").toLowerCase().includes(q))return false; return true;}
function cards(){const vis=STATIONS.filter(s=>$("showLost").checked||s.status!=="Lost");
  const c=[["Total",vis.length]];const by=(k)=>{const o={};vis.forEach(s=>o[s[k]]=(o[s[k]]||0)+1);return o;};
  Object.entries(by("State")).sort().forEach(([k,v])=>c.push([k,v]));
  const bs=by("status");  // always show the working statuses (incl. Lead); Lost/Unknown only when present
  Object.keys(COLORS).forEach(k=>{if(["Open","Converting","Planned","Lead"].includes(k)||bs[k])c.push([k,bs[k]||0]);});
  $("cards").innerHTML=c.map(([k,v],i)=>`<div class="card${i?"":" total"}" style="${COLORS[k]?`border-top-color:${COLORS[k]}`:""}"><b>${v}</b><span>${esc(k)}</span></div>`).join("");}
function render(){const rows=STATIONS.filter(visible).sort((a,b)=>String(a[sortK]).localeCompare(String(b[sortK]),undefined,{numeric:true})*sortDir);
  document.querySelector("#tbl tbody").innerHTML=rows.map(s=>`<tr class="${s.status==="Lost"?"lost":""}"><td>${esc(s.Name)}</td><td>${esc(s.loc)}</td><td>${esc(s.Address)}</td><td><span class="pill" style="--c:${COLORS[s.status]}">${esc(s.status)}</span></td></tr>`).join("");
  markers.forEach(({s,m})=>{visible(s)?m.addTo(map):m.remove();});
  document.querySelectorAll("th").forEach(th=>th.className=th.dataset.k===sortK?(sortDir>0?"asc":"desc"):"");
  cards();
  const nm=STATIONS.filter(s=>s.lat==null&&visible(s)).map(s=>s.Name);$("nomap").textContent=nm.length?`Not on map yet (address being confirmed): ${nm.join(", ")}`:"";}
document.querySelectorAll("th").forEach(th=>th.onclick=()=>{const k=th.dataset.k;sortDir=(sortK===k)?-sortDir:1;sortK=k;render();});
["q","fState","fStatus","showLost"].forEach(id=>$(id).addEventListener("input",render));
render();
const pts=markers.map(x=>x.m.getLatLng());if(pts.length)map.fitBounds(L.latLngBounds(pts).pad(.1));
</script></body></html>
"""


def main():
    stations = parse(load_text(sys.argv[1:]))
    (HERE / "data").mkdir(exist_ok=True)
    with open(HERE / "data" / "stations.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=PUBLIC, extrasaction="ignore")
        w.writeheader()
        w.writerows(stations)
    built = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    data = json.dumps([{k: s[k] for k in PUBLIC + ["lat", "lng"]} for s in stations], ensure_ascii=False).replace("</", "<\\/")
    logo_path = HERE / "assets" / "pemex-logo.svg"  # Pemex eagle mark, Wikimedia Commons (public domain)
    if not logo_path.exists():
        sys.exit(f"Missing logo: {logo_path}")
    logo = "data:image/svg+xml;base64," + base64.b64encode(logo_path.read_bytes()).decode()
    out = TEMPLATE.replace("__DATA__", data).replace("__BUILT__", html.escape(built)).replace("__LOGO__", logo)
    (HERE / "index.html").write_text(out, encoding="utf-8")
    geo = sum(1 for s in stations if s["lat"] is not None)
    print(f"Wrote index.html: {len(stations)} stations, {geo} with coordinates")


if __name__ == "__main__":
    main()
