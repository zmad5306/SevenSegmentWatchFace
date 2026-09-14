#!/usr/bin/env python3
"""Generates the 7-segment Watch Face Format resources.

Outputs (relative to the repo root):
  app/src/main/res/raw/watchface.xml        - the WFF scene
  app/src/main/res/values/strings.xml       - labels used by the editor
  app/src/main/res/drawable-nodpi/preview.png - picker preview
  app/src/main/res/drawable-nodpi/cfg_*.png   - editor icons for each setting
  app/src/main/res/drawable/ic_launcher_foreground.xml, mipmap-anydpi/ic_launcher.xml - app icon

Every lit segment is a pill-shaped RoundRectangle. Each digit position is a
Condition with one Compare per digit value (0-9) holding that value's lit
segments, so only lit segments are ever drawn. Standard library only.

Run from anywhere:  python tools/generate_watchface.py
"""

import math
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "app" / "src" / "main" / "res"

CANVAS = 450

#  aaa
# f   b
#  ggg
# e   c
#  ddd
DIGIT_SEGMENTS = {
    0: "abcdef",
    1: "bc",
    2: "abdeg",
    3: "abcdg",
    4: "bcfg",
    5: "acdfg",
    6: "acdefg",
    7: "abc",
    8: "abcdefg",
    9: "abcdfg",
}

# (option id / string suffix, display label, ARGB color)
PALETTE = [
    ("red", "Red", "#FFFF3B30"),
    ("amber", "Amber", "#FFFFB000"),
    ("orange", "Orange", "#FFFF6D00"),
    ("green", "Green", "#FF39FF14"),
    ("lime", "Lime", "#FFC6FF00"),
    ("cyan", "Cyan", "#FF00E5FF"),
    ("blue", "Blue", "#FF2979FF"),
    ("purple", "Purple", "#FFB388FF"),
    ("pink", "Pink", "#FFFF4FA3"),
    ("white", "White", "#FFF5F5F5"),
    ("silver", "Silver", "#FFB0B0B0"),
]
DEFAULT_TIME_COLOR = "red"
DEFAULT_DATE_COLOR = "silver"

TIME_COLOR = "[CONFIGURATION.timeColor.0]"
DATE_COLOR = "[CONFIGURATION.dateColor.0]"

GHOST_ALPHA = 36  # unlit segments of the large time digits, out of 255
# The thin date/seconds segments sit next to bright lit ones and vanish at the
# same alpha (silver at 36 is only #191919), so they get a stronger level.
SMALL_GHOST_ALPHA = 72
# The battery meter's 4px segments need more still to be visible on the watch.
BATTERY_GHOST_ALPHA = 120
AMBIENT_LIT_ALPHA = 170  # lit segments while in always-on mode
AMBIENT_BATTERY_ALPHA = 140


@dataclass(frozen=True)
class DigitStyle:
    width: int
    height: int
    thickness: int

    @property
    def gap(self) -> int:
        # Keeps neighboring pill ends visibly apart (needs > ~0.21 * thickness).
        return max(2, round(self.thickness * 0.35))


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int
    corner: float | None = None  # None = fully rounded (pill)

    @property
    def radius(self) -> float:
        return self.corner if self.corner is not None else min(self.w, self.h) / 2


