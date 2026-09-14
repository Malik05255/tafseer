import unittest

from app.scripture_service import TafseerService
from app.scripture_sources import ScriptureRetriever, _grade_class, _keywords


class ScriptureSourceTests(unittest.TestCase):
    def test_keywords_remove_common_dream_words(self):
        words = _keywords("رأيت في المنام بابا كبيرا ولبنا أبيض ثم دخلت البيت")
        self.assertIn("بابا", words)
        self.assertIn("لبنا", words)
        self.assertNotIn("المنام", words)

    def test_grade_classification(self):
        self.assertEqual(_grade_class("إسناده صحيح"), "accepted")
        self.assertEqual(_grade_class("حسن وله شواهد"), "accepted")
        self.assertEqual(_grade_class("حديث ضعيف"), "weak")
        self.assertEqual(_grade_class("لا يصح من قبل إسناده"), "weak")

    def test_dorar_parser_preserves_grading(self):
        raw = """
        1 - مثال حديث للاختبار.</div>
        الراوي:</span> أبو هريرة</span>
        المحدث:</span> الألباني
        المصدر:</span> صحيح الجامع
        الصفحة أو الرقم:</span> 123
        خلاصة حكم المحدث:</span> صحيح</span>
        </div>
        --------------
        """
        rows = ScriptureRetriever._parse_dorar(raw)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["grade_class"], "accepted")
        self.assertEqual(rows[0]["source_type"], "hadith_accepted")
        self.assertIn("أبو هريرة", rows[0]["notes"])

    def test_weak_hadith_cannot_be_displayed_as_evidence(self):
        knowledge = [
            {
                "source_title": "كتاب ما",
                "source_ref": "كتاب ما — 1",
                "source_type": "hadith_weak",
                "grade_class": "weak",
                "grade": "ضعيف",
            }
        ]
        raw_refs = [
            {
                "claim": "معنى",
                "source_title": "كتاب ما",
                "source_ref": "كتاب ما — 1",
                "relation": "direct",
                "explanation": "شرح",
            }
        ]
        self.assertEqual(TafseerService._sanitize_references(raw_refs, knowledge), [])

    def test_generic_quran_match_is_downgraded_to_semantic(self):
        knowledge = [
            {
                "source_title": "القرآن الكريم",
                "source_ref": "القرآن 35:2",
                "source_type": "quran",
                "grade_class": "quran",
                "grade": "قرآن",
            }
        ]
        raw_refs = [
            {
                "claim": "الفتح قد يستأنس به لمعنى الرحمة",
                "source_title": "القرآن الكريم",
                "source_ref": "القرآن 35:2",
                "relation": "direct",
                "explanation": "استئناس لغوي وسياقي فقط",
            }
        ]
        refs = TafseerService._sanitize_references(raw_refs, knowledge)
        self.assertEqual(refs[0]["relation"], "semantic")


if __name__ == "__main__":
    unittest.main()
