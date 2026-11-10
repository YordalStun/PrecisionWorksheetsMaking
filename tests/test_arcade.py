"""Plays every Word Arcade game to the end, headlessly, through the same
clicks/keys a child would use, and checks scores are sensible and saved."""

import math
import os
import unittest

try:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication([])
    HAVE_QT = True
except Exception:  # pragma: no cover - PySide6 missing / no display libs
    HAVE_QT = False

WORDS = ["the", "said", "because", "jump", "house"]


def _bubble_x(g, b):
    return b["x"] + math.sin(g.t * 1.6 + b["ph"]) * 14


@unittest.skipUnless(HAVE_QT, "PySide6 not available")
class TestArcadeGames(unittest.TestCase):
    def setUp(self):
        from precision_worksheets.arcade import sound

        sound.set_enabled(False)
        self.finished = []

    def make(self, key, words=WORDS):
        from precision_worksheets.arcade.games import GAME_CLASSES

        g = GAME_CLASSES[key](words, on_finish=lambda score, lines, stars: self.finished.append((score, lines, stars)))
        g.resize(1000, 680)
        g._timer.stop()
        self.addCleanup(g.deleteLater)
        for _ in range(60):  # through the 3-2-1 countdown
            g.advance(0.05)
        self.assertEqual(g.state, "play")
        return g

    def run_until_done(self, g, step, limit=4000):
        for _ in range(limit):
            if g.state == "done":
                return
            step()
            g.advance(0.05)
        self.fail(f"{g.key_name} never finished")

    def test_rocket_blitz_counts_reads_until_time_runs_out(self):
        g = self.make("flash")
        for _ in range(12):
            g.key(Qt.Key_Right)
        g.key(Qt.Key_Left)
        self.run_until_done(g, lambda: None)
        score, _lines, stars = self.finished[0]
        self.assertEqual(score, 12)
        self.assertEqual(stars, 1)

    def test_bubble_pop_perfect_game(self):
        g = self.make("pop")

        def step():
            for b in g.bubbles:
                if b["word"] == g.target and not b["popped"] and 80 < b["y"] < 660:
                    g.click(_bubble_x(g, b), b["y"])
                    return

        self.run_until_done(g, step)
        self.assertEqual(self.finished[0][0], g.ROUNDS)
        self.assertEqual(self.finished[0][2], 3)

    def test_memory_match_perfect_game(self):
        g = self.make("memory")
        seen = {}
        for c in g.cards:
            seen.setdefault(c["word"], []).append(c)
        for pair in seen.values():
            for c in pair:
                r = c["rect"]
                g.click(r.center().x(), r.center().y())
        self.assertEqual(g.state, "done")
        self.assertEqual(self.finished[0][0], len(WORDS))
        self.assertEqual(self.finished[0][2], 3)

    def test_memory_mismatch_flips_back(self):
        g = self.make("memory")
        a = g.cards[0]
        b = next(c for c in g.cards if c["word"] != a["word"])
        for c in (a, b):
            g.click(c["rect"].center().x(), c["rect"].center().y())
        self.assertTrue(a["up"] and b["up"])
        for _ in range(30):
            g.advance(0.05)
        self.assertFalse(a["up"] or b["up"])
        self.assertEqual(g.moves, 1)

    def test_peekaboo_owl(self):
        g = self.make("peek")

        def step():
            if g.phase == "hidden":
                g.key(Qt.Key_Space)
            elif g.phase == "reveal":
                g.key(Qt.Key_Right)

        self.run_until_done(g, step)
        self.assertEqual(self.finished[0][0], g.ROUNDS)

    def test_letter_train_no_oops(self):
        g = self.make("scramble")

        def step():
            if g.phase == "load":
                need = g.letters[g.pos].lower()
                b = next(b for b in g.balloons if b["fly"] is None and b["ch"].lower() == need)
                g.click(b["x"] + math.sin(g.t * 2 + b["ph"]) * 6, b["y"] + math.sin(g.t * 1.7 + b["ph"]) * 8)
            elif g.phase == "say" and g.buttons:
                g.key(Qt.Key_Space)

        self.run_until_done(g, step)
        self.assertEqual(self.finished[0][0], 0)
        self.assertEqual(self.finished[0][2], 3)

    def test_letter_train_counts_wrong_letters(self):
        g = self.make("scramble", ["dog"])
        while g.phase != "load":
            g.advance(0.05)
        wrong = next(b for b in g.balloons if b["ch"] != g.letters[0])
        g.click(wrong["x"] + math.sin(g.t * 2 + wrong["ph"]) * 6, wrong["y"] + math.sin(g.t * 1.7 + wrong["ph"]) * 8)
        self.assertEqual(g.oops, 1)

    def test_whack_a_word_only_counts_the_target(self):
        g = self.make("whack")

        def step():
            for i, m in enumerate(g.moles):
                if m and m["bonked"] is None and g._height(m) > 0.9:
                    hx, hy = g.HOLES[i]
                    if m["word"] == g.target:
                        g.click(hx, hy - 60)
                    return

        self.run_until_done(g, step)
        self.assertGreater(g.hits, 5)
        self.assertEqual(g.misses, 0)
        self.assertEqual(self.finished[0][0], g.hits)

    def test_word_catcher_basket_follows_target_apples(self):
        g = self.make("catch")

        def step():
            targets = [it for it in g.items if it["word"] == g.target]
            if targets:
                lowest = max(targets, key=lambda it: it["y"])
                g.hover_move(lowest["x"], 600)

        self.run_until_done(g, step)
        self.assertGreater(g.caught, 3)
        self.assertEqual(self.finished[0][0], g.caught)

    def test_every_game_paints_and_handles_one_long_word(self):
        from precision_worksheets.arcade.games import GAME_CLASSES

        for key in GAME_CLASSES:
            g = self.make(key, ["caterpillar", "a"])
            for _ in range(20):
                g.advance(0.05)
            img = g.grab()
            self.assertFalse(img.isNull(), key)

    def test_results_say_new_best(self):
        g = self.make("memory")
        g.previous_best = 50
        g.finish(9, ["x"])
        self.assertIn("New best score!", g.result_lines)


@unittest.skipUnless(HAVE_QT, "PySide6 not available")
class TestArcadeWindow(unittest.TestCase):
    def test_play_records_score_and_returns_to_hub(self):
        from precision_worksheets import db
        from precision_worksheets.arcade import sound
        from precision_worksheets.arcade.arcade import ArcadeWindow
        from precision_worksheets.games_ui import best_scores

        sound.set_enabled(False)
        conn = db.connect(":memory:")
        self.addCleanup(conn.close)
        cid = db.add_child(conn, "Alex", "Year 1", "first100", set())
        win = ArcadeWindow(None, conn, cid, "Alex", WORDS)
        self.addCleanup(win.deleteLater)
        win.play("whack")
        win.game.finish(7, ["done"])
        self.assertEqual(best_scores(conn, cid)["whack"], (7, 1))
        win.show_hub()
        self.assertIs(win.stack.currentWidget(), win.hub)
        win.play("surprise")
        self.assertIsNotNone(win.game)


if __name__ == "__main__":
    unittest.main()
