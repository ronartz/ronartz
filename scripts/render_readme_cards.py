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


def svg(w, h, label, parts, css=""):
    style = "" if STATIC else f"<style>{css}</style>"
    defs = (
        '<defs>'
        '<linearGradient id="fire" x1="0" y1="0" x2="1" y2="0">'
        f'<stop stop-color="{FIRE}"/><stop offset=".6" stop-color="{ORANGE}"/>'
        f'<stop offset="1" stop-color="{GOLD}"/></linearGradient>'
        '<linearGradient id="shine" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0" stop-color="#FFFFFF" stop-opacity="0"/>'
        '<stop offset=".5" stop-color="#FFE5BD" stop-opacity=".8"/>'
        '<stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/></linearGradient>'
        '</defs>'
    )
    base = f'<rect width="{w}" height="{h}" rx="14" fill="{INK}"/>'
    border = f'<rect x="1" y="1" width="{w-2}" height="{h-2}" rx="13" fill="none" stroke="{LINE}" stroke-width="1.3"/>'
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'role="img" aria-label="{esc(label)}">'
        f'<title>{esc(label)}</title>{defs}{style}{base}{border}{"".join(parts)}</svg>\n'
    )


def text(x, y, value, size=18, color=PAPER, weight=400, family="Arial,Helvetica,sans-serif", extra=""):
    return (
        f'<text x="{x}" y="{y}" fill="{color}" font-family="{esc(family)}" '
        f'font-size="{size}" font-weight="{weight}" {extra}>{esc(value)}</text>'
    )


def render_hero(total):
    w, h = 1080, 286
    p = [
        '<rect x="0" y="0" width="11" height="286" rx="5" fill="url(#fire)"/>',
        '<rect x="28" y="26" width="11" height="11" rx="5" fill="#FF7D45"/>',
        text(50, 36, "DEVELOPER / RONARTZ", 14, ORANGE, 700, "monospace", 'letter-spacing="2.5"'),
        text(43, 117, "SHREEJIT", 73, PAPER, 800, extra='class="intro"'),
        text(43, 193, "MONDAL", 76, ORANGE, 800, extra='class="intro second"'),
        '<rect x="45" y="210" width="558" height="2" rx="1" fill="url(#fire)"/>',
        text(45, 244, "PYTHON  /  APPLIED AI  /  CLOUD", 19, "#E9C0A8", 500, "monospace"),
        text(45, 270, "Learning independently. Building with intention.", 15, MUTED),
        '<rect x="722" y="18" width="332" height="248" rx="9" fill="#1B1617" stroke="#5B3226" stroke-width="1"/>',
        text(746, 39, "> portrait.asc", 13, GOLD, 500, "monospace"),
        '<path d="M734 48H1042" stroke="#684030" stroke-opacity=".8"/>',
        '<circle cx="985" cy="36" r="4" fill="#FF512A"/>',
        '<circle cx="1000" cy="36" r="4" fill="#FF9A56"/>',
        '<circle cx="1015" cy="36" r="4" fill="#F6C78A"/>',
    ]
    lines = PORTRAIT.splitlines()
    for i, line in enumerate(lines):
        attr = f'class="portrait" style="animation-delay:{0.34 + i * 0.034:.3f}s"' if not STATIC else ""
        p.append(text(744, 65 + i * 5.9, line, 7.4, "#FFA66E", 400, "monospace", f'xml:space="preserve" {attr}'))
    p += [
        '<rect x="741" y="245" width="294" height="1" fill="#633B2F"/>',
        text(745, 259, f"{total:,} public-profile contributions / last year", 11, MUTED, 400, "monospace"),
    ]
    css = (
        '@keyframes in{0%{opacity:0;transform:translateY(12px)}100%{opacity:1;transform:translateY(0)}}'
        '@keyframes letter{0%{opacity:0}100%{opacity:1}}'
        '.intro{animation:in .65s ease-out both}.intro.second{animation-delay:.15s}'
        '.portrait{animation:letter .25s ease-out both}'
        '@media(prefers-reduced-motion:reduce){.intro,.portrait{animation:none!important}}'
    )
    return svg(w, h, "Shreejit Mondal — Python, AI and cloud developer profile with printing ASCII portrait", p, css)


