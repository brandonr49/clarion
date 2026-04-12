package com.clarion.app.widget

import android.content.Context
import com.clarion.app.data.ApiClient
import com.clarion.app.data.NoteCreate
import com.clarion.app.data.NoteCreateResponse
import com.clarion.app.data.QueryRequest
import com.clarion.app.data.QueryResponse
import com.clarion.app.data.ServerConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Shared API helper for widget operations.
 * Widgets can't use ViewModel, so this provides direct API access.
 */
object WidgetApiHelper {
    suspend fun submitNote(context: Context, content: String): Result<NoteCreateResponse> {
        return withContext(Dispatchers.IO) {
            try {
                val config = ServerConfig(context)
                val api = ApiClient.create(config.serverUrl)
                val response = api.createNote(NoteCreate(content = content))
                Result.success(response)
            } catch (e: Exception) {
                Result.failure(e)
            }
        }
    }

    suspend fun submitQuery(context: Context, query: String): Result<QueryResponse> {
        return withContext(Dispatchers.IO) {
            try {
                val config = ServerConfig(context)
                val api = ApiClient.create(config.serverUrl)
                val response = api.query(QueryRequest(query = query))
                Result.success(response)
            } catch (e: Exception) {
                Result.failure(e)
            }
        }
    }
}
