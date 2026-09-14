package com.tafseer.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.weight
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material.icons.outlined.Edit
import androidx.compose.material.icons.outlined.ErrorOutline
import androidx.compose.material.icons.outlined.KeyboardArrowDown
import androidx.compose.material.icons.outlined.KeyboardArrowUp
import androidx.compose.material.icons.outlined.MenuBook
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.tafseer.app.TafseerViewModel
import com.tafseer.app.domain.ClarifyingQuestion
import com.tafseer.app.domain.InterpretationResult
import com.tafseer.app.domain.TafseerUiState

@Composable
fun TafseerApp(viewModel: TafseerViewModel = viewModel()) {
    val state by viewModel.uiState.collectAsState()

    Surface(
        modifier = Modifier.fillMaxSize(),
        color = MaterialTheme.colorScheme.background
    ) {
        when (val current = state) {
            is TafseerUiState.Writing -> WritingScreen(
                initialDream = current.dream,
                error = current.error,
                onDreamChange = viewModel::updateDream,
                onInterpret = viewModel::startInterpretation
            )

            is TafseerUiState.Analyzing -> AnalysisScreen(
                state = current,
                onAnswer = viewModel::answerQuestion
            )

            is TafseerUiState.Result -> ResultScreen(
                result = current.result,
                onEdit = viewModel::editCurrentDream,
                onNew = viewModel::interpretAnother
            )
        }
    }
}

@Composable
private fun BrandHeader() {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            modifier = Modifier
                .size(44.dp)
                .clip(RoundedCornerShape(14.dp))
                .background(MaterialTheme.colorScheme.primary),
            contentAlignment = Alignment.Center
        ) {
            Icon(
                imageVector = Icons.Outlined.MenuBook,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.onPrimary,
                modifier = Modifier.size(23.dp)
            )
        }
        Spacer(Modifier.width(12.dp))
        Text(
            text = "تفسير HAI",
            style = MaterialTheme.typography.titleLarge
        )
    }
}

@Composable
private fun WritingScreen(
    initialDream: String,
    error: String?,
    onDreamChange: (String) -> Unit,
    onInterpret: () -> Unit
) {
    var editorValue by remember {
        mutableStateOf(
            TextFieldValue(
                text = initialDream,
                selection = TextRange(initialDream.length)
            )
        )
    }
    val dream = editorValue.text
    val canSubmit = dream.trim().length >= 8

    Column(
        modifier = Modifier
            .fillMaxSize()
            .statusBarsPadding()
            .navigationBarsPadding()
            .imePadding()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Spacer(Modifier.height(10.dp))
        BrandHeader()
        Spacer(Modifier.height(20.dp))

        Text(
            text = "اكتب رؤياك",
            style = MaterialTheme.typography.headlineLarge
        )

        OutlinedTextField(
            value = editorValue,
            onValueChange = { updated ->
                editorValue = updated
                onDreamChange(updated.text)
            },
            modifier = Modifier.fillMaxWidth(),
            enabled = true,
            readOnly = false,
            singleLine = false,
            minLines = 9,
            maxLines = 12,
            placeholder = {
                Text(
                    text = "اكتب المنام كما تتذكره…",
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.40f)
                )
            },
            textStyle = MaterialTheme.typography.bodyLarge,
            shape = RoundedCornerShape(22.dp),
            keyboardOptions = KeyboardOptions(
                capitalization = KeyboardCapitalization.Sentences
            )
        )

        Text(
            text = "${dream.length} حرف",
            modifier = Modifier.fillMaxWidth(),
            textAlign = TextAlign.End,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.52f)
        )

        if (error != null) {
            ErrorBanner(error)
        }

        Button(
            onClick = onInterpret,
            enabled = canSubmit,
            modifier = Modifier
                .fillMaxWidth()
                .height(58.dp),
            shape = RoundedCornerShape(18.dp)
        ) {
            Icon(
                imageVector = Icons.Outlined.AutoAwesome,
                contentDescription = null,
                modifier = Modifier.size(21.dp)
            )
            Spacer(Modifier.width(9.dp))
            Text(
                text = "فسّر الرؤيا",
                style = MaterialTheme.typography.labelLarge,
                fontWeight = FontWeight.Bold
            )
        }

        Spacer(Modifier.height(20.dp))
    }
}

