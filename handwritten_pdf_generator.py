"""
handwritten_pdf_generator.py
─────────────────────────────────────────────────────────────────────────────
Converts assignment_structured.json → a multi-page handwritten-looking PDF.

Features
  • A4 paper with very light paper texture
  • Two SVG font folders: alpha3 (cursive, normal text) and code_alpha (code)
  • Missing-SVG placeholder rendered inline ("⬜ svg_name missing")
  • Multi-page support with automatic page breaks
  • Subtle paper tilt for realism
  • Soft drop-shadow + scan-line vignette overlay
  • Variable pen-pressure simulation (opacity + slight blur per stroke)
  • Full table rendering with hand-drawn ruled grid
  • All algorithm symbols mapped (Θ, Ω, Σ, ≤, ≥, →, ∈, ⊆, ¬, ∧, ∨ …)

Usage
  python handwritten_pdf_generator.py [--json PATH] [--out PATH]
      [--svg-text DIR] [--svg-code DIR]

Defaults:
  --json   assignment_structured.json
  --out    handwritten_assignment.pdf
  --svg-text  /home/sumit/Downloads/alpha3/
  --svg-code  /home/sumit/Downloads/code_alpha/
─────────────────────────────────────────────────────────────────────────────
"""

import os, sys, json, math, random, argparse
from io import BytesIO

import numpy as np
from PIL import Image, ImageFilter, ImageDraw, ImageFont, ImageEnhance

try:
    import cairosvg
    CAIROSVG_OK = True
except ImportError:
    CAIROSVG_OK = False
    print("[WARN] cairosvg not found — SVG characters will show as placeholders. "
          "Install with: pip install cairosvg")

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG — edit paths here or pass CLI flags
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_SVG_FOLDER      = r"/home/sumit/Downloads/alpha3/"
DEFAULT_SVG_CODE_FOLDER = r"/home/sumit/Downloads/code_alpha/"
DEFAULT_INPUT_JSON      = "assignment_structured.json"
DEFAULT_OUTPUT_PDF      = "handwritten_assignment.pdf"

# ── Paper (A4 at 150 dpi → 1240×1754 px) ───────────────────────────────────
PAGE_W, PAGE_H = 1240, 1754
MARGIN_LEFT    = 90
MARGIN_TOP     = 80
MARGIN_RIGHT   = 90
MARGIN_BOTTOM  = 100

# ── Cursive (normal text) font metrics ──────────────────────────────────────
FONT_SIZE        = 32
ASCENDER_H       = 32
X_HEIGHT         = 20
DESCENDER_D      = 13
CHAR_SPACING     = -2
WORD_SPACING     = 10
LINE_HEIGHT      = 52
BASELINE_JITTER  = 2
LINE_ANGLE_MIN   = -0.8
LINE_ANGLE_MAX   = 1.2
LINE_DRIFT_MAX   = 3.5

# ── Code / pseudocode font metrics ──────────────────────────────────────────
CODE_FONT_SIZE    = 22
CODE_ASCENDER_H   = int(ASCENDER_H * 0.92)
CODE_X_HEIGHT     = int(X_HEIGHT * 0.92)
CODE_DESCENDER_D  = int(DESCENDER_D * 0.92)
CODE_CHAR_SPACING = 1
CODE_WORD_SPACING = 10
CODE_LINE_HEIGHT  = 34
CODE_INDENT_BASE  = 50    # left offset for code blocks
CODE_INDENT_STEP  = 14    # pixels per indentation level

# ── Heading scale ────────────────────────────────────────────────────────────
HEADING_SCALE = {1: 1.18, 2: 1.14, 3: 1.10, 4: 1.06, 5: 1.03, 6: 1.0}
HEADING_UNDERLINE = {1, 2, 3}   # draw an underline below these heading levels

# ── Typography classification ────────────────────────────────────────────────
ASCENDERS  = set("bdhkltABCDEFGHIJKLMNOPQRSTUVWXYZ(){}[]\"'1234567890·")
DESCENDERS = set("gjpqy")

