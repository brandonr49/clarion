package com.clarion.app.viewmodel

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.clarion.app.data.ApiClient
import com.clarion.app.data.ClarionApi
import com.clarion.app.data.NoteCreate
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

class NoteViewModel : ViewModel() {
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

    private var api: ClarionApi? = null
    private var currentUrl: String = ""

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
    }

    fun submitNote() {
        val content = noteText.trim()
        if (content.isEmpty()) return
        val currentApi = api ?: return

        submitState = SubmitState.Submitting
        viewModelScope.launch {
            try {
                val response = currentApi.createNote(NoteCreate(content = content))
                submitState = SubmitState.Success(response.note_id)
                noteText = ""
                kotlinx.coroutines.delay(1500)
                submitState = SubmitState.Idle
            } catch (e: Exception) {
                submitState = SubmitState.Error(friendlyError(e))
            }
        }
    }

    fun submitInteraction(content: String) {
        val currentApi = api ?: return
        viewModelScope.launch {
            try {
                currentApi.createNote(NoteCreate(
                    content = content,
                    input_method = "ui_action",
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
