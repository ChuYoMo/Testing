"""SQLite 持久化层：schema 初始化与数据库工具函数。"""

import sqlite3


def init_db(db_path: str = "dex.db") -> sqlite3.Connection:
    """打开（或创建）SQLite 数据库，初始化所有表，返回连接。"""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _create_tables(conn)
    _migrate_schema(conn)
    return conn


def clear_db(conn: sqlite3.Connection) -> None:
    """清空所有表的数据（保留 schema），用于 GUI 重置。"""
    conn.executescript("""
        DELETE FROM pending_transactions;
        DELETE FROM blocks;
        DELETE FROM trades;
        DELETE FROM orders;
        DELETE FROM wallets;
        DELETE FROM sessions;
        DELETE FROM users;
    """)
    conn.commit()


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            username      TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            password_salt TEXT NOT NULL,
            created_at    TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token    TEXT PRIMARY KEY,
            username TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS wallets (
            owner     TEXT NOT NULL,
            asset     TEXT NOT NULL,
            available TEXT NOT NULL DEFAULT '0.00000000',
            frozen    TEXT NOT NULL DEFAULT '0.00000000',
            PRIMARY KEY (owner, asset)
        );
        CREATE TABLE IF NOT EXISTS orders (
            order_id           TEXT PRIMARY KEY,
            user_id            TEXT NOT NULL,
            pair               TEXT NOT NULL,
            side               TEXT NOT NULL,
            price              TEXT NOT NULL,
            quantity           TEXT NOT NULL,
            remaining_quantity TEXT NOT NULL,
            status             TEXT NOT NULL,
            created_at         TEXT NOT NULL,
            sequence           INTEGER NOT NULL,
            order_type         TEXT NOT NULL DEFAULT 'LIMIT'
        );
        CREATE TABLE IF NOT EXISTS trades (
            trade_id      TEXT PRIMARY KEY,
            buy_order_id  TEXT NOT NULL,
            sell_order_id TEXT NOT NULL,
            buyer_id      TEXT NOT NULL,
            seller_id     TEXT NOT NULL,
            pair          TEXT NOT NULL,
            price         TEXT NOT NULL,
            quantity      TEXT NOT NULL,
            quote_amount  TEXT NOT NULL,
            timestamp     TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS blocks (
            block_index   INTEGER PRIMARY KEY,
            timestamp     TEXT NOT NULL,
            previous_hash TEXT NOT NULL,
            block_hash    TEXT NOT NULL,
            transactions  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pending_transactions (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            tx_data TEXT NOT NULL
        );
    """)
    conn.commit()


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """对已存在的 schema 做幂等增量迁移。"""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(orders)")}
    if "order_type" not in columns:
        conn.execute(
            "ALTER TABLE orders ADD COLUMN order_type TEXT NOT NULL DEFAULT 'LIMIT'"
        )
        conn.commit()
