#!/usr/bin/env python3
"""Generate self-contained, animated GitHub README SVG cards from real contribution data.

Usage:
    GITHUB_TOKEN=... python scripts/render_readme_cards.py
    STATIC=1 python scripts/render_readme_cards.py  # render without motion
Only Python's standard library is required.
"""
from __future__ import annotations
import calendar
import datetime as dt
import html
import json
import os
from pathlib import Path
import re
import urllib.request
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
CARDS = ROOT / "cards"
DATA = ROOT / "data" / "contributions.json"
USER = "ronartz"
STATIC = os.environ.get("STATIC", "0") == "1"
INK, PAPER, MUTED = "#111012", "#FFF7F0", "#BEA49B"
FIRE, ORANGE, GOLD = "#FF4D31", "#FF874A", "#FFC38A"
PANEL, LINE = "#191415", "#563026"

# A stylized ASCII treatment of a photograph provided by the profile owner.
PORTRAIT = r"""
                .=+*###+-
              +%@@@@@@@@@@%*-
            *@@@@@@@@@@@@@@@@@*-
          :%@@@@@@@@@@@@@@@@@@@@%-
         +@@@@@@@@@@@@@@@@@@@@@@@@-
        =@@@@@@@@@@@@@@@@@@@@@@@@@@:
       :%@@@@@@@@@@@@@@@@@@@@@@@@@@@*.
       #@@@@@@@@@@@@@@@@@@@@@@@@@@@@@%.
      -@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@#
      %@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@+
     .%@@@@@@@@@@%#####*###%%%@@@@@@@@@@
     +@@@@@@@@%%#*****++****###%@@@@@@@@
     #@@@@@@##*++++++++++****##%@@@@@@@@
     *@@@@@*==---====++++++**####@@@@@@@
     +@@@#=-:::::---======++****##@@@@@@
     :@@%--+****++++=====+++*#%###%@@@@@
      %@+=#%@@@@@@@@%#**#%%@@@@@@@@#@@@%
      +%#@#**##%@@@@@%@@@@@@@@@@@@@@@@@-
      .*@#+*#+%@@%%*%@@@@@%%@@@*###%@@#
      =-+=:++-*@%%#=+@%@%*@@@@@*%%*#@@=
      =--+.--==++=--##+%@*###%%%%#**%%%-
      .-.+:.:----::+*:-*@#**********##%.
       : .=-:::---=*::-+#@#*+++++++#+%=
       .. .--=++*+-:.:=+**##***+****+*
       :.....:-=*=+#+=*#%#*####****+*-
       .......::--+*++#@@@%**+*****+*:
         .....::-=+*###@@@#*********=
         ....:=*##****#%%@@@%#*****=
          ..:-#@@**###%@@@@@@%#****.
          .::-+*=---++*#%@@@@%#***-
""".strip("\n")


