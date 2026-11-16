"""Reads a scanned "known words" checklist (checklist_sheet.py) back in.

Purely classical image processing - no OCR, no machine learning. It finds
the four black corner squares printed on the page, uses their positions to
work out the exact scale/rotation/offset the scanner produced (so this
works regardless of DPI or minor skew), then for every word's checkbox
position (computed the same way the PDF generator computed it) measures
how much dark ink sits inside that box to decide tick vs blank.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageOps

from .checklist_sheet import (
    CHECKBOX_SIZE,
    PAGE_HEIGHT,
    PAGE_WIDTH,
    ChecklistPage,
    checkbox_centres,
    marker_positions,
)

# A scanned pixel is "ink" once it's this dark (0 = black, 255 = white).
INK_THRESHOLD = 140
# Fraction of dark pixels inside a checkbox's sampling region above which
# it counts as ticked. Real hand-drawn ticks are thin pen/pencil strokes,
# not a solid fill, so this is tuned low - calibrated against real scanned
# sheets, not just solid synthetic test marks.
TICK_FILL_RATIO = 0.07
# How far in from each checkbox edge to sample, as a fraction of the box
# size - keeps the printed grey border out of the measurement. Vertical
# inset is deliberately larger than horizontal: a big diagonal tick often
# overshoots into the row above or below, and excluding more of the box's
# own top/bottom keeps that overshoot from being mistaken for the
# neighbouring checkbox's own mark.
SAMPLE_INSET_X = 0.12
SAMPLE_INSET_Y = 0.34

# A detected marker whose area differs from the expected size by more than
# this (as a ratio) is treated as noise, not a real marker.
_MARKER_AREA_TOLERANCE = 3.0


class OmrError(ValueError):
    """Raised when a scanned page can't be read reliably."""


@dataclass
class PageResult:
    words: dict[str, bool]  # word -> ticked
    marker_confidence: float  # 0..1, how cleanly the 4 corners were found


def load_image(path: str) -> Image.Image:
    """Opens a scanned page from an image file. Phone photos often carry an
    EXIF orientation tag instead of actually rotating the pixels, which
    would otherwise make the corner markers show up sideways to this
    code - exif_transpose bakes that rotation in first."""
    img = Image.open(path)
    img.load()
    img = ImageOps.exif_transpose(img)
    return img.convert("L")


def load_page_image(path: str, page_number: int = 1) -> Image.Image:
    """Opens a scanned page from either an image file or a PDF (1-based
    page_number, for a multi-page PDF covering more than one page)."""
    if path.lower().endswith(".pdf"):
        pages = load_pdf_pages(path)
        if page_number > len(pages):
            raise OmrError(f"That PDF only has {len(pages)} page(s), but page {page_number} was requested.")
        return pages[page_number - 1]
    return load_image(path)


def load_pdf_pages(path: str, dpi: int = 200) -> list[Image.Image]:
    """Rasterises every page of a PDF scan to a grayscale image, in order."""
    import fitz  # PyMuPDF

    images: list[Image.Image] = []
    doc = fitz.open(path)
    try:
        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        for page in doc:
            pix = page.get_pixmap(matrix=matrix, colorspace=fitz.csGRAY)
            img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
            images.append(img)
    finally:
        doc.close()
    return images


def _to_array(img: Image.Image) -> np.ndarray:
    return np.asarray(img, dtype=np.uint8)


def _find_corner_marker(region: np.ndarray) -> tuple[float, float] | None:
    """Finds the centroid of the largest dark blob in a small image region.
    Returns (x, y) in that region's own pixel coordinates, or None."""
    dark = region < INK_THRESHOLD
    if not dark.any():
        return None
    ys, xs = np.nonzero(dark)
    # A lone marker square should be a single compact blob; if the dark
    # pixels are too spread out, something else (text, a stray mark) is in
    # this corner and we can't trust it.
    if (xs.max() - xs.min() + 1) > region.shape[1] * 0.6 or (ys.max() - ys.min() + 1) > region.shape[0] * 0.6:
        return None
    return float(xs.mean()), float(ys.mean())


def _detect_markers_at_radius(arr: np.ndarray, search_radius_pt: float) -> dict[str, tuple[float, float]] | None:
    h, w = arr.shape
    # The scanned page should be close to a full A4 at some unknown DPI -
    # use that to estimate pixels-per-point, even before markers are found.
    approx_scale_x = w / PAGE_WIDTH
    approx_scale_y = h / PAGE_HEIGHT

    found: dict[str, tuple[float, float]] = {}
    for key, (px, py) in marker_positions().items():
        py_img = PAGE_HEIGHT - py  # flip to top-down image coordinates
        cx, cy = px * approx_scale_x, py_img * approx_scale_y
        rx, ry = search_radius_pt * approx_scale_x, search_radius_pt * approx_scale_y

        x0, x1 = max(int(cx - rx), 0), min(int(cx + rx), w)
        y0, y1 = max(int(cy - ry), 0), min(int(cy + ry), h)
        if x1 <= x0 or y1 <= y0:
            return None

        centre = _find_corner_marker(arr[y0:y1, x0:x1])
        if centre is None:
            return None
        found[key] = (centre[0] + x0, centre[1] + y0)
    return found