# ── Symbol map — algorithm-heavy, covers all chars in the JSON ───────────────
SYMBOL_MAP = {
    # punctuation
    '.': 'dot.svg',      ',': 'comma.svg',    '!': 'exclamation.svg',
    '?': 'question.svg', ':': 'colon.svg',    ';': 'semicolon.svg',
    "'": 'apostrophe.svg','"': 'quote.svg',   '-': 'dash.svg',
    '_': 'underscore.svg','+': 'plus.svg',    '=': 'equals.svg',
    '(': 'lparen.svg',   ')': 'rparen.svg',   '[': 'lbracket.svg',
    ']': 'rbracket.svg', '{': 'lbrace.svg',   '}': 'rbrace.svg',
    '/': 'slash.svg',   '\\': 'backslash.svg','*': 'asterisk.svg',
    '&': 'ampersand.svg','%': 'percent.svg',  '$': 'dollar.svg',
    '#': 'hash.svg',    '@': 'at.svg',        '<': 'lt.svg',
    '>': 'gt.svg',      '|': 'pipe.svg',      '^': 'cap.svg',
    '~': 'tilde.svg',   '`': 'backtick.svg',
    # maths / algorithms
    '—': 'dash.svg',    '·': 'dot.svg',
    '∨': 'CV.svg',      '≥': 'gteq.svg',     '≤': 'lteq.svg',
    '∈': 'blongsto.svg','⊆': 'belongeq.svg', 'Σ': 'summation.svg',
    '¬': 'neg.svg',     '∧': 'cap.svg',      '≠': 'noteq.svg',
    '⊇': 'rbeq.svg',   '∩': 'intsec.svg',   '→': 'rarrow.svg',
    '×': 'CX.svg',      '∞': 'infi.svg',     '✓': 'corr.svg',
    '≈': 'apeq.svg',    '∪': 'union.svg',    '∝': 'prop.svg',
    'ε': 'epsi.svg',    '⌋': 'rrange.svg',   '⌊': 'lbrange.svg',
    '←': 'larrow.svg',  'Θ': 'theta.svg',    'Ω': 'bigo.svg',
    'π': 'pi.svg',      '√': 'sqrt.svg',     '∀': 'forall.svg',
    '∃': 'exists.svg',  '⊕': 'oplus.svg',    '⊂': 'subset.svg',
    # subscript / superscript Unicode digits — map to normal digit SVGs
    '₀': '0.svg', '₁': '1.svg', '₂': '2.svg', '₃': '3.svg',
    '₄': '4.svg', '₅': '5.svg', '₆': '6.svg', '₇': '7.svg',
    '₈': '8.svg', '₉': '9.svg',
    '⁰': '0.svg', '¹': '1.svg', '²': '2.svg', '³': '3.svg',
    '⁴': '4.svg', '⁵': '5.svg', '⁶': '6.svg', '⁷': '7.svg',
    '⁸': '8.svg', '⁹': '9.svg',
}

# ── Pen-pressure settings ────────────────────────────────────────────────────
# Each character gets a random opacity in [PEN_OPACITY_MIN, 1.0]
# and very rarely a micro-blur (simulates ink variation / pressure lift)
PEN_OPACITY_MIN   = 0.72
PEN_OPACITY_MAX   = 1.00
PEN_BLUR_CHANCE   = 0.04   # 4% of chars get a tiny blur
PEN_BLUR_RADIUS   = 0.6

# ── Paper colour ─────────────────────────────────────────────────────────────
PAPER_COLOR = (253, 251, 244)   # warm off-white

# ── Ink colour ───────────────────────────────────────────────────────────────
INK_COLOR   = (18, 22, 68)      # dark navy-blue (ballpoint feel)

# ═══════════════════════════════════════════════════════════════════════════════
# SVG CACHE
# ═══════════════════════════════════════════════════════════════════════════════

_svg_cache: dict = {}

def _get_svg_filename(char: str) -> str:
    """Return the expected SVG filename for a character."""
    if char.islower():
        return f"s{char}.svg"
    if char.isupper():
        return f"C{char}.svg"
    if char.isdigit():
        return f"{char}.svg"
    if char in SYMBOL_MAP:
        return SYMBOL_MAP[char]
    return None   # unknown


def _load_svg(char: str, folder: str, target_height: int) -> Image.Image | None:
    """
    Load one SVG character at *target_height* px tall.
    Returns RGBA PIL image, or None if the file does not exist.
    On None the caller should render a "missing" placeholder.
    """
    filename = _get_svg_filename(char)
    if filename is None:
        return None

    path = os.path.join(folder, filename)
    cache_key = (path, target_height)
    if cache_key in _svg_cache:
        return _svg_cache[cache_key]

    if not os.path.exists(path):
        _svg_cache[cache_key] = ("MISSING", filename)
        return ("MISSING", filename)

    if not CAIROSVG_OK:
        _svg_cache[cache_key] = ("MISSING", filename)
        return ("MISSING", filename)

    try:
        png_data = cairosvg.svg2png(url=path, output_height=target_height)
        img = Image.open(BytesIO(png_data)).convert("RGBA")
    except Exception as e:
        print(f"[ERR] Could not render {path}: {e}")
        _svg_cache[cache_key] = ("MISSING", filename)
        return ("MISSING", filename)

    _svg_cache[cache_key] = img
    return img