def get_json_days():
    """Prefer GitHub's official GraphQL contribution calendar."""
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if not token:
        raise RuntimeError("No GitHub token available")
    query = """
      query($login: String!) {
        user(login: $login) {
          contributionsCollection {
            contributionCalendar {
              totalContributions
              weeks { contributionDays { date contributionCount } }
            }
          }
        }
      }
    """
    payload = json.dumps({"query": query, "variables": {"login": USER}}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.github.com/graphql", data=payload,
        headers={"Authorization": "Bearer " + token,
                 "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json",
                 "User-Agent": "ronartz-readme-cards"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        result = json.load(response)
    if result.get("errors") or not result.get("data", {}).get("user"):
        raise RuntimeError("GitHub GraphQL: " + str(result.get("errors", "no user")))
    cal = result["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    days = [
        {"date": day["date"], "count": int(day["contributionCount"])}
        for week in cal["weeks"] for day in week["contributionDays"]
    ]
    if len(days) < 300:
        raise RuntimeError("Incomplete contribution calendar")
    return days


def get_public_days():
    """Public GitHub calendar fallback, independently checks tooltip counts."""
    req = urllib.request.Request(
        f"https://github.com/users/{USER}/contributions",
        headers={"User-Agent": "Mozilla/5.0 (README contribution renderer)"}
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        page = response.read().decode("utf-8", "replace")
    tooltips = {}
    for match in re.finditer(
        r"<tool-tip\b([^>]*)>(.*?)</tool-tip>", page, flags=re.I | re.S
    ):
        attrs, body = match.groups()
        target = re.search(r'\bfor="([^"]+)"', attrs)
        count = re.search(r"([\d,]+)\s+contributions?", html.unescape(re.sub(r"<[^>]+>", " ", body)), re.I)
        if target and count:
            tooltips[target.group(1)] = int(count.group(1).replace(",", ""))
        elif target and re.search(r"No contributions?", body, re.I):
            tooltips[target.group(1)] = 0
    result = {}
    unresolved = 0
    for cell in re.finditer(r"<td\b([^>]*)>", page, re.I | re.S):
        attrs = cell.group(1)
        date = re.search(r'\bdata-date="(\d{4}-\d{2}-\d{2})"', attrs)
        if not date:
            continue
        target = re.search(r'\bid="([^"]+)"', attrs)
        level = re.search(r'\bdata-level="([0-4])"', attrs)
        if target and target.group(1) in tooltips:
            result[date.group(1)] = tooltips[target.group(1)]
        elif level and level.group(1) == "0":
            result[date.group(1)] = 0
        else:
            unresolved += 1
    if len(result) < 300 or unresolved:
        raise RuntimeError(f"Public calendar incomplete ({len(result)} days, {unresolved} unresolved cells)")
    return [{"date": d, "count": n} for d, n in sorted(result.items())]


def read_days():
    try:
        days = get_json_days()
        source = "github-graphql"
    except Exception as gql_error:
        print("GraphQL unavailable:", gql_error)
        try:
            days = get_public_days()
            source = "github-public-calendar"
        except Exception as public_error:
            print("Public calendar unavailable:", public_error)
            if not DATA.exists():
                raise RuntimeError("No verified contribution data; refusing to invent statistics") from public_error
            cached = json.loads(DATA.read_text(encoding="utf-8"))
            days = cached["days"]
            source = cached.get("source", "cached") + " (cached)"
            print("Using previously verified cached contribution data")
    by_date = {}
    for row in days:
        day = dt.date.fromisoformat(row["date"])
        count = int(row["count"])
        if count < 0:
            raise ValueError("Negative contribution count")
        by_date[day.isoformat()] = count
    clean = [{"date": d, "count": n} for d, n in sorted(by_date.items())]
    if len(clean) < 300:
        raise ValueError("Calendar too short to render accurately")
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps({
        "username": USER, "source": source,
        "fetched_on": dt.datetime.now(dt.timezone.utc).date().isoformat(),
        "days": clean,
    }, indent=2) + "\n", encoding="utf-8")
    return clean


def esc(s):
    return html.escape(str(s), quote=True)




# ---------------------------------------------------------------------------
# Profile design: single 880px grid, 4px card insets, 8px shared gutters.
# Original implementation inspired by RichardtJustke's visual layout.
# No sensitive destinations, no fabricated skill levels, no third-party widgets.
# ---------------------------------------------------------------------------
W, THIRD, INSET = 880, 880/3, 4
BG, SURFACE, PANEL = "#08090B", "#0F1014", "#15161B"
TEXT, MUTED, DIM = "#F8F5F1", "#ADABA9", "#78797D"
ORANGE, RED, PEACH = "#FE784A", "#E54D37", "#FFC299"
LINE, LINE_SOFT = "#34343B", "#292A30"
WHITE, DARK = "#FFF9F3", "#18151A"
SANS, MONO = "Arial,Helvetica,sans-serif", "Consolas,Menlo,monospace"


def esc(s):
    return html.escape(str(s), quote=True)


def T(x,y,value,size=16,color=TEXT,weight="normal",family=SANS,extra=""):
    return (f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" fill="{color}" '
            f'font-family="{family}" font-weight="{weight}" {extra}>{esc(value)}</text>')


def R(x,y,w,h,fill,rad=0,extra=""):
    return (f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
            f'rx="{rad}" fill="{fill}" {extra}/>')


def H(x1,x2,y,c=LINE):
    return f'<path d="M{x1:.1f} {y:.1f}H{x2:.1f}" stroke="{c}" stroke-width="1"/>'


STYLE = """
@keyframes enter{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
@keyframes fade{from{opacity:0}to{opacity:1}}
@keyframes pop{from{opacity:.1;transform:scale(.2)}to{opacity:1;transform:scale(1)}}
@keyframes grow{from{transform:scaleY(0)}to{transform:scaleY(1)}}
@keyframes glide{from{transform:translateX(-140px)}to{transform:translateX(320px)}}
@keyframes pulse{0%,100%{opacity:.5}50%{opacity:1}}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes blink{0%,50%{opacity:1}51%,100%{opacity:0}}
.enter{animation:enter .7s cubic-bezier(.2,.75,.2,1) both}
.fade{animation:fade .8s ease both}
.pop{transform-box:fill-box;transform-origin:center;animation:pop .38s ease-out both}
.grow{transform-box:fill-box;transform-origin:bottom;animation:grow .7s cubic-bezier(.2,.75,.2,1) both}
.pulse{animation:pulse 2s ease-in-out infinite}
.spin{transform-box:fill-box;transform-origin:center;animation:spin 22s linear infinite}
.blink{animation:blink .85s steps(1) infinite}
.glint{animation:glide 6s ease-in-out infinite}
@media(prefers-reduced-motion:reduce){*{animation:none!important;opacity:1!important;transform:none!important}}
"""


def wrap_svg(width,height,body,label):
    css = STYLE if not STATIC else "*{animation:none!important;opacity:1!important;transform:none!important}"
    defs = f'''<defs><linearGradient id="heat" x1="0" x2="1">
<stop stop-color="{RED}"/><stop offset=".62" stop-color="{ORANGE}"/>
<stop offset="1" stop-color="{PEACH}"/></linearGradient>
<linearGradient id="sheen" x1="0" x2="1">
<stop stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".25"/>
<stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient></defs>'''
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:g}" height="{height:g}" '
            f'viewBox="0 0 {width:g} {height:g}" role="img" aria-label="{esc(label)}">'
            f'<title>{esc(label)}</title><style>{css}</style>{defs}{body}</svg>\n')


