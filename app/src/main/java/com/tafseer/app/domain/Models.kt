package com.tafseer.app.domain

enum class AnalysisStage(val title: String, val detail: String) {
    READING("قراءة المنام", "ترتيب الأحداث وفهم النص كما رويته"),
    EXTRACTING("فهم العناصر", "استخراج الأشخاص والأماكن والمشاعر والرموز"),
    CONTEXT("فهم السياق", "تمييز التفاصيل المؤثرة من التفاصيل العابرة"),
    CLARIFYING("التحقق", "تحديد ما إذا كانت هناك معلومة ناقصة تغيّر المعنى"),
    RETRIEVING("البحث", "مقارنة المنام بالمعرفة والحالات ذات البنية المشابهة"),
    HYPOTHESES("الموازنة", "بناء أكثر من احتمال وعدم التعلق بأول تفسير"),
    CRITIQUE("المراجعة", "محاولة نقض الاحتمالات الضعيفة وكشف التناقض"),
    CLASSIFYING("طبيعة المنام", "تقدير مدى الترابط وحديث النفس والاضطراب"),
    WRITING("الصياغة", "صياغة تفسير متزن دون جزم بما لا يمكن الجزم به"),
    VERIFYING("المراجعة النهائية", "فحص النتيجة قبل عرضها")
}

data class QuestionOption(val id: String, val label: String)

data class ClarifyingQuestion(
    val id: String,
    val title: String,
    val explanation: String,
    val options: List<QuestionOption> = emptyList(),
    val allowText: Boolean = false,
    val textHint: String = "اكتب إجابتك هنا…"
)

data class QuestionAnswer(
    val questionId: String,
    val questionText: String,
    val value: String
)

enum class DreamNature(val label: String) {
    COHERENT("منام مترابط نسبيًا"),
    MIXED("منام مختلط يحتمل أكثر من وجه"),
    DAILY_THOUGHTS("قد يغلب عليه حديث النفس"),
    FRAGMENTED("منام شديد التشتت ولا يظهر له تأويل واضح"),
    UNCERTAIN("النوع غير محسوم")
}

data class EvidencePoint(val title: String, val explanation: String)

data class InterpretationResult(
    val interpretation: String,
    val nature: DreamNature,
    val evidence: List<EvidencePoint>,
    val alternatives: List<String>,
    val whyThisInterpretation: String,
    val caution: String = "هذا تأويل اجتهادي وليس حكمًا يقينيًا، والله أعلم."
)

sealed interface TafseerUiState {
    data class Writing(val dream: String = "") : TafseerUiState

    data class Analyzing(
        val dream: String,
        val progress: Int,
        val stage: AnalysisStage,
        val stageDetail: String,
        val question: ClarifyingQuestion? = null
    ) : TafseerUiState

    data class Result(
        val dream: String,
        val result: InterpretationResult
    ) : TafseerUiState
}
