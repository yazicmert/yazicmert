"""Generate a GitHub activity card styled like the lunar landing animation.

Reads the contribution calendar and repository languages through the GitHub
GraphQL API (token in the METRICS_TOKEN environment variable). If the token is
missing or the API call fails, an existing card is left unchanged.

Standard library only, so the workflow needs no pip install.
"""

import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone

OUT = sys.argv[1] if len(sys.argv) > 1 else "assets/activity.svg"
LOGIN = "yazicmert"
IGNORED_LANGUAGES = {"HTML", "CSS", "Jupyter Notebook"}
TOP_LANGUAGES = 5

W, H = 800, 320
FONT = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
CELL, GAP = 11, 3
LEVELS = ["#161b2e", "#0e4a6e", "#1673a8", "#2196f3", "#7fd0ff"]

QUERY = """
query($login: String!) {
  user(login: $login) {
    repositories(ownerAffiliations: OWNER, isFork: false, first: 100) {
      totalCount
      nodes {
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


def fetch(token):
    body = json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql", data=body,
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]["user"]


def streaks(days):
    """(current, best) streaks in days. Today without contributions does not break the current streak."""
    best = run = 0
    for _, n in days:
        run = run + 1 if n > 0 else 0
        best = max(best, run)
    current = 0
    for i, (d, n) in enumerate(reversed(days)):
        if n > 0:
            current += 1
        elif i == 0 and d == date.today():
            continue
        else:
            break
    return current, best


def languages(user):
    totals = {}
    for repo in user["repositories"]["nodes"]:
        for edge in repo["languages"]["edges"]:
            name, color = edge["node"]["name"], edge["node"]["color"] or "#8b949e"
            if name in IGNORED_LANGUAGES:
                continue
            size, _ = totals.get(name, (0, color))
            totals[name] = (size + edge["size"], color)
    ranked = sorted(totals.items(), key=lambda kv: -kv[1][0])
    total = sum(s for s, _ in totals.values()) or 1
    top = [(n, s / total, c) for n, (s, c) in ranked[:TOP_LANGUAGES]]
    rest = 1 - sum(p for _, p, _ in top)
    if rest > 0.005:
        top.append(("Other", rest, "#3a4560"))
    return top


def level(n, q):
    if n == 0:
        return 0
    return 1 + sum(n > t for t in q)


def render(user, now):
    cal = user["contributionsCollection"]["contributionCalendar"]
    weeks = cal["weeks"]
    days = [(date.fromisoformat(d["date"]), d["contributionCount"])
            for w in weeks for d in w["contributionDays"]]
    current, best = streaks(days)
    nonzero = sorted(n for _, n in days if n > 0) or [1]
    q = [nonzero[int(len(nonzero) * f)] for f in (0.25, 0.5, 0.75)]

    x0, y0 = 30, 150
    grid_w = len(weeks) * (CELL + GAP) - GAP
    x0 = (W - grid_w) // 2

    cells, months = [], []
    last_month = None
    for wi, w in enumerate(weeks):
        x = x0 + wi * (CELL + GAP)
        first = date.fromisoformat(w["contributionDays"][0]["date"])
        if first.month != last_month and first.day <= 7 and wi < len(weeks) - 2:
            months.append(f'<text x="{x}" y="{y0 - 8}" fill="#6e7681" font-size="9">{first:%b}</text>')
            last_month = first.month
        for d in w["contributionDays"]:
            dd = date.fromisoformat(d["date"])
            row = (dd.weekday() + 1) % 7  # Sunday first, like GitHub
            y = y0 + row * (CELL + GAP)
            lv = level(d["contributionCount"], q)
            delay = 0.15 + wi * 0.018
            cells.append(
                f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2.5" fill="{LEVELS[lv]}" opacity="0">'
                f'<animate attributeName="opacity" from="0" to="1" begin="{delay:.2f}s" dur="0.4s" fill="freeze"/>'
                f'<title>{dd:%d %b %Y}: {d["contributionCount"]} contributions</title></rect>')

    grid_h = 7 * (CELL + GAP) - GAP
    stats = [
        (f'{cal["totalContributions"]:,}', "CONTRIBUTIONS · 12 MO"),
        (f"{best} d", "BEST STREAK"),
        (f"{current} d", "CURRENT STREAK"),
        (f'{user["repositories"]["totalCount"]}', "REPOSITORIES"),
    ]
    stat_svg = []
    col_w = grid_w / len(stats)
    for i, (value, label) in enumerate(stats):
        x = x0 + i * col_w
        stat_svg.append(
            f'<text x="{x:.0f}" y="104" fill="#e6edf3" font-size="22" font-weight="600">{value}</text>'
            f'<text x="{x:.0f}" y="122" fill="#8b949e" font-size="9" letter-spacing="1">{label}</text>')

    langs = languages(user)
    bar_y = y0 + grid_h + 34
    bar, legend = [], []
    bx = x0
    lx = x0
    for name, p, color in langs:
        w = grid_w * p
        bar.append(f'<rect x="{bx:.1f}" y="{bar_y}" width="{max(w - 2, 1):.1f}" height="6" rx="3" fill="{color}"/>')
        bx += w
        label = f"{name} {p * 100:.0f}%"
        legend.append(f'<circle cx="{lx + 4}" cy="{bar_y + 24}" r="4" fill="{color}"/>'
                      f'<text x="{lx + 13}" y="{bar_y + 28}" fill="#c9d1d9" font-size="11">{label}</text>')
        lx += 22 + len(label) * 7

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#05070f"/><stop offset="1" stop-color="#0d1426"/>
    </linearGradient>
    <linearGradient id="scan" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#4fc3f7" stop-opacity="0"/>
      <stop offset="0.8" stop-color="#4fc3f7" stop-opacity="0.18"/>
      <stop offset="1" stop-color="#4fc3f7" stop-opacity="0.5"/>
    </linearGradient>
    <clipPath id="grid"><rect x="{x0 - 2}" y="{y0 - 2}" width="{grid_w + 4}" height="{grid_h + 4}"/></clipPath>
  </defs>
  <rect width="{W}" height="{H}" rx="16" fill="url(#bg)"/>
  <text x="{x0}" y="42" fill="#e6edf3" font-size="15" font-weight="600" letter-spacing="2">GITHUB ACTIVITY</text>
  <text x="{x0}" y="62" fill="#8b949e" font-size="11">Contribution log · last 12 months</text>
  <text x="{x0 + grid_w}" y="42" fill="#6e7681" font-size="9" text-anchor="end">UPDATED {now:%Y-%m-%d}</text>
  {"".join(stat_svg)}
  {"".join(months)}
  {"".join(cells)}
  <g clip-path="url(#grid)">
    <rect x="{x0 - 80}" y="{y0 - 2}" width="80" height="{grid_h + 4}" fill="url(#scan)">
      <animate attributeName="x" values="{x0 - 80};{x0 + grid_w}" dur="6s" begin="1.2s" repeatCount="indefinite"/>
    </rect>
  </g>
  <text x="{x0}" y="{bar_y - 10}" fill="#8b949e" font-size="9" letter-spacing="1">LANGUAGES</text>
  {"".join(bar)}
  {"".join(legend)}
</svg>
'''


def main():
    token = os.environ.get("METRICS_TOKEN")
    if not token:
        print("METRICS_TOKEN not set; activity card unchanged", file=sys.stderr)
        return
    try:
        user = fetch(token)
    except Exception as exc:
        print(f"GitHub API failed ({exc}); activity card unchanged", file=sys.stderr)
        return
    svg = render(user, datetime.now(timezone.utc))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
