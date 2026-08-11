# Handwriting Generator

Converts structured text/assignment content (JSON) into a multi-page PDF that looks like genuine handwriting — not a "handwriting font," but per-character SVG glyph rendering with realistic pen-pressure variation, baseline jitter, and paper texture.

## What makes this different from a handwriting font

A font renders every instance of the same letter identically. This renders each character as an individually-processed SVG glyph with:
- **Variable pen pressure** — each character gets a randomized opacity (0.72–1.0) to mimic real ink flow, plus a small chance (4%) of a subtle blur to simulate ink lift
- **Baseline jitter and line drift** — lines aren't perfectly straight or evenly spaced; each has slight angle and vertical drift variation
- **Correct ascender/descender/x-height typography** — letters are classified (ascenders, descenders, x-height-only) and scaled/positioned individually, the way real handwriting varies stroke height by letterform, not just a fixed font baseline
- **A full symbol set for technical/algorithmic content** — beyond A–Z/0–9, it maps mathematical and CS notation (Σ, Θ, Ω, ∈, ⊆, →, ∀, ∃, ≤, ≥, ¬, ∧, ∨, and more) plus full punctuation, so it can render actual computer science assignments, not just prose
- **Two distinct glyph sets** — a cursive set for normal text and a separate, more upright set for code/pseudocode blocks, with independently tuned metrics (size, spacing, line height) for each
- **Paper realism** — subtle page tilt, soft drop shadow, and a scan-line vignette overlay so the output reads as a photographed/scanned page rather than a flat render

## How it works


assignment_structured.json
        │
        ▼
┌────────────────────────────┐
│ handwritten_pdf_generator  │
│                            │
│  1. classify each char     │  (ascender / descender / x-height / symbol)
│  2. look up its SVG glyph  │  (alpha3/ = text, code_alpha/ = code)
│  3. trim + scale + tint    │  (per-char pen-pressure opacity, occasional blur)
│  4. lay out along a line   │  (jittered baseline, char/word spacing)
│  5. render tables as a     │  (hand-drawn ruled grid)
│     hand-drawn grid        │
│  6. paginate + overlay     │  (paper texture, tilt, vignette)
└────────────────────────────┘
        │
        ▼
handwritten_assignment.pdf


Glyphs are cached in memory per (path, target_height) so repeated characters at the same size are only rasterized from SVG once per run.

## Usage

bash
pip install pillow numpy cairosvg

python handwritten_pdf_generator.py \
    --json assignment_structured.json \
    --out handwritten_assignment.pdf \
    --svg-text alpha3/ \
    --svg-code code_alpha/


If a glyph SVG is missing for a given character, the generator renders an inline placeholder (⬜ svg_name missing) rather than failing the whole run — useful for spotting gaps in the glyph set during development.

## Repository contents

- handwritten_pdf_generator.py — the generator (~900 lines)
- alpha2/, alpha3/, alpha3_png/ — handwriting glyph sets (SVG source + rasterized variants) covering letters, digits, and technical/math symbols

## Known limitations / roadmap

- [ ] Default paths in the script point to a local /home/sumit/Downloads/... — should default to relative paths (./alpha3/, ./code_alpha/) so the repo runs out of the box for anyone who clones it
- [ ] Glyph assets (alpha2/, alpha3_png/) are committed directly as binary files — fine for now, but if the glyph set grows further this is a candidate for Git LFS
- [ ] No requirements.txt yet — dependencies are pillow, numpy, cairosvg
- [ ] No sample assignment_structured.json or example output image in the repo — add one so a visitor can see the output without running it themselves first (this is the single highest-impact addition: a before/after image sells this project in one glance)

## Example use case

Built to auto-generate handwritten-looking assignment submissions and study materials from structured JSON — including full support for algorithm pseudocode and CS notation, not just plain prose.
