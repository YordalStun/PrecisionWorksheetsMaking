import os
import random
import unittest

from precision_worksheets.arcade.pirate_island import (
    CANNON,
    DIE_TOP,
    FULL_SET_BONUS,
    MAP_CARDS,
    MAX_LEVEL,
    N_SQUARES,
    QUICKSAND,
    ROUNDS_FOR_PLAYERS,
    START,
    TREASURE,
    IslandGame,
    MapCard,
    axis_angle,
    build_squares,
    die_face_up,
    hut_spots,
    mat_mul,
    pawn_spot,
    rot_y,
    square_rect,
    tex_to_world,
)

try:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication([])
    HAVE_QT = True
except Exception:  # pragma: no cover - PySide6 missing / no display libs
    HAVE_QT = False

WORDS = ["the", "said", "because", "jump", "house"]


class TestBoardLayout(unittest.TestCase):
    def setUp(self):
        self.squares = build_squares(WORDS, random.Random(1))

    def test_corners_map_squares_and_sixteen_word_squares(self):
        self.assertEqual(len(self.squares), N_SQUARES)
        kinds = {i: s.kind for i, s in enumerate(self.squares)}
        self.assertEqual(kinds[START], "start")
        self.assertEqual(kinds[TREASURE], "treasure")
        self.assertEqual(kinds[CANNON], "cannon")
        self.assertEqual(kinds[QUICKSAND], "quicksand")
        self.assertEqual([s.index for s in self.squares if s.kind == "map"], [3, 9, 15, 21])
        self.assertEqual(sum(1 for s in self.squares if s.kind == "word"), 16)

    def test_every_word_appears_about_equally_often(self):
        counts = {w: 0 for w in WORDS}
        for s in self.squares:
            if s.kind == "word":
                counts[s.word] += 1
        self.assertLessEqual(max(counts.values()) - min(counts.values()), 1)
        self.assertTrue(all(counts.values()))

    def test_both_squares_of_a_colour_set_show_different_words(self):
        groups: dict[int, list[str]] = {}
        for s in self.squares:
            if s.kind == "word":
                groups.setdefault(s.group, []).append(s.word)
        self.assertEqual(len(groups), 8)
        for words in groups.values():
            self.assertEqual(len(words), 2)
            self.assertNotEqual(words[0], words[1])

    def test_a_single_word_still_fills_the_board(self):
        squares = build_squares(["a"], random.Random(2))
        self.assertTrue(all(s.word == "a" for s in squares if s.kind == "word"))

    def test_squares_tile_the_rim_without_overlapping(self):
        rects = [square_rect(i) for i in range(N_SQUARES)]
        for r in rects:
            self.assertGreaterEqual(r.left(), 0)
            self.assertGreaterEqual(r.top(), 0)
            self.assertLessEqual(r.right(), 780)
            self.assertLessEqual(r.bottom(), 780)
        for i, a in enumerate(rects):
            for b in rects[i + 1:]:
                self.assertFalse(a.adjusted(1, 1, -1, -1).intersects(b.adjusted(1, 1, -1, -1)))

    def test_huts_and_pawns_stand_on_their_own_square(self):
        for i in range(N_SQUARES):
            r = square_rect(i)
            x0, z0 = tex_to_world(r.left(), r.top())
            x1, z1 = tex_to_world(r.right(), r.bottom())
            for x, z in hut_spots(i, 2) + [pawn_spot(i)]:
                self.assertTrue(x0 < x < x1 and z0 < z < z1, (i, x, z))


