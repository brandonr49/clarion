package com.clarion.app.viewmodel

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.clarion.app.data.ApiClient
import com.clarion.app.data.ClarionApi
import com.clarion.app.data.NoteCreate
import kotlinx.coroutines.launch

sealed class SubmitState {
    data object Idle : SubmitState()
    data object Submitting : SubmitState()
    data class Success(val noteId: String) : SubmitState()
    data class Error(val message: String) : SubmitState()
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

    var submitState: SubmitState by mutableStateOf(SubmitState.Idle)
        private set

    var connectionState: ConnectionState by mutableStateOf(ConnectionState.Unknown)
        private set

    private var api: ClarionApi? = null
    private var currentUrl: String = ""

    fun updateNoteText(text: String) {
        noteText = text
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
                submitState = SubmitState.Success(response.noteId)
                noteText = ""
                // Reset to idle after brief display
                kotlinx.coroutines.delay(1500)
                submitState = SubmitState.Idle
            } catch (e: Exception) {
                val msg = when {
                    e.message?.contains("Unable to resolve host") == true -> "Cannot reach server"
                    e.message?.contains("Connection refused") == true -> "Server not running"
                    e.message?.contains("timeout") == true -> "Connection timed out"
                    else -> e.message ?: "Unknown error"
                }
                submitState = SubmitState.Error(msg)
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
                val msg = when {
                    e.message?.contains("Unable to resolve host") == true -> "Cannot reach server"
                    e.message?.contains("Connection refused") == true -> "Server not running"
                    else -> e.message ?: "Connection failed"
                }
                connectionState = ConnectionState.Failed(msg)
            }
        }
    }
}
