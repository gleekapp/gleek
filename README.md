<div align="center">

# Gleek

**Pair with trusted contacts, see when their app is online, and jump straight into an Element/Matrix chat.**

![Platform: Windows](https://img.shields.io/badge/platform-Windows-0078D6?logo=windows&logoColor=white)
![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)
![UI: PyQt6](https://img.shields.io/badge/UI-PyQt6-41CD52?logo=qt&logoColor=white)
![Backend: Supabase](https://img.shields.io/badge/backend-Supabase-3ECF8E?logo=supabase&logoColor=white)
![Version 1.0.3](https://img.shields.io/badge/version-1.0.3-blue)

<!-- Add a screenshot or short GIF here, e.g.: -->
<!-- ![Gleek screenshot](docs/screenshot.png) -->

</div>

---

## Table of contents

- [What is Gleek?](#what-is-gleek)
- [What Gleek is not](#what-gleek-is-not)
- [Features](#features)
- [Quick start](#quick-start)
- [How to use it](#how-to-use-it)
- [Configuration](#configuration)
- [Privacy and security](#privacy-and-security)
- [Build from source](#build-from-source)
- [Project structure](#project-structure)
- [FAQ](#faq)

## What is Gleek?

Gleek is a Windows desktop app that connects two people through a simple, consent-based pairing flow. Once paired, you can see whether each other's Gleek app has checked in recently and open each other's Matrix profile in Element with one click.

Accounts, pairings, and presence are stored in a shared [Supabase](https://supabase.com) project. Chat itself happens in Element/Matrix, not in Gleek.

## What Gleek is not

> [!IMPORTANT]
> Gleek does **not** provide remote desktop, screen sharing, remote control, or command execution. Pairing grants no access to another person's screen or computer.

- **Presence is not reachability.** It only means the other person's Gleek app checked in recently. It does not confirm their computer is on or reachable.
- **There is no in-app chat.** Messaging is handled entirely by Element or another Matrix client.
- **The Devices page is a demo.** It uses a built-in demo inventory, and its connect action is a UI demonstration only.

## Features

| | |
|---|---|
| **Accounts** | Sign up or sign in with email and password. |
| **Remembered sign-in** | Optionally stay signed in, with the session protected by Windows DPAPI for the current Windows user. |
| **Consent-based pairing** | Send a request using another user's 12-character pairing code. The recipient must approve it. |
| **App presence** | See which paired contacts have recently checked in with Gleek. |
| **Element/Matrix launch** | Save your Matrix ID and open a paired contact's Matrix profile in Element or your browser. |
| **Animated UI** | Desktop interface built with Python and PyQt6. |

## Quick start

### 1. Install

Download and run **`Gleek-Setup-1.0.3.exe`** from the project's releases or shared download.

- Default install location: `%LOCALAPPDATA%\Programs\Gleek` (you can choose another folder)
- Creates a Start menu shortcut, with an optional desktop shortcut

### 2. Set up the backend (project owner, one time)

Gleek uses the project's shared Supabase backend by default. Before anyone can sign up or sign in:

1. Open your Supabase project's **SQL Editor**.
2. Run the **complete** [`supabase_roles.sql`](./supabase_roles.sql) script.

The script creates or updates the profile, pairing, and presence schema and configures access for authenticated users. Re-run the full script whenever you pull a version that changes the schema.

> [!WARNING]
> Never put a Supabase `service_role` or secret key in this desktop client. Use only a publishable (or legacy anon) key.

### 3. Launch and sign in

Start Gleek from the Start menu, create an account, and you're ready to pair.

## How to use it

### Pair with another Gleek user

1. Sign in and open the **Pairing** tab.
2. Share your pairing code, or enter theirs and send a request.
3. The recipient approves or declines the request in their own Pairing tab.
4. Once paired, you can both see each other's app presence. Either of you can remove the pairing at any time.

### Open a chat in Element

You and your contact each need your own Matrix account and the Element app (or another Matrix client).

1. In the **Pairing** tab, save your Matrix ID (for example, `@name:matrix.org`).
2. Confirm your contact's Matrix ID with them through a trusted channel. IDs are self-entered, and **Gleek does not verify account ownership**.
3. Select **Open Element** next to the paired account. Element or your browser opens their Matrix profile.
4. Verify the other person's devices in Element before sharing anything sensitive.

## Configuration

Gleek works out of the box with the project's default Supabase backend. To use your own project (for development or a separate deployment), provide a project URL and a **publishable** (or legacy **anon**) key in either of two ways:

- **In the app:** open Gleek's configuration dialog.
- **Via environment:** set variables in your environment or a local `.env` file.

| Variable | Description |
|---|---|
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_ANON_KEY` | Your publishable (or legacy anon) key |

See [`.env.example`](./.env.example) for a template. Keep your `.env` out of source control.

## Privacy and security

**What Gleek handles**
- Traffic to Supabase uses HTTPS. Account, pairing, and presence data are processed by whichever Supabase project Gleek is configured to use.
- Saved sign-ins are protected with Windows DPAPI and are tied to the current Windows user account.

**What Gleek does not handle**
- Message encryption and delivery are handled by Element/Matrix. Matrix homeservers can still see account and connection metadata, including IP addresses.
- Gleek cannot enforce two-person confirmation of chat deletion or guarantee that Matrix messages are removed from other devices, backups, or logs.
- No software can promise absolute secrecy. Device compromise, screenshots, account recovery, and service metadata can all affect your privacy.

**Note for project owners: legacy message data**

Older versions of Gleek may have stored plaintext messages in the Supabase `pairing_messages` table. The current migration revokes the app's access to the legacy message RPCs, but it **does not delete historical rows**. Review that table and remove any data you no longer need.

## Build from source

**Requirements**

- Windows
- Python 3.12 or newer
- [Inno Setup 6](https://jrsoftware.org/isinfo.php)

**Steps**

From the project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r build-requirements.txt
powershell -ExecutionPolicy Bypass -File .\build_windows.ps1
```

**Output**

- `dist\Gleek.exe`: the standalone executable
- `installer\Gleek-Setup-1.0.3.exe`: the packaged installer

## Project structure

| File | Purpose |
|---|---|
| [`main.py`](./main.py) | PyQt6 application and user interface |
| [`supabase_auth.py`](./supabase_auth.py) | Supabase authentication, profiles, pairing, and secure saved-session helpers |
| [`supabase_roles.sql`](./supabase_roles.sql) | Supabase schema and access-control migration |
| [`installer.iss`](./installer.iss) | Inno Setup installer configuration |
| [`build_windows.ps1`](./build_windows.ps1) | Windows build and packaging script |

## FAQ

**Can I see or control my contact's screen?**
No. Gleek has no remote desktop, screen sharing, or remote control features.

**Why does a contact show as offline when their PC is on?**
Presence reflects only whether their Gleek app has recently checked in. If Gleek isn't running or can't reach Supabase, they'll appear offline.

**Does Gleek read my chats?**
No. Chats happen in Element/Matrix. Gleek only stores your Matrix ID so it can open a contact's profile.

**Sign-up or sign-in fails. What should I check?**
Make sure the Supabase project owner has run the full [`supabase_roles.sql`](./supabase_roles.sql) script, and that the URL and publishable key in Gleek's configuration are correct.

**Can I use my own Supabase project?**
Yes. See [Configuration](#configuration), and run `supabase_roles.sql` in your project before first use.
