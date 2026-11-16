import unittest

import numpy as np
from PIL import Image, ImageDraw

from precision_worksheets import omr
from precision_worksheets.checklist_sheet import (
    CHECKBOX_SIZE,
    MARKER_SIZE,
    PAGE_HEIGHT,
    PAGE_WIDTH,
    checkbox_centres,
    marker_positions,
    paginate,
)

DPI = 180
SCALE = DPI / 72.0


def _pt_to_px(x_pt: float, y_pt_bottom_up: float) -> tuple[float, float]:
    y_top_down = PAGE_HEIGHT - y_pt_bottom_up
    return x_pt * SCALE, y_top_down * SCALE


def render_synthetic_scan(page, known_words, rotation_deg=0.0, dpi=DPI):
    """Builds a blank-page image with markers and ticks drawn directly,
    bypassing the real PDF/printer/scanner round trip entirely - this is
    what lets these tests run without any external PDF renderer."""
    scale = dpi / 72.0
    w = int(PAGE_WIDTH * scale)
    h = int(PAGE_HEIGHT * scale)
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    for x_pt, y_pt in marker_positions().values():
        cx, cy = x_pt * scale, (PAGE_HEIGHT - y_pt) * scale
        half = (MARKER_SIZE / 2) * scale
        draw.rectangle([cx - half, cy - half, cx + half, cy + half], fill=(0, 0, 0))

    centres = checkbox_centres(len(page.words))
    for (x_pt, y_pt), word in zip(centres, page.words):
        cx, cy = x_pt * scale, (PAGE_HEIGHT - y_pt) * scale
        half = (CHECKBOX_SIZE / 2) * scale
        draw.rectangle([cx - half, cy - half, cx + half, cy + half], outline=(160, 160, 160), width=2)
        if word in known_words:
            r = half * 0.65
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(10, 10, 10))

    if rotation_deg:
        img = img.rotate(rotation_deg, expand=True, fillcolor=(255, 255, 255))
    return img


def render_sloppy_diagonal_scan(page, known_words, rng, dpi=DPI):
    """Simulates a human drawing a big diagonal slash through each ticked
    box's centre that overshoots well past that box's own top/bottom
    edge into the neighbouring row - the real failure mode a live scan
    exposed (see the "real scan under-detects / over-detects" bug)."""
    scale = dpi / 72.0
    w = int(PAGE_WIDTH * scale)
    h = int(PAGE_HEIGHT * scale)
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    for x_pt, y_pt in marker_positions().values():
        cx, cy = x_pt * scale, (PAGE_HEIGHT - y_pt) * scale
        half = (MARKER_SIZE / 2) * scale
        draw.rectangle([cx - half, cy - half, cx + half, cy + half], fill=(0, 0, 0))

    centres = checkbox_centres(len(page.words))
    for (x_pt, y_pt), word in zip(centres, page.words):
        cx, cy = x_pt * scale, (PAGE_HEIGHT - y_pt) * scale
        half = (CHECKBOX_SIZE / 2) * scale
        draw.rectangle([cx - half, cy - half, cx + half, cy + half], outline=(160, 160, 160), width=2)
        if word in known_words:
            overshoot = half * rng.uniform(1.4, 1.9)
            jitter = rng.uniform(-half * 0.3, half * 0.3)
            draw.line(
                [(cx - overshoot + jitter, cy - overshoot), (cx + overshoot + jitter, cy + overshoot)],
                fill=(190, 20, 130), width=max(2, int(half * 0.22)),
            )
    return img


class TestOmrToleratesSloppyHandwrittenTicks(unittest.TestCase):
    """A thin, overshooting diagonal pen slash (the real way people tick
    boxes by hand) is a very different mark from a solid synthetic blob -
    these guard against regressing the threshold/inset tuning needed to
    read real scans reliably."""

    def test_overshooting_ticks_do_not_bleed_into_neighbours(self):
        import random

        page = paginate("first100")[0]
        for seed in range(5):
            rng = random.Random(seed)
            known = {w for w in page.words if rng.random() < 0.4}
            img = render_sloppy_diagonal_scan(page, known, rng)
            result = omr.read_page(img, page)
            detected = {w for w, ticked in result.words.items() if ticked}
            self.assertEqual(detected, known, f"seed {seed}")

    def test_every_word_ticked_with_overshoot(self):
        import random

        page = paginate("first100")[0]
        rng = random.Random(42)
        known = set(page.words)
        img = render_sloppy_diagonal_scan(page, known, rng)
        result = omr.read_page(img, page)
        detected = {w for w, ticked in result.words.items() if ticked}
        self.assertEqual(detected, known)


