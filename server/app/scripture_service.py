import json
import logging

from pydantic import ValidationError

from .compact_service import AnalysisTechnicalFailure, TafseerService as CompactTafseerService
from .config import settings
from .dialogue_prompts import (
    FINAL_SYSTEM_PROMPT,
    FINAL_TURN_PROMPT,
    INTERVIEW_SYSTEM_PROMPT,
    INTERVIEW_TURN_PROMPT,
)
from .models import FinalResult, InterpretRequest, InterpretResponse, Question
from .providers import ProviderUnavailable
from .scripture_sources import ScriptureRetriever


logger = logging.getLogger("tafseer.scripture_service")

_ALLOWED_AXES = {
    "reality_link",
    "emotion",
    "ambiguity",
    "relationship",
    "personal_symbol",
    "chronology",
}
_AXIS_ORDER = (
    "reality_link",
    "emotion",
    "ambiguity",
    "relationship",
    "personal_symbol",
    "chronology",
)
_EMOTION_TERMS = {
    "فرح", "فرحان", "سعيد", "سعاده", "سعادة", "خوف", "خايف", "خائف", "قلق", "متوتر",
    "حزن", "حزين", "زعل", "زعلان", "ضيق", "مرتاح", "راحه", "راحة", "استغراب", "مستغرب",
    "اطمئنان", "مطمئن", "غضب", "غاضب", "ندم", "متحمس", "حماس",
}
_REALITY_EXPLICIT_PHRASES = (
    "في الواقع", "بالواقع", "في الحقيقه", "في الحقيقة", "حصل فعلا", "حصل فعلاً",
    "صار فعلا", "صار فعلاً", "يشغلني", "افكر فيه", "أفكر فيه", "هذه الفتره", "هذه الفترة",
    "هالفتره", "هالفترة", "واقعيا", "واقعيًا",
)
_NEGATIVE_REALITY_TERMS = (
    "لا علاقه", "لا علاقة", "ما له علاقه", "ماله علاقه", "لا يشغلني", "مو مرتبط", "غير مرتبط",
    "مجرد رمز", "لا اصل له", "لا أصل له",
)
_POSITIVE_REALITY_TERMS = (
    "نعم", "مرتبط", "يشغلني", "حصل", "واقع", "حقيقي", "فعلا", "فعلاً", "افكر", "أفكر",
)