# ═══════════════════════════════════════════════════════════════════════════════
# CHARACTER PROCESSING
# ═══════════════════════════════════════════════════════════════════════════════

def _trim(img: Image.Image) -> Image.Image:
    bb = img.getbbox()
    return img.crop(bb) if bb else img


def _normalise(img: Image.Image, target_h: int) -> Image.Image:
    w, h = img.size
    if h == 0:
        return img
    nw = max(1, int(w * target_h / h))
    return img.resize((nw, target_h), Image.LANCZOS)


def _char_geometry(char: str, img: Image.Image,
                   asc_h: int, x_h: int, desc_d: int):
    """
    Trim, scale, and return (processed_img, y_offset_from_baseline).
    y_offset is negative = image is *above* the baseline reference point.
    """
    img = _trim(img)
    if char in ASCENDERS:
        img = _normalise(img, asc_h)
        return img, -asc_h
    if char in DESCENDERS:
        img = _normalise(img, asc_h)
        return img, -(asc_h - desc_d)
    if char == 'f':
        img = _normalise(img, asc_h + desc_d)
        return img, -asc_h
    img = _normalise(img, x_h)
    return img, -x_h


def _tint_to_ink(img: Image.Image, ink=INK_COLOR, opacity=1.0) -> Image.Image:
    """
    Replace the dark pixels of an RGBA SVG with INK_COLOR and scale overall
    alpha by *opacity* (pen-pressure effect).
    """
    r, g, b, a = img.split()
    # Invert luminance: dark stroke → INK_COLOR
    inv = Image.new("L", img.size, 0)
    ink_r = Image.new("L", img.size, ink[0])
    ink_g = Image.new("L", img.size, ink[1])
    ink_b = Image.new("L", img.size, ink[2])
    out = Image.merge("RGBA", (ink_r, ink_g, ink_b, a))
    # Apply opacity
    if opacity < 1.0:
        a2 = a.point(lambda v: int(v * opacity))
        out = Image.merge("RGBA", (ink_r, ink_g, ink_b, a2))
    return out


