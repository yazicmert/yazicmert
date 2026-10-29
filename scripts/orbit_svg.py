"""Generate an animated SVG of Earth and asteroid 85990 (1999 JV6) around the Sun.

Orbital elements of the asteroid are fetched from the JPL Small-Body Database
(falls back to built-in approximate values if the API is unreachable). Both
bodies start the animation at their positions for today's date and move with
Keplerian speeds, so the picture changes every day the workflow runs.

Standard library only, so the workflow needs no pip install.
"""

import json
import math
import os
import sys
import urllib.request
from datetime import datetime, timezone

OUT = sys.argv[1] if len(sys.argv) > 1 else "assets/orbit.svg"

SBDB_URL = "https://ssd-api.jpl.nasa.gov/sbdb.api?sstr=85990"

# Approximate heliocentric elements (J2000 ecliptic), used only if SBDB fails.
JV6_FALLBACK = {
    "a": 1.008, "e": 0.311, "i": 5.4, "om": 125.0, "w": 141.0,
    "ma": 0.0, "epoch": 2460600.5,
}

# Earth: JPL approximate elements (Standish), J2000.
EARTH = {"a": 1.00000261, "e": 0.01671123, "varpi": 102.93768, "L0": 100.46457,
         "Ldot": 35999.37244981}  # deg / Julian century

W, H = 800, 400
CX, CY = 400, 200
SCALE = 125  # px per AU
FRAMES = 120
YEAR_SECONDS = 12.0  # animation seconds per Earth year


def julian_day(dt):
    return dt.timestamp() / 86400.0 + 2440587.5


def fetch_jv6():
    try:
        with urllib.request.urlopen(SBDB_URL, timeout=20) as r:
            data = json.load(r)
        el = {e["name"]: float(e["value"]) for e in data["orbit"]["elements"]}
        return {"a": el["a"], "e": el["e"], "i": el["i"], "om": el["om"],
                "w": el["w"], "ma": el["ma"],
                "epoch": float(data["orbit"]["epoch"])}, True
    except Exception as exc:  # network or format problem: use fallback
        print(f"SBDB fetch failed ({exc}); using fallback elements", file=sys.stderr)
        return JV6_FALLBACK, False


def solve_kepler(M, e):
    E = M if e < 0.8 else math.pi
    for _ in range(50):
        dE = (E - e * math.sin(E) - M) / (1 - e * math.cos(E))
        E -= dE
        if abs(dE) < 1e-12:
            break
    return E


def position(a, e, varpi, M):
    """In-plane position (AU), projected onto the ecliptic with longitude of perihelion varpi."""
    E = solve_kepler(M % (2 * math.pi), e)
    x = a * (math.cos(E) - e)
    y = a * math.sqrt(1 - e * e) * math.sin(E)
    c, s = math.cos(varpi), math.sin(varpi)
    return x * c - y * s, x * s + y * c


def to_px(x, y):
    # SVG y axis points down; flip so motion is counter-clockwise (prograde).
    return CX + x * SCALE, CY - y * SCALE


def track(a, e, varpi, M0, period_days):
    """Positions over one full period, starting at mean anomaly M0."""
    pts = []
    for k in range(FRAMES + 1):
        M = M0 + 2 * math.pi * k / FRAMES
        pts.append(to_px(*position(a, e, varpi, M)))
    return pts


def orbit_path(a, e, varpi):
    pts = [to_px(*position(a, e, varpi, 2 * math.pi * k / 360)) for k in range(361)]
    return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + " Z"


def anim(attr, values, dur):
    vals = ";".join(f"{v:.1f}" for v in values)
    return (f'<animate attributeName="{attr}" values="{vals}" dur="{dur:.2f}s" '
            f'repeatCount="indefinite"/>')


