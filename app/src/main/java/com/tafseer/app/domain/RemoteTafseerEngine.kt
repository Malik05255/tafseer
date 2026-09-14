package com.tafseer.app.domain

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

class AiProviderUnavailableException(message: String) : IOException(message)

class RemoteTafseerEngine(
    private val baseUrl: String
) : TafseerEngine {

    override suspend fun interpret(
        dream: String,
        onProgress: suspend (progress: Int, stage: AnalysisStage) -> Unit,
        ask: suspend (ClarifyingQuestion) -> QuestionAnswer
    ): InterpretationResult = coroutineScope {
        ensureProviderReady()

        val answers = mutableListOf<QuestionAnswer>()
        var progress = 0

        while (true) {
            val ceiling = minOf(88, 34 + answers.size * 16)
            val request = async(Dispatchers.IO) { postStep(dream, answers) }

            while (!request.isCompleted && progress < ceiling) {
                onProgress(progress, stageFor(progress))
                delay(90L)
                progress += 1
            }

            val response = request.await()
            val checkpoint = response.optInt("progress_checkpoint", ceiling).coerceIn(progress, 96)
            while (progress < checkpoint) {
                onProgress(progress, stageFor(progress))
                delay(18L)
                progress += 1
            }

            when (response.getString("status")) {
                "question" -> {
                    val question = parseQuestion(response.getJSONObject("question"))
                    val answer = ask(question)
                    answers += answer
                    progress = maxOf(progress, checkpoint)
                }

                "complete" -> {
                    val result = parseResult(response.getJSONObject("result"))
                    while (progress <= 100) {
                        onProgress(progress, stageFor(progress))
                        if (progress < 100) delay(16L)
                        progress += 1
                    }
                    return@coroutineScope result
                }

                "error" -> {
                    val message = response.optString(
                        "message",
                        "تعذر إكمال التحليل تقنيًا. حاول مرة أخرى."
                    )
                    throw IOException(message)
                }

                else -> throw IOException("Unknown Tafseer API state")
            }
        }
        @Suppress("UNREACHABLE_CODE")
        error("Unreachable")
    }

    private suspend fun ensureProviderReady() = withContext(Dispatchers.IO) {
        val endpoint = baseUrl.trimEnd('/') + "/health"
        val connection = (URL(endpoint).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 12_000
            readTimeout = 20_000
            setRequestProperty("Accept", "application/json")
        }
        val code = connection.responseCode
        val stream = if (code in 200..299) connection.inputStream else connection.errorStream
        val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
        connection.disconnect()
        if (code !in 200..299) throw IOException("Tafseer health HTTP $code")
        if (text.isBlank()) throw IOException("Tafseer health returned an empty response")

        val json = JSONObject(text)
        if (!json.optBoolean("ai_ready", false)) {
            throw AiProviderUnavailableException("AI provider is not configured")
        }
    }

    private suspend fun postStep(dream: String, answers: List<QuestionAnswer>): JSONObject = withContext(Dispatchers.IO) {
        val endpoint = baseUrl.trimEnd('/') + "/v1/interpret"
        val connection = (URL(endpoint).openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 15_000
            readTimeout = 80_000
            doOutput = true
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
            setRequestProperty("Accept", "application/json")
        }

        val body = JSONObject().apply {
            put("dream", dream)
            put("answers", JSONArray().apply {
                answers.forEach { answer ->
                    put(JSONObject().apply {
                        put("question_id", answer.questionId)
                        put("question_text", answer.questionText)
                        put("value", answer.value)
                    })
                }
            })
        }.toString()

        connection.outputStream.bufferedWriter(Charsets.UTF_8).use { it.write(body) }
        val code = connection.responseCode
        val stream = if (code in 200..299) connection.inputStream else connection.errorStream
        val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
        connection.disconnect()

        if (code == 503 && text.contains("ai_provider_not_configured")) {
            throw AiProviderUnavailableException("AI provider is not configured")
        }
        if (code !in 200..299) throw IOException("Tafseer API HTTP $code: ${text.take(180)}")
        if (text.isBlank()) throw IOException("Tafseer API returned an empty response")
        JSONObject(text)
    }

    private fun parseQuestion(json: JSONObject): ClarifyingQuestion {
        val optionsJson = json.optJSONArray("options") ?: JSONArray()
        val options = buildList {
            for (i in 0 until optionsJson.length()) {
                val item = optionsJson.getJSONObject(i)
                add(QuestionOption(item.getString("id"), item.getString("label")))
            }
        }
        return ClarifyingQuestion(
            id = json.getString("id"),
            title = json.getString("title"),
            explanation = json.optString("explanation"),
            options = options,
            allowText = json.optBoolean("allow_text", false),
            textHint = json.optString("text_hint", "اكتب إجابتك هنا…")
        )
    }

    private fun parseResult(json: JSONObject): InterpretationResult {
        val evidenceJson = json.optJSONArray("evidence") ?: JSONArray()
        val evidence = buildList {
            for (i in 0 until evidenceJson.length()) {
                val item = evidenceJson.getJSONObject(i)
                add(EvidencePoint(item.getString("title"), item.getString("explanation")))
            }
        }

        val referencesJson = json.optJSONArray("references") ?: JSONArray()
        val references = buildList {
            for (i in 0 until referencesJson.length()) {
                val item = referencesJson.getJSONObject(i)
                val claim = item.optString("claim").trim()
                val sourceTitle = item.optString("source_title").trim()
                val sourceRef = item.optString("source_ref").trim()
                val relation = item.optString("relation", "semantic").trim()
                val explanation = item.optString("explanation").trim()
                if (claim.isNotBlank() && sourceTitle.isNotBlank() && sourceRef.isNotBlank() && explanation.isNotBlank()) {
                    add(
                        SourceReference(
                            claim = claim,
                            sourceTitle = sourceTitle,
                            sourceRef = sourceRef,
                            relation = relation,
                            explanation = explanation
                        )
                    )
                }
            }
        }

        val alternativesJson = json.optJSONArray("alternatives") ?: JSONArray()
        val alternatives = buildList {
            for (i in 0 until alternativesJson.length()) add(alternativesJson.getString(i))
        }
        val nature = when (json.optString("nature")) {
            "coherent" -> DreamNature.COHERENT
            "daily_thoughts" -> DreamNature.DAILY_THOUGHTS
            "fragmented" -> DreamNature.FRAGMENTED
            "uncertain" -> DreamNature.MIXED
            else -> DreamNature.MIXED
        }
        return InterpretationResult(
            interpretation = json.getString("interpretation"),
            nature = nature,
            evidence = evidence,
            references = references,
            alternatives = alternatives,
            whyThisInterpretation = json.optString("why_this_interpretation"),
            caution = json.optString("caution", "هذا تأويل اجتهادي وليس حكمًا يقينيًا، والله أعلم.")
        )
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
}