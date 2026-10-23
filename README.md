# PDF Merger

A small Python tool I made to combine PDF figures horizontally or vertically and add panel labels. I use it to prepare figures for papers (especially on overleaf), and I hope it is useful for others too.

It keeps vector graphics sharp without converting the PDFs to images.

## Installation

```bash
pip3 install --user git+https://github.com/Soheil-Arbabi/pdfmerger.git
```

You need Python 3.9 or newer and Git. The required Python package, PyMuPDF, is installed automatically. If you use a virtual environment, remove `--user`.

## Usage

For two figures next to each other:

```bash
pdfmerger figure1.pdf figure2.pdf h "a(0.05,0.90)" "b(0.05,0.90)" combined.pdf
```

Use `h` for horizontal arrangement and `v` to stack figures vertically. You can combine more than two PDFs:

```bash
pdfmerger figure1.pdf figure2.pdf figure3.pdf v "a(0.05,0.90)" "b(0.05,0.90)" "c(0.05,0.90)" combined.pdf
```

The figures appear in the order you provide them. By default, the first page of each PDF is used.

## Labels

Label coordinates range from 0 to 1, relative to each panel. `(0,0)` is bottom-left and `(1,1)` is top-right. For example, `"a(0.05,0.90)"` puts **a** near the upper-left corner.

If your figures already have labels, you can leave out the label arguments:

```bash
pdfmerger figure1.pdf figure2.pdf v combined.pdf
```

Or use `"-"` to skip a particular label:

```bash
pdfmerger figure1.pdf figure2.pdf v "-" "b(0.05,0.90)" combined.pdf
```

If you provide labels, you need one argument for each PDF. To skip one, use `"-"` alone, without coordinates.

## Aligning plot areas

Sometimes figures have different margins, so their axes do not line up after merging. You can try:

```bash
pdfmerger figure1.pdf figure2.pdf v combined.pdf --align-plot-areas
```

This matches plot widths for vertical arrangements, or plot heights for horizontal arrangements, using the first figure as the reference. It scales the whole page, including existing text, and keeps the surrounding labels and legends.

This option currently needs a rectangular vector plot frame with all four edges visible. It does not work with scanned plots and may not work with complicated subplot layouts. If detection fails, run the command without this option.

## Other options

| Option | What it does | Default |
|---|---|---|
| `--gap` | Space between panels, in points | `10` |
| `--margin` | Outer margin, in points | `0` |
| `--fontsize` | Font size of the added labels, in points | `16` |
| `--page` | Page to use from each PDF | `1` |
| `--force` | Overwrite an existing output file | Off |
| `--help` | Show help | |

For example:

```bash
pdfmerger figure1.pdf figure2.pdf h "a(0.05,0.90)" "b(0.05,0.90)" combined.pdf --gap 20 --margin 10 --fontsize 18 --force
```

There are also very useful tools such as pdfcrop for removing empty margins and pdfjam for arranging PDF pages.
I made this tool for the figure arrangements and labels I often need in my own work.

If you find a problem or have a suggestion, please open an issue.

Have fun!
