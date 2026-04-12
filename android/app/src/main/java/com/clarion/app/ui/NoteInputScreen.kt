package com.clarion.app.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.clarion.app.viewmodel.NoteViewModel
import com.clarion.app.viewmodel.QueryState
import com.clarion.app.viewmodel.SubmitState

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NoteInputScreen(
    viewModel: NoteViewModel,
    onNavigateToSettings: () -> Unit,
) {
    var selectedTab by remember { mutableIntStateOf(0) }
    val tabs = listOf("Note", "Ask")

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Clarion", fontSize = 20.sp) },
                actions = {
                    IconButton(onClick = onNavigateToSettings) {
                        Icon(Icons.Default.Settings, contentDescription = "Settings")
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
                .padding(paddingValues),
        ) {
            // Tab row
            TabRow(
                selectedTabIndex = selectedTab,
                containerColor = MaterialTheme.colorScheme.background,
            ) {
                tabs.forEachIndexed { index, title ->
                    Tab(
                        selected = selectedTab == index,
                        onClick = { selectedTab = index },
                        text = { Text(title) },
                    )
                }
            }

            when (selectedTab) {
                0 -> NoteTab(viewModel)
                1 -> QueryTab(viewModel)
            }
        }
    }
}

@Composable
private fun NoteTab(viewModel: NoteViewModel) {
    val focusRequester = remember { FocusRequester() }

    LaunchedEffect(Unit) {
        focusRequester.requestFocus()
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 16.dp, vertical = 8.dp),
    ) {
        OutlinedTextField(
            value = viewModel.noteText,
            onValueChange = { viewModel.updateNoteText(it) },
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f)
                .focusRequester(focusRequester),
            placeholder = { Text("Type a note, thought, or instruction...") },
            colors = OutlinedTextFieldDefaults.colors(
                focusedContainerColor = MaterialTheme.colorScheme.surfaceVariant,
                unfocusedContainerColor = MaterialTheme.colorScheme.surfaceVariant,
                focusedBorderColor = MaterialTheme.colorScheme.primary,
                unfocusedBorderColor = MaterialTheme.colorScheme.outline,
            ),
        )

        Spacer(modifier = Modifier.height(12.dp))

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            when (val state = viewModel.submitState) {
                is SubmitState.Idle -> Spacer(Modifier.weight(1f))
                is SubmitState.Submitting -> Text("Sending...", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 14.sp, modifier = Modifier.weight(1f))
                is SubmitState.Success -> Text(state.noteId, color = MaterialTheme.colorScheme.tertiary, fontSize = 13.sp, modifier = Modifier.weight(1f), maxLines = 2)
                is SubmitState.Error -> Text(state.message, color = MaterialTheme.colorScheme.error, fontSize = 14.sp, modifier = Modifier.weight(1f))
            }

            Button(
                onClick = { viewModel.submitNote() },
                enabled = viewModel.noteText.isNotBlank() && viewModel.submitState !is SubmitState.Submitting,
            ) {
                Text("Submit")
            }
        }

        Spacer(modifier = Modifier.height(8.dp))
    }
}

@Composable
private fun QueryTab(viewModel: NoteViewModel) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 16.dp, vertical = 8.dp),
    ) {
        // Query input
        OutlinedTextField(
            value = viewModel.queryText,
            onValueChange = { viewModel.updateQueryText(it) },
            modifier = Modifier.fillMaxWidth(),
            placeholder = { Text("Ask the brain something...") },
            singleLine = true,
            colors = OutlinedTextFieldDefaults.colors(
                focusedContainerColor = MaterialTheme.colorScheme.surfaceVariant,
                unfocusedContainerColor = MaterialTheme.colorScheme.surfaceVariant,
            ),
        )

        Spacer(modifier = Modifier.height(8.dp))

        Button(
            onClick = { viewModel.submitQuery() },
            enabled = viewModel.queryText.isNotBlank() && viewModel.queryState !is QueryState.Loading,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(if (viewModel.queryState is QueryState.Loading) "Thinking..." else "Ask")
        }

        Spacer(modifier = Modifier.height(12.dp))

        // Response area
        when (val state = viewModel.queryState) {
            is QueryState.Idle -> {}
            is QueryState.Loading -> {
                CircularProgressIndicator(
                    modifier = Modifier.align(Alignment.CenterHorizontally),
                    color = MaterialTheme.colorScheme.primary,
                )
            }
            is QueryState.Error -> {
                Card(
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(
                        state.message,
                        modifier = Modifier.padding(12.dp),
                        color = MaterialTheme.colorScheme.onErrorContainer,
                    )
                }
            }
            is QueryState.Result -> {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f)
                        .verticalScroll(rememberScrollState()),
                ) {
                    if (state.view != null) {
                        ViewRenderer(
                            view = state.view,
                            onInteraction = { content -> viewModel.submitInteraction(content) },
                        )
                    }
                    if (state.rawText.isNotBlank() && state.view == null) {
                        Text(
                            state.rawText,
                            fontSize = 14.sp,
                            modifier = Modifier.padding(8.dp),
                        )
                    }
                }
            }
        }
    }
}