def _missing_glyph_img(filename: str, height: int) -> Image.Image:
    """
    Create a small placeholder image showing the missing SVG name.
    """
    w = max(30, len(filename) * 7)
    img = Image.new("RGBA", (w, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Red box
    draw.rectangle([0, 0, w-1, height-1], outline=(200, 50, 50, 200), width=1)
    # Tiny label
    try:
        draw.text((2, height//2 - 5), filename[:12], fill=(200, 50, 50, 220))
    except Exception:
        pass
    return img


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

class PageManager:
    def __init__(self):
        self.pages: list[Image.Image] = []
        self.canvas = self._new_canvas()
        self.x = MARGIN_LEFT
        self.y = MARGIN_TOP

    def _new_canvas(self) -> Image.Image:
        img = Image.new("RGB", (PAGE_W, PAGE_H), PAPER_COLOR)
        img = _add_paper_texture(img)
        return img

    def newpage(self):
        self.pages.append(self.canvas)
        self.canvas = self._new_canvas()
        self.x = MARGIN_LEFT
        self.y = MARGIN_TOP

    def ensure_space(self, needed_px: int):
        """Start a new page if not enough vertical space remains."""
        if self.y + needed_px > PAGE_H - MARGIN_BOTTOM:
            self.newpage()

    def finish(self):
        """Flush the last page."""
        self.pages.append(self.canvas)


# ═══════════════════════════════════════════════════════════════════════════════
# PAPER EFFECTS
# ═══════════════════════════════════════════════════════════════════════════════

def _add_paper_texture(img: Image.Image) -> Image.Image:
    """Very subtle grain — keeps the paper feeling real, not distracting."""
    arr = np.array(img).astype(np.float32)
    h, w = arr.shape[:2]
    # Gaussian grain
    grain = np.random.normal(0, 2.5, (h, w, 1)).repeat(3, axis=2)
    arr += grain
    # Slight warm tint drift across the page (coffee-stained paper feel)
    row_fade = np.linspace(0, 0.3, h).reshape(h, 1, 1)
    arr[:, :, 2] -= row_fade * 2   # reduce blue slightly toward bottom
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def _add_scan_effect(img: Image.Image) -> Image.Image:
    """
    Add:
      1. Very faint horizontal scan-line pattern (scanner CCD rows)
      2. Slight vignette (edges darker — as if lit from center)
    """
    arr = np.array(img).astype(np.float32)
    h, w = arr.shape[:2]

    # Scan lines — every other row very slightly dimmed
    for row in range(0, h, 3):
        arr[row] *= random.uniform(0.989, 0.998)

    # Vignette
    cx, cy = w / 2, h / 2
    Y, X = np.mgrid[0:h, 0:w]
    dist = np.sqrt(((X - cx) / cx) ** 2 + ((Y - cy) / cy) ** 2)
    vignette = 1.0 - 0.12 * dist ** 2
    vignette = np.clip(vignette, 0.82, 1.0).reshape(h, w, 1)
    arr *= vignette

    arr = np.clip(arr, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def _add_shadow_and_tilt(img: Image.Image) -> Image.Image:
    """
    Apply a small random tilt + soft drop-shadow so the page looks
    like a photograph of a hand-placed piece of paper.
    """
    # 1. Tilt
    angle = random.uniform(-0.6, 0.9)
    tilted = img.rotate(angle, expand=True, resample=Image.BICUBIC,
                        fillcolor=(30, 8, 5))

    # 2. Shadow
    ox = random.randint(4, 10)
    oy = random.randint(6, 14)
    blur_r = 14
    shadow_alpha = 140
    tw, th = tilted.size
    bg = Image.new("RGB", (tw + ox + blur_r, th + oy + blur_r), (28, 8, 5))

    # soft shadow layer
    shadow_mask = Image.new("L", (tw, th), shadow_alpha)
    shadow_mask = shadow_mask.filter(ImageFilter.GaussianBlur(blur_r))
    shadow_rgb  = Image.new("RGB", (tw, th), (0, 0, 0))
    bg.paste(shadow_rgb, (ox, oy), shadow_mask)

    # paste actual page on top
    bg.paste(tilted, (0, 0))
    return bg


def _perspective_warp(img: Image.Image) -> Image.Image:
    """
    Very subtle perspective warp — makes it look like the photo was taken
    slightly off-centre rather than perfectly overhead.
    """
    w, h = img.size
    sk = 0.008
    dx, dy = int(w * sk), int(h * sk)
    src = [(0, 0), (w, 0), (w, h), (0, h)]
    dst = [
        (random.randint(0, dx),     random.randint(0, dy)),
        (w - random.randint(0, dx), random.randint(0, dy)),
        (w - random.randint(0, dx), h - random.randint(0, dy)),
        (random.randint(0, dx),     h - random.randint(0, dy)),
    ]
    M = []
    for (px, py), (qx, qy) in zip(dst, src):
        M += [[px, py, 1, 0, 0, 0, -qx*px, -qx*py],
              [0, 0, 0, px, py, 1, -qy*px, -qy*py]]
    A = np.array(M, dtype=float)
    b = np.array([c for pt in src for c in pt], dtype=float)
    coeffs = np.linalg.solve(A, b)
    return img.transform((w, h), Image.PERSPECTIVE, coeffs, Image.BICUBIC)


# ═══════════════════════════════════════════════════════════════════════════════
# CORE RENDERING — render a string onto the canvas
# ═══════════════════════════════════════════════════════════════════════════════

def _render_string(
    text: str,
    pm: PageManager,
    folder: str,
    font_size: int,
    char_spacing: int,
    word_spacing: int,
    asc_h: int, x_h: int, desc_d: int,
    line_height: int,
    left_margin: int,
    right_margin: int = MARGIN_RIGHT,
    wrap: bool = True,
) -> None:
    """
    Render *text* onto pm.canvas starting at (pm.x, pm.y).
    Handles word-wrap (wrap=True) and page breaks.
    Updates pm.x and pm.y in place.
    """
    max_x = PAGE_W - right_margin

    slope = math.tan(math.radians(
        random.uniform(LINE_ANGLE_MIN, LINE_ANGLE_MAX)))
    line_drift = 0.0
    line_start_x = pm.x
    loff = random.randint(-6, 6)   # per-line vertical offset

    for char in text:
        line_drift += random.uniform(-0.3, 0.3)
        line_drift = max(-LINE_DRIFT_MAX, min(LINE_DRIFT_MAX, line_drift))

        if char == ' ':
            pm.x += word_spacing
            continue

        if char == '\n':
            pm.y += line_height + loff
            pm.x  = left_margin
            loff  = random.randint(-6, 6)
            line_drift = 0.0
            slope = math.tan(math.radians(
                random.uniform(LINE_ANGLE_MIN, LINE_ANGLE_MAX)))
            line_start_x = pm.x
            pm.ensure_space(line_height * 2)
            continue

        # load glyph
        raw = _load_svg(char, folder, font_size)

        if raw is None:
            # truly unknown char — skip silently
            pm.x += x_h // 2
            continue

        if isinstance(raw, tuple) and raw[0] == "MISSING":
            # show placeholder
            filename = raw[1]
            glyph = _missing_glyph_img(filename, asc_h)
            cx = pm.x
            cy = pm.y - asc_h + int(line_drift)
            pm.canvas.paste(glyph, (cx, cy), glyph)
            pm.x += glyph.width + char_spacing
            continue

        # process glyph
        glyph, y_off = _char_geometry(char, raw, asc_h, x_h, desc_d)

        # pen-pressure: random opacity
        opacity = random.uniform(PEN_OPACITY_MIN, PEN_OPACITY_MAX)
        glyph   = _tint_to_ink(glyph, INK_COLOR, opacity)

        # occasional micro-blur
        if random.random() < PEN_BLUR_CHANCE:
            glyph = glyph.filter(ImageFilter.GaussianBlur(PEN_BLUR_RADIUS))

        # word-wrap
        if wrap and pm.x + glyph.width > max_x:
            pm.y += line_height + loff
            pm.x  = left_margin
            loff  = random.randint(-6, 6)
            line_drift = 0.0
            slope = math.tan(math.radians(
                random.uniform(LINE_ANGLE_MIN, LINE_ANGLE_MAX)))
            line_start_x = pm.x
            pm.ensure_space(line_height * 2)

        # baseline wobble
        bjitter = random.randint(-BASELINE_JITTER, BASELINE_JITTER)
        slope_dy = int((pm.x - line_start_x) * slope)
        cy = pm.y + y_off + bjitter + slope_dy + int(line_drift)
        cx = pm.x

        # paste with alpha
        pm.canvas.paste(glyph, (cx, cy), glyph)

        pm.x += glyph.width + char_spacing

    # after rendering, leave x at where we left off (caller decides newline)


# ═══════════════════════════════════════════════════════════════════════════════
# BLOCK RENDERERS
# ═══════════════════════════════════════════════════════════════════════════════

def render_text_block(content: str, pm: PageManager) -> None:
    pm.ensure_space(LINE_HEIGHT * 2)
    pm.x = MARGIN_LEFT
    _render_string(
        content, pm,
        folder=_cfg.svg_text,
        font_size=FONT_SIZE,
        char_spacing=CHAR_SPACING,
        word_spacing=WORD_SPACING,
        asc_h=ASCENDER_H, x_h=X_HEIGHT, desc_d=DESCENDER_D,
        line_height=LINE_HEIGHT,
        left_margin=MARGIN_LEFT,
    )
    pm.y += LINE_HEIGHT
    pm.x  = MARGIN_LEFT


def render_heading_block(content: str, level: int, pm: PageManager) -> None:
    scale   = HEADING_SCALE.get(level, 1.0)
    asc_h   = int(ASCENDER_H * scale)
    x_h     = int(X_HEIGHT   * scale)
    desc_d  = int(DESCENDER_D * scale)
    fs      = int(FONT_SIZE   * scale)
    lh      = int(LINE_HEIGHT * scale * 1.05)
    cs      = int(CHAR_SPACING * scale)
    ws      = int(WORD_SPACING * scale)

    # gap above heading
    if pm.y > MARGIN_TOP + LINE_HEIGHT:
        pm.y += int(LINE_HEIGHT * 0.35)

    pm.ensure_space(lh * 2)
    pm.x = MARGIN_LEFT

    y_before = pm.y

    _render_string(
        content, pm,
        folder=_cfg.svg_text,
        font_size=fs,
        char_spacing=cs,
        word_spacing=ws,
        asc_h=asc_h, x_h=x_h, desc_d=desc_d,
        line_height=lh,
        left_margin=MARGIN_LEFT,
    )

    # underline for top-level headings
    if level in HEADING_UNDERLINE:
        ul_y = pm.y + 4
        draw = ImageDraw.Draw(pm.canvas)
        # slightly wobbly underline
        segments = 40
        x0 = MARGIN_LEFT
        x1 = PAGE_W - MARGIN_RIGHT
        step = (x1 - x0) / segments
        for i in range(segments):
            sx = int(x0 + i * step)
            ex = int(x0 + (i + 1) * step)
            sy = ul_y + random.randint(-1, 1)
            ey = ul_y + random.randint(-1, 1)
            draw.line([(sx, sy), (ex, ey)], fill=INK_COLOR, width=2)

    pm.y += lh
    pm.x  = MARGIN_LEFT


def render_list_block(items: list, style: str, pm: PageManager) -> None:
    indent = MARGIN_LEFT + 24
    for idx, item in enumerate(items):
        prefix = f"{idx+1}. " if style == 'numbered' else "- "
        full   = prefix + item
        pm.ensure_space(LINE_HEIGHT * 2)
        pm.x = indent
        _render_string(
            full, pm,
            folder=_cfg.svg_text,
            font_size=FONT_SIZE,
            char_spacing=CHAR_SPACING,
            word_spacing=WORD_SPACING,
            asc_h=ASCENDER_H, x_h=X_HEIGHT, desc_d=DESCENDER_D,
            line_height=LINE_HEIGHT,
            left_margin=indent,
        )
        pm.y += LINE_HEIGHT
        pm.x  = MARGIN_LEFT


def render_code_block(content: str, pm: PageManager) -> None:
    pm.y += int(LINE_HEIGHT * 0.35)

    lines = content.split('\n')
    for raw_line in lines:
        stripped    = raw_line.expandtabs(4)
        n_indent    = len(stripped) - len(stripped.lstrip())
        stripped    = stripped.lstrip()
        extra       = n_indent * CODE_INDENT_STEP
        left        = MARGIN_LEFT + CODE_INDENT_BASE + extra

        pm.ensure_space(CODE_LINE_HEIGHT * 2)
        pm.x = left

        _render_string(
            stripped, pm,
            folder=_cfg.svg_code,
            font_size=CODE_FONT_SIZE,
            char_spacing=CODE_CHAR_SPACING,
            word_spacing=CODE_WORD_SPACING,
            asc_h=CODE_ASCENDER_H, x_h=CODE_X_HEIGHT, desc_d=CODE_DESCENDER_D,
            line_height=CODE_LINE_HEIGHT,
            left_margin=left,
            wrap=False,   # code lines should NOT wrap
        )
        pm.y += CODE_LINE_HEIGHT
        pm.x  = MARGIN_LEFT

    pm.y += int(LINE_HEIGHT * 0.35)


def render_table_block(block: dict, pm: PageManager) -> None:
    """
    Render a table with hand-drawn ruled lines and handwritten cell content.
    Falls back gracefully when cells overflow.
    """
    headers = block.get('headers', [])
    rows    = block.get('rows', [])
    caption = block.get('caption', '')

    if not headers and not rows:
        return

    ncols = len(headers) if headers else (len(rows[0]) if rows else 1)
    nrows = len(rows) + (1 if headers else 0)

    # Estimate column width (equal distribution)
    total_w   = PAGE_W - MARGIN_LEFT - MARGIN_RIGHT
    col_w     = total_w // ncols
    cell_h    = int(LINE_HEIGHT * 1.6)
    table_h   = nrows * cell_h + cell_h  # + caption row

    pm.y += int(LINE_HEIGHT * 0.4)
    pm.ensure_space(table_h + LINE_HEIGHT * 2)

    draw = ImageDraw.Draw(pm.canvas)

    # Optional caption above
    if caption:
        pm.x = MARGIN_LEFT
        _render_string(
            caption, pm,
            folder=_cfg.svg_text,
            font_size=int(FONT_SIZE * 0.85),
            char_spacing=CHAR_SPACING,
            word_spacing=WORD_SPACING,
            asc_h=int(ASCENDER_H * 0.85), x_h=int(X_HEIGHT * 0.85),
            desc_d=int(DESCENDER_D * 0.85),
            line_height=LINE_HEIGHT,
            left_margin=MARGIN_LEFT,
        )
        pm.y += int(LINE_HEIGHT * 1.1)
        pm.x  = MARGIN_LEFT

    table_top = pm.y
    all_rows  = ([headers] if headers else []) + list(rows)

    for ri, row in enumerate(all_rows):
        row_y = table_top + ri * cell_h
        is_header = (ri == 0 and bool(headers))

        for ci in range(ncols):
            cell_x = MARGIN_LEFT + ci * col_w
            cell_text = str(row[ci]) if ci < len(row) else ''

            # Draw cell border (wobbly hand-drawn style)
            _draw_wobbly_rect(draw,
                              cell_x, row_y,
                              cell_x + col_w, row_y + cell_h)

            # Render cell text
            text_x = cell_x + 8
            text_y = row_y + int(cell_h * 0.55)   # vertically centred
            _tmp_x, _tmp_y = pm.x, pm.y
            pm.x = text_x
            pm.y = text_y

            fs      = int(FONT_SIZE * (0.80 if is_header else 0.72))
            asc_h   = int(ASCENDER_H * (0.80 if is_header else 0.72))
            x_h     = int(X_HEIGHT   * (0.80 if is_header else 0.72))
            desc_d  = int(DESCENDER_D * (0.80 if is_header else 0.72))
            lh      = int(LINE_HEIGHT * 0.75)

            _render_string(
                cell_text, pm,
                folder=_cfg.svg_text,
                font_size=fs,
                char_spacing=CHAR_SPACING,
                word_spacing=WORD_SPACING,
                asc_h=asc_h, x_h=x_h, desc_d=desc_d,
                line_height=lh,
                left_margin=text_x,
                right_margin=PAGE_W - (cell_x + col_w) + 8,
                wrap=True,
            )

            pm.x = _tmp_x
            pm.y = _tmp_y   # reset; table controls its own y

    pm.y = table_top + len(all_rows) * cell_h + int(LINE_HEIGHT * 0.5)
    pm.x = MARGIN_LEFT


def _draw_wobbly_rect(draw: ImageDraw.Draw,
                      x0: int, y0: int, x1: int, y1: int,
                      color=INK_COLOR, width: int = 2) -> None:
    """Draw a rectangle with slightly wobbly edges (hand-drawn feel)."""
    def wobble(v, a=2):
        return v + random.randint(-a, a)

    corners = [(wobble(x0), wobble(y0)),
               (wobble(x1), wobble(y0)),
               (wobble(x1), wobble(y1)),
               (wobble(x0), wobble(y1)),
               (wobble(x0), wobble(y0))]

    for i in range(len(corners) - 1):
        draw.line([corners[i], corners[i+1]], fill=color, width=width)


def render_diagram_block(block: dict, pm: PageManager) -> None:
    """Placeholder — leave a visible gap with a note."""
    pm.ensure_space(LINE_HEIGHT * 4)
    draw = ImageDraw.Draw(pm.canvas)
    note = "[Diagram — see original document]"
    # Draw dashed box
    x0, y0 = MARGIN_LEFT, pm.y
    x1, y1 = PAGE_W - MARGIN_RIGHT, pm.y + LINE_HEIGHT * 3
    for x in range(x0, x1, 12):
        draw.line([(x, y0), (min(x + 6, x1), y0)], fill=(150, 100, 80), width=1)
        draw.line([(x, y1), (min(x + 6, x1), y1)], fill=(150, 100, 80), width=1)
    for y in range(y0, y1, 12):
        draw.line([(x0, y), (x0, min(y + 6, y1))], fill=(150, 100, 80), width=1)
        draw.line([(x1, y), (x1, min(y + 6, y1))], fill=(150, 100, 80), width=1)
    pm.y += LINE_HEIGHT * 3 + 10
    pm.x  = MARGIN_LEFT


# ═══════════════════════════════════════════════════════════════════════════════
# BLOCK DISPATCHER
# ═══════════════════════════════════════════════════════════════════════════════

def render_block(block: dict, pm: PageManager) -> None:
    btype = block.get('type', '')

    if btype == 'text':
        render_text_block(block['content'], pm)

    elif btype == 'heading':
        render_heading_block(block['content'], block.get('level', 4), pm)

    elif btype == 'list':
        render_list_block(block.get('items', []), block.get('style', 'bullet'), pm)

    elif btype in ('code', 'pseudocode'):
        render_code_block(block['content'], pm)

    elif btype == 'table':
        render_table_block(block, pm)

    elif btype == 'diagram':
        render_diagram_block(block, pm)

    else:
        print(f"[UNKNOWN BLOCK TYPE] '{btype}' — skipping")


# ═══════════════════════════════════════════════════════════════════════════════
# JSON LOADER  — flattens the nested JSON into a flat list of render-blocks
# ═══════════════════════════════════════════════════════════════════════════════

def load_blocks(json_path: str) -> list:
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    blocks = []

    meta = data.get('meta', {})
    if meta.get('title'):
        blocks.append({'type': 'heading', 'level': 1, 'content': meta['title']})
    if meta.get('description'):
        blocks.append({'type': 'text', 'content': meta['description']})

    for question in data.get('questions', []):
        q_title = question.get('title', question.get('id', ''))
        blocks.append({'type': 'heading', 'level': 2, 'content': q_title})

        for part in question.get('parts', []):
            p_title = part.get('title', part.get('id', ''))
            marks   = part.get('marks')
            if marks:
                p_title += f"  [{marks} marks]"
            blocks.append({'type': 'heading', 'level': 3, 'content': p_title})

            for b in part.get('blocks', []):
                blocks.append(b)

    return blocks


# ═══════════════════════════════════════════════════════════════════════════════
# MASTER RENDER
# ═══════════════════════════════════════════════════════════════════════════════

def render_assignment(json_path: str) -> list[Image.Image]:
    blocks = load_blocks(json_path)
    pm     = PageManager()

    total  = len(blocks)
    for i, block in enumerate(blocks):
        sys.stdout.write(f"\r  Rendering block {i+1}/{total} ({block.get('type','?')})...   ")
        sys.stdout.flush()
        render_block(block, pm)

    pm.finish()
    print(f"\n  Done — {len(pm.pages)} page(s) generated.")
    return pm.pages


# ═══════════════════════════════════════════════════════════════════════════════
# POST-PROCESSING
# ═══════════════════════════════════════════════════════════════════════════════

def post_process_pages(pages: list[Image.Image]) -> list[Image.Image]:
    processed = []
    for i, pg in enumerate(pages):
        print(f"  Post-processing page {i+1}/{len(pages)}…")
        pg = _add_scan_effect(pg)
        pg = _perspective_warp(pg)
        pg = _add_shadow_and_tilt(pg)
        processed.append(pg)
    return processed


# ═══════════════════════════════════════════════════════════════════════════════
# SAVE
# ═══════════════════════════════════════════════════════════════════════════════

def save_pdf(pages: list[Image.Image], out_path: str) -> None:
    if not pages:
        print("[ERR] No pages to save.")
        return
    # Convert to RGB (PDF via Pillow requires RGB or L)
    rgb_pages = [p.convert("RGB") for p in pages]
    rgb_pages[0].save(
        out_path,
        save_all=True,
        append_images=rgb_pages[1:],
        resolution=150,
    )
    print(f"  Saved: {out_path}  ({len(pages)} pages)")


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG OBJECT  (populated from CLI args)
# ═══════════════════════════════════════════════════════════════════════════════

class _Config:
    svg_text: str = DEFAULT_SVG_FOLDER
    svg_code: str = DEFAULT_SVG_CODE_FOLDER

_cfg = _Config()


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Convert assignment JSON to handwritten PDF")
    parser.add_argument('--json',      default=DEFAULT_INPUT_JSON,
                        help='Path to assignment_structured.json')
    parser.add_argument('--out',       default=DEFAULT_OUTPUT_PDF,
                        help='Output PDF path')
    parser.add_argument('--svg-text',  default=DEFAULT_SVG_FOLDER,
                        help='Folder with cursive SVG glyphs (alpha3)')
    parser.add_argument('--svg-code',  default=DEFAULT_SVG_CODE_FOLDER,
                        help='Folder with monospace SVG glyphs (code_alpha)')
    args = parser.parse_args()

    # Wire config
    _cfg.svg_text = args.svg_text
    _cfg.svg_code = args.svg_code

    print("=" * 60)
    print("  Handwritten Assignment PDF Generator")
    print("=" * 60)
    print(f"  Input  : {args.json}")
    print(f"  Output : {args.out}")
    print(f"  SVG text folder : {args.svg_text}")
    print(f"  SVG code folder : {args.svg_code}")
    print()

    if not os.path.exists(args.json):
        sys.exit(f"[ERR] JSON not found: {args.json}")

    print("► Rendering pages…")
    pages = render_assignment(args.json)

    print("► Post-processing (scan, warp, shadow)…")
    pages = post_process_pages(pages)

    print("► Saving PDF…")
    save_pdf(pages, args.out)

    print()
    print("✓ Complete!")


if __name__ == '__main__':
    main()