class TestOmrReadsTicks(unittest.TestCase):
    def setUp(self):
        self.page = paginate("first100")[0]
        self.known = set(list(self.page.words)[::4])  # every 4th word ticked

    def test_straight_scan_matches_exactly(self):
        img = render_synthetic_scan(self.page, self.known)
        result = omr.read_page(img, self.page)
        detected = {w for w, ticked in result.words.items() if ticked}
        self.assertEqual(detected, self.known)

    def test_tolerates_small_rotation(self):
        img = render_synthetic_scan(self.page, self.known, rotation_deg=1.8)
        result = omr.read_page(img, self.page)
        detected = {w for w, ticked in result.words.items() if ticked}
        self.assertEqual(detected, self.known)

    def test_tolerates_different_dpi(self):
        img = render_synthetic_scan(self.page, self.known, dpi=300)
        result = omr.read_page(img, self.page)
        detected = {w for w, ticked in result.words.items() if ticked}
        self.assertEqual(detected, self.known)

    def test_no_ticks_means_nothing_detected(self):
        img = render_synthetic_scan(self.page, set())
        result = omr.read_page(img, self.page)
        detected = {w for w, ticked in result.words.items() if ticked}
        self.assertEqual(detected, set())

    def test_every_word_ticked(self):
        all_words = set(self.page.words)
        img = render_synthetic_scan(self.page, all_words)
        result = omr.read_page(img, self.page)
        detected = {w for w, ticked in result.words.items() if ticked}
        self.assertEqual(detected, all_words)


class TestOmrErrors(unittest.TestCase):
    def test_blank_page_with_no_markers_raises(self):
        img = Image.new("RGB", (1240, 1754), (255, 255, 255))
        page = paginate("first100")[0]
        with self.assertRaises(omr.OmrError):
            omr.read_page(img, page)


class TestReadChecklist(unittest.TestCase):
    def test_aggregates_known_words_across_pages(self):
        pages = paginate("first100")
        known_p1 = set(list(pages[0].words)[:5])
        known_p2 = set(list(pages[1].words)[:3])
        images = {
            1: render_synthetic_scan(pages[0], known_p1),
            2: render_synthetic_scan(pages[1], known_p2),
        }
        result = omr.read_checklist("first100", images)
        self.assertEqual(result, known_p1 | known_p2)

    def test_missing_page_is_skipped_not_an_error(self):
        pages = paginate("first100")
        known_p1 = set(list(pages[0].words)[:4])
        images = {1: render_synthetic_scan(pages[0], known_p1)}
        result = omr.read_checklist("first100", images)
        self.assertEqual(result, known_p1)


class TestLoadPdfPages(unittest.TestCase):
    def _make_pdf(self, path, n_pages=2):
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas as rl_canvas

        c = rl_canvas.Canvas(path, pagesize=A4)
        for i in range(n_pages):
            c.drawString(100, 700, f"Page {i + 1}")
            c.showPage()
        c.save()

    def test_rasterises_every_page_in_order(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/test.pdf"
            self._make_pdf(path, n_pages=3)
            images = omr.load_pdf_pages(path)
            self.assertEqual(len(images), 3)
            for img in images:
                self.assertEqual(img.mode, "L")
                self.assertGreater(img.width, 0)
                self.assertGreater(img.height, 0)

    def test_load_page_image_dispatches_pdf_by_extension(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/test.pdf"
            self._make_pdf(path, n_pages=2)
            img1 = omr.load_page_image(path, page_number=1)
            img2 = omr.load_page_image(path, page_number=2)
            self.assertEqual(img1.mode, "L")
            self.assertEqual(img2.mode, "L")

    def test_requesting_a_page_past_the_end_raises(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/test.pdf"
            self._make_pdf(path, n_pages=1)
            with self.assertRaises(omr.OmrError):
                omr.load_page_image(path, page_number=2)


if __name__ == "__main__":
    unittest.main()
