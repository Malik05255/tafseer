import logging

from pydantic import ValidationError

from .compact_prompts import SYSTEM_PROMPT, TURN_PROMPT
from .compact_service import AnalysisTechnicalFailure, TafseerService as CompactTafseerService
from .config import settings
from .models import FinalResult, InterpretRequest, InterpretResponse
from .providers import ProviderUnavailable
from .scripture_sources import ScriptureRetriever


logger = logging.getLogger("tafseer.scripture_service")


class TafseerService(CompactTafseerService):
    """Compact tafseer flow grounded in live Quran and hadith retrieval."""

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
        can_ask = len(answers) < settings.max_questions

        try:
            local_knowledge = self.knowledge.retrieve(dream, limit=8)
            scripture_knowledge = await self.scripture.retrieve(dream, answers, limit=12)
            knowledge = self._merge_knowledge(scripture_knowledge, local_knowledge, limit=18)

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
                )
                if question is not None:
                    return InterpretResponse(
                        status="question",
                        progress_checkpoint=min(86, 38 + len(answers) * 10),
                        question=question,
                    )

                repair_prompt = (
                    prompt
                    + "\n\nالسؤال الذي اقترحته مكرر أو غير صالح. لا تكرر أي سؤال سابق. "
                    "إما اسأل سؤالًا مختلفًا مؤثرًا أو أخرج action=complete."
                )
                decision = await self.models.generate_json(SYSTEM_PROMPT, repair_prompt)
                if str(decision.get("action", "")).strip().lower() == "question":
                    question = self._question_from_decision(
                        {"need_question": True, "question": decision.get("question")},
                        answered_ids,
                        answered_question_texts,
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
