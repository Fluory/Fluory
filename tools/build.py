#!/usr/bin/env python3
"""Builds the README graphics and the project blocks from tools/projects.json.

    pip install fonttools brotli
    python3 tools/build.py            # write
    python3 tools/build.py --check    # exit 1 if a generated file is out of date

The output is deterministic (font subsets keep the source timestamp), so
--check can run in CI.

Writes:
  assets/hero-dark.svg, assets/hero-light.svg
  assets/card-<id>-dark.svg, assets/card-<id>-light.svg
  the block between <!-- projects:start --> and <!-- projects:end --> in README.md
  the block between <!-- projects:start --> and <!-- projects:end --> in docs/index.html

Every SVG is self-contained (fonts as subset woff2 data URIs, CSS animation
only, no script, no external reference) because GitHub serves README images
through its image proxy as plain <img>.
"""
from __future__ import annotations

import base64
import html
import io
import json
import math
import re
from functools import lru_cache
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "docs" / "fonts"
ASSETS = ROOT / "assets"

FONT_FILES = {
    "serif": (FONTS / "instrument-serif-italic.woff2", None),
    "sans": (FONTS / "instrument-sans-wght.woff2", 430),
    "sans-sb": (FONTS / "instrument-sans-wght.woff2", 600),
    "mono": (FONTS / "jetbrains-mono-wght.woff2", 420),
}
FAMILY = {
    "serif": "'FH Serif', 'Instrument Serif', Georgia, 'Times New Roman', serif",
    "sans": "'FH Sans', 'Instrument Sans', 'Segoe UI', Helvetica, Arial, sans-serif",
    "sans-sb": "'FH Sans SB', 'Instrument Sans', 'Segoe UI', Helvetica, Arial, sans-serif",
    "mono": "'FH Mono', 'JetBrains Mono', ui-monospace, Menlo, Consolas, monospace",
}
FACE_NAME = {"serif": "FH Serif", "sans": "FH Sans", "sans-sb": "FH Sans SB", "mono": "FH Mono"}

THEMES = {
    "dark": dict(
        bg="#050608", bg2="#0b0e13", fg="#ecebe6", fg2="rgba(236,235,230,0.78)",
        fg3="rgba(236,235,230,0.56)", line="rgba(236,235,230,0.13)", line2="rgba(236,235,230,0.26)",
        ice="#9fd3ff", ice2="#5aa7e6", paper="#11151c", dot="#ecebe6", dotop="0.26", band="#9fd3ff",
        panel="rgba(8,10,14,0.86)", gold="#f1c27d",
    ),
    "light": dict(
        bg="#f4f3ee", bg2="#fbfaf7", fg="#0d0f12", fg2="rgba(13,15,18,0.76)",
        fg3="rgba(13,15,18,0.58)", line="rgba(13,15,18,0.12)", line2="rgba(13,15,18,0.24)",
        ice="#1f6fb0", ice2="#3b8fd4", paper="#ffffff", dot="#0d0f12", dotop="0.2", band="#1f6fb0",
        panel="rgba(251,250,247,0.9)", gold="#a86a12",
    ),
}

EASE_IO = "cubic-bezier(0.65,0,0.35,1)"
EASE_OUT = "cubic-bezier(0.16,1,0.3,1)"


# ---------------------------------------------------------------- fonts
@lru_cache(maxsize=None)
def base_font(kind: str) -> TTFont:
    path, wght = FONT_FILES[kind]
    font = TTFont(path, recalcTimestamp=False)
    if "fvar" in font:
        axes = {a.axisTag: a.defaultValue for a in font["fvar"].axes}
        if wght is not None:
            axes["wght"] = wght
        font = instancer.instantiateVariableFont(font, axes)
    buf = io.BytesIO()
    font.flavor = None
    font.save(buf)
    return TTFont(io.BytesIO(buf.getvalue()), recalcTimestamp=False)


def text_width(kind: str, text: str, size: float, tracking: float = 0.0) -> float:
    font = base_font(kind)
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]
    upm = font["head"].unitsPerEm
    total = 0
    for ch in text:
        g = cmap.get(ord(ch)) or cmap.get(ord("?"))
        total += hmtx[g][0]
    return total * size / upm + tracking * max(len(text) - 1, 0)


def font_face(kind: str, text: str) -> str:
    font = TTFont(io.BytesIO(_raw(kind)), recalcTimestamp=False)
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["kern", "liga"]
    opts.name_IDs = [1]
    opts.hinting = False
    opts.notdef_outline = False
    opts.desubroutinize = True
    sub = subset.Subsetter(opts)
    sub.populate(text="".join(sorted(set(text + " "))))
    sub.subset(font)
    buf = io.BytesIO()
    font.flavor = "woff2"
    font.save(buf)
    data = base64.b64encode(buf.getvalue()).decode()
    style = "italic" if kind == "serif" else "normal"
    return (f"@font-face{{font-family:'{FACE_NAME[kind]}';font-style:{style};"
            f"src:url(data:font/woff2;base64,{data}) format('woff2')}}")


@lru_cache(maxsize=None)
def _raw(kind: str) -> bytes:
    buf = io.BytesIO()
    base_font(kind).save(buf)
    return buf.getvalue()


def wrap(kind: str, text: str, size: float, width: float) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if text_width(kind, trial, size) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def esc(s: str) -> str:
    return html.escape(s, quote=True)


class Text:
    """Collects text per font kind so each SVG embeds only the glyphs it uses."""

    def __init__(self):
        self.used: dict[str, str] = {}

    def __call__(self, kind, x, y, s, size, fill, extra="", tracking=0.0, anchor=None):
        cmap = base_font(kind).getBestCmap()
        missing = sorted({ch for ch in s if not ch.isspace() and ord(ch) not in cmap})
        assert not missing, f"font {kind!r} has no glyph for {missing} in {s!r}: it would render in a fallback font"
        self.used[kind] = self.used.get(kind, "") + s
        attrs = f'x="{x:g}" y="{y:g}" font-family="{FAMILY[kind]}" font-size="{size:g}" fill="{fill}"'
        if kind == "serif":
            attrs += ' font-style="italic"'
        if kind == "sans-sb":
            attrs += ' font-weight="600"'
        if tracking:
            attrs += f' letter-spacing="{tracking:g}"'
        if anchor:
            attrs += f' text-anchor="{anchor}"'
        return f"<text {attrs}{extra}>{esc(s)}</text>"

    def faces(self):
        return "".join(font_face(k, v) for k, v in self.used.items())


