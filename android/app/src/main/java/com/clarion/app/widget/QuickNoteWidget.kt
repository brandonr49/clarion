package com.clarion.app.widget

import android.content.Context
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.glance.GlanceId
import androidx.glance.GlanceModifier
import androidx.glance.action.actionStartActivity
import androidx.glance.action.clickable
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.GlanceAppWidgetReceiver
import androidx.glance.appwidget.cornerRadius
import androidx.glance.appwidget.provideContent
import androidx.glance.background
import androidx.glance.layout.Alignment
import androidx.glance.layout.Row
import androidx.glance.layout.fillMaxWidth
import androidx.glance.layout.padding
import androidx.glance.text.FontWeight
import androidx.glance.text.Text
import androidx.glance.text.TextStyle
import androidx.glance.unit.ColorProvider

private val BgDark = Color(0xFF141414)
private val TextLight = Color(0xFFE0E0E0)

class QuickNoteWidget : GlanceAppWidget() {
    override suspend fun provideGlance(context: Context, id: GlanceId) {
        provideContent {
            QuickNoteContent()
        }
    }
}

@Composable
private fun QuickNoteContent() {
    Row(
        modifier = GlanceModifier
            .fillMaxWidth()
            .padding(8.dp)
            .background(BgDark)
            .cornerRadius(12.dp)
            .clickable(actionStartActivity(WidgetInputActivity::class.java)),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = "✏️",
            modifier = GlanceModifier.padding(start = 12.dp, end = 8.dp),
        )
        Text(
            text = "Quick Note — tap to type",
            style = TextStyle(
                color = ColorProvider(TextLight),
                fontWeight = FontWeight.Medium,
            ),
            modifier = GlanceModifier.defaultWeight(),
        )
    }
}

class QuickNoteWidgetReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget: GlanceAppWidget = QuickNoteWidget()
}
