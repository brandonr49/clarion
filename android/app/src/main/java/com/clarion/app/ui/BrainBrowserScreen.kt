package com.clarion.app.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.clarion.app.data.ApiClient
import com.clarion.app.data.BrainFileResponse
import com.clarion.app.data.BrainTreeEntry
import com.clarion.app.data.ServerConfig
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BrainBrowserScreen(serverConfig: ServerConfig) {
    var tree by remember { mutableStateOf<List<BrainTreeEntry>>(emptyList()) }
    var selectedFile by remember { mutableStateOf<BrainFileResponse?>(null) }
    var loading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    val api = remember { ApiClient.create(serverConfig.serverUrl) }

    LaunchedEffect(Unit) {
        loading = true
        try {
            val resp = api.getBrainTree()
            tree = resp.tree
        } catch (e: Exception) {
            error = e.message
        }
        loading = false
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 12.dp, vertical = 8.dp),
    ) {
        if (loading) {
            CircularProgressIndicator(modifier = Modifier.padding(16.dp))
        } else if (error != null) {
            Text("Error: $error", color = MaterialTheme.colorScheme.error, fontSize = 14.sp)
        } else if (selectedFile != null) {
            // File viewer
            val file = selectedFile!!
            Row(modifier = Modifier.fillMaxWidth()) {
                TextButton(onClick = { selectedFile = null }) {
                    Text("← Back")
                }
                Spacer(Modifier.weight(1f))
                Text(
                    "${file.line_count} lines",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 12.sp,
                    modifier = Modifier.padding(top = 12.dp),
                )
            }
            Text(
                file.path,
                fontWeight = FontWeight.Bold,
                fontSize = 14.sp,
                modifier = Modifier.padding(bottom = 8.dp),
            )
            HorizontalDivider(color = MaterialTheme.colorScheme.outline)
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState())
                    .padding(top = 8.dp),
            ) {
                Text(
                    file.content,
                    fontSize = 13.sp,
                    fontFamily = FontFamily.Monospace,
                    lineHeight = 18.sp,
                )
            }
        } else {
            // Tree view
            Text(
                "Brain Files",
                fontWeight = FontWeight.Bold,
                fontSize = 16.sp,
                modifier = Modifier.padding(bottom = 8.dp),
            )
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState()),
            ) {
                TreeView(tree, api) { file ->
                    selectedFile = file
                }
            }
        }
    }
}

@Composable
private fun TreeView(
    entries: List<BrainTreeEntry>,
    api: com.clarion.app.data.ClarionApi,
    onFileSelected: (BrainFileResponse) -> Unit,
) {
    val scope = rememberCoroutineScope()

    for (entry in entries) {
        if (entry.type == "directory") {
            var expanded by remember { mutableStateOf(false) }
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { expanded = !expanded }
                    .padding(vertical = 4.dp, horizontal = 4.dp),
            ) {
                Text(
                    if (expanded) "📂" else "📁",
                    fontSize = 14.sp,
                    modifier = Modifier.padding(end = 6.dp),
                )
                Text(
                    "${entry.name}/",
                    fontWeight = FontWeight.SemiBold,
                    fontSize = 14.sp,
                    color = MaterialTheme.colorScheme.onSurface,
                )
                Spacer(Modifier.weight(1f))
                Text(
                    "${entry.file_count} files",
                    fontSize = 11.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            if (expanded) {
                Column(modifier = Modifier.padding(start = 20.dp)) {
                    TreeView(entry.children, api, onFileSelected)
                }
            }
        } else {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable {
                        scope.launch {
                            try {
                                val file = api.getBrainFile(entry.path)
                                onFileSelected(file)
                            } catch (_: Exception) { }
                        }
                    }
                    .padding(vertical = 3.dp, horizontal = 4.dp),
            ) {
                Text("📄", fontSize = 14.sp, modifier = Modifier.padding(end = 6.dp))
                Text(entry.name, fontSize = 13.sp)
                Spacer(Modifier.weight(1f))
                val sizeText = if (entry.size < 1024) "${entry.size}b" else "${entry.size / 1024}kb"
                Text(sizeText, fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}
