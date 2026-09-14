import json
import logging
import re

from pydantic import ValidationError

from .config import settings
from .knowledge import KnowledgeStore
from .models import FinalResult, InterpretRequest, InterpretResponse, Question
from .prompts import (
    CRITIC_PROMPT,
    DRAFT_PROMPT,
    EXTRACT_PROMPT,
    FINAL_PROMPT,
    QUESTION_PROMPT,
    RECOVERY_QUESTION_PROMPT,
    SYSTEM_PROMPT,
    VERIFY_PROMPT,
)
from .providers import ModelRouter, ProviderUnavailable


logger = logging.getLogger("tafseer.service")
_ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
_WORDS = re.compile(r"[\w\u0600-\u06FF]{2,}")


class AnalysisTechnicalFailure(RuntimeError):
    pass


class TafseerService:
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
            knowledge = self.knowledge.retrieve(dream)
            base_context = self._context(dream, answers, knowledge, fact_map=None)
            fact_map = await self._extract_facts(base_context)
            compact_context = self._context(dream, answers, knowledge, fact_map=fact_map)
            valid_fact_ids = {
                item.get("id")
                for item in fact_map.get("facts", [])
                if isinstance(item, dict) and item.get("id")
            }

            if not valid_fact_ids:
                raise AnalysisTechnicalFailure("fact_extraction_empty")

            # Gate 1: ask before interpretation when one missing fact can materially
            # change the reading.
            if can_ask:
                question = await self._initial_context_question(
                    compact_context,
                    answered_ids,
                    answered_question_texts,
                )
                if question is not None:
                    return InterpretResponse(
                        status="question",
                        progress_checkpoint=min(76, 34 + len(answers) * 14),
                        question=question,
                    )

            draft = await self._build_draft(compact_context, valid_fact_ids)
            critique = await self._build_critique(compact_context, draft)

            # Gate 2: the critic found an assumption or ambiguity that can be resolved
            # by asking the user, so ask instead of forcing a conclusion.
            if can_ask and self._critique_needs_context(critique, draft):
                recovery_details = {
                    "stage": "critic",
                    "missing_context": critique.get("missing_context", []),
                    "unsupported_claims": critique.get("unsupported_claims", []),
                    "warnings": critique.get("warnings", []),
                    "uncertainties": draft.get("uncertainties", []),
                    "required_assumptions": self._required_assumptions(draft),
                }
                question = await self._recovery_context_question(
                    compact_context,
                    recovery_details,
                    answered_ids,
                    answered_question_texts,
                )
                if question is not None:
                    return InterpretResponse(
                        status="question",
                        progress_checkpoint=min(88, 62 + len(answers) * 10),
                        question=question,
                    )

            final_context = compact_context
            if draft:
                final_context += "\n\nملخص المرشحات الداخلية:\n" + json.dumps(
                    draft, ensure_ascii=False, separators=(",", ":")
                )
            if critique:
                final_context += "\n\nمراجعة الناقد الداخلية:\n" + json.dumps(
                    critique, ensure_ascii=False, separators=(",", ":")
                )

            outcome = await self._build_verified_result(
                final_context=final_context,
                compact_context=compact_context,
                valid_fact_ids=valid_fact_ids,
                answered_ids=answered_ids,
                answered_question_texts=answered_question_texts,
                can_ask=can_ask,
            )
            if isinstance(outcome, Question):
                return InterpretResponse(
                    status="question",
                    progress_checkpoint=min(94, 78 + len(answers) * 6),
                    question=outcome,
                )
            return InterpretResponse(status="complete", progress_checkpoint=100, result=outcome)

        except AnalysisTechnicalFailure as exc:
            logger.warning("analysis_technical_failure stage=%s", str(exc)[:80])
            return InterpretResponse(
                status="error",
                progress_checkpoint=95,
                error_code="analysis_pipeline_failed",
                message=(
                    "تعذر إكمال التحليل تقنيًا في هذه المحاولة. احتفظنا بنص المنام؛ "
                    "أعد المحاولة بعد قليل."
                ),
            )
        except ProviderUnavailable:
            logger.warning("analysis_technical_failure stage=provider_unavailable")
            return InterpretResponse(
                status="error",
                progress_checkpoint=95,
                error_code="provider_unavailable",
                message=(
                    "تعذر الوصول إلى مزود الذكاء الاصطناعي في هذه المحاولة. "
                    "احتفظنا بنص المنام؛ أعد المحاولة بعد قليل."
                ),
            )
        except Exception as exc:
            logger.exception("analysis_unexpected_failure type=%s", type(exc).__name__)
            return InterpretResponse(
                status="error",
                progress_checkpoint=95,
                error_code="unexpected_analysis_error",
                message=(
                    "حدث خطأ أثناء التحليل ولم يتم إنشاء تفسير. "
                    "احتفظنا بنص المنام ويمكنك إعادة المحاولة."
                ),
            )

    async def _initial_context_question(
        self,
        compact_context: str,
        answered_ids: set[str],
        answered_question_texts: set[str],
    ) -> Question | None:
        try:
            decision = await self.models.generate_json(
                SYSTEM_PROMPT,
                QUESTION_PROMPT + "\n\n" + compact_context,
            )
        except Exception as exc:
            raise AnalysisTechnicalFailure("initial_question") from exc
        return self._question_from_decision(
            decision,
            answered_ids,
            answered_question_texts,
        )

    async def _recovery_context_question(
        self,
        compact_context: str,
        trigger_details: dict,
        answered_ids: set[str],
        answered_question_texts: set[str],
    ) -> Question | None:
        recovery_context = (
            compact_context
            + "\n\nسبب طلب محاولة سؤال توضيحي إضافي:\n"
            + json.dumps(trigger_details, ensure_ascii=False, separators=(",", ":"))
        )
        try:
            decision = await self.models.generate_json(
                SYSTEM_PROMPT,
                RECOVERY_QUESTION_PROMPT + "\n\n" + recovery_context,
            )
        except Exception as exc:
            raise AnalysisTechnicalFailure("recovery_question") from exc
        return self._question_from_decision(
            decision,
            answered_ids,
            answered_question_texts,
        )

    @classmethod
    def _question_from_decision(
        cls,
        decision: dict,
        answered_ids: set[str],
        answered_question_texts: set[str] | None = None,
    ) -> Question | None:
        if not isinstance(decision, dict) or not bool(decision.get("need_question")):
            return None
        question_data = decision.get("question")
        if not isinstance(question_data, dict):
            return None

        question_id = str(question_data.get("id", "")).strip()
        title = str(question_data.get("title", "")).strip()
        if not question_id or question_id in answered_ids or not title:
            return None

        normalized_title = cls._normalize_question_text(title)
        previous = answered_question_texts or set()
        if normalized_title in previous:
            return None
        if any(cls._question_similarity(normalized_title, old) >= 0.82 for old in previous):
            return None

        if not question_data.get("options") and not question_data.get("allow_text"):
            question_data["allow_text"] = True
        try:
            return Question.model_validate(question_data)
        except ValidationError:
            return None

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

    async def _extract_facts(self, base_context: str) -> dict:
        try:
            raw = await self.models.generate_json(
                SYSTEM_PROMPT,
                EXTRACT_PROMPT + "\n\n" + base_context,
            )
        except Exception as exc:
            raise AnalysisTechnicalFailure("extract_facts") from exc

        facts: list[dict] = []
        seen_ids: set[str] = set()
        for item in raw.get("facts", []) if isinstance(raw, dict) else []:
            if not isinstance(item, dict):
                continue
            fact_id = str(item.get("id", "")).strip()
            text = str(item.get("text", "")).strip()
            fact_type = str(item.get("type", "other")).strip() or "other"
            if not fact_id or not text or fact_id in seen_ids:
                continue
            seen_ids.add(fact_id)
            facts.append({"id": fact_id, "text": text, "type": fact_type})
            if len(facts) >= 40:
                break

        unknowns = [
            str(x).strip()
            for x in raw.get("unknowns", [])
            if isinstance(x, str) and x.strip()
        ][:12]
        explicit_context = [
            str(x).strip()
            for x in raw.get("explicit_real_life_context", [])
            if isinstance(x, str) and x.strip()
        ][:12]
        return {
            "facts": facts,
            "unknowns": unknowns,
            "explicit_real_life_context": explicit_context,
        }

    async def _build_draft(self, compact_context: str, valid_fact_ids: set[str]) -> dict:
        try:
            raw = await self.models.generate_json(
                SYSTEM_PROMPT,
                DRAFT_PROMPT + "\n\n" + compact_context,
            )
        except Exception as exc:
            raise AnalysisTechnicalFailure("draft") from exc
        return self._sanitize_draft(raw, valid_fact_ids)

    async def _build_critique(self, compact_context: str, draft: dict) -> dict:
        try:
            return await self.models.generate_json(
                SYSTEM_PROMPT,
                CRITIC_PROMPT
                + "\n\n"
                + compact_context
                + "\n\nملخص المرشحات المطلوب نقده:\n"
                + json.dumps(draft, ensure_ascii=False, separators=(",", ":")),
            )
        except Exception as exc:
            raise AnalysisTechnicalFailure("critique") from exc

    @staticmethod
    def _sanitize_draft(draft: dict, valid_fact_ids: set[str]) -> dict:
        if not isinstance(draft, dict):
            return {}
        sanitized = dict(draft)
        candidates = []
        for candidate in draft.get("candidates", []):
            if not isinstance(candidate, dict):
                continue
            ids = [
                fact_id
                for fact_id in candidate.get("support_fact_ids", [])
                if isinstance(fact_id, str) and fact_id in valid_fact_ids
            ]
            if not ids:
                continue
            clean = dict(candidate)
            clean["support_fact_ids"] = ids
            candidates.append(clean)
        sanitized["candidates"] = candidates[:8]
        return sanitized

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

    async def _build_verified_result(
        self,
        final_context: str,
        compact_context: str,
        valid_fact_ids: set[str],
        answered_ids: set[str],
        answered_question_texts: set[str],
        can_ask: bool,
    ) -> FinalResult | Question:
        raw = await self._generate_final(final_context)

        if not self._python_grounding_ok(raw, valid_fact_ids):
            raw = await self._retry_after_rejection(
                final_context,
                raw,
                ["هناك ادعاء رئيسي بلا fact_ids صحيحة من خريطة الحقائق."],
            )
            if not self._python_grounding_ok(raw, valid_fact_ids):
                if can_ask:
                    question = await self._recovery_context_question(
                        compact_context,
                        {
                            "stage": "grounding",
                            "missing_context": ["المعنى المقترح لا يمكن ربطه بما ورد صراحة"],
                        },
                        answered_ids,
                        answered_question_texts,
                    )
                    if question is not None:
                        return question
                return self._insufficient_evidence_result()

        verification = await self._verify_result(final_context, raw)
        if not verification.get("pass", False):
            question = await self._question_from_verification(
                compact_context,
                verification,
                answered_ids,
                answered_question_texts,
                can_ask,
                stage="final_verifier",
            )
            if question is not None:
                return question

            raw = await self._retry_after_rejection(
                final_context,
                raw,
                verification.get("unsupported_claims", []),
            )
            if not self._python_grounding_ok(raw, valid_fact_ids):
                return self._insufficient_evidence_result()

            verification = await self._verify_result(final_context, raw)
            if not verification.get("pass", False):
                question = await self._question_from_verification(
                    compact_context,
                    verification,
                    answered_ids,
                    answered_question_texts,
                    can_ask,
                    stage="final_verifier_retry",
                )
                if question is not None:
                    return question
                return self._insufficient_evidence_result()

        try:
            return FinalResult.model_validate(raw)
        except ValidationError:
            repaired = await self._retry_after_rejection(
                final_context,
                raw,
                ["صيغة النتيجة النهائية غير مكتملة أو غير صالحة."],
            )
            try:
                return FinalResult.model_validate(repaired)
            except ValidationError as exc:
                raise AnalysisTechnicalFailure("final_schema") from exc

    async def _generate_final(self, final_context: str) -> dict:
        try:
            return await self.models.generate_json(
                SYSTEM_PROMPT,
                FINAL_PROMPT + "\n\n" + final_context,
            )
        except Exception as exc:
            raise AnalysisTechnicalFailure("final_generation") from exc

    async def _question_from_verification(
        self,
        compact_context: str,
        verification: dict,
        answered_ids: set[str],
        answered_question_texts: set[str],
        can_ask: bool,
        stage: str,
    ) -> Question | None:
        if not can_ask:
            return None
        missing = verification.get("missing_context", [])
        unsupported = verification.get("unsupported_claims", [])
        if not missing and not unsupported:
            return None
        return await self._recovery_context_question(
            compact_context,
            {
                "stage": stage,
                "missing_context": missing,
                "unsupported_claims": unsupported,
                "reason": verification.get("reason", ""),
            },
            answered_ids,
            answered_question_texts,
        )

    async def _verify_result(self, final_context: str, raw: dict) -> dict:
        try:
            return await self.models.generate_json(
                SYSTEM_PROMPT,
                VERIFY_PROMPT
                + "\n\n"
                + final_context
                + "\n\nالنتيجة المقترحة للتدقيق:\n"
                + json.dumps(raw, ensure_ascii=False, separators=(",", ":")),
            )
        except Exception as exc:
            raise AnalysisTechnicalFailure("final_verification") from exc

    async def _retry_after_rejection(
        self,
        final_context: str,
        raw: dict,
        unsupported_claims: list,
    ) -> dict:
        rejection_context = (
            final_context
            + "\n\nالنتيجة السابقة رُفضت لأنها احتوت على ادعاءات غير مسندة أو صيغة غير صالحة:\n"
            + json.dumps(unsupported_claims, ensure_ascii=False, separators=(",", ":"))
            + "\n\nالنتيجة السابقة:\n"
            + json.dumps(raw, ensure_ascii=False, separators=(",", ":"))
            + "\n\nأعد صياغة نتيجة جديدة محافظة، واحذف كل ادعاء لا تدعمه خريطة الحقائق."
        )
        try:
            return await self.models.generate_json(
                SYSTEM_PROMPT,
                FINAL_PROMPT + "\n\n" + rejection_context,
            )
        except Exception as exc:
            raise AnalysisTechnicalFailure("final_retry") from exc

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

    @staticmethod
    def _context(
        dream: str,
        answers: list[dict],
        knowledge: list[dict],
        fact_map: dict | None,
    ) -> str:
        knowledge_text = json.dumps(knowledge, ensure_ascii=False, separators=(",", ":"))
        answers_text = json.dumps(answers, ensure_ascii=False, separators=(",", ":"))
        fact_text = json.dumps(fact_map or {}, ensure_ascii=False, separators=(",", ":"))
        return (
            "نص المنام كما كتبه المستخدم:\n" + dream
            + "\n\nإجابات التوضيح السابقة، وكل عنصر يتضمن السؤال وإجابته (لا تكرر معناها):\n"
            + answers_text
            + "\n\nخريطة الحقائق الصريحة المستخرجة:\n" + fact_text
            + "\n\nالمعرفة المسترجعة الموثقة فقط:\n" + knowledge_text
            + "\n\nمهم: غياب مصدر موثق يعني عدم نسبة قول إلى كتاب أو عالم. "
            + "وخريطة الحقائق هي الحد الأعلى لما يجوز اعتباره معلومًا عن المستخدم."
        )

    @staticmethod
    def _insufficient_evidence_result() -> FinalResult:
        return FinalResult(
            interpretation=(
                "بعد التوضيحات المتاحة لا تكفي القرائن لترجيح تفسير محدد دون إضافة افتراضات من خارج المنام. "
                "الأفضل التوقف هنا بدل بناء معنى مقنع شكليًا لا يسنده النص."
            ),
            nature="uncertain",
            nature_label="الترجيح غير كافٍ",
            evidence=[],
            alternatives=[],
            why_this_interpretation=(
                "رفض المدقق الداخلي الترجيح لأن المعنى احتاج استنتاجات لا يمكن ربطها مباشرة بما ورد في المنام أو إجاباتك."
            ),
            caution="هذا تأويل اجتهادي وليس حكمًا يقينيًا، والله أعلم.",
        )
