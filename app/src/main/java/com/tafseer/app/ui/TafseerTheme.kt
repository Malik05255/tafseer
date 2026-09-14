package com.tafseer.app.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val LightColors = lightColorScheme(
    primary = Color(0xFF415A4A),
    onPrimary = Color.White,
    primaryContainer = Color(0xFFDCE8DF),
    onPrimaryContainer = Color(0xFF13251A),
    secondary = Color(0xFF766C57),
    background = Color(0xFFF7F4EE),
    onBackground = Color(0xFF1B1D1A),
    surface = Color(0xFFFFFCF7),
    onSurface = Color(0xFF1B1D1A),
    surfaceVariant = Color(0xFFEDE8DF),
    outline = Color(0xFFB7B0A5),
    error = Color(0xFF9B3A36)
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFFB7CDBD),
    onPrimary = Color(0xFF243A2C),
    background = Color(0xFF171A17),
    onBackground = Color(0xFFE8E6E0),
    surface = Color(0xFF1D211D),
    onSurface = Color(0xFFE8E6E0),
    surfaceVariant = Color(0xFF292E29),
    outline = Color(0xFF8E958F)
)

@Composable
fun TafseerTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = if (isSystemInDarkTheme()) DarkColors else LightColors,
        content = content
    )
}
