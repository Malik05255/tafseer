package com.tafseer.app.ui

import androidx.compose.animation.AnimatedVisibility
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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.Edit
import androidx.compose.material.icons.outlined.KeyboardArrowDown
import androidx.compose.material.icons.outlined.KeyboardArrowUp
import androidx.compose.material.icons.outlined.MenuBook
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
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
    Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        // Render the current screen directly. The text editor keeps its own IME state.
        when (val screenState = state) {
            is TafseerUiState.Writing -> WritingScreen(
                initialDream = screenState.dream,
                onDreamChange = viewModel::updateDream,
                onInterpret = viewModel::startInterpretation
            )
            is TafseerUiState.Analyzing -> AnalysisScreen(
                state = screenState,
                onAnswer = viewModel::answerQuestion
            )
            is TafseerUiState.Result -> ResultScreen(
                result = screenState.result,
                onEdit = viewModel::editCurrentDream,
                onNew = viewModel::interpretAnother
            )
        }
    }
}

@Composable
private fun BrandHeader(modifier: Modifier = Modifier) {
    Row(modifier = modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Box(
            modifier = Modifier.size(46.dp).clip(RoundedCornerShape(15.dp)).background(MaterialTheme.colorScheme.primary),
            contentAlignment = Alignment.Center
        ) {
            Icon(Icons.Outlined.MenuBook, contentDescription = null, tint = MaterialTheme.colorScheme.onPrimary, modifier = Modifier.size(24.dp))
        }
        Spacer(Modifier.width(12.dp))
        Column {
            Text("تفسير HAI", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            Text(
                "تأويل متأنٍ، لا إجابة مستعجلة",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.58f)
            )
        }
    }
}

@Composable
private fun WritingScreen(initialDream: String, onDreamChange: (String) -> Unit, onInterpret: () -> Unit) {
    // Keep the full TextFieldValue locally so Arabic IMEs can preserve composition/cursor state.
    // Mirroring a plain String from StateFlow on every key event can cancel IME composition on some devices.
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
        modifier = Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding().imePadding().padding(horizontal = 20.dp).verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(18.dp)
    ) {
        Spacer(Modifier.height(8.dp))
        BrandHeader()
        Spacer(Modifier.height(8.dp))
        Text("اكتب رؤيتك كما تتذكرها", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        Text(
            "اكتب التفاصيل كما حدثت، حتى التي تبدو غير مهمة. إذا احتاج التحليل معلومة مؤثرة فسيسألك أثناء التفسير فقط.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.66f),
            lineHeight = 23.sp
        )
        OutlinedTextField(
            value = editorValue,
            onValueChange = { updated ->
                editorValue = updated
                onDreamChange(updated.text)
            },
            modifier = Modifier.fillMaxWidth().height(300.dp),
            enabled = true,
            readOnly = false,
            singleLine = false,
            placeholder = { Text("مثال: رأيت أنني في بيت قديم أعرفه، ثم دخل…", color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.38f)) },
            shape = RoundedCornerShape(24.dp),
            keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences),
            supportingText = {
                Text(
                    text = if (dream.isBlank()) "كلما كان السرد أدق كان التحليل أفضل." else "${dream.length} حرف",
                    modifier = Modifier.fillMaxWidth(),
                    textAlign = TextAlign.End
                )
            }
        )
        Button(
            onClick = onInterpret,
            enabled = canSubmit,
            modifier = Modifier.fillMaxWidth().height(58.dp),
            shape = RoundedCornerShape(18.dp)
        ) {
            Icon(Icons.Outlined.AutoAwesome, contentDescription = null)
            Spacer(Modifier.width(9.dp))
            Text("تفسير", fontWeight = FontWeight.Bold, fontSize = 17.sp)
        }
        Text(
            "لا يُبنى على التأويل حكم شرعي أو قرار مصيري. النتيجة اجتهادية وليست معرفة بالغيب.",
            modifier = Modifier.fillMaxWidth().padding(bottom = 18.dp),
            textAlign = TextAlign.Center,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.48f),
            lineHeight = 19.sp
        )
    }
}

