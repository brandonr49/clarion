package com.clarion.app.viewmodel

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import android.app.Application
import androidx.lifecycle.AndroidViewModel
import com.clarion.app.data.ApiClient
import com.clarion.app.data.ClarionApi
import com.clarion.app.data.NoteCreate
import com.clarion.app.data.OfflineQueue
import com.clarion.app.data.QueryRequest
import com.clarion.app.data.QueryResponse
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject

sealed class SubmitState {
    data object Idle : SubmitState()
    data object Submitting : SubmitState()
    data class Success(val noteId: String) : SubmitState()
    data class Error(val message: String) : SubmitState()
}

sealed class QueryState {
    data object Idle : QueryState()
    data object Loading : QueryState()
    data class Result(val rawText: String, val view: JsonObject?) : QueryState()
    data class Error(val message: String) : QueryState()
}

sealed class ConnectionState {
    data object Unknown : ConnectionState()
    data object Testing : ConnectionState()
    data class Connected(val version: String) : ConnectionState()
    data class Failed(val message: String) : ConnectionState()
}

class NoteViewModel(application: Application) : AndroidViewModel(application) {
    var noteText by mutableStateOf("")
        private set

    var queryText by mutableStateOf("")
        private set

    var submitState: SubmitState by mutableStateOf(SubmitState.Idle)
        private set

    var queryState: QueryState by mutableStateOf(QueryState.Idle)
        private set

    var connectionState: ConnectionState by mutableStateOf(ConnectionState.Unknown)
        private set

    var queuedCount by mutableStateOf(0)
        private set

    private var api: ClarionApi? = null
    private var currentUrl: String = ""
    private val offlineQueue = OfflineQueue(application)

    fun updateNoteText(text: String) {
        noteText = text
    }

    fun updateQueryText(text: String) {
        queryText = text
    }

    fun setServerUrl(url: String) {
        if (url != currentUrl) {
            currentUrl = url
            api = ApiClient.create(url)
            connectionState = ConnectionState.Unknown
        }
        queuedCount = offlineQueue.size
    }

    fun submitNote() {
        val content = noteText.trim()
        if (content.isEmpty()) return
        val currentApi = api ?: return

        submitState = SubmitState.Submitting
        viewModelScope.launch {
            val note = NoteCreate(content = content)
            try {
                val response = currentApi.createNote(note)
                submitState = SubmitState.Success(response.note_id)
                noteText = ""

                // Flush any queued notes now that we have connectivity
                flushQueue(currentApi)

                // Poll for processing summary (up to 30s)
                pollForSummary(currentApi, response.note_id)
            } catch (e: Exception) {
                // Server unreachable — queue locally
                offlineQueue.enqueue(note)
                queuedCount = offlineQueue.size
                submitState = SubmitState.Success("Saved offline (${offlineQueue.size} queued)")
                noteText = ""
                kotlinx.coroutines.delay(2000)
                submitState = SubmitState.Idle
            }
        }
    }

    private suspend fun flushQueue(api: ClarionApi) {
        if (offlineQueue.isEmpty) return
        var flushed = 0
        while (!offlineQueue.isEmpty) {
            val note = offlineQueue.removeFirst() ?: break
            try {
                api.createNote(note)
                flushed++
            } catch (_: Exception) {
                // Server went down again — re-queue and stop
                offlineQueue.enqueue(note)
                break
            }
        }
        queuedCount = offlineQueue.size
        if (flushed > 0) {
            submitState = SubmitState.Success("Synced $flushed queued note(s)")
            kotlinx.coroutines.delay(2000)
            submitState = SubmitState.Idle
        }
    }

    private suspend fun pollForSummary(api: ClarionApi, noteId: String) {
        for (i in 0 until 15) {
            kotlinx.coroutines.delay(2000)
            try {
                val status = api.getNoteStatus(noteId)
                if (status.status == "processed" && status.summary != null) {
                    submitState = SubmitState.Success(status.summary)
                    kotlinx.coroutines.delay(3000)
                    submitState = SubmitState.Idle
                    return
                }
                if (status.status == "failed") {
                    submitState = SubmitState.Error(status.summary ?: "Processing failed")
                    return
                }
            } catch (_: Exception) {
                break
            }
        }
        // Timed out waiting for processing — just clear
        submitState = SubmitState.Idle
    }

    fun submitInteraction(content: String) {
        val currentApi = api ?: return
        viewModelScope.launch {
            try {
                // Extract context hint if present: "completed: Item [from: List > Section]"
                val contextMatch = Regex("""\[from: (.+)]$""").find(content)
                val cleanContent = content.replace(Regex("""\s*\[from: .+]$"""), "")
                val metadata = if (contextMatch != null) {
                    mapOf("source_list" to contextMatch.groupValues[1])
                } else {
                    emptyMap()
                }

                currentApi.createNote(NoteCreate(
                    content = cleanContent,
                    input_method = "ui_action",
                    metadata = metadata,
                ))
            } catch (_: Exception) {
                // Silent — interaction feedback is best-effort
            }
        }
    }

    fun submitQuery() {
        val q = queryText.trim()
        if (q.isEmpty()) return
        val currentApi = api ?: return

        queryState = QueryState.Loading
        viewModelScope.launch {
            try {
                val response = currentApi.query(QueryRequest(query = q))
                queryState = QueryState.Result(response.raw_text, response.view)
            } catch (e: Exception) {
                queryState = QueryState.Error(friendlyError(e))
            }
        }
    }

    fun dismissError() {
        submitState = SubmitState.Idle
    }

    fun testConnection() {
        val currentApi = api ?: return
        connectionState = ConnectionState.Testing
        viewModelScope.launch {
            try {
                val status = currentApi.getStatus()
                connectionState = ConnectionState.Connected(status.version)
            } catch (e: Exception) {
                connectionState = ConnectionState.Failed(friendlyError(e))
            }
        }
    }

    private fun friendlyError(e: Exception): String = when {
        e.message?.contains("Unable to resolve host") == true -> "Cannot reach server"
        e.message?.contains("Connection refused") == true -> "Server not running"
        e.message?.contains("timeout") == true -> "Connection timed out"
        else -> e.message ?: "Unknown error"
    }
}
