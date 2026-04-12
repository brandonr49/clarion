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
import androidx.glance.layout.Column
import androidx.glance.layout.Row
import androidx.glance.layout.Spacer
import androidx.glance.layout.fillMaxSize
import androidx.glance.layout.fillMaxWidth
import androidx.glance.layout.height
import androidx.glance.layout.padding
import androidx.glance.text.FontWeight
import androidx.glance.text.Text
import androidx.glance.text.TextStyle
import androidx.glance.unit.ColorProvider

private val BgDark = Color(0xFF141414)
private val BgField = Color(0xFF1A1A1A)
private val TextWhite = Color(0xFFFFFFFF)
private val TextGray = Color(0xFF888888)

class QueryWidget : GlanceAppWidget() {
    override suspend fun provideGlance(context: Context, id: GlanceId) {
        provideContent {
            QueryWidgetContent()
        }
    }
}

@Composable
private fun QueryWidgetContent() {
    Column(
        modifier = GlanceModifier
            .fillMaxSize()
            .padding(8.dp)
            .background(BgDark)
            .cornerRadius(12.dp)
            .clickable(actionStartActivity(WidgetQueryActivity::class.java)),
    ) {
        Row(
            modifier = GlanceModifier.fillMaxWidth().padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = "🔔 Clarion",
                style = TextStyle(
                    color = ColorProvider(TextWhite),
                    fontWeight = FontWeight.Bold,
                ),
            )
        }

        Spacer(modifier = GlanceModifier.height(4.dp))

        Row(
            modifier = GlanceModifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 8.dp)
                .background(BgField)
                .cornerRadius(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = "🔍  Ask the brain something...",
                style = TextStyle(
                    color = ColorProvider(TextGray),
                ),
                modifier = GlanceModifier.padding(12.dp),
            )
        }
    }
}

class QueryWidgetReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget: GlanceAppWidget = QueryWidget()
}
