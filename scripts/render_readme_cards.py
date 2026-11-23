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



# --- Design system -----------------------------------------------------------
# Based on a spacious, editorial stacked-SVG layout, with original artwork.
# Each card is self-contained and requires no external image or font requests.
BG, WHITE, INK = "#F5F0E8", "#FFFCF7", "#221B18"
MUTED, RULE, RED, EMBER, PEACH = "#766D67", "#DDD2C6", "#D84F35", "#EE7945", "#FFD5B6"
SERIF = "Georgia,Times New Roman,serif"
SANS = "Arial,Helvetica,sans-serif"
MONO = "Consolas,Monaco,monospace"


def esc(value):
    return html.escape(str(value), quote=True)


def t(x, y, value, size=16, color=INK, family=SANS, weight="normal", extra=""):
    return (
        f'<text x="{x}" y="{y}" font-family="{esc(family)}" font-size="{size}" '
        f'font-weight="{weight}" fill="{color}" {extra}>{esc(value)}</text>'
    )


def rect(x, y, w, h, fill, radius=0, extra=""):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" {extra}/>'


def svg(w, h, label, parts, css=""):
    defs = (
        '<defs><linearGradient id="brand" x1="0" y1="0" x2="1" y2="0">'
        f'<stop stop-color="{RED}"/><stop offset=".65" stop-color="{EMBER}"/>'
        f'<stop offset="1" stop-color="{PEACH}"/></linearGradient>'
        '<linearGradient id="shine" x1="0" y1="0" x2="1" y2="0">'
        '<stop stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".45"/>'
        '<stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
        f'<clipPath id="tileclip"><rect width="{w}" height="{h}" rx="14"/></clipPath>'
        '</defs>'
    )
    anim = (f'<style>{css}</style>' if not STATIC and css else "")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" aria-label="{esc(label)}">'
        f'<title>{esc(label)}</title>{defs}{anim}'
        + "".join(parts) + '</svg>\n'
    )


def metrics(days):
    dates = {dt.date.fromisoformat(row["date"]): int(row["count"]) for row in days}
    today = dt.datetime.now(dt.timezone.utc).date()
    active = sum(n > 0 for n in dates.values())
    total = sum(dates.values())
    current = 0
    cursor = today if dates.get(today, 0) else today - dt.timedelta(days=1)
    while dates.get(cursor, 0) > 0:
        current += 1
        cursor -= dt.timedelta(days=1)
    longest = 0
    running = 0
    for date in sorted(dates):
        running = running + 1 if dates[date] else 0
        longest = max(longest, running)
    busiest_day, busiest_count = max(dates.items(), key=lambda kv: kv[1])
    return dates, total, active, current, longest, (busiest_day, busiest_count)


