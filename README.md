# Gleek

Gleek is a Windows desktop app for account pairing, app-based presence, and opening paired contacts in Element/Matrix. It uses a shared Supabase project for accounts and pairing.

> **Project status:** Gleek does not currently provide remote desktop, screen sharing, remote control, or command execution. The Devices page uses a built-in demo inventory and its connect action is only a UI demonstration.

## Features

- Create an account or sign in with email and password.
- Securely remember a sign-in on the current Windows user account using Windows DPAPI.
- Request a pairing using another user's 12-character pairing code. The recipient must approve the request.
- See paired accounts and whether their Gleek app has checked in recently.
- Save a Matrix ID and open a paired contact's Matrix profile in Element or a browser.
- Use animated desktop UI built with Python and PyQt6.

Presence indicates that Gleek recently checked in; it does not confirm that a computer is powered on or reachable. Pairing grants no access to another person's screen or computer.

## Getting started

### Install Gleek

Download and run `Gleek-Setup-1.0.3.exe` from the project's releases or shared download. The installer lets you choose an installation folder. Start Gleek from the Start menu or optional desktop shortcut.

### Configure the shared backend

Gleek is configured to use the project's shared Supabase backend by default. Before accounts can sign up or sign in, the Supabase project owner must run the complete [`supabase_roles.sql`](./supabase_roles.sql) script in the Supabase Dashboard's SQL Editor.

The script creates or updates the required profile, pairing, and presence schema and configures access for authenticated users. Apply the full script when setting up the project or after pulling a version that changes the schema. Do not use a Supabase `service_role` or secret key in this desktop client.

For development or an alternate Supabase project, configure the project URL and a **publishable** (or legacy **anon**) key in Gleek's configuration dialog, or set `SUPABASE_URL` and `SUPABASE_ANON_KEY` in the environment or a local `.env` file. See [`.env.example`](./.env.example). Keep `.env` out of source-control uploads.

### Pair with another Gleek user

1. Sign in and open **Pairing**.
2. Share your displayed pairing code with the other person, or enter their code and send a request.
3. The recipient approves or declines the request in their Pairing tab.
4. Once paired, both users can see each other's Gleek app presence and can remove the pairing later.

### Open an encrypted chat in Element

Gleek does not provide in-app chat. Each person needs a separate Matrix account and the Element app (or another Matrix client).

1. In Gleek's **Pairing** tab, save your Matrix ID, such as `@name:matrix.org`.
2. Confirm your contact's Matrix ID with them through a trusted channel. IDs are self-entered; Gleek does not verify account ownership.
3. Select **Open Element** for the paired account. Element or your browser opens their Matrix profile.
4. Verify the other person's devices in Element before sharing sensitive information.

## Privacy and security

- Gleek uses HTTPS to communicate with Supabase, but account, pairing, and presence data are processed by the configured Supabase project.
- Matrix message encryption and delivery are handled by Element/Matrix, not Gleek. Matrix homeservers can still observe account and connection metadata, including IP addresses.
- Gleek cannot enforce a two-person end-chat confirmation or guarantee deletion of Matrix messages from other devices, backups, or logs.
- No software can promise absolute secrecy. Device compromise, screenshots, account recovery, and service metadata can affect privacy.
- Older versions of Gleek may have stored plaintext messages in the Supabase `pairing_messages` table. The current migration revokes the app's access to the legacy message RPCs, but does not delete historical rows. The project owner should review and remove any data they no longer need.

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
- [`supabase_auth.py`](./supabase_auth.py) — Supabase authentication, profile, pairing, and secure saved-session helpers.
- [`supabase_roles.sql`](./supabase_roles.sql) — Supabase schema and access-control migration.
- [`installer.iss`](./installer.iss) and [`build_windows.ps1`](./build_windows.ps1) — Windows installer build configuration.

