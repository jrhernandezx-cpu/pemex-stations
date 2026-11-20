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
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Saira+Condensed:wght@300;400&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
:root{--g:#3dcc76;--r:#d12203;--ink:#f2f2f2;--muted:#9a9a9a;--line:#262626;--bg:#0b0b0b;--rad:4px;--header:#0b0b0b;--display:"Saira Condensed",Inter,sans-serif;--input:#151515}
*{box-sizing:border-box}
body{margin:0;font-family:Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:var(--ink);background:var(--bg);-webkit-font-smoothing:antialiased;line-height:1.5;font-size:15px;color-scheme:dark}
header{background:var(--header);color:#fff;border-bottom:2px solid var(--r)}
.hwrap{max-width:1120px;margin:0 auto;padding:16px 24px;display:flex;align-items:center;justify-content:space-between;gap:28px}
.brand{display:flex;align-items:center;gap:14px;min-width:0}
header .logo{display:block;height:44px;width:auto;flex:none}
.stat{flex:none;display:grid;grid-template-columns:auto auto;grid-template-rows:auto auto;column-gap:10px;align-items:center;text-align:left;line-height:1.15;color:#fff}
.stat .n{grid-column:1;grid-row:1 / span 2;font-family:var(--display);font-weight:300;font-size:50px;letter-spacing:-.03em;line-height:.85;font-variant-numeric:tabular-nums}
.stat .lbl{grid-column:2;grid-row:1;align-self:end;margin:0;font-size:.82rem;opacity:.9}
.stat .sub{grid-column:2;grid-row:2;align-self:start;margin:0;font-size:.75rem;opacity:.7;white-space:nowrap}
main{max-width:868px;margin:0 auto;padding:28px 24px 36px}
.panel{background:transparent;border:0;border-radius:0;overflow:visible}
.mapbleed{background:#0b0b0b}
#map{height:56vh;min-height:360px;background:#0b0b0b}
.mapbar{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:10px;padding:10px 14px;border-top:1px solid var(--line);font-size:.82rem;color:var(--muted)}
.legend{display:flex;flex-wrap:wrap;gap:14px}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;vertical-align:middle;position:relative;top:-1px}
.controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 12px}
.controls input{font:inherit;font-size:.9rem;padding:8px 10px;border:1px solid var(--line);border-radius:var(--rad);background:var(--input);color:var(--ink);outline:none}
.controls input::placeholder{color:#8a8a8a}
.controls input:focus{border-color:#555}
.controls input[type=search]{flex:1;min-width:200px}
.seg{display:flex;flex:none;align-items:stretch;gap:32px;border:0;border-bottom:1px solid #262626;border-radius:0;overflow:visible;background:transparent}
.seg button{appearance:none;background:transparent;border:0;margin:0;padding:8px 0 10px;font:inherit;font-size:.82rem;color:#8a8a8a;cursor:pointer;line-height:1.2;border-radius:0;box-shadow:none;position:relative;white-space:nowrap}
.seg button:hover{background:transparent;color:#c8c8c8}
.seg button.on{background:transparent;color:#fff}
.seg button.on:hover{background:transparent;color:#fff}
.seg button .c{opacity:.55;font-variant-numeric:tabular-nums}
.seg button.on .c{opacity:.7}
.seg button.on::after{content:"";position:absolute;left:0;right:0;bottom:-1px;height:2px;background:#d12203}
tr.empty td{padding:20px 14px;border-bottom:0;color:var(--muted);font-weight:400}
#list .empty{padding:16px 0;border-bottom:0;color:var(--muted)}
table{border-collapse:separate;border-spacing:0;width:100%;font-size:.85rem;table-layout:fixed}
th,td{padding:10px 12px;text-align:left;vertical-align:middle;border-bottom:1px solid var(--line)}
th:nth-child(1),td:nth-child(1){width:25%}th:nth-child(2),td:nth-child(2){width:16%}th:nth-child(4),td:nth-child(4){width:12%}
th{position:sticky;top:0;z-index:1;background:var(--bg);font-size:.82rem;font-weight:500;color:var(--muted);cursor:pointer;white-space:nowrap;user-select:none}
th.asc:after{content:" ↑"}th.desc:after{content:" ↓"}
td:first-child{font-weight:500}td:nth-child(2),td:nth-child(4){white-space:nowrap}td:nth-child(2){color:var(--muted)}
tbody tr:hover{background:#151515}tbody tr:last-child td{border-bottom:0}
.pill{white-space:nowrap}
.pill:before{content:"";display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--c);margin-right:7px;position:relative;top:-1px}
#nomap{font-size:.82rem;color:var(--muted);margin:12px 2px 0}
footer{font-size:.75rem;color:#7a7a7a;padding:16px 24px 28px;text-align:center;line-height:1.7}
.leaflet-popup-content-wrapper,.leaflet-popup-tip{border-radius:var(--rad);background:#151515;color:var(--ink);box-shadow:none}.leaflet-popup-content{font-family:Inter,system-ui,sans-serif;font-size:.85rem;line-height:1.5;margin:10px 14px;color:var(--ink)}.leaflet-popup-close-button{color:var(--muted)!important}
.leaflet-container{font-family:inherit;background:#222529}
.leaflet-top.leaflet-left{margin-top:10px;margin-left:10px}.leaflet-bar,.leaflet-bar a{border-radius:var(--rad)!important;border-color:#333!important}
.leaflet-bar a{background:#161616;color:#eee;border-bottom-color:#2a2a2a}
.leaflet-bar a:hover{background:#222;color:#fff}
.leaflet-control-attribution{background:rgba(0,0,0,.45)!important;color:rgba(255,255,255,.55);font-size:10px;margin:0 8px 8px!important;padding:2px 7px;border-radius:2px}
.leaflet-control-attribution a{color:rgba(255,255,255,.7)}
.pin{background:none!important;border:none!important}
.pin-hit{width:28px;height:28px;display:flex;align-items:flex-end;justify-content:center}
.pin-hit svg{display:block}
tr.ghead td,tr.ghead:hover td{padding:22px 14px 8px;font-family:var(--display);font-size:1.2rem;font-weight:400;letter-spacing:.03em;color:#c8c8c8;background:var(--bg);border-bottom:1px solid var(--line);cursor:default}
#list .ghead{padding:18px 0 8px;font-family:var(--display);font-size:1.2rem;font-weight:400;letter-spacing:.03em;color:#c8c8c8;border-bottom:1px solid var(--line)}
#list .ghead:first-child{padding-top:8px}
.list{display:none}
@media (max-width:600px){
.hwrap{flex-wrap:nowrap;padding:8px 14px;gap:12px;align-items:center}
header .logo{height:32px}
.stat{width:auto;text-align:left;padding-top:0;border-top:0;column-gap:8px}
.stat .n{font-size:32px}
.stat .lbl{font-size:.7rem}
.stat .sub{font-size:.62rem}
main{max-width:none;padding:12px 14px 20px}
#map{height:45vh;min-height:260px}
.mapbar{padding:8px 10px;gap:8px}
.controls{margin:12px 0;flex-direction:column;align-items:stretch;gap:8px}
.controls input[type=search]{flex:none;width:100%;min-width:0}
.seg{width:100%;gap:0;justify-content:space-between}
.seg button{flex:none;padding:8px 0 10px;font-size:.75rem;text-align:left}
.tablewrap{display:none}
.list{display:block;list-style:none;margin:0;padding:0;border-top:0}
.list li{padding:12px 0;border-bottom:1px solid var(--line)}
.l-top{display:flex;justify-content:space-between;align-items:baseline;gap:12px}
.l-top strong{font-weight:600;min-width:0;flex:1;overflow-wrap:anywhere}
.l-top .pill{flex:none;font-size:.82rem}
.l-addr,.l-loc{font-size:.82rem;color:var(--muted);margin-top:2px;overflow-wrap:anywhere;line-height:1.4}
}
@media (max-width:340px){.stat .sub{display:none}}
</style>
<body>
<header><div class="hwrap"><div class="brand"><img class="logo" src="__LOGO__" alt="PEMEX Stations"></div>__STAT__</div></header>
<div class="mapbleed"><div id="map"></div>
<div class="mapbar" id="mapbar"><div class="legend" id="legend"></div></div></div>
<main>
<div class="controls">
 <input type="search" id="q" placeholder="Search station, city or address">
 <div class="seg" id="seg" role="tablist" aria-label="Filter stations">
  <button type="button" class="on" data-f="all" role="tab" aria-selected="true">All</button>
  <button type="button" data-f="CA" role="tab" aria-selected="false">California <span class="c" id="nCA">0</span></button>
  <button type="button" data-f="TX" role="tab" aria-selected="false">Texas <span class="c" id="nTX">0</span></button>
  <button type="button" data-f="leads" role="tab" aria-selected="false">Leads <span class="c" id="nLead">0</span></button>
 </div>
</div>
<div class="panel tablewrap"><table id="tbl"><thead><tr>
<th data-k="Name">Station</th><th data-k="loc">City</th><th data-k="Address">Address</th><th data-k="status">Status</th></tr></thead><tbody></tbody></table></div>
<ul class="list" id="list"></ul>
<p id="nomap"></p>
</main>
<footer>__BUILT__<br>Map data © OpenStreetMap contributors</footer>
<script>
const STATIONS = __DATA__;
const COLORS = {Open:"#3dcc76",Converting:"#fdae61",Planned:"#6ba3e8",Lead:"#c084fc",Unknown:"#9a9a9a"};
STATIONS.forEach(s=>{s.status = COLORS[s.Status] ? s.Status : "Unknown"; s.loc=[s.City,s.State].filter(Boolean).join(", ");});
const $=id=>document.getElementById(id);
const esc=t=>String(t??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const map=L.map("map",{scrollWheelZoom:false,zoomSnap:1}).setView([32.5,-108],5);
map.attributionControl.setPrefix(false);
// Esri public dark-gray canvas (CARTO dark tiles require an API key).
const attrib='© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> © <a href="https://www.esri.com/">Esri</a>';
L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",{maxZoom:16,attribution:attrib}).addTo(map);
L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}",{maxZoom:16,attribution:""}).addTo(map);
const pinPath='d="M8 20.8C8 20.8 14.7 12.8 14.7 8.1A6.7 6.7 0 1 0 1.3 8.1C1.3 12.8 8 20.8 8 20.8Z"';
const pinSvg='<div class="pin-hit"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="22" viewBox="0 0 16 22" aria-hidden="true"><path fill="#d12203" stroke="#fff" stroke-width="1.25" stroke-linejoin="round" '+pinPath+"/></svg></div>";
const hollowSvg='<div class="pin-hit"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="22" viewBox="0 0 16 22" aria-hidden="true"><path fill="#0b0b0b" fill-opacity=".35" stroke="#d12203" stroke-width="1.6" stroke-linejoin="round" '+pinPath+"/></svg></div>";
const pinIcon=L.divIcon({className:"pin",html:pinSvg,iconSize:[28,28],iconAnchor:[14,27],popupAnchor:[0,-20]});
const hollowIcon=L.divIcon({className:"pin",html:hollowSvg,iconSize:[28,28],iconAnchor:[14,27],popupAnchor:[0,-20]});
const PIPE=new Set(["Lead","Planned","Converting"]);
const isPipe=s=>PIPE.has(s.status);
const markers=[];
STATIONS.forEach(s=>{ if(s.lat==null) return;
  const m=L.marker([s.lat,s.lng],{icon:isPipe(s)?hollowIcon:pinIcon,riseOnHover:true,keyboard:true});
  m.bindPopup(`<b>${esc(s.Name)}</b><br>${esc(s.Address)}<br>Status: ${esc(s.status)}`+[["Operator or owner contact","Operator"],["Date branded","Date branded"],["Date debranded","Date debranded"],["Cost estimate","Cost estimate"]].map(([k,l])=>s[k]?`<br>${l}: ${esc(s[k])}`:"").join(""));
  markers.push({s,m});});
const bar=$("mapbar"); if(bar) bar.remove();
$("nCA").textContent=STATIONS.filter(s=>s.status==="Open"&&s.State==="CA").length;
$("nTX").textContent=STATIONS.filter(s=>s.status==="Open"&&s.State==="TX").length;
$("nLead").textContent=STATIONS.filter(isPipe).length;
let filter="all",sortK="loc",sortDir=1;
function visible(s){const q=$("q").value.toLowerCase();
  if(filter==="leads"){if(!isPipe(s))return false;}
  else{if(isPipe(s))return false; if(filter==="CA"&&s.State!=="CA")return false; if(filter==="TX"&&s.State!=="TX")return false;}
  if(q&&!Object.values(s).join(" ").toLowerCase().includes(q))return false; return true;}
const STATE_NAMES={CA:"California",TX:"Texas"};
function stateName(s){return STATE_NAMES[s.State]||s.State;}
function cmp(a,b){const keys=sortK==="loc"?["City","Name"]:[sortK];
  for(const k of keys){const d=String(a[k]??"").localeCompare(String(b[k]??""),undefined,{numeric:true});if(d)return d*sortDir;}return 0;}
function grouped(rows){
  const counts={}; rows.forEach(s=>{const k=stateName(s);counts[k]=(counts[k]||0)+1;});
  const ordered=[...rows].sort((a,b)=>{const d=stateName(a).localeCompare(stateName(b));return d||cmp(a,b);});
  return {ordered,counts};
}
function render(){const {ordered:rows,counts}=grouped(STATIONS.filter(visible));
  let last="",tbl="",lis="";
  if(!rows.length&&filter==="leads"){
    const msg="No leads yet. Add a row with Status Lead in the Sheet.";
    tbl=`<tr class="empty"><td colspan="4">${msg}</td></tr>`;
    lis=`<li class="empty">${msg}</li>`;
  }else rows.forEach(s=>{
    const k=stateName(s);
    if(k!==last){tbl+=`<tr class="ghead"><td colspan="4">${esc(k)} · ${counts[k]}</td></tr>`;lis+=`<li class="ghead">${esc(k)} · ${counts[k]}</li>`;last=k;}
    tbl+=`<tr><td>${esc(s.Name)}</td><td>${esc(s.City)}</td><td>${esc(s.Address)}</td><td><span class="pill" style="--c:${COLORS[s.status]}">${esc(s.status)}</span></td></tr>`;
    lis+=`<li><div class="l-top"><strong>${esc(s.Name)}</strong><span class="pill" style="--c:${COLORS[s.status]}">${esc(s.status)}</span></div><div class="l-addr">${esc(s.Address)}</div></li>`;
  });
  document.querySelector("#tbl tbody").innerHTML=tbl;
  $("list").innerHTML=lis;
  markers.forEach(({s,m})=>{visible(s)?m.addTo(map):m.remove();});
  document.querySelectorAll("th").forEach(th=>th.className=th.dataset.k===sortK?(sortDir>0?"asc":"desc"):"");
  const nm=STATIONS.filter(s=>s.lat==null&&visible(s)).map(s=>s.Name);$("nomap").textContent=nm.length?`Not on map yet (address being confirmed): ${nm.join(", ")}`:"";}
function fitVisible(){
  const pts=markers.filter(({s})=>visible(s)).map(({m})=>m.getLatLng());
  if(!pts.length)return;
  const mobile=window.matchMedia("(max-width:600px)").matches;
  const tight=filter!=="all";
  map.fitBounds(L.latLngBounds(pts),{paddingTopLeft:mobile?[28,20]:[48,tight?56:80],paddingBottomRight:mobile?[28,20]:[48,48],maxZoom:tight?9:6});
}
document.querySelectorAll("th").forEach(th=>th.onclick=()=>{const k=th.dataset.k;sortDir=(sortK===k)?-sortDir:1;sortK=k;render();});
$("q").addEventListener("input",()=>{render();});
document.querySelectorAll("#seg button").forEach(btn=>btn.addEventListener("click",()=>{
  filter=btn.dataset.f;
  document.querySelectorAll("#seg button").forEach(b=>{b.classList.toggle("on",b===btn);b.setAttribute("aria-selected",b===btn?"true":"false");});
  render(); fitVisible();
}));
render();
map.whenReady(()=>{map.invalidateSize(); fitVisible();});
</script></body></html>
"""

def check_build(stations, html_path, csv_path):
    """Assert the built page lists every published station and omits Lost rows and demo data."""
    ids = [s["ID"] for s in stations]
    if not ids:
        sys.exit("Build check failed: no stations")
    if len(ids) != len(set(ids)):
        sys.exit("Build check failed: duplicate station IDs")
    if any(s["Status"] == "Lost" for s in stations):
        sys.exit("Build check failed: Lost stations were not excluded from published data")
    open_n = sum(1 for s in stations if s["Status"] == "Open")
    default_n = len(stations)
    others = {s["Status"] for s in stations} - {"Open", ""}
    if not others and default_n != open_n:
        sys.exit(f"Build check failed: published rows {default_n} != open count {open_n}")
    text = html_path.read_text(encoding="utf-8")
    csv_text = csv_path.read_text(encoding="utf-8")
    if "max-height:70vh" in text or ".tablewrap{overflow:auto" in text:
        sys.exit("Build check failed: table still has an inner scroll box")
    if 'id="list"' not in text or 'id="tbl"' not in text:
        sys.exit("Build check failed: table or phone list markup missing")
    if 'id="seg"' not in text or 'data-f="leads"' not in text:
        sys.exit("Build check failed: All / California / Texas / Leads buttons missing")
    if "No leads yet. Add a row with Status Lead in the Sheet." not in text:
        sys.exit("Build check failed: empty Leads message missing")
    if ".hwrap{flex-wrap:wrap" in text or "border-top:1px solid rgba(255,255,255,.25)" in text:
        sys.exit("Build check failed: phone header still stacks the count under the logo")
    if "height:45vh" not in text or "min-height:260px" not in text:
        sys.exit("Build check failed: phone map height is not 45vh / min 260px")
    if "attributionControl:{prefix:false}" not in text and "setPrefix(false)" not in text:
        sys.exit("Build check failed: Leaflet attribution prefix is still enabled")
    # Ignore the embedded logo data URI when looking for forbidden demo / Lost strings.
    logo_i, logo_j = text.find("data:image/png;base64,"), text.find('"', text.find("data:image/png;base64,"))
    text_no_logo = text if logo_i == -1 else text[:logo_i] + text[logo_j:]
    for blob, label in ((text_no_logo, "index.html"), (csv_text, "stations.csv")):
        lower = blob.lower()
        if "lost" in lower or "us petro" in lower or "showlost" in lower:
            sys.exit(f"Build check failed: Lost or US Petro still in {label}")
        if "leafletjs.com" in lower:
            sys.exit(f"Build check failed: leafletjs.com still in {label}")
        for banned in ("Example lead", "Example data", "DEMO"):
            if banned in blob:
                sys.exit(f"Build check failed: {banned!r} found in {label}")
    # Notes and fuel volume never leave the Sheet
    if "Fuel volume" in text or "Fuel volume" in csv_text:
        sys.exit("Build check failed: fuel volume leaked into public output")
    for s in stations:
        if s["ID"] not in text or s["Name"] not in text:
            sys.exit(f"Build check failed: {s['ID']} {s['Name']!r} missing from index.html")
        if s["ID"] not in csv_text or s["Name"] not in csv_text:
            sys.exit(f"Build check failed: {s['ID']} {s['Name']!r} missing from stations.csv")
        if s["Status"] == "Open" and s["Name"] not in text:
            sys.exit(f"Build check failed: Open station {s['Name']!r} missing from index.html")
    open_names = [s["Name"] for s in stations if s["Status"] == "Open"]
    if len(open_names) != open_n:
        sys.exit("Build check failed: Open name list does not match open count")
    blob_i = text.find("const STATIONS = ")
    if blob_i == -1:
        sys.exit("Build check failed: STATIONS data missing")
    if default_n != open_n and others:
        print(f"Note: published rows ({default_n}) include non-Open statuses {sorted(others)}")


def main():
    all_stations = parse(load_text(sys.argv[1:]))
    stations = [s for s in all_stations if s["Status"] != "Lost"]
    (HERE / "data").mkdir(exist_ok=True)
    csv_path = HERE / "data" / "stations.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
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
    # Header count is Open only; pipeline counts appear on the Leads button, not in the header.
    stat = f'<div class="stat"><div class="n">{len(open_rows)}</div><div class="lbl">Open stations</div>'
    if state_line:
        stat += f'<div class="sub">{html.escape(state_line)}</div>'
    stat += "</div>"
    out = (TEMPLATE.replace("__DATA__", data).replace("__BUILT__", html.escape(built))
           .replace("__LOGO__", logo).replace("__STAT__", stat))
    html_path = HERE / "index.html"
    html_path.write_text(out, encoding="utf-8")
    check_build(stations, html_path, csv_path)
    geo = sum(1 for s in stations if s["lat"] is not None)
    skipped = len(all_stations) - len(stations)
    print(f"Wrote index.html: {len(stations)} stations, {geo} with coordinates, {len(open_rows)} open ({skipped} Lost held in the Sheet only)")


if __name__ == "__main__":
    main()
