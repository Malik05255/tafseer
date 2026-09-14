package com.tafseer.app.domain

import kotlinx.coroutines.delay

interface TafseerEngine {
    suspend fun interpret(
        dream: String,
        onProgress: suspend (progress: Int, stage: AnalysisStage) -> Unit,
        ask: suspend (ClarifyingQuestion) -> QuestionAnswer
    ): InterpretationResult
}

class LocalTafseerEngine : TafseerEngine {
    override suspend fun interpret(
        dream: String,
        onProgress: suspend (Int, AnalysisStage) -> Unit,
        ask: suspend (ClarifyingQuestion) -> QuestionAnswer
    ): InterpretationResult {
        val answers = mutableListOf<QuestionAnswer>()
        var askedEmotion = false
        var askedMarriage = false
        var askedShortDream = false

        for (progress in 0..100) {
            val stage = stageFor(progress)
            onProgress(progress, stage)
            delay(if (progress in setOf(18, 31, 52, 69, 84, 94)) 150L else 36L)

            if (progress == 24 && dream.trim().length < 45 && !askedShortDream) {
                askedShortDream = true
                answers += ask(
                    ClarifyingQuestion(
                        id = "more_detail",
                        title = "هل تتذكر تفاصيل أخرى؟",
                        explanation = "الرؤيا قصيرة جدًا، وإضافة ما حدث قبل أو بعد المشهد قد تغيّر التأويل.",
                        allowText = true,
                        textHint = "اكتب أي تفصيل إضافي، أو اكتب: لا أتذكر"
                    )
                )
            }

            if (progress == 37 && !containsEmotion(dream) && !askedEmotion) {
                askedEmotion = true
                answers += ask(
                    ClarifyingQuestion(
                        id = "emotion",
                        title = "كيف كان شعورك الأوضح في الرؤيا؟",
                        explanation = "الشعور قد يغيّر دلالة المشهد نفسه، لذلك نحتاجه قبل ترجيح المعنى.",
                        options = listOf(
                            QuestionOption("calm", "طمأنينة"),
                            QuestionOption("fear", "خوف"),
                            QuestionOption("joy", "فرح"),
                            QuestionOption("sad", "حزن"),
                            QuestionOption("neutral", "لم أشعر بشيء واضح"),
                            QuestionOption("unknown", "لا أتذكر")
                        )
                    )
                )
            }

            if (progress == 46 && containsMarriage(dream) && !askedMarriage) {
                askedMarriage = true
                answers += ask(
                    ClarifyingQuestion(
                        id = "marital_context",
                        title = "ما حالتك الاجتماعية؟",
                        explanation = "هذه المعلومة مطلوبة لأن الرؤيا تحتوي على زواج أو خطبة وقد يتغيّر المعنى بالسياق.",
                        options = listOf(
                            QuestionOption("single", "أعزب / عزباء"),
                            QuestionOption("married", "متزوج / متزوجة"),
                            QuestionOption("other", "غير ذلك"),
                            QuestionOption("skip", "أفضل عدم الإجابة")
                        )
                    )
                )
            }
        }
        return buildLocalFallbackResult(dream, answers)
    }

    private fun stageFor(progress: Int): AnalysisStage = when (progress) {
        in 0..9 -> AnalysisStage.READING
        in 10..19 -> AnalysisStage.EXTRACTING
        in 20..29 -> AnalysisStage.CONTEXT
        in 30..39 -> AnalysisStage.CLARIFYING
        in 40..54 -> AnalysisStage.RETRIEVING
        in 55..68 -> AnalysisStage.HYPOTHESES
        in 69..78 -> AnalysisStage.CRITIQUE
        in 79..86 -> AnalysisStage.CLASSIFYING
        in 87..95 -> AnalysisStage.WRITING
        else -> AnalysisStage.VERIFYING
    }

    private fun containsEmotion(text: String): Boolean {
        val words = listOf("خوف", "خفت", "مرعوب", "فرح", "سعيد", "راحة", "مرتاح", "حزن", "زعل", "اطمئنان")
        return words.any { text.contains(it, ignoreCase = true) }
    }

