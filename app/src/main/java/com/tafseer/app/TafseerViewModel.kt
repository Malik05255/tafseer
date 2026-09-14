package com.tafseer.app

import android.app.Application
import android.widget.Toast
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.tafseer.app.domain.AiProviderUnavailableException
import com.tafseer.app.domain.AnalysisStage
import com.tafseer.app.domain.ClarifyingQuestion
import com.tafseer.app.domain.LocalTafseerEngine
import com.tafseer.app.domain.QuestionAnswer
import com.tafseer.app.domain.RemoteTafseerEngine
import com.tafseer.app.domain.TafseerEngine
import com.tafseer.app.domain.TafseerUiState
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class TafseerViewModel(
    application: Application
) : AndroidViewModel(application) {

    // Keep a single Application-only constructor so the default Android ViewModel factory
    // can instantiate this class reliably at app startup.
    private val engine: TafseerEngine = defaultEngine()

    private val _uiState = MutableStateFlow<TafseerUiState>(TafseerUiState.Writing())
    val uiState: StateFlow<TafseerUiState> = _uiState.asStateFlow()

    private var pendingAnswer: CompletableDeferred<QuestionAnswer>? = null
    private var pendingQuestion: ClarifyingQuestion? = null

    fun updateDream(text: String) {
        val current = _uiState.value
        if (current is TafseerUiState.Writing) {
            _uiState.value = current.copy(dream = text)
        }
    }

    fun startInterpretation() {
        val writing = _uiState.value as? TafseerUiState.Writing ?: return
        val dream = writing.dream.trim()
        if (dream.length < 8) return

        viewModelScope.launch {
            _uiState.value = TafseerUiState.Analyzing(
                dream = dream,
                progress = 0,
                stage = AnalysisStage.READING,
                stageDetail = AnalysisStage.READING.detail
            )

            try {
                val result = engine.interpret(
                    dream = dream,
                    onProgress = { progress, stage ->
                        val current = _uiState.value as? TafseerUiState.Analyzing
                        _uiState.value = TafseerUiState.Analyzing(
                            dream = dream,
                            progress = progress,
                            stage = stage,
                            stageDetail = stage.detail,
                            question = current?.question
                        )
                    },
                    ask = { question ->
                        pendingQuestion = question
                        val current = _uiState.value as TafseerUiState.Analyzing
                        _uiState.value = current.copy(question = question)
                        val deferred = CompletableDeferred<QuestionAnswer>()
                        pendingAnswer = deferred
                        val answer = deferred.await()
                        pendingAnswer = null
                        pendingQuestion = null
                        val resumed = _uiState.value as TafseerUiState.Analyzing
                        _uiState.value = resumed.copy(question = null)
                        answer
                    }
                )

                _uiState.value = TafseerUiState.Result(dream, result)
            } catch (exc: AiProviderUnavailableException) {
                clearPendingQuestion()
                _uiState.value = TafseerUiState.Writing(dream)
                Toast.makeText(
                    getApplication(),
                    "محرك التفسير غير مفعّل بعد. فعّل Gemini أو OpenRouter على الخادم ثم أعد المحاولة.",
                    Toast.LENGTH_LONG
                ).show()
            } catch (exc: CancellationException) {
                throw exc
            } catch (exc: Exception) {
                clearPendingQuestion()
                _uiState.value = TafseerUiState.Writing(dream)
                Toast.makeText(
                    getApplication(),
                    "تعذر الاتصال بمحرك التفسير. احتفظنا بنص الرؤيا ويمكنك إعادة المحاولة.",
                    Toast.LENGTH_LONG
                ).show()
            }
        }
    }

    fun answerQuestion(value: String) {
        val question = pendingQuestion ?: return
        if (value.isBlank()) return
        pendingAnswer?.complete(QuestionAnswer(question.id, value.trim()))
    }

    fun interpretAnother() {
        clearPendingQuestion()
        _uiState.value = TafseerUiState.Writing()
    }

    fun editCurrentDream() {
        val current = _uiState.value as? TafseerUiState.Result ?: return
        _uiState.value = TafseerUiState.Writing(current.dream)
    }

    private fun clearPendingQuestion() {
        pendingAnswer?.cancel()
        pendingAnswer = null
        pendingQuestion = null
    }

    companion object {
        private fun defaultEngine(): TafseerEngine {
            val url = BuildConfig.TAFSEER_API_BASE_URL.trim()
            return if (url.isNotBlank()) {
                RemoteTafseerEngine(url)
            } else {
                LocalTafseerEngine()
            }
        }
    }
}
