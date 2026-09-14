import json
import logging
import re

from pydantic import ValidationError

from .compact_prompts import SYSTEM_PROMPT, TURN_PROMPT
from .config import settings
from .knowledge import KnowledgeStore
from .models import FinalResult, InterpretRequest, InterpretResponse, Question
from .providers import ModelRouter, ProviderUnavailable


logger = logging.getLogger("tafseer.compact_service")
_ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
_WORDS = re.compile(r"[\w\u0600-\u06FF]{2,}")
_STATUS_QUESTION_WORDS = {
    "هل", "الشخص", "الذي", "رايته", "رأيته", "حي", "حيا", "متوفي", "متوفى",
    "ميت", "ام", "أم", "كان", "هو", "هي", "حاله", "حالة", "الان", "الآن",
}
_DECEASED_MARKERS = {"المرحوم", "مرحوم", "المتوفي", "متوفي", "المتوفى", "متوفى", "توفي", "ميت"}


class AnalysisTechnicalFailure(RuntimeError):
    pass


class TafseerService:
    """Compact conversational tafseer flow.

    Each user turn uses one model request in the normal path. The model either asks
    one useful context question or returns the final structured result. This keeps
    free-tier RPM usage low while preserving contextual questioning.
    """

    def __init__(self) -> None:
        self.models = ModelRouter()
        self.knowledge = KnowledgeStore()

    async def interpret_step(self, request: InterpretRequest) -> InterpretResponse:
        dream = request.dream.strip()
        answers = [a.model_dump() for a in request.answers]
        answered_ids = {str(a.get("question_id", "")).strip() for a in answers}
        answered_question_texts = {
            self._normalize_question_text(str(a.get("question_text", "")))
            for a in answers
            if str(a.get("question_text", "")).strip()
        }
        can_ask = len(answers) < settings.max_questions

        try:
            knowledge = self.knowledge.retrieve(dream, limit=10)
            prompt = TURN_PROMPT + "\n\n" + self._context(dream, answers, knowledge)
            if not can_ask:
                prompt += (
                    "\n\nبلغت المحادثة الحد الأقصى للأسئلة. ممنوع طرح سؤال جديد. "
                    "أخرج action=complete واختر طبيعة المنام الأقرب واشرح السبب دون استخدام غير محسوم."
                )

            decision = await self.models.generate_json(SYSTEM_PROMPT, prompt)
            action = str(decision.get("action", "")).strip().lower()

            if action == "question" and can_ask:
                question = self._question_from_decision(
                    {"need_question": True, "question": decision.get("question")},
                    answered_ids,
                    answered_question_texts,
                    dream=dream,
                )
                if question is not None:
                    return InterpretResponse(
                        status="question",
                        progress_checkpoint=min(86, 38 + len(answers) * 10),
                        question=question,
                    )

                repair_prompt = (
                    prompt
                    + "\n\nالسؤال الذي اقترحته مكرر أو مركب أو يسأل عن معلومة مذكورة أصلًا. "
                    "اسأل سؤالًا واحدًا ذريًا عن مجهول واحد فقط، ولا تسأل عما حُسم في نص المنام. "
                    "إن لم يبق سؤال مؤثر صالح فأخرج action=complete."
                )
                decision = await self.models.generate_json(SYSTEM_PROMPT, repair_prompt)
                if str(decision.get("action", "")).strip().lower() == "question":
                    question = self._question_from_decision(
                        {"need_question": True, "question": decision.get("question")},
                        answered_ids,
                        answered_question_texts,
                        dream=dream,
                    )
                    if question is not None:
                        return InterpretResponse(
                            status="question",
                            progress_checkpoint=min(90, 44 + len(answers) * 10),
                            question=question,
                        )

            raw_result = decision.get("result")
            if not isinstance(raw_result, dict):
                raise AnalysisTechnicalFailure("turn_result_missing")

            clean = self._sanitize_result(raw_result, knowledge)
            try:
                result = FinalResult.model_validate(clean)
            except ValidationError as exc:
                raise AnalysisTechnicalFailure("turn_result_schema") from exc

            return InterpretResponse(status="complete", progress_checkpoint=100, result=result)

        except ProviderUnavailable:
            logger.warning("analysis_technical_failure stage=provider_unavailable")
            return InterpretResponse(
                status="error",
                progress_checkpoint=92,
                error_code="provider_unavailable",
                message="الخدمة تحت ضغط الآن. احتفظنا بنص المنام ويمكنك إعادة المحاولة بعد قليل.",
            )
        except AnalysisTechnicalFailure as exc:
            logger.warning("analysis_technical_failure stage=%s", str(exc)[:80])
            return InterpretResponse(
                status="error",
                progress_checkpoint=92,
                error_code="analysis_pipeline_failed",
                message="تعذر إكمال التحليل في هذه المحاولة. احتفظنا بنص المنام.",
            )
        except Exception as exc:
            logger.exception("analysis_unexpected_failure type=%s", type(exc).__name__)
            return InterpretResponse(
                status="error",
                progress_checkpoint=92,
                error_code="unexpected_analysis_error",
                message="حدث خطأ أثناء التحليل. احتفظنا بنص المنام ويمكن إعادة المحاولة.",
            )

    @staticmethod
    def _context(dream: str, answers: list[dict], knowledge: list[dict]) -> str:
        return (
            "نص المنام كما كتبه المستخدم:\n"
            + dream
            + "\n\nإجابات التوضيح السابقة (السؤال مع الإجابة):\n"
            + json.dumps(answers, ensure_ascii=False, separators=(",", ":"))
            + "\n\nالمعرفة الموثقة المتاحة لهذه الرؤيا فقط:\n"
            + json.dumps(knowledge, ensure_ascii=False, separators=(",", ":"))
            + "\n\nأي مصدر غير موجود أعلاه ممنوع اختراعه أو نسبته للقرآن أو السنة."
        )

    @classmethod
    def _sanitize_result(cls, raw: dict, knowledge: list[dict]) -> dict:
        clean = dict(raw)
        nature = str(clean.get("nature", "mixed")).strip().lower()
        if nature not in {"coherent", "mixed", "daily_thoughts", "fragmented"}:
            nature = "mixed"
        clean["nature"] = nature

        label = str(clean.get("nature_label", "")).strip()
        if not label or "غير محسوم" in label:
            label = {
                "coherent": "منام مترابط قابل للتأويل",
                "daily_thoughts": "أقرب إلى حديث النفس",
                "fragmented": "منام شديد التشتت",
                "mixed": "منام مختلط",
            }[nature]
        clean["nature_label"] = label

        clean["interpretation"] = str(clean.get("interpretation", "")).strip()
        clean["why_this_interpretation"] = str(clean.get("why_this_interpretation", "")).strip()
        clean["caution"] = str(
            clean.get("caution", "هذا تأويل اجتهادي وليس حكمًا يقينيًا، والله أعلم.")
        ).strip()

        evidence = []
        for item in clean.get("evidence", []) if isinstance(clean.get("evidence"), list) else []:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            explanation = str(item.get("explanation", "")).strip()
            if title and explanation:
                evidence.append({"title": title, "explanation": explanation})
            if len(evidence) >= 6:
                break
        clean["evidence"] = evidence

        alternatives = []
        for item in clean.get("alternatives", []) if isinstance(clean.get("alternatives"), list) else []:
            text = str(item).strip()
            if text and text not in alternatives:
                alternatives.append(text)
            if len(alternatives) >= 3:
                break
        clean["alternatives"] = alternatives
        clean["references"] = cls._sanitize_references(clean.get("references"), knowledge)

        if not clean["interpretation"]:
            raise AnalysisTechnicalFailure("empty_interpretation")
        if not clean["why_this_interpretation"]:
            clean["why_this_interpretation"] = "بُني الترجيح على تفاصيل المنام وإجابات التوضيح المتاحة."
        return clean

    @staticmethod
    def _sanitize_references(raw_refs, knowledge: list[dict]) -> list[dict]:
        allowed_by_ref: dict[str, dict] = {}
        for item in knowledge:
            if not isinstance(item, dict):
                continue
            ref = str(item.get("source_ref", "")).strip()
            if not ref:
                continue

            source_type = str(item.get("source_type", "")).strip().lower()
            if source_type == "quran":
                allowed_by_ref[ref] = item
                continue

            if source_type in {"hadith", "sunnah"}:
                grade_class = str(item.get("grade_class", "")).strip().lower()
                if grade_class == "accepted":
                    allowed_by_ref[ref] = item

        result: list[dict] = []
        if not isinstance(raw_refs, list):
            return result

        for item in raw_refs:
            if not isinstance(item, dict):
                continue
            claim = str(item.get("claim", "")).strip()
            explanation = str(item.get("explanation", "")).strip()
            relation = str(item.get("relation", "semantic")).strip().lower()
            if relation not in {"direct", "semantic"}:
                continue
            if not claim or not explanation:
                continue

            ref = str(item.get("source_ref", "")).strip()
            source = allowed_by_ref.get(ref)
            if source is None:
                continue

            source_text = str(source.get("text", "")).strip()
            if not source_text:
                continue
            if len(source_text) > 900:
                source_text = source_text[:897].rstrip() + "…"

            title = str(source.get("source_title", "")).strip() or str(item.get("source_title", "")).strip()
            visible_explanation = source_text
            if explanation:
                visible_explanation += "\n\nوجه الاستدلال: " + explanation

            result.append(
                {
                    "claim": claim,
                    "source_title": title,
                    "source_ref": ref,
                    "relation": relation,
                    "explanation": visible_explanation,
                }
            )
            if len(result) >= 2:
                break
        return result

    @classmethod
    def _question_from_decision(
        cls,
        decision: dict,
        answered_ids: set[str],
        answered_question_texts: set[str] | None = None,
        dream: str = "",
    ) -> Question | None:
        if not isinstance(decision, dict) or not bool(decision.get("need_question")):
            return None
        question_data = decision.get("question")
        if not isinstance(question_data, dict):
            return None

        question_data = dict(question_data)
        question_id = str(question_data.get("id", "")).strip()
        title = str(question_data.get("title", "")).strip()
        if not question_id or question_id in answered_ids or not title:
            return None
        if len(title) > 140 or cls._is_bundled_question(title):
            return None
        if dream and cls._question_already_answered_in_dream(title, dream):
            return None

        normalized_title = cls._normalize_question_text(title)
        previous = answered_question_texts or set()
        if normalized_title in previous:
            return None
        if any(cls._question_similarity(normalized_title, old) >= 0.82 for old in previous):
            return None

        question_data.setdefault("explanation", "")
        question_data.setdefault("options", [])
        question_data.setdefault("allow_text", False)
        question_data.setdefault("text_hint", "اكتب إجابتك هنا…")
        options = question_data.get("options")
        if isinstance(options, list) and len(options) > 5:
            question_data["options"] = options[:5]
        if not question_data.get("options") and not question_data.get("allow_text"):
            question_data["allow_text"] = True
        try:
            return Question.model_validate(question_data)
        except ValidationError:
            return None

    @staticmethod
    def _is_bundled_question(title: str) -> bool:
        if title.count("؟") + title.count("?") > 1:
            return True
        normalized = TafseerService._normalize_question_text(title)
        if len(re.findall(r"(?:^|\s)و?هل(?:\s|$)", normalized)) > 1:
            return True
        if re.search(r"[؟?]\s*(?:و|ثم)?\s*هل\b", title):
            return True
        return False

    @classmethod
    def _question_already_answered_in_dream(cls, title: str, dream: str) -> bool:
        title_norm = cls._normalize_question_text(title)
        dream_norm = cls._normalize_question_text(dream)

        asks_life_status = "حي" in title_norm and any(word in title_norm for word in ("متوفي", "ميت"))
        if not asks_life_status:
            return False

        dream_tokens = _WORDS.findall(dream_norm)
        title_tokens = set(_WORDS.findall(title_norm)) - {
            cls._normalize_question_text(word) for word in _STATUS_QUESTION_WORDS
        }
        if not title_tokens:
            return False

        normalized_markers = {cls._normalize_question_text(marker) for marker in _DECEASED_MARKERS}
        for index, token in enumerate(dream_tokens):
            if token not in normalized_markers:
                continue
            start = max(0, index - 5)
            end = min(len(dream_tokens), index + 7)
            nearby = set(dream_tokens[start:end])
            if title_tokens & nearby:
                return True
        return False

    @staticmethod
    def _normalize_question_text(text: str) -> str:
        text = _ARABIC_DIACRITICS.sub("", text.strip().lower())
        text = text.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي"}))
        return " ".join(_WORDS.findall(text))

    @staticmethod
    def _question_similarity(left: str, right: str) -> float:
        left_tokens = set(_WORDS.findall(left))
        right_tokens = set(_WORDS.findall(right))
        if not left_tokens or not right_tokens:
            return 0.0
        return len(left_tokens & right_tokens) / max(1, min(len(left_tokens), len(right_tokens)))

    @staticmethod
    def _required_assumptions(draft: dict) -> list[str]:
        assumptions: list[str] = []
        if not isinstance(draft, dict):
            return assumptions
        for candidate in draft.get("candidates", []):
            if not isinstance(candidate, dict):
                continue
            for item in candidate.get("required_assumptions", []):
                if isinstance(item, str) and item.strip() and item.strip() not in assumptions:
                    assumptions.append(item.strip())
                    if len(assumptions) >= 8:
                        return assumptions
        return assumptions

    @classmethod
    def _critique_needs_context(cls, critique: dict, draft: dict) -> bool:
        if not isinstance(critique, dict):
            return False
        missing = critique.get("missing_context", [])
        if isinstance(missing, list) and any(isinstance(x, str) and x.strip() for x in missing):
            return True
        if cls._required_assumptions(draft):
            return True
        preferred = str(critique.get("preferred", "")).strip()
        confidence = str(critique.get("confidence", "")).strip().lower()
        return confidence == "low" or "لا يوجد ترجيح" in preferred

    @staticmethod
    def _python_grounding_ok(raw: dict, valid_fact_ids: set[str]) -> bool:
        if not isinstance(raw, dict):
            return False
        grounding = raw.get("grounding")
        if not isinstance(grounding, list) or not grounding:
            return False
        for item in grounding:
            if not isinstance(item, dict):
                return False
            claim = str(item.get("claim", "")).strip()
            ids = item.get("fact_ids", [])
            if not claim or not isinstance(ids, list) or not ids:
                return False
            if any(not isinstance(fact_id, str) or fact_id not in valid_fact_ids for fact_id in ids):
                return False
        return True