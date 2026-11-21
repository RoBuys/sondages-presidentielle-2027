import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import update_polls as up  # noqa: E402


class ParserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        html = (Path(__file__).parent / "fixture.html").read_text(encoding="utf-8")
        cls.rows, cls.stats = up.parse_html(html, 2025)

    def get(self, poll, scenario, cand):
        for r in self.rows:
            if r["poll_id"] == poll and r["scenario"] == scenario and r["candidate"] == cand:
                return r
        return None

    def test_counts(self):
        self.assertEqual(self.stats["tables"], 1)  # 2024 et 2e tour ignorés
        self.assertEqual(self.stats["polls"], 3)
        self.assertEqual(self.stats["scenarios"], 6)
        self.assertEqual(self.stats["skipped_rows"], 1)  # ligne irrégulière ignorée

    def test_rowspan_meta_carried(self):
        r = self.get("2026-09-29-ifop-1", 3, "Le Pen")
        self.assertEqual((r["pollster"], r["date"], r["sample"], r["value"]), ("Ifop", "2026-09-29", 1527, 36.0))

    def test_decimal_comma_and_missing(self):
        self.assertEqual(self.get("2026-09-29-ifop-1", 1, "Roussel")["value"], 2.5)
        self.assertIsNone(self.get("2026-09-29-ifop-1", 2, "Attal"))

    def test_name_in_cell(self):
        self.assertEqual(self.get("2026-09-29-ifop-1", 3, "Faure")["value"], 4.0)
        self.assertIsNone(self.get("2026-09-29-ifop-1", 3, "Glucksmann"))

    def test_autres_split_and_lt(self):
        p = "2026-10-02-opinionway-1"
        self.assertEqual(self.get(p, 1, "Bouamrane")["value"], 0.5)
        self.assertEqual(self.get(p, 1, "Lisnard")["value"], 2.0)
        self.assertEqual(self.get("2026-10-03-harris-1", 1, "Riner")["value"], 1.0)
        self.assertEqual(self.get("2026-10-03-harris-1", 1, "Villepin")["value"], 2.0)

    def test_pollster_normalised_and_dates(self):
        self.assertTrue(any(r["pollster"] == "OpinionWay" for r in self.rows))
        self.assertEqual(up.end_date("1er-3 octobre", 2026), "2026-10-03")
        self.assertEqual(up.end_date("28 novembre-1er décembre", 2026), "2026-12-01")
        self.assertEqual(up.end_date("12-17 novembre", 2026), "2026-11-17")


if __name__ == "__main__":
    unittest.main()
