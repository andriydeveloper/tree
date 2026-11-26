#!/usr/bin/env python3
"""
Christmas tree in the screen corner, always on top: garlands, ornaments, gifts,
a semi-transparent WiMo logo flying around, falling snow, random wind gusts.

Controls:
  left click          - next garland program
  left button + move  - drag the tree
  middle click        - new random tree
  right mouse button  - menu: new random tree, settings, close
Settings are saved to settings.json next to this file.
Start it with start.bat (Windows) or start.sh (Linux): they update the app and install what is missing.

Author: Andrii Havrysh
"""
import colorsys
import json
import math
import os
import random
import sys
import threading
import time
import traceback

import cairo
from PySide6.QtCore import QByteArray, QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QAction, QGuiApplication, QImage, QPainter
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit, QMenu, QPushButton, QScrollArea, QSpinBox, QTabWidget,
                               QVBoxLayout, QWidget)

HERE = os.path.dirname(os.path.abspath(__file__))
APP_NAME = "Christmas tree"
__author__ = "Andrii Havrysh"
try:
    with open(os.path.join(HERE, "VERSION")) as _f:
        __version__ = _f.read().strip()
except OSError:
    __version__ = "dev"
LOGO_FILE = os.path.join(HERE, "wimo-logo-blau.svg")   # official logo (WiMo Styleguide V1.5); only its shape is used

# Tree look: "random" - a new realistic spruce on every start (trunk, branches, needles, cones
# are generated); "classic" - the previous fixed cartoon tree.
TREE_STYLE = "random"
TREE_SEED = None              # number = always the same random tree; None = new one (seed goes to tree.log)
TREE_HEIGHT = 258             # tree height incl. gifts, px; only the tree grows, the window widens to fit it
RANDOM_GIFTS = True           # False = the classic fixed gifts
GIFT_COUNT = (3, 6)           # random gifts under the tree
RANDOM_TOPPER = True          # False = the classic yellow star on top
SHOW_TOPPER = True            # star (topper) on the tree top
SHOW_SNOW = True              # falling snow and snow on branches
SHOW_GIFTS = True             # gifts under the tree
SHOW_NEEDLES = True           # needles (off = bare wood); the tree stays the same

BASE_TREE_W, BASE_TREE_H, BASE_GROUND = 180, 258, 244   # default tree area; classic tree coordinates
BASE_WIDTH, BASE_HEIGHT = 310, 280                         # default window: room for logo and snow
# Current layout, follows TREE_HEIGHT (see apply_geometry)
TREE_W, TREE_H = 180, 258     # tree area incl. gifts, px
TREE_BASE_Y = 244             # ground: the tree does not move below it
WIDTH, HEIGHT = 310, 280      # window size, px
TREE_X, TREE_Y = (WIDTH - TREE_W) / 2, 15   # tree area position in the window
MARGIN = 20                   # distance from screen edges
DRAG_THRESHOLD_PX = 4         # mouse move with left button held beyond this = drag, otherwise click
MAX_FPS = 65                  # redraw at most this often, synced to the screen refresh
MAX_DT = 0.1                  # a longer pause (load, suspend) counts as this, s
LIGHT_CHANGE_S = (0.5, 1.6)   # each ornament changes its color at its own pace, s
LIGHT_FADE_S = 0.3            # color crossfade of one ornament, s

# Logo orbit
LOGO_ENABLED = False          # show the flying WiMo logo (off by default)
LOGO_W = 70                   # logo width in front, px (height keeps 714:516 ratio)
LOGO_ALPHA = 0.7              # logo opacity: 1 = opaque, 0 = invisible
LOGO_DEPTH = 4                # logo thickness (3D), px
SCALE_BACK = 0.6              # logo size behind the tree relative to front
TILT_MAX = 0.6                # max tilt towards flight direction, radians (~35°)
TILT_FOLLOW = 4.0             # tilt spring stiffness, 1/s (bigger = follows faster)
TILT_VX_SOFT = 25             # px/s; slower horizontal motion fades the tilt to level
LOOKAHEAD_S = 0.35            # the logo leans to where it will be in this time
EDGE_ON = 0.3                 # logo width at orbit sides (edge-on), 0..1
BOB_PX = 2.5                  # up/down bobbing while flying, px
Z_FADE = 0.12                 # front/behind switch is crossfaded around z = 0

# Flight: the logo flies one pattern (orbit around the tree, figure eight, Lissajous, big loop,
# free wandering over the whole scene), then blends smoothly into the next one.
FLIGHT_PATTERN_S = (8, 18)    # one pattern lasts, s
FLIGHT_BLEND_S = 3.0          # smooth blend into the next pattern, s
FLIGHT_SPEED = 1.0            # speed of all patterns, 1 = normal
# Orbit pattern, each value (min, max), picked anew for every orbit
ORBIT_RX_RANGE = (80, 100)    # orbit radius (close to the tree)
ORBIT_RY_RANGE = (-22, 34)    # tilt: >0 seen from above, <0 from below
ORBIT_Y_RANGE = (95, 175)     # orbit height in the window
SPEED_RANGE = (0.5, 1.4)      # orbit speed, rad/s; direction is picked separately

# Snow
SNOWFLAKES = 70
SNOW_SPEED = (13, 40)         # fall speed, px/s
SNOW_SWAY = 10                # left/right flutter, px/s

# Wind: calm breeze, from time to time a gust from the left or right,
# sometimes slanting down. Never from below.
WIND_MAX = 140                # strongest gust, px/s
WIND_BREEZE = 10              # breeze between gusts, px/s at most
WIND_CALM_S = (4, 14)         # pause between gusts, s
WIND_GUST_S = (3, 12)         # gust at full strength, s
WIND_RISE_S = (1.6, 4.0)      # gust build-up, s
WIND_FALL_S = (3, 7)          # gust fading, s
WIND_DOWN_MAX = 0.5           # max downward slant, radians (~30°)
WIND_KEEP_SIDE = 0.7          # chance the next gust comes from the same side
WIND_TURBULENCE = 0.3         # gust strength wobble, 0..1

# Tree reaction
TREE_BEND_PX = 7              # top shift at the strongest wind, px
TREE_IDLE_PX = 0.6            # slight sway even without wind, px
TREE_FREQ = 2.4               # natural sway frequency, rad/s
TREE_DAMP = 0.22              # damping ratio (<1 = sways back after a gust)
ORNAMENT_SWING = 0.35         # ornament swing at the strongest wind, radians
ORNAMENT_IDLE = 0.04          # ornament idle swing, radians
BRANCH_BEND = 1.0             # how much single branches bend in the wind (0 = rigid)
BRANCH_FLUTTER = 0.4          # own turbulent flutter of every branch, 0..1
BRANCH_SHELTER = 1.0          # how much branches shelter each other from the wind (0 = no shelter)
BRANCH_DAMP = 0.18            # branch damping ratio (needles damp the swing)

# Random spruce (TREE_STYLE = "random"). Ranges: (min, max), each tree picks its own value.
SPRUCE_HALF_W = (72, 90)      # crown half width at the bottom, px
SPRUCE_TOP_Y = (16, 30)       # leader tip, px from the top of the tree area
SPRUCE_CROWN_BOTTOM = (160, 178)  # lowest branches start here
SPRUCE_TRUNK_ROOM = 20        # bare trunk between the lowest needles and the ground, px
SPRUCE_ORNAMENT_ZONE = 1.0    # ornaments only on this upper share of the crown (1 = down to the lowest branches)
SPRUCE_WHORL_GAP = (6, 9)     # distance between branch whorls at the top, px (grows downwards)
SPRUCE_BRANCHES = (5, 8)      # branches per whorl, all around the trunk
NEEDLE_DENSITY = (0.6, 1.3)   # needles per px of a twig; every twig picks its own
NEEDLE_LEN = (3.5, 5.5)       # needle length, px
SPRUCE_CONES = (0, 9)         # hanging cones
SPRUCE_ORNAMENTS = (10, 14)   # ornaments on a random tree
SPRUCE_FULLNESS = (0.75, 1.15)  # crown outline exponent: <1 full top, >1 slender
SPRUCE_LEAN = 3.0             # max trunk lean at the top, px
SPRUCE_TRUNK_R = (4.0, 6.0)   # trunk half width at the ground, px (grows a bit faster than the tree)
SPRUCE_TRUNK_BEND = 6.0       # max trunk bend (bow, S-curve), px
SPRUCE_STRAIGHT = 0.3         # chance of an (almost) straight trunk
SPRUCE_SNOW = 0.8             # max share of branches with snow
SPRUCE_FRESH = 0.5            # max share of twigs with light-green fresh tips
SPRUCE_GAPS = 0.1             # chance of a missing branch at the bottom (gaps in the crown)

# WiMo colors (Styleguide V1.5)
WIMO_BLUE = (0.0, 0x2E / 255, 0x5D / 255)                  # #002E5D
WIMO_BLUE_75 = (0x38 / 255, 0x52 / 255, 0x7C / 255)        # #38527C

COLORS = [
    (1.0, 0.15, 0.15),  # red
    (1.0, 0.85, 0.1),   # yellow
    (0.2, 0.6, 1.0),    # blue
    (1.0, 0.4, 0.9),    # pink
    (0.3, 1.0, 0.4),    # lime
    (1.0, 0.55, 0.1),   # orange
    (0.7, 0.4, 1.0),    # purple
]

# Branch layers: (apex y, bottom y, bottom half-width). Lower layers are wider.
LAYERS = [(18, 70, 30), (35, 100, 42), (55, 128, 54), (78, 156, 64), (102, 184, 75), (128, 212, 88)]

# Gifts under the tree: (x, bottom y, width, height, depth, color, ribbon color).
# List order = drawing order: back ones first.
GIFTS = [
    (118, 248, 28, 28, 8, (0.15, 0.35, 0.75), (0.92, 0.92, 0.96)),
    (22, 250, 32, 24, 9, (0.75, 0.10, 0.12), (1.0, 0.82, 0.30)),
    (54, 252, 20, 15, 6, (0.50, 0.20, 0.65), (1.0, 0.82, 0.30)),
    (146, 252, 20, 13, 6, (0.95, 0.70, 0.15), (0.80, 0.10, 0.12)),
    (84, 255, 17, 12, 5, (0.93, 0.93, 0.96), (0.80, 0.10, 0.12)),
]

# Garlands: from (x1, y1) to (x2, y2), sag, number of bulbs
GARLANDS = [
    (62, 82, 122, 92, 10, 7),
    (50, 125, 140, 142, 14, 10),
    (35, 178, 158, 196, 14, 13),
]
GARLAND_COLORS = [(1.0, 0.85, 0.3), (1.0, 0.3, 0.2), (0.3, 0.7, 1.0), (0.4, 1.0, 0.5)]
# Garland show: programs follow each other in a loop with a smooth crossfade.
# wave - slow wave, rainbow - moving rainbow, twinkle - random twinkling, fill - bulbs light up
# one by one, breathe - whole garland breathes, alternate - even/odd bulbs swap.
GARLAND_PROGRAM = ["wave", "rainbow", "twinkle", "fill", "breathe", "alternate"]
GARLAND_PROGRAM_S = 9         # duration of one program, seconds
GARLAND_FADE_S = 2.0          # crossfade between programs, seconds
GARLAND_CLICK_FADE_S = 0.8    # crossfade after a click (faster response)
GARLAND_CLICK_FLASH_S = 0.6   # all bulbs flash smoothly after a click, seconds
GARLAND_MIN_LIGHT = 0.12      # a bulb never goes fully dark
GARLAND_SAG = 1.0             # how much garlands sag between the branches they hang on

# Ornaments: (x, y, shape). Shapes: ball, star, bell, candy, drop, gift, snowflake
ORNAMENTS = [
    (90, 58, "ball"), (74, 74, "bell"), (106, 72, "drop"),
    (65, 112, "gift"), (92, 106, "snowflake"), (119, 116, "candy"), (80, 148, "ball"),
    (52, 160, "star"), (86, 168, "bell"), (115, 160, "ball"), (135, 205, "drop"),
    (68, 205, "candy"), (102, 202, "gift"), (40, 208, "snowflake"), (124, 186, "star"),
]


def tree_k():
    """Tree size relative to the default 258 px tree. Only the tree grows; snow, logo, gifts stay."""
    return TREE_HEIGHT / BASE_TREE_H


def apply_geometry():
    """Tree area and window from TREE_HEIGHT. The window widens just enough for the tree and the logo orbit."""
    global TREE_W, TREE_H, TREE_BASE_Y, WIDTH, HEIGHT, TREE_X, TREE_Y
    k = tree_k()
    TREE_BASE_Y = round(BASE_GROUND * k)
    TREE_H = TREE_BASE_Y + BASE_TREE_H - BASE_GROUND        # room for gifts below the ground stays
    TREE_W = max(BASE_TREE_W, round(BASE_TREE_W * k))       # never narrower than the gifts row
    WIDTH = TREE_W + BASE_WIDTH - BASE_TREE_W
    HEIGHT = TREE_H + BASE_HEIGHT - BASE_TREE_H
    TREE_X, TREE_Y = (WIDTH - TREE_W) / 2, 15


def load_logo():
    """
    SVG logo -> bitmap. Rendered once at higher resolution so the SVG is not parsed
    every frame. Used as a shape (mask) afterwards.
    """
    res = 2
    QGuiApplication.instance() or QGuiApplication([])     # Qt needs an application to render SVG
    renderer = QSvgRenderer(LOGO_FILE)
    size = renderer.defaultSize()
    w = round(LOGO_W * res)
    h = round(w * size.height() / size.width())
    image = QImage(w, h, QImage.Format_ARGB32_Premultiplied)   # same pixel layout as cairo ARGB32
    image.fill(0)
    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, w, h))
    painter.end()
    data = bytearray(image.constBits().tobytes())
    surface = cairo.ImageSurface.create_for_data(data, cairo.FORMAT_ARGB32, w, h, image.bytesPerLine())
    return {"surface": surface, "res": res, "data": data}   # data keeps the pixels alive


def star_path(cr, x, y, outer, inner, points=5):
    for i in range(points * 2):
        radius = outer if i % 2 == 0 else inner
        angle = -math.pi / 2 + i * math.pi / points
        px, py = x + radius * math.cos(angle), y + radius * math.sin(angle)
        cr.move_to(px, py) if i == 0 else cr.line_to(px, py)
    cr.close_path()


# ---------- garlands ----------

def garland_point(x1, y1, x2, y2, sag, t):
    """Point on the sagging arc (quadratic curve), t from 0 to 1."""
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2 + sag * 2
    u = 1 - t
    return u * u * x1 + 2 * u * t * cx + t * t * x2, u * u * y1 + 2 * u * t * cy + t * t * y2


_rng = random.Random(7)
TWINKLE = [(_rng.uniform(0.6, 1.6), _rng.uniform(0, 2 * math.pi)) for _ in range(400)]