def _detect_markers(arr: np.ndarray) -> dict[str, tuple[float, float]] | None:
    """Looks for the 4 corner markers, searching a window around where each
    one is *expected* to be (from the page's known scale) rather than the
    raw image corner, so nearby header/footer text never gets mistaken for
    one. Tries a tight window first (safest against stray marks nearby),
    then a progressively wider one, to tolerate a scanner/scanning app
    that cropped or shifted the page more than usual. Returns pixel
    centres, or None if no window size found all 4."""
    for search_radius_pt in (45.0, 70.0, 100.0):
        found = _detect_markers_at_radius(arr, search_radius_pt)
        if found is not None:
            return found
    return None


def _fit_affine(src_pts: list[tuple[float, float]], dst_pts: list[tuple[float, float]]) -> np.ndarray:
    """Least-squares affine transform mapping src (PDF points) -> dst
    (image pixels). Returns a 2x3 matrix [[a,b,tx],[c,d,ty]]."""
    A = []
    b = []
    for (sx, sy), (dx, dy) in zip(src_pts, dst_pts):
        A.append([sx, sy, 1, 0, 0, 0])
        A.append([0, 0, 0, sx, sy, 1])
        b.append(dx)
        b.append(dy)
    sol, *_ = np.linalg.lstsq(np.array(A, dtype=float), np.array(b, dtype=float), rcond=None)
    return sol.reshape(2, 3)


def _apply_affine(m: np.ndarray, x: float, y: float) -> tuple[float, float]:
    px = m[0, 0] * x + m[0, 1] * y + m[0, 2]
    py = m[1, 0] * x + m[1, 1] * y + m[1, 2]
    return px, py


def read_page(image: Image.Image, page: ChecklistPage) -> PageResult:
    """Reads one scanned page against the word layout it should match."""
    img_gray = image.convert("L") if image.mode != "L" else image
    arr = _to_array(img_gray)

    markers = _detect_markers(arr)
    if markers is None:
        raise OmrError(
            "Couldn't find the 4 black corner squares on this page. "
            "Make sure the whole page was scanned, the right way up, without cropping the edges."
        )

    pdf_corners = marker_positions()
    # PDF points have the origin bottom-left (y grows upward); image pixels
    # have the origin top-left (y grows downward) - flip y to match.
    src = [pdf_corners["tl"], pdf_corners["tr"], pdf_corners["bl"], pdf_corners["br"]]
    src = [(x, PAGE_HEIGHT - y) for x, y in src]
    dst = [markers["tl"], markers["tr"], markers["bl"], markers["br"]]
    transform = _fit_affine(src, dst)

    # Scale factor (image pixels per PDF point) from how far apart the
    # markers ended up, used to size the per-checkbox sampling region.
    scale_x = abs(markers["tr"][0] - markers["tl"][0]) / abs(pdf_corners["tr"][0] - pdf_corners["tl"][0])
    scale_y = abs(markers["bl"][1] - markers["tl"][1]) / abs(pdf_corners["tl"][1] - pdf_corners["bl"][1])

    centres = checkbox_centres(len(page.words))
    half_box_x = (CHECKBOX_SIZE / 2) * scale_x * (1 - SAMPLE_INSET_X)
    half_box_y = (CHECKBOX_SIZE / 2) * scale_y * (1 - SAMPLE_INSET_Y)

    h, w = arr.shape
    results: dict[str, bool] = {}
    for (px, py), word in zip(centres, page.words):
        py_img = PAGE_HEIGHT - py
        ix, iy = _apply_affine(transform, px, py_img)

        x0, x1 = int(round(ix - half_box_x)), int(round(ix + half_box_x))
        y0, y1 = int(round(iy - half_box_y)), int(round(iy + half_box_y))
        x0, y0 = max(x0, 0), max(y0, 0)
        x1, y1 = min(x1, w), min(y1, h)
        if x1 <= x0 or y1 <= y0:
            results[word] = False
            continue

        patch = arr[y0:y1, x0:x1]
        fill_ratio = float((patch < INK_THRESHOLD).mean())
        results[word] = fill_ratio >= TICK_FILL_RATIO

    return PageResult(words=results, marker_confidence=1.0)


def read_checklist(tier_key: str, page_images: dict[int, Image.Image]) -> set[str]:
    """Reads one or more scanned pages for a tier and returns the set of
    words ticked as known. `page_images` maps 1-based page number -> image."""
    from .checklist_sheet import paginate

    pages = paginate(tier_key)
    known: set[str] = set()
    for page in pages:
        image = page_images.get(page.page_index)
        if image is None:
            continue
        result = read_page(image, page)
        known.update(word for word, ticked in result.words.items() if ticked)
    return known
