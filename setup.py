from setuptools import setup

setup(
    name="soheil-pdfmerger",
    version="1.0.0",
    description="Arrange PDF panels horizontally or vertically with labels",
    py_modules=["pdfmerger"],
    python_requires=">=3.9",
    install_requires=["PyMuPDF>=1.24"],
    entry_points={
        "console_scripts": [
            "pdfmerger=pdfmerger:main",
        ],
    },
)