def main():
    now = datetime.now(timezone.utc)
    jd = julian_day(now)

    # Earth today
    T = (jd - 2451545.0) / 36525.0
    L = math.radians(EARTH["L0"] + EARTH["Ldot"] * T)
    e_varpi = math.radians(EARTH["varpi"])
    e_M0 = L - e_varpi
    e_period = 365.25

    # Asteroid today (ecliptic-plane projection; i ~ 5 deg so this is fine visually)
    jv6, live = fetch_jv6()
    if not live and os.path.exists(OUT):
        print(f"keeping existing {OUT}", file=sys.stderr)
        return
    n = 0.01720209895 / jv6["a"] ** 1.5  # rad/day (Gaussian constant)
    a_M0 = math.radians(jv6["ma"]) + n * (jd - jv6["epoch"])
    a_varpi = math.radians(jv6["om"] + jv6["w"])
    a_period = 2 * math.pi / n

    ex, ey = position(EARTH["a"], EARTH["e"], e_varpi, e_M0)
    ax, ay = position(jv6["a"], jv6["e"], a_varpi, a_M0)
    dist_au = math.hypot(ex - ax, ey - ay)
    dist_mkm = dist_au * 149.5978707

    e_track = track(EARTH["a"], EARTH["e"], e_varpi, e_M0, e_period)
    a_track = track(jv6["a"], jv6["e"], a_varpi, a_M0, a_period)
    e_dur = YEAR_SECONDS
    a_dur = YEAR_SECONDS * a_period / e_period

    stars = []
    seed = 85990
    for _ in range(70):
        seed = (seed * 1103515245 + 12345) % 2**31
        sx = seed % W
        seed = (seed * 1103515245 + 12345) % 2**31
        sy = seed % H
        r = 0.6 + (seed % 10) / 12
        dur = 2 + seed % 5
        stars.append(f'<circle cx="{sx}" cy="{sy}" r="{r:.1f}" fill="#fff">'
                     f'<animate attributeName="opacity" values="0.2;0.9;0.2" '
                     f'dur="{dur}s" repeatCount="indefinite"/></circle>')

    source = "JPL SBDB" if live else "approx. elements"
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="Fira Code, monospace">
  <defs>
    <radialGradient id="sun" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#fff7c2"/>
      <stop offset="45%" stop-color="#ffcc33"/>
      <stop offset="100%" stop-color="#ff8800" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="{W}" height="{H}" rx="16" fill="#0b1021"/>
  {"".join(stars)}
  <path d="{orbit_path(EARTH["a"], EARTH["e"], e_varpi)}" fill="none" stroke="#2196F3" stroke-opacity="0.55" stroke-width="1.2"/>
  <path d="{orbit_path(jv6["a"], jv6["e"], a_varpi)}" fill="none" stroke="#ff7b54" stroke-opacity="0.65" stroke-width="1.2" stroke-dasharray="4 4"/>
  <circle cx="{CX}" cy="{CY}" r="22" fill="url(#sun)"/>
  <circle cx="{CX}" cy="{CY}" r="7" fill="#ffd54a"/>
  <circle cx="{e_track[0][0]:.1f}" cy="{e_track[0][1]:.1f}" r="6" fill="#4fc3f7">
    {anim("cx", [p[0] for p in e_track], e_dur)}
    {anim("cy", [p[1] for p in e_track], e_dur)}
  </circle>
  <circle cx="{a_track[0][0]:.1f}" cy="{a_track[0][1]:.1f}" r="4" fill="#ff7b54">
    {anim("cx", [p[0] for p in a_track], a_dur)}
    {anim("cy", [p[1] for p in a_track], a_dur)}
  </circle>
  <text x="24" y="36" fill="#e6edf3" font-size="16" font-weight="600">Earth &amp; 85990 (1999 JV6)</text>
  <text x="24" y="58" fill="#8b949e" font-size="12">Heliocentric view · starts at today's positions</text>
  <circle cx="30" cy="330" r="5" fill="#4fc3f7"/><text x="42" y="334" fill="#c9d1d9" font-size="12">Earth</text>
  <circle cx="30" cy="352" r="4" fill="#ff7b54"/><text x="42" y="356" fill="#c9d1d9" font-size="12">85990 JV6 (a={jv6["a"]:.3f} AU, e={jv6["e"]:.3f})</text>
  <text x="{W - 24}" y="334" fill="#c9d1d9" font-size="12" text-anchor="end">Earth–JV6 today: {dist_au:.3f} AU ({dist_mkm:.1f} M km)</text>
  <text x="{W - 24}" y="356" fill="#8b949e" font-size="11" text-anchor="end">{now:%Y-%m-%d} UTC · {source}</text>
</svg>
'''
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"wrote {OUT}: distance {dist_au:.3f} AU, live={live}")


if __name__ == "__main__":
    main()
