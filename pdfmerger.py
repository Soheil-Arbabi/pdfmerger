import argparse
import math
import re
import sys
from contextlib import ExitStack
from pathlib import Path

import pymupdf


def detect_plot_area(page, layout):
    """Find closed, axis-aligned vector frames; fail instead of guessing.

    Stacked frames may share x bounds in vertical layouts, and side-by-side
    frames may share y bounds in horizontal layouts. Returned coordinates
    use the visible page coordinate system.
    """
    horizontal, vertical = [], []
    tolerance = 0.75  # PDF points
    min_w = max(30, page.rect.width * 0.20)
    min_h = max(30, page.rect.height * 0.12)

    def edge(a, b):
        a = a * page.rotation_matrix
        b = b * page.rotation_matrix
        if abs(a.y - b.y) <= tolerance and abs(a.x - b.x) >= min_w:
            horizontal.append((min(a.x, b.x), max(a.x, b.x), (a.y+b.y)/2))
        if abs(a.x - b.x) <= tolerance and abs(a.y - b.y) >= min_h:
            vertical.append(((a.x+b.x)/2, min(a.y, b.y), max(a.y, b.y)))

    for drawing in page.get_drawings():
        if drawing.get('color') is None or drawing.get('stroke_opacity', 1) == 0:
            continue
        for item in drawing['items']:
            if item[0] == 'l':
                edge(item[1], item[2])
            elif item[0] == 're':
                r = item[1]
                for a, b in [(r.tl, r.tr), (r.tr, r.br),
                             (r.br, r.bl), (r.bl, r.tl)]:
                    edge(a, b)

    frames = []
    for i, (left, right, y1) in enumerate(horizontal):
        for l2, r2, y2 in horizontal[i+1:]:
            if abs(left-l2) > tolerance or abs(right-r2) > tolerance:
                continue
            top, bottom = sorted((y1, y2))
            if bottom-top < min_h:
                continue
            def has_side(x):
                return any(abs(vx-x) <= tolerance and abs(vt-top) <= tolerance
                           and abs(vb-bottom) <= tolerance
                           for vx, vt, vb in vertical)
            if has_side(left) and has_side(right):
                r = pymupdf.Rect(left, top, right, bottom)
                if not any(max(abs(a-b) for a, b in zip(r, old)) <= tolerance
                           for old in frames):
                    frames.append(r)

    # Inner grid rectangles and inset axes should not replace the main frame.
    frames = [r for r in frames if not any(
        other.contains(r) and other.get_area() > r.get_area() * 1.01
        for other in frames)]
    if not frames:
        raise ValueError('No closed vector plot frame detected. '
                         'Use PDFs with four visible axes spines, or omit '
                         '--align-plot-areas (scanned plots are unsupported).')
    axis = (0, 2) if layout == 'v' else (1, 3)
    if any(abs(r[k]-frames[0][k]) > tolerance
           for r in frames for k in axis):
        raise ValueError('Multiple plot frames have different alignment bounds. '
                         'Split the page into individual plots or omit '
                         '--align-plot-areas.')
    return frames[0]


def panel_rectangles(pages, layout, gap, margin, align):
    """Uniformly scale full pages, preserving every margin and annotation."""
    areas = [detect_plot_area(p, layout) for p in pages] if align else None
    scales = [1.0] * len(pages)
    offsets = [0.0] * len(pages)
    if align:
        spans = [r.width if layout == 'v' else r.height for r in areas]
        scales = [spans[0]/span for span in spans]
        starts = [(r.x0 if layout == 'v' else r.y0)*s
                  for r, s in zip(areas, scales)]
        offsets = [max(starts)-start for start in starts]
    rectangles = []
    cursor = margin
    for page, scale, offset in zip(pages, scales, offsets):
        w, h = page.rect.width*scale, page.rect.height*scale
        x, y = (margin+offset, cursor) if layout == 'v' else (cursor, margin+offset)
        rectangles.append(pymupdf.Rect(x, y, x+w, y+h))
        cursor += (h if layout == 'v' else w) + gap
    return rectangles


def parse_label(value):
    """Read 'Any text(x,y)'; '-' means no label."""
    if value == "-":
        return None

    match = re.fullmatch(
        r"(.*)\(\s*([^,]+)\s*,\s*([^,]+)\s*\)", value
    )
    if not match:
        raise ValueError(
            f"Invalid label: {value!r}. Use 'a(0.1,0.9)' or '-'."
        )

    text, x, y = match.groups()
    x, y = float(x), float(y)

    if not all(math.isfinite(v) and 0 <= v <= 1 for v in (x, y)):
        raise ValueError("Label coordinates must be between 0 and 1.")

    return text, x, y


