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
        minimum_questions = min(settings.max_questions, self._recommended_min_questions(dream))

        try:
            local_knowledge = self.knowledge.retrieve(dream, limit=8)
            scripture_knowledge = await self.scripture.retrieve(dream, answers, limit=12)
            knowledge = self._merge_knowledge(scripture_knowledge, local_knowledge, limit=18)

            prompt = TURN_PROMPT + "\n\n" + self._context(dream, answers, knowledge)
            if can_ask and len(answers) < minimum_questions:
                prompt += (
                    f"\n\nهذه الرؤيا متعددة العناصر وتحتاج على الأقل {minimum_questions} إجابات توضيحية مؤثرة قبل النتيجة. "
                    f"الموجود حاليًا {len(answers)} فقط. يجب في هذه الجولة إخراج action=question عن أهم مجهول واحد فقط. "
                    "لا تسأل عن معلومة مذكورة أصلًا، ولا تجمع محورين في سؤال واحد."
                )
            elif not can_ask:
                prompt += (
                    "\n\nبلغت المحادثة الحد الأقصى للأسئلة. ممنوع طرح سؤال جديد. "
                    "أخرج action=complete واختر طبيعة المنام الأقرب واشرح السبب دون استخدام غير محسوم."
                )

            decision = await self.models.generate_json(SYSTEM_PROMPT, prompt)
            action = str(decision.get("action", "")).strip().lower()

            if action != "question" and can_ask and len(answers) < minimum_questions:
                forced_prompt = (
                    prompt
                    + "\n\nأنت حاولت إنهاء التأويل قبل اكتمال الحد الأدنى من السياق. ممنوع complete الآن. "
                    "أعد JSON من نوع action=question فقط. اسأل عن مجهول واحد مؤثر لم يُذكر جوابه في النص أو الإجابات."
                )
                decision = await self.models.generate_json(SYSTEM_PROMPT, forced_prompt)
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
                    "إن كان الحد الأدنى للسياق لم يكتمل فلابد من سؤال صالح، وإلا فأخرج action=complete."
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

                if len(answers) < minimum_questions:
                    fallback = self._fallback_context_question(answers, answered_ids)
                    if fallback is not None:
                        return InterpretResponse(
                            status="question",
                            progress_checkpoint=min(90, 44 + len(answers) * 10),
                            question=fallback,
                        )

            raw_result = decision.get("result")
            if not isinstance(raw_result, dict):
                raise AnalysisTechnicalFailure("turn_result_missing")

            if can_ask and self._result_needs_more_context(raw_result, answers, dream):
                context_prompt = (
                    prompt
                    + "\n\nالنتيجة المقترحة ما زالت تعتمد على سياق لم يثبته المستخدم، أو صنفت المنام كحديث نفس/مختلط قبل اكتمال السياق. "
                    "لا تعرض نتيجة الآن. أخرج action=question فقط عن أهم معلومة واحدة يمكن أن تغيّر هذا الترجيح."
                )
                followup = await self.models.generate_json(SYSTEM_PROMPT, context_prompt)
                question = self._question_from_decision(
                    {"need_question": True, "question": followup.get("question")},
                    answered_ids,
                    answered_question_texts,
                    dream=dream,
                )
                if question is None:
                    question = self._fallback_context_question(answers, answered_ids)
                if question is not None:
                    return InterpretResponse(
                        status="question",
                        progress_checkpoint=min(92, 50 + len(answers) * 10),
                        question=question,
                    )

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