class TestRules(unittest.TestCase):
    def setUp(self):
        self.g = IslandGame(WORDS, 2, ["Lola", ""], random.Random(3))

    def first_word_square(self, group: int = 0):
        return next(s for s in self.g.squares if s.kind == "word" and s.group == group)

    def test_unnamed_players_get_a_default_name(self):
        self.assertEqual([p.name for p in self.g.players], ["Lola", "Player 2"])

    def test_sailing_past_start_earns_a_coin(self):
        self.g.player.pos = N_SQUARES - 2
        earned = [self.g.step() for _ in range(3)]
        self.assertEqual(earned, [0, 1, 0])
        self.assertEqual(self.g.player.coins, 1)
        self.assertEqual(self.g.player.pos, 1)

    def test_sliding_backwards_over_start_earns_nothing(self):
        self.g.player.pos = 1
        self.g.step(-1)
        self.g.step(-1)
        self.assertEqual(self.g.player.pos, N_SQUARES - 1)
        self.assertEqual(self.g.player.coins, 0)

    def test_reading_a_free_word_builds_a_hut(self):
        sq = self.first_word_square()
        self.g.player.pos = sq.index
        res = self.g.answer_word(True)
        self.assertEqual((res["coins"], res["built"]), (1, 1))
        self.assertEqual((sq.owner, sq.level), (0, 1))
        self.assertEqual(self.g.player.words_read, 1)

    def test_not_yet_changes_nothing(self):
        sq = self.first_word_square()
        self.g.player.pos = sq.index
        res = self.g.answer_word(False)
        self.assertEqual(res["coins"], 0)
        self.assertIsNone(sq.owner)
        self.assertEqual(self.g.player.coins, 0)

    def test_hut_grows_into_a_sandcastle_and_stops_there(self):
        sq = self.first_word_square()
        self.g.player.pos = sq.index
        built = [self.g.answer_word(True)["built"] for _ in range(MAX_LEVEL + 1)]
        self.assertEqual(built, [1, 2, 3, 0])
        self.assertEqual(sq.level, MAX_LEVEL)

    def test_landing_on_someone_elses_hut_pays_them_rent(self):
        sq = self.first_word_square()
        self.g.player.pos = sq.index
        self.g.answer_word(True)
        self.g.end_turn()
        self.g.player.pos = sq.index
        res = self.g.answer_word(True)
        self.assertEqual(res["rent_to"], 0)
        self.assertEqual(self.g.players[1].coins, 1)
        self.assertEqual(self.g.players[0].coins, 2)
        self.assertEqual(sq.owner, 0)

    def test_full_colour_set_bonus_is_paid_once(self):
        a, b = [s for s in self.g.squares if s.group == 0]
        for sq in (a, b):
            self.g.player.pos = sq.index
            res = self.g.answer_word(True)
        self.assertTrue(res["full_set"])
        self.assertEqual(self.g.player.coins, 2 + FULL_SET_BONUS)
        res = self.g.answer_word(True)
        self.assertFalse(res["full_set"])
        self.assertEqual(self.g.player.coins, 3 + FULL_SET_BONUS)

    def test_rounds_scale_with_players_and_extra_turns_do_not_count(self):
        self.assertEqual(ROUNDS_FOR_PLAYERS, {1: 12, 2: 8, 3: 6, 4: 5})
        self.assertEqual(self.g.total_turns, 16)
        self.g.end_turn(extra=True)
        self.assertEqual((self.g.turns_taken, self.g.current), (0, 0))
        for _ in range(16):
            self.assertFalse(self.g.done)
            self.g.end_turn()
        self.assertTrue(self.g.done)
        self.assertEqual(self.g.round_number, 8)

    def test_map_cards(self):
        p = self.g.player
        self.assertEqual(self.g.resolve_card(MapCard("challenge", "x", 2), ok=True), 2)
        self.assertEqual(self.g.resolve_card(MapCard("challenge", "x", 2), ok=False), 0)
        p.pos = 9
        self.assertEqual(self.g.resolve_card(MapCard("again", "x")), 0)
        self.assertEqual(p.pos, 9)
        self.assertEqual(self.g.resolve_card(MapCard("home", "x", 1)), 1)
        self.assertEqual(p.pos, START)
        self.assertEqual(p.coins, 3)

    def test_the_deck_deals_every_card_before_reshuffling(self):
        drawn = [self.g.draw_card() for _ in range(len(MAP_CARDS))]
        self.assertEqual(sorted(c.text for c, _w in drawn), sorted(c.text for c in MAP_CARDS))
        self.assertTrue(all(w in WORDS for _c, w in drawn))
        self.g.draw_card()

    def test_treasure_and_winners(self):
        self.assertEqual(self.g.treasure(), 2)
        self.assertEqual(self.g.winners(), [0])
        self.g.players[1].coins = 2
        self.assertEqual(self.g.winners(), [0, 1])


