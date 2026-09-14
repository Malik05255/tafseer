import json
from pydantic import ValidationError

from .config import settings
from .knowledge import KnowledgeStore
from .models import FinalResult, InterpretRequest, InterpretResponse, Question
from .prompts import CRITIC_PROMPT, DRAFT_PROMPT, FINAL_PROMPT, QUESTION_PROMPT, SYSTEM_PROMPT
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
        compact_context = self._context(dream, answers, knowledge)

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
                # Failure to generate a useful question must not block the final analysis.
                pass

        draft: dict = {}
        critique: dict = {}

        try:
            draft = await self.models.generate_json(
                SYSTEM_PROMPT,
                DRAFT_PROMPT + "\n\n" + compact_context,
            )
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

        try:
            raw = await self.models.generate_json(
                SYSTEM_PROMPT,
                FINAL_PROMPT + "\n\n" + final_context,
            )
            result = FinalResult.model_validate(raw)
        except (ProviderUnavailable, ValidationError, ValueError, KeyError, TypeError):
            result = self._safe_fallback(dream)

        return InterpretResponse(status="complete", progress_checkpoint=100, result=result)

    @staticmethod
    def _context(dream: str, answers: list[dict], knowledge: list[dict]) -> str:
        knowledge_text = json.dumps(knowledge, ensure_ascii=False, separators=(",", ":"))
        answers_text = json.dumps(answers, ensure_ascii=False, separators=(",", ":"))
        return (
            "الرؤيا:\n" + dream
            + "\n\nإجابات التوضيح:\n" + answers_text
            + "\n\nالمعرفة المسترجعة الموثقة فقط:\n" + knowledge_text
            + "\n\nمهم: غياب مصدر موثق يعني عدم نسبة قول إلى كتاب أو عالم."
        )

    @staticmethod
    def _safe_fallback(dream: str) -> FinalResult:
        length_label = "مترابط نسبيًا" if len(dream) >= 120 else "مختصر ويحتمل أكثر من وجه"
        return FinalResult(
            interpretation=(
                "تعذر الوصول إلى محرك التأويل المتقدم الآن، لذلك لن أختلق تفسيرًا من رموز منفصلة. "
                "يمكن إعادة المحاولة عند توفر مزود الذكاء الاصطناعي."
            ),
            nature="uncertain",
            nature_label=length_label,
            evidence=[],
            alternatives=[],
            why_this_interpretation="تم اختيار الامتناع عن التخمين لأن المحرك المتقدم أو مصادر كافية لم تكن متاحة.",
            caution="لا توجد نتيجة تفسيرية موثوقة في هذه المحاولة. والله أعلم.",
        )
