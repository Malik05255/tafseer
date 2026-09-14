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
        question = TafseerService._question_from_decision(decision, set(), {old})
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

    def test_bundled_question_is_rejected(self):
        decision = {
            "need_question": True,
            "question": {
                "id": "two_axes",
                "title": "هل الجد حي أم متوفى؟ وهل حفل الاعتزال مرتبط بواقعك؟",
                "explanation": "السياق مهم.",
                "options": [],
                "allow_text": True,
                "text_hint": "اكتب الإجابة",
            },
        }
        question = TafseerService._question_from_decision(decision, set())
        self.assertIsNone(question)

    def test_explicit_deceased_fact_prevents_status_question(self):
        decision = {
            "need_question": True,
            "question": {
                "id": "grandfather_status",
                "title": "هل الجد حسن حي أم متوفى؟",
                "explanation": "حالة الشخص قد تؤثر.",
                "options": [
                    {"id": "alive", "label": "حي"},
                    {"id": "dead", "label": "متوفى"},
                ],
                "allow_text": False,
                "text_hint": "",
            },
        }
        dream = "رأيت في المنام المرحوم جدي حسن حاضرًا في الحفل."
        question = TafseerService._question_from_decision(decision, set(), dream=dream)
        self.assertIsNone(question)

    def test_complex_narrative_requires_reality_and_emotion_axes(self):
        dream = (
            "كان الشباب فريق السحاب بيسوون لي حفل اعتزال وفيه عشاء وناس جابوا ذبايح، "
            "ومن ضمنهم المرحوم جدي حسن معه كبش لكنه متردد يعطينا بسبب الملعب، ثم وافق."
        )
        self.assertEqual(TafseerService._recommended_min_questions(dream), 2)
        self.assertEqual(TafseerService._mandatory_axes(dream), ["reality_link", "emotion"])

    def test_short_simple_dream_does_not_force_two_axes(self):
        dream = "رأيت بابًا مفتوحًا وشعرت بالراحة."
        self.assertLess(TafseerService._recommended_min_questions(dream), 2)
        self.assertNotIn("emotion", TafseerService._mandatory_axes(dream))

    def test_interview_question_is_bound_to_single_axis(self):
        interview = {
            "ready": False,
            "question": {
                "axis": "reality_link",
                "title": "هل حفل الاعتزال مرتبط بواقعك الحالي؟",
                "explanation": "لفهم صلته بواقعك.",
                "options": [],
                "allow_text": True,
                "text_hint": "وضح باختصار",
            },
        }
        question = TafseerService._question_from_interview(
            interview,
            set(),
            set(),
            set(),
            "رأيت حفل اعتزال.",
            required_axis="reality_link",
        )
        self.assertIsNotNone(question)
        self.assertEqual(question.id, "ctx_reality_link")

    def test_interviewer_cannot_swap_required_axis(self):
        interview = {
            "ready": False,
            "question": {
                "axis": "emotion",
                "title": "ما شعورك؟",
                "explanation": "مهم.",
                "options": [],
                "allow_text": True,
                "text_hint": "",
            },
        }
        question = TafseerService._question_from_interview(
            interview,
            set(),
            set(),
            set(),
            "رأيت حفل اعتزال.",
            required_axis="reality_link",
        )
        self.assertIsNone(question)

    def test_answered_axes_are_tracked_from_question_ids(self):
        answers = [
            {
                "question_id": "ctx_reality_link",
                "question_text": "هل له صلة بواقعك؟",
                "value": "نعم",
            },
            {
                "question_id": "ctx_emotion",
                "question_text": "ما شعورك؟",
                "value": "كنت مستغربًا",
            },
        ]
        self.assertEqual(TafseerService._answered_axes(answers), {"reality_link", "emotion"})

    def test_daily_thoughts_requires_positive_reality_support(self):
        no_answers = [
            {
                "question_id": "ctx_reality_link",
                "question_text": "هل المشهد مرتبط بواقعك؟",
                "value": "لا، لا علاقة مباشرة ولا يشغلني",
            }
        ]
        yes_answers = [
            {
                "question_id": "ctx_reality_link",
                "question_text": "هل المشهد مرتبط بواقعك؟",
                "value": "نعم، هذا الموضوع يشغلني هذه الفترة",
            }
        ]
        self.assertFalse(TafseerService._positive_reality_support(no_answers))
        self.assertTrue(TafseerService._positive_reality_support(yes_answers))

    def test_generic_evidence_without_mapping_is_rejected(self):
        result = {
            "evidence": [
                {
                    "title": "حفل الاعتزال",
                    "explanation": "هذه قرينة مهمة في المنام.",
                }
            ]
        }
        self.assertFalse(TafseerService._evidence_explains_mapping(result))

    def test_explanatory_evidence_mapping_is_accepted(self):
        result = {
            "evidence": [
                {
                    "title": "من الرؤيا: تردد الجد ثم موافقته",
                    "explanation": (
                        "المعنى المرجح: انتقال من المنع إلى القبول.\n"
                        "لماذا هذا الربط: لأن التحول وقع داخل المشهد نفسه وكان نهايته.\n"
                        "نوع السند: سياق الرؤيا"
                    ),
                }
            ]
        }
        self.assertTrue(TafseerService._evidence_explains_mapping(result))

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
        raw = {"grounding": [{"claim": "ادعاء", "fact_ids": ["F99"]}]}
        self.assertFalse(TafseerService._python_grounding_ok(raw, {"F1", "F2"}))

    def test_grounding_accepts_known_fact_ids(self):
        raw = {"grounding": [{"claim": "ادعاء", "fact_ids": ["F1"]}]}
        self.assertTrue(TafseerService._python_grounding_ok(raw, {"F1", "F2"}))


if __name__ == "__main__":
    unittest.main()