@Composable
private fun AnalysisScreen(state: TafseerUiState.Analyzing, onAnswer: (String) -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding().imePadding().padding(horizontal = 20.dp).verticalScroll(rememberScrollState()),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Spacer(Modifier.height(8.dp))
        BrandHeader()
        Spacer(Modifier.height(54.dp))
        Box(contentAlignment = Alignment.Center) {
            CircularProgressIndicator(
                progress = { state.progress / 100f },
                modifier = Modifier.size(154.dp),
                strokeWidth = 8.dp,
                trackColor = MaterialTheme.colorScheme.surfaceVariant
            )
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text("${state.progress}%", fontSize = 38.sp, fontWeight = FontWeight.Bold)
                Text(
                    if (state.question == null) "يحلّل" else "بانتظارك",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.55f)
                )
            }
        }
        Spacer(Modifier.height(30.dp))
        Text(state.stage.title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(8.dp))
        Text(
            state.stageDetail,
            textAlign = TextAlign.Center,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.62f),
            lineHeight = 22.sp
        )
        Spacer(Modifier.height(24.dp))
        LinearProgressIndicator(
            progress = { state.progress / 100f },
            modifier = Modifier.fillMaxWidth().height(5.dp).clip(CircleShape),
            trackColor = MaterialTheme.colorScheme.surfaceVariant
        )
        AnimatedVisibility(visible = state.question != null) {
            state.question?.let { question ->
                ClarifyingQuestionCard(question, onAnswer, Modifier.padding(top = 28.dp, bottom = 24.dp))
            }
        }
        if (state.question == null) {
            Spacer(Modifier.height(34.dp))
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface), shape = RoundedCornerShape(20.dp)) {
                Row(modifier = Modifier.padding(18.dp), verticalAlignment = Alignment.Top) {
                    Icon(Icons.Outlined.AutoAwesome, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                    Spacer(Modifier.width(12.dp))
                    Text(
                        "لا نسرّع العداد على حساب التحليل. قد يتوقف إذا ظهرت معلومة ناقصة يمكن أن تغيّر الترجيح.",
                        style = MaterialTheme.typography.bodyMedium,
                        lineHeight = 22.sp,
                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.68f)
                    )
                }
            }
        }
    }
}

@Composable
private fun ClarifyingQuestionCard(question: ClarifyingQuestion, onAnswer: (String) -> Unit, modifier: Modifier = Modifier) {
    var textAnswer by remember(question.id) { mutableStateOf(TextFieldValue()) }
    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        shape = RoundedCornerShape(24.dp),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(modifier = Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(13.dp)) {
            Text("معلومة واحدة قبل أن نكمل", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
            Text(question.title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            Text(
                question.explanation,
                style = MaterialTheme.typography.bodyMedium,
                lineHeight = 22.sp,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.66f)
            )
            question.options.forEach { option ->
                OutlinedButton(
                    onClick = { onAnswer(option.label) },
                    modifier = Modifier.fillMaxWidth().height(50.dp),
                    shape = RoundedCornerShape(15.dp)
                ) { Text(option.label) }
            }
            if (question.allowText) {
                OutlinedTextField(
                    value = textAnswer,
                    onValueChange = { textAnswer = it },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = true,
                    readOnly = false,
                    placeholder = { Text(question.textHint) },
                    shape = RoundedCornerShape(16.dp),
                    minLines = 3
                )
                Button(
                    onClick = { onAnswer(textAnswer.text) },
                    enabled = textAnswer.text.isNotBlank(),
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(15.dp)
                ) { Text("متابعة التحليل") }
            }
        }
    }
}