def card(w,h,fill=SURFACE,border=LINE,radius=14):
    return R(INSET+.5,INSET+.5,w-2*INSET-1,h-2*INSET-1,fill,radius,
             f'stroke="{border}" stroke-width="1"')


def section_heading(number,label,subtitle=None):
    b = [T(36,46,number,13,ORANGE,"bold",MONO),
         T(70,46,label,18,TEXT,"bold")]
    if subtitle:
        b.append(T(843,46,subtitle,11,DIM,"normal",MONO,'text-anchor="end"'))
    return "".join(b)


def fade_group(content,delay=0.2):
    return f'<g class="enter" style="animation-delay:{delay:.2f}s">{content}</g>'


def metrics(days):
    dates={dt.date.fromisoformat(item["date"]): int(item["count"]) for item in days}
    total=sum(dates.values())
    active=sum(n>0 for n in dates.values())
    today=dt.datetime.now(dt.timezone.utc).date()
    check=today if dates.get(today,0) else today-dt.timedelta(days=1)
    streak=0
    while dates.get(check,0):
        streak+=1
        check-=dt.timedelta(days=1)
    busiest=max(dates.items(),key=lambda z:z[1])
    months=defaultdict(int)
    for day,n in dates.items():
        months[(day.year,day.month)]+=n
    m0=max(dates).replace(day=1)
    recent=[]
    for offset in range(11,-1,-1):
        absolute=m0.year*12+m0.month-1-offset
        ym=(absolute//12, absolute%12+1)
        recent.append((ym,months.get(ym,0)))
    return dates,total,active,streak,busiest,recent


def make_hero(total):
    w,h=W,326
    p=[card(w,h),R(38,38,8,8,ORANGE,4),T(53,47,"OPEN TO LEARNING & COLLABORATION",12,MUTED,"normal",MONO)]
    p.append(R(36,26,326,37,"#1A1B20",18,f'stroke="{LINE}"'))
    p.append(R(50,39,8,8,ORANGE,4))
    p.append(T(68,50,"BUILDING IN PUBLIC",12,TEXT,"normal",MONO))
    p.append(R(370,26,167,37,"#17171B",18,f'stroke="{LINE}"'))
    p.append(T(387,50,"BCA (HONS) 2027",12,MUTED,"normal",MONO))
    p.append(T(38,137,"Shreejit",64,TEXT,"bold",SANS,
               'letter-spacing="-2" class="enter" style="animation-delay:.25s"'))
    p.append(T(38,202,"Mondal",64,ORANGE,"bold",SANS,
               'letter-spacing="-2" class="enter" style="animation-delay:.72s"'))
    p.append(R(41,216,345,2,ORANGE,1))
    p.append(T(41,253,"Python · AI / RAG · Cloud",18,PEACH,"normal",SANS,
               'class="enter" style="animation-delay:1.25s"'))
    p.append(T(41,281,"Curious about the systems behind",15,MUTED))
    p.append(T(41,301,"the products I build.",15,MUTED))
    # Right-side stylized terminal: geometric and subtle, not noisy.
    p.append(R(572,34,270,258,"#111217",12,f'stroke="{LINE}"'))
    p.append(R(572,34,270,35,"#191B21",12))
    p.append(R(572,57,270,12,"#191B21"))
    for cx,c in [(592,RED),(607,ORANGE),(622,PEACH)]:
        p.append(f'<circle cx="{cx}" cy="52" r="4" fill="{c}"/>')
    p.append(T(645,56,"ronartz — status",11,MUTED,"normal",MONO))
    p.append(T(595,99,"> whoami",14,ORANGE,"normal",MONO))
    p.append(T(595,125,"shreejit.mondal",15,TEXT,"normal",MONO))
    p.append(T(595,163,"> current_focus",14,ORANGE,"normal",MONO))
    p.append(T(595,187,"python / backend / ai",14,TEXT,"normal",MONO))
    p.append(R(594,218,224,1,LINE_SOFT))
    p.append(T(595,251,"learn  →  build  →  refine",12,MUTED,"normal",MONO))
    p.append(R(788,244,7,15,ORANGE,1,'class="blink"'))
    p.append(f'<circle class="pulse" cx="802" cy="276" r="4" fill="{ORANGE}"/>')
    p.append(T(812,279,f"{total:,} contributions",9,DIM,"normal",MONO,'text-anchor="end"'))
    return wrap_svg(w,h,"".join(p),"Animated GitHub developer hero for Shreejit Mondal")


def make_about():
    w,h=W,342
    p=[card(w,h),section_heading("01","About me")]
    lines=[
      "I'm a BCA (Honours) student exploring how",
      "software systems work—from Python and SQL",
      "to cloud services and AI applications.",
      "",
      "I built SHINPO using extensive AI-assisted",
      "development. Now I'm strengthening my",
      "fundamentals and independent problem-solving.",
    ]
    y=91
    for line in lines:
        if line:
            p.append(T(36,y,line,15.3,MUTED))
        y+=24 if line else 15
    p.append(H(36,552,259))
    facts=[
      ("working with","Python, SQL, AWS & Linux"),
      ("exploring","React, TypeScript, Tauri & Docker"),
      ("learning","FastAPI, LLMs & RAG"),
    ]
    for i,(k,v) in enumerate(facts):
        y=282+i*18
        p.append(T(36,y,"› "+k,11.5,ORANGE,"bold",MONO))
        p.append(T(176,y,v,11.5,TEXT,"normal",SANS))
    # Illustration: a cohesive animated code panel.
    p.append(R(592,67,240,240,"#17181E",10,f'stroke="{LINE}"'))
    p.append(T(610,91,"/dev/learning.py",12,PEACH,"normal",MONO))
    p.append(H(609,814,103))
    snippet=[
      ("class Developer:",ORANGE),
      ("  focus = 'fundamentals'",TEXT),
      ("  tools = ['python', 'aws']",TEXT),
      ("  while learning:",ORANGE),
      ("    build()",TEXT),
      ("    understand()",TEXT),
      ("    improve()",TEXT),
    ]
    for i,(line,color) in enumerate(snippet):
        p.append(T(609,129+i*22,line,11.2,color,"normal",MONO,
                   f'class="enter" style="animation-delay:{.65+i*.13:.2f}s"'))
    p.append(f'<circle cx="804" cy="292" r="4" fill="{ORANGE}" class="pulse"/>')
    return wrap_svg(w,h,"".join(p),"About Shreejit, projects and honest learning background")


def make_heatmap(days):
    w,h=W,189
    dates,total,active,streak,busiest,months=metrics(days)
    ordered=sorted(dates.items())
    p=[card(w,h),T(37,37,f"LAST 12 MONTHS  ·  {total:,} CONTRIBUTIONS  ·  {active} ACTIVE DAYS",
                   12,MUTED,"normal",MONO)]
    ramp=["#24252A","#5E332B","#934B36","#C56441",ORANGE]
    for i in range(5):
        p.append(R(743+i*15,29,10,10,ramp[i],2))
    p.append(T(732,38,"LESS",10,DIM,"normal",MONO,'text-anchor="end"'))
    x0,y0=37,59
    for i,(date,count) in enumerate(ordered):
        week,row=i//7,i%7
        if week>53:continue
        level=0 if count==0 else 1 if count==1 else 2 if count<4 else 3 if count<8 else 4
        p.append(R(x0+week*15,y0+row*15,11.7,11.7,ramp[level],2,
                   f'class="pop" style="animation-delay:{.24+week*.025:.3f}s"'))
    p.append(T(37,178,"Real contribution data, updated daily.",10,DIM,"normal",MONO))
    return wrap_svg(w,h,"".join(p),"Real 12 month GitHub contribution heatmap")


def make_activity(days):
    w,h=W,267
    dates,total,active,streak,busiest,months=metrics(days)
    p=[card(w,h)]
    x=37
    rows=[
       ("CURRENT STREAK",f"{streak} days",30,ORANGE),
       ("ACTIVE DAYS",str(active),30,TEXT),
       ("BUSIEST DAY",str(busiest[0]),14,TEXT),
    ]
    for i,(k,v,size,color) in enumerate(rows):
        y=47+i*72
        p.append(fade_group(T(x,y,k,11,DIM,"normal",MONO)+T(x,y+36,v,size,color,"bold",SANS),1.8+i*.16))
    p.append(H(37,239,250))
    p.append(f'<path d="M258 28V239" stroke="{LINE}" stroke-width="1"/>')
    maxv=max([v for _,v in months] or [1]) or 1
    area_x, area_w, base, max_h=283, 539, 224, 136
    gap=10
    bw=(area_w-gap*11)/12
    best=max(range(12),key=lambda i: months[i][1])
    for i,((year,month),v) in enumerate(months):
        bx=area_x+i*(bw+gap)
        bh=max(3, v/maxv*max_h)
        fill=ORANGE if i==best and v else "#36363D"
        p.append(R(bx,base-bh,bw,bh,fill,4,
                 f'class="grow" style="animation-delay:{2.1+i*.09:.2f}s"'))
        p.append(T(bx+bw/2,244,calendar.month_abbr[month].upper(),9,DIM,
                   "normal",MONO,'text-anchor="middle"'))
        if i==best and v:
            p.append(T(bx+bw/2,base-bh-10,str(v),10,ORANGE,"bold",MONO,
                    'text-anchor="middle" class="fade" style="animation-delay:3.25s"'))
    p.append(T(286,46,"CONTRIBUTIONS BY MONTH",11,MUTED,"normal",MONO))
    return wrap_svg(w,h,"".join(p),"Monthly GitHub contribution bars, streak and active days")


def make_tile(name,title,sub,style,delay):
    w,h=THIRD,165
    if style=="orange":fill,fg,muted=ORANGE,DARK,"#4C261F"
    elif style=="light":fill,fg,muted=WHITE,DARK,"#71534A"
    else:fill,fg,muted=SURFACE,TEXT,MUTED
    p=[card(w,h,fill,LINE if style=="dark" else fill,12)]
    p.append(fade_group(T(29,38,name,12,muted,"bold",MONO)+
             T(259,38,"↗",20,fg,"normal",SANS,'text-anchor="end"'),delay))
    p.append(fade_group(T(29,92,title,30,fg,"bold",SANS),delay+.15))
    p.append(fade_group(T(29,129,sub,12.4,muted,"normal",MONO),delay+.26))
    p.append(f'<circle class="pulse" cx="264" cy="139" r="5" fill="{RED if style=="light" else fg}" opacity=".3"/>')
    return wrap_svg(w,h,"".join(p),f"{name} — {title}")


def make_title():
    w,h=W,81
    p=[card(w,h),section_heading("02","Selected work","PROJECTS / 2026")]
    return wrap_svg(w,h,"".join(p),"Featured projects section")


def make_repo(name,category,short1,short2,stack,design,delay):
    w,h=THIRD,237
    p=[card(w,h),T(28,34,category,11,ORANGE,"normal",MONO),
       T(263,35,"↗",20,ORANGE,"normal",SANS,'text-anchor="end"'),
       T(28,74,name,23,TEXT,"bold",SANS),
       T(28,100,short1,12,MUTED),T(28,119,short2,12,MUTED)]
    # Compact abstract original project graphics; illustrative, not app screenshots.
    p.append(R(28,133,237,66,"#1C1D23",7,f'stroke="{LINE_SOFT}"'))
    if design=="focus":
        p += [R(39,145,60,42,"#25252B",6),T(49,170,"25:00",12,ORANGE,"bold",MONO),
              R(111,145,139,9,"#33353B",4),R(111,164,88,8,ORANGE,4),
              R(111,182,122,6,"#35363D",3)]
    elif design=="progress":
        for i,v in enumerate([42,70,102,143]):
            x=42+i*51
            p.append(R(x,185-v/4,14,v/4,ORANGE if i==3 else "#6E4438",3))
        p.append(T(42,152,"skills  /  progress",10,PEACH,"normal",MONO))
    else:
        p += [T(42,153,"> model.fit(X, y)",11,ORANGE,"normal",MONO),
              T(42,173,"accuracy  /  evaluation",10,TEXT,"normal",MONO),
              R(43,181,160,4,LINE,2),R(43,181,99,4,ORANGE,2)]
    p.append(T(28,220,stack,11,PEACH,"normal",MONO))
    return wrap_svg(w,h,"".join(p),name+" featured GitHub project")


def make_toolkit():
    w,h=W,273
    p=[card(w,h),section_heading("03","Tools & technologies","EXPOSURE + LEARNING")]
    p.append(T(36,83,"WORKED WITH / EXPLORED",11,ORANGE,"bold",MONO))
    cats=["Python","Java","SQL","AWS","Linux","Git / GitHub","React","TypeScript","Tauri","Docker"]
    for i,c in enumerate(cats):
        col=i%5; row=i//5;x=35+col*164;y=95+row*47
        p.append(R(x,y,151,35,"#1B1C22",7,f'stroke="{LINE}" class="enter" style="animation-delay:{.3+i*.06:.2f}s"'))
        p.append(R(x+12,y+14,7,7,ORANGE if i in [0,2,3,4] else "#A46D54",3))
        p.append(T(x+28,y+23,c,13,TEXT,"normal",SANS))
    p.append(H(36,844,198))
    p.append(T(36,220,"CURRENTLY LEARNING",11,ORANGE,"bold",MONO))
    p.append(T(36,248,"Python foundations   /   FastAPI & APIs   /   RAG & LLMs   /   Cloud fundamentals",
               13,TEXT))
    p.append(T(844,260,"Skill exposure ≠ professional mastery",9,DIM,"normal",MONO,'text-anchor="end"'))
    return wrap_svg(w,h,"".join(p),"Tools explored and areas currently learning")


def make_contact():
    w,h=W,158
    p=[card(w,h),section_heading("04","Let's connect")]
    p.append(T(36,101,"Interested in useful software and thoughtful collaboration.",19,TEXT))
    p.append(T(36,129,"Say hello, share feedback or check out my projects.",14,MUTED))
    p.append(f'<circle class="pulse" cx="808" cy="95" r="17" fill="none" stroke="{ORANGE}" stroke-width="2"/>')
    p.append(T(800,102,"↗",20,ORANGE))
    return wrap_svg(w,h,"".join(p),"Get in touch — GitHub, LinkedIn and email")


def make_link(name,value,style):
    w,h=THIRD,80
    fill=ORANGE if style=="accent" else WHITE if style=="light" else SURFACE
    color=DARK if style!="dark" else TEXT
    sec="#563323" if style!="dark" else MUTED
    p=[card(w,h,fill,fill if style!="dark" else LINE,12),
       T(26,31,name,11,sec,"bold",MONO),T(27,56,value,14,color,"bold",SANS),
       T(263,55,"↗",19,color,"normal",SANS,'text-anchor="end"')]
    return wrap_svg(w,h,"".join(p),f"{name} — {value}")


def make_footer():
    w,h=W,62
    p=[card(w,h),T(34,39,"© 2026  /  SHREEJIT MONDAL",12,MUTED,"normal",MONO),
       T(844,39,"LEARN · BUILD · IMPROVE",12,ORANGE,"normal",MONO,'text-anchor="end"')]
    return wrap_svg(w,h,"".join(p),"Shreejit Mondal profile footer")


def write(path,content):
    import xml.etree.ElementTree as ET
    ET.fromstring(content)
    destination=CARDS/path
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(content,encoding="utf-8")
    print("Rendered",destination.relative_to(ROOT),len(content),"bytes")


def main():
    days=read_days()
    d,total,active,streak,busiest,months=metrics(days)
    write("v3-hero.svg",make_hero(total))
    write("v3-about.svg",make_about())
    write("v3-heatmap.svg",make_heatmap(days))
    write("v3-activity.svg",make_activity(days))
    write("v3-tile-build.svg",make_tile("BUILD","SHINPO","desktop / productivity","orange",2.7))
    write("v3-tile-learn.svg",make_tile("LEARN","Python + AI","building foundations","light",2.9))
    write("v3-tile-explore.svg",make_tile("EXPLORE","Cloud","AWS / Linux / Docker","dark",3.1))
    write("v3-title-work.svg",make_title())
    write("v3-repo-shinpo.svg",make_repo("SHINPO","01 / DESKTOP","Productivity & focus workspace","AI-assisted development","React · TS · Tauri","focus",3.4))
    write("v3-repo-skill-track.svg",make_repo("Skill Track","02 / STUDENT","Track skills and progress","College hackathon project","Student web app","progress",3.6))
    write("v3-repo-titanic.svg",make_repo("Titanic ML","03 / DATA","Logistic regression","Introductory data science","Python · ML","ml",3.8))
    write("v3-toolkit.svg",make_toolkit())
    write("v3-contact.svg",make_contact())
    write("v3-link-github.svg",make_link("GITHUB","@ronartz","dark"))
    write("v3-link-linkedin.svg",make_link("LINKEDIN","/in/shreejitmondal","light"))
    write("v3-link-email.svg",make_link("EMAIL","Get in touch","accent"))
    write("v3-footer.svg",make_footer())
    print(f"Verified: {total} contributions, {active} active days, {streak} streak days")


if __name__ == "__main__":
    main()
