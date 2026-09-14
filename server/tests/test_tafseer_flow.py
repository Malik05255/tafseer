import unittest

from app.models import Answer
from app.service import TafseerService


class TafseerFlowTests(unittest.TestCase):
    def test_answer_preserves_question_text(self):
        answer = Answer(
            question_id="person_alive",
            question_text="هل الشخص الذي رأيته حي أم متوفى؟",
            value="حي",
        )
        payload = answer.model_dump()
        self.assertEqual(payload["question_text"], "هل الشخص الذي رأيته حي أم متوفى؟")
        self.assertEqual(payload["value"], "حي")

    def test_duplicate_question_id_is_rejected(self):
        decision = {
            "need_question": True,
            "question": {
                "id": "person_alive",
                "title": "هل الشخص حي أم متوفى؟",
                "explanation": "قد يغيّر ذلك فهم المشهد.",
                "options": [
                    {"id": "alive", "label": "حي"},
                    {"id": "dead", "label": "متوفى"},
                ],
                "allow_text": False,
                "text_hint": "",
            },
        }
        question = TafseerService._question_from_decision(decision, {"person_alive"})
        self.assertIsNone(question)

    def test_semantically_repeated_question_is_rejected(self):
        old = TafseerService._normalize_question_text("هل الشخص حي أم متوفى؟")
        decision = {
            "need_question": True,
            "question": {
                "id": "person_status_again",
                "title": "هل الشخص الذي رأيته حي أم متوفى؟",
                "explanation": "قد يغيّر ذلك فهم المشهد.",
                "options": [],
                "allow_text": True,
                "text_hint": "اكتب الإجابة",
            },
        }
        question = TafseerService._question_from_decision(
            decision,
            set(),
            {old},
        )
        self.assertIsNone(question)

    def test_new_context_question_is_accepted(self):
        old = TafseerService._normalize_question_text("هل الشخص حي أم متوفى؟")
        decision = {
            "need_question": True,
            "question": {
                "id": "emotion_scene",
                "title": "ما شعورك أثناء المشهد؟",
                "explanation": "الشعور قد يغيّر معنى الحدث.",
                "options": [],
                "allow_text": True,
                "text_hint": "اكتب شعورك",
            },
        }
        question = TafseerService._question_from_decision(decision, set(), {old})
        self.assertIsNotNone(question)

    def test_missing_context_triggers_recovery(self):
        critique = {
            "preferred": "لا يوجد ترجيح كافٍ",
            "confidence": "low",
            "missing_context": ["علاقة الرائي بالشخص المذكور"],
        }
        self.assertTrue(TafseerService._critique_needs_context(critique, {}))

    def test_required_assumption_triggers_recovery(self):
        draft = {
            "candidates": [
                {
                    "support_fact_ids": ["F1"],
                    "required_assumptions": ["أن الرائي يعمل في مجال معين"],
                }
            ]
        }
        self.assertTrue(TafseerService._critique_needs_context({}, draft))

    def test_grounding_rejects_unknown_fact_ids(self):
        raw = {
            "grounding": [
                {"claim": "ادعاء", "fact_ids": ["F99"]},
            ]
        }
        self.assertFalse(TafseerService._python_grounding_ok(raw, {"F1", "F2"}))

    def test_grounding_accepts_known_fact_ids(self):
        raw = {
            "grounding": [
                {"claim": "ادعاء", "fact_ids": ["F1"]},
            ]
        }
        self.assertTrue(TafseerService._python_grounding_ok(raw, {"F1", "F2"}))


if __name__ == "__main__":
    unittest.main()
