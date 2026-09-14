package com.tafseer.app.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

private val LightColors = lightColorScheme(
    primary = Color(0xFF355B46),
    onPrimary = Color.White,
    primaryContainer = Color(0xFFE2ECE5),
    onPrimaryContainer = Color(0xFF173324),
    background = Color(0xFFF8F6F1),
    onBackground = Color(0xFF1B201C),
    surface = Color(0xFFFFFFFF),
    onSurface = Color(0xFF1B201C),
    surfaceVariant = Color(0xFFF0ECE5),
    outline = Color(0xFFC9C2B8),
    error = Color(0xFFA23D37)
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFFB7D2BF),
    onPrimary = Color(0xFF163323),
    primaryContainer = Color(0xFF284534),
    onPrimaryContainer = Color(0xFFDCEADF),
    background = Color(0xFF151815),
    onBackground = Color(0xFFE9ECE8),
    surface = Color(0xFF1D211D),
    onSurface = Color(0xFFE9ECE8),
    surfaceVariant = Color(0xFF282D28),
    outline = Color(0xFF8C958D),
    error = Color(0xFFFFB4AB)
)

private val TafseerTypography = Typography(
    headlineLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Bold,
        fontSize = 32.sp,
        lineHeight = 40.sp
    ),
    headlineSmall = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Bold,
        fontSize = 27.sp,
        lineHeight = 35.sp
    ),
    titleLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Bold,
        fontSize = 23.sp,
        lineHeight = 31.sp
    ),
    titleMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.SemiBold,
        fontSize = 19.sp,
        lineHeight = 27.sp
    ),
    bodyLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Normal,
        fontSize = 19.sp,
        lineHeight = 31.sp
    ),
    bodyMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Normal,
        fontSize = 16.sp,
        lineHeight = 25.sp
    ),
    bodySmall = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Normal,
        fontSize = 14.sp,
        lineHeight = 21.sp
    ),
    labelLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.SemiBold,
        fontSize = 16.sp,
        lineHeight = 22.sp
    )
)

@Composable
fun TafseerTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = if (isSystemInDarkTheme()) DarkColors else LightColors,
        typography = TafseerTypography,
        content = content
    )
}
