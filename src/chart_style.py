"""Shared chart colours and matplotlib style, so every chart in the project looks the same.

Usage in a notebook:
    import sys; sys.path.append("../src")
    from chart_style import apply_style, YEAR_COLOR, FY_COLOR, INK_2, MUTED, AXIS
    apply_style()
"""

import time

import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

SURFACE = "#fcfcfb"
INK = "#0b0b0b"     # titles, key numbers
INK_2 = "#52514e"   # labels, legends
MUTED = "#898781"   # tick labels, reference lines
GRID = "#e1e0d9"
AXIS = "#c3c2b7"

# One blue ramp, light -> dark = old -> recent
RAMP = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"]

# A year keeps the same colour in every chart
YEAR_COLOR = dict(zip(range(2022, 2027), RAMP))                      # season-years 2022..2026
FY_COLOR = dict(zip(["FY22", "FY23", "FY24", "FY25", "FY26"], RAMP))  # financial years


# A region keeps the same colour in every chart that compares regions
REGION_COLOR = {"NSW1": "#2a78d6", "SA1": "#eb6834"}

# Sequential blue for heatmaps: near-zero is light, high is dark
SEQUENTIAL = LinearSegmentedColormap.from_list("blue_seq", [
    "#f0f6fe", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b",
])


def save_chart(fig, path, attempts=5):
    """Save a figure as PNG, retrying briefly if Windows has the file open (e.g. an image preview tab)."""
    for attempt in range(attempts):
        try:
            fig.savefig(path, dpi=200, bbox_inches="tight")
            return
        except OSError:
            if attempt == attempts - 1:
                raise
            time.sleep(1)


def apply_style():
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "font.family": "Segoe UI", "font.size": 10,
        "text.color": INK, "axes.labelcolor": INK_2, "axes.titlecolor": INK,
        "xtick.color": MUTED, "ytick.color": MUTED,
        "axes.edgecolor": AXIS, "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": 0.8,
        "axes.titlesize": 11, "axes.titleweight": "semibold", "axes.titlelocation": "left",
    })
