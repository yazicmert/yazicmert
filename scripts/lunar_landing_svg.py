"""Generate an animated SVG of an autonomous lunar landing.

The descent is simulated, not hand-drawn: a 2D point-mass lander under lunar
gravity follows E-guidance (linear-acceleration polynomial guidance). Midway
through the approach a hazard scan flags the nominal site as unsafe and the
guidance is retargeted to a safe cell, as in hazard detection & avoidance.

A small "tonight's Moon" widget shows the current lunar phase, so the image
changes every day the workflow runs.

Standard library only, so the workflow needs no pip install.
"""

import math
import sys
from datetime import datetime, timezone

OUT = sys.argv[1] if len(sys.argv) > 1 else "assets/lunar-landing.svg"

W, H = 800, 420
GROUND_Y = 350
FONT = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

# --- descent simulation (SI units) -----------------------------------------
G_MOON = 1.62
DT = 0.05
X0, H0, VX0, VH0 = -1300.0, 1600.0, 55.0, -15.0
NOMINAL_X, SAFE_X = 0.0, 150.0
GATE_H, GATE_VH = 20.0, -2.0     # end of approach phase, start of terminal descent
T_APPROACH = 55.0                # time to reach the gate [s]
T_SCAN, T_DIVERT = 22.0, 32.0    # hazard scan window; retarget at its end

# --- animation timing ------------------------------------------------------
LOOP = 14.0                      # seconds per loop
DESCENT_ANIM = 10.5              # seconds of the loop spent descending

# --- view mapping (not to scale: vertical exaggerated) ----------------------
PX_PER_M_X = 0.30
PX_PER_M_H = 0.17
ORIGIN_PX = 455


def to_px(x, h):
    return ORIGIN_PX + x * PX_PER_M_X, GROUND_Y - h * PX_PER_M_H


def simulate():
    x, h, vx, vh = X0, H0, VX0, VH0
    t = 0.0
    target_x = NOMINAL_X
    states = []
    while True:
        if t >= T_DIVERT:
            target_x = SAFE_X
        tgo = T_APPROACH - t
        if tgo > 0.5:
            # E-guidance: a = 6(r_f - r - v*T)/T^2 - 2(v_f - v)/T, plus gravity compensation
            ax = 6 * (target_x - x - vx * tgo) / tgo**2 - 2 * (0 - vx) / tgo
            ah = 6 * (GATE_H - h - vh * tgo) / tgo**2 - 2 * (GATE_VH - vh) / tgo
            tx, th = ax, ah + G_MOON
        else:
            # terminal descent: null horizontal velocity, hold constant sink rate
            if tgo > -DT:
                x, vx, vh = target_x, 0.0, GATE_VH
            tx, th = 0.0, G_MOON
            ax, ah = 0.0, 0.0
        states.append((t, x, h, vx, vh, tx, th))
        if h <= 0:
            break
        vx += ax * DT
        vh += ah * DT
        x += vx * DT
        h = max(0.0, h + vh * DT)
        t += DT
    return states


def sample(states, n):
    """n evenly spaced samples over the descent."""
    t_end = states[-1][0]
    out, j = [], 0
    for k in range(n + 1):
        tk = t_end * k / n
        while j < len(states) - 1 and states[j + 1][0] <= tk:
            j += 1
        out.append(states[j])
    return out


def kt(t_sim, t_end):
    """Simulation time -> keyTime fraction of the loop."""
    return DESCENT_ANIM * t_sim / t_end / LOOP


# --- moon phase ------------------------------------------------------------
SYNODIC = 29.530588853
NEW_MOON_JD = 2451550.26  # 2000-01-06 18:14 UTC


def moon_phase(now):
    jd = now.timestamp() / 86400.0 + 2440587.5
    f = ((jd - NEW_MOON_JD) / SYNODIC) % 1.0
    illum = (1 - math.cos(2 * math.pi * f)) / 2
    names = ["New Moon", "Waxing Crescent", "First Quarter", "Waxing Gibbous",
             "Full Moon", "Waning Gibbous", "Last Quarter", "Waning Crescent"]
    name = names[int((f * 8 + 0.5)) % 8]
    return f, illum, name


