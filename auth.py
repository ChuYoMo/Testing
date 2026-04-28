
"""用户认证模块。

职责：
1. 用户注册；
2. 密码安全存储（PBKDF2 + salt）；
3. 登录校验与会话令牌生成。

测试友好性设计：
- 用户仓储采用内存字典，便于隔离测试；
- 时间提供器可注入，便于断言 created_at；
- 令牌生成与校验与 UI 解耦。
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import secrets
import sqlite3
from typing import Callable, Dict, Optional

from exceptions import (
    InvalidCredentialsError,
    UserAlreadyExistsError,
    UserNotFoundError,
    ValidationError,
)
from models import User


class PasswordHasher:
    """密码哈希工具类。"""

    def __init__(self, iterations: int = 120_000) -> None:
        self.iterations = iterations

    def hash_password(self, password: str, salt_hex: str | None = None) -> tuple[str, str]:
        """生成盐值与密码哈希。

        :param password: 原始密码。
        :param salt_hex: 可选固定盐值，便于测试时构造确定性数据。
        :return: (salt_hex, digest_hex)
        """
        if not password:
            raise ValidationError("密码不能为空。")
        salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            self.iterations,
        )
        return salt.hex(), digest.hex()

    def verify_password(self, password: str, salt_hex: str, digest_hex: str) -> bool:
        """验证密码是否匹配。"""
        _, calculated = self.hash_password(password, salt_hex=salt_hex)
        return secrets.compare_digest(calculated, digest_hex)


class AuthService:
    """用户认证服务。"""

    def __init__(
        self,
        clock: Callable[[], datetime] | None = None,
        password_hasher: PasswordHasher | None = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._password_hasher = password_hasher or PasswordHasher()
        self._conn = conn
        self._users: Dict[str, User] = {}
        self._sessions: Dict[str, str] = {}
        if conn:
            self._load_from_db()

    def _load_from_db(self) -> None:
        """从数据库加载用户和会话到内存。"""
        for row in self._conn.execute("SELECT username, password_hash, password_salt, created_at FROM users"):
            self._users[row["username"]] = User(
                username=row["username"],
                password_hash=row["password_hash"],
                password_salt=row["password_salt"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
        for row in self._conn.execute("SELECT token, username FROM sessions"):
            self._sessions[row["token"]] = row["username"]

    def register(self, username: str, password: str) -> User:
        """注册用户。

        :raises UserAlreadyExistsError: 用户已存在。
        :raises ValidationError: 输入不合法。
        """
        normalized_username = username.strip()
        if not normalized_username:
            raise ValidationError("用户名不能为空。")
        if normalized_username in self._users:
            raise UserAlreadyExistsError(f"用户 {normalized_username} 已存在。")
        salt_hex, digest_hex = self._password_hasher.hash_password(password)
        user = User(
            username=normalized_username,
            password_hash=digest_hex,
            password_salt=salt_hex,
            created_at=self._clock(),
        )
        self._users[normalized_username] = user
        if self._conn:
            self._conn.execute(
                "INSERT INTO users (username, password_hash, password_salt, created_at) VALUES (?, ?, ?, ?)",
                (user.username, user.password_hash, user.password_salt, user.created_at.isoformat()),
            )
            self._conn.commit()
        return user

    def login(self, username: str, password: str) -> str:
        """登录并返回会话令牌。

        :raises UserNotFoundError: 用户不存在。
        :raises InvalidCredentialsError: 密码错误。
        """
        normalized_username = username.strip()
        user = self._users.get(normalized_username)
        if user is None:
            raise UserNotFoundError(f"用户 {normalized_username} 不存在。")
        if not self._password_hasher.verify_password(
            password=password,
            salt_hex=user.password_salt,
            digest_hex=user.password_hash,
        ):
            raise InvalidCredentialsError("用户名或密码错误。")
        token = secrets.token_hex(16)
        self._sessions[token] = user.username
        if self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO sessions (token, username) VALUES (?, ?)",
                (token, user.username),
            )
            self._conn.commit()
        return token

    def logout(self, token: str) -> None:
        """登出指定会话。"""
        self._sessions.pop(token, None)
        if self._conn:
            self._conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            self._conn.commit()

    def is_authenticated(self, token: str) -> bool:
        """校验会话令牌是否有效。"""
        return token in self._sessions

    def get_user(self, username: str) -> User:
        """按用户名获取用户实体。"""
        normalized_username = username.strip()
        user = self._users.get(normalized_username)
        if user is None:
            raise UserNotFoundError(f"用户 {normalized_username} 不存在。")
        return user

    def get_user_by_token(self, token: str) -> User:
        """根据会话令牌获取当前用户。"""
        username = self._sessions.get(token)
        if username is None:
            raise InvalidCredentialsError("无效会话令牌。")
        return self.get_user(username)

    def user_exists(self, username: str) -> bool:
        """判断用户是否存在。"""
        return username.strip() in self._users

    def list_users(self) -> Dict[str, User]:
        """返回用户快照。"""
        return dict(self._users)