# Every animation runs a fixed 1.8 times and then holds its state at 80 % of the
# loop, where each card shows its finished picture (rows filled, route drawn,
# bars grown). GitHub shows README images as <img>; a viewer cannot pause them,
# so motion must end on its own (about 18–22 s). Chromium does not pass
# prefers-reduced-motion into SVG images (checked 2026-11-20 with an <img> page
# under emulated "reduce": still moving), so the media query in svg_doc() helps
# only where a browser does; the finite loop count is what every viewer gets.
LOOPS = "1.8"


def svg_doc(w, h, title, desc, style, body):
    reduce = ("@media (prefers-reduced-motion: reduce){*{animation:none!important}}")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
        f'role="img" aria-labelledby="t d">'
        f"<title id=\"t\">{esc(title)}</title><desc id=\"d\">{esc(desc)}</desc>"
        f"<style>{style}{reduce}</style>{body}</svg>\n"
    )


# ---------------------------------------------------------------- halftone
def halftone(x0, y0, x1, y1, step, radius_fn, buckets=(0.7, 1.1, 1.5, 1.9, 2.3, 2.7, 3.1)):
    """Dot field as a few round-capped zero-length paths, one per dot size."""
    groups: dict[float, list[str]] = {b: [] for b in buckets}
    y = y0
    row = 0
    while y <= y1:
        x = x0 + (step / 2 if row % 2 else 0)
        while x <= x1:
            r = radius_fn(x, y)
            if r >= buckets[0] * 0.8:
                b = min(buckets, key=lambda v: abs(v - r))
                groups[b].append(f"M{x:.0f} {y:.0f}h0")
            x += step
        y += step * 0.866
        row += 1
    out = []
    for b, cmds in groups.items():
        if cmds:
            out.append(f'<path stroke-width="{b * 2:.1f}" d="{"".join(cmds)}"/>')
    return "".join(out)


