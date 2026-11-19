#!/usr/bin/env python3
"""Build index.html ("Pemex Stations" map + table) from the Pemex Station Tracker Sheet.

Input (pick one):
  python3 build.py data/stations.csv          # CSV export of the "Stations" tab
  python3 build.py connector_output.json      # raw Google Sheets connector read_range output
  python3 build.py --url "<csv export url>"   # only works if the Sheet is readable without login
Output: index.html (and data/stations.csv refreshed) in this folder.
"""
import base64, csv, io, json, os, sys, html, datetime, urllib.request, pathlib

# Sheet ID is kept out of the public repo; see README in /workspace/pemex-tracker.
SHEET_ID = os.environ.get("PEMEX_SHEET_ID", "")
HERE = pathlib.Path(__file__).resolve().parent
COLS = ["ID", "Name", "State", "City", "Address", "Latitude", "Longitude", "Status",
        "Operator or owner contact", "Pemex go-live date", "Fuel volume or sales", "Last updated", "Notes"]


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
        return data["ranges"][0]["content"]
    return raw


def parse(text):
    rows = list(csv.DictReader(io.StringIO(text)))
    missing = [c for c in COLS if c not in (rows[0].keys() if rows else [])]
    if missing:
        sys.exit(f"Sheet is missing columns: {missing}")
    out = []
    for r in rows:
        if not (r.get("ID") or "").strip():
            continue
        s = {c: (r.get(c) or "").strip() for c in COLS}
        try:
            s["lat"], s["lng"] = float(s["Latitude"]), float(s["Longitude"])
        except ValueError:
            s["lat"] = s["lng"] = None
        out.append(s)
    return out, text


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pemex Stations</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
:root{--g:#006847;--r:#ce1126}
*{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#222;background:#f6f7f8}
header{background:var(--g);color:#fff;padding:12px 16px;border-bottom:4px solid var(--r);display:flex;align-items:center;gap:14px}
header .logo{flex:none;width:64px;height:64px;background:#fff;border-radius:12px;padding:6px;display:flex;align-items:center;justify-content:center;box-shadow:0 1px 3px #0004}
header .logo img{width:100%;height:100%;object-fit:contain}
header h1{margin:0;font-size:1.6rem}header small{opacity:.85}
main{max-width:1200px;margin:0 auto;padding:12px}
#map{height:55vh;min-height:320px;border-radius:8px;border:1px solid #ccc}
.cards{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}
.card{background:#fff;border:1px solid #ddd;border-radius:8px;padding:8px 12px;min-width:120px}
.card b{display:block;font-size:1.3rem}.card span{font-size:.8rem;color:#555}
.controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:8px 0}
.controls input,.controls select{padding:6px 8px;font-size:1rem;border:1px solid #bbb;border-radius:6px}
.controls input[type=search]{flex:1;min-width:180px}
.legend{display:flex;flex-wrap:wrap;gap:10px;font-size:.85rem;margin:6px 0}
.dot{display:inline-block;width:12px;height:12px;border-radius:50%;margin-right:4px;vertical-align:middle;border:1px solid #0003}
.tablewrap{overflow-x:auto;background:#fff;border:1px solid #ddd;border-radius:8px}
table{border-collapse:collapse;width:100%;font-size:.9rem}
th,td{padding:6px 8px;border-bottom:1px solid #eee;text-align:left;vertical-align:top}
th{background:#eef3f0;cursor:pointer;white-space:nowrap;position:sticky;top:0}
th.asc:after{content:" ▲"}th.desc:after{content:" ▼"}
td:first-child,td:nth-child(8){white-space:nowrap}td.notes{max-width:360px;color:#555;font-size:.8rem}
tr.lost{opacity:.6}tr:hover{background:#fafcfb}
.badge{padding:2px 8px;border-radius:10px;color:#fff;font-size:.8rem;white-space:nowrap}
footer{font-size:.8rem;color:#666;padding:12px 16px;text-align:center}
@media (max-width:600px){header{padding:10px 12px;gap:10px}header .logo{width:48px;height:48px;border-radius:10px;padding:4px}header h1{font-size:1.3rem}#map{height:45vh}td.notes{display:none}th.notes{display:none}}
</style></head><body>
<header><div class="logo"><img src="__LOGO__" alt="Pemex eagle logo"></div><div><h1>Pemex Stations</h1><small>Data last built __BUILT__ from the Pemex Station Tracker sheet</small></div></header>
<main>
<div id="map"></div>
<div class="legend" id="legend"></div>
<label><input type="checkbox" id="showLost"> Show Lost stations</label>
<div class="cards" id="cards"></div>
<div class="controls">
 <input type="search" id="q" placeholder="Search name, city, address, notes…">
 <select id="fState"><option value="">All states</option></select>
 <select id="fStatus"><option value="">All statuses</option></select>
</div>
<div class="tablewrap"><table id="tbl"><thead><tr>
<th data-k="ID">ID</th><th data-k="Name">Name</th><th data-k="State">State</th><th data-k="City">City</th>
<th data-k="Address">Address</th><th data-k="status">Status</th><th data-k="Pemex go-live date">Go-live</th>
<th data-k="Last updated">Updated</th><th data-k="Notes" class="notes">Notes</th></tr></thead><tbody></tbody></table></div>
<p id="nomap" style="font-size:.85rem;color:#666"></p>
</main>
<footer>Map data © OpenStreetMap contributors</footer>
<script>
const STATIONS = __DATA__;
const COLORS = {Open:"#1a9850",Converting:"#fdae61",Planned:"#4575b4",Lost:"#d73027",Unknown:"#9e9e9e"};
STATIONS.forEach(s=>{s.status = COLORS[s.Status] ? s.Status : "Unknown";});
const $=id=>document.getElementById(id);
const esc=t=>String(t??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const map=L.map("map",{scrollWheelZoom:false}).setView([32.5,-108],5);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:"© OpenStreetMap"}).addTo(map);
const markers=[];
STATIONS.forEach(s=>{ if(s.lat==null) return;
  const m=L.circleMarker([s.lat,s.lng],{radius:8,color:"#333",weight:1,fillColor:COLORS[s.status],fillOpacity:.9});
  m.bindPopup(`<b>${esc(s.ID)} · ${esc(s.Name)}</b><br>${esc(s.Address)}<br>Status: ${esc(s.status)}`+(s["Pemex go-live date"]?`<br>Go-live: ${esc(s["Pemex go-live date"])}`:""));
  markers.push({s,m});});
$("legend").innerHTML=Object.entries(COLORS).map(([k,v])=>`<span><span class="dot" style="background:${v}"></span>${k}</span>`).join("");
const uniq=a=>[...new Set(a)].sort();
uniq(STATIONS.map(s=>s.State)).forEach(v=>$("fState").insertAdjacentHTML("beforeend",`<option>${esc(v)}</option>`));
Object.keys(COLORS).forEach(v=>$("fStatus").insertAdjacentHTML("beforeend",`<option>${v}</option>`));
let sortK="ID",sortDir=1;
function visible(s){const q=$("q").value.toLowerCase(),st=$("fState").value,ss=$("fStatus").value;
  if(st&&s.State!==st)return false; if(ss&&s.status!==ss)return false;
  if(!ss&&s.status==="Lost"&&!$("showLost").checked)return false;
  if(q&&!Object.values(s).join(" ").toLowerCase().includes(q))return false; return true;}
function cards(){const vis=STATIONS.filter(s=>$("showLost").checked||s.status!=="Lost");
  const c=[["Total",vis.length]];const by=(k)=>{const o={};vis.forEach(s=>o[s[k]]=(o[s[k]]||0)+1);return o;};
  Object.entries(by("State")).sort().forEach(([k,v])=>c.push([k,v]));
  Object.entries(by("status")).sort().forEach(([k,v])=>c.push([k,v]));
  $("cards").innerHTML=c.map(([k,v])=>`<div class="card"><b>${v}</b><span>${esc(k)}</span></div>`).join("");}
function render(){const rows=STATIONS.filter(visible).sort((a,b)=>String(a[sortK]).localeCompare(String(b[sortK]),undefined,{numeric:true})*sortDir);
  document.querySelector("#tbl tbody").innerHTML=rows.map(s=>`<tr class="${s.status==="Lost"?"lost":""}"><td>${esc(s.ID)}</td><td>${esc(s.Name)}</td><td>${esc(s.State)}</td><td>${esc(s.City)}</td><td>${esc(s.Address)}</td><td><span class="badge" style="background:${COLORS[s.status]}">${esc(s.status)}</span></td><td>${esc(s["Pemex go-live date"])}</td><td>${esc(s["Last updated"])}</td><td class="notes">${esc(s.Notes)}</td></tr>`).join("");
  markers.forEach(({s,m})=>{visible(s)?m.addTo(map):m.remove();});
  document.querySelectorAll("th").forEach(th=>th.className=(th.classList.contains("notes")?"notes ":"")+(th.dataset.k===sortK?(sortDir>0?"asc":"desc"):""));
  cards();
  const nm=STATIONS.filter(s=>s.lat==null).map(s=>s.ID);$("nomap").textContent=nm.length?`Not on map yet (no confirmed coordinates): ${nm.join(", ")}`:"";}
document.querySelectorAll("th").forEach(th=>th.onclick=()=>{const k=th.dataset.k;sortDir=(sortK===k)?-sortDir:1;sortK=k;render();});
["q","fState","fStatus","showLost"].forEach(id=>$(id).addEventListener("input",render));
render();
const pts=markers.map(x=>x.m.getLatLng());if(pts.length)map.fitBounds(L.latLngBounds(pts).pad(.1));
</script></body></html>
"""


def main():
    stations, text = parse(load_text(sys.argv[1:]))
    (HERE / "data").mkdir(exist_ok=True)
    (HERE / "data" / "stations.csv").write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    built = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    data = json.dumps(stations, ensure_ascii=False).replace("</", "<\\/")
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