def moon_svg(cx, cy, r, f):
    waxing = f < 0.5
    illum = (1 - math.cos(2 * math.pi * f)) / 2
    rx = r * abs(math.cos(2 * math.pi * f))
    crescent = illum < 0.5
    limb_sweep = 1 if waxing else 0
    term_sweep = (0 if waxing else 1) if crescent else (1 if waxing else 0)
    lit = (f"M{cx},{cy - r} A{r},{r} 0 0 {limb_sweep} {cx},{cy + r} "
           f"A{rx:.2f},{r} 0 0 {term_sweep} {cx},{cy - r} Z")
    return (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#1c2233"/>'
            f'<path d="{lit}" fill="#e8e4d8"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#3a4560" stroke-width="1"/>')


# --- svg helpers -----------------------------------------------------------
def discrete_text(x, y, items, t_end, size, fill, anchor="start", weight="400"):
    """items: list of (t_sim_start, label). Each label is shown until the next one."""
    parts = []
    for i, (ts, label) in enumerate(items):
        k0 = kt(ts, t_end)
        k1 = kt(items[i + 1][0], t_end) if i + 1 < len(items) else 1.0
        if i + 1 == len(items):
            vals, keys = "0;1", f"0;{k0:.4f}"
        elif k0 <= 0:
            vals, keys = "1;0", f"0;{k1:.4f}"
        else:
            vals, keys = "0;1;0", f"0;{k0:.4f};{k1:.4f}"
        parts.append(
            f'<text x="{x}" y="{y}" fill="{fill}" font-size="{size}" font-weight="{weight}" '
            f'text-anchor="{anchor}" opacity="0">{label}'
            f'<animate attributeName="opacity" values="{vals}" keyTimes="{keys}" '
            f'dur="{LOOP}s" calcMode="discrete" repeatCount="indefinite"/></text>')
    return "".join(parts)


def window(k0, k1, fade=0.01):
    """opacity animation visible between keyTimes k0..k1."""
    return (f'<animate attributeName="opacity" values="0;0;1;1;0;0" '
            f'keyTimes="0;{k0:.4f};{k0 + fade:.4f};{k1 - fade:.4f};{k1:.4f};1" '
            f'dur="{LOOP}s" repeatCount="indefinite"/>')


def rng(seed):
    while True:
        seed = (seed * 1103515245 + 12345) % 2**31
        yield seed


