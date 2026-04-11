package com.clarion.app.ui

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.serialization.json.*

@Composable
fun ViewRenderer(
    view: JsonObject,
    onInteraction: (String) -> Unit = {},
) {
    val type = view["type"]?.jsonPrimitive?.contentOrNull ?: "markdown"

    Card(
        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface,
        ),
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            // Title
            val title = view["title"]?.jsonPrimitive?.contentOrNull
            if (title != null) {
                Text(
                    title,
                    fontWeight = FontWeight.Bold,
                    fontSize = 16.sp,
                    color = MaterialTheme.colorScheme.onSurface,
                )
                Spacer(modifier = Modifier.height(8.dp))
            }

            when (type) {
                "checklist" -> ChecklistRenderer(view, onInteraction)
                "table" -> TableRenderer(view)
                "key_value" -> KeyValueRenderer(view)
                "markdown" -> MarkdownRenderer(view)
                "composite" -> CompositeRenderer(view, onInteraction)
                else -> Text("Unknown view type: $type", fontSize = 12.sp)
            }
        }
    }
}

@Composable
private fun ChecklistRenderer(view: JsonObject, onInteraction: (String) -> Unit) {
    val sections = view["sections"]?.jsonArray ?: return

    sections.forEach { sectionEl ->
        val section = sectionEl.jsonObject
        val heading = section["heading"]?.jsonPrimitive?.contentOrNull
        if (heading != null) {
            Text(
                heading,
                fontWeight = FontWeight.SemiBold,
                fontSize = 14.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = 8.dp, bottom = 4.dp),
            )
        }

        val items = section["items"]?.jsonArray ?: return@forEach
        items.forEach { itemEl ->
            val item = itemEl.jsonObject
            val label = item["label"]?.jsonPrimitive?.contentOrNull ?: ""
            val checked = item["checked"]?.jsonPrimitive?.booleanOrNull ?: false

            var isChecked by remember(label) { mutableStateOf(checked) }

            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 2.dp),
            ) {
                Checkbox(
                    checked = isChecked,
                    onCheckedChange = { newValue ->
                        isChecked = newValue
                        val action = if (newValue) "completed" else "uncompleted"
                        onInteraction("$action: $label")
                    },
                    colors = CheckboxDefaults.colors(
                        checkedColor = MaterialTheme.colorScheme.primary,
                    ),
                )
                Text(
                    label,
                    fontSize = 14.sp,
                    color = if (isChecked)
                        MaterialTheme.colorScheme.onSurfaceVariant
                    else
                        MaterialTheme.colorScheme.onSurface,
                )
            }
        }
    }
}

@Composable
private fun TableRenderer(view: JsonObject) {
    val headers = view["headers"]?.jsonArray?.map { it.jsonPrimitive.content } ?: emptyList()
    val rows = view["rows"]?.jsonArray ?: return

    Column(modifier = Modifier.horizontalScroll(rememberScrollState())) {
        // Header
        if (headers.isNotEmpty()) {
            Row(modifier = Modifier.padding(bottom = 4.dp)) {
                headers.forEach { header ->
                    Text(
                        header,
                        fontWeight = FontWeight.Bold,
                        fontSize = 13.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.width(120.dp).padding(4.dp),
                    )
                }
            }
            HorizontalDivider(color = MaterialTheme.colorScheme.outline)
        }

        // Rows
        rows.forEach { rowEl ->
            val cells = rowEl.jsonArray
            Row(modifier = Modifier.padding(vertical = 2.dp)) {
                cells.forEach { cell ->
                    Text(
                        cell.jsonPrimitive.contentOrNull ?: "",
                        fontSize = 13.sp,
                        modifier = Modifier.width(120.dp).padding(4.dp),
                    )
                }
            }
        }
    }
}

@Composable
private fun KeyValueRenderer(view: JsonObject) {
    val pairs = view["pairs"]?.jsonArray ?: return

    pairs.forEach { pairEl ->
        val pair = pairEl.jsonObject
        val key = pair["key"]?.jsonPrimitive?.contentOrNull ?: ""
        val value = pair["value"]?.jsonPrimitive?.contentOrNull ?: ""

        Row(
            modifier = Modifier.fillMaxWidth().padding(vertical = 3.dp),
        ) {
            Text(
                key,
                fontWeight = FontWeight.SemiBold,
                fontSize = 13.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.width(120.dp),
            )
            Text(value, fontSize = 14.sp)
        }
    }
}

@Composable
private fun MarkdownRenderer(view: JsonObject) {
    val content = view["content"]?.jsonPrimitive?.contentOrNull ?: ""
    // Simple markdown rendering — just show as text for now
    // A proper markdown library can be added later
    Text(content, fontSize = 14.sp, lineHeight = 20.sp)
}

@Composable
private fun CompositeRenderer(view: JsonObject, onInteraction: (String) -> Unit) {
    val children = view["children"]?.jsonArray ?: return

    children.forEach { childEl ->
        val child = childEl.jsonObject
        ViewRenderer(view = child, onInteraction = onInteraction)
        Spacer(modifier = Modifier.height(8.dp))
    }
}
