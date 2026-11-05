import unittest

from precision_worksheets import db
from precision_worksheets.games_ui import best_scores


class TestBestScores(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        self.addCleanup(self.conn.close)
        self.child_id = db.add_child(self.conn, "Alex", "Year 1", "first100", set())

    def test_empty_when_no_games_played(self):
        self.assertEqual(best_scores(self.conn, self.child_id), {})

    def test_higher_is_better_keeps_the_higher_score(self):
        db.record_game_score(self.conn, self.child_id, "flash", "01/01/2026", 4, "/min")
        db.record_game_score(self.conn, self.child_id, "flash", "08/01/2026", 7, "/min")
        db.record_game_score(self.conn, self.child_id, "flash", "15/01/2026", 5, "/min")
        best, plays = best_scores(self.conn, self.child_id)["flash"]
        self.assertEqual(best, 7)
        self.assertEqual(plays, 3)

    def test_lower_is_better_keeps_the_lower_score(self):
        db.record_game_score(self.conn, self.child_id, "memory", "01/01/2026", 9, " moves")
        db.record_game_score(self.conn, self.child_id, "memory", "08/01/2026", 6, " moves")
        db.record_game_score(self.conn, self.child_id, "memory", "15/01/2026", 8, " moves")
        best, plays = best_scores(self.conn, self.child_id)["memory"]
        self.assertEqual(best, 6)
        self.assertEqual(plays, 3)


if __name__ == "__main__":
    unittest.main()