def segment_rects(style: DigitStyle) -> dict[str, Rect]:
    w, h, t, g = style.width, style.height, style.thickness, style.gap
    half_t = t // 2
    horiz_x = half_t + g
    horiz_w = w - t - 2 * g
    vert_h = h // 2 - half_t - 2 * g
    upper_y = half_t + g
    lower_y = h // 2 + g
    return {
        "a": Rect(horiz_x, 0, horiz_w, t),
        "g": Rect(horiz_x, h // 2 - half_t, horiz_w, t),
        "d": Rect(horiz_x, h - t, horiz_w, t),
        "f": Rect(0, upper_y, t, vert_h),
        "b": Rect(w - t, upper_y, t, vert_h),
        "e": Rect(0, lower_y, t, vert_h),
        "c": Rect(w - t, lower_y, t, vert_h),
    }


# ---------------------------------------------------------------------------
# Layout (450 x 450, round)
# ---------------------------------------------------------------------------

TIME_STYLE = DigitStyle(width=66, height=124, thickness=12)
SMALL_STYLE = DigitStyle(width=32, height=56, thickness=8)

TIME_Y = 150
TIME_PAIR_GAP = 14
TIME_COLON_GAP = 36
_time_total = TIME_STYLE.width * 4 + TIME_PAIR_GAP * 2 + TIME_COLON_GAP
TIME_X = (CANVAS - _time_total) // 2
TIME_RIGHT = TIME_X + _time_total
HOUR_XS = (TIME_X, TIME_X + TIME_STYLE.width + TIME_PAIR_GAP)
_minute_x = HOUR_XS[1] + TIME_STYLE.width + TIME_COLON_GAP
MINUTE_XS = (_minute_x, _minute_x + TIME_STYLE.width + TIME_PAIR_GAP)
COLON_CX = HOUR_XS[1] + TIME_STYLE.width + TIME_COLON_GAP // 2

ROW2_Y = 300
SMALL_PAIR_GAP = 8
DASH_SLOT = 28
DATE_WIDTH = SMALL_STYLE.width * 4 + SMALL_PAIR_GAP * 2 + DASH_SLOT
SECONDS_WIDTH = SMALL_STYLE.width * 2 + SMALL_PAIR_GAP
# With seconds shown the date is flush with the hours and the seconds flush
# with the minutes; without seconds the date is centered.
DATE_X_WITH_SECONDS = TIME_X
DATE_X_CENTERED = (CANVAS - DATE_WIDTH) // 2
SECONDS_X = TIME_RIGHT - SECONDS_WIDTH

# LCD-style battery meter above the time: a battery outlined in segment pills
# with five charge bars, then the level in small 7-segment digits and a "%".
BATTERY_Y = 92
BATTERY_H = 32
BATTERY_T = 4  # segment thickness
BATTERY_W = 58
BATTERY_BARS = 5
BATTERY_DIGIT = DigitStyle(width=18, height=BATTERY_H, thickness=BATTERY_T)
BATTERY_HUNDREDS = DigitStyle(width=BATTERY_T, height=BATTERY_H, thickness=BATTERY_T)  # a lone "1"
PERCENT_W = 20
LOW_BATTERY_COLOR = "#FFFF3B30"


@dataclass(frozen=True)
class BatteryLayout:
    outline: list[Rect]  # absolute coordinates
    bars: list[Rect]  # absolute coordinates
    hundreds_x: int
    tens_x: int
    ones_x: int
    percent_x: int


def battery_layout() -> BatteryLayout:
    t, h, w = BATTERY_T, BATTERY_H, BATTERY_W
    g = BATTERY_DIGIT.gap
    nub_gap, nub_w = 2, 4
    digit_gap = 4
    widths = [
        w + nub_gap + nub_w, 12,
        BATTERY_HUNDREDS.width, digit_gap,
        BATTERY_DIGIT.width, digit_gap,
        BATTERY_DIGIT.width, 5,
        PERCENT_W,
    ]
    x = (CANVAS - sum(widths)) // 2
    y = BATTERY_Y
    # Same pill geometry as a digit's outer segments, with full-height sides.
    outline = [
        Rect(x + t // 2 + g, y, w - t - 2 * g, t),
        Rect(x + t // 2 + g, y + h - t, w - t - 2 * g, t),
        Rect(x, y + t // 2 + g, t, h - t - 2 * g),
        Rect(x + w - t, y + t // 2 + g, t, h - t - 2 * g),
        Rect(x + w + nub_gap, y + h // 2 - 5, nub_w, 10),
    ]
    inner_x, inner_w = x + t + 3, w - 2 * t - 6
    bar_gap = 2
    bar_w = (inner_w - bar_gap * (BATTERY_BARS - 1)) // BATTERY_BARS
    bars = [
        Rect(inner_x + i * (bar_w + bar_gap), y + t + 3, bar_w, h - 2 * t - 6)
        for i in range(BATTERY_BARS)
    ]
    hundreds_x = x + sum(widths[:2])
    tens_x = hundreds_x + sum(widths[2:4])
    ones_x = tens_x + sum(widths[4:6])
    percent_x = ones_x + sum(widths[6:8])
    return BatteryLayout(outline, bars, hundreds_x, tens_x, ones_x, percent_x)


def percent_shapes() -> tuple[list[Rect], tuple[int, int, int, int]]:
    """Two round dots plus a slash (start/end point), relative to the % cell."""
    dots = [Rect(0, 2, 6, 6), Rect(PERCENT_W - 6, BATTERY_H - 8, 6, 6)]
    return dots, (PERCENT_W - 3, 3, 3, BATTERY_H - 3)


def date_positions(x0: int) -> tuple[list[int], Rect]:
    s = SMALL_STYLE
    d1 = x0
    d2 = d1 + s.width + SMALL_PAIR_GAP
    dash_x = d2 + s.width
    d3 = dash_x + DASH_SLOT
    d4 = d3 + s.width + SMALL_PAIR_GAP
    dash_w = DASH_SLOT - 2 * s.gap
    dash = Rect(dash_x + s.gap, ROW2_Y + s.height // 2 - s.thickness // 2, dash_w, s.thickness)
    return [d1, d2, d3, d4], dash


def seconds_positions() -> list[int]:
    return [SECONDS_X, SECONDS_X + SMALL_STYLE.width + SMALL_PAIR_GAP]


# ---------------------------------------------------------------------------
# XML emission
# ---------------------------------------------------------------------------


class Xml:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.depth = 0

    def line(self, text: str) -> None:
        self.lines.append("    " * self.depth + text)

    def open(self, text: str) -> None:
        self.line(text)
        self.depth += 1

    def close(self, text: str) -> None:
        self.depth -= 1
        self.line(text)

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"


def tens(source: str) -> str:
    return f"floor({source} / 10)"


def ones(source: str) -> str:
    return f"{source} % 10"


def round_rect(x: Xml, r: Rect, color: str, width_transform: str | None = None) -> None:
    rad = int(r.radius)
    x.open(
        f'<RoundRectangle x="{r.x}" y="{r.y}" width="{r.w}" height="{r.h}" '
        f'cornerRadiusX="{rad}" cornerRadiusY="{rad}">'
    )
    x.line(f'<Fill color="{color}" />')
    if width_transform:
        x.line(f'<Transform target="width" value="{width_transform}" />')
    x.close("</RoundRectangle>")


def part_draw(x: Xml, name: str, bounds: Rect, shapes: list[Rect], color: str) -> None:
    """One PartDraw holding several shapes (coordinates relative to `bounds`)."""
    x.open(f'<PartDraw name="{name}" x="{bounds.x}" y="{bounds.y}" width="{bounds.w}" height="{bounds.h}">')
    for r in shapes:
        round_rect(x, r, color)
    x.close("</PartDraw>")


def open_full_group(x: Xml, name: str) -> None:
    """Wrapper for places (Compare, Default, ListOption) that take one child."""
    x.open(f'<Group name="{name}" x="0" y="0" width="{CANVAS}" height="{CANVAS}">')


def ghost_digit(x: Xml, name: str, dx: int, dy: int, style: DigitStyle, color: str) -> None:
    bounds = Rect(dx, dy, style.width, style.height)
    part_draw(x, name, bounds, list(segment_rects(style).values()), color)


def lit_digit(
    x: Xml,
    name: str,
    dx: int,
    dy: int,
    style: DigitStyle,
    value_expr: str,
    color: str,
    blank_zero: bool = False,
    zero_guard: str | None = None,
) -> None:
    """One digit position: a Compare per value containing its lit segments.

    blank_zero drops 0 entirely; zero_guard shows 0 only while that expression holds.
    """
    rects = segment_rects(style)
    values = [v for v in range(10) if not (blank_zero and v == 0)]
    x.open(f'<Group name="{name}" x="{dx}" y="{dy}" width="{style.width}" height="{style.height}">')
    x.open("<Condition>")
    x.open("<Expressions>")
    for v in values:
        expr = f"{value_expr} == {v}"
        if v == 0 and zero_guard:
            expr = f"{expr} && {zero_guard}"
        x.line(f'<Expression name="{name}_is{v}"><![CDATA[{expr}]]></Expression>')
    x.close("</Expressions>")
    for v in values:
        x.open(f'<Compare expression="{name}_is{v}">')
        bounds = Rect(0, 0, style.width, style.height)
        part_draw(x, f"{name}_{v}", bounds, [rects[seg] for seg in DIGIT_SEGMENTS[v]], color)
        x.close("</Compare>")
    x.close("</Condition>")
    x.close("</Group>")


def full_group(x: Xml, name: str, alpha: int | None = None) -> None:
    alpha_attr = f' alpha="{alpha}"' if alpha is not None else ""
    x.open(f'<Group name="{name}" x="0" y="0" width="{CANVAS}" height="{CANVAS}"{alpha_attr}>')


def ambient_alpha(x: Xml, value: int) -> None:
    x.line(f'<Variant mode="AMBIENT" target="alpha" value="{value}" />')


def emit_time(x: Xml) -> None:
    s = TIME_STYLE

    x.open('<ListConfiguration id="ghost">')
    x.open('<ListOption id="on">')
    full_group(x, "time_ghost", GHOST_ALPHA)
    ambient_alpha(x, 0)
    for i, dx in enumerate(HOUR_XS + MINUTE_XS):
        ghost_digit(x, f"time_ghost_{i}", dx, TIME_Y, s, TIME_COLOR)
    x.close("</Group>")
    x.close("</ListOption>")
    x.close("</ListConfiguration>")

    full_group(x, "time_lit")
    ambient_alpha(x, AMBIENT_LIT_ALPHA)

    x.open("<Condition>")
    x.open("<Expressions>")
    x.line('<Expression name="is24"><![CDATA[[IS_24_HOUR_MODE]]]></Expression>')
    x.close("</Expressions>")
    x.open('<Compare expression="is24">')
    open_full_group(x, "hours24")
    lit_digit(x, "hour24_tens", HOUR_XS[0], TIME_Y, s, tens("[HOUR_0_23]"), TIME_COLOR)
    lit_digit(x, "hour24_ones", HOUR_XS[1], TIME_Y, s, ones("[HOUR_0_23]"), TIME_COLOR)
    x.close("</Group>")
    x.close("</Compare>")
    x.open("<Default>")
    open_full_group(x, "hours12")
    lit_digit(x, "hour12_tens", HOUR_XS[0], TIME_Y, s, tens("[HOUR_1_12]"), TIME_COLOR, blank_zero=True)
    lit_digit(x, "hour12_ones", HOUR_XS[1], TIME_Y, s, ones("[HOUR_1_12]"), TIME_COLOR)
    x.close("</Group>")
    x.close("</Default>")
    x.close("</Condition>")

    lit_digit(x, "minute_tens", MINUTE_XS[0], TIME_Y, s, tens("[MINUTE]"), TIME_COLOR)
    lit_digit(x, "minute_ones", MINUTE_XS[1], TIME_Y, s, ones("[MINUTE]"), TIME_COLOR)

    part_draw(x, "colon", Rect(0, 0, CANVAS, CANVAS), colon_rects(), TIME_COLOR)
    x.close("</Group>")


def colon_rects() -> list[Rect]:
    t = TIME_STYLE.thickness
    ys = (TIME_Y + round(TIME_STYLE.height * 0.3), TIME_Y + round(TIME_STYLE.height * 0.7))
    return [Rect(COLON_CX - t // 2, y - t // 2, t, t) for y in ys]


def emit_date(x: Xml, x0: int, suffix: str) -> None:
    s = SMALL_STYLE
    xs, dash = date_positions(x0)
    sources = [
        tens("[MONTH]"),
        ones("[MONTH]"),
        tens("[DAY]"),
        ones("[DAY]"),
    ]

    x.open('<ListConfiguration id="ghost">')
    x.open('<ListOption id="on">')
    full_group(x, f"date_ghost_{suffix}", SMALL_GHOST_ALPHA)
    ambient_alpha(x, 0)
    for i, dx in enumerate(xs):
        ghost_digit(x, f"date_ghost_{suffix}_{i}", dx, ROW2_Y, s, DATE_COLOR)
    x.close("</Group>")
    x.close("</ListOption>")
    x.close("</ListConfiguration>")

    full_group(x, f"date_lit_{suffix}")
    ambient_alpha(x, AMBIENT_LIT_ALPHA)
    for i, (dx, expr) in enumerate(zip(xs, sources)):
        lit_digit(x, f"date_{suffix}_{i}", dx, ROW2_Y, s, expr, DATE_COLOR)
    part_draw(x, f"date_dash_{suffix}", Rect(0, 0, CANVAS, CANVAS), [dash], DATE_COLOR)
    x.close("</Group>")


def emit_seconds(x: Xml) -> None:
    s = SMALL_STYLE
    xs = seconds_positions()
    full_group(x, "seconds")
    ambient_alpha(x, 0)

    x.open('<ListConfiguration id="ghost">')
    x.open('<ListOption id="on">')
    full_group(x, "seconds_ghost", SMALL_GHOST_ALPHA)
    for i, dx in enumerate(xs):
        ghost_digit(x, f"seconds_ghost_{i}", dx, ROW2_Y, s, TIME_COLOR)
    x.close("</Group>")
    x.close("</ListOption>")
    x.close("</ListConfiguration>")

    lit_digit(x, "second_tens", xs[0], ROW2_Y, s, tens("[SECOND]"), TIME_COLOR)
    lit_digit(x, "second_ones", xs[1], ROW2_Y, s, ones("[SECOND]"), TIME_COLOR)
    x.close("</Group>")


def emit_battery(x: Xml) -> None:
    lay = battery_layout()
    pct = "[BATTERY_PERCENT]"
    y, h, t = BATTERY_Y, BATTERY_H, BATTERY_T
    canvas = Rect(0, 0, CANVAS, CANVAS)
    hundreds = segment_rects(BATTERY_HUNDREDS)
    full_group(x, "battery")
    ambient_alpha(x, AMBIENT_BATTERY_ALPHA)

    x.open('<ListConfiguration id="ghost">')
    x.open('<ListOption id="on">')
    full_group(x, "battery_ghost", BATTERY_GHOST_ALPHA)
    ambient_alpha(x, 0)
    part_draw(x, "battery_ghost_bars", canvas, lay.bars, DATE_COLOR)
    part_draw(x, "battery_ghost_hundreds", Rect(lay.hundreds_x, y, t, h), [hundreds["b"], hundreds["c"]], DATE_COLOR)
    ghost_digit(x, "battery_ghost_tens", lay.tens_x, y, BATTERY_DIGIT, DATE_COLOR)
    ghost_digit(x, "battery_ghost_ones", lay.ones_x, y, BATTERY_DIGIT, DATE_COLOR)
    x.close("</Group>")
    x.close("</ListOption>")
    x.close("</ListConfiguration>")

    part_draw(x, "battery_outline", canvas, lay.outline, DATE_COLOR)

    # Charge bars: bar i lights above i * 20%; all bars turn red when the battery is low.
    def bars(suffix: str, color: str) -> None:
        open_full_group(x, f"battery_bars_{suffix}")
        for i, bar in enumerate(lay.bars):
            name = f"battery_bar{i}_{suffix}"
            x.open("<Condition>")
            x.open("<Expressions>")
            x.line(f'<Expression name="{name}_on"><![CDATA[{pct} > {i * 100 // BATTERY_BARS}]]></Expression>')
            x.close("</Expressions>")
            x.open(f'<Compare expression="{name}_on">')
            part_draw(x, name, bar, [Rect(0, 0, bar.w, bar.h)], color)
            x.close("</Compare>")
            x.close("</Condition>")
        x.close("</Group>")

    x.open("<Condition>")
    x.open("<Expressions>")
    x.line('<Expression name="battery_low"><![CDATA[[BATTERY_IS_LOW]]]></Expression>')
    x.close("</Expressions>")
    x.open('<Compare expression="battery_low">')
    bars("low", LOW_BATTERY_COLOR)
    x.close("</Compare>")
    x.open("<Default>")
    bars("normal", DATE_COLOR)
    x.close("</Default>")
    x.close("</Condition>")

    x.open("<Condition>")
    x.open("<Expressions>")
    x.line(f'<Expression name="battery_full"><![CDATA[{pct} >= 100]]></Expression>')
    x.close("</Expressions>")
    x.open('<Compare expression="battery_full">')
    part_draw(x, "battery_hundreds", Rect(lay.hundreds_x, y, t, h), [hundreds["b"], hundreds["c"]], DATE_COLOR)
    x.close("</Compare>")
    x.close("</Condition>")
    lit_digit(x, "battery_tens", lay.tens_x, y, BATTERY_DIGIT, f"floor({pct} / 10) % 10", DATE_COLOR,
              zero_guard=f"{pct} >= 100")
    lit_digit(x, "battery_ones", lay.ones_x, y, BATTERY_DIGIT, ones(pct), DATE_COLOR)

    dots, (x1, y1, x2, y2) = percent_shapes()
    x.open(f'<PartDraw name="battery_percent" x="{lay.percent_x}" y="{y}" width="{PERCENT_W}" height="{h}">')
    for dot in dots:
        round_rect(x, dot, DATE_COLOR)
    x.open(f'<Line startX="{x1}" startY="{y1}" endX="{x2}" endY="{y2}">')
    x.line(f'<Stroke color="{DATE_COLOR}" thickness="{t}" cap="ROUND" />')
    x.close("</Line>")
    x.close("</PartDraw>")
    x.close("</Group>")


def build_xml() -> str:
    x = Xml()
    x.line('<?xml version="1.0" encoding="utf-8"?>')
    x.line("<!-- GENERATED by tools/generate_watchface.py - do not edit by hand. -->")
    x.open(f'<WatchFace width="{CANVAS}" height="{CANVAS}">')
    x.line('<Metadata key="CLOCK_TYPE" value="DIGITAL" />')
    x.line('<Metadata key="PREVIEW_TIME" value="10:08:32" />')

    # Every configuration gets an icon: without one the runtime logs
    # "Failed to read from inputStream ... Path is empty or null" on each load.
    x.open("<UserConfigurations>")
    for cfg_id, label, default in (
        ("timeColor", "config_time_color", DEFAULT_TIME_COLOR),
        ("dateColor", "config_date_color", DEFAULT_DATE_COLOR),
    ):
        x.open(
            f'<ColorConfiguration id="{cfg_id}" displayName="{label}" '
            f'icon="{CONFIG_ICONS[cfg_id]}" defaultValue="{default}">'
        )
        for opt_id, _, color in PALETTE:
            x.line(f'<ColorOption id="{opt_id}" displayName="color_{opt_id}" colors="{color}" />')
        x.close("</ColorConfiguration>")
    # On/Off lists rather than BooleanConfigurations: the Wear OS 6 editor clips the
    # right edge of BooleanConfiguration switches regardless of label length or icon.
    for cfg_id, label in (("showSeconds", "config_show_seconds"), ("ghost", "config_ghost")):
        x.open(
            f'<ListConfiguration id="{cfg_id}" displayName="{label}" '
            f'icon="{CONFIG_ICONS[cfg_id]}" defaultValue="on">'
        )
        x.line('<ListOption id="on" displayName="option_on" />')
        x.line('<ListOption id="off" displayName="option_off" />')
        x.close("</ListConfiguration>")
    x.close("</UserConfigurations>")

    x.open('<Scene backgroundColor="#FF000000">')
    emit_battery(x)
    emit_time(x)
    x.open('<ListConfiguration id="showSeconds">')
    x.open('<ListOption id="on">')
    open_full_group(x, "row2_with_seconds")
    emit_date(x, DATE_X_WITH_SECONDS, "left")
    emit_seconds(x)
    x.close("</Group>")
    x.close("</ListOption>")
    x.open('<ListOption id="off">')
    open_full_group(x, "row2_date_only")
    emit_date(x, DATE_X_CENTERED, "center")
    x.close("</Group>")
    x.close("</ListOption>")
    x.close("</ListConfiguration>")
    x.close("</Scene>")
    x.close("</WatchFace>")
    return x.text()


def build_strings() -> str:
    entries = [
        ("app_name", "Seven Segment"),
        ("config_time_color", "Time color"),
        ("config_date_color", "Date color"),
        ("config_show_seconds", "Show seconds"),
        ("config_ghost", "Unlit segments"),
        ("option_on", "On"),
        ("option_off", "Off"),
    ] + [(f"color_{opt_id}", label) for opt_id, label, _ in PALETTE]
    body = "\n".join(f'    <string name="{k}">{v}</string>' for k, v in entries)
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<!-- GENERATED by tools/generate_watchface.py - do not edit by hand. -->\n"
        f"<resources>\n{body}\n</resources>\n"
    )


# ---------------------------------------------------------------------------
# Preview PNG (anti-aliased signed-distance rasterizer)
# ---------------------------------------------------------------------------


class Canvas:
    def __init__(self, size: int) -> None:
        self.size = size
        self.px = [[0.0, 0.0, 0.0, 0.0] for _ in range(size * size)]  # premultiplied

    def _blend(self, i: int, rgb: tuple[float, float, float], a: float) -> None:
        p = self.px[i]
        inv = 1.0 - a
        p[0] = rgb[0] * a + p[0] * inv
        p[1] = rgb[1] * a + p[1] * inv
        p[2] = rgb[2] * a + p[2] * inv
        p[3] = a + p[3] * inv

    def circle(self, cx: float, cy: float, radius: float, rgb, alpha: float = 1.0) -> None:
        for py in range(max(0, int(cy - radius) - 1), min(self.size, int(cy + radius) + 2)):
            for px in range(max(0, int(cx - radius) - 1), min(self.size, int(cx + radius) + 2)):
                d = math.hypot(px + 0.5 - cx, py + 0.5 - cy) - radius
                cov = min(1.0, max(0.0, 0.5 - d))
                if cov > 0:
                    self._blend(py * self.size + px, rgb, cov * alpha)

    def round_rect(self, r: Rect, rgb, alpha: float = 1.0) -> None:
        rad = r.radius
        cx, cy = r.x + r.w / 2, r.y + r.h / 2
        hx, hy = r.w / 2 - rad, r.h / 2 - rad
        for py in range(max(0, r.y - 1), min(self.size, r.y + r.h + 1)):
            for px in range(max(0, r.x - 1), min(self.size, r.x + r.w + 1)):
                qx = abs(px + 0.5 - cx) - hx
                qy = abs(py + 0.5 - cy) - hy
                d = math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - rad
                cov = min(1.0, max(0.0, 0.5 - d))
                if cov > 0:
                    self._blend(py * self.size + px, rgb, cov * alpha)

    def capsule(self, x1: float, y1: float, x2: float, y2: float, radius: float, rgb, alpha: float = 1.0) -> None:
        """A line segment with round caps (matches Stroke cap="ROUND")."""
        dx, dy = x2 - x1, y2 - y1
        length_sq = dx * dx + dy * dy
        for py in range(max(0, int(min(y1, y2) - radius) - 1), min(self.size, int(max(y1, y2) + radius) + 2)):
            for px in range(max(0, int(min(x1, x2) - radius) - 1), min(self.size, int(max(x1, x2) + radius) + 2)):
                cx, cy = px + 0.5 - x1, py + 0.5 - y1
                u = max(0.0, min(1.0, (cx * dx + cy * dy) / length_sq))
                d = math.hypot(cx - u * dx, cy - u * dy) - radius
                cov = min(1.0, max(0.0, 0.5 - d))
                if cov > 0:
                    self._blend(py * self.size + px, rgb, cov * alpha)

    def png(self) -> bytes:
        raw = bytearray()
        for y in range(self.size):
            raw.append(0)
            for x in range(self.size):
                r, g, b, a = self.px[y * self.size + x]
                if a > 0:
                    r, g, b = r / a, g / a, b / a
                raw += bytes(int(round(min(1.0, v) * 255)) for v in (r, g, b, a))

        def chunk(tag: bytes, data: bytes) -> bytes:
            return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

        header = struct.pack(">IIBBBBB", self.size, self.size, 8, 6, 0, 0, 0)
        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b"")
        )


def hex_rgb(argb: str) -> tuple[float, float, float]:
    v = argb.lstrip("#")[-6:]
    return tuple(int(v[i : i + 2], 16) / 255 for i in (0, 2, 4))


def build_preview() -> bytes:
    colors = {opt_id: hex_rgb(c) for opt_id, _, c in PALETTE}
    time_rgb, date_rgb = colors[DEFAULT_TIME_COLOR], colors[DEFAULT_DATE_COLOR]
    cv = Canvas(CANVAS)
    cv.circle(CANVAS / 2, CANVAS / 2, CANVAS / 2, (0, 0, 0))

    def digit(dx: int, dy: int, style: DigitStyle, value: int, rgb) -> None:
        ghost = {TIME_STYLE: GHOST_ALPHA, BATTERY_DIGIT: BATTERY_GHOST_ALPHA}.get(style, SMALL_GHOST_ALPHA) / 255
        for seg, r in segment_rects(style).items():
            shifted = Rect(r.x + dx, r.y + dy, r.w, r.h)
            cv.round_rect(shifted, rgb, 1.0 if seg in DIGIT_SEGMENTS[value] else ghost)

    for dx, v in zip(HOUR_XS + MINUTE_XS, (1, 0, 0, 8)):
        digit(dx, TIME_Y, TIME_STYLE, v, time_rgb)
    for r in colon_rects():
        cv.round_rect(r, time_rgb)

    xs, dash = date_positions(DATE_X_WITH_SECONDS)
    for dx, v in zip(xs, (0, 9, 1, 4)):
        digit(dx, ROW2_Y, SMALL_STYLE, v, date_rgb)
    cv.round_rect(dash, date_rgb)
    for dx, v in zip(seconds_positions(), (3, 2)):
        digit(dx, ROW2_Y, SMALL_STYLE, v, time_rgb)

    # Battery meter at 80%.
    lay = battery_layout()
    battery_ghost = BATTERY_GHOST_ALPHA / 255
    for r in lay.outline:
        cv.round_rect(r, date_rgb)
    for i, r in enumerate(lay.bars):
        cv.round_rect(r, date_rgb, 1.0 if 80 > i * 100 // BATTERY_BARS else battery_ghost)
    hundreds = segment_rects(BATTERY_HUNDREDS)
    for seg in "bc":
        r = hundreds[seg]
        cv.round_rect(Rect(r.x + lay.hundreds_x, r.y + BATTERY_Y, r.w, r.h), date_rgb, battery_ghost)
    digit(lay.tens_x, BATTERY_Y, BATTERY_DIGIT, 8, date_rgb)
    digit(lay.ones_x, BATTERY_Y, BATTERY_DIGIT, 0, date_rgb)
    dots, (x1, y1, x2, y2) = percent_shapes()
    for r in dots:
        cv.round_rect(Rect(r.x + lay.percent_x, r.y + BATTERY_Y, r.w, r.h), date_rgb)
    cv.capsule(lay.percent_x + x1, BATTERY_Y + y1, lay.percent_x + x2, BATTERY_Y + y2, BATTERY_T / 2, date_rgb)
    return cv.png()


# ---------------------------------------------------------------------------
# Editor icons for the user configurations
# ---------------------------------------------------------------------------

CONFIG_ICON_SIZE = 96  # the runtime resizes anything over 360x360
CONFIG_ICONS = {
    "timeColor": "cfg_time_color",
    "dateColor": "cfg_date_color",
    "showSeconds": "cfg_show_seconds",
    "ghost": "cfg_ghost",
}


def build_config_icon(cfg_id: str) -> bytes:
    white = (1.0, 1.0, 1.0)
    cv = Canvas(CONFIG_ICON_SIZE)

    def digit(dx: int, dy: int, style: DigitStyle, value: int, unlit_alpha: float = 0.0) -> None:
        for seg, r in segment_rects(style).items():
            alpha = 1.0 if seg in DIGIT_SEGMENTS[value] else unlit_alpha
            if alpha:
                cv.round_rect(Rect(r.x + dx, r.y + dy, r.w, r.h), white, alpha)

    if cfg_id in ("timeColor", "ghost"):
        style = DigitStyle(width=40, height=72, thickness=9)
        x0, y0 = (CONFIG_ICON_SIZE - style.width) // 2, (CONFIG_ICON_SIZE - style.height) // 2
        if cfg_id == "timeColor":
            digit(x0, y0, style, 8)
        else:
            digit(x0, y0, style, 7, unlit_alpha=0.3)
    elif cfg_id == "dateColor":
        style, gap, dash_slot = DigitStyle(width=16, height=30, thickness=4), 4, 12
        total = style.width * 4 + gap * 2 + dash_slot
        x, y0 = (CONFIG_ICON_SIZE - total) // 2, (CONFIG_ICON_SIZE - style.height) // 2
        for i in range(4):
            digit(x, y0, style, 8)
            x += style.width + (dash_slot if i == 1 else gap)
        dash_x = (CONFIG_ICON_SIZE - dash_slot) // 2 + style.gap
        cv.round_rect(Rect(dash_x, y0 + style.height // 2 - 2, dash_slot - 2 * style.gap, 4), white)
    else:  # showSeconds
        style, gap = DigitStyle(width=26, height=48, thickness=6), 8
        x0 = (CONFIG_ICON_SIZE - style.width * 2 - gap) // 2
        y0 = (CONFIG_ICON_SIZE - style.height) // 2
        digit(x0, y0, style, 3)
        digit(x0 + style.width + gap, y0, style, 2)
    return cv.png()


# ---------------------------------------------------------------------------
# Launcher icon (adaptive icon, vector foreground)
# ---------------------------------------------------------------------------


def pill_path(x: float, y: float, w: float, h: float) -> str:
    r = min(w, h) / 2
    return (
        f"M{x + r:g},{y:g} H{x + w - r:g} A{r:g},{r:g} 0 0 1 {x + w:g},{y + r:g} "
        f"V{y + h - r:g} A{r:g},{r:g} 0 0 1 {x + w - r:g},{y + h:g} "
        f"H{x + r:g} A{r:g},{r:g} 0 0 1 {x:g},{y + h - r:g} "
        f"V{y + r:g} A{r:g},{r:g} 0 0 1 {x + r:g},{y:g} Z"
    )


def build_icon_foreground() -> str:
    # A lit "8" scaled into the 66dp safe zone of the 108dp adaptive icon canvas.
    viewport = 108
    style = DigitStyle(width=66, height=124, thickness=12)
    scale = 56 / style.height
    ox = (viewport - style.width * scale) / 2
    oy = (viewport - style.height * scale) / 2
    color = dict((opt_id, c) for opt_id, _, c in PALETTE)[DEFAULT_TIME_COLOR]
    paths = "\n".join(
        f'    <path android:fillColor="{color}" android:pathData="'
        + pill_path(
            round(ox + r.x * scale, 2), round(oy + r.y * scale, 2),
            round(r.w * scale, 2), round(r.h * scale, 2),
        )
        + '" />'
        for r in segment_rects(style).values()
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<!-- GENERATED by tools/generate_watchface.py - do not edit by hand. -->\n"
        '<vector xmlns:android="http://schemas.android.com/apk/res/android"\n'
        f'    android:width="{viewport}dp" android:height="{viewport}dp"\n'
        f'    android:viewportWidth="{viewport}" android:viewportHeight="{viewport}">\n'
        f"{paths}\n"
        "</vector>\n"
    )


ICON_ADAPTIVE = """<?xml version="1.0" encoding="utf-8"?>
<!-- GENERATED by tools/generate_watchface.py - do not edit by hand. -->
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@android:color/black" />
    <foreground android:drawable="@drawable/ic_launcher_foreground" />
    <monochrome android:drawable="@drawable/ic_launcher_foreground" />
</adaptive-icon>
"""


def write(path: Path, data: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8", newline="\n")
    else:
        path.write_bytes(data)
    print(f"wrote {path.relative_to(ROOT)}")


def main() -> None:
    write(RES / "raw" / "watchface.xml", build_xml())
    write(RES / "values" / "strings.xml", build_strings())
    write(RES / "drawable-nodpi" / "preview.png", build_preview())
    for cfg_id, name in CONFIG_ICONS.items():
        write(RES / "drawable-nodpi" / f"{name}.png", build_config_icon(cfg_id))
    write(RES / "drawable" / "ic_launcher_foreground.xml", build_icon_foreground())
    write(RES / "mipmap-anydpi" / "ic_launcher.xml", ICON_ADAPTIVE)


if __name__ == "__main__":
    main()