class TestDie(unittest.TestCase):
    def test_every_value_lands_face_up_whatever_way_it_faces(self):
        for value in range(1, 7):
            for yaw in (0.0, 1.0, 2.5, 4.0):
                self.assertEqual(die_face_up(mat_mul(rot_y(yaw), DIE_TOP[value])), value)

    def test_a_fully_unwound_spin_shows_the_rolled_value(self):
        final = mat_mul(rot_y(0.7), DIE_TOP[5])
        self.assertEqual(die_face_up(mat_mul(final, axis_angle((0.3, 1, -0.4), 0.0))), 5)


@unittest.skipUnless(HAVE_QT, "PySide6 not available")
class TestPirateIslandCanvas(unittest.TestCase):
    def setUp(self):
        from precision_worksheets.arcade import sound

        sound.set_enabled(False)
        self.finished = []

    def make(self, words=WORDS):
        from precision_worksheets.arcade.pirate_island import PirateIsland

        g = PirateIsland(words, on_finish=lambda score, lines, stars: self.finished.append((score, lines, stars)))
        g.resize(1000, 680)
        g._timer.stop()
        self.addCleanup(g.deleteLater)
        g.rng.seed(4)
        for _ in range(60):
            g.advance(0.05)
        self.assertEqual(g.state, "play")
        self.assertEqual(g.phase, "setup")
        return g

    def play_out(self, g, answer):
        for _ in range(30000):
            if g.state == "done":
                return
            if g.phase == "await_roll":
                g.key(Qt.Key_Space)
            elif g.phase == "word":
                g.key(answer)
            elif g.phase == "map":
                g.key(answer if g.card[0].kind == "challenge" else Qt.Key_Space)
            g.advance(0.05)
        self.fail("the game never finished")

    def test_two_player_game_plays_to_the_end_and_scores_player_one(self):
        g = self.make()
        g.player_name = "Lola"
        g.key(Qt.Key_2)
        self.assertEqual([p.name for p in g.game.players], ["Lola", "Player 2"])
        self.play_out(g, Qt.Key_Right)
        score, lines, _stars = self.finished[0]
        self.assertEqual(score, g.game.players[0].coins)
        self.assertEqual(g.game.turns_taken, g.game.total_turns)
        self.assertTrue(any(s.owner is not None for s in g.game.squares))
        self.assertTrue(any("Lola" in line for line in lines))

    def test_saying_not_yet_every_time_builds_nothing(self):
        g = self.make()
        g.key(Qt.Key_1)
        self.play_out(g, Qt.Key_Left)
        self.assertFalse(any(s.owner is not None for s in g.game.squares))
        self.assertEqual(g.game.players[0].words_read, 0)

    def test_picking_the_number_of_players_by_clicking(self):
        g = self.make()
        r = g._setup_rects()[2]
        g.click(r.center().x(), r.center().y())
        self.assertEqual(len(g.game.players), 3)
        self.assertEqual(g.phase, "await_roll")

    def test_the_die_shows_the_roll_and_the_pawn_moves_that_far(self):
        g = self.make()
        g.key(Qt.Key_1)
        g.key(Qt.Key_Space)
        while g.phase in ("rolling", "moving"):
            g.advance(0.05)
        self.assertEqual(die_face_up(g.die_rot), g.roll_value)
        self.assertEqual(g.game.player.pos, g.roll_value)

    def test_every_screen_paints(self):
        g = self.make(["caterpillar", "a"])
        self.assertFalse(g.grab().isNull())
        g.key(Qt.Key_4)
        for _ in range(400):
            if g.phase == "await_roll":
                g.key(Qt.Key_Space)
            if g.phase in ("word", "map"):
                self.assertFalse(g.grab().isNull())
                break
            g.advance(0.05)
        self.assertFalse(g.grab().isNull())


if __name__ == "__main__":
    unittest.main()
