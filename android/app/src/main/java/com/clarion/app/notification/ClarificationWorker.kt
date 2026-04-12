package com.clarion.app.notification

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.work.*
import com.clarion.app.MainActivity
import com.clarion.app.data.ApiClient
import com.clarion.app.data.ServerConfig
import java.util.concurrent.TimeUnit

/**
 * Background worker that polls for pending clarifications
 * and shows notifications when the LLM has questions.
 */
class ClarificationWorker(
    context: Context,
    params: WorkerParameters,
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        try {
            val config = ServerConfig(applicationContext)
            val api = ApiClient.create(config.serverUrl)

            val response = api.getClarifications()
            val clarifications = response.clarifications

            if (clarifications.isEmpty()) return Result.success()

            // Check which ones are new (not already notified)
            val prefs = applicationContext.getSharedPreferences(
                "clarion_notifications", Context.MODE_PRIVATE
            )
            val notifiedIds = prefs.getStringSet("notified_ids", emptySet()) ?: emptySet()

            val newOnes = clarifications.filter { it.id !in notifiedIds }
            if (newOnes.isEmpty()) return Result.success()

            // Show notifications
            ensureChannel()
            for (clar in newOnes) {
                showNotification(clar.id, clar.question)
            }

            // Remember which ones we've notified about
            val updatedIds = notifiedIds + newOnes.map { it.id }
            prefs.edit().putStringSet("notified_ids", updatedIds).apply()

            return Result.success()
        } catch (_: Exception) {
            // Server unreachable — don't retry aggressively
            return Result.success()
        }
    }

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Clarion Questions",
                NotificationManager.IMPORTANCE_DEFAULT,
            ).apply {
                description = "Questions from Clarion when it needs more context"
            }
            val manager = applicationContext.getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }

    private fun showNotification(clarId: String, question: String) {
        // Check permission on Android 13+
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(
                    applicationContext, Manifest.permission.POST_NOTIFICATIONS
                ) != PackageManager.PERMISSION_GRANTED
            ) {
                return
            }
        }

        val intent = Intent(applicationContext, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
        }
        val pendingIntent = PendingIntent.getActivity(
            applicationContext, clarId.hashCode(), intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val notification = NotificationCompat.Builder(applicationContext, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("Clarion has a question")
            .setContentText(question)
            .setStyle(NotificationCompat.BigTextStyle().bigText(question))
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .build()

        NotificationManagerCompat.from(applicationContext)
            .notify(clarId.hashCode(), notification)
    }

    companion object {
        const val CHANNEL_ID = "clarion_clarifications"
        const val WORK_NAME = "clarion_clarification_poll"

        /**
         * Schedule periodic polling for clarifications.
         * Runs every 15 minutes (minimum WorkManager interval).
         */
        fun schedule(context: Context) {
            val request = PeriodicWorkRequestBuilder<ClarificationWorker>(
                15, TimeUnit.MINUTES,
            ).setConstraints(
                Constraints.Builder()
                    .setRequiredNetworkType(NetworkType.CONNECTED)
                    .build()
            ).build()

            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                WORK_NAME,
                ExistingPeriodicWorkPolicy.KEEP,
                request,
            )
        }

        /** Run a one-time check immediately. */
        fun checkNow(context: Context) {
            val request = OneTimeWorkRequestBuilder<ClarificationWorker>()
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build()
                ).build()

            WorkManager.getInstance(context).enqueue(request)
        }
    }
}