def smoothstep(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def spring(x, v, target, omega, zeta, dt):
    """Damped spring step. Velocity stays continuous, so a new target never causes a jerk."""
    v += (omega * omega * (target - x) - 2 * zeta * omega * v) * dt
    return x + v * dt, v


def garland_program(name, i, t, n):
    """Brightness (0..1) and color of bulb i of n (counted across all garlands) in program name."""
    i %= len(TWINKLE)
    color = GARLAND_COLORS[i % len(GARLAND_COLORS)]
    if name == "wave":                                     # wave runs slowly from top to bottom
        return 0.5 + 0.5 * math.sin(t * 1.6 - i * 0.45), color
    if name == "rainbow":                                  # all on, rainbow colors drift
        hue = (i / n - t * 0.08) % 1.0
        return 0.85 + 0.15 * math.sin(t * 2 + i), colorsys.hsv_to_rgb(hue, 0.7, 1.0)
    if name == "twinkle":                                  # each bulb twinkles at its own rhythm
        speed, phase = TWINKLE[i]
        return (0.5 + 0.5 * math.sin(t * speed * 1.2 + phase)) ** 2, color
    if name == "fill":                                     # light up one by one, then fade out together
        cycle = 7.0
        k = (t % cycle) / cycle
        on = smoothstep((k * 1.4 * n - i) / 6)             # soft front moves along the garland
        off = 1 - smoothstep((k - 0.72) / 0.28)            # everything fades out at the end of the cycle
        return on * off, color
    if name == "breathe":                                  # whole garland slowly breathes
        return (0.5 + 0.5 * math.sin(t * 1.3)) ** 1.5, color
    if name == "alternate":                                # even and odd bulbs swap smoothly
        return 0.5 + 0.5 * math.sin(t * 1.4 + (i % 2) * math.pi), color
    return 1.0, color


class GarlandShow:
    """
    Which garland program is playing. Switches to the next one every GARLAND_PROGRAM_S
    seconds or on click; after each switch the previous program crossfades into the new one.
    """

    def __init__(self):
        self.index = 0
        self.started = 0.0
        self.previous = None
        self.fade_len = GARLAND_FADE_S
        self.flash_at = None
        self.total = 1                                 # bulbs on the current tree, set by the scene

    def step(self, t):
        if t - self.started >= GARLAND_PROGRAM_S:
            self.next(t, GARLAND_FADE_S)

    def click(self, t):
        self.next(t, GARLAND_CLICK_FADE_S)
        self.flash_at = t

    def next(self, t, fade_len):
        self.previous = self.index
        self.index = (self.index + 1) % len(GARLAND_PROGRAM)
        self.started = t
        self.fade_len = fade_len

    def light(self, i, t):
        light, color = garland_program(GARLAND_PROGRAM[self.index], i, t, self.total)
        if self.previous is not None:
            mix = smoothstep((t - self.started) / self.fade_len)
            if mix < 1:
                old_light, old_color = garland_program(GARLAND_PROGRAM[self.previous], i, t, self.total)
                light = old_light + (light - old_light) * mix
                color = tuple(a + (b - a) * mix for a, b in zip(old_color, color))
        if self.flash_at is not None:
            k = (t - self.flash_at) / GARLAND_CLICK_FLASH_S
            if 0 <= k < 1:
                light += (1 - light) * math.sin(math.pi * k)   # smooth rise and fall, no jump
        return GARLAND_MIN_LIGHT + (1 - GARLAND_MIN_LIGHT) * max(0.0, min(1.0, light)), color


def draw_bulb(cr, px, py, light, rgb):
    r, g, b = rgb
    glow = cairo.RadialGradient(px, py + 2, 0.5, px, py + 2, 8)
    glow.add_color_stop_rgba(0, r, g, b, 0.7 * light)
    glow.add_color_stop_rgba(1, r, g, b, 0.0)
    cr.set_source(glow)
    cr.arc(px, py + 2, 8, 0, 2 * math.pi)
    cr.fill()
    cr.set_source_rgb(r * (0.4 + 0.6 * light), g * (0.4 + 0.6 * light), b * (0.4 + 0.6 * light))
    cr.save()
    cr.translate(px, py + 2.5)
    cr.scale(1.6, 2.3)
    cr.arc(0, 0, 1, 0, 2 * math.pi)
    cr.restore()
    cr.fill()


def hanging_garlands(cr, garlands, t, show, sway):
    """
    Garlands that hang on branches: every anchor moves with its branch, the wire sags between
    anchors under its weight and the sagging part swings in the wind.
    """
    bulb_index = 0
    seg_index = 0
    for g in garlands:
        pts = [sway.branch_point(i, x, y) if i is not None and i < len(sway.angle) else (x + sway.offset(y), y)
               for i, x, y in g["anchors"]]
        curves = []
        for j, (p0, p1) in enumerate(zip(pts, pts[1:])):
            swing = sway.garland_swing(seg_index)
            seg_index += 1
            sag = g["sags"][j]
            ctrl = ((p0[0] + p1[0]) / 2 + 2 * sag * math.sin(swing),
                    (p0[1] + p1[1]) / 2 + 2 * sag * math.cos(swing))
            curves.append((p0, ctrl, p1))
        cr.set_source_rgba(0.1, 0.15, 0.1, 0.9)            # wire
        cr.set_line_width(1.0)
        for j, (p0, c, p1) in enumerate(curves):
            if j == 0:
                cr.move_to(*p0)
            cr.curve_to(p0[0] + 2 / 3 * (c[0] - p0[0]), p0[1] + 2 / 3 * (c[1] - p0[1]),
                        p1[0] + 2 / 3 * (c[0] - p1[0]), p1[1] + 2 / 3 * (c[1] - p1[1]), *p1)
        cr.stroke()
        for j, u in g["bulbs"]:                            # bulbs: brightness and color from the show
            (x0, y0), (cx, cy), (x1, y1) = curves[j]
            v = 1 - u
            px = v * v * x0 + 2 * v * u * cx + u * u * x1
            py = v * v * y0 + 2 * v * u * cy + u * u * y1
            light, rgb = show.light(bulb_index, t)
            bulb_index += 1
            draw_bulb(cr, px, py, light, rgb)


def draw_garlands(cr, garlands, t, show, sway):
    if garlands and isinstance(garlands[0], dict):
        hanging_garlands(cr, garlands, t, show, sway)
        return
    bulb_index = 0
    for x1, y1, x2, y2, sag, count in garlands:
        # wire
        cr.set_source_rgba(0.1, 0.15, 0.1, 0.9)
        cr.set_line_width(1.0)
        for i in range(31):
            px, py = garland_point(x1, y1, x2, y2, sag, i / 30)
            px += sway.offset(py)
            cr.move_to(px, py) if i == 0 else cr.line_to(px, py)
        cr.stroke()

        # bulbs: brightness and color come from the show program
        for i in range(count):
            px, py = garland_point(x1, y1, x2, y2, sag, (i + 0.5) / count)
            px += sway.offset(py)
            light, rgb = show.light(bulb_index, t)
            bulb_index += 1
            draw_bulb(cr, px, py, light, rgb)


# ---------- ornaments ----------

def hanger(cr, x, y, length=4):
    """Thread the ornament hangs on."""
    cr.set_source_rgba(0.9, 0.85, 0.6, 0.8)
    cr.set_line_width(0.7)
    cr.move_to(x, y - length)
    cr.line_to(x, y)
    cr.stroke()


def shine(cr, x, y, r=1.6):
    cr.set_source_rgba(1, 1, 1, 0.75)
    cr.arc(x, y, r, 0, 2 * math.pi)
    cr.fill()


def ornament_ball(cr, x, y, rgb):
    hanger(cr, x, y - 6)
    cr.set_source_rgb(0.8, 0.7, 0.3)                  # cap
    cr.rectangle(x - 2, y - 8, 4, 2.5)
    cr.fill()
    grad = cairo.RadialGradient(x - 2, y - 2, 1, x, y, 7)
    grad.add_color_stop_rgb(0, *(min(1, c + 0.35) for c in rgb))
    grad.add_color_stop_rgb(1, *(c * 0.55 for c in rgb))
    cr.set_source(grad)
    cr.arc(x, y, 6.5, 0, 2 * math.pi)
    cr.fill()
    shine(cr, x - 2.2, y - 2.2)


def ornament_star(cr, x, y, rgb):
    hanger(cr, x, y - 7)
    cr.set_source_rgb(*rgb)
    star_path(cr, x, y, 8, 3.5)
    cr.fill_preserve()
    cr.set_source_rgba(1, 1, 1, 0.5)
    cr.set_line_width(0.6)
    cr.stroke()


def ornament_bell(cr, x, y, rgb):
    hanger(cr, x, y - 7)
    cr.set_source_rgb(*rgb)
    cr.move_to(x - 7, y + 5)                          # bell bottom
    cr.curve_to(x - 5, y + 3, x - 5, y - 6, x, y - 7)  # left side up to the top
    cr.curve_to(x + 5, y - 6, x + 5, y + 3, x + 7, y + 5)
    cr.close_path()
    cr.fill()
    cr.set_source_rgb(0.85, 0.75, 0.3)                # clapper
    cr.arc(x, y + 6, 1.8, 0, 2 * math.pi)
    cr.fill()
    shine(cr, x - 2, y - 2, 1.2)


def ornament_candy(cr, x, y, rgb):
    """Candy cane: white base + colored stripes."""
    cr.save()
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_width(3)
    path = lambda: (cr.move_to(x + 1, y + 8), cr.line_to(x + 1, y - 3), cr.arc_negative(x - 2, y - 3, 3, 0, math.pi))
    cr.set_source_rgb(1, 1, 1)
    path()
    cr.stroke()
    cr.set_source_rgb(*rgb)
    cr.set_line_cap(cairo.LINE_CAP_BUTT)
    cr.set_dash([2, 2])
    path()
    cr.stroke()
    cr.restore()


def ornament_drop(cr, x, y, rgb):
    """Icicle / drop, pointed at the bottom."""
    hanger(cr, x, y - 6)
    grad = cairo.LinearGradient(x - 4, 0, x + 4, 0)
    grad.add_color_stop_rgb(0, *(min(1, c + 0.3) for c in rgb))
    grad.add_color_stop_rgb(1, *(c * 0.6 for c in rgb))
    cr.set_source(grad)
    cr.move_to(x, y + 10)
    cr.curve_to(x - 2, y + 4, x - 5, y - 1, x - 4, y - 4)
    cr.curve_to(x - 3, y - 7, x + 3, y - 7, x + 4, y - 4)
    cr.curve_to(x + 5, y - 1, x + 2, y + 4, x, y + 10)
    cr.fill()
    shine(cr, x - 1.5, y - 3, 1.1)


def ornament_gift(cr, x, y, rgb):
    cr.set_source_rgb(*rgb)
    cr.rectangle(x - 6, y - 5, 12, 11)
    cr.fill()
    cr.set_source_rgb(1, 0.9, 0.4)                    # ribbon
    cr.rectangle(x - 1.2, y - 5, 2.4, 11)
    cr.rectangle(x - 6, y - 0.8, 12, 2.4)
    cr.fill()
    cr.set_line_width(1.2)                            # bow
    cr.arc(x - 2.5, y - 7, 2.3, 0, 2 * math.pi)
    cr.stroke()
    cr.arc(x + 2.5, y - 7, 2.3, 0, 2 * math.pi)
    cr.stroke()


def ornament_snowflake(cr, x, y, rgb):
    cr.save()
    cr.set_source_rgb(*rgb)
    cr.set_line_width(1.3)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    for i in range(6):
        a = i * math.pi / 3
        ex, ey = x + 7 * math.cos(a), y + 7 * math.sin(a)
        cr.move_to(x, y)
        cr.line_to(ex, ey)
        mx, my = x + 4 * math.cos(a), y + 4 * math.sin(a)       # side branches
        for side in (-0.6, 0.6):
            cr.move_to(mx, my)
            cr.line_to(mx + 2.5 * math.cos(a + side), my + 2.5 * math.sin(a + side))
    cr.stroke()
    cr.restore()


ORNAMENT_DRAW = {
    "ball": ornament_ball, "star": ornament_star, "bell": ornament_bell, "candy": ornament_candy,
    "drop": ornament_drop, "gift": ornament_gift, "snowflake": ornament_snowflake,
}


class OrnamentLights:
    """Each ornament changes its color at its own moment, with a short crossfade."""

    OFF = (0.35, 0.35, 0.4)                            # "off" ornament is darker, without glow

    def __init__(self, count):
        self.state = []
        for _ in range(count):
            look = self.pick()
            self.state.append({"from": look, "to": look, "at": 0.0,
                               "next": random.uniform(*LIGHT_CHANGE_S)})

    @classmethod
    def pick(cls):
        return (random.choice(COLORS), 1.0) if random.random() > 0.15 else (cls.OFF, 0.0)

    @staticmethod
    def current(s, t):
        mix = smoothstep((t - s["at"]) / LIGHT_FADE_S)
        (rgb0, glow0), (rgb1, glow1) = s["from"], s["to"]
        return tuple(a + (b - a) * mix for a, b in zip(rgb0, rgb1)), glow0 + (glow1 - glow0) * mix

    def step(self, t):
        for s in self.state:
            if t >= s["next"]:
                s["from"], s["to"], s["at"] = self.current(s, t), self.pick(), t
                s["next"] = t + random.uniform(*LIGHT_CHANGE_S)

    def get(self, t):
        return [self.current(s, t) for s in self.state]


def draw_ornaments(cr, ornaments, lights, sway):
    for i, (ornament, (rgb, glow_k)) in enumerate(zip(ornaments, lights)):
        x, y, shape = ornament[:3]
        cr.save()
        pivot_y = y - 10                               # ornaments swing around the hanger top
        branch = ornament[3] if len(ornament) > 3 else None
        if branch is not None and branch < len(sway.angle):
            cr.translate(*sway.branch_point(branch, x, pivot_y))   # hanger moves with the branch
        else:
            cr.translate(x + sway.offset(pivot_y), pivot_y)
        cr.rotate(sway.swing[i][0])
        cr.translate(-x, -pivot_y)
        if glow_k > 0.01:
            glow = cairo.RadialGradient(x, y, 2, x, y, 14)
            glow.add_color_stop_rgba(0, *rgb, 0.55 * glow_k)
            glow.add_color_stop_rgba(1, *rgb, 0.0)
            cr.set_source(glow)
            cr.arc(x, y, 14, 0, 2 * math.pi)
            cr.fill()
        ORNAMENT_DRAW[shape](cr, x, y, rgb)
        cr.restore()


# ---------- tree ----------

def layer_shape(apex, bottom, half, rng):
    """
    Outline of one branch layer: sides with twigs pointing down and out,
    bottom edge with drooping branch tips. Returns (path ops, branch tips).
    """
    cx = BASE_TREE_W / 2
    h = bottom - apex
    steps = max(3, int(h / 9))
    ops = [("M", cx, apex)]
    for j in range(1, steps):                              # right side, top to bottom
        t, t2 = j / steps, (j + 0.35) / steps
        ops.append(("L", cx + half * t + rng.uniform(2, 4), apex + h * t + rng.uniform(1.5, 3.5)))
        ops.append(("L", cx + half * t2 - rng.uniform(1, 2.5), apex + h * t2))
    ops.append(("L", cx + half + 2, bottom + 3))           # right corner

    tips_count = 3 + int(half / 14)                        # bottom: branch tips right to left
    tips = []
    for j in range(1, tips_count + 1):
        x = cx + half - 2 * half * j / tips_count
        y = bottom + rng.uniform(1.5, 5)
        prev_x = cx + half - 2 * half * (j - 1) / tips_count
        ops.append(("Q", (prev_x + x) / 2, bottom - rng.uniform(4, 8), x, y))
        tips.append((x, y))

    for j in range(steps - 1, 0, -1):                      # left side, bottom to top
        t, t2 = j / steps, (j + 0.35) / steps
        ops.append(("L", cx - half * t2 + rng.uniform(1, 2.5), apex + h * t2))
        ops.append(("L", cx - half * t - rng.uniform(2, 4), apex + h * t + rng.uniform(1.5, 3.5)))
    return ops, tips


def trace(cr, ops):
    for op in ops:
        if op[0] == "M":
            cr.move_to(op[1], op[2])
        elif op[0] == "L":
            cr.line_to(op[1], op[2])
        else:                                              # quadratic curve -> cubic (cairo)
            x0, y0 = cr.get_current_point()
            _, qx, qy, x, y = op
            cr.curve_to(x0 + 2 / 3 * (qx - x0), y0 + 2 / 3 * (qy - y0),
                        x + 2 / 3 * (qx - x), y + 2 / 3 * (qy - y), x, y)
    cr.close_path()


def draw_trunk(cr, rng):
    cx = BASE_TREE_W / 2
    top, base = 195, 244
    cr.move_to(cx - 10, top)
    cr.line_to(cx - 12, base - 9)
    cr.curve_to(cx - 13, base - 4, cx - 17, base - 1, cx - 21, base)   # root flare on the left
    cr.line_to(cx + 21, base)
    cr.curve_to(cx + 17, base - 1, cx + 13, base - 4, cx + 12, base - 9)
    cr.line_to(cx + 10, top)
    cr.close_path()
    grad = cairo.LinearGradient(cx - 14, 0, cx + 14, 0)    # cylinder shading, light from the left
    grad.add_color_stop_rgb(0, 0.22, 0.12, 0.06)
    grad.add_color_stop_rgb(0.32, 0.50, 0.31, 0.16)
    grad.add_color_stop_rgb(0.65, 0.33, 0.19, 0.09)
    grad.add_color_stop_rgb(1, 0.15, 0.08, 0.04)
    cr.set_source(grad)
    cr.fill_preserve()

    cr.save()
    cr.clip()
    cr.set_line_width(0.8)
    for _ in range(14):                                    # bark grooves
        x = cx + rng.uniform(-13, 13)
        cr.move_to(x, top)
        for y in range(top, base + 1, 4):
            cr.line_to(x + math.sin(y * 0.35 + x) * 0.9, y)
        cr.set_source_rgba(0.12, 0.06, 0.02, rng.uniform(0.35, 0.6))
        cr.stroke()
    for _ in range(6):                                     # horizontal cracks
        x, y = cx + rng.uniform(-10, 8), rng.uniform(top + 4, base - 6)
        cr.move_to(x, y)
        cr.line_to(x + rng.uniform(3, 6), y + rng.uniform(-1, 1))
        cr.set_source_rgba(0.1, 0.05, 0.02, 0.5)
        cr.stroke()
    cr.restore()


def draw_gift(cr, x, yb, w, h, d, color, ribbon):
    """3D box: front, lid, right side; crossed ribbons and a bow."""
    dy = d * 0.6
    shade = lambda k: tuple(min(1, c * k) for c in color)
    top_y = yb - h

    faces = [
        ([(x, top_y), (x + d, top_y - dy), (x + w + d, top_y - dy), (x + w, top_y)], shade(1.25)),   # lid
        ([(x + w, top_y), (x + w + d, top_y - dy), (x + w + d, yb - dy), (x + w, yb)], shade(0.6)),  # side
        ([(x, top_y), (x + w, top_y), (x + w, yb), (x, yb)], shade(1.0)),                            # front
    ]
    for points, rgb in faces:
        cr.move_to(*points[0])
        for p in points[1:]:
            cr.line_to(*p)
        cr.close_path()
        cr.set_source_rgb(*rgb)
        cr.fill_preserve()
        cr.set_source_rgba(0, 0, 0, 0.25)
        cr.set_line_width(0.5)
        cr.stroke()

    rw = max(2.0, w * 0.13)
    cr.set_line_width(rw)
    cr.set_source_rgb(*ribbon)
    for (x1, y1), (x2, y2) in [
        ((x + w / 2, top_y), (x + w / 2, yb)),                               # front, vertical
        ((x, yb - h / 2), (x + w, yb - h / 2)),                              # front, horizontal
        ((x + w, yb - h / 2), (x + w + d, yb - h / 2 - dy)),                 # side
    ]:
        cr.move_to(x1, y1)
        cr.line_to(x2, y2)
        cr.stroke()
    cr.set_line_width(rw * 0.45)                                             # ribbons on the lid are thinner in perspective
    for (x1, y1), (x2, y2) in [
        ((x + w / 2, top_y), (x + w / 2 + d, top_y - dy)),
        ((x + d / 2, top_y - dy / 2), (x + w + d / 2, top_y - dy / 2)),
    ]:
        cr.move_to(x1, y1)
        cr.line_to(x2, y2)
        cr.stroke()

    bx, by = x + w / 2 + d / 2, top_y - dy / 2             # bow
    size = max(3.0, w * 0.16)
    cr.set_line_width(1.2)
    for side in (-1, 1):
        cr.save()
        cr.translate(bx + side * size * 0.8, by - size * 0.5)
        cr.rotate(side * 0.5)
        cr.scale(size, size * 0.6)
        cr.arc(0, 0, 1, 0, 2 * math.pi)
        cr.restore()
        cr.stroke()
    cr.arc(bx, by - 0.5, 1.6, 0, 2 * math.pi)
    cr.fill()


def tree_part(x, y, w, h, res=2):
    """Bitmap for one tree part (res px per unit); drawing uses tree coordinates."""
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, math.ceil(w * res), math.ceil(h * res))
    cr = cairo.Context(surface)
    cr.scale(res, res)
    cr.translate(-x, -y)
    return {"surface": surface, "x": x, "y": y, "res": res}, cr


def draw_ground_shadow(cr, cx, y, radius):
    shadow = cairo.RadialGradient(cx, y, 5, cx, y, radius)
    shadow.add_color_stop_rgba(0, 0, 0, 0, 0.35)
    shadow.add_color_stop_rgba(1, 0, 0, 0, 0)
    cr.save()
    cr.translate(cx, y)
    cr.scale(1, 0.12)
    cr.translate(-cx, -y)
    cr.set_source(shadow)
    cr.arc(cx, y, radius, 0, 2 * math.pi)
    cr.fill()
    cr.restore()


# ---------- random gifts ----------

GIFT_PAPER = [
    (0.75, 0.08, 0.10), (0.10, 0.36, 0.20), (0.12, 0.25, 0.62), (0.46, 0.15, 0.56), (0.86, 0.64, 0.15),
    (0.93, 0.93, 0.95), (0.72, 0.74, 0.79), (0.90, 0.45, 0.60), (0.10, 0.50, 0.55), (0.08, 0.12, 0.30),
    (0.90, 0.42, 0.10), (0.35, 0.18, 0.10),
]
GIFT_RIBBON = [
    (1.0, 0.82, 0.30), (0.96, 0.96, 0.98), (0.82, 0.10, 0.12), (0.78, 0.80, 0.86),
    (0.15, 0.52, 0.25), (0.25, 0.42, 0.88), (0.92, 0.50, 0.70),
]
GIFT_PATTERNS = ["plain", "stripes", "dots", "stars", "checks", "zigzag", "snowflakes"]


