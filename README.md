<div align="center">

# 💬 Gleek

**Pair up, check in, and chat privately, all from your Windows desktop.**

![Platform](https://img.shields.io/badge/platform-Windows-0078D6?logo=windows&logoColor=white)
![Python](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)
![UI](https://img.shields.io/badge/UI-PyQt6-41CD52?logo=qt&logoColor=white)
![Backend](https://img.shields.io/badge/backend-Supabase-3ECF8E?logo=supabase&logoColor=white)
![Version](https://img.shields.io/badge/version-1.0.3-blue)

</div>

<!--
  Tip: drop a screenshot or short GIF here once you have one, for example:
  <p align="center"><img src="docs/screenshot.png" alt="Gleek app screenshot" width="720"></p>
-->

---

Hey there! 👋 **Gleek** is a small, friendly desktop app for connecting with the people you trust. Create an account, swap pairing codes, and once you've both said yes, you can see when each other's Gleek app is online and chat inside the app with end-to-end encrypted messages. No Matrix account required.

It's built with Python and PyQt6, and it uses a shared Supabase project for accounts and pairing.

> [!IMPORTANT]
> **What Gleek is not (yet).** Gleek does **not** provide remote desktop, screen sharing, remote control, or command execution. Pairing never gives anyone access to your screen or computer. The **Devices** page uses a built-in demo inventory, and its connect button is just a UI demonstration.

## 📖 Contents

- [What you can do](#-what-you-can-do)
- [Getting started](#-getting-started)
- [Keyboard shortcuts](#-keyboard-shortcuts)
- [Privacy and security](#-privacy-and-security)
- [Known limitations](#-known-limitations)
- [Set up the backend](#-set-up-the-backend)
- [Build from source](#-build-from-source)
- [Project layout](#-project-layout)
- [Questions, bugs, and ideas](#-questions-bugs-and-ideas)

## ✨ What you can do

**Accounts**
- Create an account or sign in with your email and password.
- Stay signed in safely. Gleek remembers your session on your current Windows user account using **Windows DPAPI**.

**Pairing and presence**
- Send a pairing request using someone's 12-character pairing code. They have to approve it first.
- See your paired accounts and whether their Gleek app has checked in recently.
- Remove a pairing whenever you like.

**Encrypted chat**
- Chat with paired accounts right inside Gleek.
- Messages are encrypted on the sending device and decrypted on the receiving device.
- Optionally save a Matrix ID and open a paired contact's Matrix profile in Element or your browser.

**Desktop comforts**
- Lives in the system tray, sends pairing-request notifications, and has a command palette.
- Remembers your window size, last page, and local preferences.
- Can start with Windows if you want it to.
- Animated, polished UI built with PyQt6.

> [!NOTE]
> Presence means Gleek **recently checked in**. It doesn't tell you whether a computer is powered on or reachable.

## 🚀 Getting started

### 1. Install Gleek

Download and run **`Gleek-Setup-1.0.3.exe`** from the project's releases or shared download. The installer lets you pick an install folder, then you can launch Gleek from the Start menu or the optional desktop shortcut.

### 2. Pair with a friend

1. Sign in and open **Pairing**.
2. Share your pairing code with the other person, or enter theirs and send a request.
3. The recipient approves or declines the request in their Pairing tab.
4. Once you're paired, you can both see each other's Gleek app presence.

### 3. Start chatting

Select **Chat** beside a paired account and say hi. Element is totally optional, since the in-app chat works on its own for any approved pairing.

> [!WARNING]
> **Your chat key stays on one PC.** Each Gleek account has a single chat key, protected by Windows DPAPI on the **first PC that signs in**. Keys don't sync or transfer, so signing in to the same account on another PC won't enable chat until multi-device key transfer is built. If the private key is lost, old messages can't be decrypted.

### Living in the tray

When you're signed in, closing the window hides Gleek to the tray (if your system supports it and the tray preference is on). To fully exit and clear your app presence, choose **Quit** from the tray menu. The **Settings** page has options for notifications, tray behavior, low-power mode, and Windows startup.

## ⌨️ Keyboard shortcuts

| Shortcut | What it does |
| --- | --- |
| `Ctrl` + `K` | Open the command palette |
| `Ctrl` + `1` to `4` | Jump between pages |

## 🔒 Privacy and security

We'd rather be upfront than impressive, so here's the honest version.

**Who can see what**

| | Can see | Can't see |
| --- | --- | --- |
| **Supabase** (the backend) | Account IDs, pairing relationships, message timing, ciphertext sizes | The contents of your in-app messages |
| **Matrix / Element** (optional) | Account and connection metadata, including IP addresses | Nothing from Gleek, because Matrix encryption and delivery are handled by Element, not Gleek |

**Good to know**

- Gleek talks to Supabase over HTTPS, and account, pairing, and presence data are processed by the configured Supabase project.
- Message contents are encrypted on the clients, and Supabase stores only encrypted envelopes.
- Gleek sign-in is email-based, so even without a Matrix account, Gleek accounts aren't anonymous.
- Chat public keys are distributed through Supabase and **aren't independently fingerprint-verified**. Client-side encryption protects your stored messages from ordinary database reads, but it doesn't protect against a malicious backend operator swapping in different public keys.
- Gleek can't enforce a two-person end-chat confirmation or guarantee that Matrix messages get deleted from other devices, backups, or logs.
- No software can promise absolute secrecy. Device compromise, screenshots, account recovery, and service metadata can all affect your privacy.

## 🧩 Known limitations

- Remote desktop, screen sharing, remote control, and command execution aren't part of Gleek today.
- Chat keys live on a single PC (see the warning above).
- Public keys aren't fingerprint-verified.
- Presence is a "recently checked in" signal, not a guarantee of reachability.

## 🛠️ Set up the backend

*This section is for the project owner.*

Gleek uses the project's shared Supabase backend by default. Before anyone can sign up or sign in, run the complete [`supabase_roles.sql`](./supabase_roles.sql) script in the Supabase Dashboard's **SQL Editor**.

The script creates or updates the profile, pairing, presence, and encrypted chat schema, and sets up access for authenticated users. Run the full script on first setup and again after pulling any version that changes the schema.

> [!CAUTION]
> Never put a Supabase `service_role` or secret key in this desktop client.

**Using your own Supabase project?** Set the project URL and a **publishable** (or legacy **anon**) key in Gleek's configuration dialog, or set `SUPABASE_URL` and `SUPABASE_ANON_KEY` in your environment or a local `.env` file. See [`.env.example`](./.env.example), and keep your `.env` out of source control.

**A note on older data.** Earlier versions of Gleek may have stored plaintext messages in the `pairing_messages` table. The migration keeps access to those legacy message RPCs revoked, but it doesn't delete historical rows. New encrypted chats use a separate table. Please review the old rows and remove any you no longer need.

## 🏗️ Build from source

<details>
<summary><b>Show build instructions</b></summary>

<br>

**You'll need**

- Windows
- Python 3.12 or newer
- [Inno Setup 6](https://jrsoftware.org/isinfo.php)

**Build it**

From the project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r build-requirements.txt
powershell -ExecutionPolicy Bypass -File .\build_windows.ps1
```

The script creates `dist\Gleek.exe` and packages it as `installer\Gleek-Setup-1.0.3.exe`. The installer defaults to `%LOCALAPPDATA%\Programs\Gleek`, lets you choose another folder, adds a Start menu shortcut, and offers an optional desktop shortcut.

</details>

## 🗂️ Project layout

| File | What it does |
| --- | --- |
| [`main.py`](./main.py) | The PyQt6 application and user interface |
| [`chat_crypto.py`](./chat_crypto.py) | Client-side encryption for in-app chat |
| [`supabase_auth.py`](./supabase_auth.py) | Supabase authentication, profiles, pairing, and secure saved-session helpers |
| [`supabase_roles.sql`](./supabase_roles.sql) | Supabase schema and access-control migration |
| [`installer.iss`](./installer.iss) and [`build_windows.ps1`](./build_windows.ps1) | Windows installer build configuration |

## 💡 Questions, bugs, and ideas

Found a bug, have a question, or got an idea that would make Gleek better? Please [open an issue](../../issues). Every bit of feedback helps. 💙

<!--
  Don't forget to add a LICENSE file and a "License" section here before publishing.
-->