package com.clarion.app.ui

import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.clarion.app.viewmodel.ConnectionState
import com.clarion.app.viewmodel.NoteViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    viewModel: NoteViewModel,
    currentUrl: String,
    onSave: (String) -> Unit,
    onBack: () -> Unit,
) {
    var urlText by remember { mutableStateOf(currentUrl) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Settings") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.background,
                ),
            )
        },
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .padding(16.dp),
        ) {
            Text(
                "Server URL",
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            Spacer(modifier = Modifier.height(8.dp))

            OutlinedTextField(
                value = urlText,
                onValueChange = { urlText = it },
                modifier = Modifier.fillMaxWidth(),
                placeholder = { Text("http://192.168.1.100:8080") },
                singleLine = true,
                colors = OutlinedTextFieldDefaults.colors(
                    focusedContainerColor = MaterialTheme.colorScheme.surfaceVariant,
                    unfocusedContainerColor = MaterialTheme.colorScheme.surfaceVariant,
                ),
            )

            Spacer(modifier = Modifier.height(16.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Button(
                    onClick = {
                        onSave(urlText)
                        viewModel.setServerUrl(urlText)
                    },
                ) {
                    Text("Save")
                }

                OutlinedButton(
                    onClick = {
                        viewModel.setServerUrl(urlText)
                        viewModel.testConnection()
                    },
                ) {
                    Text("Test Connection")
                }
            }

            Spacer(modifier = Modifier.height(16.dp))

            // Connection status
            when (val state = viewModel.connectionState) {
                is ConnectionState.Unknown -> {}
                is ConnectionState.Testing -> {
                    Text("Testing connection...", fontSize = 14.sp)
                }
                is ConnectionState.Connected -> {
                    Text(
                        "Connected (server v${state.version})",
                        color = MaterialTheme.colorScheme.tertiary,
                        fontSize = 14.sp,
                    )
                }
                is ConnectionState.Failed -> {
                    Text(
                        "Connection failed: ${state.message}",
                        color = MaterialTheme.colorScheme.error,
                        fontSize = 14.sp,
                    )
                }
            }
        }
    }
}
