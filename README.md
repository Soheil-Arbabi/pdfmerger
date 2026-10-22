# pdfmerger


Combine PDF figures horizontally or vertically with custom labels.


installation: pip3 install --user git+https://github.com/Soheil-Arbabi/pdfmerger.git



Usage Example:


pdfmerger figure1.pdf figure2.pdf h "a(0.05,0.90)" "b(0.05,0.90)" combined.pdf

h arranges panels horizontally; v stacks them vertically.
Label coordinates range from 0 to 1, relative to each panel.
(0,0) is bottom-left; (1,1) is top-right.
By default, the first page of each input PDF is used.

Have Fun!