def metrics(days):
    dates = {dt.date.fromisoformat(row["date"]): row["count"] for row in days}
    today = dt.datetime.now(dt.timezone.utc).date()
    active = sum(1 for n in dates.values() if n > 0)
    total = sum(dates.values())
    longest = 0
    streak = 0
    for day in sorted(dates):
        if dates[day] > 0:
            streak += 1
            longest = max(longest, streak)
        else:
            streak = 0
    current = 0
    cursor = today if dates.get(today, 0) else today - dt.timedelta(days=1)
    while dates.get(cursor, 0) > 0:
        current += 1
        cursor -= dt.timedelta(days=1)
    busiest = max(dates.items(), key=lambda x: x[1])
    return dates, total, active, current, longest, busiest


def render_heatmap(days):
    by_date, total, active, current, longest, busiest = metrics(days)
    today = max(by_date)
    start = today - dt.timedelta(days=364)
    start -= dt.timedelta(days=(start.weekday() + 1) % 7)
    colors = ["#281D1B", "#5B3022", "#984329", "#DC6235", "#FFAD68"]
    p = [
        text(25, 39, "01 / CONTRIBUTION ACTIVITY", 17, ORANGE, 700, "monospace"),
        text(1053, 40, f"{total:,} contributions  ·  {active} active days", 15, MUTED, 400, "monospace", 'text-anchor="end"')
    ]
    for d in range((today - start).days + 1):
        date = start + dt.timedelta(days=d)
        week, weekday = d // 7, (date.weekday() + 1) % 7
        count = by_date.get(date, 0)
        level = 0 if count == 0 else (1 if count == 1 else 2 if count < 4 else 3 if count < 7 else 4)
        delay = .05 + week * .024
        extra = f'class="dot" style="animation-delay:{delay:.2f}s"' if not STATIC else ""
        p.append(f'<rect x="{24 + week*18.5:.1f}" y="{59 + weekday*18}" width="12" height="12" rx="2.5" fill="{colors[level]}" {extra}><title>{esc(str(date))}: {count} contributions</title></rect>')
    p += [text(24, 204, f"Current streak  {current}d", 15, PAPER, 600),
          text(340, 204, f"Longest streak  {longest}d", 15, PAPER, 600),
          text(1030, 204, "LESS", 11, MUTED, 500, "monospace", 'text-anchor="end"')]
    css = ('@keyframes pop{from{opacity:.1;transform:scale(.25)}to{opacity:1;transform:scale(1)}}'
           '.dot{transform-box:fill-box;transform-origin:center;animation:pop .44s ease-out both}'
           '@media(prefers-reduced-motion:reduce){.dot{animation:none!important}}')
    return svg(1080, 222, "Real GitHub contributions over the past year, animated column by column", p, css)


def months_for(today):
    end = today.replace(day=1)
    months = []
    for i in range(11, -1, -1):
        y = end.year
        m = end.month - i
        while m <= 0:
            m += 12
            y -= 1
        months.append((y, m))
    return months


def render_activity(days):
    dates, total, active, current, longest, busiest = metrics(days)
    grouped = defaultdict(int)
    for day, n in dates.items():
        grouped[(day.year, day.month)] += n
    months = months_for(max(dates))
    values = [grouped[m] for m in months]
    highest = max(values) or 1
    best = max(range(12), key=lambda i: values[i])
    p = [text(27, 37, "02 / MONTHLY MOMENTUM", 17, ORANGE, 700, "monospace"),
         text(1053, 36, "Real activity, refreshed daily", 13, MUTED, 400, "monospace", 'text-anchor="end"'),
         '<path d="M35 210H1043" stroke="#6E3830" stroke-width="1"/>']
    for i, ((y, m), n) in enumerate(zip(months, values)):
        height = max(4, (n / highest) * 123)
        x = 49 + i * 82
        y0 = 210 - height
        fill = ORANGE if i == best else ("#B95236" if n else "#46302B")
        anim = f'class="bar" style="animation-delay:{.6+i*.08:.2f}s"' if not STATIC else ""
        p.append(f'<rect x="{x}" y="{y0:.1f}" width="47" height="{height:.1f}" rx="4" fill="{fill}" {anim}/>')
        p.append(text(x + 23.5, 230, calendar.month_abbr[m].upper(), 11, MUTED, 500, "monospace", 'text-anchor="middle"'))
        if n:
            p.append(text(x + 23.5, y0 - 7, str(n), 12, GOLD if i == best else PAPER, 700, "monospace", 'text-anchor="middle"'))
    p += [text(29, 264, f"TOTAL {total:,}", 15, PAPER, 700, "monospace"),
          text(300, 264, f"ACTIVE DAYS {active}", 15, PAPER, 700, "monospace"),
          text(650, 264, f"BEST DAY {busiest[0]} ({busiest[1]})", 15, PAPER, 700, "monospace")]
    css = ('@keyframes grow{from{transform:scaleY(0)}to{transform:scaleY(1)}}'
           '.bar{transform-box:fill-box;transform-origin:center bottom;animation:grow .8s cubic-bezier(.2,.8,.15,1) both}'
           '@media(prefers-reduced-motion:reduce){.bar{animation:none!important}}')
    return svg(1080, 290, "Monthly contribution chart with real totals and busiest day", p, css)