def color_distance(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def shaded(rgb, k):
    return tuple(min(1.0, c * k) for c in rgb)


def random_gifts(rng, floor_half):
    """
    Gifts with random size, shape (box or round hat box), paper, pattern, ribbon, bow and tag.
    Placed anywhere on the floor under the crown (floor_half wide to each side of the trunk),
    some behind the trunk, without covering each other too much; back ones first.
    """
    gifts = []
    for _ in range(rng.randint(*GIFT_COUNT)):
        for _attempt in range(40):
            round_box = rng.random() < 0.2
            w = rng.uniform(16, 30) if round_box else rng.uniform(14, 34)
            h = rng.uniform(10, 28)
            d = rng.uniform(5, 10)
            yb = TREE_BASE_Y + rng.uniform(-7, 12)           # < ground: behind the trunk
            x = rng.uniform(TREE_W / 2 - floor_half, TREE_W / 2 + floor_half - w - d)
            if all(abs(yb - g["yb"]) > 6 or min(x + w, g["x"] + g["w"]) - max(x, g["x"]) < 0.25 * min(w, g["w"])
                   for g in gifts):
                break
        paper = rng.choice(GIFT_PAPER)
        ribbon = max(rng.sample(GIFT_RIBBON, 3), key=lambda c: color_distance(c, paper))   # contrasting
        pattern = rng.choice(GIFT_PATTERNS)
        pattern_rgb = rng.choice([(1, 1, 1), (1.0, 0.85, 0.35), shaded(paper, 0.6), ribbon])
        if color_distance(pattern_rgb, paper) < 0.3:
            pattern_rgb = shaded(paper, 0.55)
        gifts.append({
            "round": round_box, "x": x, "yb": yb, "w": w, "h": h, "d": d,
            "paper": paper, "ribbon": ribbon, "pattern": pattern, "pattern_rgb": pattern_rgb,
            "pattern_size": rng.uniform(3.5, 6), "pattern_turn": rng.choice((1, -1)),
            "lid": rng.random() < 0.55, "lid_k": rng.uniform(0.16, 0.26),
            "ribbons": rng.choice(["cross", "cross", "band", "double"]),
            "bow": rng.choice(["loops", "loops", "rosette", "none"]),
            "bow_size": rng.uniform(0.8, 1.2),
            "tag": rng.random() < 0.35, "tag_turn": rng.uniform(-0.4, 0.4),
        })
    return sorted(gifts, key=lambda g: g["yb"])


def paper_pattern(cr, g, U, V, k):
    """Paper print inside a face (face coordinates, px)."""
    s = g["pattern_size"]
    cr.set_source_rgba(*shaded(g["pattern_rgb"], k), 0.85)
    kind = g["pattern"]
    if kind == "stripes":
        cr.set_line_width(s * 0.35)
        for i in range(-int(V / s) - 2, int(U / s) + 3):
            x0 = i * s
            cr.move_to(x0, 0) if g["pattern_turn"] > 0 else cr.move_to(x0 + V, 0)
            cr.line_to(x0 + V, V) if g["pattern_turn"] > 0 else cr.line_to(x0, V)
        cr.stroke()
    elif kind in ("dots", "stars", "snowflakes"):
        row = 0
        y = s * 0.5
        while y < V + s:
            x = s * (0.5 if row % 2 == 0 else 1.0)
            while x < U + s:
                if kind == "dots":
                    cr.arc(x, y, s * 0.17, 0, 2 * math.pi)
                    cr.fill()
                elif kind == "stars":
                    star_path(cr, x, y, s * 0.3, s * 0.13)
                    cr.fill()
                else:
                    cr.set_line_width(0.35)
                    for a in range(3):
                        ang = a * math.pi / 3
                        cr.move_to(x - math.cos(ang) * s * 0.28, y - math.sin(ang) * s * 0.28)
                        cr.line_to(x + math.cos(ang) * s * 0.28, y + math.sin(ang) * s * 0.28)
                    cr.stroke()
                x += s
            y += s * 0.9
            row += 1
    elif kind == "checks":
        cr.set_source_rgba(*shaded(g["pattern_rgb"], k), 0.3)
        for i in range(int(U / s) + 1):
            for j in range(int(V / s) + 1):
                if (i + j) % 2 == 0:
                    cr.rectangle(i * s, j * s, s, s)
        cr.fill()
    elif kind == "zigzag":
        cr.set_line_width(0.6)
        y = s * 0.6
        while y < V + s:
            cr.move_to(0, y)
            x, up = 0.0, True
            while x < U + s:
                x += s * 0.5
                cr.line_to(x, y - s * 0.25 if up else y + s * 0.25)
                up = not up
            y += s
        cr.stroke()


def gift_face(cr, g, origin, eu, ev, U, V, k, bands=()):
    """
    One face of a box: paper, print, ribbon bands, edge. origin + u*eu + v*ev, u in [0, U], v in [0, V].
    bands: ("u", pos) - band across the face at u = pos, ("v", pos) - at v = pos.
    """
    cr.save()
    cr.transform(cairo.Matrix(eu[0], eu[1], ev[0], ev[1], origin[0], origin[1]))
    cr.rectangle(0, 0, U, V)
    cr.clip()
    cr.set_source_rgb(*shaded(g["paper"], k))
    cr.paint()
    paper_pattern(cr, g, U, V, k)
    rw = max(2.0, g["w"] * 0.12)
    for axis, pos in bands:
        rect = (pos - rw / 2, 0, rw, V) if axis == "u" else (0, pos - rw / 2, U, rw)
        cr.rectangle(*rect)
        cr.set_source_rgb(*shaded(g["ribbon"], k))
        cr.fill()
        cr.set_line_width(0.35)                            # satin: light middle line, darker edges
        cr.set_source_rgba(1, 1, 1, 0.35)
        if axis == "u":
            cr.move_to(pos - rw * 0.15, 0)
            cr.line_to(pos - rw * 0.15, V)
        else:
            cr.move_to(0, pos - rw * 0.15)
            cr.line_to(U, pos - rw * 0.15)
        cr.stroke()
        cr.set_source_rgba(0, 0, 0, 0.25)
        cr.rectangle(*rect)
        cr.stroke()
    cr.set_source_rgba(0, 0, 0, 0.3)
    cr.set_line_width(0.5)
    cr.rectangle(0, 0, U, V)
    cr.stroke()
    cr.restore()


def draw_bow(cr, g, bx, by):
    """Bow on the top: two loops with tails, or a rosette of many loops."""
    size = max(3.0, g["w"] * 0.17) * g["bow_size"]
    rgb = g["ribbon"]
    if g["bow"] == "none":
        return
    if g["bow"] == "rosette":
        loops = 9
        for i in range(loops):
            a = i * 2 * math.pi / loops + 0.2
            cr.save()
            cr.translate(bx + math.cos(a) * size * 0.55, by - size * 0.35 + math.sin(a) * size * 0.3)
            cr.rotate(a)
            cr.scale(size * 0.6, size * 0.3)
            cr.arc(0, 0, 1, 0, 2 * math.pi)
            cr.restore()
            cr.set_source_rgb(*shaded(rgb, 0.8 + 0.35 * (math.sin(a) + 1) / 2))   # front loops lighter
            cr.fill_preserve()
            cr.set_source_rgba(0, 0, 0, 0.25)
            cr.set_line_width(0.35)
            cr.stroke()
    else:
        for side in (-1, 1):                                # tails
            cr.move_to(bx, by - size * 0.3)
            cr.curve_to(bx + side * size * 0.4, by + size * 0.2, bx + side * size * 0.7, by + size * 0.5,
                        bx + side * size * 0.9, by + size * 0.9)
            cr.line_to(bx + side * size * 0.6, by + size * 0.75)
            cr.curve_to(bx + side * size * 0.45, by + size * 0.4, bx + side * size * 0.2, by + size * 0.1,
                        bx, by - size * 0.2)
            cr.close_path()
            cr.set_source_rgb(*shaded(rgb, 0.8))
            cr.fill()
        for side in (-1, 1):                                # loops with a dark inside
            cr.save()
            cr.translate(bx + side * size * 0.75, by - size * 0.6)
            cr.rotate(side * 0.45)
            cr.scale(size * 0.8, size * 0.5)
            cr.arc(0, 0, 1, 0, 2 * math.pi)
            cr.restore()
            cr.set_source_rgb(*rgb)
            cr.fill_preserve()
            cr.set_source_rgba(0, 0, 0, 0.3)
            cr.set_line_width(0.4)
            cr.stroke()
            cr.save()
            cr.translate(bx + side * size * 0.7, by - size * 0.6)
            cr.rotate(side * 0.45)
            cr.scale(size * 0.4, size * 0.2)
            cr.arc(0, 0, 1, 0, 2 * math.pi)
            cr.restore()
            cr.set_source_rgb(*shaded(rgb, 0.5))
            cr.fill()
    cr.arc(bx, by - size * 0.45, size * 0.28, 0, 2 * math.pi)  # knot
    cr.set_source_rgb(*shaded(rgb, 1.15))
    cr.fill()


def draw_tag(cr, g, x, y):
    """Gift tag on a string, hanging over the front."""
    cr.set_source_rgba(0.9, 0.85, 0.7, 0.9)
    cr.set_line_width(0.3)
    cr.move_to(x, y)
    cr.line_to(x - 2, y + 4)
    cr.stroke()
    cr.save()
    cr.translate(x - 2, y + 4)
    cr.rotate(g["tag_turn"])
    cr.rectangle(-3, 0, 6, 4)
    cr.set_source_rgb(0.96, 0.92, 0.82)
    cr.fill_preserve()
    cr.set_source_rgba(0, 0, 0, 0.3)
    cr.stroke()
    cr.set_source_rgba(0.6, 0.15, 0.1, 0.7)               # "To: ..." scribble
    cr.move_to(-2, 1.6)
    cr.line_to(1.5, 1.6)
    cr.move_to(-2, 2.8)
    cr.line_to(0.5, 2.8)
    cr.stroke()
    cr.restore()


def draw_box_gift(cr, g):
    x, yb, w, h, d = g["x"], g["yb"], g["w"], g["h"], g["d"]
    up = (1, -0.6)                                         # one px of depth on screen
    lid_h = h * g["lid_k"] if g["lid"] else 0.0
    body_top = yb - h + lid_h
    front_bands = {"cross": [("u", w / 2)], "band": [("u", w / 2)],
                   "double": [("u", w * 0.33), ("u", w * 0.67)]}[g["ribbons"]]
    side_bands = [("u", d / 2)] if g["ribbons"] == "cross" else []

    gift_face(cr, g, (x + w, body_top), up, (0, 1), d, h - lid_h, 0.62, side_bands)
    gift_face(cr, g, (x, body_top), (1, 0), (0, 1), w, h - lid_h, 1.0, front_bands)
    if g["lid"]:
        o = 1.0                                            # lid is a bit bigger than the box
        shadow = cairo.LinearGradient(0, body_top, 0, body_top + 2.5)   # lid shadow on the box
        shadow.add_color_stop_rgba(0, 0, 0, 0, 0.35)
        shadow.add_color_stop_rgba(1, 0, 0, 0, 0)
        cr.rectangle(x, body_top, w, 2.5)
        cr.set_source(shadow)
        cr.fill()
        lx, lw, ld = x - o, w + 2 * o, d + o
        lid_front = [(a, p + o) for a, p in front_bands]
        gift_face(cr, g, (lx + lw, yb - h), up, (0, 1), ld, lid_h, 0.7, [(a, p + o / 2) for a, p in side_bands])
        gift_face(cr, g, (lx, yb - h), (1, 0), (0, 1), lw, lid_h, 1.08, lid_front)
        top = ((lx, yb - h), lw, ld)
    else:
        top = ((x, yb - h), w, d)
    (tx, ty), tw, td = top
    top_bands = [(a, p + (tw - w) / 2) for a, p in front_bands]
    if g["ribbons"] == "cross":
        top_bands.append(("v", td / 2))
    gift_face(cr, g, (tx, ty), (1, 0), up, tw, td, 1.22, top_bands)
    bx, by = tx + tw / 2 + td / 2, ty - td * 0.3
    if g["tag"]:
        draw_tag(cr, g, bx - 1, by)
    draw_bow(cr, g, bx, by)


def draw_round_gift(cr, g):
    """Round hat box: cylinder body, lid with a rim, ribbon over the top."""
    x, yb, w, h = g["x"], g["yb"], g["w"], g["h"]
    cx, rx = x + w / 2, w / 2
    ry = rx * 0.35
    lid_h = max(3.0, h * g["lid_k"])

    def body(top, bottom, r):
        cr.new_path()
        cr.save()
        cr.translate(cx, bottom)
        cr.scale(r, ry * r / rx)
        cr.arc(0, 0, 1, 0, math.pi)
        cr.restore()
        cr.save()
        cr.translate(cx, top)
        cr.scale(r, ry * r / rx)
        cr.arc_negative(0, 0, 1, math.pi, 0)
        cr.restore()
        cr.close_path()

    for top, bottom, r, k in ((yb - h + lid_h, yb, rx, 1.0), (yb - h, yb - h + lid_h, rx + 1, 1.08)):
        body(top, bottom, r)
        cr.save()
        cr.clip_preserve()
        cr.set_source_rgb(*shaded(g["paper"], k))
        cr.fill_preserve()
        cr.save()
        cr.translate(cx - r, top - ry)
        paper_pattern(cr, g, 2 * r, bottom - top + 2 * ry, k)
        cr.restore()
        shade = cairo.LinearGradient(cx - r, 0, cx + r, 0)          # round shading, light from the left
        shade.add_color_stop_rgba(0, 1, 1, 1, 0.15)
        shade.add_color_stop_rgba(0.35, 1, 1, 1, 0)
        shade.add_color_stop_rgba(1, 0, 0, 0, 0.45)
        cr.set_source(shade)
        cr.paint()
        rw = max(2.0, w * 0.12)                                       # ribbon down the front
        cr.rectangle(cx - rw / 2, top, rw, bottom - top + ry)
        cr.set_source_rgb(*shaded(g["ribbon"], k))
        cr.fill()
        cr.restore()
        body(top, bottom, r)
        cr.set_source_rgba(0, 0, 0, 0.3)
        cr.set_line_width(0.5)
        cr.stroke()

    cr.save()                                                          # top of the lid
    cr.translate(cx, yb - h)
    cr.scale(rx + 1, ry * (rx + 1) / rx)
    cr.arc(0, 0, 1, 0, 2 * math.pi)
    cr.restore()
    cr.set_source_rgb(*shaded(g["paper"], 1.22))
    cr.fill_preserve()
    cr.save()
    cr.clip()
    cr.rectangle(cx - max(2.0, w * 0.12) / 2, yb - h - ry - 2, max(2.0, w * 0.12), 2 * ry + 4)
    cr.set_source_rgb(*shaded(g["ribbon"], 1.1))
    cr.fill()
    cr.restore()
    if g["tag"]:
        draw_tag(cr, g, cx - 1, yb - h)
    draw_bow(cr, g, cx, yb - h)


def gifts_parts(rng, floor_half):
    """Gifts as two bitmaps: behind the trunk and in front of it (the tree puts its layers between)."""
    if not SHOW_GIFTS:
        return [], []
    def part_for(gifts):
        part, cr = tree_part(0, TREE_BASE_Y - 60, TREE_W, TREE_H - TREE_BASE_Y + 60)
        part["mode"] = "static"
        for g in gifts:                                    # soft contact shadows first
            cx, w = g["x"] + (g["w"] + g["d"]) / 2, g["w"] + g["d"]
            cr.save()
            cr.translate(cx, g["yb"] - 1)
            cr.scale(w * 0.62, 2.6)
            cr.arc(0, 0, 1, 0, 2 * math.pi)
            cr.restore()
            cr.set_source_rgba(0, 0, 0, 0.28)
            cr.fill()
        for g in gifts:
            (draw_round_gift if g["round"] else draw_box_gift)(cr, g)
        return part

    if not RANDOM_GIFTS:
        part, cr = tree_part(0, TREE_BASE_Y - 50, TREE_W, TREE_H - TREE_BASE_Y + 50)
        part["mode"] = "static"
        cr.translate(TREE_W / 2 - BASE_TREE_W / 2, TREE_BASE_Y - BASE_GROUND)   # classic gifts at the ground
        for gift in GIFTS:
            draw_gift(cr, *gift)
        return [], [part]
    floor_half = max(60.0, min(TREE_W / 2 - 2, floor_half))
    gifts = random_gifts(rng, floor_half)
    back = [g for g in gifts if g["yb"] < TREE_BASE_Y - 1]
    front = [g for g in gifts if g["yb"] >= TREE_BASE_Y - 1]
    return ([part_for(back)] if back else []), ([part_for(front)] if front else [])


def classic_tree(seed):
    """
    The previous fixed cartoon tree (TREE_STYLE = "classic"). Its picture is scaled to the tree
    height; ornaments, garland bulbs and the star keep their size, only their positions follow.
    """
    k = tree_k()
    ox, oy = TREE_W / 2 - BASE_TREE_W / 2 * k, TREE_BASE_Y - BASE_GROUND * k
    at = lambda x, y: (ox + x * k, oy + y * k)
    return {
        "parts": [*render_static_tree(seed), *sum(gifts_parts(random.Random(seed + 1), 88 * k), [])],
        "topper": random_topper(random.Random(seed + 2), 14 * k + TREE_Y + oy) if RANDOM_TOPPER else None,
        "scale": k, "origin": (ox, oy),
        "ornaments": [(*at(x, y), shape) for x, y, shape in ORNAMENTS],
        "garlands": [(*at(x1, y1), *at(x2, y2), sag * k, max(2, round(n * k))) for x1, y1, x2, y2, sag, n in GARLANDS],
        "star": at(BASE_TREE_W / 2, 14),
    }


def render_static_tree(seed):
    """
    Classic tree parts: back (ground shadow, trunk), each branch layer separately (so it can bend
    in the wind), front (gifts). Rendered once at startup, then just copied every frame.
    """
    rng = random.Random(42)                                # same look on every start
    cx = BASE_TREE_W / 2
    res = 2 * max(1.0, tree_k())                           # sharp also when drawn bigger
    back, cr = tree_part(0, 190, BASE_TREE_W, BASE_TREE_H - 190, res)
    back.update(mode="static", scaled=True)
    draw_ground_shadow(cr, cx, 247, 85)
    draw_trunk(cr, rng)

    shapes = [layer_shape(apex, bottom, half, rng) for apex, bottom, half in LAYERS]
    layers = []
    for i in reversed(range(len(LAYERS))):                 # lower layers behind upper ones
        apex, bottom, half = LAYERS[i]
        ops, tips = shapes[i]
        part, cr = tree_part(cx - half - 8, apex - 4, 2 * half + 16, bottom - apex + 14, res)
        part.update(mode="shear", apex=apex, bottom=bottom, scaled=True)
        layers.append(part)

        trace(cr, ops)
        grad = cairo.LinearGradient(cx - half, 0, cx + half, 0)   # light from the left
        grad.add_color_stop_rgb(0, 0.17, 0.50, 0.23)
        grad.add_color_stop_rgb(0.45, 0.09, 0.38, 0.16)
        grad.add_color_stop_rgb(1, 0.03, 0.21, 0.09)
        cr.set_source(grad)
        cr.fill_preserve()

        cr.save()
        cr.clip()
        if i > 0:                                          # shadow from the layer above
            upper = LAYERS[i - 1][1]
            dark = cairo.LinearGradient(0, upper - 6, 0, upper + 14)
            dark.add_color_stop_rgba(0, 0, 0, 0, 0.45)
            dark.add_color_stop_rgba(1, 0, 0, 0, 0)
            cr.set_source(dark)
            cr.paint()
        cr.set_line_width(0.6)                             # needles
        for _ in range(int(half * (bottom - apex) / 10)):
            t = rng.random() ** 0.7
            y = apex + (bottom - apex) * t
            x = cx + rng.uniform(-half * t, half * t)
            side = 1 if x >= cx else -1
            angle = math.radians(rng.uniform(20, 55))
            length = rng.uniform(3, 6)
            light = 0.5 - 0.5 * (x - cx) / (half + 1)      # 1 = lit left side
            cr.set_source_rgba(0.06 + 0.12 * light, 0.26 + 0.32 * light * rng.uniform(0.6, 1), 0.1 + 0.1 * light, 0.55)
            cr.move_to(x, y)
            cr.line_to(x + side * math.cos(angle) * length, y + math.sin(angle) * length)
            cr.stroke() if SHOW_NEEDLES else cr.new_path()   # rng is used either way: same tree
        cr.restore()

        for x, y in tips:                                  # a bit of snow on branch tips
            if rng.random() < 0.45:
                cr.save()
                cr.translate(x, y - 2.5)
                cr.scale(2.3, 1.2)
                cr.arc(0, 0, 1, 0, 2 * math.pi)
                cr.restore()
                cr.set_source_rgba(1, 1, 1, 0.8)
                cr.fill() if SHOW_SNOW else cr.new_path()

    return [back, *layers]


# ---------- random spruce ----------

def blend(a, b, k):
    return tuple(x + (y - x) * k for x, y in zip(a, b))


def draw_cone(cr, x, y, length, tilt, rgb):
    """Spruce cone hanging from a branch: short stalk, scaled body."""
    w = length * 0.36
    cr.save()
    cr.translate(x, y)
    cr.rotate(tilt)
    cr.set_source_rgb(*(c * 0.6 for c in rgb))
    cr.set_line_width(0.7)
    cr.move_to(0, 0)
    cr.line_to(0, 1.6)
    cr.stroke()
    grad = cairo.LinearGradient(-w, 0, w, 0)
    grad.add_color_stop_rgb(0, *(min(1, c * 1.3) for c in rgb))
    grad.add_color_stop_rgb(1, *(c * 0.5 for c in rgb))
    cr.save()
    cr.translate(0, 1.5 + length / 2)
    cr.scale(w, length / 2)
    cr.arc(0, 0, 1, 0, 2 * math.pi)
    cr.restore()
    cr.set_source(grad)
    cr.fill()
    cr.set_source_rgba(*(c * 0.35 for c in rgb), 0.8)  # scales: rows of small arcs
    cr.set_line_width(0.35)
    rows = max(3, int(length / 1.7))
    for r in range(1, rows):
        k = r / rows
        yy = 1.5 + length * k
        hw = w * math.sqrt(max(0.0, 1 - (2 * k - 1) ** 2))
        for c in (-0.5, 0.0, 0.5):
            cr.new_sub_path()
            cr.arc(c * hw, yy - 0.6, hw * 0.33, 0.2, math.pi - 0.2)
        cr.stroke()
    cr.restore()


class Spruce:
    """
    Random spruce built like a real one, in separate steps with their own randomness:
      trunk    - slightly curved, tapered, root flare; own bark color, fissures, knots, dead stubs;
      branches - whorls all around the trunk (3D, seen slightly from above); length follows the crown
                 outline with uneven sides; upper ones point up, lower ones droop, tips curl up;
                 side twigs grow from each branch, its inner part stays bare like on a real spruce;
      needles  - grow on every twig; each twig has its own needle density, so there are denser and
                 sparser spots; color depends on light, depth, fresh tips;
      cones    - hang under some upper branches.
    Ornament, garland and star positions come from the generated branches. Same seed = same tree.
    """

    def __init__(self, seed, progress=None):
        self.seed = seed
        self.progress = progress or (lambda share: None)   # build progress 0..1 for the loader
        self.rng = rng = random.Random(seed)
        self.k = k = tree_k()                               # sizes below are for the default tree
        self.cx = TREE_W / 2
        self.top = rng.uniform(*SPRUCE_TOP_Y) * k
        self.bottom = rng.uniform(*SPRUCE_CROWN_BOTTOM) * k
        self.half = rng.uniform(*SPRUCE_HALF_W) * k
        self.fullness = rng.uniform(*SPRUCE_FULLNESS)        # outline exponent: <1 full top, >1 slender
        self.uneven = rng.uniform(0.9, 1.1)                 # one side longer than the other
        self.waves = [rng.uniform(0, 2 * math.pi) for _ in range(3)]
        # Trunk has its own random source, so its look does not change the branch layout.
        trng = self.trunk_rng = random.Random(seed * 7919 + 13)
        self.lean = trng.uniform(-SPRUCE_LEAN, SPRUCE_LEAN) * k
        straight = trng.random() < SPRUCE_STRAIGHT
        # bends: (amplitude, half-waves over the height); 0.5 = bow to one side, 1 = arc, 1.5+ = S-curve
        self.bends = [(trng.uniform(-1, 1) * SPRUCE_TRUNK_BEND * k * (0.15 if straight else 1.0),
                       trng.uniform(0.5, 1.8)) for _ in range(trng.choice((1, 1, 2)))]
        self.wiggle = [trng.uniform(0, 2 * math.pi) for _ in range(2)]
        # sabre: the trunk leaves the ground at an angle and straightens up (tree grown on a slope)
        self.sabre = (0.0 if straight or trng.random() < 0.4 else
                      trng.choice((1, -1)) * trng.uniform(0.4, 1.0) * SPRUCE_TRUNK_BEND * k, trng.uniform(10, 28) * k)
        self.trunk_r = trng.uniform(*SPRUCE_TRUNK_R) * k ** 1.15    # taller trees are relatively thicker
        self.flare = self.trunk_r * trng.uniform(0.35, 0.8)           # root flare
        self.bark_scale = trng.uniform(0.8, 1.3) * k ** 0.5          # bark plate size
        self.bark_rgb = blend(trng.choice([(0.38, 0.31, 0.25), (0.40, 0.26, 0.16), (0.30, 0.28, 0.26)]),
                              (0.36, 0.30, 0.24), trng.uniform(0, 0.5))   # grey-brown, reddish, dark grey
        self.whorls = []
        self.wood_rgb = blend(self.bark_rgb, (0.17, 0.14, 0.10), 0.6)
        self.needle_rgb = blend((0.05, 0.31, 0.13), (0.09, 0.30, 0.28), rng.random() ** 2)  # green .. blue spruce
        self.cone_rgb = blend((0.42, 0.25, 0.11), (0.56, 0.36, 0.19), rng.random())
        self.snow = SPRUCE_SNOW * rng.random() ** 2                # 0 = no snow on branches
        self.fresh = rng.uniform(0, SPRUCE_FRESH)                 # share of light-green fresh tips
        self.branches = []
        self.cones = []
        self.low_limit = TREE_BASE_Y - (SPRUCE_TRUNK_ROOM + 5) * k   # lowest twig; needles hang up to 5 px more

    # ----- shape -----

    def h(self, y):
        """0 at the leader tip, 1 at the lowest branches."""
        return max(0.0, min(1.0, (y - self.top) / (self.bottom - self.top)))

    def outline(self, y):
        """Crown half width at height y."""
        return self.half * self.h(y) ** self.fullness * (1 + 0.06 * math.sin(y / self.k * 0.13 + self.waves[2]))

    def trunk_u(self, y):
        """0 at the leader tip, 1 at the ground."""
        return max(0.0, min(1.0, (y - self.top) / (TREE_BASE_Y - self.top)))

    def trunk_x(self, y):
        """Trunk center line: base stays in place; lean, bow or S-curve over the height, small waves."""
        u = self.trunk_u(y)
        x = self.cx + self.lean * (1 - u) ** 1.5
        for amp, waves in self.bends:
            x += amp * math.sin(math.pi * waves * (1 - u))       # zero at the ground
        x += (0.5 * math.sin(u * 9 + self.wiggle[0]) + 0.25 * math.sin(u * 23 + self.wiggle[1])) * self.k * (1 - u)
        amount, reach = self.sabre
        x += amount * (1 - math.exp(-max(0.0, TREE_BASE_Y - y) / reach))   # bend right above the ground
        return x

    def trunk_w(self, y):
        """Trunk half width: thin leader, slight swelling at branch whorls, root flare at the ground."""
        u = self.trunk_u(y)
        w = 0.6 * self.k ** 0.5 + (self.trunk_r - 0.6 * self.k ** 0.5) * u ** 0.8
        zone = 16 * self.k
        flare = max(0.0, (y - (TREE_BASE_Y - zone)) / zone)
        w += self.flare * flare ** 2.2
        for wy in self.whorls:                                     # branch collars
            d = (y - wy) / (1.5 * self.k)
            if abs(d) < 3:
                w += 0.25 * self.k * u * math.exp(-d * d)
        return w

    def bark_xy(self, theta, y):
        """Point on the visible half of the trunk cylinder: theta -pi/2 (left edge) .. pi/2 (right edge)."""
        return self.trunk_x(y) + self.trunk_w(y) * math.sin(theta)

    @staticmethod
    def bark_light(theta):
        """Cylinder lighting, light from the left."""
        return 0.38 + 0.8 * max(0.0, math.cos(theta + 0.55))

    @staticmethod
    def project(length, az, pitch):
        """3D step (azimuth around the trunk, pitch down from horizontal) -> screen dx, dy."""
        flat = length * math.cos(pitch)
        return flat * math.cos(az), length * math.sin(pitch) + flat * math.sin(az) * 0.2

    @staticmethod
    def along(pts, f):
        """Point and pitch at fraction f of a branch polyline."""
        i = min(len(pts) - 2, int(f * (len(pts) - 1)))
        k = f * (len(pts) - 1) - i
        (x0, y0, p0), (x1, y1, p1) = pts[i], pts[i + 1]
        return x0 + (x1 - x0) * k, y0 + (y1 - y0) * k, p0 + (p1 - p0) * k

    # ----- growth -----

    def grow(self):
        rng = self.rng
        y = self.top + rng.uniform(5, 9)
        while y < self.bottom:
            self.progress(0.12 * (y - self.top) / max(1.0, self.bottom - self.top))   # ~12% of the build
            self.whorls.append(y)
            hy = self.h(y)
            n = rng.randint(*SPRUCE_BRANCHES)
            turn = rng.uniform(0, 2 * math.pi)
            for j in range(n):
                if rng.random() < SPRUCE_GAPS * hy:               # a missing branch leaves a gap
                    continue
                az = turn + 2 * math.pi * j / n + rng.uniform(-0.35, 0.35)
                side = self.uneven if math.cos(az) > 0 else 1 / self.uneven
                reach = 0.55 + 0.45 * abs(math.cos(az))      # turned branches look shorter, grow them longer
                length = max(4.0, self.outline(y) * side * rng.uniform(0.85, 1.08) / reach)
                self.branches.append(self.branch(y, az, length, hy))
                self.progress(0.12 * (y - self.top) / max(1.0, self.bottom - self.top))   # also lets a frame in
            y += rng.uniform(*SPRUCE_WHORL_GAP) * (1 + 0.8 * hy)

        # cones hang under some upper branches on the visible side
        spots = [b for b in self.branches if b["hy"] < 0.65 and b["depth"] > -0.3 and b["len"] > 14]
        total = round(rng.randint(*SPRUCE_CONES) * self.k)
        for b in rng.sample(spots, min(len(spots), total)):
            for _ in range(min(rng.choice((1, 1, 2)), total - len(self.cones))):   # sometimes a pair
                f = rng.uniform(0.55, 0.9)
                x, y, _ = self.along(b["pts"], f)
                cone = {"x": x + rng.uniform(-1, 1), "y": y + 1, "len": rng.uniform(6, 9),
                        "tilt": rng.uniform(-0.25, 0.25), "f": f}
                b["cones"].append(cone)
                self.cones.append(cone)

    def limb(self, rng, x, y, az, pitch, length, bend, droop):
        """
        A curved side limb: its direction wanders (smoothed random turns = natural bends) and
        sinks under its weight. Returns points (x, y, pitch, azimuth).
        """
        steps = max(3, int(length / 2.2))
        pts = [(x, y, pitch, az)]
        turn_az = turn_pitch = 0.0
        for _ in range(steps):
            turn_az = 0.6 * turn_az + rng.gauss(0, bend)
            turn_pitch = 0.6 * turn_pitch + rng.gauss(0, bend)
            az += turn_az
            pitch += turn_pitch + droop / steps
            dx, dy = self.project(length / steps, az, pitch)
            x, y = x + dx, y + dy
            pts.append((x, y, pitch, az))
        return pts

    def branch(self, y, az, length, hy):
        """
        One branch from the trunk, built like a real one: the main limb bends randomly, side limbs
        grow from it alternately left and right, and small twigs from those. Needles come later.
        twigs: (points, depth, place on the main limb 0..1, order 2 = side limb / 3 = twig).
        """
        rng = self.rng
        pitch0 = -0.35 + 0.7 * hy + rng.uniform(-0.12, 0.12)   # upper ones point up, lower ones droop
        sag = rng.uniform(0.1, 0.3)                          # bends down under its own weight
        curl = rng.uniform(0.15, 0.45)                       # tip turns up
        trng = random.Random(rng.random())                   # shape of this branch
        x, yy = self.trunk_x(y), y
        pts, azs = [(x, yy, pitch0)], [az]
        steps = max(4, int(length / 3))
        wander_pitch = wander_az = 0.0
        for i in range(1, steps + 1):
            f = i / steps
            wander_pitch = 0.75 * wander_pitch + trng.gauss(0, 0.06)   # the main limb is never straight
            wander_az = 0.75 * wander_az + trng.gauss(0, 0.05)
            pitch = pitch0 + sag * f - curl * smoothstep((f - 0.6) / 0.4) + wander_pitch
            dx, dy = self.project(length / steps, az + wander_az, pitch)
            x, yy = x + dx, yy + dy
            pts.append((x, yy, pitch))
            azs.append(az + wander_az)

        twigs = []
        s = length * trng.uniform(0.15, 0.3)                 # inner part of the branch stays bare
        side = trng.choice((1, -1))
        while s < length * 0.97:
            f = s / length
            tx, ty, pitch = self.along(pts, f)
            local_az = azs[min(len(azs) - 1, round(f * (len(azs) - 1)))]
            for sd in ((side, -side) if trng.random() < 0.7 else (side,)):
                sub_az = local_az + sd * trng.uniform(0.55, 1.05)
                sub_len = min(18.0 * self.k, (1 - f) ** 0.7 * length * 0.45 * trng.uniform(0.7, 1.2) + 3.5)
                sub = self.limb(trng, tx, ty, sub_az, pitch + trng.uniform(-0.35, 0.5), sub_len, 0.09, 0.35)
                twigs.append(([p[:2] for p in sub], math.sin(sub_az), f, 2))
                g = trng.uniform(0.2, 0.35)                  # twigs on the side limb
                twig_side = trng.choice((1, -1))
                while g < 0.95:
                    twig_len = (1 - g) ** 0.8 * sub_len * 0.5 * trng.uniform(0.6, 1.2) + 1.5
                    if twig_len > 2.5 and trng.random() < 0.75:
                        i = min(len(sub) - 1, round(g * (len(sub) - 1)))
                        sx, sy, sp, sa = sub[i]
                        twig_az = sa + twig_side * trng.uniform(0.6, 1.1)
                        twig = self.limb(trng, sx, sy, twig_az, sp + trng.uniform(-0.3, 0.5), twig_len, 0.12, 0.3)
                        twigs.append(([p[:2] for p in twig], math.sin(twig_az), f, 3))
                    twig_side = -twig_side
                    g += trng.uniform(2.0, 3.5) / sub_len
            side = -side
            s += trng.uniform(2.5, 4.5)

        # A low branch must not reach the ground: the whole branch with its twigs is lifted
        # (its drop scaled down) so it keeps its shape, only its lowest point meets the limit.
        low = max([p[1] for p in pts] + [p[1] for t in twigs for p in t[0]])
        if low > self.low_limit:
            squash = max(0.0, (self.low_limit - y) / (low - y))
            lift = lambda py: y + (py - y) * squash
            pts = [(px, lift(py), math.atan(math.tan(pitch) * squash)) for px, py, pitch in pts]
            twigs = [([(px, lift(py)) for px, py in line], depth, f, order) for line, depth, f, order in twigs]

        # Long branches bend in the wind at a joint: the outer part is lighter and swings on its own.
        joint = trng.uniform(0.45, 0.6) if length > 14 * self.k else 1.01
        snowy = trng.random() < self.snow and math.sin(az) > -0.4
        snow = []                                            # clumps on the outer part, decided here
        if snowy:
            f = trng.uniform(0.45, 0.7)
            while f < 0.97:
                if trng.random() < 0.55:
                    sx, sy, _ = self.along(pts, f)
                    snow.append((f, sx + trng.uniform(-1, 1), sy - 1.4, trng.uniform(1.1, 2.4), trng.uniform(0.6, 1.1)))
                f += trng.uniform(0.06, 0.12)
        return {"pts": pts, "twigs": twigs, "az": az, "depth": math.sin(az), "len": length, "hy": hy,
                "vigor": rng.uniform(0.75, 1.25), "cones": [], "joint": joint, "snowy": snowy, "snow": snow}

    # ----- drawing -----

    def add_needles(self, needles, line, depth, vigor, outer):
        """Needles along a twig. Each twig gets its own density: denser and sparser spots."""
        rng = self.rng
        rand = rng.random                                    # hot loop: plain random() calls
        len_lo, len_span = NEEDLE_LEN[0], NEEDLE_LEN[1] - NEEDLE_LEN[0]
        far = 0.55 + 0.45 * (depth + 1) / 2                  # far side of the tree is darker
        density = rng.uniform(*NEEDLE_DENSITY) * vigor
        fresh = rng.random() < self.fresh
        segs = [(a, b, math.hypot(b[0] - a[0], b[1] - a[1])) for a, b in zip(line, line[1:])]
        total = sum(s[2] for s in segs)
        pos, done, si = rng.uniform(0, 1 / density), 0.0, 0
        while pos < total:
            while si < len(segs) - 1 and pos > done + segs[si][2]:
                done += segs[si][2]
                si += 1
            (x0, y0), (x1, y1), ln = segs[si]
            k = (pos - done) / ln if ln else 0
            x, y = x0 + (x1 - x0) * k, y0 + (y1 - y0) * k
            tx, ty = ((x1 - x0) / ln, (y1 - y0) / ln) if ln else (1, 0)
            frac = pos / total
            light = 0.5 - 0.5 * (x - self.cx) / self.half        # lit from the left
            base = 0.45 + 0.35 * light + 0.35 * outer
            tip = fresh and frac > 0.75
            for side in (1, -1):
                if rand() > 0.85:
                    continue
                a = side * (0.55 + 0.65 * rand())               # needles point forward along the twig
                length = (len_lo + len_span * rand()) * (0.55 + 0.45 * rand()) * (1 - 0.3 * frac)
                ca, sa = math.cos(a), math.sin(a)
                nx = tx * ca - ty * sa
                ny = tx * sa + ty * ca + 0.2
                shade = (base - 0.35 * ny) * far * (0.85 + 0.3 * rand())
                level = max(0, min(9, int(shade * 7)))
                bucket = needles.get((level, tip))
                if bucket is None:
                    bucket = needles[(level, tip)] = []
                bucket.append((x, y, x + nx * length, y + ny * length))
            pos += (0.6 + 0.8 * rand()) / density

    def stroke_needles(self, cr, needles):
        """Needles are grouped by shade, one stroke per group."""
        if not SHOW_NEEDLES:
            return
        cr.set_line_width(0.8)
        cr.set_line_cap(cairo.LINE_CAP_BUTT)
        for (level, fresh), segs in needles.items():
            rgb = tuple(min(1.0, c * (0.3 + 0.16 * level)) for c in self.needle_rgb)
            if fresh:
                rgb = blend(rgb, (0.40, 0.64, 0.30), 0.45)
            cr.set_source_rgba(*rgb, 0.92)
            for x0, y0, x1, y1 in segs:
                cr.move_to(x0, y0)
                cr.line_to(x1, y1)
            cr.stroke()

    def link_of(self, b, f):
        """0 = inner part of the branch, 1 = outer part (beyond the joint)."""
        return 1 if f >= b["joint"] else 0

    def draw_branch(self, cr, b, link=None):
        """Wood, needles, snow and cones of a branch; link 0/1 draws only the inner/outer part."""
        pts = b["pts"]
        n = len(pts) - 1
        cut = round(b["joint"] * n) if link is not None and b["joint"] < 1 else None
        mine = lambda f: link is None or self.link_of(b, f) == link
        dark = 0.6 + 0.4 * (b["depth"] + 1) / 2              # far side of the tree is darker
        wood = tuple(c * dark for c in self.wood_rgb)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_source_rgb(*wood)
        for i in range(n):                                   # main limb: thick at the trunk, thin at the tip
            if cut is not None and (i < cut) != (link == 0):
                continue
            cr.set_line_width(max(0.5, 1.4 * (1 - i / n) * min(1.0, b["len"] / 30)))
            cr.move_to(*pts[i][:2])
            cr.line_to(*pts[i + 1][:2])
            cr.stroke()

        needles = {}
        mine_twigs = [t for t in b["twigs"] if mine(t[2])]
        # wood: side limbs taper in two steps, twigs are thin; one stroke per group is much faster
        for alpha, width, pieces in ((0.85, 0.6, [t[0][:len(t[0]) // 2 + 1] for t in mine_twigs if t[3] == 2]),
                                     (0.85, 0.42, [t[0][len(t[0]) // 2:] for t in mine_twigs if t[3] == 2]),
                                     (0.7, 0.35, [t[0] for t in mine_twigs if t[3] == 3])):
            for line in pieces:
                cr.move_to(*line[0])
                for p in line[1:]:
                    cr.line_to(*p)
            cr.set_source_rgba(*wood, alpha)
            cr.set_line_width(width)
            cr.stroke()
        for line, depth, f, order in mine_twigs:
            # needles: on the outer part of side limbs, all along the small twigs
            m = len(line) - 1
            self.add_needles(needles, line[int(m * 0.35):] if order == 2 else line, depth, b["vigor"], f)
        first = int(n * 0.3)                                 # needles on the main limb itself
        outer = [p[:2] for p in pts[first:]]
        if cut is not None:
            outer = [p[:2] for p in (pts[first:cut + 1] if link == 0 else pts[max(first, cut):])]
        if len(outer) > 1:
            self.add_needles(needles, outer, b["depth"], b["vigor"], 1.0)
        self.stroke_needles(cr, needles)

        cr.set_source_rgba(1, 1, 1, 0.8)
        for f, x, y, sx, sy in (b["snow"] if SHOW_SNOW else ()):   # snow lies on the outer part
            if mine(f):
                cr.save()
                cr.translate(x, y)
                cr.scale(sx, sy)
                cr.arc(0, 0, 1, 0, 2 * math.pi)
                cr.restore()
                cr.fill()
        for c in b["cones"]:
            if mine(c["f"]):
                draw_cone(cr, c["x"], c["y"], c["len"], c["tilt"], self.cone_rgb)

    def trunk_path(self, cr, ys):
        cr.move_to(self.trunk_x(ys[0]) - self.trunk_w(ys[0]), ys[0])
        for y in ys[1:]:
            cr.line_to(self.trunk_x(y) - self.trunk_w(y), y)
        for y in reversed(ys):
            cr.line_to(self.trunk_x(y) + self.trunk_w(y), y)
        cr.close_path()

    def draw_roots(self, cr):
        """Roots spreading into the ground at the sides, drawn before the trunk covers their upper part."""
        rng, g, k = self.trunk_rng, TREE_BASE_Y, self.k
        for _ in range(rng.randint(2, 4)):
            side = rng.choice((1, -1))
            theta = side * rng.uniform(0.7, 1.35)
            y0 = g - self.flare * rng.uniform(1.2, 2.6) - 4 * k
            x0 = self.bark_xy(theta, y0)
            reach = self.trunk_w(g) + rng.uniform(2, 6) * k
            x1, y1 = self.trunk_x(g) + side * reach, g + rng.uniform(0.5, 2)
            inner = self.trunk_x(g) + side * self.trunk_w(g) * 0.4
            cr.move_to(x0, y0)
            cr.curve_to(x0 + 0.4 * (x1 - x0), y0 + (y1 - y0) * 0.65,
                        x1 - side * 2 * k, y1 - 1.2 * k, x1, y1)
            cr.line_to(inner, g + 1.5)
            cr.close_path()
            grad = cairo.LinearGradient(x0, y0, x1, y1)
            grad.add_color_stop_rgb(0, *shaded(self.bark_rgb, self.bark_light(theta)))
            grad.add_color_stop_rgb(1, *shaded(self.bark_rgb, 0.45))
            cr.set_source(grad)
            cr.fill_preserve()
            cr.set_source_rgba(*shaded(self.bark_rgb, 0.3), 0.6)
            cr.set_line_width(0.4)
            cr.stroke()

    def draw_trunk(self, cr):
        """
        Trunk as a cylinder: row shading, scaly bark plates mapped onto the cylinder (narrower at the
        edges), fissures between them, lichen, resin, knots, crown shadow, roots and dead stubs.
        """
        rng, k, g = self.trunk_rng, self.k, TREE_BASE_Y
        dark = shaded(self.bark_rgb, 0.3)
        ys = [self.top + i for i in range(int(g - self.top) + 1)] + [g]

        self.draw_roots(cr)
        self.trunk_path(cr, ys)
        cr.save()
        cr.clip()
        for y in ys:                                               # cylinder shading row by row
            x, w = self.trunk_x(y), self.trunk_w(y) + 0.5
            grad = cairo.LinearGradient(x - w, 0, x + w, 0)
            for stop in (0, 0.15, 0.3, 0.5, 0.7, 0.85, 1):
                grad.add_color_stop_rgb(stop, *shaded(self.bark_rgb, self.bark_light(math.asin(stop * 2 - 1))))
            cr.set_source(grad)
            cr.rectangle(x - w, y, 2 * w, 1.05)
            cr.fill()

        # Bark scales: small flakes overlapping like roof tiles (upper ones over lower ones),
        # narrower towards the cylinder edges, a dark crack under each one.
        area = sum(2 * self.trunk_w(y) for y in ys)
        plate = 3.0 * 4.5 * self.bark_scale ** 2
        weathered = blend(self.bark_rgb, (0.58, 0.55, 0.52), 0.35)
        flakes = []
        for _ in range(int(area / plate * 2.4)):
            y = rng.uniform(self.top + 2, g + 1)
            if self.trunk_w(y) < 1.3:                              # thin leader: smooth
                continue
            theta = rng.uniform(-1.5, 1.5)
            pw = rng.uniform(2.0, 4.0) * self.bark_scale * math.cos(theta)
            if pw >= 0.35:
                flakes.append((y, theta, pw, rng.uniform(3.0, 6.0) * self.bark_scale,
                               weathered if rng.random() < 0.2 else self.bark_rgb, rng.uniform(0.9, 1.1)))
        for y, theta, pw, ph, base, tone in sorted(flakes, reverse=True):   # bottom first
            x = self.bark_xy(theta, y)
            cr.save()
            cr.translate(x, y)
            cr.scale(pw, ph)
            cr.move_to(-0.5, 0.45)                                 # rounded top, ragged bottom edge
            cr.curve_to(-0.58, -0.25, -0.25, -0.52, 0, -0.5)
            cr.curve_to(0.25, -0.52, 0.58, -0.25, 0.5, 0.45)
            cr.line_to(0.18, 0.38)
            cr.line_to(-0.08, 0.5)
            cr.close_path()
            cr.restore()
            cr.set_source_rgb(*shaded(base, self.bark_light(theta) * tone))
            cr.fill()
            cr.save()                                              # crack under the flake
            cr.translate(x, y)
            cr.scale(pw, ph)
            cr.move_to(-0.5, 0.45)
            cr.line_to(-0.08, 0.5)
            cr.line_to(0.18, 0.38)
            cr.line_to(0.5, 0.45)
            cr.restore()
            cr.set_source_rgba(*dark, 0.55)
            cr.set_line_width(0.35)
            cr.stroke()
            if theta < 0.5:                                        # lit top edge
                cr.save()
                cr.translate(x, y)
                cr.scale(pw, ph)
                cr.move_to(-0.42, -0.2)
                cr.curve_to(-0.3, -0.45, 0.1, -0.5, 0.3, -0.42)
                cr.restore()
                cr.set_source_rgba(1, 0.96, 0.88, 0.16)
                cr.set_line_width(0.3)
                cr.stroke()

        for _ in range(int(rng.uniform(3, 7) * self.trunk_r / (5 * k ** 0.5))):    # long fissures
            theta = rng.uniform(-1.2, 1.2)
            y = rng.uniform(self.top + 30 * k, g - 4)
            end = min(g, y + rng.uniform(15, 50) * k)
            cr.move_to(self.bark_xy(theta, y), y)
            while y < end:
                y += 1.5
                theta = max(-1.4, min(1.4, theta + rng.uniform(-0.06, 0.06)))
                cr.line_to(self.bark_xy(theta, y), y)
            cr.set_source_rgba(*dark, rng.uniform(0.3, 0.5))
            cr.set_line_width(rng.uniform(0.3, 0.55) * k ** 0.3)
            cr.stroke()

        if rng.random() < 0.55:                                    # lichen on one side, lower part
            lichen = rng.choice([(0.58, 0.65, 0.48), (0.66, 0.70, 0.62), (0.45, 0.55, 0.35)])
            for _ in range(rng.randint(1, 3)):
                ty, th = rng.uniform(self.bottom, g - 6 * k), rng.uniform(-0.3, 1.0)
                for _ in range(int(rng.uniform(12, 35) * k)):
                    t2 = max(-1.4, min(1.4, th + rng.gauss(0, 0.25)))
                    y = ty + rng.gauss(0, 3 * k)
                    cr.arc(self.bark_xy(t2, y), y, rng.uniform(0.25, 0.8), 0, 2 * math.pi)
                    cr.set_source_rgba(*shaded(lichen, self.bark_light(t2) * 1.1), 0.75)
                    cr.fill()

        for _ in range(rng.randint(1, 3)):                         # knots / old branch scars
            y = rng.uniform(self.bottom - 30 * k, g - 12 * k)
            theta = rng.uniform(-0.9, 0.9)
            x = self.bark_xy(theta, y)
            rw, rh = rng.uniform(0.8, 1.4) * k ** 0.5 * math.cos(theta), rng.uniform(0.6, 1.0) * k ** 0.5
            light = self.bark_light(theta)
            for scale_k, color in ((1.7, shaded(self.bark_rgb, light * 1.15)),      # swollen collar
                                   (1.0, shaded(self.bark_rgb, light * 0.55))):     # healed scar
                cr.save()
                cr.translate(x, y)
                cr.scale(rw * scale_k, rh * scale_k)
                cr.arc(0, 0, 1, 0, 2 * math.pi)
                cr.restore()
                cr.set_source_rgba(*color, 0.9)
                cr.fill()

        if rng.random() < 0.4:                                     # resin drops with a drip trail
            for _ in range(rng.randint(1, 3)):
                y = rng.uniform(self.bottom - 20 * k, g - 15 * k)
                theta = rng.uniform(-0.8, 0.8)
                x = self.bark_xy(theta, y)
                drip = rng.uniform(1.5, 4) * k ** 0.5
                cr.set_source_rgba(0.85, 0.55, 0.12, 0.8)
                cr.set_line_width(0.7)
                cr.move_to(x, y)
                cr.line_to(x, y + drip)
                cr.stroke()
                cr.arc(x, y + drip, 0.9 * k ** 0.4, 0, 2 * math.pi)
                cr.fill()
                cr.arc(x - 0.3, y + drip - 0.3, 0.3, 0, 2 * math.pi)
                cr.set_source_rgba(1, 1, 0.85, 0.9)
                cr.fill()

        shade = cairo.LinearGradient(0, self.bottom - 10 * k, 0, self.bottom + 25 * k)   # crown shadow
        shade.add_color_stop_rgba(0, 0, 0, 0, 0.45)
        shade.add_color_stop_rgba(1, 0, 0, 0, 0)
        cr.set_source(shade)
        cr.rectangle(0, self.top, TREE_W, self.bottom + 25 * k - self.top)
        cr.fill()
        ground = cairo.LinearGradient(0, g - 8 * k, 0, g)          # darker at the ground
        ground.add_color_stop_rgba(0, 0, 0, 0, 0)
        ground.add_color_stop_rgba(1, 0, 0, 0, 0.35)
        cr.set_source(ground)
        cr.rectangle(0, g - 8 * k, TREE_W, 8 * k + 1)
        cr.fill()
        cr.restore()

        self.trunk_path(cr, ys)                                   # thin dark edge
        cr.set_source_rgba(*dark, 0.5)
        cr.set_line_width(0.4)
        cr.stroke()

        for _ in range(rng.randint(0, 3)):                         # dead stubs below the crown
            y = rng.uniform(self.bottom - 5 * k, g - 18 * k)
            side = rng.choice((1, -1))
            x = self.trunk_x(y) + side * self.trunk_w(y) * 0.8
            length = rng.uniform(3, 7) * k
            drop = rng.uniform(0.5, 3) * k
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            for width, color in ((rng.uniform(0.8, 1.3) * k ** 0.5, shaded(self.wood_rgb, 0.8)),
                                 (0.35, shaded(self.wood_rgb, 1.3))):     # dry wood + lit top edge
                cr.set_source_rgb(*color)
                cr.set_line_width(width)
                cr.move_to(x, y - (0.3 if width < 0.4 else 0))
                cr.line_to(x + side * length, y + drop - (0.3 if width < 0.4 else 0))
                cr.stroke()
            if self.snow > 0.2 and SHOW_SNOW:
                cr.set_source_rgba(1, 1, 1, 0.8)
                cr.arc(x + side * length * 0.6, y - 0.4, 0.8, 0, 2 * math.pi)
                cr.fill()

    def draw_core(self, cr):
        """Dark inside of the crown, so it is not see-through between branches."""
        rng = self.rng
        core = tuple(c * 0.35 for c in self.needle_rgb)
        for _ in range(round(260 * self.k ** 2)):
            y = rng.uniform(self.top + 10, self.bottom)
            w = self.outline(y) * 0.4
            cr.set_source_rgba(*core, 0.1)
            cr.arc(self.trunk_x(y) + rng.uniform(-w, w), y, rng.uniform(4, 9) * self.k * (0.5 + 0.5 * self.h(y)),
                   0, 2 * math.pi)
            cr.fill() if SHOW_NEEDLES else cr.new_path()      # dense needles inside; rng used either way

    def branch_sprites(self, branches):
        """Every branch in its own small bitmap, so it can swing around its attach point."""
        sprites = []
        for b in branches:
            jx, jy, _ = self.along(b["pts"], min(1.0, b["joint"]))
            n = len(b["pts"]) - 1
            for link in ((0, 1) if b["joint"] < 1 else (0,)):   # inner part, outer part
                cut = round(b["joint"] * n)
                main = b["pts"] if b["joint"] >= 1 else (b["pts"][:cut + 1] if link == 0 else b["pts"][cut:])
                pts = [p[:2] for p in main] + [p for line, _, f, _ in b["twigs"]
                                                if b["joint"] >= 1 or self.link_of(b, f) == link for p in line]
                x0, x1 = min(p[0] for p in pts) - 8, max(p[0] for p in pts) + 8
                y0, y1 = min(p[1] for p in pts) - 8, max(p[1] for p in pts) + 16   # needles, snow, cones
                sprite, cr = tree_part(x0, y0, x1 - x0, y1 - y0)
                self.draw_branch(cr, b, link if b["joint"] < 1 else None)
                sprite.update(branch=self.branches.index(b), link=link, ax=b["pts"][0][0], ay=b["pts"][0][1],
                              jx=jx, jy=jy, filter=cairo.FILTER_BILINEAR)   # 3x faster than GOOD, same at 1:2
                sprites.append(sprite)
            self.sprites_done = getattr(self, "sprites_done", 0) + 1   # branch bitmaps: ~83% of the build
            self.progress(0.12 + 0.83 * self.sprites_done / max(1, len(self.branches)))
        return {"mode": "branches", "sprites": sprites}

    def branch_physics(self):
        """
        Wind properties of every branch (a simplified model, not real mechanics):
          mass      - needles + wood, snow and cones add weight: slower, longer swing;
          sail      - needle area that catches the wind (snow adds a bit);
          strength  - own random stiffness; long branches are softer;
          shelter   - how much foliage of other branches stands between this branch and the wind,
                      from the left, from the right and from above (density map of the crown).
        """
        rng = random.Random(self.seed * 104729 + 3)
        cell = 5 * self.k
        grid, own = {}, []
        for b in self.branches:                              # density map of the crown
            self.progress(0.95)                              # no new share, only lets a frame in
            mine = {}
            for line in [[p[:2] for p in b["pts"]]] + [t[0] for t in b["twigs"]]:
                for (xa, ya), (xb, yb) in zip(line, line[1:]):
                    n = max(1, int(math.hypot(xb - xa, yb - ya) / (cell * 0.5)))
                    for i in range(n):
                        key = (int((xa + (xb - xa) * (i + 0.5) / n) // cell), int((ya + (yb - ya) * (i + 0.5) / n) // cell))
                        mine[key] = mine.get(key, 0) + b["vigor"]
            own.append(mine)
            for key, v in mine.items():
                grid[key] = grid.get(key, 0) + v

        steps = int(2.4 * self.half / cell) + 2
        raw = []
        for b, mine in zip(self.branches, own):              # foliage of others between the branch and the wind
            self.progress(0.96)
            x, y, _ = self.along(b["pts"], 0.6)
            cx, cy = int(x // cell), int(y // cell)
            sums = []
            for dx, dy in ((-1, 0), (1, 0), (0, -1)):        # wind from the left, from the right, from above
                total = 0.0
                for i in range(1, steps):
                    for side, weight in ((0, 1.0), (-1, 0.5), (1, 0.5)):   # a ray 3 cells wide
                        key = (cx + dx * i + side * abs(dy), cy + dy * i + side * abs(dx))
                        total += weight * (grid.get(key, 0) - mine.get(key, 0))
                sums.append(max(0.0, total))
            raw.append(sums)
        positive = sorted(v for sums in raw for v in sums if v > 0)
        median = positive[len(positive) // 2] if positive else 1.0

        out = []
        for b, sums in zip(self.branches, raw):
            self.progress(0.98)
            length = b["len"] / self.k
            foliage = sum(math.hypot(xb - xa, yb - ya) for t in b["twigs"]
                          for (xa, ya), (xb, yb) in zip(t[0], t[0][1:])) / self.k * b["vigor"]
            outer = sum(math.hypot(xb - xa, yb - ya) for t in b["twigs"] if t[2] >= b["joint"]
                        for (xa, ya), (xb, yb) in zip(t[0], t[0][1:])) / self.k * b["vigor"]
            snow = 1.35 if b.get("snowy") and SHOW_SNOW else 1.0
            x, y, _ = self.along(b["pts"], 0.6)
            ax, ay = b["pts"][0][:2]
            reach = math.hypot(x - ax, y - ay) or 1.0
            dx, dy = (x - ax) / reach, (y - ay) / reach
            jx, jy, _ = self.along(b["pts"], min(1.0, b["joint"]))
            out.append({
                "ax": ax, "ay": ay, "dir": (dx, dy),
                "joint": (jx, jy) if b["joint"] < 1 else None,
                "jdist": (jx - ax) * dx + (jy - ay) * dy,        # points farther along belong to the outer part
                "outer": outer / max(1e-6, foliage),             # share of the foliage on the outer part
                "length": length, "mass": (foliage + 0.4 * length) * snow + 4 * len(b["cones"]),
                "sail": foliage * (1.1 if snow > 1 else 1.0), "strength": rng.uniform(0.7, 1.35),
                "exposure": [math.exp(-v / median * math.log(2.5)) for v in sums],   # median branch: 0.4
                "height": 1 - b["hy"],                         # wind is stronger higher up
                "flutter": (rng.uniform(1.5, 4.0), rng.uniform(0, 2 * math.pi),
                            rng.uniform(4.0, 9.0), rng.uniform(0, 2 * math.pi)),
            })
        means = {key: sum(o[key] for o in out) / len(out) for key in ("length", "mass", "sail")} if out else {}
        for o in out:
            o["sail"] /= means["sail"] or 1
            o["mass"] /= means["mass"] or 1
            o["length"] /= means["length"] or 1
            # natural frequency: stiff light branches swing fast, long heavy ones slowly
            o["freq"] = max(2.5, min(10.0, 5.0 * math.sqrt(o["strength"] / (o["length"] * o["mass"]))))
        return out

    def place_ornaments(self):
        """Ornaments hang under visible branches, not too close to each other or to cones."""
        rng = self.rng
        spots = []
        for i, b in enumerate(self.branches):
            if b["depth"] < -0.25 or b["hy"] < 0.1 or b["hy"] > SPRUCE_ORNAMENT_ZONE or b["len"] < 12:
                continue
            for _ in range(2):
                x, y, _ = self.along(b["pts"], rng.uniform(0.45, 0.85))
                spots.append((x, y + 9, i))
        rng.shuffle(spots)
        cones = [(c["x"], c["y"] + 5) for c in self.cones]
        taken = []
        want = round(rng.randint(*SPRUCE_ORNAMENTS) * self.k ** 1.5)   # more room on a bigger tree
        shapes, out = [], []
        for x, y, branch in spots:
            if len(out) >= want:
                break
            if (y < self.top + 28 or y > self.low_limit or any(math.hypot(x - ox, y - oy) < 18 for ox, oy in taken)
                    or any(math.hypot(x - ox, y - oy) < 11 for ox, oy in cones)):
                continue
            if not shapes:                                   # every shape before repeating
                shapes = list(ORNAMENT_DRAW)
                rng.shuffle(shapes)
            out.append((x, y, shapes.pop(), branch))         # the ornament moves with its branch
            taken.append((x, y))
        return out

    def place_garlands(self):
        """
        Garlands run across the front like a spiral, each with its own slant (not always level).
        They rest on the tops of branches: from edge to edge the next hook is the branch point nearest
        to the planned line; between hooks the wire sags under its weight (longer span = deeper).
        """
        rng = random.Random(self.seed * 15485863 + 11)      # own random source: branches stay as they are
        hooks = []                                           # branch tops a garland can rest on
        for i, b in enumerate(self.branches):
            if b["depth"] < -0.15 or b["len"] < 8:
                continue
            for f in (0.35, 0.5, 0.65, 0.8, 0.92):
                x, y, _ = self.along(b["pts"], f)
                hooks.append((x, y - 1.5, i))
        turn = rng.choice((1, -1))
        count = max(3, round(3 * self.k))
        out = []
        for n in range(count):
            ym = self.top + ((n + 0.75) / (count + 0.4) + rng.uniform(-0.04, 0.04)) * (self.bottom - self.top)
            slope = turn * rng.uniform(0.04, 0.32)           # spiral, every garland its own slant
            line = lambda x: ym + slope * (x - self.cx)
            half = self.outline(ym) * rng.uniform(0.8, 0.95)
            x, end = self.trunk_x(ym) - half, self.trunk_x(ym) + half
            anchors = []
            while x <= end + 1:
                near = [(math.hypot(hx - x, hy - line(x)), hx, hy, i) for hx, hy, i in hooks
                        if (not anchors or hx > anchors[-1][1] + 6 * self.k)]
                d, hx, hy, i = min(near, default=(1e9, 0, 0, None))
                if d < 15 * self.k:                          # no branch near the line: longer span
                    anchors.append((i, hx, hy))
                x += rng.uniform(10, 20) * self.k
            if len(anchors) < 2:
                continue
            sags, bulbs = [], []
            for j, ((_, x0, y0), (_, x1, y1)) in enumerate(zip(anchors, anchors[1:])):
                span = math.hypot(x1 - x0, y1 - y0)
                slack = rng.uniform(0.03, 0.1)               # extra wire length, share of the span
                sag = span * math.sqrt(3 * slack / 8) * GARLAND_SAG   # parabola sag for that slack
                sags.append(sag)
                wire = span + 8 * sag * sag / (3 * span)      # parabola length
                per = max(1, round(wire / 9))
                bulbs += [(j, (m + 0.5) / per) for m in range(per)]
            out.append({"anchors": anchors, "sags": sags, "bulbs": bulbs, "count": len(bulbs)})
        return out

    def build(self):
        self.grow()
        back, cr = tree_part(0, TREE_BASE_Y - 14, TREE_W, TREE_H - TREE_BASE_Y + 14)
        back["mode"] = "static"
        draw_ground_shadow(cr, self.cx, TREE_BASE_Y + 3, 85 * self.k)

        # Layers from back to front, gifts between them: back branches, gifts behind the trunk,
        # trunk, gifts in front of it, front branches (they hang over the gifts).
        margin = 30 * self.k                                 # branches may reach past the tree area

        def crown_layer():
            part, cr = tree_part(-margin, 0, TREE_W + 2 * margin, TREE_H)
            part.update(mode="strips", h=TREE_H, w=TREE_W + 2 * margin, filter=cairo.FILTER_BILINEAR)
            return part, cr

        reach = lambda b: b["depth"] * b["len"]              # how far the tip comes towards the viewer
        core, cr = crown_layer()
        self.draw_core(cr)
        back_branches = self.branch_sprites(sorted((b for b in self.branches if b["depth"] < -0.1), key=reach))

        ys = range(int(self.top), TREE_BASE_Y + 1)
        x0 = min(self.trunk_x(y) - self.trunk_w(y) for y in ys) - 10 * self.k   # room for stubs and leader needles
        x1 = max(self.trunk_x(y) + self.trunk_w(y) for y in ys) + 10 * self.k
        y0 = int(self.top) - 12
        trunk, cr = tree_part(x0, y0, x1 - x0, TREE_BASE_Y + 4 - y0)
        trunk.update(mode="strips", h=TREE_BASE_Y + 4 - y0, w=x1 - x0, filter=cairo.FILTER_BILINEAR)
        self.draw_trunk(cr)
        leader = {}                                          # needles on the leader above the top whorl
        self.add_needles(leader, [(self.trunk_x(self.top + 12), self.top + 12),
                                  (self.trunk_x(self.top), self.top)], 0.5, 1.2, 1.0)
        self.stroke_needles(cr, leader)

        front_branches = self.branch_sprites(sorted((b for b in self.branches if b["depth"] >= -0.1), key=reach))

        gifts_back, gifts_front = gifts_parts(random.Random(self.seed + 1), self.half * 1.05)
        star = (self.trunk_x(self.top), self.top - 2)
        return {"parts": [back, core, back_branches, *gifts_back, trunk, *gifts_front, front_branches],
                "branches": self.branch_physics(),
                "ornaments": self.place_ornaments(), "garlands": self.place_garlands(), "star": star,
                "topper": random_topper(random.Random(self.seed + 2), star[1] + TREE_Y) if RANDOM_TOPPER else None}


def build_tree(style, seed, progress=None):
    if style == "classic":
        return classic_tree(seed)
    return Spruce(seed, progress).build()


def paint_part(cr, part):
    cr.save()
    cr.translate(part["x"], part["y"])
    cr.scale(1 / part["res"], 1 / part["res"])
    cr.set_source_surface(part["surface"], 0, 0)
    cr.get_source().set_filter(part.get("filter", cairo.FILTER_GOOD))
    cr.paint()
    cr.restore()


class TreeSway:
    """
    Tree bending in the wind: a damped spring, so it sways back after a gust.
    The top moves most, the trunk base stays. Ornaments are pendulums on their hangers.
    """

    def __init__(self, ornaments, branches=(), garlands=()):
        self.bend = 0.0                                    # top shift, px
        self.bend_v = 0.0
        self.t = 0.0
        self.ornaments = ornaments
        self.branches = list(branches)
        self.angle = [0.0] * len(self.branches)            # branch rotation around its attach point
        self.angle_v = [0.0] * len(self.branches)
        self.squash = [0.0] * len(self.branches)           # <0 pressed to the trunk, >0 streaming out
        self.squash_v = [0.0] * len(self.branches)
        self.tip = [0.0] * len(self.branches)              # outer part turn at the joint
        self.tip_v = [0.0] * len(self.branches)
        # sagging garland spans are pendulums too: angle, velocity, own frequency
        spans = sum(len(g["sags"]) for g in garlands if isinstance(g, dict))
        self.gswing = [[0.0, 0.0, random.uniform(2.0, 3.5)] for _ in range(spans)]
        # per ornament: angle, angular velocity, own frequency, idle phase
        self.swing = [[0.0, 0.0, random.uniform(2.5, 4.5), random.uniform(0, 2 * math.pi)] for _ in ornaments]

    @staticmethod
    def profile(y):
        """How much height y (tree coords) follows the top: 1 at the top, 0 at the trunk base."""
        return max(0.0, (TREE_BASE_Y - y) / (TREE_BASE_Y - 10)) ** 1.7

    def offset(self, y):
        """Horizontal shift of the tree at height y."""
        return self.bend * self.profile(y)

    def step(self, dt, wind):
        self.t += dt
        w = max(-1.2, min(1.2, wind.vx / WIND_MAX))
        push = TREE_BEND_PX * tree_k() * math.copysign(abs(w) ** 1.5, w)   # drag grows faster than wind speed
        idle = TREE_IDLE_PX * tree_k() * (math.sin(self.t * 0.9) + 0.5 * math.sin(self.t * 2.3 + 1)) / 1.5
        old_v = self.bend_v
        self.bend, self.bend_v = spring(self.bend, self.bend_v, push + idle, TREE_FREQ, TREE_DAMP, dt)
        accel = (self.bend_v - old_v) / dt if dt > 0 else 0.0

        self.step_branches(dt, wind, accel)
        for s in self.gswing:                              # garland spans lean downwind, lag behind
            target = -0.5 * ORNAMENT_SWING * math.copysign(abs(w) ** 1.2, w) + 0.003 * accel
            s[0], s[1] = spring(s[0], s[1], target, s[2], 0.2, dt)
        for o, s in zip(self.ornaments, self.swing):
            y = o[1]
            angle, vel, freq, phase = s
            # downwind lean + lag when the branch moves + small own swing
            target = (-ORNAMENT_SWING * math.copysign(abs(w) ** 1.2, w)
                      + 0.004 * accel * self.profile(y)
                      + ORNAMENT_IDLE * math.sin(self.t * freq * 0.35 + phase))
            s[0], s[1] = spring(angle, vel, target, freq, 0.15, dt)


    def step_branches(self, dt, wind, accel):
        """
        Each branch is a damped spring, its softness = sail * length / strength.
          across the branch - the wind turns it;
          into the branch   - windward branches are pressed to the trunk and lift their tips;
          along the branch  - leeward branches stream out with the wind and droop a little;
          shelter, height   - weaken or strengthen the local wind; own flutter adds turbulence;
          trunk move        - branches lag behind (inertia).
        """
        if not self.branches:
            return
        wx, wy = wind.vx / WIND_MAX, wind.vy / WIND_MAX
        side = 0 if wx > 0 else 1                          # wind from the left / from the right
        across = abs(wx) + wy + 1e-6
        steps = max(1, math.ceil(dt * 60))                 # stiff springs need small steps
        h = dt / steps
        t = self.t
        for i, b in enumerate(self.branches):
            shelter = (abs(wx) * b["exposure"][side] + wy * b["exposure"][2]) / across
            k = (1 - BRANCH_SHELTER + BRANCH_SHELTER * shelter) * (0.65 + 0.35 * b["height"])
            f1, p1, f2, p2 = b["flutter"]
            gust = 1 + BRANCH_FLUTTER * (0.6 * math.sin(t * f1 + p1) + 0.4 * math.sin(t * f2 + p2))
            lx = wx * k * gust - 0.004 * accel * self.profile(b["ay"]) * b["mass"]   # inertia of the branch
            ly = wy * k * gust
            dx, dy = b["dir"]
            soft = BRANCH_BEND * b["sail"] * b["length"] / b["strength"]
            push = lx * -dy + ly * dx                      # wind across the branch
            along = lx * dx + ly * dy                      # < 0: the branch points into the wind
            target = soft * (0.25 * push * abs(push)
                             + -dx * (0.2 * max(0.0, -along) - 0.06 * max(0.0, along)))   # lift / droop
            target += BRANCH_FLUTTER * 0.08 * (abs(wx) + wy) * soft ** 0.5 * math.sin(t * f2 * 1.3 + p1)
            target = 0.45 * math.tanh(target / 0.45)
            squash = max(-0.25, min(0.08, soft * (-0.14 * max(0.0, -along) + 0.04 * max(0.0, along))))
            a, v, w = self.angle[i], self.angle_v[i], b["freq"]
            q, qv = self.squash[i], self.squash_v[i]
            # outer part: lighter, so it bends further and flutters faster; lags when the inner part moves
            tip_target = 0.45 * math.tanh(0.9 * target * (0.6 + b.get("outer", 0.5)) / 0.45)
            tip_target += BRANCH_FLUTTER * 0.06 * (abs(wx) + wy) * soft ** 0.5 * math.sin(t * f1 * 2.1 + p2)
            c, cv, tw = self.tip[i], self.tip_v[i], min(14.0, w * 1.8)
            for _ in range(steps):
                a0 = v
                a, v = spring(a, v, target, w, BRANCH_DAMP, h)
                q, qv = spring(q, qv, squash, w, BRANCH_DAMP, h)
                c, cv = spring(c, cv, tip_target - 0.02 * (v - a0) / h, tw, BRANCH_DAMP, h)
            self.angle[i], self.angle_v[i] = a, v
            self.squash[i], self.squash_v[i] = q, qv
            self.tip[i], self.tip_v[i] = c, cv

    def garland_swing(self, i):
        return self.gswing[i][0] if i < len(self.gswing) else 0.0

    def branch_point(self, i, x, y):
        """Where a point that belongs to branch i is now (branch turn + tree bend)."""
        b, a = self.branches[i], self.angle[i]
        ax, ay = b["ax"], b["ay"]
        if b.get("joint") and (x - ax) * b["dir"][0] + (y - ay) * b["dir"][1] > b["jdist"]:
            jx, jy = b["joint"]                            # outer part: first its own turn at the joint
            c, s = math.cos(self.tip[i]), math.sin(self.tip[i])
            x, y = jx + (x - jx) * c - (y - jy) * s, jy + (x - jx) * s + (y - jy) * c
        c, s = math.cos(a), math.sin(a)
        dx = (x - ax) * (1 + self.squash[i])
        return ax + dx * c - (y - ay) * s + self.offset(ay), ay + dx * s + (y - ay) * c


class ScaledSway:
    """Bend seen from inside a scaled drawing (classic tree picture)."""

    def __init__(self, sway, k, oy):
        self.sway, self.k, self.oy = sway, k, oy

    def offset(self, y):
        return self.sway.offset(self.oy + y * self.k) / self.k


STRIP_PX = 16                                              # random tree bends in strips of this height


def paint_sheared(cr, part, sway, top, bottom, clip=False):
    """Paint a part sheared so that y = top and y = bottom follow the bend."""
    d_top, d_bottom = sway.offset(top), sway.offset(bottom)
    k = (d_top - d_bottom) / (top - bottom)
    cr.save()
    cr.transform(cairo.Matrix(1, 0, k, 1, d_bottom - k * bottom, 0))
    if clip:                                               # whole-pixel strip edges: no seams between strips
        cr.rectangle(part["x"] - 20, top, part["w"] + 40, bottom - top)
        cr.clip()
    paint_part(cr, part)
    cr.restore()


def draw_tree(cr, tree, lights, t, show, sway):
    """Tree in its own coordinates (TREE_W x TREE_H): cached parts + animated parts."""
    k = tree.get("scale", 1.0)
    ox, oy = tree.get("origin", (0.0, 0.0))
    for part in tree["parts"]:
        if part.get("scaled"):                             # classic picture: drawn k times bigger
            cr.save()
            cr.translate(ox, oy)
            cr.scale(k, k)
            view = ScaledSway(sway, k, oy)
            if part["mode"] == "shear":                    # each layer sheared as a whole
                paint_sheared(cr, part, view, part["apex"], part["bottom"])
            else:
                paint_part(cr, part)
            cr.restore()
        elif part["mode"] == "branches":                   # random: every branch turns on its own
            for sprite in part["sprites"]:
                i = sprite["branch"]
                ax, ay = sprite["ax"], sprite["ay"]
                cr.save()
                cr.translate(ax + sway.offset(ay), ay)
                if i < len(sway.angle):
                    cr.rotate(sway.angle[i])
                    cr.scale(1 + sway.squash[i], 1)        # pressed to the trunk / streaming out
                cr.translate(-ax, -ay)
                if sprite.get("link") == 1 and i < len(sway.tip):   # outer part bends at the joint
                    cr.translate(sprite["jx"], sprite["jy"])
                    cr.rotate(sway.tip[i])
                    cr.translate(-sprite["jx"], -sprite["jy"])
                paint_part(cr, sprite)
                cr.restore()
        elif part["mode"] == "strips":                     # one bitmap, bent strip by strip
            y0 = int(part["y"])
            for a in range(y0, y0 + int(part["h"]), STRIP_PX):
                paint_sheared(cr, part, sway, a, min(a + STRIP_PX, y0 + int(part["h"])), clip=True)
        else:
            paint_part(cr, part)

    draw_garlands(cr, tree["garlands"], t, show, sway)
    draw_ornaments(cr, tree["ornaments"], lights, sway)

    if not SHOW_TOPPER:
        return
    # topper follows the tree top
    sx, sy = tree["star"]
    cx = sx + sway.offset(sy)
    cr.save()
    cr.translate(cx, sy)
    cr.rotate((sway.offset(sy) - sway.offset(sy + 20)) / 20)
    cr.translate(-cx, -sy)
    if tree.get("topper"):
        draw_topper(cr, tree["topper"], cx, sy, t)
        cr.restore()
        return
    glow = cairo.RadialGradient(cx, sy, 3, cx, sy, 24)
    glow.add_color_stop_rgba(0, 1, 0.9, 0.3, 0.35 + 0.15 * math.sin(t * 2))
    glow.add_color_stop_rgba(1, 1, 0.9, 0.3, 0)
    cr.set_source(glow)
    cr.arc(cx, sy, 24, 0, 2 * math.pi)
    cr.fill()
    cr.set_source_rgb(1.0, 0.85, 0.0)
    star_path(cr, cx, sy, 15, 6.5)
    cr.fill()
    cr.restore()


# ---------- topper ----------

# (main color, highlight color)
TOPPER_COLORS = {
    "gold": ((1.0, 0.80, 0.15), (1.0, 0.96, 0.65)),
    "silver": ((0.75, 0.78, 0.84), (1.0, 1.0, 1.0)),
    "red": ((0.85, 0.08, 0.10), (1.0, 0.60, 0.55)),
    "blue": ((0.18, 0.42, 0.95), (0.70, 0.85, 1.0)),
    "white": ((0.88, 0.92, 1.0), (1.0, 1.0, 1.0)),
    "rose": ((0.92, 0.45, 0.62), (1.0, 0.82, 0.88)),
}
TOPPER_KINDS = ["star", "star", "double", "bethlehem", "spire", "snowflake"]


def random_topper(rng, room):
    """Random tree topper. room: free px above the anchor point, so the topper is not cut off."""
    room = max(10.0, room - 2)
    return {
        "kind": rng.choice(TOPPER_KINDS),
        "color": rng.choice(list(TOPPER_COLORS)),
        "color2": rng.choice(list(TOPPER_COLORS)),
        "points": rng.choice((5, 5, 6, 7, 8)),
        "inner": rng.uniform(0.36, 0.5),
        "size": min(rng.uniform(11, 16), room),
        "spire_h": min(rng.uniform(28, 40), room + 6),
        "turn": rng.uniform(-0.12, 0.12),
        "phase": rng.uniform(0, 2 * math.pi),
    }


def topper_glow(cr, x, y, rgb, radius, t, phase):
    glow = cairo.RadialGradient(x, y, 2, x, y, radius)
    glow.add_color_stop_rgba(0, *rgb, 0.35 + 0.15 * math.sin(t * 2 + phase))
    glow.add_color_stop_rgba(1, *rgb, 0)
    cr.set_source(glow)
    cr.arc(x, y, radius, 0, 2 * math.pi)
    cr.fill()


def topper_star(cr, x, y, size, points, inner, rgb, light, turn=0.0):
    """Star with a shiny gradient and a thin edge."""
    cr.save()
    cr.translate(x, y)
    cr.rotate(turn)
    star_path(cr, 0, 0, size, size * inner, points)
    grad = cairo.RadialGradient(-size * 0.3, -size * 0.35, 1, 0, 0, size)
    grad.add_color_stop_rgb(0, *light)
    grad.add_color_stop_rgb(0.5, *rgb)
    grad.add_color_stop_rgb(1, *shaded(rgb, 0.7))
    cr.set_source(grad)
    cr.fill_preserve()
    cr.set_source_rgba(*shaded(rgb, 0.55), 0.8)
    cr.set_line_width(0.6)
    cr.stroke()
    for i in range(points):                                # ridge lines: the star looks faceted
        a = -math.pi / 2 + i * 2 * math.pi / points
        cr.move_to(0, 0)
        cr.line_to(size * 0.85 * math.cos(a), size * 0.85 * math.sin(a))
    cr.set_source_rgba(1, 1, 1, 0.3)
    cr.set_line_width(0.5)
    cr.stroke()
    cr.restore()


def draw_topper(cr, spec, x, y, t):
    rgb, light = TOPPER_COLORS[spec["color"]]
    s = spec["size"]
    kind = spec["kind"]
    cr.save()
    cr.translate(x, y)
    cr.rotate(spec["turn"])
    cr.translate(-x, -y)
    if kind == "star":
        topper_glow(cr, x, y, light, s * 1.6, t, spec["phase"])
        topper_star(cr, x, y, s, spec["points"], spec["inner"], rgb, light)
    elif kind == "double":                                 # two stars, the back one turned half a point
        rgb2, light2 = TOPPER_COLORS[spec["color2"]]
        topper_glow(cr, x, y, light, s * 1.7, t, spec["phase"])
        topper_star(cr, x, y, s, spec["points"], spec["inner"], rgb2, light2, math.pi / spec["points"])
        topper_star(cr, x, y, s * 0.72, spec["points"], spec["inner"], rgb, light)
    elif kind == "bethlehem":                              # long ray down, shorter rays to the sides and up
        topper_glow(cr, x, y, light, s * 1.8, t, spec["phase"])
        twinkle = 1 + 0.08 * math.sin(t * 3 + spec["phase"])
        rays = [(-math.pi / 2, s * 0.9), (math.pi / 2, s * 1.9), (0, s), (math.pi, s)]
        rays += [(a, s * 0.5) for a in (-math.pi / 4, -3 * math.pi / 4, math.pi / 4, 3 * math.pi / 4)]
        for a, length in rays:
            length *= twinkle
            w = 1.6 if length > s * 0.6 else 1.0
            tx, ty = x + math.cos(a) * length, y + math.sin(a) * length
            nx, ny = -math.sin(a) * w, math.cos(a) * w
            cr.move_to(x + nx, y + ny)
            cr.line_to(tx, ty)
            cr.line_to(x - nx, y - ny)
            cr.close_path()
            grad = cairo.LinearGradient(x, y, tx, ty)
            grad.add_color_stop_rgba(0, *light, 1)
            grad.add_color_stop_rgba(1, *rgb, 0.5)
            cr.set_source(grad)
            cr.fill()
        cr.arc(x, y, 2.4, 0, 2 * math.pi)
        cr.set_source_rgb(1, 1, 1)
        cr.fill()
    elif kind == "spire":                                  # glass finial: two balls and a spike
        h = spec["spire_h"]
        base = y + 6
        topper_glow(cr, x, base - h * 0.4, light, h * 0.6, t, spec["phase"])
        cr.move_to(x - 1.5, base + 2)                      # spike first, the balls cover its foot
        cr.line_to(x, base - h)
        cr.line_to(x + 1.5, base + 2)
        cr.close_path()
        grad = cairo.LinearGradient(x - 1.5, 0, x + 1.5, 0)
        grad.add_color_stop_rgb(0, *light)
        grad.add_color_stop_rgb(1, *shaded(rgb, 0.7))
        cr.set_source(grad)
        cr.fill()
        for by, r in ((base - h * 0.18, 6.0), (base - h * 0.48, 3.6)):
            ball = cairo.RadialGradient(x - r * 0.35, by - r * 0.35, 0.5, x, by, r)
            ball.add_color_stop_rgb(0, *light)
            ball.add_color_stop_rgb(0.45, *rgb)
            ball.add_color_stop_rgb(1, *shaded(rgb, 0.5))
            cr.arc(x, by, r, 0, 2 * math.pi)
            cr.set_source(ball)
            cr.fill()
            cr.set_source_rgba(1, 1, 1, 0.8)               # glass shine
            cr.arc(x - r * 0.4, by - r * 0.4, r * 0.18, 0, 2 * math.pi)
            cr.fill()
            cr.set_source_rgb(0.85, 0.78, 0.45)            # metal rings
            cr.rectangle(x - r * 0.35, by + r * 0.85, r * 0.7, 1.2)
            cr.fill()
    else:                                                  # snowflake
        topper_glow(cr, x, y, light, s * 1.6, t, spec["phase"])
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        for width, color in ((2.4, shaded(rgb, 0.6)), (1.2, light)):
            cr.set_line_width(width)
            cr.set_source_rgb(*color)
            for i in range(6):
                a = -math.pi / 2 + i * math.pi / 3
                ex, ey = x + s * math.cos(a), y + s * math.sin(a)
                cr.move_to(x, y)
                cr.line_to(ex, ey)
                for f, length in ((0.45, 0.35), (0.72, 0.25)):
                    mx, my = x + s * f * math.cos(a), y + s * f * math.sin(a)
                    for side in (-0.7, 0.7):
                        cr.move_to(mx, my)
                        cr.line_to(mx + s * length * math.cos(a + side), my + s * length * math.sin(a + side))
            cr.stroke()
        for i in range(6):                                 # crystal beads at the tips
            a = -math.pi / 2 + i * math.pi / 3
            cr.arc(x + s * math.cos(a), y + s * math.sin(a), 1.3, 0, 2 * math.pi)
            cr.set_source_rgb(*light)
            cr.fill()
        cr.arc(x, y, 2.2, 0, 2 * math.pi)
        cr.set_source_rgb(*rgb)
        cr.fill()
    cr.restore()


# ---------- logo ----------

def smoother(x):
    """0..1 with zero speed and zero acceleration at both ends."""
    x = max(0.0, min(1.0, x))
    return x * x * x * (x * (6 * x - 15) + 10)


class Flight:
    """
    The logo flies patterns over the whole scene: orbit around the tree, figure eight, Lissajous
    figure, big loop, free wandering. Each lasts FLIGHT_PATTERN_S, then the next one starts near
    the current point, in the same direction, and the two are blended with zero speed and
    acceleration jumps. Depth z: > 0 in front of the tree, < 0 behind it.
    """

    KINDS = ["orbit", "orbit", "figure8", "lissajous", "loop", "wander"]

    def __init__(self):
        self.t = 0.0
        self.cur = self.make("orbit", 0.0, random.uniform(0, 2 * math.pi), random.choice((1, -1)))
        self.prev = None
        self.blend_at = 0.0
        self.next_change = random.uniform(*FLIGHT_PATTERN_S)
        self.tilt = self.tilt_v = 0.0
        self.face, self.face_v = 1.0, 0.0                  # 1 = facing the viewer, 0 = edge-on

    @staticmethod
    def make(kind, t0, phase, direction):
        """One pattern with random size and speed, fitted into the current window."""
        w, h, m = WIDTH, HEIGHT, 30
        k = tree_k()
        p = {"kind": kind, "t0": t0, "phase": phase, "dir": direction, "cx": w / 2}
        if kind == "orbit":                                # around the tree, close to the crown
            p.update(ax=random.uniform(*ORBIT_RX_RANGE) * k, ay=random.uniform(*ORBIT_RY_RANGE) * k,
                     cy=TREE_Y + (random.uniform(*ORBIT_Y_RANGE) - TREE_Y) * k, w=random.uniform(*SPEED_RANGE))
            p["depth"] = p["ax"]
        elif kind == "figure8":
            p.update(ax=random.uniform(0.3, 0.42) * w, ay=random.uniform(0.12, 0.25) * h,
                     cy=random.uniform(0.35, 0.65) * h, w=random.uniform(0.35, 0.7))
            p["depth"] = p["ax"] * 0.6
        elif kind == "lissajous":
            p.update(ax=random.uniform(0.3, 0.4) * w, ay=random.uniform(0.25, 0.35) * h, cy=h / 2,
                     w=random.uniform(0.2, 0.4), ratio=random.choice([(1, 2), (2, 3), (3, 2), (1, 3), (3, 4)]),
                     shift=random.uniform(0, math.pi))
            p["depth"] = p["ax"] * 0.5
        elif kind == "loop":                               # big loop through the whole scene
            p.update(ax=random.uniform(0.32, 0.42) * w, ay=random.uniform(0.28, 0.4) * h, cy=h / 2,
                     w=random.uniform(0.35, 0.7), zshift=random.uniform(0, 2 * math.pi))
            p["depth"] = p["ax"] * 0.6
        else:                                              # wander: slow mix of waves on every axis
            p.update(ax=w / 2 - m - LOGO_W / 2, ay=h / 2 - m, cy=h / 2, w=1.0,
                     waves=[(random.uniform(0.12, 0.4), random.uniform(0, 2 * math.pi)) for _ in range(5)])
            p["depth"] = w * 0.25
        return p

    @staticmethod
    def at(p, t):
        """Position x, y, depth z (-1..1) and depth in px of pattern p at time t."""
        tau = (t - p["t0"]) * FLIGHT_SPEED
        a = p["phase"] + p["dir"] * p["w"] * tau
        kind, cx, cy, ax, ay = p["kind"], p["cx"], p["cy"], p["ax"], p["ay"]
        if kind == "orbit":
            x, y, z = cx + ax * math.sin(a), cy + ay * math.cos(a), math.cos(a)
        elif kind == "figure8":
            x, y, z = cx + ax * math.sin(a), cy + ay * math.sin(2 * a), math.cos(a)
        elif kind == "lissajous":
            i, j = p["ratio"]
            x, y, z = cx + ax * math.sin(i * a + p["shift"]), cy + ay * math.sin(j * a), math.cos(i * a + p["shift"])
        elif kind == "loop":
            x, y, z = cx + ax * math.sin(a), cy + ay * math.cos(a), 0.8 * math.sin(0.5 * a + p["zshift"])
        else:
            (f1, p1), (f2, p2), (f3, p3), (f4, p4), (f5, p5) = p["waves"]
            s = p["phase"] + p["dir"] * tau
            x = cx + ax * (0.65 * math.sin(f1 * s + p1) + 0.35 * math.sin(f2 * s + p2))
            y = cy + ay * (0.65 * math.sin(f3 * s + p3) + 0.35 * math.sin(f4 * s + p4))
            z = math.sin(f5 * s + p5)
        return x, y, z, p["depth"]

    def position(self, t):
        x, y, z, d = self.at(self.cur, t)
        if self.prev is not None:
            mix = smoother((t - self.blend_at) / FLIGHT_BLEND_S)
            if mix < 1:
                x0, y0, z0, d0 = self.at(self.prev, t)
                x, y, z, d = (x0 + (x - x0) * mix, y0 + (y - y0) * mix, z0 + (z - z0) * mix, d0 + (d - d0) * mix)
        return x, y, z, d

    def switch(self):
        """Next pattern: starts near the current point and moves the same way, then blends in."""
        t = self.t
        x, y, z, _ = self.position(t)
        x2, y2, _, _ = self.position(t + 0.05)
        vx, vy = (x2 - x) / 0.05, (y2 - y) / 0.05
        kind = random.choice([k for k in self.KINDS if k != self.cur["kind"]] or self.KINDS)
        best, best_score = None, None
        for _ in range(24):                                # a few candidates, keep the best fit
            cand = self.make(kind, t, random.uniform(0, 2 * math.pi), random.choice((1, -1)))
            cx, cy, cz, _ = self.at(cand, t)
            nx, ny, _, _ = self.at(cand, t + 0.05)
            cvx, cvy = (nx - cx) / 0.05, (ny - cy) / 0.05
            speed = math.hypot(vx, vy) * math.hypot(cvx, cvy) or 1.0
            score = math.hypot(cx - x, cy - y) + 40 * abs(cz - z) - 30 * (vx * cvx + vy * cvy) / speed
            if best is None or score < best_score:
                best, best_score = cand, score
        self.prev, self.cur, self.blend_at = self.cur, best, t
        self.next_change = random.uniform(*FLIGHT_PATTERN_S)

    def pick_new_target(self):
        """Window or tree size changed: fly a new pattern that fits it."""
        self.switch()

    def step(self, dt):
        self.t += dt
        if self.prev is not None and self.t - self.blend_at >= FLIGHT_BLEND_S + LOOKAHEAD_S + 0.1:
            self.prev = None                               # blend finished (also for the look-ahead)
        self.next_change -= dt
        if self.next_change <= 0 and self.prev is None:
            self.switch()

        # Tilt: the logo leans to where it will be in LOOKAHEAD_S, by the screen velocity there.
        # atan(vx*vy / (vx² + c²)) is the flight slope, mirrored for leftward flight
        # (never upside down) and fading to level when the horizontal motion stops.
        t, e = self.t + LOOKAHEAD_S, 0.02
        x0, y0, z0, d = self.position(t)
        x1, y1, z1, _ = self.position(t + e)
        vx, vy, vz = (x1 - x0) / e, (y1 - y0) / e, (z1 - z0) * d / e
        target = math.atan(vx * vy / (vx * vx + TILT_VX_SOFT ** 2))
        target = TILT_MAX * math.tanh(target / TILT_MAX)  # soft limit instead of a hard clamp
        self.tilt, self.tilt_v = spring(self.tilt, self.tilt_v, target, TILT_FOLLOW, 1.0, dt)
        # Facing: flying across the screen shows the face, flying in depth shows the edge.
        flat = math.hypot(vx, vz)
        face = abs(vx) / flat if flat > 5 else 1.0
        self.face, self.face_v = spring(self.face, self.face_v, face, 4.0, 1.0, dt)

    def logo_position(self):
        """z > 0 - logo in front of the tree, z < 0 - behind it. Farther = smaller."""
        x, y, z, _ = self.position(self.t)
        face = max(0.0, min(1.0, self.face))
        return {
            "x": x,
            "y": y + BOB_PX * math.sin(self.t * 2.7),                     # bobbing while flying
            "z": z,
            "scale": SCALE_BACK + (1 - SCALE_BACK) * (z + 1) / 2,
            "turn": EDGE_ON + (1 - EDGE_ON) * face,
            "angle": self.tilt + 0.05 * math.sin(self.t * 1.9),           # tilt + slight wobble
            "front": smoothstep((z + Z_FADE) / (2 * Z_FADE)),             # 0 = behind, 1 = in front
        }


def draw_logo(cr, logo, p, alpha):
    """
    Logo without background: white face + blue thickness (3D), semi-transparent as a whole.
    Drawn into a separate group first, then painted with LOGO_ALPHA,
    so the thickness layers do not accumulate opacity.
    """
    logo, res = logo["surface"], logo["res"]
    logo_w = logo.get_width() / res
    logo_h = logo.get_height() / res

    cr.save()
    cr.translate(p["x"], p["y"])
    cr.rotate(p["angle"])
    cr.scale(p["scale"] * p["turn"], p["scale"])
    cr.translate(-logo_w / 2, -logo_h / 2)
    cr.push_group()
    cr.scale(1 / res, 1 / res)                         # bitmap is rendered at higher resolution

    for d in range(LOGO_DEPTH, 0, -1):                 # thickness: from dark blue to lighter blue
        k = d / LOGO_DEPTH
        cr.set_source_rgb(*(b75 + (b - b75) * k for b, b75 in zip(WIMO_BLUE, WIMO_BLUE_75)))
        cr.mask_surface(logo, d * res * 0.6, d * res)
    cr.set_source_rgb(1, 1, 1)                         # front
    cr.mask_surface(logo, 0, 0)

    cr.pop_group_to_source()
    cr.paint_with_alpha(alpha)
    cr.restore()


# ---------- snow ----------

def snow_count():
    """SNOWFLAKES is for the default window; a bigger window gets more, so the density stays."""
    return round(SNOWFLAKES * WIDTH * HEIGHT / (BASE_WIDTH * BASE_HEIGHT))


class Snow:
    """Snowflakes. Small (far) ones fall slower and are drawn behind the tree, big ones in front."""

    def __init__(self):
        self.size = (WIDTH, HEIGHT)
        self.flakes = [self.new_flake(random.uniform(0, HEIGHT)) for _ in range(snow_count())]

    @staticmethod
    def new_flake(y):
        near = random.random()                     # 0 = far, 1 = near
        return {
            "x": random.uniform(0, WIDTH),
            "y": y,
            "r": 0.8 + near * 1.8,
            "near": near,
            "speed": SNOW_SPEED[0] + near * (SNOW_SPEED[1] - SNOW_SPEED[0]),
            "sway": random.uniform(0, 2 * math.pi),  # left/right sway phase
            "front": near > 0.6,
        }

    def step(self, dt, wind):
        gust = min(1.0, abs(wind.vx) / WIND_MAX)
        for i, f in enumerate(self.flakes):
            drift = 0.45 + 0.55 * f["near"]        # near flakes are blown harder (parallax)
            f["sway"] += dt * (1.3 + 2.0 * gust)   # flutter faster in a gust
            f["x"] += (wind.vx * drift + math.sin(f["sway"]) * SNOW_SWAY * (1 + gust)) * dt
            f["y"] += (f["speed"] + wind.vy * drift) * dt
            if f["x"] < -4:                        # blown out of the window: comes back on the other side
                f["x"] += WIDTH + 8
            elif f["x"] > WIDTH + 4:
                f["x"] -= WIDTH + 8
            if f["y"] > HEIGHT + 3:
                self.flakes[i] = self.new_flake(-3)

    def draw(self, cr, front):
        for f in self.flakes:
            if f["front"] != front:
                continue
            cr.set_source_rgba(1, 1, 1, 0.55 + 0.35 * (f["r"] / 2.6))
            cr.arc(f["x"], f["y"], f["r"], 0, 2 * math.pi)
            cr.fill()


# ---------- wind ----------

class Wind:
    """
    Light breeze, and from time to time a gust from the left or right, sometimes slanting
    down (never from below). Each gust has its own strength, length and direction, builds up
    and fades smoothly, with turbulence on top. vx, vy - current wind, px/s (vy >= 0).
    """

    def __init__(self):
        self.t = 0.0
        self.vx = self.vy = 0.0
        self.side = random.choice((1, -1))
        self.breeze = self.breeze_v = self.breeze_target = 0.0
        self.breeze_change = 0.0
        self.gust = None
        self.next_gust = random.uniform(*WIND_CALM_S)
        self.phases = [random.uniform(0, 2 * math.pi) for _ in range(3)]

    def plan_gust(self):
        if random.random() > WIND_KEEP_SIDE:
            self.side = -self.side
        strength = WIND_MAX * random.uniform(0.15, 1.0)
        slant = random.uniform(0, WIND_DOWN_MAX) if random.random() < 0.6 else 0.0
        self.gust = {
            "start": self.t,
            "rise": random.uniform(*WIND_RISE_S),
            "hold": random.uniform(*WIND_GUST_S),
            "fall": random.uniform(*WIND_FALL_S),
            "vx": self.side * strength * math.cos(slant),
            "vy": strength * math.sin(slant),
        }

    def envelope(self):
        g = self.gust
        k = self.t - g["start"]
        if k < g["rise"]:
            return smoothstep(k / g["rise"])
        k -= g["rise"] + g["hold"]
        if k < 0:
            return 1.0
        if k < g["fall"]:
            return 1 - smoothstep(k / g["fall"])
        return None                                    # gust is over

    def step(self, dt):
        self.t += dt
        self.breeze_change -= dt
        if self.breeze_change <= 0:
            self.breeze_target = random.uniform(-WIND_BREEZE, WIND_BREEZE)
            self.breeze_change = random.uniform(3, 8)
        self.breeze, self.breeze_v = spring(self.breeze, self.breeze_v, self.breeze_target, 0.8, 1.0, dt)

        env = 0.0
        if self.gust is None and self.t >= self.next_gust:
            self.plan_gust()
        if self.gust is not None:
            env = self.envelope()
            if env is None:
                self.gust, env = None, 0.0
                self.next_gust = self.t + random.uniform(*WIND_CALM_S)

        p, t = self.phases, self.t
        turbulence = 1 + WIND_TURBULENCE * (0.5 * math.sin(t * 1.7 + p[0]) + 0.3 * math.sin(t * 3.1 + p[1])
                                + 0.2 * math.sin(t * 5.3 + p[2]))
        gx, gy = (self.gust["vx"], self.gust["vy"]) if self.gust else (0.0, 0.0)
        self.vx = (self.breeze + gx * env) * turbulence
        self.vy = gy * env * turbulence


# ---------- scene and window ----------

class Scene:
    """Whole animation state: wind, tree, ornaments, garlands, logo orbit, snow. Independent of the window."""

    def __init__(self, wait=False):
        self.logo = load_logo()
        self.wind = Wind()
        self.sway = None
        self.orbit = Flight()
        self.snow = Snow()
        self.garland = GarlandShow()
        self.t = 0.0                                   # time since start, seconds
        self.tree = None                               # shown tree; None until the first one is built
        self.job = None                                # tree being built in the background
        self.frame_lock = threading.Lock()             # held while a frame is stepped and drawn
        self.grow_tree(TREE_SEED, wait)

    def grow_tree(self, seed=None, wait=False):
        """
        Build the tree in a background thread; the current tree keeps moving and a loader shows the
        progress. A newer request cancels the older build. A random tree gets a new seed unless given.
        """
        if seed is None:
            seed = random.randrange(10 ** 9)
        self.seed = seed
        print(f"tree seed: {seed}  (Settings > Tree seed = {seed} keeps this tree)", flush=True)
        job = {"progress": 0.0, "tree": None, "failed": False, "geometry": tree_geometry()}
        self.job = job

        def report(share):
            # The builder waits here while a frame is drawn; otherwise both threads fight for the
            # interpreter lock on every cairo call and a frame takes 100+ ms.
            with self.frame_lock:
                pass
            if self.job is not job:
                raise BuildCancelled
            job["progress"] = max(job["progress"], min(1.0, share))

        def run():
            try:
                job["tree"] = build_tree(TREE_STYLE, seed, report)
            except BuildCancelled:
                pass
            except Exception:                          # keep the old tree, report the error
                traceback.print_exc()
                job["failed"] = True

        if wait:
            run()
            self.take_tree()
        else:
            threading.Thread(target=run, name="tree-build", daemon=True).start()

    def take_tree(self):
        """Show a finished tree (called from the animation loop)."""
        job = self.job
        if job is None or (job["tree"] is None and not job["failed"]):
            return
        self.job = None
        if job["failed"]:
            return
        self.tree, self.tree_geometry = job["tree"], job["geometry"]
        old = self.sway
        self.sway = TreeSway(self.tree["ornaments"], self.tree.get("branches", ()), self.tree["garlands"])
        if old:                                        # a new tree keeps swaying in the current wind
            self.sway.bend, self.sway.bend_v, self.sway.t = old.bend, old.bend_v, old.t
        self.lights = OrnamentLights(len(self.tree["ornaments"]))
        self.garland.total = max(1, sum(g["count"] if isinstance(g, dict) else g[5] for g in self.tree["garlands"]))

    def reconfigure(self):
        """After settings change: same tree (unless a seed is set) rebuilt with the new values."""
        self.logo = load_logo()
        if len(self.snow.flakes) != snow_count() or self.snow.size != (WIDTH, HEIGHT):
            self.snow = Snow()
        self.orbit.pick_new_target()                   # glide to the orbit of the new tree size
        self.grow_tree(TREE_SEED if TREE_SEED is not None else self.seed)

    def step(self, dt):
        with self.frame_lock:
            self.step_frame(dt)

    def step_frame(self, dt):
        self.t += dt
        self.take_tree()
        self.wind.step(dt)
        self.orbit.step(dt)
        if SHOW_SNOW:
            self.snow.step(dt, self.wind)
        if self.tree:
            self.sway.step(dt, self.wind)
            self.garland.step(self.t)
            self.lights.step(self.t)

    def draw(self, cr):
        with self.frame_lock:
            self.draw_frame(cr)

    def draw_frame(self, cr):
        """Far snow -> logo behind -> tree -> logo in front -> near snow -> loader."""
        p = self.orbit.logo_position()
        # Near z = 0 the logo is drawn both behind and in front; alphas add up to LOGO_ALPHA.
        alpha = LOGO_ALPHA if LOGO_ENABLED else 0.0
        a_front = alpha * p["front"]
        a_back = alpha * (1 - p["front"]) / (1 - a_front)
        if SHOW_SNOW:
            self.snow.draw(cr, front=False)
        if a_back > 0.002:
            draw_logo(cr, self.logo, p, a_back)
        if self.tree and self.tree_geometry == tree_geometry():   # an old tree of another size waits hidden
            cr.save()
            cr.translate(TREE_X, TREE_Y)
            draw_tree(cr, self.tree, self.lights.get(self.t), self.t, self.garland, self.sway)
            cr.restore()
        if a_front > 0.002:
            draw_logo(cr, self.logo, p, a_front)
        if SHOW_SNOW:
            self.snow.draw(cr, front=True)
        if self.job:
            draw_loader(cr, self.job["progress"])


class BuildCancelled(Exception):
    """A newer tree was requested while this one was being built."""


def tree_geometry():
    return TREE_STYLE, TREE_W, TREE_H, TREE_X, TREE_Y


def draw_loader(cr, share):
    """Small progress pill in the middle of the tree area: "Growing tree 42%" and a bar."""
    text = f"Growing tree {int(share * 100)}%"
    w, h = 132, 34
    x, y = TREE_X + TREE_W / 2 - w / 2, TREE_Y + TREE_H * 0.55 - h / 2
    r = 9
    cr.save()
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    cr.close_path()
    cr.set_source_rgba(0.05, 0.12, 0.08, 0.78)
    cr.fill()
    cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    cr.set_font_size(11)
    ext = cr.text_extents(text)
    cr.move_to(x + w / 2 - ext.x_advance / 2, y + 15)
    cr.set_source_rgba(1, 1, 1, 0.95)
    cr.show_text(text)
    bx, by, bw, bh = x + 12, y + 22, w - 24, 4                # progress bar
    cr.rectangle(bx, by, bw, bh)
    cr.set_source_rgba(1, 1, 1, 0.2)
    cr.fill()
    cr.rectangle(bx, by, bw * share, bh)
    cr.set_source_rgb(0.95, 0.78, 0.25)
    cr.fill()
    cr.restore()


# ---------- settings ----------

SETTINGS_FILE = os.path.join(HERE, "settings.json")

# Every tunable value: (tab, name, label, kind, min, max, step). Kinds: int, float, range (min..max pair),
# irange (int pair), bool, choice (min = options), seed (empty = random).
SETTINGS = [
    ("General", "TREE_STYLE", "Tree style", "choice", ("random", "classic"), None, None),
    ("General", "TREE_SEED", "Tree seed (empty = new tree every start)", "seed", None, None, None),
    ("General", "TREE_HEIGHT", "Tree height, px (only the tree grows)", "int", 120, 900, 2),
    ("General", "MARGIN", "Distance from screen edges, px", "int", 0, 300, 1),
    ("General", "DRAG_THRESHOLD_PX", "Mouse move that starts a drag, px", "int", 1, 50, 1),
    ("General", "MAX_FPS", "Max frames per second", "int", 10, 240, 1),
    ("General", "MAX_DT", "Longest frame step, s", "float", 0.02, 1.0, 0.01),
    ("General", "SHOW_TOPPER", "Show topper (star)", "bool", None, None, None),
    ("General", "SHOW_SNOW", "Show snow (falling and on branches)", "bool", None, None, None),
    ("General", "SHOW_GIFTS", "Show gifts", "bool", None, None, None),
    ("General", "SHOW_NEEDLES", "Show needles", "bool", None, None, None),
    ("General", "LIGHT_CHANGE_S", "Ornament color change every, s", "range", 0.1, 10, 0.1),
    ("General", "LIGHT_FADE_S", "Ornament color crossfade, s", "float", 0.0, 3.0, 0.05),

    ("Tree", "SPRUCE_HALF_W", "Crown half width, px (258 px tree)", "range", 30, 100, 1),
    ("Tree", "SPRUCE_TOP_Y", "Leader tip from the top, px (258 px tree)", "range", 0, 120, 1),
    ("Tree", "SPRUCE_CROWN_BOTTOM", "Lowest branches at, px (258 px tree)", "range", 80, 235, 1),
    ("Tree", "SPRUCE_TRUNK_ROOM", "Bare trunk above the ground, px (258 px tree)", "float", 0, 120, 1),
    ("Tree", "SPRUCE_ORNAMENT_ZONE", "Ornaments on the upper share of the crown", "float", 0.2, 1.0, 0.02),
    ("Tree", "SPRUCE_FULLNESS", "Crown shape (<1 full, >1 slender)", "range", 0.4, 2.0, 0.05),
    ("Tree", "SPRUCE_WHORL_GAP", "Gap between branch whorls, px", "range", 3, 20, 0.5),
    ("Tree", "SPRUCE_BRANCHES", "Branches per whorl", "irange", 2, 14, 1),
    ("Tree", "SPRUCE_GAPS", "Missing branch chance", "float", 0.0, 0.8, 0.01),
    ("Tree", "NEEDLE_DENSITY", "Needles per px of a twig", "range", 0.1, 3.0, 0.05),
    ("Tree", "NEEDLE_LEN", "Needle length, px", "range", 1.0, 10.0, 0.1),
    ("Tree", "SPRUCE_TRUNK_R", "Trunk half width, px (258 px tree)", "range", 2.0, 12.0, 0.5),
    ("Tree", "SPRUCE_LEAN", "Max trunk lean, px (258 px tree)", "float", 0.0, 15.0, 0.5),
    ("Tree", "SPRUCE_TRUNK_BEND", "Max trunk bend, px (258 px tree)", "float", 0.0, 20.0, 0.5),
    ("Tree", "SPRUCE_STRAIGHT", "Straight trunk chance", "float", 0.0, 1.0, 0.05),
    ("Tree", "SPRUCE_CONES", "Cones (258 px tree)", "irange", 0, 40, 1),
    ("Tree", "SPRUCE_SNOW", "Max share of snowy branches", "float", 0.0, 1.0, 0.05),
    ("Tree", "SPRUCE_FRESH", "Max share of fresh light tips", "float", 0.0, 1.0, 0.05),
    ("Tree", "SPRUCE_ORNAMENTS", "Ornaments (258 px tree)", "irange", 0, 40, 1),

    ("Gifts", "RANDOM_GIFTS", "Random gifts (off = classic gifts)", "bool", None, None, None),
    ("Gifts", "GIFT_COUNT", "Number of gifts", "irange", 0, 12, 1),
    ("Tree", "RANDOM_TOPPER", "Random topper (off = classic star)", "bool", None, None, None),

    ("Logo", "LOGO_ENABLED", "Show logo", "bool", None, None, None),
    ("Logo", "LOGO_W", "Logo width in front, px", "int", 10, 200, 1),
    ("Logo", "LOGO_ALPHA", "Logo opacity", "float", 0.0, 1.0, 0.05),
    ("Logo", "LOGO_DEPTH", "Logo thickness, px", "int", 0, 12, 1),
    ("Logo", "SCALE_BACK", "Size behind the tree vs in front", "float", 0.2, 1.0, 0.05),
    ("Logo", "TILT_MAX", "Max tilt, rad", "float", 0.0, 1.5, 0.05),
    ("Logo", "TILT_FOLLOW", "Tilt stiffness, 1/s", "float", 0.5, 20.0, 0.1),
    ("Logo", "TILT_VX_SOFT", "Tilt fades below speed, px/s", "float", 1, 200, 1),
    ("Logo", "LOOKAHEAD_S", "Tilt look-ahead, s", "float", 0.0, 2.0, 0.05),
    ("Logo", "EDGE_ON", "Width when seen edge-on", "float", 0.05, 1.0, 0.05),
    ("Logo", "BOB_PX", "Bobbing, px", "float", 0.0, 15.0, 0.5),
    ("Logo", "Z_FADE", "Front/behind crossfade width", "float", 0.01, 0.5, 0.01),

    ("Orbit", "FLIGHT_PATTERN_S", "One flight pattern lasts, s", "range", 2, 120, 1),
    ("Orbit", "FLIGHT_BLEND_S", "Blend into the next pattern, s", "float", 0.5, 15, 0.5),
    ("Orbit", "FLIGHT_SPEED", "Flight speed (1 = normal)", "float", 0.1, 4, 0.05),
    ("Orbit", "ORBIT_RX_RANGE", "Orbit radius, px (258 px tree)", "range", 20, 160, 1),
    ("Orbit", "ORBIT_RY_RANGE", "Orbit tilt (ellipse height), px (258 px tree)", "range", -80, 80, 1),
    ("Orbit", "ORBIT_Y_RANGE", "Orbit height, px (258 px tree)", "range", 0, 280, 1),
    ("Orbit", "SPEED_RANGE", "Orbit speed, rad/s", "range", 0.05, 5.0, 0.05),

    ("Snow", "SNOWFLAKES", "Snowflakes (default window size)", "int", 0, 600, 5),
    ("Snow", "SNOW_SPEED", "Fall speed, px/s", "range", 1, 200, 1),
    ("Snow", "SNOW_SWAY", "Flutter, px/s", "float", 0, 60, 1),

    ("Wind", "WIND_MAX", "Strongest gust, px/s", "float", 0, 500, 5),
    ("Wind", "WIND_BREEZE", "Breeze between gusts, px/s", "float", 0, 100, 1),
    ("Wind", "WIND_CALM_S", "Pause between gusts, s", "range", 0.5, 120, 0.5),
    ("Wind", "WIND_GUST_S", "Gust at full strength, s", "range", 0.5, 60, 0.5),
    ("Wind", "WIND_RISE_S", "Gust build-up, s", "range", 0.1, 20, 0.1),
    ("Wind", "WIND_FALL_S", "Gust fading, s", "range", 0.1, 20, 0.1),
    ("Wind", "WIND_DOWN_MAX", "Max downward slant, rad", "float", 0.0, 1.4, 0.05),
    ("Wind", "WIND_KEEP_SIDE", "Same side as the last gust, chance", "float", 0.0, 1.0, 0.05),
    ("Wind", "WIND_TURBULENCE", "Turbulence", "float", 0.0, 1.0, 0.05),

    ("Sway", "TREE_BEND_PX", "Top shift at the strongest wind, px (258 px tree)", "float", 0, 40, 0.5),
    ("Sway", "TREE_IDLE_PX", "Sway without wind, px (258 px tree)", "float", 0, 10, 0.1),
    ("Sway", "TREE_FREQ", "Natural sway frequency, rad/s", "float", 0.2, 10, 0.1),
    ("Sway", "TREE_DAMP", "Damping (<1 sways back)", "float", 0.02, 2.0, 0.02),
    ("Sway", "ORNAMENT_SWING", "Ornament swing in wind, rad", "float", 0, 1.5, 0.05),
    ("Sway", "ORNAMENT_IDLE", "Ornament idle swing, rad", "float", 0, 0.5, 0.01),
    ("Sway", "BRANCH_BEND", "Single branches bend (0 = rigid)", "float", 0, 4, 0.05),
    ("Sway", "BRANCH_FLUTTER", "Branch flutter", "float", 0, 1, 0.05),
    ("Sway", "BRANCH_SHELTER", "Branches shelter each other", "float", 0, 1, 0.05),
    ("Sway", "BRANCH_DAMP", "Branch damping", "float", 0.02, 1.5, 0.01),

    ("Garland", "GARLAND_PROGRAM_S", "Program length, s", "float", 1, 120, 1),
    ("Garland", "GARLAND_FADE_S", "Program crossfade, s", "float", 0.0, 10, 0.1),
    ("Garland", "GARLAND_CLICK_FADE_S", "Crossfade after a click, s", "float", 0.0, 5, 0.1),
    ("Garland", "GARLAND_CLICK_FLASH_S", "Flash after a click, s", "float", 0.0, 5, 0.1),
    ("Garland", "GARLAND_MIN_LIGHT", "Min bulb brightness", "float", 0.0, 1.0, 0.01),
    ("Garland", "GARLAND_SAG", "Garland sag between branches", "float", 0.0, 4.0, 0.05),
]
DEFAULTS = {name: globals()[name] for _, name, *_ in SETTINGS}


def clean_value(kind, value, lo, hi):
    """Bring a value from the file or the dialog to its kind and limits."""
    if kind == "seed":
        return None if value in (None, "") else int(value)
    if kind == "bool":
        return bool(value)
    if kind == "choice":
        if value not in lo:
            raise ValueError(value)
        return value
    if kind in ("range", "irange"):
        cast = int if kind == "irange" else float
        a, b = sorted(max(lo, min(hi, cast(v))) for v in value)
        return a, b
    cast = int if kind == "int" else float
    return max(lo, min(hi, cast(value)))


def load_settings():
    try:
        with open(SETTINGS_FILE) as f:
            saved = json.load(f)
    except FileNotFoundError:
        return
    except (OSError, ValueError) as e:
        print(f"settings ignored: {e}", flush=True)
        return
    for _, name, _, kind, lo, hi, _ in SETTINGS:
        if name in saved:
            try:
                globals()[name] = clean_value(kind, saved[name], lo, hi)
            except (TypeError, ValueError):
                print(f"setting {name} ignored: {saved[name]!r}", flush=True)


def save_settings():
    """Only values that differ from the defaults are saved, so later default changes still apply."""
    same = lambda a, b: (list(map(float, a)) == list(map(float, b))) if isinstance(a, tuple) else a == b
    changed = {name: globals()[name] for _, name, *_ in SETTINGS if not same(globals()[name], DEFAULTS[name])}
    with open(SETTINGS_FILE, "w") as f:
        json.dump(changed, f, indent=2)


class SettingsWindow(QWidget):
    """All settings in tabs. Apply = use now and save to settings.json."""

    def __init__(self, on_apply):
        super().__init__(None, Qt.Window | Qt.WindowStaysOnTopHint)
        self.setWindowTitle(f"Christmas tree settings ({__version__})")
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(600, 600)
        self.on_apply = on_apply
        self.editors = {}

        tabs, grids = QTabWidget(), {}
        for tab, name, label, kind, lo, hi, step in SETTINGS:
            if tab not in grids:
                page = QWidget()
                grid = QGridLayout(page)
                grid.setColumnStretch(0, 1)
                scroll = QScrollArea()
                scroll.setWidgetResizable(True)
                scroll.setWidget(page)
                tabs.addTab(scroll, tab)
                grids[tab] = [grid, 0]
            grid, row = grids[tab]
            text = QLabel(label)
            text.setToolTip(name)
            widget, get, put = self.editor(kind, lo, hi, step)
            grid.addWidget(text, row, 0)
            grid.addWidget(widget, row, 1)
            grids[tab][1] += 1
            self.editors[name] = (kind, lo, hi, get, put)
            put(globals()[name])
        for grid, row in grids.values():
            grid.setRowStretch(row, 1)                     # rows at the top, not spread out

        buttons = QHBoxLayout()
        for label, handler in (("Reset to defaults", self.on_reset), (None, None), ("Cancel", self.close),
                               ("Apply", self.on_apply_clicked), ("OK", self.on_ok)):
            if label is None:
                buttons.addStretch(1)
                continue
            button = QPushButton(label)
            button.clicked.connect(handler)
            buttons.addWidget(button)
        self.status = QLabel()
        author = QLabel(f"{APP_NAME} {__version__} · {__author__}")
        author.setStyleSheet("color: gray")
        box = QVBoxLayout(self)
        box.addWidget(tabs, 1)
        box.addWidget(self.status)
        box.addLayout(buttons)
        box.addWidget(author)

    @staticmethod
    def spin(kind, lo, hi, step):
        if kind in ("int", "irange"):
            w = QSpinBox()
            w.setRange(int(lo), int(hi))
            w.setSingleStep(max(1, int(step)))
        else:
            w = QDoubleSpinBox()
            w.setDecimals(0 if step >= 1 else max(1, -math.floor(math.log10(step))))
            w.setRange(lo, hi)
            w.setSingleStep(step)
        return w

    def editor(self, kind, lo, hi, step):
        """Widget for one setting + getter + setter."""
        if kind == "bool":
            w = QCheckBox()
            return w, w.isChecked, lambda v: w.setChecked(bool(v))
        if kind == "choice":
            w = QComboBox()
            w.addItems(list(lo))
            return w, w.currentText, lambda v: w.setCurrentIndex(lo.index(v))
        if kind == "seed":
            w = QLineEdit()
            w.setPlaceholderText("random")
            return w, lambda: w.text().strip(), lambda v: w.setText("" if v is None else str(v))
        if kind in ("range", "irange"):
            a, b = self.spin(kind, lo, hi, step), self.spin(kind, lo, hi, step)
            box = QWidget()
            row = QHBoxLayout(box)
            row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(a)
            row.addWidget(QLabel("to"))
            row.addWidget(b)
            return box, lambda: (a.value(), b.value()), lambda v: (a.setValue(v[0]), b.setValue(v[1]))
        w = self.spin(kind, lo, hi, step)
        return w, w.value, w.setValue

    def on_reset(self):
        for name, (kind, lo, hi, get, put) in self.editors.items():
            put(DEFAULTS[name])
        self.status.setText("Defaults loaded, press Apply to use them.")

    def collect(self):
        values = {}
        for name, (kind, lo, hi, get, put) in self.editors.items():
            try:
                values[name] = clean_value(kind, get(), lo, hi)
            except (TypeError, ValueError):
                self.status.setText(f"Invalid value: {name}")
                return None
        return values

    def on_apply_clicked(self):
        values = self.collect()
        if values is None:
            return False
        self.on_apply(values)
        for name, (kind, lo, hi, get, put) in self.editors.items():
            put(globals()[name])                           # show cleaned values (sorted ranges etc.)
        self.status.setText(f"Applied and saved to {SETTINGS_FILE}")
        return True

    def on_ok(self):
        if self.on_apply_clicked():
            self.close()


# ---------- window ----------

def window_size():
    return WIDTH, HEIGHT


class TreeWindow(QWidget):
    """Frameless, transparent, always on top, not in the taskbar. The scene is drawn with cairo."""

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setWindowTitle(APP_NAME)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.scene = Scene()
        self.press = None                  # left button press (global pos) while not yet dragging
        self.settings = None
        self.frame = None                  # cairo surface the scene is drawn into
        self.frame_data = None

        w, h = window_size()
        self.setFixedSize(w, h)
        area = (self.screen() or QGuiApplication.primaryScreen()).availableGeometry()   # without panels
        self.move(area.right() - w - MARGIN, area.bottom() - h - MARGIN)

        # Frames use the real elapsed time, so uneven timer ticks do not stutter.
        self.last_frame = time.perf_counter()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.timer.start(max(1, int(1000 / MAX_FPS)))

    def paintEvent(self, _event):
        ratio = self.devicePixelRatioF()                   # sharp on scaled (HiDPI) screens
        w, h = round(self.width() * ratio), round(self.height() * ratio)
        if self.frame is None or (self.frame.get_width(), self.frame.get_height()) != (w, h):
            self.frame = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        cr = cairo.Context(self.frame)
        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        cr.scale(ratio, ratio)
        self.scene.draw(cr)
        self.frame.flush()
        image = QImage(self.frame.get_data(), w, h, self.frame.get_stride(), QImage.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(ratio)
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.drawImage(0, 0, image)
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.press = event.globalPosition().toPoint()
        elif event.button() == Qt.MiddleButton:
            self.scene.grow_tree()
        elif event.button() == Qt.RightButton:
            self.show_menu(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event):
        # Left button held and mouse moved far enough: the window manager moves the window.
        if self.press is not None:
            if (event.globalPosition().toPoint() - self.press).manhattanLength() > DRAG_THRESHOLD_PX:
                self.press = None
                handle = self.windowHandle()
                if not (handle and handle.startSystemMove()):
                    self.drag_from = event.globalPosition().toPoint() - self.pos()   # fallback: move by hand
        elif getattr(self, "drag_from", None) is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_from)

    def mouseReleaseEvent(self, event):
        # Released without dragging: a click switches the garland program.
        if event.button() == Qt.LeftButton:
            if self.press is not None:
                self.scene.garland.click(self.scene.t)
            self.press = None
            self.drag_from = None

    def show_menu(self, pos):
        menu = QMenu(self)
        menu.addAction("New random tree", self.scene.grow_tree)
        menu.addSeparator()
        logo = QAction("Show logo", menu, checkable=True, checked=LOGO_ENABLED)
        logo.toggled.connect(self.toggle_logo)
        menu.addAction(logo)
        menu.addAction("Settings…", self.open_settings)
        menu.addSeparator()
        menu.addAction("Close", QApplication.quit)
        menu.exec(pos)

    def toggle_logo(self, enabled):
        global LOGO_ENABLED
        LOGO_ENABLED = enabled
        try:
            save_settings()
        except OSError as e:
            print(f"settings not saved: {e}", flush=True)
        if self.settings:                                  # keep an open settings window in sync
            self.settings.editors["LOGO_ENABLED"][4](enabled)

    def open_settings(self):
        if self.settings:
            self.settings.raise_()
            self.settings.activateWindow()
            return
        self.settings = SettingsWindow(self.apply_settings)
        self.settings.destroyed.connect(lambda *_: setattr(self, "settings", None))
        self.settings.show()

    def apply_settings(self, values):
        old_w, old_h = window_size()
        globals().update(values)
        apply_geometry()
        try:
            save_settings()
        except OSError as e:
            print(f"settings not saved: {e}", flush=True)
        self.scene.reconfigure()
        self.timer.setInterval(max(1, int(1000 / MAX_FPS)))
        w, h = window_size()
        if (w, h) != (old_w, old_h):                       # keep the bottom-right corner in place
            pos = self.pos()
            self.setFixedSize(w, h)
            self.move(pos + QPoint(old_w - w, old_h - h))

    def tick(self):
        now = time.perf_counter()
        self.scene.step(min(now - self.last_frame, MAX_DT))
        self.last_frame = now
        self.update()


# ---------- single instance ----------

INSTANCE_NAME = "wimo-christmas-tree"


def close_running_instance():
    """A running tree is asked to quit, so a new start always uses the latest files."""
    socket = QLocalSocket()
    socket.connectToServer(INSTANCE_NAME)
    if socket.waitForConnected(300):
        socket.write(QByteArray(b"quit"))
        socket.waitForBytesWritten(300)
        socket.disconnectFromServer()
        time.sleep(0.5)
        return True
    return False


def listen_for_quit(app):
    QLocalServer.removeServer(INSTANCE_NAME)               # stale name after a crash
    server = QLocalServer(app)
    server.newConnection.connect(lambda: app.quit())
    server.listen(INSTANCE_NAME)
    return server


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)                   # closing settings must not end the tree
    closed = close_running_instance()
    if "--stop" in sys.argv:
        print("stopped" if closed else "not running", flush=True)
        return 0
    server = listen_for_quit(app)
    load_settings()
    apply_geometry()
    window = TreeWindow()
    window.show()
    code = app.exec()
    server.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
