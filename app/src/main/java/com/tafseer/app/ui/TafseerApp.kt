package com.tafseer.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
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
import androidx.compose.material.icons.outlined.HelpOutline
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
        Text("اكتب رؤياك", style = MaterialTheme.typography.headlineLarge)

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
                    "اكتب المنام كما تتذكره…",
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.40f)
                )
            },
            textStyle = MaterialTheme.typography.bodyLarge,
            shape = RoundedCornerShape(22.dp),
            keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences)
        )

        Text(
            text = "${dream.length} حرف",
            modifier = Modifier.fillMaxWidth(),
            textAlign = TextAlign.End,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.52f)
        )

        if (error != null) ErrorBanner(error)

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
                "فسّر الرؤيا",
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
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 14.dp),
            verticalAlignment = Alignment.Top
        ) {
            Icon(
                imageVector = Icons.Outlined.ErrorOutline,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.error,
                modifier = Modifier
                    .padding(top = 2.dp)
                    .size(20.dp)
            )
            Spacer(Modifier.width(10.dp))
            Text(
                text = message,
                modifier = Modifier.weight(1f),
                style = MaterialTheme.typography.bodyMedium.copy(lineHeight = 24.sp),
                textAlign = TextAlign.Start,
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

        if (state.question == null) {
            Spacer(Modifier.height(54.dp))
            Box(contentAlignment = Alignment.Center) {
                CircularProgressIndicator(
                    progress = { state.progress / 100f },
                    modifier = Modifier.size(118.dp),
                    strokeWidth = 7.dp,
                    trackColor = MaterialTheme.colorScheme.surfaceVariant
                )
                Text(
                    "${state.progress}%",
                    fontSize = 28.sp,
                    fontWeight = FontWeight.Bold
                )
            }
            Spacer(Modifier.height(24.dp))
            Text(
                text = state.stage.title,
                style = MaterialTheme.typography.titleLarge,
                textAlign = TextAlign.Center
            )
            Spacer(Modifier.height(18.dp))
        } else {
            Spacer(Modifier.height(32.dp))
            Text(
                text = "سؤال قبل التفسير",
                style = MaterialTheme.typography.headlineSmall,
                modifier = Modifier.fillMaxWidth(),
                textAlign = TextAlign.Start
            )
            Spacer(Modifier.height(14.dp))
        }

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
                modifier = Modifier.padding(top = 22.dp, bottom = 24.dp)
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
            verticalArrangement = Arrangement.spacedBy(14.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.Top
            ) {
                Surface(
                    modifier = Modifier.size(40.dp),
                    shape = RoundedCornerShape(13.dp),
                    color = MaterialTheme.colorScheme.primaryContainer
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Icon(
                            imageVector = Icons.Outlined.HelpOutline,
                            contentDescription = null,
                            tint = MaterialTheme.colorScheme.primary,
                            modifier = Modifier.size(21.dp)
                        )
                    }
                }
                Spacer(Modifier.width(12.dp))
                Text(
                    text = question.title,
                    modifier = Modifier.weight(1f),
                    style = MaterialTheme.typography.titleMedium.copy(lineHeight = 30.sp),
                    textAlign = TextAlign.Start
                )
            }

            question.options.forEach { option ->
                OutlinedButton(
                    onClick = { onAnswer(option.label) },
                    modifier = Modifier
                        .fillMaxWidth()
                        .defaultMinSize(minHeight = 54.dp),
                    shape = RoundedCornerShape(15.dp),
                    contentPadding = PaddingValues(horizontal = 14.dp, vertical = 13.dp)
                ) {
                    Text(
                        text = option.label,
                        modifier = Modifier.fillMaxWidth(),
                        textAlign = TextAlign.Center,
                        style = MaterialTheme.typography.bodyMedium.copy(lineHeight = 24.sp),
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
                    textStyle = MaterialTheme.typography.bodyMedium.copy(lineHeight = 25.sp),
                    shape = RoundedCornerShape(16.dp)
                )

                Button(
                    onClick = { onAnswer(textAnswer.text) },
                    enabled = textAnswer.text.isNotBlank(),
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(54.dp),
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
    var sourcesExpanded by remember { mutableStateOf(true) }
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
            Text("التفسير", style = MaterialTheme.typography.headlineSmall)
            Spacer(Modifier.weight(1f))
            IconButton(onClick = onEdit) {
                Icon(Icons.Outlined.Edit, contentDescription = "تعديل الرؤيا")
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
                style = MaterialTheme.typography.bodyLarge,
                textAlign = TextAlign.Start
            )
        }

        if (result.references.isNotEmpty()) {
            DisclosureCard(
                title = "الاستدلال",
                expanded = sourcesExpanded,
                onToggle = { sourcesExpanded = !sourcesExpanded }
            ) {
                result.references.forEachIndexed { index, source ->
                    Column(modifier = Modifier.padding(vertical = 9.dp)) {
                        Text(
                            text = source.claim,
                            modifier = Modifier.fillMaxWidth(),
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.SemiBold,
                            textAlign = TextAlign.Start
                        )
                        Spacer(Modifier.height(7.dp))
                        Surface(
                            shape = RoundedCornerShape(50.dp),
                            color = MaterialTheme.colorScheme.primaryContainer
                        ) {
                            Text(
                                text = relationLabel(source.relation),
                                modifier = Modifier.padding(horizontal = 9.dp, vertical = 4.dp),
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onPrimaryContainer
                            )
                        }
                        Spacer(Modifier.height(7.dp))
                        Text(
                            text = source.explanation,
                            style = MaterialTheme.typography.bodySmall,
                            textAlign = TextAlign.Start,
                            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.68f)
                        )
                        if (source.relation != "contextual" && source.sourceRef.isNotBlank()) {
                            Spacer(Modifier.height(5.dp))
                            Text(
                                text = "${source.sourceTitle} — ${source.sourceRef}",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.primary
                            )
                        }
                    }
                    if (index != result.references.lastIndex) HorizontalDivider()
                }
            }
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
                            fontWeight = FontWeight.SemiBold,
                            textAlign = TextAlign.Start
                        )
                        Text(
                            text = point.explanation,
                            style = MaterialTheme.typography.bodySmall,
                            textAlign = TextAlign.Start,
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
                    style = MaterialTheme.typography.bodyMedium,
                    textAlign = TextAlign.Start
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
                            style = MaterialTheme.typography.bodyMedium,
                            textAlign = TextAlign.Start
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
            Icon(Icons.Outlined.Refresh, contentDescription = null, modifier = Modifier.size(21.dp))
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
                modifier = Modifier.fillMaxWidth(),
                contentPadding = PaddingValues(horizontal = 16.dp, vertical = 11.dp)
            ) {
                Text(
                    text = title,
                    modifier = Modifier.weight(1f),
                    textAlign = TextAlign.Start,
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.onSurface
                )
                Icon(
                    imageVector = if (expanded) Icons.Outlined.KeyboardArrowUp else Icons.Outlined.KeyboardArrowDown,
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

private fun relationLabel(relation: String): String = when (relation) {
    "direct" -> "نص مباشر"
    "semantic" -> "استئناس بالمعنى"
    else -> "قرينة سياقية"
}
