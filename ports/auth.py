"""Password hashing interface + its ``pwdlib`` implementation.

``pwdlib`` is not on the domain/ports import-linter forbidden list (see
``pyproject.toml``), so the concrete implementation lives here directly
rather than behind a separate ``adapters/`` module.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher


class PasswordHasher(ABC):
    @abstractmethod
    def hash(self, plain_password: str) -> str: ...

    @abstractmethod
    def verify(self, plain_password: str, hashed_password: str) -> bool: ...


class PwdlibPasswordHasher(PasswordHasher):
    """bcrypt-backed hasher (Consistency Conventions: pwdlib, not passlib)."""

    def __init__(self) -> None:
        self._hasher = PasswordHash((BcryptHasher(),))

    def hash(self, plain_password: str) -> str:
        return self._hasher.hash(plain_password)

    def verify(self, plain_password: str, hashed_password: str) -> bool:
        return self._hasher.verify(plain_password, hashed_password)
