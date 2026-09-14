import json
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
    SYSTEM_PROMPT,
    VERIFY_PROMPT,
)
from .providers import ModelRouter, ProviderUnavailable


class TafseerService:
    def __init__(self) -> None:
        self.models = ModelRouter()
        self.knowledge = KnowledgeStore()

    async def interpret_step(self, request: InterpretRequest) -> InterpretResponse:
        dream = request.dream.strip()
        answers = [a.model_dump() for a in request.answers]
        answered_ids = {a["question_id"] for a in answers}
        knowledge = self.knowledge.retrieve(dream)

        base_context = self._context(dream, answers, knowledge, fact_map=None)
        fact_map = await self._extract_facts(base_context)
        compact_context = self._context(dream, answers, knowledge, fact_map=fact_map)
        valid_fact_ids = {
            item.get("id")
            for item in fact_map.get("facts", [])
            if isinstance(item, dict) and item.get("id")
        }

        if len(answers) < settings.max_questions:
            try:
                decision = await self.models.generate_json(
                    SYSTEM_PROMPT,
                    QUESTION_PROMPT + "\n\n" + compact_context,
                )
                question_data = decision.get("question") if bool(decision.get("need_question")) else None
                if question_data and question_data.get("id") not in answered_ids:
                    if not question_data.get("options") and not question_data.get("allow_text"):
                        question_data["allow_text"] = True
                    question = Question.model_validate(question_data)
                    return InterpretResponse(
                        status="question",
                        progress_checkpoint=min(76, 34 + len(answers) * 14),
                        question=question,
                    )
            except (ProviderUnavailable, ValidationError, ValueError, KeyError, TypeError):
                pass

        draft: dict = {}
        critique: dict = {}

        try:
            draft = await self.models.generate_json(
                SYSTEM_PROMPT,
                DRAFT_PROMPT + "\n\n" + compact_context,
            )
            draft = self._sanitize_draft(draft, valid_fact_ids)
        except (ProviderUnavailable, ValueError, KeyError, TypeError):
            draft = {}

        if draft:
            try:
                critique = await self.models.generate_json(
                    SYSTEM_PROMPT,
                    CRITIC_PROMPT
                    + "\n\n"
                    + compact_context
                    + "\n\nملخص المرشحات المطلوب نقده:\n"
                    + json.dumps(draft, ensure_ascii=False, separators=(",", ":")),
                )
            except (ProviderUnavailable, ValueError, KeyError, TypeError):
                critique = {}

        final_context = compact_context
        if draft:
            final_context += "\n\nملخص المرشحات الداخلية:\n" + json.dumps(
                draft, ensure_ascii=False, separators=(",", ":")
            )
        if critique:
            final_context += "\n\nمراجعة الناقد الداخلية:\n" + json.dumps(
                critique, ensure_ascii=False, separators=(",", ":")
            )

        result = await self._build_verified_result(
            dream=dream,
            final_context=final_context,
            valid_fact_ids=valid_fact_ids,
        )
        return InterpretResponse(status="complete", progress_checkpoint=100, result=result)

    async def _extract_facts(self, base_context: str) -> dict:
        try:
            raw = await self.models.generate_json(
                SYSTEM_PROMPT,
                EXTRACT_PROMPT + "\n\n" + base_context,
            )
        except (ProviderUnavailable, ValueError, KeyError, TypeError):
            return {"facts": [], "unknowns": [], "explicit_real_life_context": []}

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

    async def _build_verified_result(
        self,
        dream: str,
        final_context: str,
        valid_fact_ids: set[str],
    ) -> FinalResult:
        try:
            raw = await self.models.generate_json(
                SYSTEM_PROMPT,
                FINAL_PROMPT + "\n\n" + final_context,
            )
        except (ProviderUnavailable, ValueError, KeyError, TypeError):
            return self._safe_fallback(dream)

        if not self._python_grounding_ok(raw, valid_fact_ids):
            raw = await self._retry_after_rejection(
                final_context,
                raw,
                ["هناك ادعاء رئيسي بلا fact_ids صحيحة من خريطة الحقائق."],
            )
            if not self._python_grounding_ok(raw, valid_fact_ids):
                return self._insufficient_evidence_result()

        verification = await self._verify_result(final_context, raw)
        if not verification.get("pass", False):
            unsupported = verification.get("unsupported_claims", [])
            raw = await self._retry_after_rejection(final_context, raw, unsupported)
            if not self._python_grounding_ok(raw, valid_fact_ids):
                return self._insufficient_evidence_result()
            verification = await self._verify_result(final_context, raw)
            if not verification.get("pass", False):
                return self._insufficient_evidence_result()

        try:
            return FinalResult.model_validate(raw)
        except ValidationError:
            return self._insufficient_evidence_result()

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
        except (ProviderUnavailable, ValueError, KeyError, TypeError):
            return {"pass": False, "unsupported_claims": ["تعذر إجراء التدقيق النهائي."]}

    async def _retry_after_rejection(
        self,
        final_context: str,
        raw: dict,
        unsupported_claims: list,
    ) -> dict:
        rejection_context = (
            final_context
            + "\n\nالنتيجة السابقة رُفضت لأنها احتوت على ادعاءات غير مسندة:\n"
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
        except (ProviderUnavailable, ValueError, KeyError, TypeError):
            return {}

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
            + "\n\nإجابات التوضيح:\n" + answers_text
            + "\n\nخريطة الحقائق الصريحة المستخرجة:\n" + fact_text
            + "\n\nالمعرفة المسترجعة الموثقة فقط:\n" + knowledge_text
            + "\n\nمهم: غياب مصدر موثق يعني عدم نسبة قول إلى كتاب أو عالم. "
            + "وخريطة الحقائق هي الحد الأعلى لما يجوز اعتباره معلومًا عن المستخدم."
        )

    @staticmethod
    def _insufficient_evidence_result() -> FinalResult:
        return FinalResult(
            interpretation=(
                "لا تكفي القرائن الحالية لترجيح تفسير محدد دون إضافة افتراضات من خارج المنام. "
                "الأفضل التوقف هنا بدل بناء معنى مقنع شكليًا لا يسنده النص."
            ),
            nature="uncertain",
            nature_label="الترجيح غير كافٍ",
            evidence=[],
            alternatives=[],
            why_this_interpretation=(
                "رفض المدقق الداخلي النتيجة لأنها احتاجت استنتاجات لا يمكن ربطها مباشرة بما ورد في المنام أو إجاباتك."
            ),
            caution="هذا تأويل اجتهادي وليس حكمًا يقينيًا، والله أعلم.",
        )

    @staticmethod
    def _safe_fallback(dream: str) -> FinalResult:
        length_label = "مترابط نسبيًا" if len(dream) >= 120 else "مختصر ويحتمل أكثر من وجه"
        return FinalResult(
            interpretation=(
                "تعذر إكمال مسار التأويل الموثق في هذه المحاولة، لذلك لن أختلق تفسيرًا من رموز منفصلة. "
                "يمكن إعادة المحاولة لاحقًا."
            ),
            nature="uncertain",
            nature_label=length_label,
            evidence=[],
            alternatives=[],
            why_this_interpretation="تم اختيار الامتناع عن التخمين لأن مسار التحقق لم يكتمل.",
            caution="لا توجد نتيجة تفسيرية موثوقة في هذه المحاولة. والله أعلم.",
        )
