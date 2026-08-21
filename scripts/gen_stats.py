#!/usr/bin/env python3
"""Genera assets/stats.svg y assets/langs.svg desde la API de GitHub.

No depende de servicios externos: corre en GitHub Actions con GITHUB_TOKEN
y commitea los SVG al repo.
"""
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from xml.sax.saxutils import escape

API = "https://api.github.com/graphql"
LOGIN = os.environ.get("GH_LOGIN", "anthoniriv")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")

BG = "#0d1117"
BORDER = "#1f2733"
ACCENT = "#6366f1"
TEXT = "#c9d1d9"
MUTED = "#8b949e"

if not TOKEN:
    sys.exit("falta GH_TOKEN / GITHUB_TOKEN")


def gql(query, variables):
    req = urllib.request.Request(
        API,
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={
            "Authorization": f"bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "readme-stats",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.load(r)
    if "errors" in body:
        sys.exit("GraphQL: " + json.dumps(body["errors"]))
    return body["data"]


PROFILE_Q = """
query($login:String!) {
  user(login:$login) {
    createdAt
    followers { totalCount }
    pullRequests { totalCount }
    issues { totalCount }
    repositoriesContributedTo(contributionTypes:[COMMIT,PULL_REQUEST,ISSUE,PULL_REQUEST_REVIEW]) { totalCount }
    repositories(first:100, ownerAffiliations:OWNER, isFork:false, orderBy:{field:STARGAZERS, direction:DESC}) {
      totalCount
      nodes {
        stargazerCount
        languages(first:10, orderBy:{field:SIZE, direction:DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""

YEAR_Q = """
query($login:String!, $from:DateTime!, $to:DateTime!) {
  user(login:$login) {
    contributionsCollection(from:$from, to:$to) {
      totalCommitContributions
      restrictedContributionsCount
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


def fetch():
    prof = gql(PROFILE_Q, {"login": LOGIN})["user"]
    created = datetime.fromisoformat(prof["createdAt"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)

    days, commits = {}, 0
    for year in range(created.year, now.year + 1):
        start = max(created, datetime(year, 1, 1, tzinfo=timezone.utc))
        end = min(now, datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc))
        if start >= end:
            continue
        cc = gql(
            YEAR_Q,
            {"login": LOGIN, "from": start.isoformat(), "to": end.isoformat()},
        )["user"]["contributionsCollection"]
        commits += cc["totalCommitContributions"] + cc["restrictedContributionsCount"]
        for week in cc["contributionCalendar"]["weeks"]:
            for d in week["contributionDays"]:
                days[d["date"]] = d["contributionCount"]

    repos = prof["repositories"]["nodes"]
    stars = sum(r["stargazerCount"] for r in repos)

    langs = {}
    for r in repos:
        for e in r["languages"]["edges"]:
            n = e["node"]["name"]
            langs.setdefault(n, {"size": 0, "color": e["node"]["color"] or MUTED})
            langs[n]["size"] += e["size"]

    return {
        "commits": commits,
        "stars": stars,
        "prs": prof["pullRequests"]["totalCount"],
        "issues": prof["issues"]["totalCount"],
        "contributed": prof["repositoriesContributedTo"]["totalCount"],
        "followers": prof["followers"]["totalCount"],
        "repos": prof["repositories"]["totalCount"],
        "total_contribs": sum(days.values()),
        "streaks": streaks(days),
        "langs": langs,
    }


def streaks(days):
    """Racha actual y más larga. Hoy sin commits no rompe la racha todavía."""
    if not days:
        return (0, 0)
    dates = sorted(days)
    longest = run = 0
    prev = None
    for d in dates:
        if days[d] > 0:
            cur = date.fromisoformat(d)
            run = run + 1 if prev and (cur - prev).days == 1 else 1
            longest = max(longest, run)
            prev = cur
        else:
            prev, run = None, 0

    today = date.today()
    cursor = today
    if days.get(today.isoformat(), 0) == 0:
        cursor = today - timedelta(days=1)
    current = 0
    while days.get(cursor.isoformat(), 0) > 0:
        current += 1
        cursor -= timedelta(days=1)
    return (current, longest)


def human(n):
    if n >= 1000:
        return f"{n / 1000:.1f}".rstrip("0").rstrip(".") + "k"
    return str(n)


FONT = "'Segoe UI', Ubuntu, Sans-Serif"


def text(x, y, content, size=14, weight=400, fill=TEXT, anchor="start", extra=""):
    """Atributos inline en vez de <style>: GitHub sanitiza el CSS embebido en SVG."""
    return (
        f'  <text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" '
        f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}"{extra}>{content}</text>'
    )


def card(width, height, title, body):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">
  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="10" fill="{BG}" stroke="{BORDER}"/>
{text(25, 35, escape(title), size=17, weight=600, fill=ACCENT)}
{body}
</svg>
"""


def stats_svg(d):
    cur, long = d["streaks"]
    rows = [
        ("Estrellas totales", human(d["stars"])),
        ("Commits totales", human(d["commits"])),
        ("Pull requests", human(d["prs"])),
        ("Issues", human(d["issues"])),
        ("Contribuyó a", human(d["contributed"])),
        ("Repos públicos", human(d["repos"])),
        ("Racha actual", f"{cur} días"),
        ("Racha más larga", f"{long} días"),
    ]
    body = []
    y = 68
    for k, v in rows:
        body.append(text(25, y, escape(k)))
        body.append(text(375, y, escape(v), weight=700, fill=ACCENT, anchor="end"))
        y += 25
    body.append(text(25, y + 6, f'{human(d["total_contribs"])} contribuciones en total', size=12, fill=MUTED))
    return card(400, y + 26, "Estadísticas de GitHub", "\n".join(body))


def langs_svg(d, top=8):
    items = sorted(d["langs"].items(), key=lambda kv: kv[1]["size"], reverse=True)[:top]
    total = sum(v["size"] for _, v in items) or 1

    bar, x, W = [], 25.0, 350.0
    for name, v in items:
        w = v["size"] / total * W
        bar.append(f'  <rect x="{x:.2f}" y="55" width="{w:.2f}" height="9" fill="{v["color"]}"/>')
        x += w

    rows, y = [], 92
    for i, (name, v) in enumerate(items):
        cx = 25 if i % 2 == 0 else 205
        if i % 2 == 0 and i:
            y += 24
        pct = v["size"] / total * 100
        rows.append(f'  <circle cx="{cx + 6}" cy="{y - 5}" r="5" fill="{v["color"]}"/>')
        rows.append(text(cx + 18, y, f'{escape(name)} <tspan font-size="12" fill="{MUTED}">{pct:.1f}%</tspan>'))

    body = "\n".join(['  <clipPath id="r"><rect x="25" y="55" width="350" height="9" rx="4.5"/></clipPath>',
                      '  <g clip-path="url(#r)">'] + bar + ["  </g>"] + rows)
    return card(400, y + 22, "Lenguajes más usados", body)


def main():
    d = fetch()
    os.makedirs(OUT, exist_ok=True)
    for name, svg in (("stats.svg", stats_svg(d)), ("langs.svg", langs_svg(d))):
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
            f.write(svg)
        print("escrito", name)


if __name__ == "__main__":
    main()
