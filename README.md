# Gleek

Gleek is a Windows desktop app for account pairing, app-based presence, and encrypted in-app chats. It uses a shared Supabase project for accounts and pairing.

> **Project status:** Gleek does not currently provide remote desktop, screen sharing, remote control, or command execution. The Devices page uses a built-in demo inventory and its connect action is only a UI demonstration.

## Features

- Create an account or sign in with email and password.
- Securely remember a sign-in on the current Windows user account using Windows DPAPI.
- Request a pairing using another user's 12-character pairing code. The recipient must approve the request.
- See paired accounts and whether their Gleek app has checked in recently.
- Chat with paired accounts inside Gleek; neither person needs a Matrix account.
- Optionally save a Matrix ID and open a paired contact's Matrix profile in Element or a browser.
- Keep Gleek in the system tray, get pairing-request notifications, and use the command palette.
- Save window size, selected page, and local preferences; optionally start Gleek with Windows.
- Use animated desktop UI built with Python and PyQt6.

Use **Ctrl+K** to open the command palette or **Ctrl+1** through **Ctrl+4** to switch pages.
The **Settings** page includes notification, tray, low-power, and Windows startup preferences.
When signed in, closing the window hides Gleek to the tray if tray support is available and the
tray preference is enabled. Choose **Quit** from the tray menu to exit and clear app presence.

Presence indicates that Gleek recently checked in; it does not confirm that a computer is powered on or reachable. Pairing grants no access to another person's screen or computer.

## Getting started

### Install Gleek

Download and run `Gleek-Setup-1.0.3.exe` from the project's releases or shared download. The installer lets you choose an installation folder. Start Gleek from the Start menu or optional desktop shortcut.

### Configure the shared backend

Gleek is configured to use the project's shared Supabase backend by default. Before accounts can sign up or sign in, the Supabase project owner must run the complete [`supabase_roles.sql`](./supabase_roles.sql) script in the Supabase Dashboard's SQL Editor.

The script creates or updates the required profile, pairing, presence, and encrypted chat schema and configures access for authenticated users. Apply the full script when setting up the project or after pulling a version that changes the schema. Do not use a Supabase `service_role` or secret key in this desktop client.

For development or an alternate Supabase project, configure the project URL and a **publishable** (or legacy **anon**) key in Gleek's configuration dialog, or set `SUPABASE_URL` and `SUPABASE_ANON_KEY` in the environment or a local `.env` file. See [`.env.example`](./.env.example). Keep `.env` out of source-control uploads.

### Pair with another Gleek user

1. Sign in and open **Pairing**.
2. Share your displayed pairing code with the other person, or enter their code and send a request.
3. The recipient approves or declines the request in their Pairing tab.
4. Once paired, both users can see each other's Gleek app presence and can remove the pairing later.

### Chat with a paired Gleek user

Element is optional. Gleek provides encrypted in-app chat for approved pairings.

1. Sign in to Gleek and enter the other person's pairing code.
2. The recipient approves the pairing request.
3. Select **Chat** beside the paired account. Messages are encrypted on the sending device and decrypted on the receiving device.

Each Gleek account currently has one chat key protected by Windows DPAPI on the first PC that signs in. Chat keys do not sync or transfer to another PC; signing in to the same Gleek account elsewhere will not enable chat until multi-device key transfer is implemented. If the private key is lost, old messages cannot be decrypted.

## Privacy and security

- Gleek uses HTTPS to communicate with Supabase, but account, pairing, and presence data are processed by the configured Supabase project.
- In-app message contents are encrypted on the clients and Supabase stores only encrypted message envelopes. Supabase still sees account IDs, pairing relationships, message timing, and ciphertext sizes. No Matrix account is needed, but Gleek sign-in remains email-based; this does not make Gleek accounts anonymous.
- Chat public keys are distributed by Supabase and are not independently fingerprint-verified. Client-side encryption protects stored message contents from ordinary database reads, but this design does not protect against a malicious backend operator substituting public keys.
- Matrix message encryption and delivery are handled by Element/Matrix, not Gleek. Matrix homeservers can still observe account and connection metadata, including IP addresses.
- Gleek cannot enforce a two-person end-chat confirmation or guarantee deletion of Matrix messages from other devices, backups, or logs.
- No software can promise absolute secrecy. Device compromise, screenshots, account recovery, and service metadata can affect privacy.
- Older versions of Gleek may have stored plaintext messages in the Supabase `pairing_messages` table. The migration keeps access to those legacy message RPCs revoked and does not delete historical rows. New encrypted chats use a separate table; the project owner should review and remove historical rows they no longer need.

## Build from source

### Requirements

- Windows
- Python 3.12 or newer
- Inno Setup 6

From the project directory, create the environment, install build dependencies, and run the build script:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r build-requirements.txt
powershell -ExecutionPolicy Bypass -File .\build_windows.ps1
```

The script creates `dist\Gleek.exe` and packages it as `installer\Gleek-Setup-1.0.3.exe`. The installer defaults to `%LOCALAPPDATA%\Programs\Gleek`, allows choosing another destination folder, creates a Start menu shortcut, and offers an optional desktop shortcut.

## Project files

- [`main.py`](./main.py) — PyQt6 application and user interface.
- [`chat_crypto.py`](./chat_crypto.py) — client-side encryption for in-app chat.
- [`supabase_auth.py`](./supabase_auth.py) — Supabase authentication, profile, pairing, and secure saved-session helpers.
- [`supabase_roles.sql`](./supabase_roles.sql) — Supabase schema and access-control migration.
- [`installer.iss`](./installer.iss) and [`build_windows.ps1`](./build_windows.ps1) — Windows installer build configuration.
