
"""区块链/链式账本模拟模块。

教学目标：
- 用最小实现体现"前一区块哈希 + 当前区块哈希"的链式不可篡改思想；
- 将撮合产生的成交记录持久化为链上交易列表；
- 支持链完整性校验，便于测试 tamper 场景。
"""

from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from datetime import UTC, datetime
from typing import Callable, Dict, List, Optional

from exceptions import ChainValidationError, EmptyBlockError, InvalidBlockError
from models import Block, Trade


class SimpleBlockchain:
    """简化区块链实现，可选 SQLite 持久化。"""

    def __init__(
        self,
        clock: Callable[[], datetime] | None = None,
        block_capacity: int = 2,
        conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        if block_capacity <= 0:
            raise InvalidBlockError("block_capacity 必须大于 0。")
        self._clock = clock or (lambda: datetime.now(UTC))
        self._block_capacity = block_capacity
        self._conn = conn
        self._chain: List[Block] = []
        self._pending_transactions: List[Dict[str, str]] = []
        if conn:
            self._load_from_db()
        if not self._chain:
            self._create_genesis_block()

    def _load_from_db(self) -> None:
        """从数据库恢复区块链和待打包交易。"""
        for row in self._conn.execute(
            "SELECT block_index, timestamp, previous_hash, block_hash, transactions FROM blocks ORDER BY block_index"
        ):
            block = Block(
                index=row["block_index"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                previous_hash=row["previous_hash"],
                transactions=json.loads(row["transactions"]),
                block_hash=row["block_hash"],
            )
            self._chain.append(block)
        for row in self._conn.execute(
            "SELECT tx_data FROM pending_transactions ORDER BY id"
        ):
            self._pending_transactions.append(json.loads(row["tx_data"]))

    def _persist_block(self, block: Block) -> None:
        """将区块写入数据库。"""
        if not self._conn:
            return
        self._conn.execute(
            "INSERT OR REPLACE INTO blocks (block_index, timestamp, previous_hash, block_hash, transactions) VALUES (?, ?, ?, ?, ?)",
            (
                block.index,
                block.timestamp.isoformat(),
                block.previous_hash,
                block.block_hash,
                json.dumps(block.transactions, ensure_ascii=False),
            ),
        )
        self._conn.commit()

    @property
    def chain(self) -> List[Block]:
        """返回链快照。"""
        return deepcopy(self._chain)

    @property
    def pending_transactions(self) -> List[Dict[str, str]]:
        """返回待打包交易快照。"""
        return deepcopy(self._pending_transactions)

    def _create_genesis_block(self) -> None:
        """创建创世区块。"""
        genesis = Block(
            index=0,
            timestamp=self._clock(),
            previous_hash="0" * 64,
            transactions=[
                {
                    "type": "GENESIS",
                    "description": "DEX ledger genesis block",
                }
            ],
        )
        genesis.block_hash = genesis.compute_hash()
        self._chain.append(genesis)
        self._persist_block(genesis)

    def add_transaction(self, transaction: Dict[str, str]) -> None:
        """添加待打包交易。

        :raises InvalidBlockError: 交易记录为空或结构非法。
        """
        if not transaction or not isinstance(transaction, dict):
            raise InvalidBlockError("交易记录不能为空，且必须为字典。")
        self._pending_transactions.append(deepcopy(transaction))
        if self._conn:
            self._conn.execute(
                "INSERT INTO pending_transactions (tx_data) VALUES (?)",
                (json.dumps(transaction, ensure_ascii=False),),
            )
            self._conn.commit()
        if len(self._pending_transactions) >= self._block_capacity:
            self.seal_pending_transactions()

    def add_trade(self, trade: Trade) -> None:
        """将成交记录加入待打包列表。"""
        self.add_transaction(trade.to_record())

    def seal_pending_transactions(self) -> Block:
        """将待打包交易写入新区块。

        :raises EmptyBlockError: 无待打包交易时禁止创建空区块。
        """
        if not self._pending_transactions:
            raise EmptyBlockError("当前不存在待打包交易，不能创建空区块。")
        previous_block = self._chain[-1]
        block = Block(
            index=len(self._chain),
            timestamp=self._clock(),
            previous_hash=previous_block.block_hash,
            transactions=deepcopy(self._pending_transactions),
        )
        block.block_hash = block.compute_hash()
        self._chain.append(block)
        self._pending_transactions.clear()
        if self._conn:
            self._persist_block(block)
            self._conn.execute("DELETE FROM pending_transactions")
            self._conn.commit()
        return deepcopy(block)

    def validate_chain(self) -> bool:
        """校验整条链的完整性。

        :raises ChainValidationError: 任意区块被篡改或哈希链接错误。
        """
        if not self._chain:
            raise ChainValidationError("区块链为空。")
        for index, block in enumerate(self._chain):
            if not block.transactions:
                raise ChainValidationError(f"区块 {index} 交易列表为空。")
            recalculated_hash = block.compute_hash()
            if block.block_hash != recalculated_hash:
                raise ChainValidationError(f"区块 {index} 哈希值不匹配。")
            if index == 0:
                if block.previous_hash != "0" * 64:
                    raise ChainValidationError("创世区块 previous_hash 非法。")
            else:
                previous_block = self._chain[index - 1]
                if block.previous_hash != previous_block.block_hash:
                    raise ChainValidationError(
                        f"区块 {index} previous_hash 与前一区块不一致。"
                    )
        return True

    def export_chain(self) -> List[dict]:
        """导出链结构，便于演示或测试断言。"""
        return [
            {
                "index": block.index,
                "timestamp": block.timestamp.isoformat(),
                "previous_hash": block.previous_hash,
                "transactions": deepcopy(block.transactions),
                "block_hash": block.block_hash,
            }
            for block in self._chain
        ]
