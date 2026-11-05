import random
import unittest

from precision_worksheets import db
from precision_worksheets.data.word_lists import FIRST_100, NEXT_200, TIERS
from precision_worksheets.tracking import STATUS_KNOWN, STATUS_LEARNING


class TestDbBase(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        self.addCleanup(self.conn.close)


class TestAddChild(TestDbBase):
    def test_known_words_are_seeded_as_known_rest_as_learning(self):
        known = set(FIRST_100[:10])
        child_id = db.add_child(self.conn, "Alex", "Year 1", "first100", known)
        states = db.get_word_states(self.conn, child_id, "first100")
        self.assertEqual(len(states), len(FIRST_100))
        known_in_db = {s.word for s in states if s.status == STATUS_KNOWN}
        self.assertEqual(known_in_db, known)
        for s in states:
            if s.word in known:
                self.assertEqual(s.correct_streak, 3)
            else:
                self.assertEqual(s.status, STATUS_LEARNING)
                self.assertEqual(s.times_seen, 0)

    def test_rejects_blank_name(self):
        with self.assertRaises(ValueError):
            db.add_child(self.conn, "   ", "Year 1", "first100", set())

    def test_rejects_unknown_tier(self):
        with self.assertRaises(ValueError):
            db.add_child(self.conn, "Alex", "Year 1", "not_a_tier", set())

    def test_list_children_sorted_by_name(self):
        db.add_child(self.conn, "Zoe", "Year 2", "first100", set())
        db.add_child(self.conn, "Amir", "Year 2", "first100", set())
        names = [c["name"] for c in db.list_children(self.conn)]
        self.assertEqual(names, ["Amir", "Zoe"])


class TestWordSelection(TestDbBase):
    def test_choose_session_words_returns_five_words(self):
        known = set(FIRST_100[:20])
        child_id = db.add_child(self.conn, "Alex", "Year 1", "first100", known)
        words = db.choose_session_words(self.conn, child_id, rng=random.Random(1))
        self.assertEqual(len(words), 5)
        self.assertEqual(len(set(words)), 5)

    def test_practice_words_are_next_in_tier_order_when_nothing_in_progress(self):
        child_id = db.add_child(self.conn, "Alex", "Year 1", "first100", set())
        words = db.choose_session_words(self.conn, child_id, rng=random.Random(1))
        practice = [w for w in words if w in FIRST_100[:3]]
        self.assertEqual(set(practice), set(FIRST_100[:3]))

    def test_known_words_from_earlier_tiers_are_available_for_the_known_slot(self):
        child_id = db.add_child(self.conn, "Alex", "Year 1", "next200", set())
        known_pool = db.all_known_words(self.conn, child_id, "next200")
        self.assertEqual(set(known_pool[: len(FIRST_100)]), set(FIRST_100))

    def test_last_sheet_words_round_trip(self):
        child_id = db.add_child(self.conn, "Alex", "Year 1", "first100", set())
        self.assertIsNone(db.get_last_sheet_words(self.conn, child_id))
        words = ["the", "and", "a", "to", "said"]
        db.set_last_sheet(self.conn, child_id, words, "01/01/2026")
        self.assertEqual(db.get_last_sheet_words(self.conn, child_id), words)
        child = db.get_child(self.conn, child_id)
        self.assertEqual(child["last_sheet_date"], "01/01/2026")


class TestRecordSession(TestDbBase):
    def test_three_correct_sessions_marks_word_known(self):
        child_id = db.add_child(self.conn, "Alex", "Year 1", "first100", set())
        word = FIRST_100[0]
        for _ in range(3):
            db.record_session(self.conn, child_id, "01/01/2026", [(word, True)])
        states = {s.word: s for s in db.get_word_states(self.conn, child_id, "first100")}
        self.assertEqual(states[word].status, STATUS_KNOWN)

    def test_a_miss_after_mastery_drops_word_back_to_learning(self):
        child_id = db.add_child(self.conn, "Alex", "Year 1", "first100", set())
        word = FIRST_100[0]
        for _ in range(3):
            db.record_session(self.conn, child_id, "01/01/2026", [(word, True)])
        db.record_session(self.conn, child_id, "08/01/2026", [(word, False)])
        states = {s.word: s for s in db.get_word_states(self.conn, child_id, "first100")}
        self.assertEqual(states[word].status, STATUS_LEARNING)
        self.assertEqual(states[word].correct_streak, 0)

    def test_session_stores_time_and_counts(self):
        child_id = db.add_child(self.conn, "Alex", "Year 1", "first100", set())
        db.record_session(
            self.conn, child_id, "01/01/2026", [(FIRST_100[0], True)],
            time_seconds=58, correct_count=4, error_count=1, notes="good focus",
        )
        sessions = db.get_sessions(self.conn, child_id)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["time_seconds"], 58)
        self.assertEqual(sessions[0]["correct_count"], 4)
        self.assertEqual(sessions[0]["error_count"], 1)
        self.assertEqual(sessions[0]["notes"], "good focus")

    def test_session_words_are_retrievable(self):
        child_id = db.add_child(self.conn, "Alex", "Year 1", "first100", set())
        session_id = db.record_session(
            self.conn, child_id, "01/01/2026",
            [(FIRST_100[0], True), (FIRST_100[1], False)],
        )
        words = {r["word"]: r["correct"] for r in db.get_session_words(self.conn, session_id)}
        self.assertEqual(words[FIRST_100[0]], 1)
        self.assertEqual(words[FIRST_100[1]], 0)

    def test_mastering_every_word_advances_to_the_next_tier(self):
        # Seed every word as already known except the last one.
        known = set(FIRST_100[:-1])
        child_id = db.add_child(self.conn, "Alex", "Year 1", "first100", known)
        last_word = FIRST_100[-1]
        for _ in range(3):
            db.record_session(self.conn, child_id, "01/01/2026", [(last_word, True)])
        child = db.get_child(self.conn, child_id)
        self.assertEqual(child["current_tier"], "next200")
        states = db.get_word_states(self.conn, child_id, "next200")
        self.assertEqual(len(states), len(NEXT_200))
        self.assertTrue(all(s.status == STATUS_LEARNING for s in states))

    def test_does_not_advance_past_the_final_tier(self):
        last_tier = TIERS[-1]
        known = set(last_tier.words[:-1])
        child_id = db.add_child(self.conn, "Alex", "Year 6", last_tier.key, known)
        last_word = last_tier.words[-1]
        for _ in range(3):
            db.record_session(self.conn, child_id, "01/01/2026", [(last_word, True)])
        child = db.get_child(self.conn, child_id)
        self.assertEqual(child["current_tier"], last_tier.key)


class TestDeleteAndRename(TestDbBase):
    def test_delete_child_removes_their_data(self):
        child_id = db.add_child(self.conn, "Alex", "Year 1", "first100", set())
        db.record_session(self.conn, child_id, "01/01/2026", [(FIRST_100[0], True)])
        db.delete_child(self.conn, child_id)
        self.assertIsNone(db.get_child(self.conn, child_id))
        self.assertEqual(db.get_word_states(self.conn, child_id, "first100"), [])

    def test_rename_child(self):
        child_id = db.add_child(self.conn, "Alex", "Year 1", "first100", set())
        db.rename_child(self.conn, child_id, "Alexandra", "Year 2")
        child = db.get_child(self.conn, child_id)
        self.assertEqual(child["name"], "Alexandra")
        self.assertEqual(child["year_group"], "Year 2")


if __name__ == "__main__":
    unittest.main()