@Composable
private fun ResultScreen(result: InterpretationResult, onEdit: () -> Unit, onNew: () -> Unit) {
    var whyExpanded by remember { mutableStateOf(false) }
    var alternativesExpanded by remember { mutableStateOf(false) }
    Column(
        modifier = Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding().padding(horizontal = 20.dp).verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Spacer(Modifier.height(8.dp))
        BrandHeader()
        Spacer(Modifier.height(10.dp))
        Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
            Column(modifier = Modifier.weight(1f)) {
                Text("تفسير رؤيتك", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                Text("والله أعلم", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.primary)
            }
            IconButton(onClick = onEdit) { Icon(Icons.Outlined.Edit, contentDescription = "تعديل الرؤيا") }
        }
        Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer), shape = RoundedCornerShape(18.dp)) {
            Row(modifier = Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Outlined.CheckCircle, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                Spacer(Modifier.width(10.dp))
                Column {
                    Text("طبيعة المنام", style = MaterialTheme.typography.labelMedium)
                    Text(result.nature.label, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                }
            }
        }
        Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface), shape = RoundedCornerShape(24.dp)) {
            Text(result.interpretation, modifier = Modifier.padding(20.dp), style = MaterialTheme.typography.bodyLarge, lineHeight = 29.sp)
        }
        if (result.evidence.isNotEmpty()) {
            Text("أبرز ما بُني عليه الترجيح", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface), shape = RoundedCornerShape(20.dp)) {
                Column(modifier = Modifier.padding(horizontal = 18.dp)) {
                    result.evidence.forEachIndexed { index, point ->
                        Column(modifier = Modifier.padding(vertical = 14.dp)) {
                            Text(point.title, fontWeight = FontWeight.SemiBold)
                            Spacer(Modifier.height(4.dp))
                            Text(point.explanation, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.65f), lineHeight = 21.sp)
                        }
                        if (index != result.evidence.lastIndex) HorizontalDivider()
                    }
                }
            }
        }
        ExpandableResultCard("لماذا هذا التفسير؟", whyExpanded, { whyExpanded = !whyExpanded }) {
            Text(result.whyThisInterpretation, style = MaterialTheme.typography.bodyMedium, lineHeight = 23.sp)
        }
        if (result.alternatives.isNotEmpty()) {
            ExpandableResultCard("احتمالات أخرى لم تُهمل", alternativesExpanded, { alternativesExpanded = !alternativesExpanded }) {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    result.alternatives.forEach { item ->
                        Row(verticalAlignment = Alignment.Top) {
                            Text("•", modifier = Modifier.padding(end = 8.dp))
                            Text(item, style = MaterialTheme.typography.bodyMedium, lineHeight = 22.sp)
                        }
                    }
                }
            }
        }
        Text(
            result.caution,
            modifier = Modifier.fillMaxWidth(),
            textAlign = TextAlign.Center,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.52f),
            lineHeight = 19.sp
        )
        Button(onClick = onNew, modifier = Modifier.fillMaxWidth().height(54.dp), shape = RoundedCornerShape(17.dp)) {
            Icon(Icons.Outlined.Refresh, contentDescription = null)
            Spacer(Modifier.width(8.dp))
            Text("رؤيا جديدة", fontWeight = FontWeight.Bold)
        }
        Spacer(Modifier.height(18.dp))
    }
}

@Composable
private fun ExpandableResultCard(title: String, expanded: Boolean, onToggle: () -> Unit, content: @Composable () -> Unit) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface), shape = RoundedCornerShape(20.dp)) {
        Column {
            TextButton(
                onClick = onToggle,
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.textButtonColors(contentColor = MaterialTheme.colorScheme.onSurface)
            ) {
                Text(title, modifier = Modifier.weight(1f), textAlign = TextAlign.Start, fontWeight = FontWeight.SemiBold)
                Icon(if (expanded) Icons.Outlined.KeyboardArrowUp else Icons.Outlined.KeyboardArrowDown, contentDescription = null)
            }
            AnimatedVisibility(visible = expanded) {
                Column(modifier = Modifier.padding(start = 18.dp, end = 18.dp, bottom = 18.dp)) { content() }
            }
        }
    }
}