def merge(args):
    items = args.items
    separators = [i for i, item in enumerate(items) if item in ("h", "v")]

    if len(separators) != 1:
        raise ValueError("Provide exactly one layout: h or v.")

    split = separators[0]
    inputs = items[:split]
    trailing = items[split + 1:]

    if len(inputs) < 2 or not trailing:
        raise ValueError("Provide at least two input PDFs and an output filename.")

    layout = items[split]
    output = Path(trailing[-1]).expanduser()
    labels = [parse_label(value) for value in trailing[:-1]]

    if labels and len(labels) != len(inputs):
        raise ValueError(
            "Provide one label per PDF, or omit all labels. "
            "Use '-' to skip an individual label."
        )

    if not labels:
        labels = [None] * len(inputs)

    if output.suffix.lower() != ".pdf":
        output = output.with_name(output.name + ".pdf")

    sources = [Path(name).expanduser() for name in inputs]

    if any(source.resolve() == output.resolve() for source in sources):
        raise ValueError("Output must not be an input file.")

    if output.exists() and not args.force:
        raise ValueError(f"{output} already exists. Use --force to replace it.")

    for name in ("gap", "margin", "fontsize"):
        value = getattr(args, name)
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"--{name} must be finite and nonnegative.")

    if args.fontsize == 0:
        raise ValueError("--fontsize must be greater than zero.")

    if args.page < 1:
        raise ValueError("--page starts at 1.")

    with ExitStack() as stack:
        documents = [
            stack.enter_context(pymupdf.open(source))
            for source in sources
        ]

        pages = []
        for source, document in zip(sources, documents):
            if not document.is_pdf:
                raise ValueError(f"{source} is not a PDF.")
            if document.needs_pass:
                raise ValueError(f"{source} requires a password.")
            if args.page > len(document):
                raise ValueError(f"{source} has no page {args.page}.")
            pages.append(document[args.page - 1])

        rectangles = panel_rectangles(pages, layout, args.gap, args.margin,
                                      args.align_plot_areas)

        result = stack.enter_context(pymupdf.open())
        canvas = result.new_page(
            width=max(r.x1 for r in rectangles) + args.margin,
            height=max(r.y1 for r in rectangles) + args.margin,
        )

        x = y = args.margin
        placements = []

        # Place all panels first so later panels cannot cover labels.
        for document, page, label, rectangle in zip(documents, pages, labels, rectangles):
            x, y = rectangle.x0, rectangle.y0
            w, h = rectangle.width, rectangle.height

            # Blank PDF pages need no embedded content.
            if page.get_contents():
                canvas.show_pdf_page(
                    rectangle, document, args.page - 1
                )

            if label is not None:
                text, relative_x, relative_y = label

                # Convert normalized coordinates to PDF coordinates.
                # User coordinates: origin at bottom-left; y increases upward.
                # PDF coordinates: origin at top-left; y increases downward.
                dx = relative_x * w
                dy = (1 - relative_y) * h
                font = pymupdf.Font("hebo")
                if any(not font.has_glyph(ord(char)) for char in text):
                    raise ValueError(
                        "This version uses Helvetica labels. "
                        "A label contains an unsupported character."
                    )

                text_width = font.text_length(
                    text, fontsize=args.fontsize
                )
                top = dy - font.ascender * args.fontsize
                bottom = dy - font.descender * args.fontsize

                if dx + text_width > w or top < 0 or bottom > h:
                    raise ValueError(
                        f"Label {text!r} does not fit inside its panel. "
                        "Adjust its coordinates or --fontsize."
                    )

                placements.append((text, x + dx, y + dy))

            if layout == "h":
                x += w + args.gap
            else:
                y += h + args.gap

        if placements:
            canvas.insert_font(fontname="PanelLabelBold",
                               fontbuffer=pymupdf.Font("hebo").buffer)
        for text, x, y in placements:
            canvas.insert_text(
                (x, y),
                text,
                fontsize=args.fontsize,
                fontname="PanelLabelBold",
                color=(0, 0, 0),
                overlay=True,
            )

        result.save(output, garbage=4, deflate=True)

    print(f"Saved: {output}")


def main():
    parser = argparse.ArgumentParser(
        description="Combine PDF panels on a single page with custom labels.",
        usage='%(prog)s PDF PDF [...] h|v ["label(x,y)" ...] OUTPUT [options]',
    )
    parser.add_argument("items", nargs="+")
    parser.add_argument("--align-plot-areas", action="store_true",
                        help="Align closed vector plot frames: equal widths and left/right "
                             "edges for v; equal heights and top/bottom edges for h. "
                             "Uses the first PDF's plot size; preserves full pages.")
    parser.add_argument("--gap", type=float, default=10,
                        help="Space between panels in points (default: 10)")
    parser.add_argument("--margin", type=float, default=0,
                        help="Outer margin in points (default: 0)")
    parser.add_argument("--fontsize", type=float, default=16,
                        help="Label font size in points (default: 16)")
    parser.add_argument("--page", type=int, default=1,
                        help="Page to use from each PDF, starting at 1")
    parser.add_argument("--force", action="store_true",
                        help="Replace an existing output")
    args = parser.parse_args()

    try:
        merge(args)
    except Exception as error:
        print(f"pdfmerger: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