def smooth(e0, e1, x):
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------- hero
def hero(theme: str) -> str:
    c = THEMES[theme]
    W, H = 1200, 480
    T = Text()

    def r_fn(x, y):
        fade = smooth(470, 820, x)
        dx, dy = (x - 1010) / 360, (y - 210) / 260
        glow = math.exp(-(dx * dx + dy * dy) * 1.25)
        wave = 0.5 + 0.5 * math.sin(x * 0.012 + y * 0.02)
        return fade * (0.6 + 2.9 * glow * (0.7 + 0.3 * wave))

    dots = halftone(440, 22, 1186, 466, 15, r_fn)

    # Document cards drifting in from the left of the field, turning into rows.
    docs, rows, css = [], [], []
    starts = [(560, 88, -9), (600, 286, 7), (700, 176, -4)]
    mids = [(706, 108, -3), (744, 268, 3), (796, 190, -1)]
    arrive = [32, 48, 64]  # percent of the loop
    table_x, table_y, row_h = 892, 194, 48
    for i in range(3):
        sx, sy, sr = starts[i]
        mx, my, mr = mids[i]
        tx, ty = table_x + 4, table_y + i * row_h
        a = arrive[i]
        lines = "".join(
            f'<rect x="12" y="{22 + k * 14}" width="{[54, 46, 58, 38, 50][k]}" height="4" rx="2" '
            f'fill="{c["ice"] if k == 2 else c["fg3"]}" opacity="{1 if k == 2 else 0.55}"/>'
            for k in range(5)
        )
        docs.append(
            f'<g class="doc d{i}"><rect width="84" height="104" rx="7" fill="{c["paper"]}" '
            f'stroke="{c["line2"]}"/><rect x="12" y="10" width="22" height="4" rx="2" fill="{c["fg2"]}"/>'
            f'<path d="M64 0v14h20" fill="none" stroke="{c["line2"]}"/>{lines}</g>'
        )
        css.append(
            f".d{i}{{transform:translate({mx}px,{my}px) rotate({mr}deg) scale(1,1);"
            f"opacity:{1 if i == 2 else 0};animation:dk{i} 12s {EASE_IO} {LOOPS} both}}"
            f"@keyframes dk{i}{{0%,{a - 27}%{{transform:translate({sx}px,{sy}px) rotate({sr}deg) scale(1,1);opacity:0}}"
            f"{a - 21}%{{opacity:1}}"
            f"{a - 8}%{{transform:translate({mx}px,{my}px) rotate({mr}deg) scale(1,1);opacity:1}}"
            f"{a}%{{transform:translate({tx}px,{ty}px) rotate(0deg) scale(2.9,0.36);opacity:0}}"
            f"100%{{transform:translate({tx}px,{ty}px) rotate(0deg) scale(2.9,0.36);opacity:0}}}}"
        )
        ry = table_y + i * row_h
        filled = (
            f'<g class="row r{i}"><rect x="{table_x}" y="{ry}" width="252" height="38" rx="7" fill="{c["bg2"]}" stroke="{c["line2"]}"/>'
            f'<rect x="{table_x + 14}" y="{ry + 17}" width="{[44, 52, 38][i]}" height="4" rx="2" fill="{c["fg3"]}"/>'
            f'<rect x="{table_x + 84}" y="{ry + 16}" width="{[76, 58, 68][i]}" height="6" rx="3" fill="{c["fg"]}"/>'
            f'<rect x="{table_x + 184}" y="{ry + 11}" width="54" height="16" rx="8" fill="none" stroke="{c["ice"]}"/>'
            f'<circle cx="{table_x + 196}" cy="{ry + 19}" r="3" fill="{c["ice"]}"/>'
            f'<rect x="{table_x + 205}" y="{ry + 17}" width="24" height="4" rx="2" fill="{c["ice"]}" opacity="0.7"/></g>'
        )
        empty = (f'<rect x="{table_x}" y="{ry}" width="252" height="38" rx="7" fill="none" '
                 f'stroke="{c["line2"]}" stroke-dasharray="3 5"/>')
        rows.append(empty + filled)
        css.append(
            f".r{i}{{transform-origin:{table_x}px {ry}px;opacity:{1 if i < 2 else 0};"
            f"animation:rk{i} 12s {EASE_OUT} {LOOPS} both}}"
            f"@keyframes rk{i}{{0%,{a - 2}%{{opacity:0;transform:scale(0.96,1)}}"
            f"{a + 5}%,88%{{opacity:1;transform:scale(1,1)}}95%,100%{{opacity:0;transform:scale(1,1)}}}}"
        )

    panel = (
        f'<rect x="{table_x - 20}" y="{table_y - 62}" width="292" height="230" rx="14" fill="{c["panel"]}" stroke="{c["line"]}"/>'
        + T("mono", table_x, table_y - 30, "FELD", 11, c["fg3"], tracking=1.4)
        + T("mono", table_x + 84, table_y - 30, "WERT", 11, c["fg3"], tracking=1.4)
        + T("mono", table_x + 184, table_y - 30, "QUELLE", 11, c["fg3"], tracking=1.4)
        + f'<path d="M{table_x} {table_y - 18}h252" stroke="{c["line"]}"/>'
        + "".join(rows)
    )

    # Travelling light band across the dot field.
    band = (
        f'<linearGradient id="bg" x1="0" x2="1"><stop offset="0" stop-color="#000"/>'
        f'<stop offset="0.5" stop-color="#fff"/><stop offset="1" stop-color="#000"/></linearGradient>'
        f'<mask id="m" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{H}">'
        f'<rect class="band" x="0" y="-80" width="320" height="{H + 160}" fill="url(#bg)"/></mask>'
    )
    css.append(
        f".band{{transform:translate(760px,0) skewX(-14deg);animation:bd 11s {EASE_IO} {LOOPS} both}}"
        f"@keyframes bd{{0%{{transform:translate(280px,0) skewX(-14deg)}}100%{{transform:translate(1240px,0) skewX(-14deg)}}}}"
        f".doc,.row,.band{{transform-box:view-box}}"
        f".pulse{{animation:pl 4s {EASE_IO} {LOOPS} both}}@keyframes pl{{0%,100%{{opacity:.35}}50%{{opacity:1}}}}"
    )

    name = "Florian Hein"
    name_size = 112
    assert text_width("serif", name, name_size) < 520, text_width("serif", name, name_size)
    l1, l2 = "Software-Prototypen", "für Unternehmen · Heilbronn"
    tsize = 33
    assert text_width("sans", l2, tsize) < 470, text_width("sans", l2, tsize)

    text = (
        f'<g class="a"><circle class="pulse" cx="70" cy="83" r="4" fill="{c["ice"]}"/></g>'
        + T("mono", 84, 88, "FLUORY · 49.14° N 9.22° E", 13, c["fg3"], tracking=1.6)
        + T("serif", 60, 222, name, name_size, c["fg"], tracking=-1)
        + T("sans", 64, 290, l1, tsize, c["fg"])
        + T("sans", 64, 330, l2, tsize, c["fg2"])
        + f'<path d="M64 384h40" stroke="{c["ice"]}" stroke-width="1.5"/>'
        + T("mono", 118, 388, "Weniger abtippen. Mehr entscheiden.", 13, c["fg3"], tracking=0.4)
    )

    body = (
        f'<defs>{band}<g id="f" fill="none" stroke-linecap="round">{dots}</g></defs>'
        f'<rect width="{W}" height="{H}" rx="20" fill="{c["bg"]}"/>'
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="19.5" fill="none" stroke="{c["line"]}"/>'
        f'<use href="#f" stroke="{c["dot"]}" opacity="{c["dotop"]}"/>'
        f'<g class="a"><use href="#f" stroke="{c["band"]}" opacity="0.9" mask="url(#m)"/></g>'
        f'<g class="a">{panel}{"".join(docs)}</g>'
        f"{text}"
    )
    return svg_doc(
        W, H, "Florian Hein – Software-Prototypen für Unternehmen · Heilbronn",
        "Ein Punktraster mit wanderndem Lichtband; Dokumentkarten schweben hinein und werden zu geordneten Tabellenzeilen.",
        T.faces() + "".join(css), body,
    )


