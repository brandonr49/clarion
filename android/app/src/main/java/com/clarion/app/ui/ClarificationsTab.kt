package com.clarion.app.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.clarion.app.data.ApiClient
import com.clarion.app.data.ClarificationItem
import com.clarion.app.data.NoteCreate
import com.clarion.app.data.ServerConfig
import com.clarion.app.viewmodel.NoteViewModel
import kotlinx.coroutines.launch

@Composable
fun ClarificationsTab(
    viewModel: NoteViewModel,
    serverConfig: ServerConfig,
) {
    var clarifications by remember { mutableStateOf<List<ClarificationItem>>(emptyList()) }
    var loading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    val api = remember { ApiClient.create(serverConfig.serverUrl) }

    // Load clarifications on tab open
    LaunchedEffect(Unit) {
        loading = true
        try {
            val resp = api.getClarifications()
            clarifications = resp.clarifications
        } catch (e: Exception) {
            error = e.message
        }
        loading = false
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 16.dp, vertical = 8.dp),
    ) {
        Row(modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp)) {
            Text(
                "Pending Questions",
                fontWeight = FontWeight.Bold,
                fontSize = 16.sp,
            )
            Spacer(Modifier.weight(1f))
            TextButton(onClick = {
                scope.launch {
                    loading = true
                    try {
                        clarifications = api.getClarifications().clarifications
                    } catch (e: Exception) {
                        error = e.message
                    }
                    loading = false
                }
            }) {
                Text("Refresh")
            }
        }

        if (loading) {
            CircularProgressIndicator(modifier = Modifier.padding(16.dp))
        } else if (error != null) {
            Text("Error: $error", color = MaterialTheme.colorScheme.error, fontSize = 14.sp)
        } else if (clarifications.isEmpty()) {
            Text(
                "No pending questions. The brain will ask when it needs more context.",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 14.sp,
                modifier = Modifier.padding(16.dp),
            )
        } else {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState()),
            ) {
                clarifications.forEach { clar ->
                    ClarificationCard(clar, api, viewModel) {
                        // After answering, refresh the list
                        scope.launch {
                            try {
                                clarifications = api.getClarifications().clarifications
                            } catch (_: Exception) {}
                        }
                    }
                    Spacer(modifier = Modifier.height(8.dp))
                }
            }
        }
    }
}

@Composable
private fun ClarificationCard(
    clar: ClarificationItem,
    api: com.clarion.app.data.ClarionApi,
    viewModel: NoteViewModel,
    onAnswered: () -> Unit,
) {
    var answer by remember { mutableStateOf("") }
    var submitting by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant,
        ),
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(
                clar.question,
                fontWeight = FontWeight.SemiBold,
                fontSize = 14.sp,
                color = MaterialTheme.colorScheme.primary,
            )

            Spacer(modifier = Modifier.height(8.dp))

            OutlinedTextField(
                value = answer,
                onValueChange = { answer = it },
                modifier = Modifier.fillMaxWidth(),
                placeholder = { Text("Your answer...") },
                singleLine = false,
                minLines = 2,
                colors = OutlinedTextFieldDefaults.colors(
                    focusedContainerColor = MaterialTheme.colorScheme.surface,
                    unfocusedContainerColor = MaterialTheme.colorScheme.surface,
                ),
            )

            Spacer(modifier = Modifier.height(8.dp))

            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                Button(
                    onClick = {
                        if (answer.isNotBlank() && !submitting) {
                            submitting = true
                            scope.launch {
                                try {
                                    api.createNote(NoteCreate(
                                        content = answer.trim(),
                                        metadata = mapOf("clarification_id" to clar.id),
                                    ))
                                    onAnswered()
                                } catch (_: Exception) {}
                                submitting = false
                            }
                        }
                    },
                    enabled = answer.isNotBlank() && !submitting,
                ) {
                    Text(if (submitting) "Sending..." else "Answer")
                }
            }
        }
    }
}
