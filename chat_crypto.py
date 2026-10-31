import base64
import os
import re

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


_BASE64_URL = re.compile(r"^[A-Za-z0-9_-]+$")
_AAD_PREFIX = b"gleek-chat-v1|"


class ChatCryptoError(Exception):
    pass


def _encode(data):
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _decode(value, expected_length=None):
    if not isinstance(value, str) or not _BASE64_URL.fullmatch(value):
        raise ChatCryptoError("The encrypted chat data is malformed.")
    try:
        result = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, base64.binascii.Error) as exc:
        raise ChatCryptoError("The encrypted chat data is malformed.") from exc
    if expected_length is not None and len(result) != expected_length:
        raise ChatCryptoError("The encrypted chat data has an invalid length.")
    return result


def generate_identity():
    private_key = X25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return private_bytes, _encode(public_bytes)


def public_key_for_private(private_bytes):
    try:
        private_key = X25519PrivateKey.from_private_bytes(private_bytes)
    except (ValueError, TypeError) as exc:
        raise ChatCryptoError("The saved chat private key is invalid.") from exc
    public_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return _encode(public_bytes)


def _derive_key(private_key, peer_public_key):
    try:
        shared_secret = private_key.exchange(peer_public_key)
    except ValueError as exc:
        raise ChatCryptoError("The chat encryption key is invalid.") from exc
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=_AAD_PREFIX,
    ).derive(shared_secret)


def encrypt_message(message, recipient_public_key, sender_id, recipient_id):
    if not isinstance(message, str) or not message:
        raise ChatCryptoError("Enter a message before sending.")
    try:
        recipient_key = X25519PublicKey.from_public_bytes(_decode(recipient_public_key, 32))
    except (ValueError, TypeError) as exc:
        raise ChatCryptoError("A chat encryption key is invalid.") from exc

    ephemeral_key = X25519PrivateKey.generate()
    nonce = os.urandom(12)
    aad = _AAD_PREFIX + f"{sender_id}|{recipient_id}".encode("utf-8")
    try:
        ciphertext = AESGCM(_derive_key(ephemeral_key, recipient_key)).encrypt(
            nonce,
            message.encode("utf-8"),
            aad,
        )
    except ChatCryptoError:
        raise
    except ValueError as exc:
        raise ChatCryptoError("The chat encryption key is invalid.") from exc
    ephemeral_public = ephemeral_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    envelope = {
        "version": 1,
        "ephemeral_key": _encode(ephemeral_public),
        "nonce": _encode(nonce),
        "ciphertext": _encode(ciphertext),
    }

    return envelope


def decrypt_message(envelope, recipient_private_key, sender_id, recipient_id):
    if not isinstance(envelope, dict) or envelope.get("version") != 1:
        raise ChatCryptoError("This message uses an unsupported encryption format.")
    try:
        private_key = X25519PrivateKey.from_private_bytes(recipient_private_key)
        ephemeral_key = X25519PublicKey.from_public_bytes(
            _decode(envelope.get("ephemeral_key"), 32)
        )
        nonce = _decode(envelope.get("nonce"), 12)
        ciphertext = _decode(envelope.get("ciphertext"))
        if len(ciphertext) < 16 or len(ciphertext) > 4096:
            raise ChatCryptoError("The encrypted chat message has an invalid size.")
        aad = _AAD_PREFIX + f"{sender_id}|{recipient_id}".encode("utf-8")
        plaintext = AESGCM(_derive_key(private_key, ephemeral_key)).decrypt(
            nonce,
            ciphertext,
            aad,
        )
        message = plaintext.decode("utf-8")
    except InvalidTag as exc:
        raise ChatCryptoError(
            "This message could not be authenticated or decrypted with this device's chat key."
        ) from exc
    except (ValueError, TypeError, UnicodeDecodeError) as exc:
        raise ChatCryptoError("The encrypted chat message is malformed.") from exc
    return message