def months_for(today):
    end = today.replace(day=1)
    out = []
    for offset in range(11, -1, -1):
        n = end.year * 12 + end.month - 1 - offset
        out.append((n // 12, n % 12 + 1))
    return out


COMMON_ANIM = (
    '@keyframes rise{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:none}}'
    '@keyframes fade{from{opacity:0}to{opacity:1}}'
    '@keyframes pop{from{opacity:0;transform:scale(.25)}to{opacity:1;transform:scale(1)}}'
    '@keyframes grow{from{transform:scaleY(0)}to{transform:scaleY(1)}}'
    '@keyframes glow{0%,100%{opacity:.4}50%{opacity:1}}'
    '.rise{animation:rise .85s cubic-bezier(.2,.7,.2,1) both}'
    '.fade{animation:fade .75s ease-out both}'
    '.pop{transform-box:fill-box;transform-origin:center;animation:pop .45s ease-out both}'
    '.grow{transform-box:fill-box;transform-origin:bottom;animation:grow .85s cubic-bezier(.2,.8,.2,1) both}'
    '.glow{animation:glow 2.1s ease-in-out infinite}'
    '@media(prefers-reduced-motion:reduce){.rise,.fade,.pop,.grow,.glow{animation:none!important;opacity:1!important;transform:none!important}}'
)


def render_hero(total):
    w, h = 880, 416
    p = [
        rect(0, 0, w, h, BG, 14),
        rect(0, 0, 9, h, RED, 0),
        rect(35, 40, 8, 8, RED, 4),
        t(54, 49, "A PERSONAL BUILD LOG", 12, MUTED, MONO, "bold", 'letter-spacing="2.0"'),
        t(35, 154, "Shreejit", 90, INK, SERIF, "normal", 'class="rise" style="animation-delay:.08s"'),
        t(35, 242, "Mondal.", 91, RED, SERIF, "normal", 'font-style="italic" class="rise" style="animation-delay:.20s"'),
        rect(37, 265, 448, 2, RED),
        t(37, 301, "Python / Applied AI / Cloud", 22, INK, SANS, "bold", 'class="rise" style="animation-delay:.38s"'),
        t(37, 331, "A student, a curious builder,", 17, MUTED, SANS, "normal", 'class="rise" style="animation-delay:.47s"'),
        t(37, 353, "and someone who loves making things work.", 17, MUTED, SANS, "normal", 'class="rise" style="animation-delay:.56s"'),
        rect(37, 381, 111, 23, "#FFE0CB", 11),
        t(50, 397, "BCA  ·  2027", 11, "#7F3E2C", MONO, "bold"),
        rect(160, 381, 136, 23, "#F2E5D9", 11),
        t(172, 397, "learning in public", 11, "#65574E", MONO),
        rect(545, 25, 301, 354, WHITE, 13),
        rect(557, 37, 277, 330, "#FFF8EF", 8, f'stroke="{RULE}" stroke-width=".8"'),
        t(573, 58, "portrait.txt", 12, RED, MONO, "bold"),
        '<circle class="glow" cx="807" cy="52" r="4.2" fill="#E85F37"/>',
        '<path d="M570 68H818" stroke="#DAC5B4" stroke-width="1"/>',
    ]
    lines = PORTRAIT.splitlines()
    for i, ln in enumerate(lines):
        delay = .45 + i * .033
        p.append(t(581, 91 + i * 8.4, ln, 10.5, "#8D452D", MONO, "normal",
                   f'xml:space="preserve" class="fade" style="animation-delay:{delay:.3f}s"'))
    p.extend([
        t(574, 349, f"{total:,} real contributions / past year", 11, MUTED, MONO),
        '<path d="M0 414H880" stroke="#E8A57F" stroke-width="2"/>',
    ])
    return svg(w, h, "Shreejit Mondal — editorial orange profile hero with a printing ASCII portrait", p, COMMON_ANIM)


def render_heatmap(days):
    w, h = 880, 244
    dates, total, active, current, longest, busiest = metrics(days)
    today = max(dates)
    start = today - dt.timedelta(days=364)
    start -= dt.timedelta(days=(start.weekday()+1)%7)
    palette = ["#F0E7DE", "#F9CCAF", "#F5A47D", "#EB754C", "#CA4E32"]
    p = [
        rect(0, 0, w, h, WHITE, 14),
        t(36, 37, "GITHUB / THE LAST 365 DAYS", 12, MUTED, MONO, "bold", 'letter-spacing="1.2"'),
        t(36, 88, f"{total:,}", 54, INK, SERIF, "normal", 'class="rise" style="animation-delay:.55s"'),
        t(145, 88, "contributions", 42, RED, SERIF, "normal", 'font-style="italic" class="rise" style="animation-delay:.63s"'),
        t(839, 38, f"{active} active days", 12, MUTED, MONO, "normal", 'text-anchor="end"'),
        '<path d="M35 101H845" stroke="#E7DAD0" stroke-width="1"/>',
    ]
    n_weeks = ((today-start).days)//7 + 1
    step = 15.2
    for i in range((today - start).days+1):
        date = start + dt.timedelta(days=i)
        week, weekday = divmod(i, 7)
        n = dates.get(date, 0)
        level = 0 if n == 0 else 1 if n <= 1 else 2 if n < 4 else 3 if n < 8 else 4
        delay = .75 + week * .019
        x, y = 37 + week*step, 115 + weekday*14.0
        p.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="10.7" height="10.7" rx="2" fill="{palette[level]}" class="pop" style="animation-delay:{delay:.3f}s"><title>{esc(date)}: {n} contributions</title></rect>')
    p.append(t(37, 231, "Each square is a day of actual activity.", 12, MUTED, MONO))
    p.append(t(842, 231, "less   • • • •   more", 12, MUTED, MONO, "normal", 'text-anchor="end"'))
    return svg(w, h, "Real GitHub contribution calendar animated from left to right", p, COMMON_ANIM)


def render_activity(days):
    w, h = 880, 340
    dates, total, active, current, longest, busiest = metrics(days)
    months = months_for(max(dates))
    grouped = defaultdict(int)
    for date, n in dates.items():
        grouped[(date.year, date.month)] += n
    values = [grouped[month] for month in months]
    peak = max(values) or 1
    best_i = max(range(len(values)), key=lambda i: values[i])
    p = [
        rect(0, 0, w, h, BG, 14),
        t(36, 40, "THE LAST 12 MONTHS, IN COMMITS", 12, MUTED, MONO, "bold", 'letter-spacing="1.2"'),
        t(36, 96, f"{total:,}", 55, INK, SERIF),
        t(146, 96, "contributions", 42, RED, SERIF, "normal", 'font-style="italic"'),
        '<path d="M38 273H590" stroke="#CEBDB0" stroke-width="1"/>',
        '<path d="M626 45V297" stroke="#D6CAC0" stroke-width="1"/>',
    ]
    for i, (ym, n) in enumerate(zip(months, values)):
        barh = max(4, int((n / peak)*108))
        x = 44 + i*45
        y = 273-barh
        col = RED if i == best_i and n > 0 else ("#38302C" if n else "#DDCFC5")
        p.append(rect(x, y, 30, barh, col, 3,
                      f'class="grow" style="animation-delay:{1.45+i*.066:.2f}s"'))
        p.append(t(x+15, 297, calendar.month_abbr[ym[1]], 11, MUTED, MONO, extra='text-anchor="middle"'))
        if n and i == best_i:
            p.append(t(x+15, y-9, n, 12, RED, MONO, "bold",
                       'text-anchor="middle" class="fade" style="animation-delay:2.6s"'))
    p += [
        t(38, 322, "A quiet visual record of showing up and building.", 12, MUTED, SANS),
        t(654, 88, f"{current}", 47, INK, SERIF),
        t(708, 87, "day current streak", 15, MUTED, SANS),
        '<path d="M651 111H841" stroke="#D6CAC0"/>',
        t(654, 153, f"{active}", 45, INK, SERIF),
        t(725, 150, "active days", 15, MUTED, SANS),
        '<path d="M651 176H841" stroke="#D6CAC0"/>',
        t(654, 220, f"{busiest[1]}", 45, INK, SERIF),
        t(709, 218, "busiest day", 15, MUTED, SANS),
        t(654, 241, str(busiest[0]), 12, MUTED, MONO),
    ]
    return svg(w, h, "Monthly contributions as animated bars with verified streaks and active days", p, COMMON_ANIM)


def render_tile(label, number, headline, desc1, desc2, fill, foreground, accent, delay):
    w, h = 293, 222
    p = [
        '<g class="tile" clip-path="url(#tileclip)" style="animation-delay:'+str(delay)+'s">',
        rect(0, 0, w, 210, fill, 14),
        t(24, 36, label, 13, foreground, MONO, "bold", 'letter-spacing="1.5"'),
        t(260, 37, "↗", 20, foreground, SANS, extra='class="nudge"'),
        t(23, 111, number, 62, foreground, SERIF),
        t(24, 152, headline, 19, foreground, SANS, "bold"),
        t(24, 174, desc1, 13, foreground),
        t(24, 191, desc2, 13, foreground),
        '<circle class="ring" cx="253" cy="172" r="31" fill="none" stroke="'+foreground+'" stroke-opacity=".50" stroke-width="2"/>',
        '<path class="shine" d="M-110 0H-18V220H-110Z" fill="url(#shine)"/>',
        '</g>',
    ]
    css = COMMON_ANIM + (
        '@keyframes tilein{0%{opacity:0;transform:translateY(85px) scale(.82) rotate(-5deg)}'
        '60%{opacity:1;transform:translateY(-7px) scale(1.02) rotate(1deg)}'
        '85%{transform:translateY(2px) scale(.99)}100%{transform:none;opacity:1}}'
        '@keyframes nudge{50%{transform:translate(4px,-3px)}100%{transform:none}}'
        '@keyframes waves{0%{opacity:.6;transform:scale(.55)}100%{opacity:0;transform:scale(2.25)}}'
        '@keyframes sweep{0%{transform:translateX(0)}32%,100%{transform:translateX(495px)}}'
        '.tile{transform-box:fill-box;transform-origin:center;animation:tilein 1s cubic-bezier(.2,.7,.2,1) both}'
        '.nudge{animation:nudge 1.8s ease-in-out infinite}'
        '.ring{transform-origin:253px 172px;animation:waves 2.8s ease-out infinite}'
        '.shine{animation:sweep 5.4s ease-in-out infinite}'
        '@media(prefers-reduced-motion:reduce){.tile,.nudge,.ring,.shine{animation:none!important;opacity:1!important;transform:none!important}.ring,.shine{display:none}}'
    )
    return svg(w, h, label + " — " + headline, p, css)


def render_section_title(headline, code):
    p = [
        rect(0, 0, 880, 75, BG, 0),
        t(36, 55, headline, 38, INK, SERIF, "normal", 'font-style="italic"'),
        t(839, 53, code, 12, RED, MONO, "bold", 'text-anchor="end" letter-spacing="1"'),
        '<path d="M36 71H843" stroke="#DBCDC1" stroke-width="1"/>'
    ]
    return svg(880, 75, headline, p)


def skill_chip(x, y, label, strong=False, width=143, delay=2.0):
    p = [
        rect(x, y, width, 33, "#F8E7D8" if strong else "#F6F0E8", 7,
             f'stroke="{("#F1BE9E" if strong else "#DED1C5")}" stroke-width="1" class="rise" style="animation-delay:{delay:.2f}s"'),
        rect(x+12, y+14, 5, 5, RED if strong else "#BE937B", 3),
        t(x+26, y+22, label, 13, INK, SANS, "bold" if strong else "normal"),
    ]
    return p


def render_skills():
    w, h = 880, 255
    p = [
        rect(0, 0, w, h, WHITE, 14),
        t(29, 34, "WORKED WITH / EXPLORED", 12, RED, MONO, "bold", 'letter-spacing="1.2"'),
        t(841, 34, "through projects + coursework", 12, MUTED, MONO, extra='text-anchor="end"'),
    ]
    used = ["Python", "Java", "SQL", "AWS", "Linux", "Git / GitHub", "React", "TypeScript", "Tauri", "Docker"]
    for i, label in enumerate(used):
        x, y = 30+(i%5)*164, 48+(i//5)*44
        p += skill_chip(x, y, label, strong=False, width=149, delay=1.9+i*.055)
    p += [
        '<path d="M30 150H849" stroke="#D8CCC1"/>',
        t(30, 173, "CURRENTLY LEARNING / DEEPENING", 12, RED, MONO, "bold", 'letter-spacing="1.0"'),
    ]
    topics = ["Python foundations", "Backend APIs", "RAG + LLMs", "Cloud fundamentals"]
    for i, label in enumerate(topics):
        x = 30 + i*205
        p += skill_chip(x, 186, label, strong=True, width=188, delay=2.55+i*.09)
    p += [t(30, 241, "Experience levels vary; listed tools are learning exposure, not a claim of expertise.", 12, MUTED, SANS)]
    return svg(w, h, "Tools used or explored and skills currently being developed", p, COMMON_ANIM)


def render_repo(title, ordinal, category, description1, description2, accent, delay):
    w, h = 439, 206
    p = [
        rect(0, 0, w, h, WHITE, 11, f'stroke="{RULE}" stroke-width="1"'),
        rect(0, 0, 6, h, accent, 2),
        t(25, 38, ordinal + " / " + category.upper(), 12, RED, MONO, "bold", 'letter-spacing=".7"'),
        t(411, 39, "↗", 24, RED, SANS, extra='text-anchor="end" class="nudge"'),
        t(25, 98, title, 39, INK, SERIF, extra=f'class="rise" style="animation-delay:{delay}s"'),
        t(25, 138, description1, 15, MUTED),
        t(25, 160, description2, 15, MUTED),
        '<path d="M25 181H408" stroke="#E2D4C6" stroke-width="1"/>',
        rect(25, 181, 75, 2, accent),
    ]
    css = COMMON_ANIM + ('@keyframes nudge{50%{transform:translate(3px,-3px)}100%{transform:none}}'
                        '.nudge{animation:nudge 2s ease-in-out infinite}'
                        '@media(prefers-reduced-motion:reduce){.nudge{animation:none}}')
    return svg(w, h, "Featured project " + title, p, css)


def write(path, content):
    import xml.etree.ElementTree as ET
    ET.fromstring(content)  # prevent publishing malformed XML
    dest = CARDS / path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    print("Rendered", dest.relative_to(ROOT), len(content), "bytes")


def main():
    days = read_days()
    _, total, active, _, _, _ = metrics(days)
    write("hero.svg", render_hero(total))
    write("heatmap.svg", render_heatmap(days))
    write("activity.svg", render_activity(days))
    write("build.svg", render_tile("01 / BUILD", "04", "featured projects", "Desktop, web and data.", "Built through practice.", "#DC553D", "#FFF8F1", "#FFBDA2", 2.95))
    write("ai.svg", render_tile("02 / LEARN", "AI", "and backend systems", "Python, APIs and RAG.", "Strengthening fundamentals.", "#ED8A51", "#271815", "#FFE0BC", 3.15))
    write("grow.svg", render_tile("03 / GROW", "∞", "always improving", "Curiosity over titles.", "Understanding each step.", "#F6CDAE", "#271815", "#D95D40", 3.35))
    write("title-skills.svg", render_section_title("The tools I'm growing with", "01 / TOOLKIT"))
    write("skills.svg", render_skills())
    write("title-work.svg", render_section_title("Selected work", "02 / PROJECTS"))
    write("repo-shinpo.svg", render_repo("SHINPO (進歩)", "01", "DESKTOP / AI-ASSISTED", "Local-first productivity workspace.", "React, TypeScript, Tauri.", RED, 3.8))
    write("repo-skill-track.svg", render_repo("Skill Track", "02", "STUDENT PROJECT", "Skills and progress tracking.", "College hackathon work.", EMBER, 3.95))
    write("repo-titanic.svg", render_repo("Titanic Prediction", "03", "DATA SCIENCE", "Introductory logistic regression.", "Python ML learning exercise.", "#CB6B43", 4.1))
    write("repo-java.svg", render_repo("Java Practice", "04", "PROGRAMMING EXERCISES", "Self-paced beginner exercises.", "Java fundamentals and OOP.", "#DE8F55", 4.25))
    print(f"Refreshed verified GitHub stats: {total} contributions, {active} active days, {len(days)} calendar days")


if __name__ == "__main__":
    main()