# ---------------------------------------------------------------- glyphs (96 x 96 boxes)
def glyph(kind: str, c: dict, big: bool = False) -> tuple[str, str]:
    """Returns (svg, css) for a small looping glyph drawn in a 0..96 box."""
    st = c["fg2"]
    if kind == "extract":
        # A document whose lines light up one by one and land as fields; one export.
        rows, css = [], []
        for i in range(3):
            y = 26 + i * 18
            d0 = 6 + i * 16
            rows.append(
                f'<rect class="ex q{i}" x="10" y="{y}" width="{[44, 36, 40][i]}" height="5" rx="2.5" fill="{c["ice"]}"/>'
                f'<rect x="10" y="{y}" width="{[44, 36, 40][i]}" height="5" rx="2.5" fill="{c["fg3"]}" opacity=".35"/>'
                f'<g class="ex f{i}"><rect x="116" y="{y - 5}" width="86" height="15" rx="4" fill="none" stroke="{c["ice"]}"/>'
                f'<rect x="123" y="{y}" width="{[40, 52, 34][i]}" height="5" rx="2.5" fill="{c["fg"]}"/>'
                f'<circle cx="194" cy="{y + 2.5}" r="2.5" fill="{c["ice"]}"/></g>'
                f'<path class="ex w{i}" d="M58 {y + 2.5}C84 {y + 2.5} 88 {y + 2.5} 112 {y + 2.5}" fill="none" '
                f'stroke="{c["ice"]}" stroke-width="1.2" stroke-dasharray="60" pathLength="60"/>'
            )
            css.append(
                f".q{i}{{opacity:1;animation:qq{i} 10s {EASE_IO} {LOOPS} both}}"
                f"@keyframes qq{i}{{0%,{d0}%{{opacity:0}}{d0 + 4}%,86%{{opacity:1}}94%,100%{{opacity:0}}}}"
                f".w{i}{{stroke-dashoffset:60;animation:ww{i} 10s {EASE_IO} {LOOPS} both}}"
                f"@keyframes ww{i}{{0%,{d0 + 3}%{{stroke-dashoffset:60;opacity:1}}{d0 + 10}%{{stroke-dashoffset:0;opacity:1}}{d0 + 16}%,100%{{stroke-dashoffset:-60;opacity:0}}}}"
                f".f{i}{{opacity:1;animation:ff{i} 10s {EASE_OUT} {LOOPS} both}}"
                f"@keyframes ff{i}{{0%,{d0 + 8}%{{opacity:0;transform:translateX(-6px)}}{d0 + 14}%,86%{{opacity:1;transform:translateX(0)}}94%,100%{{opacity:0}}}}"
            )
        svg = (
            f'<rect x="0" y="6" width="66" height="84" rx="6" fill="{c["paper"]}" stroke="{c["line2"]}"/>'
            f'<rect x="10" y="14" width="20" height="4" rx="2" fill="{c["fg2"]}"/>'
            + "".join(rows)
            + f'<rect x="10" y="80" width="30" height="3" rx="1.5" fill="{c["fg3"]}" opacity=".35"/>'
            f'<g class="ex ship"><rect x="214" y="30" width="34" height="34" rx="8" fill="none" stroke="{c["line2"]}"/>'
            f'<path d="M223 47l5 5 10-11" fill="none" stroke="{c["ice"]}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></g>'
        )
        css.append(
            f".ship{{opacity:1;animation:sh 10s {EASE_OUT} {LOOPS} both}}"
            f"@keyframes sh{{0%,58%{{opacity:.25}}64%,86%{{opacity:1}}94%,100%{{opacity:.25}}}}"
        )
        return svg, "".join(css)

    if kind == "sync":
        svg = (
            f'<rect x="4" y="30" width="30" height="22" rx="4" fill="none" stroke="{st}" stroke-width="1.5"/>'
            f'<path d="M0 58h38" stroke="{st}" stroke-width="1.5" stroke-linecap="round"/>'
            f'<rect x="62" y="30" width="30" height="22" rx="4" fill="none" stroke="{st}" stroke-width="1.5"/>'
            f'<path d="M58 58h38" stroke="{st}" stroke-width="1.5" stroke-linecap="round"/>'
            f'<path d="M38 41h20" stroke="{c["line2"]}" stroke-dasharray="2 4" stroke-width="1.5" stroke-linecap="round"/>'
            f'<g class="ex"><circle class="pk" cx="38" cy="41" r="3.2" fill="{c["ice"]}"/></g>'
            f'<rect x="41" y="70" width="14" height="11" rx="2.5" fill="none" stroke="{c["fg3"]}" stroke-width="1.3"/>'
            f'<path d="M44 70v-3a4 4 0 0 1 8 0v3" fill="none" stroke="{c["fg3"]}" stroke-width="1.3"/>'
            f'<rect class="ex s1" x="9" y="35" width="20" height="3" rx="1.5" fill="{c["ice"]}"/>'
            f'<rect class="ex s2" x="67" y="35" width="20" height="3" rx="1.5" fill="{c["ice"]}"/>'
        )
        css = (
            f".pk{{animation:pk 8s {EASE_IO} {LOOPS} both}}"
            f"@keyframes pk{{0%,8%{{transform:translateX(0);opacity:0}}12%{{opacity:1}}40%{{transform:translateX(20px);opacity:1}}"
            f"46%,54%{{transform:translateX(20px);opacity:0}}58%{{opacity:1}}86%{{transform:translateX(0);opacity:1}}92%,100%{{transform:translateX(0);opacity:0}}}}"
            f".s1,.s2{{transform-box:fill-box;transform-origin:left center}}"
            f".s1{{animation:s1 8s {EASE_OUT} {LOOPS} both}}@keyframes s1{{0%,4%{{transform:scaleX(.2)}}10%,90%{{transform:scaleX(1)}}100%{{transform:scaleX(.2)}}}}"
            f".s2{{animation:s2 8s {EASE_OUT} {LOOPS} both}}@keyframes s2{{0%,40%{{transform:scaleX(.2)}}48%,90%{{transform:scaleX(1)}}100%{{transform:scaleX(.2)}}}}"
        )
        return svg, css

    if kind == "tile":
        island = ["..##..", ".####.", "######", ".#####", "..###.", "...#.."]
        cells, size, gap = [], 12, 3
        new = (4, 4)
        for r, rowtxt in enumerate(island):
            for q, ch in enumerate(rowtxt):
                x, y = 3 + q * (size + gap), 3 + r * (size + gap)
                if (q, r) == new:
                    cells.append(f'<rect class="ex nt" x="{x}" y="{y}" width="{size}" height="{size}" rx="2" fill="{c["ice"]}"/>'
                                 f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="2" fill="none" stroke="{c["ice"]}" stroke-dasharray="2 2" opacity=".5"/>')
                elif ch == "#":
                    shade = c["fg3"] if (q + r) % 3 else c["fg2"]
                    cells.append(f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="2" fill="{shade}" opacity=".8"/>')
                else:
                    cells.append(f'<rect x="{x + 5}" y="{y + 5}" width="2" height="2" fill="{c["line2"]}"/>')
        css = (
            f".nt{{transform-box:fill-box;transform-origin:center;animation:nt 8s {EASE_OUT} {LOOPS} both}}"
            f"@keyframes nt{{0%,18%{{transform:scale(0);opacity:0}}30%{{transform:scale(1.15);opacity:1}}38%,86%{{transform:scale(1);opacity:1}}96%,100%{{transform:scale(.4);opacity:0}}}}"
        )
        return "".join(cells), css

    if kind == "wish":
        star = [
            "....#....", "....#....", "...###...", "#########", ".#######.",
            "..#####..", "..##.##..", ".##...##.", ".#.....#.",
        ]
        px, out, css, n = 9, [], [], 0
        order = []
        for r, rowtxt in enumerate(star):
            for q, ch in enumerate(rowtxt):
                if ch == "#":
                    order.append((q, r))
        total = len(order)
        for idx, (q, r) in enumerate(order):
            x, y = 7 + q * px, 7 + r * px
            t = 8 + 52 * idx / total
            out.append(f'<rect class="ex p{idx}" x="{x}" y="{y}" width="{px - 1}" height="{px - 1}" fill="{c["gold"] if r < 4 else c["ice"]}"/>')
            css.append(f".p{idx}{{animation:p{idx} 9s linear {LOOPS} both}}"
                       f"@keyframes p{idx}{{0%,{t:.1f}%{{opacity:.1}}{t + 2:.1f}%,82%{{opacity:1}}90%,100%{{opacity:.1}}}}")
        return "".join(out), "".join(css)

    if kind == "grow":
        branches = (
            "M48 92V58 M48 74 L34 62 M48 66 L62 52 M48 58 L40 44 M48 58 L56 40 "
            "M34 62 L26 54 M62 52 L72 48 M40 44 L36 34 M56 40 L60 30"
        )
        svg = (
            f'<path d="M20 92h56" stroke="{c["line2"]}" stroke-width="1.5" stroke-linecap="round"/>'
            f'<path class="ex br" d="{branches}" fill="none" stroke="{c["fg2"]}" stroke-width="2" '
            f'stroke-linecap="round" pathLength="100" stroke-dasharray="100"/>'
            + "".join(
                f'<circle class="ex lf l{i}" cx="{x}" cy="{y}" r="3.4" fill="{c["ice"]}"/>'
                for i, (x, y) in enumerate([(26, 54), (72, 48), (36, 34), (60, 30)])
            )
            + "".join(
                f'<path class="ex rn r{i}" d="M{x} 6v7" stroke="{c["ice"]}" stroke-width="1.4" stroke-linecap="round"/>'
                for i, x in enumerate([22, 46, 70, 84])
            )
        )
        css = (
            f".br{{stroke-dashoffset:0;animation:br 10s {EASE_IO} {LOOPS} both}}"
            f"@keyframes br{{0%,4%{{stroke-dashoffset:100}}56%,88%{{stroke-dashoffset:0}}98%,100%{{stroke-dashoffset:100}}}}"
            f".lf{{transform-box:fill-box;transform-origin:center}}"
            + "".join(
                f".l{i}{{animation:lf{i} 10s {EASE_OUT} {LOOPS} both}}@keyframes lf{i}{{0%,{48 + i * 4}%{{transform:scale(0)}}{56 + i * 4}%,88%{{transform:scale(1)}}96%,100%{{transform:scale(0)}}}}"
                for i in range(4)
            )
            + "".join(
                f".r{i}{{animation:rn 10s linear {LOOPS} both;animation-delay:{-i * 0.7:.1f}s}}" for i in range(4)
            )
            + "@keyframes rn{0%{transform:translateY(0);opacity:0}4%{opacity:.9}22%{transform:translateY(34px);opacity:0}100%{transform:translateY(34px);opacity:0}}"
        )
        return svg, css

    if kind == "cockpit":
        heights = [30, 52, 40, 66]
        bars, css = [], []
        for i, h in enumerate(heights):
            x = 8 + i * 20
            bars.append(f'<rect x="{x}" y="{86 - 66}" width="12" height="66" rx="3" fill="{c["line"]}" opacity=".55"/>'
                        f'<rect class="ex b{i}" x="{x}" y="{86 - h}" width="12" height="{h}" rx="3" fill="{c["ice"] if i == 3 else c["fg3"]}"/>')
            css.append(
                f".b{i}{{transform-box:fill-box;transform-origin:bottom;animation:b{i} 9s {EASE_OUT} {LOOPS} both}}"
                f"@keyframes b{i}{{0%,{6 + i * 6}%{{transform:scaleY(.12)}}{20 + i * 6}%,86%{{transform:scaleY(1)}}96%,100%{{transform:scaleY(.12)}}}}"
            )
        line = "M14 62 L34 44 L54 52 L74 24"
        svg = (
            f'<path d="M4 90h88" stroke="{c["line2"]}" stroke-width="1.5" stroke-linecap="round"/>'
            + "".join(bars)
            + f'<path class="ex ln" d="{line}" fill="none" stroke="{c["fg"]}" stroke-width="1.6" stroke-linejoin="round" '
            f'stroke-linecap="round" pathLength="100" stroke-dasharray="100"/>'
            f'<circle class="ex dt" cx="74" cy="24" r="3.4" fill="{c["fg"]}"/>'
        )
        css.append(
            f".ln{{stroke-dashoffset:0;animation:ln 9s {EASE_IO} {LOOPS} both}}@keyframes ln{{0%,40%{{stroke-dashoffset:100}}62%,86%{{stroke-dashoffset:0}}96%,100%{{stroke-dashoffset:100}}}}"
            f".dt{{transform-box:fill-box;transform-origin:center;animation:dt 9s {EASE_OUT} {LOOPS} both}}@keyframes dt{{0%,60%{{transform:scale(0)}}66%,86%{{transform:scale(1)}}96%,100%{{transform:scale(0)}}}}"
        )
        return svg, "".join(css)

    if kind == "route":
        stops = [(12, 74), (30, 30), (58, 50), (84, 18), (80, 78)]
        order = [0, 1, 2, 3, 4]
        pts = [stops[i] for i in order]
        d = "M" + " L".join(f"{x} {y}" for x, y in pts)
        seg = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
        total = sum(seg)
        # Van keyframes along the straight segments, 12% .. 62% of the loop.
        kf, acc = [], 0.0
        kf.append(f"0%,12%{{transform:translate({pts[0][0]}px,{pts[0][1]}px);opacity:0}}14%{{opacity:1}}")
        for i, s in enumerate(seg):
            acc += s
            p = 12 + 50 * acc / total
            kf.append(f"{p:.1f}%{{transform:translate({pts[i + 1][0]}px,{pts[i + 1][1]}px);opacity:1}}")
        kf.append(f"86%{{transform:translate({pts[-1][0]}px,{pts[-1][1]}px);opacity:1}}94%,100%{{transform:translate({pts[-1][0]}px,{pts[-1][1]}px);opacity:0}}")
        svg = (
            "".join(f'<circle cx="{x}" cy="{y}" r="5" fill="{c["bg2"]}" stroke="{c["fg2"]}" stroke-width="1.5"/>' for x, y in stops)
            + f'<path class="ex rt" d="{d}" fill="none" stroke="{c["ice"]}" stroke-width="1.6" stroke-linejoin="round" '
            f'pathLength="100" stroke-dasharray="100" stroke-linecap="round"/>'
            + "".join(f'<circle cx="{x}" cy="{y}" r="2" fill="{c["fg"]}"/>' for x, y in stops)
            + f'<g class="ex"><rect class="van" x="-5" y="-4" width="10" height="8" rx="2.5" fill="{c["ice"]}"/></g>'
        )
        css = (
            f".rt{{stroke-dashoffset:0;animation:rt 10s {EASE_IO} {LOOPS} both}}"
            f"@keyframes rt{{0%,12%{{stroke-dashoffset:100}}62%,86%{{stroke-dashoffset:0}}96%,100%{{stroke-dashoffset:100}}}}"
            f".van{{transform:translate({pts[-1][0]}px,{pts[-1][1]}px);animation:vn 10s linear {LOOPS} both}}@keyframes vn{{{''.join(kf)}}}"
        )
        return svg, css

    if kind == "invoice":
        # An e-invoice whose lines are checked one by one, then handed on.
        rows, css = [], []
        for i, (y, w) in enumerate([(30, 30), (46, 24), (62, 28)]):
            t = 10 + i * 14
            rows.append(
                f'<rect x="22" y="{y}" width="{w}" height="4" rx="2" fill="{c["fg3"]}" opacity=".6"/>'
                f'<g class="ex ck{i}"><circle cx="61" cy="{y + 2}" r="5.5" fill="none" stroke="{c["ice"]}" stroke-width="1.4"/>'
                f'<path d="M58.4 {y + 2}l1.8 1.8 3.6-3.8" fill="none" stroke="{c["ice"]}" stroke-width="1.4" '
                f'stroke-linecap="round" stroke-linejoin="round"/></g>'
            )
            css.append(
                f".ck{i}{{transform-box:fill-box;transform-origin:center;opacity:1;animation:ck{i} 9s {EASE_OUT} {LOOPS} both}}"
                f"@keyframes ck{i}{{0%,{t}%{{opacity:0;transform:scale(.6)}}{t + 6}%,86%{{opacity:1;transform:scale(1)}}94%,100%{{opacity:0;transform:scale(1)}}}}"
            )
        svg = (
            f'<rect x="12" y="6" width="62" height="80" rx="6" fill="{c["paper"]}" stroke="{c["line2"]}"/>'
            f'<rect x="22" y="15" width="22" height="4" rx="2" fill="{c["fg2"]}"/>'
            + "".join(rows)
            + f'<path d="M22 76h20" stroke="{c["line2"]}" stroke-width="1.5" stroke-linecap="round"/>'
            f'<path class="ex iv" d="M66 76h24m-6-6 6 6-6 6" fill="none" stroke="{c["fg"]}" stroke-width="1.6" '
            f'stroke-linecap="round" stroke-linejoin="round" pathLength="100" stroke-dasharray="100"/>'
        )
        css.append(
            f".iv{{stroke-dashoffset:0;animation:iv 9s {EASE_IO} {LOOPS} both}}"
            f"@keyframes iv{{0%,56%{{stroke-dashoffset:100}}68%,86%{{stroke-dashoffset:0}}96%,100%{{stroke-dashoffset:100}}}}"
        )
        return svg, "".join(css)

    if kind == "forecast":
        # Measured load up to "now", then the day-ahead forecast with its P10-P90 band.
        history = "M6 62 L14 54 L22 60 L30 46 L38 52 L46 40 L52 48"
        ahead = "M52 48 L60 42 L68 50 L76 38 L84 44 L90 36"
        band = "M52 48 L60 34 L68 40 L76 26 L84 30 L90 20 L90 52 L84 58 L76 50 L68 60 L60 50 Z"
        svg = (
            f'<path d="M4 88h88" stroke="{c["line2"]}" stroke-width="1.5" stroke-linecap="round"/>'
            f'<path d="M52 14v74" stroke="{c["line2"]}" stroke-width="1.2" stroke-dasharray="2 3"/>'
            f'<g class="ex fb"><path d="{band}" fill="{c["ice"]}" opacity=".22"/></g>'
            f'<path d="{history}" fill="none" stroke="{c["fg2"]}" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>'
            f'<path class="ex fl" d="{ahead}" fill="none" stroke="{c["ice"]}" stroke-width="1.8" stroke-linejoin="round" '
            f'stroke-linecap="round" pathLength="100" stroke-dasharray="100"/>'
            f'<circle cx="52" cy="48" r="3" fill="{c["fg"]}"/>'
        )
        css = (
            f".fl{{stroke-dashoffset:0;animation:fl 10s {EASE_IO} {LOOPS} both}}"
            f"@keyframes fl{{0%,12%{{stroke-dashoffset:100}}44%,86%{{stroke-dashoffset:0}}96%,100%{{stroke-dashoffset:100}}}}"
            f".fb{{opacity:1;animation:fb 10s {EASE_OUT} {LOOPS} both}}"
            f"@keyframes fb{{0%,36%{{opacity:0}}52%,86%{{opacity:1}}96%,100%{{opacity:0}}}}"
        )
        return svg, css
    raise ValueError(kind)


# ---------------------------------------------------------------- cards
def card(p: dict, idx: int, theme: str) -> str:
    c = THEMES[theme]
    T = Text()
    featured = p.get("featured", False)
    W, H = (840, 300) if featured else (410, 260)
    pad = 28
    label = f"{idx:02d} — {p['label'].upper()}"
    gsvg, gcss = glyph(p["glyph"], c, featured)

    def r_fn(x, y):
        return 2.1 * smooth(W * 0.62, W * 0.97, x) * smooth(H - 80, H - 12, y) * (0.65 + 0.35 * math.sin(x * 0.05 + y * 0.03))

    dots = halftone(W * 0.6, H - 84, W - 12, H - 12, 11, r_fn, buckets=(0.6, 0.9, 1.2, 1.5, 1.8))

    if featured:
        text_w = 380
        title_size = 40
        lines = wrap("sans", p["line"], 15, text_w)
        title_y = 120
        glyph_g = f'<g transform="translate({W - pad - 318} 92) scale(1.25)">{gsvg}</g>'
    else:
        text_w = W - 2 * pad
        title_size = 30
        lines = wrap("sans", p["line"], 14.5, text_w)
        # A pending card has a footer line, so three text lines already move the title up.
        title_y = 154 if len(lines) <= (2 if p.get("pending") else 3) else 140
        glyph_g = f'<g transform="translate({W - pad - 96} 26) scale(0.92)">{gsvg}</g>'
    pending = p.get("pending")
    assert len(lines) <= (3 if pending and not featured else 4), (p["id"], lines)
    assert text_width("sans-sb", p["title"], title_size) < text_w, p["id"]

    lh = 21
    body_text = "".join(
        T("sans", pad, title_y + 30 + i * lh, ln, 15 if featured else 14.5, c["fg2"]) for i, ln in enumerate(lines)
    )
    foot = "github.com/" + p["repo"].split("github.com/")[1]
    body = (
        f'<defs><g id="f" fill="none" stroke-linecap="round">{dots}</g></defs>'
        f'<rect width="{W}" height="{H}" rx="18" fill="{c["bg2"]}"/>'
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="17.5" fill="none" stroke="{c["line"]}"/>'
        f'<use href="#f" stroke="{c["dot"]}" opacity="{c["dotop"]}"/>'
        + T("mono", pad, pad + 12, label, 11, c["fg3"], tracking=1.3)
        + f'<g class="a">{glyph_g}</g>'
        + T("sans-sb", pad, title_y, p["title"], title_size, c["fg"], tracking=-0.4)
        + body_text
        + (T("mono", pad, H - pad + 4, foot, 11, c["ice"], tracking=0.3) if featured else "")
        # The arrow is drawn: the embedded font subsets have no U+2192.
        + (f'<path d="M{pad + text_width("mono", foot, 11, 0.3) + 10:.1f} {H - pad}h11m-3.5-3.5 3.5 3.5-3.5 3.5" '
           f'fill="none" stroke="{c["ice"]}" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>'
           if featured else "")
        + (T("mono", pad, H - pad + 4, pending.upper(), 11, c["fg3"], tracking=1.3) if pending and not featured else "")
    )
    style = T.faces() + gcss
    desc = p["line"] + (f" ({pending})" if pending else "")
    return svg_doc(W, H, f"{p['title']} – {p['label']}", desc, style, body)


# ---------------------------------------------------------------- blocks
def readme_block(projects) -> str:
    out = []
    base = "assets"

    def pic(p, width):
        alt = esc(f"{p['title']}: {p['line']}" + (f" ({p['pending']})" if p.get("pending") else ""))
        # A pending repo is still private: no link to a 404. The in-page anchor keeps
        # GitHub from wrapping the image in a link to the raw SVG instead.
        href = "#projekte" if p.get("pending") else p["repo"]
        return (
            f'<a href="{href}"><picture>'
            f'<source media="(prefers-color-scheme: dark)" srcset="{base}/card-{p["id"]}-dark.svg">'
            f'<img alt="{alt}" src="{base}/card-{p["id"]}-light.svg" width="{width}">'
            f"</picture></a>"
        )

    featured = [p for p in projects if p.get("featured")]
    rest = [p for p in projects if not p.get("featured")]
    for p in featured:
        out.append(f"<p>{pic(p, 838)}</p>")
    for i in range(0, len(rest), 2):
        pair = rest[i:i + 2]
        out.append(f"<p>{' '.join(pic(q, 410) for q in pair)}</p>")
    # The cards already carry title and description (and the alt text repeats both),
    # so the text below adds only what a picture cannot: the extra links.
    extra = [p for p in projects if p["links"]]
    if extra:
        out.append("")
        for p in extra:
            links = " · ".join(f"[{t}]({u})" for t, u in p["links"])
            out.append(f"- {p['title']}: {links}")
    pending = [p["title"] for p in projects if p.get("pending")]
    if pending:
        out.append("")
        out.append(f"{', '.join(pending[:-1])} und {pending[-1]} haben eigene Repos, die noch privat sind."
                   if len(pending) > 1 else f"Das Repo von {pending[0]} ist noch privat.")
    return "\n".join(out)


TOKENS = ["bg", "bg2", "fg", "fg2", "fg3", "line", "line2", "ice", "ice2", "paper", "gold"]
SENTINEL = {k: f"#0000{i + 1:02x}" for i, k in enumerate(TOKENS)}


def page_glyph(kind: str) -> tuple[str, str]:
    """Glyph markup for the web page: colours become classes (the page CSP forbids
    style attributes), keyframes are scoped to the glyph."""
    svg, css = glyph(kind, dict(SENTINEL, dot="#000000", dotop="0", band="#000000", panel="#000000"))
    back = {v: k for k, v in SENTINEL.items()}

    def fix_tag(m):
        tag = m.group(0)
        classes = []
        for attr, pre in (("fill", "f"), ("stroke", "s")):
            mm = re.search(rf' {attr}="(#0000[0-9a-f]{{2}})"', tag)
            if mm:
                classes.append(f"{pre}-{back[mm.group(1)]}")
                tag = tag.replace(mm.group(0), "")
        if not classes:
            return tag
        if ' class="' in tag:
            return tag.replace(' class="', f' class="{" ".join(classes)} ', 1)
        return re.sub(r"^<(\w+)", lambda t: f'<{t.group(1)} class="{" ".join(classes)}"', tag)

    svg = re.sub(r"<[a-z]+[^>]*>", fix_tag, svg)
    assert "#0000" not in svg, svg
    # Scope plain rules to this glyph; leave @keyframes untouched.
    out, i, depth, start = [], 0, 0, 0
    while i < len(css):
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
            if depth == 0:
                block = css[start:i + 1]
                if not block.startswith("@"):
                    sel, rest = block.split("{", 1)
                    sel = ",".join(f".g-{kind} {x.strip()}" for x in sel.split(","))
                    block = sel + "{" + rest
                out.append(block)
                start = i + 1
        i += 1
    return svg, "".join(out)


def html_block(projects) -> str:
    items, css = [], []
    for i, p in enumerate(projects, 1):
        featured = p.get("featured")
        svg, gcss = page_glyph(p["glyph"])
        # The landing page is a document: it can switch motion off for prefers-reduced-motion
        # (styles.css), so its glyphs keep looping; only the README images stop on their own.
        css.append(gcss.replace(f" {LOOPS} both", " infinite both"))
        vb = "0 0 250 96" if p["glyph"] == "extract" else "0 0 96 96"
        links = "".join(
            f'<a class="card__link" href="{esc(u)}">{esc(t)}<span aria-hidden="true"> ↗</span></a>' for t, u in p["links"]
        )
        pending = p.get("pending")
        cls = "card card--wide" if featured else "card"
        title = (
            f'<span class="card__main">{esc(p["title"])}</span>' if pending
            else f'<a class="card__main" href="{esc(p["repo"])}">{esc(p["title"])}</a>'
        )
        repo = esc(pending) if pending else esc(p["repo"].split("github.com/")[1])
        items.append(
            f'<li class="{cls}" data-reveal>'
            f'<article class="card__inner">'
            f'<p class="card__meta meta"><span class="meta__n">{i:02d}</span> {esc(p["label"])}</p>'
            f'<svg class="card__glyph g-{p["glyph"]}" viewBox="{vb}" aria-hidden="true" focusable="false">{svg}</svg>'
            f'<h3 class="card__title">{title}</h3>'
            f'<p class="card__text">{esc(p["line"])}</p>'
            f'<p class="card__links meta"><span class="card__repo">{repo}</span>{links}</p>'
            f"</article></li>"
        )
    glyph_css = "/* Generated by tools/build.py – do not edit. */\n" + "\n".join(css) + "\n"
    return '<ol class="cards" role="list">\n' + "\n".join(items) + "\n</ol>", glyph_css


def replace_block(path: Path, block: str) -> str:
    s = path.read_text(encoding="utf-8")
    new, n = re.subn(r"(<!-- projects:start -->)(.*?)(<!-- projects:end -->)",
                     lambda m: m.group(1) + "\n" + block + "\n" + m.group(3), s, flags=re.S)
    assert n == 1, f"{path.name}: markers <!-- projects:start/end --> missing"
    return new


def main(check: bool = False) -> int:
    data = json.loads((ROOT / "tools" / "projects.json").read_text(encoding="utf-8"))
    projects = data["projects"]
    out: dict[Path, str] = {}
    for theme in THEMES:
        out[ASSETS / f"hero-{theme}.svg"] = hero(theme)
        for i, p in enumerate(projects, 1):
            out[ASSETS / f"card-{p['id']}-{theme}.svg"] = card(p, i, theme)
    out[ROOT / "README.md"] = replace_block(ROOT / "README.md", readme_block(projects))
    block, glyph_css = html_block(projects)
    out[ROOT / "docs" / "index.html"] = replace_block(ROOT / "docs" / "index.html", block)
    out[ROOT / "docs" / "glyphs.css"] = glyph_css
    expected_cards = {f for f in out if f.parent == ASSETS}
    stale = sorted(f for f in ASSETS.glob("card-*.svg") if f not in expected_cards)
    if check:
        changed = [f for f, text in out.items() if not f.exists() or f.read_text(encoding="utf-8") != text]
        for f in changed + stale:
            print(f"out of date: {f.relative_to(ROOT)}")
        if changed or stale:
            print("Run: python3 tools/build.py")
            return 1
        print("All generated files are up to date.")
        return 0
    ASSETS.mkdir(exist_ok=True)
    for f, text in out.items():
        f.write_text(text, encoding="utf-8")
    for f in stale:
        f.unlink()
        print(f"removed stale {f.name}")
    # GitHub shows README images as plain <img> via its image proxy: no scripts,
    # no foreignObject, no external references, and keep them small.
    forbidden = re.compile(r"<script|foreignObject|<image|@import|href=\"(?!#)|url\((?!data:|#)", re.I)
    for f in sorted(ASSETS.glob("*.svg")):
        text = f.read_text(encoding="utf-8")
        bad = forbidden.findall(text)
        assert not bad, (f.name, bad)
        assert f.stat().st_size < 60 * 1024, f.name
        print(f"{f.name:42s} {f.stat().st_size / 1024:6.1f} kB  ok")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main(check="--check" in sys.argv[1:]))
