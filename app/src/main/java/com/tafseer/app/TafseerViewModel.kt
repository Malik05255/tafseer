package com.tafseer.app

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.tafseer.app.domain.AnalysisStage
import com.tafseer.app.domain.ClarifyingQuestion
import com.tafseer.app.domain.LocalTafseerEngine
import com.tafseer.app.domain.QuestionAnswer
import com.tafseer.app.domain.TafseerEngine
import com.tafseer.app.domain.TafseerUiState
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class TafseerViewModel(
    private val engine: TafseerEngine = LocalTafseerEngine()
) : ViewModel() {

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
        }
    }

    fun answerQuestion(value: String) {
        val question = pendingQuestion ?: return
        if (value.isBlank()) return
        pendingAnswer?.complete(QuestionAnswer(question.id, value.trim()))
    }

    fun interpretAnother() {
        pendingAnswer?.cancel()
        pendingAnswer = null
        pendingQuestion = null
        _uiState.value = TafseerUiState.Writing()
    }

    fun editCurrentDream() {
        val current = _uiState.value as? TafseerUiState.Result ?: return
        _uiState.value = TafseerUiState.Writing(current.dream)
    }
}