def render_tile(n, heading, subtitle, detail, accent, marker):
    p = [
        f'<rect x="12" y="12" width="316" height="166" rx="10" fill="#211819" stroke="{accent}" stroke-opacity=".45"/>',
        f'<circle class="ring" cx="285" cy="41" r="22" fill="none" stroke="{accent}" stroke-width="2" opacity=".65"/>',
        text(30, 44, marker, 15, accent, 700, "monospace"),
        text(30, 93, heading, 40, PAPER, 800, extra='class="rise"'),
        text(30, 124, subtitle, 15, accent, 700),
        text(30, 153, detail, 13, "#D5B7A7"),
        text(290, 157, "↗", 25, accent, 700),
        '<path class="flash" d="M13 173H327" stroke="url(#fire)" stroke-width="3"/>'
    ]
    css = (
        '@keyframes rise{from{opacity:0;transform:translateY(17px)}to{opacity:1;transform:translateY(0)}}'
        '@keyframes ring{0%,100%{opacity:.25;transform:scale(.85)}50%{opacity:.75;transform:scale(1.15)}}'
        '@keyframes dash{to{stroke-dashoffset:-80}}'
        '.rise{animation:rise .75s 1.4s both}.ring{transform-origin:285px 41px;animation:ring 3s ease-in-out infinite}'
        '.flash{stroke-dasharray:80 120;animation:dash 4s linear infinite}'
        '@media(prefers-reduced-motion:reduce){.rise,.ring,.flash{animation:none!important}}'
    )
    return svg(340, 190, heading + " — " + subtitle, p, css)


def render_repo(title, category, info1, info2, accent, ordinal):
    p = [
        text(26, 32, ordinal + " / " + category.upper(), 13, accent, 700, "monospace"),
        text(26, 80, title, 30, PAPER, 800, extra='class="rise"'),
        text(26, 118, info1, 17, "#E0C4B5"),
        text(26, 144, info2, 17, "#E0C4B5"),
        '<path d="M26 163H490" stroke="#634033" stroke-width="1.3"/>',
        text(495, 169, "↗", 25, accent, 700, extra='text-anchor="end"'),
    ]
    css = ('@keyframes entry{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}'
           '.rise{animation:entry .65s 2s both}'
           '@media(prefers-reduced-motion:reduce){.rise{animation:none!important}}')
    return svg(520, 189, "Featured project: " + title, p, css)


def write(path, content):
    dest = CARDS / path
    dest.parent.mkdir(parents=True, exist_ok=True)
    import xml.etree.ElementTree as ET
    ET.fromstring(content)  # fail instead of publishing a broken SVG
    dest.write_text(content, encoding="utf-8")
    print("Rendered", dest.relative_to(ROOT), len(content), "bytes")


def main():
    days = read_days()
    by_date, total, active, current, longest, busiest = metrics(days)
    write("hero.svg", render_hero(total))
    write("heatmap.svg", render_heatmap(days))
    write("activity.svg", render_activity(days))
    write("build.svg", render_tile("01", "BUILD", "Tools & real projects", "SHINPO, Skill Track, Java", ORANGE, "01 / WORK"))
    write("ai.svg", render_tile("02", "EXPLORE", "Python · AI · Cloud", "Building fundamentals, then RAG", FIRE, "02 / TECH"))
    write("japan.svg", render_tile("03", "JAPAN", "Long-term career goal", "Learning Japanese step by step", GOLD, "03 / FUTURE"))
    write("repo-shinpo.svg", render_repo("SHINPO (進歩)", "AI-assisted", "Local-first productivity desktop app", "React · TypeScript · Tauri", ORANGE, "01"))
    write("repo-skill-track.svg", render_repo("Skill Track", "Student project", "Progress and skills tracking", "College hackathon project", FIRE, "02"))
    write("repo-titanic.svg", render_repo("Titanic Survival", "Data science", "Introductory logistic regression", "Python · ML learning project", GOLD, "03"))
    write("repo-java.svg", render_repo("Java Practice", "Learning", "Foundational coding exercises", "Self-paced OIBSIP tasks", ORANGE, "04"))
    print(f"GitHub real data: total={total}, active={active}, streak={current}, days={len(days)}")


if __name__ == "__main__":
    main()