class TafseerService(CompactTafseerService):
    """Two-phase tafseer flow: context interview first, interpretation second."""

    def __init__(self) -> None:
        super().__init__()
        self.scripture = ScriptureRetriever()

    async def interpret_step(self, request: InterpretRequest) -> InterpretResponse:
        dream = request.dream.strip()
        answers = [a.model_dump() for a in request.answers]
        answered_ids = {str(a.get("question_id", "")).strip() for a in answers}
        answered_question_texts = {
            self._normalize_question_text(str(a.get("question_text", "")))
            for a in answers
            if str(a.get("question_text", "")).strip()
        }
        answered_axes = self._answered_axes(answers)
        can_ask = len(answers) < settings.max_questions

        try:
            # Phase 1: interview only. No scripture retrieval and no interpretation.
            if can_ask:
                mandatory_axes = [
                    axis
                    for axis in self._mandatory_axes(dream)
                    if axis not in answered_axes and not self._dream_explicitly_answers_axis(dream, axis)
                ]
                interview_prompt = self._interview_context(dream, answers, answered_axes)
                if mandatory_axes:
                    interview_prompt += (
                        "\n\nلا يجوز إنهاء المقابلة الآن. المحور الإلزامي التالي هو: "
                        + mandatory_axes[0]
                        + ". اسأل عنه فقط في هذه الجولة، ولا تسأل عن محور آخر معه."
                    )

                interview = await self.models.generate_json(INTERVIEW_SYSTEM_PROMPT, interview_prompt)
                ready = bool(interview.get("ready", False))

                if mandatory_axes or not ready:
                    required_axis = mandatory_axes[0] if mandatory_axes else None
                    question = self._question_from_interview(
                        interview,
                        answered_ids,
                        answered_question_texts,
                        answered_axes,
                        dream,
                        required_axis=required_axis,
                    )
                    if question is None:
                        fallback_axis = required_axis or self._first_unanswered_axis(answered_axes)
                        if fallback_axis is not None:
                            question = self._fallback_axis_question(fallback_axis, answered_ids)
                    if question is not None:
                        return InterpretResponse(
                            status="question",
                            progress_checkpoint=min(88, 36 + len(answers) * 10),
                            question=question,
                        )

            # Phase 2: only now do the expensive source retrieval and interpretation.
            local_knowledge = self.knowledge.retrieve(dream, limit=8)
            scripture_knowledge = await self.scripture.retrieve(dream, answers, limit=12)
            knowledge = self._merge_knowledge(scripture_knowledge, local_knowledge, limit=18)

            final_prompt = FINAL_TURN_PROMPT + "\n\n" + self._final_context(dream, answers, knowledge)
            decision = await self.models.generate_json(FINAL_SYSTEM_PROMPT, final_prompt)
            raw_result = decision.get("result")
            if not isinstance(raw_result, dict):
                raise AnalysisTechnicalFailure("final_result_missing")

            # A daily-thoughts classification must be backed by the user's own
            # real-life answer, never inferred merely from realistic dream content.
            if str(raw_result.get("nature", "")).strip().lower() == "daily_thoughts":
                if not self._positive_reality_support(answers):
                    repair_prompt = (
                        final_prompt
                        + "\n\nرفض الخادم النتيجة السابقة لأنها صنفت المنام حديث نفس دون تصريح من المستخدم "
                        "بانشغال أو صلة واقعية. أعد النتيجة من جديد دون هذا الافتراض."
                    )
                    repaired = await self.models.generate_json(FINAL_SYSTEM_PROMPT, repair_prompt)
                    repaired_result = repaired.get("result")
                    if isinstance(repaired_result, dict):
                        raw_result = repaired_result

            clean = self._sanitize_result(raw_result, knowledge)
            try:
                result = FinalResult.model_validate(clean)
            except ValidationError as exc:
                raise AnalysisTechnicalFailure("final_result_schema") from exc

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
    def _interview_context(dream: str, answers: list[dict], answered_axes: set[str]) -> str:
        return (
            INTERVIEW_TURN_PROMPT
            + "\n\nنص المنام كما كتبه المستخدم:\n"
            + dream
            + "\n\nإجابات سابقة:\n"
            + json.dumps(answers, ensure_ascii=False, separators=(",", ":"))
            + "\n\nالمحاور التي جُمعت بالفعل:\n"
            + json.dumps(sorted(answered_axes), ensure_ascii=False)
            + "\n\nلا تفسر المنام في هذه المرحلة."
        )

    @staticmethod
    def _final_context(dream: str, answers: list[dict], knowledge: list[dict]) -> str:
        return (
            "نص المنام:\n"
            + dream
            + "\n\nإجابات المقابلة (السؤال مع الإجابة):\n"
            + json.dumps(answers, ensure_ascii=False, separators=(",", ":"))
            + "\n\nالمعرفة الموثقة/المقارنة المتاحة لهذه الرؤيا فقط:\n"
            + json.dumps(knowledge, ensure_ascii=False, separators=(",", ":"))
            + "\n\nلا تستخدم أو تنسب أي مصدر غير موجود أعلاه. الرؤى المشابهة خلفية فقط ولا تظهر كدليل."
        )

    @classmethod
    def _mandatory_axes(cls, dream: str) -> list[str]:
        complexity = cls._recommended_min_questions(dream)
        axes: list[str] = []
        if complexity >= 1:
            axes.append("reality_link")
        if complexity >= 2:
            axes.append("emotion")
        return axes

    @classmethod
    def _dream_explicitly_answers_axis(cls, dream: str, axis: str) -> bool:
        normalized = cls._normalize_question_text(dream)
        if axis == "reality_link":
            return any(cls._normalize_question_text(phrase) in normalized for phrase in _REALITY_EXPLICIT_PHRASES)
        if axis == "emotion":
            terms = {cls._normalize_question_text(item) for item in _EMOTION_TERMS}
            return any(term and term in normalized for term in terms)
        return False

    @classmethod
    def _answered_axes(cls, answers: list[dict]) -> set[str]:
        result: set[str] = set()
        for answer in answers:
            question_id = str(answer.get("question_id", "")).strip().lower()
            for axis in _ALLOWED_AXES:
                if question_id == f"ctx_{axis}" or question_id.startswith(f"ctx_{axis}_"):
                    result.add(axis)

            question_text = cls._normalize_question_text(str(answer.get("question_text", "")))
            if any(word in question_text for word in ("واقع", "يشغلك", "تفكيرك", "مرتبط")):
                result.add("reality_link")
            if any(word in question_text for word in ("شعور", "احساس", "إحساس", "شعرت")):
                result.add("emotion")
            if any(word in question_text for word in ("المقصود", "ماذا تعني", "ما معنى", "معني")):
                result.add("ambiguity")
            if any(word in question_text for word in ("علاقتك", "من يكون", "من هو")):
                result.add("relationship")
            if any(word in question_text for word in ("يعني لك", "معنى خاص", "رمز")):
                result.add("personal_symbol")
            if any(word in question_text for word in ("قبل", "بعد", "ترتيب", "ثم")):
                result.add("chronology")
        return result

    @staticmethod
    def _first_unanswered_axis(answered_axes: set[str]) -> str | None:
        for axis in _AXIS_ORDER:
            if axis not in answered_axes:
                return axis
        return None

    @classmethod
    def _question_from_interview(
        cls,
        interview: dict,
        answered_ids: set[str],
        answered_question_texts: set[str],
        answered_axes: set[str],
        dream: str,
        required_axis: str | None = None,
    ) -> Question | None:
        if not isinstance(interview, dict):
            return None
        data = interview.get("question")
        if not isinstance(data, dict):
            return None

        axis = str(data.get("axis", "")).strip().lower()
        if axis not in _ALLOWED_AXES or axis in answered_axes:
            return None
        if required_axis is not None and axis != required_axis:
            return None

        question_data = dict(data)
        question_data["id"] = f"ctx_{axis}"
        question_data.pop("axis", None)
        question_data.setdefault("explanation", "")
        question_data.setdefault("options", [])
        question_data.setdefault("allow_text", not bool(question_data.get("options")))
        question_data.setdefault("text_hint", "اكتب إجابتك هنا…")

        return cls._question_from_decision(
            {"need_question": True, "question": question_data},
            answered_ids,
            answered_question_texts,
            dream=dream,
        )

    @staticmethod
    def _fallback_axis_question(axis: str, answered_ids: set[str]) -> Question | None:
        question_id = f"ctx_{axis}"
        if question_id in answered_ids:
            return None

        if axis == "reality_link":
            return Question(
                id=question_id,
                title="هل المشهد الرئيسي في المنام له صلة بواقعك أو يشغل تفكيرك هذه الفترة؟",
                explanation="لفهم إن كان المنام متأثرًا بانشغال واقعي.",
                options=[
                    {"id": "yes", "label": "نعم، له صلة أو يشغلني"},
                    {"id": "no", "label": "لا، لا صلة مباشرة ولا يشغلني"},
                ],
                allow_text=True,
                text_hint="اذكر الصلة باختصار إن وجدت…",
            )
        if axis == "emotion":
            return Question(
                id=question_id,
                title="ما كان شعورك في المشهد الأهم من المنام؟",
                explanation="الشعور قد يغير معنى المشهد.",
                options=[],
                allow_text=True,
                text_hint="مثلاً: فرح، ضيق، استغراب، خوف…",
            )
        if axis == "ambiguity":
            return Question(
                id=question_id,
                title="هل هناك كلمة أو موقف في المنام له معنى خاص عندك ويحتاج توضيحًا؟",
                explanation="لتجنب تفسير عبارة على غير مقصودك.",
                options=[],
                allow_text=True,
                text_hint="وضح الجزء الملتبس فقط…",
            )
        if axis == "relationship":
            return Question(
                id=question_id,
                title="ما علاقتك بالشخص المحوري في المنام؟",
                explanation="طبيعة العلاقة قد تغير فهم دوره.",
                options=[],
                allow_text=True,
                text_hint="اذكر العلاقة باختصار…",
            )
        if axis == "personal_symbol":
            return Question(
                id=question_id,
                title="هل للشيء المحوري في المنام معنى شخصي خاص عندك؟",
                explanation="المعنى الشخصي قد يكون أهم من الرمز العام.",
                options=[],
                allow_text=True,
                text_hint="اذكر ما يعنيه لك إن وجد…",
            )
        if axis == "chronology":
            return Question(
                id=question_id,
                title="ما ترتيب الحدثين الأهم في المنام؟",
                explanation="ترتيب الأحداث قد يغير المعنى.",
                options=[],
                allow_text=True,
                text_hint="اذكر ما حدث أولاً ثم ما تلاه…",
            )
        return None

    @classmethod
    def _positive_reality_support(cls, answers: list[dict]) -> bool:
        for answer in answers:
            question_id = str(answer.get("question_id", "")).strip().lower()
            question_text = cls._normalize_question_text(str(answer.get("question_text", "")))
            if not (
                question_id.startswith("ctx_reality_link")
                or any(word in question_text for word in ("واقع", "يشغلك", "تفكيرك", "مرتبط"))
            ):
                continue
            value = cls._normalize_question_text(str(answer.get("value", "")))
            if any(cls._normalize_question_text(term) in value for term in _NEGATIVE_REALITY_TERMS):
                return False
            if any(cls._normalize_question_text(term) in value for term in _POSITIVE_REALITY_TERMS):
                return True
        return False

    @staticmethod
    def _merge_knowledge(primary: list[dict], secondary: list[dict], limit: int) -> list[dict]:
        result: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for item in primary + secondary:
            if not isinstance(item, dict):
                continue
            key = (
                str(item.get("source_ref", "")).strip(),
                str(item.get("text", item.get("dream_summary", ""))).strip()[:120],
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
            if len(result) >= limit:
                break
        return result

    @staticmethod
    def _sanitize_references(raw_refs, knowledge: list[dict]) -> list[dict]:
        allowed: dict[str, dict] = {}
        for item in knowledge:
            if not isinstance(item, dict):
                continue
            ref = str(item.get("source_ref", "")).strip()
            source_type = str(item.get("source_type", "")).strip().lower()
            grade_class = str(item.get("grade_class", "")).strip().lower()
            if not ref:
                continue
            if source_type == "quran":
                allowed[ref] = item
            elif source_type in {"hadith", "sunnah", "hadith_accepted"} and grade_class in {"", "accepted"}:
                allowed[ref] = item

        result: list[dict] = []
        if not isinstance(raw_refs, list):
            return result

        for item in raw_refs:
            if not isinstance(item, dict):
                continue
            claim = str(item.get("claim", "")).strip()
            explanation = str(item.get("explanation", "")).strip()
            relation = str(item.get("relation", "semantic")).strip().lower()
            if relation not in {"direct", "semantic"} or not claim or not explanation:
                continue

            ref = str(item.get("source_ref", "")).strip()
            source = allowed.get(ref)
            if source is None:
                continue

            source_type = str(source.get("source_type", "")).strip().lower()
            if source_type == "quran" and relation == "direct":
                relation = "semantic"

            source_text = str(source.get("text", "")).strip()
            if not source_text:
                continue
            if len(source_text) > 900:
                source_text = source_text[:897].rstrip() + "…"

            title = str(source.get("source_title", "")).strip() or "مصدر موثق"
            grade = str(source.get("grade", "")).strip()
            if source_type in {"hadith", "sunnah", "hadith_accepted"} and grade:
                title = f"{title} — {grade}"

            result.append(
                {
                    "claim": claim,
                    "source_title": title,
                    "source_ref": ref,
                    "relation": relation,
                    "explanation": source_text + "\n\nوجه الاستدلال: " + explanation,
                }
            )
            if len(result) >= 2:
                break
        return result
