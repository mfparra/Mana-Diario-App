"""Criptografia de campo (anotações, perfil premium) — AES-256-GCM.

Formato dos bytes guardados: `0x01 | key_id (1 byte) | nonce (12) | ciphertext+tag`.
O AAD amarra o texto cifrado ao dono e ao registro (ex.: `note:<user_id>:<date>`): copiar os bytes
para outra linha/usuário faz a decifragem falhar.

Chaves em `FIELD_ENCRYPTION_KEY`: lista separada por vírgula de `id:chave_base64url` (32 bytes); a primeira
é a ativa (cifra), as demais só decifram — rotação = pôr a nova na frente e recifrar aos poucos.
Uma chave sem `id:` vale como id 1. Gerar: `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
"""

import base64
import os
from functools import lru_cache

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings

FORMAT_VERSION = 1
NONCE_LEN = 12


class CryptoError(Exception):
    pass


def _decode_key(raw: str) -> bytes:
    raw = raw.strip()
    try:
        key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    except (ValueError, TypeError) as exc:
        raise CryptoError("chave de criptografia não é base64url") from exc
    if len(key) != 32:
        raise CryptoError("chave de criptografia precisa ter 32 bytes (AES-256)")
    return key


def parse_keys(spec: str | None) -> dict[int, bytes]:
    if not spec:
        raise CryptoError("FIELD_ENCRYPTION_KEY não configurada")
    keys: dict[int, bytes] = {}
    for part in (p for p in spec.split(",") if p.strip()):
        kid_s, sep, key = part.partition(":")
        kid = int(kid_s) if sep else 1
        key = key if sep else kid_s
        if not 1 <= kid <= 255 or kid in keys:
            raise CryptoError(f"id de chave inválido ou repetido: {kid}")
        keys[kid] = _decode_key(key)
    return keys


class FieldCipher:
    def __init__(self, spec: str | None):
        self._keys = parse_keys(spec)
        self.active_id = next(iter(self._keys))

    def encrypt(self, plaintext: str, aad: str) -> bytes:
        nonce = os.urandom(NONCE_LEN)
        ct = AESGCM(self._keys[self.active_id]).encrypt(nonce, plaintext.encode(), aad.encode())
        return bytes([FORMAT_VERSION, self.active_id]) + nonce + ct

    def decrypt(self, data: bytes, aad: str) -> str:
        if len(data) < 2 + NONCE_LEN + 16 or data[0] != FORMAT_VERSION:
            raise CryptoError("formato de dado cifrado desconhecido")
        key = self._keys.get(data[1])
        if key is None:
            raise CryptoError(f"chave {data[1]} indisponível")
        try:
            return AESGCM(key).decrypt(data[2 : 2 + NONCE_LEN], data[2 + NONCE_LEN :], aad.encode()).decode()
        except InvalidTag as exc:
            raise CryptoError("falha de autenticação ao decifrar") from exc

    def needs_reencrypt(self, data: bytes) -> bool:
        return len(data) > 1 and data[1] != self.active_id


@lru_cache
def get_cipher() -> FieldCipher:
    return FieldCipher(get_settings().field_encryption_key)
