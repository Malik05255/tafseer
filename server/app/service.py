import json
from pydantic import ValidationError

from .config import settings
from .knowledge import KnowledgeStore
from .models import FinalResult, InterpretRequest, InterpretResponse, Question
from .prompts import FINAL_PROMPT, QUESTION_PROMPT, SYSTEM_PROMPT
from .providers import ModelRouter, ProviderUnavailable


class TafseerService:
    def __init__(self) -> None:
        self.models = ModelRouter()
        self.knowledge = KnowledgeStore()

    async def interpret_step(self, request: InterpretRequest) -> InterpretResponse:
        dream = request.dream.strip()
        answers = [a.model_dump() for a in request.answers]
        knowledge = self.knowledge.retrieve(dream)
        compact_context = self._context(dream, answers, knowledge)

        if len(answers) < settings.max_questions:
            try:
                decision = await self.models.generate_json(
                    SYSTEM_PROMPT,
                    QUESTION_PROMPT + "\n\n" + compact_context,
                )
                if bool(decision.get("need_question")) and decision.get("question"):
                    question = Question.model_validate(decision["question"])
                    return InterpretResponse(
                        status="question",
                        progress_checkpoint=min(72, 34 + len(answers) * 13),
                        question=question,
                    )
            except (ProviderUnavailable, ValidationError, ValueError, KeyError):
                # Question generation must never prevent a final result attempt.
                pass

        try:
            raw = await self.models.generate_json(
                SYSTEM_PROMPT,
                FINAL_PROMPT + "\n\n" + compact_context,
            )
            result = FinalResult.model_validate(raw)
        except (ProviderUnavailable, ValidationError, ValueError, KeyError) as exc:
            result = self._safe_fallback(dream, str(exc))

        return InterpretResponse(status="complete", progress_checkpoint=100, result=result)

    @staticmethod
    def _context(dream: str, answers: list[dict], knowledge: list[dict]) -> str:
        knowledge_text = json.dumps(knowledge, ensure_ascii=False, separators=(",", ":"))
        answers_text = json.dumps(answers, ensure_ascii=False, separators=(",", ":"))
        return (
            "الرؤيا:\n" + dream +
            "\n\nإجابات التوضيح:\n" + answers_text +
            "\n\nالمعرفة المسترجعة الموثقة فقط:\n" + knowledge_text +
            "\n\nمهم: غياب مصدر موثق يعني عدم نسبة قول إلى كتاب أو عالم."
        )

    @staticmethod
    def _safe_fallback(dream: str, error: str) -> FinalResult:
        length_label = "مترابط نسبيًا" if len(dream) >= 120 else "مختصر ويحتمل أكثر من وجه"
        return FinalResult(
            interpretation=(
                "تعذر الوصول إلى محرك التأويل المتقدم الآن، لذلك لن أختلق تفسيرًا من رموز منفصلة. "
                "تم حفظ بنية الطلب فقط ويمكن إعادة المحاولة عند توفر مزود الذكاء الاصطناعي."
            ),
            nature="uncertain",
            nature_label=length_label,
            evidence=[],
            alternatives=[],
            why_this_interpretation="تم اختيار الامتناع عن التخمين لأن المحرك المتقدم أو مصادر كافية لم تكن متاحة.",
            caution="لا توجد نتيجة تفسيرية موثوقة في هذه المحاولة. والله أعلم.",
        )
