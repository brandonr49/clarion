# D2: Client Strategy

**Decision: Web UI skeleton first, Android app is the real primary client**

**Status: RESOLVED**

## Context

- Android is the primary client — always on the user's person, used for most input
- Input must be FAST: quick one-liners and paragraph dumps
- Voice-to-text on Android, ideally with a local transcription model (no network for STT)
- Android needs to be a real app: home screen, widgets, notifications
- Mac/Linux: browser tab to server IP:port is fine for now
- PWA is future work (noted, not urgent)
- CLI is very low priority
- Network required for server communication is acceptable (tailscale for remote access)
- Offline capture can be deferred

## Client Breakdown

### Android (PRIMARY)
- Real native app (not a browser wrapper)
- Home screen icon, widgets, notifications
- Optimized for quick input — open, type/speak, done
- Local voice-to-text model (avoid network dependency for transcription)
- Views will be simpler/narrower than desktop — phone-appropriate
- Technology: likely Kotlin + Jetpack Compose (modern Android standard)
  - Alternative: Flutter (cross-platform but adds Dart dependency)
  - Decision on Android tech stack deferred to implementation phase

### Web UI (SCAFFOLD)
- First client built — unblocks server and harness development
- Simple: text input box + submit, basic note viewer, query interface
- Runs at server_ip:port in any browser
- Used from Mac/Linux desktops via bookmarked browser tab
- No PWA, no service worker, no offline — just a page

### CLI (LOW PRIORITY)
- `clarion add "buy milk"` style interface
- Nice-to-have, not planned for early phases

### Desktop Apps (FUTURE)
- PWA or Electron or Tauri — decision deferred
- Richer views than phone (multi-column, dashboards)
- Not needed until view system is mature

## Key Insight

The Android app is not optional polish — it's the primary input device for the system.
The web UI exists to unblock harness development. Once the harness is working, Android
becomes the priority client.
