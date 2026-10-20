import argparse
import math
import re
import sys
from contextlib import ExitStack
from pathlib import Path

import pymupdf


def parse_label(value):
    """Read 'Any text(x,y)'; '-' means no label."""
    if value == "-":
        return None

    match = re.fullmatch(
        r"(.*)\(\s*([^,]+)\s*,\s*([^,]+)\s*\)", value
    )
    if not match:
        raise ValueError(
            f"Invalid label: {value!r}. Use 'a(10,20)' or '-'."
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

        widths = [page.rect.width for page in pages]
        heights = [page.rect.height for page in pages]

        if layout == "h":
            width = sum(widths) + args.gap * (len(pages) - 1)
            height = max(heights)
        else:
            width = max(widths)
            height = sum(heights) + args.gap * (len(pages) - 1)

        result = stack.enter_context(pymupdf.open())
        canvas = result.new_page(
            width=width + 2 * args.margin,
            height=height + 2 * args.margin,
        )

        x = y = args.margin
        placements = []

        # Place all panels first so later panels cannot cover labels.
        for document, page, label in zip(documents, pages, labels):
            w, h = page.rect.width, page.rect.height
            rectangle = pymupdf.Rect(x, y, x + w, y + h)

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

        for text, x, y in placements:
            canvas.insert_text(
                (x, y),
                text,
                fontsize=args.fontsize,
                fontname="hebo",
                color=(0, 0, 0),
            )

        result.save(output, garbage=4, deflate=True)

    print(f"Saved: {output}")


def main():
    parser = argparse.ArgumentParser(
        description="Combine PDF panels on a single page with custom labels.",
        usage='%(prog)s PDF PDF [...] h|v ["label(x,y)" ...] OUTPUT [options]',
    )
    parser.add_argument("items", nargs="+")
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