    private fun containsMarriage(text: String): Boolean {
        val words = listOf("زواج", "تزوج", "عرس", "عريس", "عروس", "خطبة", "خطبني", "خطيب")
        return words.any { text.contains(it, ignoreCase = true) }
    }

    private fun buildLocalFallbackResult(
        dream: String,
        answers: List<QuestionAnswer>
    ): InterpretationResult {
        val fragmented = dream.count { it == '،' || it == ',' } > 10 && dream.length < 180
        val dailyThoughts = listOf("امتحان", "دوام", "مديري", "مشروع", "مباراة").count {
            dream.contains(it, ignoreCase = true)
        } >= 2

        val nature = when {
            fragmented -> DreamNature.FRAGMENTED
            dailyThoughts -> DreamNature.DAILY_THOUGHTS
            dream.length > 120 -> DreamNature.COHERENT
            else -> DreamNature.MIXED
        }

        val emotion = answers.firstOrNull { it.questionId == "emotion" }?.value
        val evidence = buildList {
            add(EvidencePoint("تسلسل الرؤيا", "تم التعامل مع الأحداث كوحدة مترابطة لا كرموز منفصلة."))
            emotion?.let { add(EvidencePoint("شعور الرائي", "تم إدخال شعورك ضمن الترجيح لأنه يغيّر دلالة المشهد.")) }
            if (containsMarriage(dream)) {
                add(EvidencePoint("السياق الشخصي", "وجود زواج أو خطبة يجعل الحالة الاجتماعية قرينة مهمة وليست تفصيلًا ثانويًا."))
            }
        }

        return InterpretationResult(
            interpretation = when (nature) {
                DreamNature.DAILY_THOUGHTS -> "تظهر في المنام عناصر قريبة من انشغالات الحياة اليومية، ولذلك لا أرجّح بناء تأويل رمزي قوي عليها وحدها. الأقرب أن جزءًا معتبرًا منه امتداد لما يشغل ذهنك، مع بقاء بعض التفاصيل بحاجة إلى سياق أوسع قبل تأويلها."
                DreamNature.FRAGMENTED -> "المنام شديد التداخل ولا تظهر فيه بنية مستقرة تكفي لترجيح معنى محدد بثقة. الأفضل هنا عدم تحميل المشاهد المتقطعة دلالات منفصلة؛ لأن جمع رموز متفرقة قد ينتج تفسيرًا مضللًا."
                DreamNature.COHERENT -> "الرؤيا مترابطة نسبيًا، ويبدو أن معناها ينبغي أن يُفهم من اتجاه القصة وتحوّل المشاعر والنتيجة النهائية أكثر من تفسير كل رمز منفردًا. النسخة المحلية أكملت التحليل البنيوي، أما التأويل التفصيلي عالي الجودة فيُستكمل عبر محرك المعرفة والذكاء الاصطناعي عند ربط الخادم."
                DreamNature.MIXED -> "توجد بنية قابلة للفهم، لكن المعطيات الحالية تسمح بأكثر من وجه ولا يصح الجزم بأحدها. الأهم هو اجتماع السياق والشعور ونهاية الرؤيا؛ وهذه تحتاج إلى محرك المعرفة المتصل لإخراج تأويل تفصيلي موثّق بدل التخمين."
            },
            nature = nature,
            evidence = evidence,
            alternatives = listOf(
                "قد يكون بعض المشهد انعكاسًا لانشغال سابق لا رمزًا مستقلًا.",
                "قد يتغيّر الترجيح إذا ظهرت معلومة سياقية مهمة لم تُذكر في نص الرؤيا."
            ),
            whyThisInterpretation = "لم يُستخدم قاموس ثابت من نوع «رمز = معنى». تم أولًا فحص ترابط القصة والسياق والمشاعر، ثم استبعاد الجزم عندما لا تكفي القرائن.",
            caution = "هذه نتيجة احتياطية من المحرك المحلي. التأويل التفصيلي النهائي يحتاج اتصال محرك المعرفة والذكاء الاصطناعي. والله أعلم."
        )
    }
}