def main():
    now = datetime.now(timezone.utc)
    states = simulate()
    t_end = states[-1][0]
    frames = sample(states, 140)
    k_td = kt(t_end, t_end)

    # lander motion
    keytimes = ";".join(f"{kt(s[0], t_end):.4f}" for s in frames) + ";1"
    pos = [to_px(s[1], s[2]) for s in frames]
    translate = ";".join(f"{px:.1f},{py:.1f}" for px, py in pos) + f";{pos[-1][0]:.1f},{pos[-1][1]:.1f}"
    tilt = [max(-35.0, min(35.0, math.degrees(math.atan2(s[5], s[6])))) for s in frames]
    rotate = ";".join(f"{a:.1f}" for a in tilt) + ";0"

    # flown trajectory, revealed as the lander moves
    path_d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pos)
    travelled = [0.0]
    for i in range(1, len(pos)):
        travelled.append(travelled[-1] + math.dist(pos[i - 1], pos[i]))
    length = travelled[-1]
    offsets = ";".join(f"{length - d:.1f}" for d in travelled) + ";0"

    # telemetry
    tele = sample(states, 28)
    alt_items = [(s[0], f"ALT    {max(0, s[2]):7.0f} m") for s in tele]
    vs_items = [(s[0], f"V-SPD  {s[4]:7.1f} m/s") for s in tele]
    hs_items = [(s[0], f"H-SPD  {s[3]:7.1f} m/s") for s in tele]
    phase_items = [(0, "BRAKING"), (T_SCAN, "HAZARD SCAN"), (T_DIVERT, "DIVERT"),
                   (T_APPROACH, "TERMINAL DESCENT"), (t_end, "TOUCHDOWN ✓")]

    # stars
    g = rng(85990)
    stars = []
    for _ in range(80):
        sx, sy = next(g) % W, next(g) % (GROUND_Y - 40)
        r = 0.4 + (next(g) % 10) / 14
        d = 2 + next(g) % 5
        stars.append(f'<circle cx="{sx}" cy="{sy}" r="{r:.2f}" fill="#fff">'
                     f'<animate attributeName="opacity" values="0.15;0.8;0.15" dur="{d}s" '
                     f'repeatCount="indefinite"/></circle>')

    # terrain
    terrain = [(0, GROUND_Y + 4)]
    for xpx in range(0, W + 1, 20):
        bump = 3 * math.sin(xpx / 37) + 2 * math.sin(xpx / 11.3)
        if 410 < xpx < 540:
            bump *= 0.3
        terrain.append((xpx, GROUND_Y + bump))
    terrain_d = "M0,{} ".format(H) + " ".join(f"L{x},{y:.1f}" for x, y in terrain) + f" L{W},{H} Z"
    far_ridge = ("M0,330 L60,318 L120,326 L190,306 L260,322 L330,314 L400,326 "
                 "L560,318 L640,300 L720,316 L800,308 L800,350 L0,350 Z")

    nx, _ = to_px(NOMINAL_X, 0)
    sx_, _ = to_px(SAFE_X, 0)
    k_scan0, k_scan1 = kt(T_SCAN, t_end), kt(T_DIVERT, t_end)

    # hazard map: 8x8 cells; hazards cluster around the nominal site (crater + boulders)
    cells = []
    hm_x, hm_y, cs = 622, 228, 11
    safe_cell = (6, 4)
    for row in range(8):
        k_row = k_scan0 + (k_scan1 - k_scan0) * (row + 1) / 9
        for col in range(8):
            d = math.hypot(col - 2.5, row - 3.5)
            noise = next(g) % 100
            if d < 2.2 or noise < 9:
                color = "#e5534b"
            elif d < 3.2 or noise < 22:
                color = "#d29922"
            else:
                color = "#3fb950"
            if (col, row) == safe_cell:
                color = "#3fb950"
            cells.append(
                f'<rect x="{hm_x + col * cs}" y="{hm_y + row * cs}" width="{cs - 1.5}" height="{cs - 1.5}" '
                f'rx="1.5" fill="{color}" opacity="0">'
                f'<animate attributeName="opacity" values="0;0;0.85;0.85;0" '
                f'keyTimes="0;{k_row:.4f};{k_row + 0.01:.4f};0.97;1" dur="{LOOP}s" repeatCount="indefinite"/></rect>')
    sel_x, sel_y = hm_x + safe_cell[0] * cs - 1.5, hm_y + safe_cell[1] * cs - 1.5
    phase_f, illum, phase_name = moon_phase(now)

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}">
  <defs>
    <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#05070f"/><stop offset="1" stop-color="#0d1426"/>
    </linearGradient>
    <linearGradient id="regolith" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#8d8a84"/><stop offset="1" stop-color="#3b3a38"/>
    </linearGradient>
    <linearGradient id="beam" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#4fc3f7" stop-opacity="0.45"/><stop offset="1" stop-color="#4fc3f7" stop-opacity="0"/>
    </linearGradient>
    <radialGradient id="plume" cx="0.5" cy="0" r="1">
      <stop offset="0" stop-color="#fff6d5"/><stop offset="0.4" stop-color="#ffb347" stop-opacity="0.8"/>
      <stop offset="1" stop-color="#ff6a00" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="{W}" height="{H}" rx="16" fill="url(#sky)"/>
  {"".join(stars)}

  <!-- terrain -->
  <path d="{far_ridge}" fill="#2a2d33"/>
  <path d="{terrain_d}" fill="url(#regolith)"/>
  <ellipse cx="{nx - 4:.1f}" cy="{GROUND_Y + 3}" rx="20" ry="4" fill="#4a4844"/>
  <ellipse cx="{nx - 4:.1f}" cy="{GROUND_Y + 2}" rx="20" ry="3.2" fill="none" stroke="#a7a49c" stroke-width="0.8"/>
  <ellipse cx="{nx - 34:.1f}" cy="{GROUND_Y + 3}" rx="9" ry="2.2" fill="#4a4844"/>
  <circle cx="{nx + 14:.1f}" cy="{GROUND_Y - 1}" r="2.6" fill="#6b6964"/>
  <circle cx="{nx + 22:.1f}" cy="{GROUND_Y}" r="1.8" fill="#6b6964"/>
  <ellipse cx="180" cy="{GROUND_Y + 12}" rx="26" ry="5" fill="#4a4844" opacity="0.7"/>
  <ellipse cx="690" cy="{GROUND_Y + 18}" rx="34" ry="6" fill="#4a4844" opacity="0.6"/>

  <!-- hazard overlay on terrain -->
  <g opacity="0">{window(k_scan0, 0.97)}
    <rect x="{nx - 30:.1f}" y="{GROUND_Y - 6}" width="44" height="12" rx="2" fill="#e5534b" fill-opacity="0.25" stroke="#e5534b" stroke-width="0.8"/>
  </g>
  <g opacity="0">{window(k_scan1, 0.97)}
    <rect x="{sx_ - 12:.1f}" y="{GROUND_Y - 6}" width="24" height="12" rx="2" fill="#3fb950" fill-opacity="0.2" stroke="#3fb950" stroke-width="0.8"/>
    <path d="M{sx_:.1f},{GROUND_Y - 14} v6 M{sx_:.1f},{GROUND_Y + 8} v6 M{sx_ - 16:.1f},{GROUND_Y} h6 M{sx_ + 10:.1f},{GROUND_Y} h6" stroke="#3fb950" stroke-width="1.2"/>
  </g>

  <!-- flown trajectory -->
  <path d="{path_d}" fill="none" stroke="#4fc3f7" stroke-width="1.2" stroke-dasharray="{length:.1f}" stroke-dashoffset="{length:.1f}" opacity="0.7">
    <animate attributeName="stroke-dashoffset" values="{offsets}" keyTimes="{keytimes}" dur="{LOOP}s" repeatCount="indefinite"/>
  </path>

  <!-- lander -->
  <g>
    <animateTransform attributeName="transform" type="translate" values="{translate}" keyTimes="{keytimes}" dur="{LOOP}s" repeatCount="indefinite"/>
    <animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.02;0.96;1" dur="{LOOP}s" repeatCount="indefinite"/>
    <g opacity="0">{window(k_scan0, k_scan1)}
      <path d="M0,0 L-34,110 L34,110 Z" fill="url(#beam)">
        <animateTransform attributeName="transform" type="rotate" values="-18;18;-18" dur="1.6s" repeatCount="indefinite"/>
      </path>
    </g>
    <g>
      <animateTransform attributeName="transform" type="rotate" values="{rotate}" keyTimes="{keytimes}" dur="{LOOP}s" repeatCount="indefinite"/>
      <path d="M-4,4 L4,4 L7,22 L-7,22 Z" fill="url(#plume)">
        <animate attributeName="opacity" values="1;1;0;0" keyTimes="0;{k_td:.4f};{k_td + 0.005:.4f};1" dur="{LOOP}s" repeatCount="indefinite"/>
        <animateTransform attributeName="transform" type="scale" values="1,1;1,1.25;1,0.9;1,1.15;1,1" dur="0.3s" repeatCount="indefinite"/>
      </path>
      <path d="M-6,1 L-11,9 M6,1 L11,9 M-13,9 h4 M9,9 h4" stroke="#c9d1d9" stroke-width="1.3" fill="none"/>
      <rect x="-6" y="-7" width="12" height="9" rx="1.5" fill="#d4a72c"/>
      <rect x="-4.5" y="-13" width="9" height="6" rx="1.5" fill="#c9d1d9"/>
      <circle cx="0" cy="-10" r="1.4" fill="#4fc3f7"/>
    </g>
  </g>

  <!-- touchdown dust -->
  <g opacity="0">
    <animate attributeName="opacity" values="0;0;0.8;0;0" keyTimes="0;{k_td - 0.03:.4f};{k_td:.4f};{k_td + 0.12:.4f};1" dur="{LOOP}s" repeatCount="indefinite"/>
    <ellipse cx="{sx_:.1f}" cy="{GROUND_Y - 2}" rx="10" ry="3" fill="#b8b4aa">
      <animate attributeName="rx" values="4;4;34;34" keyTimes="0;{k_td - 0.03:.4f};{k_td + 0.12:.4f};1" dur="{LOOP}s" repeatCount="indefinite"/>
    </ellipse>
  </g>

  <!-- title -->
  <text x="26" y="38" fill="#e6edf3" font-size="15" font-weight="600" letter-spacing="2">AUTONOMOUS LUNAR LANDING</text>
  <text x="26" y="58" fill="#8b949e" font-size="11">Powered descent · hazard detection · safe-site divert</text>

  <!-- right HUD column -->
  <g>
    {moon_svg(648, 62, 24, phase_f)}
    <text x="684" y="52" fill="#8b949e" font-size="9" letter-spacing="1">TONIGHT'S MOON</text>
    <text x="684" y="67" fill="#e6edf3" font-size="11">{phase_name}</text>
    <text x="684" y="81" fill="#8b949e" font-size="10">{illum * 100:.0f}% illuminated</text>

    <line x1="622" y1="104" x2="776" y2="104" stroke="#30363d"/>
    <text x="622" y="122" fill="#8b949e" font-size="9" letter-spacing="1">TELEMETRY</text>
    {discrete_text(622, 140, alt_items, t_end, 11, "#e6edf3")}
    {discrete_text(622, 156, vs_items, t_end, 11, "#e6edf3")}
    {discrete_text(622, 172, hs_items, t_end, 11, "#e6edf3")}
    {discrete_text(622, 192, phase_items, t_end, 11, "#4fc3f7", weight="600")}

    <text x="622" y="220" fill="#8b949e" font-size="9" letter-spacing="1">HAZARD MAP</text>
    <rect x="{hm_x - 2}" y="{hm_y - 2}" width="{8 * cs + 2.5}" height="{8 * cs + 2.5}" rx="3" fill="none" stroke="#30363d"/>
    {"".join(cells)}
    <rect x="{sel_x:.1f}" y="{sel_y:.1f}" width="{cs + 1.5}" height="{cs + 1.5}" rx="2" fill="none" stroke="#ffffff" stroke-width="1.4" opacity="0">
      <animate attributeName="opacity" values="0;0;1;0.3;1;1;0" keyTimes="0;{k_scan1:.4f};{k_scan1 + 0.02:.4f};{k_scan1 + 0.05:.4f};{k_scan1 + 0.08:.4f};0.97;1" dur="{LOOP}s" repeatCount="indefinite"/>
    </rect>
  </g>

  <text x="26" y="{H - 14}" fill="#6e7681" font-size="9">E-guidance simulation under lunar gravity · not to scale · {now:%Y-%m-%d}</text>
</svg>
'''
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(svg)
    max_acc = max(math.hypot(s[5], s[6]) for s in states)
    print(f"wrote {OUT}: touchdown t={t_end:.1f}s, max thrust accel {max_acc:.2f} m/s^2, "
          f"moon {phase_name} {illum:.0%}")


if __name__ == "__main__":
    main()
