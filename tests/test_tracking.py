import random
import unittest

from precision_worksheets.tracking import (
    MASTERY_STREAK,
    STATUS_KNOWN,
    STATUS_LEARNING,
    WordState,
    apply_result,
    pick_known_words,
    pick_practice_words,
)


class TestApplyResult(unittest.TestCase):
    def test_three_correct_in_a_row_marks_known(self):
        state = WordState("cat", STATUS_LEARNING, 0, 0, 0)
        for _ in range(MASTERY_STREAK):
            state = apply_result(state, True)
        self.assertEqual(state.status, STATUS_KNOWN)
        self.assertEqual(state.correct_streak, MASTERY_STREAK)

    def test_two_correct_then_wrong_stays_learning(self):
        state = WordState("cat", STATUS_LEARNING, 0, 0, 0)
        state = apply_result(state, True)
        state = apply_result(state, True)
        state = apply_result(state, False)
        self.assertEqual(state.status, STATUS_LEARNING)
        self.assertEqual(state.correct_streak, 0)

    def test_known_word_gotten_wrong_drops_back_to_learning(self):
        state = WordState("cat", STATUS_KNOWN, MASTERY_STREAK, 10, 9)
        state = apply_result(state, False)
        self.assertEqual(state.status, STATUS_LEARNING)
        self.assertEqual(state.correct_streak, 0)

    def test_times_seen_and_correct_accumulate(self):
        state = WordState("cat", STATUS_LEARNING, 0, 2, 1)
        state = apply_result(state, True)
        self.assertEqual(state.times_seen, 3)
        self.assertEqual(state.times_correct, 2)
        state = apply_result(state, False)
        self.assertEqual(state.times_seen, 4)
        self.assertEqual(state.times_correct, 2)


class TestPickPracticeWords(unittest.TestCase):
    def test_in_progress_words_come_before_fresh_ones(self):
        words = [
            WordState("a", STATUS_LEARNING, 0, 0, 0),  # fresh
            WordState("b", STATUS_LEARNING, 1, 2, 1),  # in progress (struggling)
            WordState("c", STATUS_LEARNING, 0, 0, 0),  # fresh
        ]
        picks = pick_practice_words(words, num_words=2)
        self.assertEqual(picks[0], "b")
        self.assertEqual(len(picks), 2)

    def test_fresh_words_introduced_in_tier_order(self):
        words = [
            WordState("the", STATUS_LEARNING, 0, 0, 0),
            WordState("and", STATUS_LEARNING, 0, 0, 0),
            WordState("a", STATUS_LEARNING, 0, 0, 0),
        ]
        picks = pick_practice_words(words, num_words=3)
        self.assertEqual(picks, ["the", "and", "a"])

    def test_returns_fewer_than_requested_if_pool_is_small(self):
        words = [WordState("the", STATUS_LEARNING, 0, 0, 0)]
        picks = pick_practice_words(words, num_words=3)
        self.assertEqual(picks, ["the"])

    def test_empty_pool_returns_empty_list(self):
        self.assertEqual(pick_practice_words([], num_words=3), [])


class TestPickKnownWords(unittest.TestCase):
    def test_picks_requested_count_from_a_larger_pool(self):
        rng = random.Random(1)
        picks = pick_known_words(["a", "b", "c", "d", "e"], rng, num_words=2)
        self.assertEqual(len(picks), 2)
        self.assertEqual(len(set(picks)), 2)
        for w in picks:
            self.assertIn(w, ["a", "b", "c", "d", "e"])

    def test_returns_everything_if_pool_is_smaller_than_requested(self):
        rng = random.Random(1)
        picks = pick_known_words(["a"], rng, num_words=2)
        self.assertEqual(picks, ["a"])

    def test_empty_pool_returns_empty_list(self):
        rng = random.Random(1)
        self.assertEqual(pick_known_words([], rng, num_words=2), [])


if __name__ == "__main__":
    unittest.main()
