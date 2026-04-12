package com.clarion.app.ui

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.serialization.json.*

@Composable
fun ViewRenderer(
    view: JsonObject,
    onInteraction: (String) -> Unit = {},
) {
    val type = view["type"]?.jsonPrimitive?.contentOrNull ?: "markdown"
    val viewTitle = view["title"]?.jsonPrimitive?.contentOrNull ?: ""

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface,
        ),
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
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
                "checklist" -> ChecklistRenderer(view, viewTitle, onInteraction)
                "table" -> TableRenderer(view)
                "key_value" -> KeyValueRenderer(view)
                "markdown" -> MarkdownRenderer(view)
                "composite" -> CompositeRenderer(view, onInteraction)
                else -> MarkdownRenderer(view)
            }
        }
    }
}

@Composable
private fun ChecklistRenderer(view: JsonObject, viewTitle: String, onInteraction: (String) -> Unit) {
    val sections = view["sections"]?.jsonArray ?: return

    sections.forEach { sectionEl ->
        val section = sectionEl.jsonObject
        val heading = section["heading"]?.jsonPrimitive?.contentOrNull
        if (heading != null) {
            Text(
                heading,
                fontWeight = FontWeight.SemiBold,
                fontSize = 14.sp,
                color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.padding(top = 12.dp, bottom = 4.dp),
            )
            HorizontalDivider(
                color = MaterialTheme.colorScheme.outline.copy(alpha = 0.3f),
                modifier = Modifier.padding(bottom = 4.dp),
            )
        }

        val items = section["items"]?.jsonArray ?: return@forEach
        items.forEach { itemEl ->
            val item = itemEl.jsonObject
            val label = item["label"]?.jsonPrimitive?.contentOrNull ?: ""
            val initialChecked = item["checked"]?.jsonPrimitive?.booleanOrNull ?: false

            var isChecked by remember(label) { mutableStateOf(initialChecked) }

            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 1.dp),
            ) {
                Checkbox(
                    checked = isChecked,
                    onCheckedChange = { newValue ->
                        isChecked = newValue
                        val action = if (newValue) "completed" else "uncompleted"
                        // Include context: list name, section, and item
                        val context = listOfNotNull(
                            viewTitle.takeIf { it.isNotBlank() },
                            heading?.takeIf { it.isNotBlank() },
                        ).joinToString(" > ")
                        val contextSuffix = if (context.isNotBlank()) " [from: $context]" else ""
                        onInteraction("$action: $label$contextSuffix")
                    },
                    modifier = Modifier.size(36.dp),
                    colors = CheckboxDefaults.colors(
                        checkedColor = MaterialTheme.colorScheme.primary,
                    ),
                )
                Spacer(modifier = Modifier.width(4.dp))
                Text(
                    label,
                    fontSize = 15.sp,
                    color = if (isChecked)
                        MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f)
                    else
                        MaterialTheme.colorScheme.onSurface,
                    textDecoration = if (isChecked) TextDecoration.LineThrough else null,
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
        if (headers.isNotEmpty()) {
            Row(modifier = Modifier.padding(bottom = 4.dp)) {
                headers.forEach { header ->
                    Text(
                        header,
                        fontWeight = FontWeight.Bold,
                        fontSize = 13.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier
                            .width(120.dp)
                            .padding(4.dp),
                    )
                }
            }
            HorizontalDivider(color = MaterialTheme.colorScheme.outline)
        }

        rows.forEach { rowEl ->
            val cells = rowEl.jsonArray
            Row(modifier = Modifier.padding(vertical = 2.dp)) {
                cells.forEach { cell ->
                    Text(
                        cell.jsonPrimitive.contentOrNull ?: "",
                        fontSize = 13.sp,
                        modifier = Modifier
                            .width(120.dp)
                            .padding(4.dp),
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
            modifier = Modifier
                .fillMaxWidth()
                .padding(vertical = 4.dp),
        ) {
            Text(
                key,
                fontWeight = FontWeight.SemiBold,
                fontSize = 14.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.width(130.dp),
            )
            Text(
                value,
                fontSize = 14.sp,
                color = MaterialTheme.colorScheme.onSurface,
            )
        }
    }
}

@Composable
private fun MarkdownRenderer(view: JsonObject) {
    val content = view["content"]?.jsonPrimitive?.contentOrNull ?: ""
    if (content.isBlank()) return

    // Render markdown as styled text
    val lines = content.split("\n")
    Column {
        for (line in lines) {
            val trimmed = line.trimStart()
            when {
                trimmed.startsWith("### ") -> Text(
                    trimmed.removePrefix("### "),
                    fontWeight = FontWeight.SemiBold,
                    fontSize = 14.sp,
                    modifier = Modifier.padding(top = 8.dp, bottom = 2.dp),
                )
                trimmed.startsWith("## ") -> Text(
                    trimmed.removePrefix("## "),
                    fontWeight = FontWeight.Bold,
                    fontSize = 15.sp,
                    modifier = Modifier.padding(top = 10.dp, bottom = 3.dp),
                )
                trimmed.startsWith("# ") -> Text(
                    trimmed.removePrefix("# "),
                    fontWeight = FontWeight.Bold,
                    fontSize = 17.sp,
                    modifier = Modifier.padding(top = 12.dp, bottom = 4.dp),
                )
                trimmed.startsWith("- ") || trimmed.startsWith("* ") -> {
                    val bullet = trimmed.removePrefix("- ").removePrefix("* ")
                    Row(modifier = Modifier.padding(start = 8.dp, top = 2.dp)) {
                        Text("•  ", fontSize = 14.sp)
                        Text(
                            buildAnnotatedString {
                                renderInlineMarkdown(bullet)
                            },
                            fontSize = 14.sp,
                            lineHeight = 20.sp,
                        )
                    }
                }
                trimmed.isBlank() -> Spacer(modifier = Modifier.height(6.dp))
                else -> Text(
                    buildAnnotatedString {
                        renderInlineMarkdown(trimmed)
                    },
                    fontSize = 14.sp,
                    lineHeight = 20.sp,
                    modifier = Modifier.padding(vertical = 1.dp),
                )
            }
        }
    }
}

private fun androidx.compose.ui.text.AnnotatedString.Builder.renderInlineMarkdown(text: String) {
    var i = 0
    while (i < text.length) {
        when {
            text.startsWith("**", i) -> {
                val end = text.indexOf("**", i + 2)
                if (end != -1) {
                    withStyle(SpanStyle(fontWeight = FontWeight.Bold)) {
                        append(text.substring(i + 2, end))
                    }
                    i = end + 2
                } else {
                    append(text[i])
                    i++
                }
            }
            else -> {
                append(text[i])
                i++
            }
        }
    }
}

@Composable
private fun CompositeRenderer(view: JsonObject, onInteraction: (String) -> Unit) {
    val children = view["children"]?.jsonArray ?: return
    children.forEach { childEl ->
        val child = childEl.jsonObject
        ViewRenderer(view = child, onInteraction = onInteraction)
        Spacer(modifier = Modifier.height(4.dp))
    }
}
