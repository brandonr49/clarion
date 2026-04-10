package com.clarion.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.clarion.app.data.ServerConfig
import com.clarion.app.ui.NoteInputScreen
import com.clarion.app.ui.SettingsScreen
import com.clarion.app.ui.theme.ClarionTheme
import com.clarion.app.viewmodel.NoteViewModel

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        val serverConfig = ServerConfig(this)

        setContent {
            ClarionTheme {
                ClarionApp(serverConfig)
            }
        }
    }
}

@Composable
fun ClarionApp(serverConfig: ServerConfig) {
    val navController = rememberNavController()
    val viewModel: NoteViewModel = viewModel()

    // Initialize with saved server URL
    remember {
        viewModel.setServerUrl(serverConfig.serverUrl)
        true
    }

    NavHost(navController = navController, startDestination = "input") {
        composable("input") {
            NoteInputScreen(
                viewModel = viewModel,
                onNavigateToSettings = { navController.navigate("settings") },
            )
        }
        composable("settings") {
            SettingsScreen(
                viewModel = viewModel,
                currentUrl = serverConfig.serverUrl,
                onSave = { url -> serverConfig.serverUrl = url },
                onBack = { navController.popBackStack() },
            )
        }
    }
}