@Composable
private fun ErrorBanner(message: String) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.error.copy(alpha = 0.08f)
        )
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 13.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                imageVector = Icons.Outlined.ErrorOutline,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.error,
                modifier = Modifier.size(20.dp)
            )
            Spacer(Modifier.width(10.dp))
            Text(
                text = message,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.error
            )
        }
    }
}

@Composable
private fun AnalysisScreen(
    state: TafseerUiState.Analyzing,
    onAnswer: (String) -> Unit
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .statusBarsPadding()
            .navigationBarsPadding()
            .imePadding()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Spacer(Modifier.height(10.dp))
        BrandHeader()
        Spacer(Modifier.height(56.dp))

        Box(contentAlignment = Alignment.Center) {
            CircularProgressIndicator(
                progress = { state.progress / 100f },
                modifier = Modifier.size(126.dp),
                strokeWidth = 7.dp,
                trackColor = MaterialTheme.colorScheme.surfaceVariant
            )
            Text(
                text = "${state.progress}%",
                fontSize = 30.sp,
                fontWeight = FontWeight.Bold
            )
        }

        Spacer(Modifier.height(26.dp))
        Text(
            text = if (state.question == null) state.stage.title else "سؤال للتوضيح",
            style = MaterialTheme.typography.titleLarge,
            textAlign = TextAlign.Center
        )
        Spacer(Modifier.height(18.dp))

        LinearProgressIndicator(
            progress = { state.progress / 100f },
            modifier = Modifier
                .fillMaxWidth()
                .height(5.dp)
                .clip(CircleShape),
            trackColor = MaterialTheme.colorScheme.surfaceVariant
        )

        state.question?.let { question ->
            ClarifyingQuestionCard(
                question = question,
                onAnswer = onAnswer,
                modifier = Modifier.padding(top = 26.dp, bottom = 24.dp)
            )
        }
    }
}

