import ctypes
import json
import os
import re
import sys
from pathlib import Path
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


DEFAULT_SUPABASE_URL = "https://klrzfpzaxtnwhrqedwsf.supabase.co"
DEFAULT_SUPABASE_ANON_KEY = "sb_publishable_rNTfqPmEemBgnubz_-mNxg_Q8l3X1db"


class SupabaseAuthError(Exception):
    pass


class SupabaseConfigurationError(SupabaseAuthError):
    pass


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.c_uint32),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


class WindowsSessionStore:
    def __init__(self):
        if os.name != "nt":
            raise OSError("Secure saved sign-in is currently supported on Windows.")
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            raise OSError("The Windows local application data folder is unavailable.")
        self.path = Path(local_app_data) / "RemoteControl" / "session.dat"

    def save_refresh_token(self, refresh_token):
        if not isinstance(refresh_token, str) or not refresh_token.strip():
            raise SupabaseAuthError("Supabase did not return a valid refresh token.")
        encrypted = self._protect(refresh_token.encode("utf-8"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_path = tempfile.mkstemp(
            prefix=".session-", dir=str(self.path.parent)
        )
        try:
            with os.fdopen(file_descriptor, "wb") as session_file:
                session_file.write(encrypted)
            os.replace(temporary_path, self.path)
        finally:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)

    def load_refresh_token(self):
        if not self.path.exists():
            return None
        try:
            encrypted = self.path.read_bytes()
        except OSError as exc:
            raise SupabaseAuthError("Could not read the saved sign-in session.") from exc
        try:
            refresh_token = self._unprotect(encrypted).decode("utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            raise SupabaseAuthError(
                "The saved sign-in session could not be unlocked on this Windows account."
            ) from exc
        if not refresh_token.strip():
            raise SupabaseAuthError("The saved sign-in session is empty.")
        return refresh_token

    def clear(self):
        try:
            self.path.unlink(missing_ok=True)
        except OSError as exc:
            raise SupabaseAuthError("Could not remove the saved sign-in session.") from exc

    def save_chat_private_key(self, user_id, private_key):
        path = self._chat_key_path(user_id)
        if not isinstance(private_key, bytes) or len(private_key) != 32:
            raise SupabaseAuthError("The chat private key is invalid.")
        encrypted = self._protect(private_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_path = tempfile.mkstemp(
            prefix=".chat-key-", dir=str(path.parent)
        )
        try:
            with os.fdopen(file_descriptor, "wb") as key_file:
                key_file.write(encrypted)
            os.replace(temporary_path, path)
        except OSError as exc:
            raise SupabaseAuthError("Could not save this device's chat key.") from exc
        finally:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)

    def load_chat_private_key(self, user_id):
        path = self._chat_key_path(user_id)
        if not path.exists():
            return None
        try:
            encrypted = path.read_bytes()
            private_key = self._unprotect(encrypted)
        except OSError as exc:
            raise SupabaseAuthError(
                "Could not unlock this account's chat key on this Windows account."
            ) from exc
        if len(private_key) != 32:
            raise SupabaseAuthError("The saved chat key is invalid.")
        return private_key

    def _chat_key_path(self, user_id):
        if not isinstance(user_id, str) or not re.fullmatch(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
            user_id,
        ):
            raise SupabaseAuthError("Supabase returned an invalid account ID.")
        return self.path.parent / "chat-keys" / f"{user_id.lower()}.dat"

    @staticmethod
    def _protect(data):
        buffer = ctypes.create_string_buffer(data)
        source = _DataBlob(
            len(data),
            ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
        )
        destination = _DataBlob()
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        protect = crypt32.CryptProtectData
        protect.argtypes = [
            ctypes.POINTER(_DataBlob), ctypes.c_wchar_p, ctypes.POINTER(_DataBlob),
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
            ctypes.POINTER(_DataBlob),
        ]
        protect.restype = ctypes.c_int
        if not protect(
            ctypes.byref(source), "RemoteControl session", None, None, None, 1,
            ctypes.byref(destination),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            return ctypes.string_at(destination.pbData, destination.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(destination.pbData)

    @staticmethod
    def _unprotect(data):
        buffer = ctypes.create_string_buffer(data)
        source = _DataBlob(
            len(data),
            ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
        )
        destination = _DataBlob()
        description = ctypes.c_wchar_p()
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        unprotect = crypt32.CryptUnprotectData
        unprotect.argtypes = [
            ctypes.POINTER(_DataBlob), ctypes.POINTER(ctypes.c_wchar_p),
            ctypes.POINTER(_DataBlob), ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_uint32, ctypes.POINTER(_DataBlob),
        ]
        unprotect.restype = ctypes.c_int
        if not unprotect(
            ctypes.byref(source), ctypes.byref(description), None, None, None, 1,
            ctypes.byref(destination),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            return ctypes.string_at(destination.pbData, destination.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(destination.pbData)
            if description:
                ctypes.windll.kernel32.LocalFree(description)


def _read_environment_file():
    env_paths = []
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        env_paths.append(Path(local_app_data) / "Gleek" / ".env")
    app_directory = (
        Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent
    )
    env_paths.append(app_directory / ".env")

    for env_path in env_paths:
        if not env_path.exists():
            continue
        try:
            lines = env_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise SupabaseConfigurationError(
                f"Could not read the environment file at {env_path}."
            ) from exc

        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            name, value = name.strip(), value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            if name and name not in os.environ:
                os.environ[name] = value


class SupabaseAuthClient:
    def __init__(self, url, anon_key):
        parsed_url = urlparse(url)
        is_local_http = parsed_url.scheme == "http" and parsed_url.hostname in {
            "localhost", "127.0.0.1"
        }
        if parsed_url.scheme != "https" and not is_local_http:
            raise SupabaseConfigurationError(
                "SUPABASE_URL must use HTTPS (HTTP is allowed only for localhost)."
            )
        if not parsed_url.netloc:
            raise SupabaseConfigurationError("SUPABASE_URL is not a valid URL.")
        if not anon_key:
            raise SupabaseConfigurationError("SUPABASE_ANON_KEY is missing.")

        self.url = url.rstrip("/")
        self.anon_key = anon_key

    @classmethod
    def from_environment(cls):
        _read_environment_file()
        url = os.environ.get("SUPABASE_URL", DEFAULT_SUPABASE_URL).strip()
        anon_key = os.environ.get(
            "SUPABASE_ANON_KEY", DEFAULT_SUPABASE_ANON_KEY
        ).strip()
        missing = [
            name for name, value in (
                ("SUPABASE_URL", url),
                ("SUPABASE_ANON_KEY", anon_key),
            ) if not value
        ]
        if missing:
            raise SupabaseConfigurationError(
                f"Set {', '.join(missing)} in a .env file copied from .env.example. "
                "For Gleek, place it beside Gleek.exe or in %LOCALAPPDATA%\\Gleek."
            )
        return cls(url, anon_key)

    @classmethod
    def save_configuration(cls, url, anon_key):
        client = cls(url.strip(), anon_key.strip())
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            raise SupabaseConfigurationError(
                "The Windows local application data folder is unavailable."
            )

        config_path = Path(local_app_data) / "Gleek" / ".env"
        temporary_path = None
        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            file_descriptor, temporary_path = tempfile.mkstemp(
                prefix=".gleek-env-", dir=str(config_path.parent), text=True
            )
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as config_file:
                config_file.write(
                    f"SUPABASE_URL={client.url}\n"
                    f"SUPABASE_ANON_KEY={client.anon_key}\n"
                )
            os.replace(temporary_path, config_path)
        except OSError as exc:
            raise SupabaseConfigurationError(
                "Could not save Gleek's Supabase settings in your Windows profile."
            ) from exc
        finally:
            if temporary_path and os.path.exists(temporary_path):
                os.remove(temporary_path)

        os.environ["SUPABASE_URL"] = client.url
        os.environ["SUPABASE_ANON_KEY"] = client.anon_key
        return client

    def sign_in(self, email, password):
        return self._post(
            "/auth/v1/token?grant_type=password",
            {"email": email, "password": password},
        )

    def sign_up(self, email, password):
        return self._post(
            "/auth/v1/signup",
            {"email": email, "password": password},
        )

    def refresh_session(self, refresh_token):
        return self._post(
            "/auth/v1/token?grant_type=refresh_token",
            {"refresh_token": refresh_token},
        )

    def get_profile(self, user_id, access_token):
        if not isinstance(access_token, str) or not access_token.strip():
            raise SupabaseAuthError("Supabase did not return a valid access token.")
        query = urlencode({
            "user_id": f"eq.{user_id}",
            "select": "access_level,device_ids,pairing_code,matrix_user_id,chat_public_key",
        })
        request = Request(
            f"{self.url}/rest/v1/profiles?{query}",
            headers={
                "apikey": self.anon_key,
                "Authorization": f"Bearer {access_token}",
            },
            method="GET",
        )
        try:
            result = self._send(request)
        except SupabaseAuthError as exc:
            message = str(exc).lower()
            pairing_schema_missing = (
                (
                    "pairing_code" in message
                    or "matrix_user_id" in message
                    or "chat_public_key" in message
                )
                and (
                    "does not exist" in message
                    or "schema cache" in message
                    or "could not find" in message
                )
            )
            if pairing_schema_missing:
                raise SupabaseAuthError(
                    "Your Supabase database needs the latest Gleek update. In the "
                    "Supabase Dashboard, open SQL Editor and run the complete "
                    "supabase_roles.sql file from this project, then try signing "
                    "in again."
                ) from exc
            raise
        if not isinstance(result, list) or len(result) != 1:
            raise SupabaseAuthError(
                "No access profile was found. Run supabase_roles.sql in the "
                "Supabase SQL Editor, then try signing in again."
            )
        if not isinstance(result[0], dict):
            raise SupabaseAuthError("Supabase returned an unexpected access profile.")
        access_level = result[0].get("access_level")
        if access_level not in {"member", "admin", "owner"}:
            raise SupabaseAuthError(
                "The account has an unsupported access level. Set it to "
                "member, admin, or owner in Supabase."
            )
        device_ids = result[0].get("device_ids")
        if not isinstance(device_ids, list) or not all(
            isinstance(device_id, str) for device_id in device_ids
        ):
            raise SupabaseAuthError(
                "The account has an invalid device assignment in its Supabase profile."
            )
        pairing_code = result[0].get("pairing_code")
        if not isinstance(pairing_code, str) or not re.fullmatch(r"[a-f0-9]{12}", pairing_code):
            raise SupabaseAuthError(
                "This account does not have a valid pairing code. Run the updated "
                "supabase_roles.sql setup in the Supabase SQL Editor."
            )
        matrix_user_id = result[0].get("matrix_user_id")
        if matrix_user_id is not None and (
            not isinstance(matrix_user_id, str)
            or not re.fullmatch(
                r"@[A-Za-z0-9._=/-]+:[A-Za-z0-9.-]+(?::[0-9]{1,5})?",
                matrix_user_id,
            )
        ):
            raise SupabaseAuthError(
                "The account has an invalid Matrix ID in its Supabase profile."
            )
        chat_public_key = result[0].get("chat_public_key")
        if chat_public_key is not None and (
            not isinstance(chat_public_key, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{43}", chat_public_key)
        ):
            raise SupabaseAuthError(
                "The account has an invalid chat encryption key. Update supabase_roles.sql."
            )
        return {
            "access_level": access_level,
            "device_ids": device_ids,
            "pairing_code": pairing_code,
            "matrix_user_id": matrix_user_id,
            "chat_public_key": chat_public_key,
        }

    def request_pairing(self, pairing_code, access_token):
        if not isinstance(pairing_code, str) or not re.fullmatch(
            r"[a-fA-F0-9]{12}", pairing_code.strip()
        ):
            raise SupabaseAuthError("Enter a valid 12-character pairing code.")
        return self._rpc(
            "request_pairing",
            {"target_pairing_code": pairing_code.strip().lower()},
            access_token,
        )

    def get_pairing_state(self, access_token):
        result = self._rpc("get_pairing_state", {}, access_token)
        if not isinstance(result, dict):
            raise SupabaseAuthError("Supabase returned an unexpected pairing status.")
        requests = result.get("requests")
        pairings = result.get("pairings")
        outgoing = result.get("outgoing")
        if not all(isinstance(value, list) for value in (requests, pairings, outgoing)):
            raise SupabaseAuthError("Supabase returned incomplete pairing status.")
        return result

    def respond_to_pairing(self, request_id, accept, access_token):
        return self._rpc(
            "respond_to_pairing",
            {"target_request_id": request_id, "approve": bool(accept)},
            access_token,
        )

    def revoke_pairing(self, peer_id, access_token):
        return self._rpc(
            "revoke_pairing",
            {"target_user_id": peer_id},
            access_token,
        )

    def set_matrix_user_id(self, matrix_user_id, access_token):
        if matrix_user_id is not None and (
            not isinstance(matrix_user_id, str)
            or not re.fullmatch(
                r"@[A-Za-z0-9._=/-]+:[A-Za-z0-9.-]+(?::[0-9]{1,5})?",
                matrix_user_id,
            )
        ):
            raise SupabaseAuthError(
                "Enter a valid Matrix ID, such as @username:matrix.org, "
                "or leave the field empty to remove it."
            )
        return self._rpc(
            "set_matrix_user_id",
            {"target_matrix_user_id": matrix_user_id},
            access_token,
        )

    def set_chat_public_key(self, public_key, access_token):
        if not isinstance(public_key, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{43}", public_key
        ):
            raise SupabaseAuthError("The chat encryption public key is invalid.")
        return self._rpc(
            "set_chat_public_key",
            {"target_public_key": public_key},
            access_token,
        )

    def send_encrypted_pairing_message(
        self, peer_id, sender_envelope, recipient_envelope, access_token
    ):
        for envelope in (sender_envelope, recipient_envelope):
            if not isinstance(envelope, dict):
                raise SupabaseAuthError("The encrypted chat message is invalid.")
        return self._rpc(
            "send_encrypted_pairing_message",
            {
                "target_user_id": peer_id,
                "sender_envelope": sender_envelope,
                "recipient_envelope": recipient_envelope,
            },
            access_token,
        )

    def get_encrypted_pairing_messages(self, peer_id, access_token):
        result = self._rpc(
            "get_encrypted_pairing_messages",
            {"target_user_id": peer_id},
            access_token,
        )
        if not isinstance(result, list) or not all(
            isinstance(entry, dict)
            and isinstance(entry.get("sender_id"), str)
            and isinstance(entry.get("envelope"), dict)
            for entry in result
        ):
            raise SupabaseAuthError("Supabase returned invalid encrypted chat messages.")
        return result

    def update_presence(self, access_token):
        return self._rpc("update_presence", {}, access_token)

    def clear_presence(self, access_token):
        return self._rpc("clear_presence", {}, access_token)

    def _rpc(self, function_name, payload, access_token):
        if not isinstance(access_token, str) or not access_token.strip():
            raise SupabaseAuthError("Supabase did not return a valid access token.")
        request = Request(
            f"{self.url}/rest/v1/rpc/{function_name}",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "apikey": self.anon_key,
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        return self._send(request)

    def _post(self, path, payload):
        request = Request(
            f"{self.url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "apikey": self.anon_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        result = self._send(request)
        if not isinstance(result, dict):
            raise SupabaseAuthError("Supabase returned an unexpected response.")
        return result

    @staticmethod
    def _send(request):
        try:
            with urlopen(request, timeout=15) as response:
                body = response.read()
        except HTTPError as exc:
            body = exc.read()
            message = SupabaseAuthClient._error_message(body) or str(exc.reason)
            raise SupabaseAuthError(message) from exc
        except (URLError, TimeoutError) as exc:
            raise SupabaseAuthError(
                "Could not reach Supabase. Check your internet connection and project URL."
            ) from exc

        try:
            result = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise SupabaseAuthError(
                "Supabase returned an unreadable response. Please try again."
            ) from exc
        if not isinstance(result, (dict, list, str, bool, int, float)):
            raise SupabaseAuthError("Supabase returned an unexpected response.")
        return result

    @staticmethod
    def _error_message(body):
        try:
            result = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return ""
        if isinstance(result, dict):
            for key in ("msg", "message", "error_description", "error"):
                message = result.get(key)
                if isinstance(message, str) and message:
                    return message
        return ""
