package com.clarion.app.widget

import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.clarion.app.ui.theme.ClarionTheme
import kotlinx.coroutines.launch

/**
 * Lightweight activity launched by widgets.
 * Subclassed for note vs query mode.
 */
open class WidgetInputActivity : ComponentActivity() {
    protected open val mode: String = "note"

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            ClarionTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background.copy(alpha = 0.95f),
                ) {
                    WidgetInputScreen(
                        mode = mode,
                        onSubmit = { text -> submitAndClose(text) },
                        onCancel = { finish() },
                    )
                }
            }
        }
    }

    private fun submitAndClose(text: String) {
        val context = this
        kotlinx.coroutines.MainScope().launch {
            try {
                if (mode == "query") {
                    val result = WidgetApiHelper.submitQuery(context, text)
                    result.fold(
                        onSuccess = { resp ->
                            Toast.makeText(context, resp.raw_text.take(100), Toast.LENGTH_LONG).show()
                        },
                        onFailure = { e ->
                            Toast.makeText(context, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                        },
                    )
                } else {
                    val result = WidgetApiHelper.submitNote(context, text)
                    result.fold(
                        onSuccess = {
                            Toast.makeText(context, "Note sent", Toast.LENGTH_SHORT).show()
                        },
                        onFailure = { e ->
                            Toast.makeText(context, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                        },
                    )
                }
            } finally {
                finish()
            }
        }
    }
}

/** Subclass for query mode — registered separately in manifest. */
class WidgetQueryActivity : WidgetInputActivity() {
    override val mode: String = "query"
}

@Composable
private fun WidgetInputScreen(
    mode: String,
    onSubmit: (String) -> Unit,
    onCancel: () -> Unit,
) {
    var text by remember { mutableStateOf("") }
    var submitting by remember { mutableStateOf(false) }
    val focusRequester = remember { FocusRequester() }

    LaunchedEffect(Unit) {
        focusRequester.requestFocus()
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        Text(
            if (mode == "query") "Ask Clarion" else "Quick Note",
            fontSize = 18.sp,
            color = MaterialTheme.colorScheme.onBackground,
        )

        Spacer(modifier = Modifier.height(12.dp))

        OutlinedTextField(
            value = text,
            onValueChange = { text = it },
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(min = 80.dp, max = 200.dp)
                .focusRequester(focusRequester),
            placeholder = {
                Text(if (mode == "query") "Ask something..." else "Type a note...")
            },
            colors = OutlinedTextFieldDefaults.colors(
                focusedContainerColor = MaterialTheme.colorScheme.surfaceVariant,
                unfocusedContainerColor = MaterialTheme.colorScheme.surfaceVariant,
            ),
        )

        Spacer(modifier = Modifier.height(12.dp))

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.End,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            TextButton(onClick = onCancel) {
                Text("Cancel")
            }
            Spacer(modifier = Modifier.width(8.dp))
            Button(
                onClick = {
                    if (text.isNotBlank() && !submitting) {
                        submitting = true
                        onSubmit(text.trim())
                    }
                },
                enabled = text.isNotBlank() && !submitting,
            ) {
                Text(
                    if (submitting) "Sending..."
                    else if (mode == "query") "Ask" else "Submit"
                )
            }
        }
    }
}