@Composable
private fun ClarifyingQuestionCard(
    question: ClarifyingQuestion,
    onAnswer: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    var textAnswer by remember(question.id) { mutableStateOf(TextFieldValue()) }

    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        shape = RoundedCornerShape(22.dp)
    ) {
        Column(
            modifier = Modifier.padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Text(
                text = question.title,
                style = MaterialTheme.typography.titleMedium
            )

            question.options.forEach { option ->
                OutlinedButton(
                    onClick = { onAnswer(option.label) },
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(52.dp),
                    shape = RoundedCornerShape(15.dp)
                ) {
                    Text(
                        text = option.label,
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.SemiBold
                    )
                }
            }

            if (question.allowText) {
                OutlinedTextField(
                    value = textAnswer,
                    onValueChange = { textAnswer = it },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = true,
                    readOnly = false,
                    minLines = 2,
                    maxLines = 5,
                    placeholder = { Text(question.textHint) },
                    textStyle = MaterialTheme.typography.bodyMedium,
                    shape = RoundedCornerShape(16.dp)
                )

                Button(
                    onClick = { onAnswer(textAnswer.text) },
                    enabled = textAnswer.text.isNotBlank(),
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(52.dp),
                    shape = RoundedCornerShape(15.dp)
                ) {
                    Text("متابعة", fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}

@Composable
private fun ResultScreen(
    result: InterpretationResult,
    onEdit: () -> Unit,
    onNew: () -> Unit
) {
    var whyExpanded by remember { mutableStateOf(false) }
    var evidenceExpanded by remember { mutableStateOf(false) }
    var alternativesExpanded by remember { mutableStateOf(false) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .statusBarsPadding()
            .navigationBarsPadding()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        Spacer(Modifier.height(10.dp))
        BrandHeader()
        Spacer(Modifier.height(18.dp))

        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = "التفسير",
                style = MaterialTheme.typography.headlineSmall
            )
            Spacer(Modifier.weight(1f))
            IconButton(onClick = onEdit) {
                Icon(
                    imageVector = Icons.Outlined.Edit,
                    contentDescription = "تعديل الرؤيا"
                )
            }
        }

        Surface(
            shape = RoundedCornerShape(50.dp),
            color = MaterialTheme.colorScheme.primaryContainer
        ) {
            Text(
                text = result.nature.label,
                modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp),
                style = MaterialTheme.typography.bodySmall,
                fontWeight = FontWeight.SemiBold,
                color = MaterialTheme.colorScheme.onPrimaryContainer
            )
        }

        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
            shape = RoundedCornerShape(22.dp)
        ) {
            Text(
                text = result.interpretation,
                modifier = Modifier.padding(20.dp),
                style = MaterialTheme.typography.bodyLarge
            )
        }

        if (result.evidence.isNotEmpty()) {
            DisclosureCard(
                title = "القرائن",
                expanded = evidenceExpanded,
                onToggle = { evidenceExpanded = !evidenceExpanded }
            ) {
                result.evidence.forEachIndexed { index, point ->
                    Column(modifier = Modifier.padding(vertical = 8.dp)) {
                        Text(
                            text = point.title,
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.SemiBold
                        )
                        Text(
                            text = point.explanation,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.62f)
                        )
                    }
                    if (index != result.evidence.lastIndex) HorizontalDivider()
                }
            }
        }

        if (result.whyThisInterpretation.isNotBlank()) {
            DisclosureCard(
                title = "لماذا؟",
                expanded = whyExpanded,
                onToggle = { whyExpanded = !whyExpanded }
            ) {
                Text(
                    text = result.whyThisInterpretation,
                    style = MaterialTheme.typography.bodyMedium
                )
            }
        }

        if (result.alternatives.isNotEmpty()) {
            DisclosureCard(
                title = "احتمال آخر",
                expanded = alternativesExpanded,
                onToggle = { alternativesExpanded = !alternativesExpanded }
            ) {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    result.alternatives.forEach { item ->
                        Text(
                            text = "• $item",
                            style = MaterialTheme.typography.bodyMedium
                        )
                    }
                }
            }
        }

        Text(
            text = "تأويل اجتهادي، والله أعلم.",
            modifier = Modifier.fillMaxWidth(),
            textAlign = TextAlign.Center,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.52f)
        )

        Button(
            onClick = onNew,
            modifier = Modifier
                .fillMaxWidth()
                .height(56.dp),
            shape = RoundedCornerShape(18.dp)
        ) {
            Icon(
                imageVector = Icons.Outlined.Refresh,
                contentDescription = null,
                modifier = Modifier.size(21.dp)
            )
            Spacer(Modifier.width(8.dp))
            Text("رؤيا جديدة", fontWeight = FontWeight.Bold)
        }

        Spacer(Modifier.height(20.dp))
    }
}

@Composable
private fun DisclosureCard(
    title: String,
    expanded: Boolean,
    onToggle: () -> Unit,
    content: @Composable () -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        shape = RoundedCornerShape(18.dp)
    ) {
        Column {
            TextButton(
                onClick = onToggle,
                modifier = Modifier.fillMaxWidth()
            ) {
                Text(
                    text = title,
                    modifier = Modifier.weight(1f),
                    textAlign = TextAlign.Start,
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.onSurface
                )
                Icon(
                    imageVector = if (expanded) {
                        Icons.Outlined.KeyboardArrowUp
                    } else {
                        Icons.Outlined.KeyboardArrowDown
                    },
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.70f)
                )
            }

            if (expanded) {
                Column(
                    modifier = Modifier.padding(start = 18.dp, end = 18.dp, bottom = 18.dp)
                ) {
                    content()
                }
            }
        }
    }
}
