
"""订单与撮合模块。

核心规则：
1. 仅支持限价单；
2. 价格优先、时间优先；
3. 支持部分成交与完全成交；
4. 默认启用自成交保护：当最优对手单来自同一用户时，撮合停止。

测试友好性设计：
- 订单 ID / 成交 ID / 顺序号均由内置计数器生成，便于断言；
- 时间函数可注入，便于稳定测试；
- 订单簿采用显式列表，便于验证价格与时间优先级。
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from itertools import count
from typing import Callable, DefaultDict, Dict, Iterable, List, Optional

from auth import AuthService
from blockchain import SimpleBlockchain
from exceptions import (
    OrderNotCancellableError,
    OrderNotFoundError,
    UnsupportedTradingPairError,
    ValidationError,
)
from models import (
    Order,
    OrderPlacementResult,
    OrderSide,
    OrderStatus,
    Trade,
    TradingPair,
    ZERO,
    ensure_positive,
    normalize_decimal,
)
from wallet import WalletService


class OrderBook:
    """单个撮合引擎使用的订单簿容器。"""

    def __init__(self) -> None:
        self._buys: DefaultDict[str, List[Order]] = defaultdict(list)
        self._sells: DefaultDict[str, List[Order]] = defaultdict(list)

    def add(self, order: Order) -> None:
        """向订单簿加入活跃订单，并保持排序。"""
        book = self._select_book(order.pair, order.side)
        book.append(order)
        self._sort_book(book, order.side)

    def get_orders(self, pair: TradingPair, side: OrderSide) -> List[Order]:
        """返回指定交易对与方向的订单列表（内部引用）。"""
        return self._select_book(pair, side)

    def remove(self, order: Order) -> bool:
        """从订单簿中移除指定订单。已不在簿中返回 False。"""
        book = self._select_book(order.pair, order.side)
        for index, candidate in enumerate(book):
            if candidate.order_id == order.order_id:
                book.pop(index)
                return True
        return False

    def snapshot(self, pair: TradingPair) -> Dict[str, List[dict]]:
        """返回订单簿快照。"""
        return {
            "buy": [self._order_to_dict(order) for order in self._buys[pair.symbol]],
            "sell": [self._order_to_dict(order) for order in self._sells[pair.symbol]],
        }

    @staticmethod
    def _sort_book(book: List[Order], side: OrderSide) -> None:
        """按价格优先、时间优先排序。"""
        if side == OrderSide.BUY:
            book.sort(key=lambda order: (-order.price, order.sequence))
        else:
            book.sort(key=lambda order: (order.price, order.sequence))

    def _select_book(self, pair: TradingPair, side: OrderSide) -> List[Order]:
        return self._buys[pair.symbol] if side == OrderSide.BUY else self._sells[pair.symbol]

    @staticmethod
    def _order_to_dict(order: Order) -> dict:
        return {
            "order_id": order.order_id,
            "user_id": order.user_id,
            "pair": order.pair.symbol,
            "side": order.side.value,
            "price": str(order.price),
            "quantity": str(order.quantity),
            "remaining_quantity": str(order.remaining_quantity),
            "status": order.status.value,
            "created_at": order.created_at.isoformat(),
            "sequence": order.sequence,
        }


class MatchingEngine:
    """DEX 限价撮合引擎，可选 SQLite 持久化。"""

    def __init__(
        self,
        auth_service: AuthService,
        wallet_service: WalletService,
        blockchain: SimpleBlockchain,
        supported_pairs: Iterable[TradingPair],
        clock: Callable[[], datetime] | None = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        self._auth_service = auth_service
        self._wallet_service = wallet_service
        self._blockchain = blockchain
        self._supported_pairs = {pair.symbol: pair for pair in supported_pairs}
        self._clock = clock or (lambda: datetime.now(UTC))
        self._conn = conn
        self._order_book = OrderBook()
        self._order_sequence = count(1)
        self._order_id_sequence = count(1)
        self._trade_id_sequence = count(1)
        self._orders: Dict[str, Order] = {}
        if conn:
            self._load_from_db()

    def _load_from_db(self) -> None:
        """从数据库恢复订单，重建订单簿并还原序列计数器。"""
        for row in self._conn.execute(
            "SELECT order_id, user_id, pair, side, price, quantity, remaining_quantity, status, created_at, sequence FROM orders"
        ):
            pair = self._supported_pairs.get(row["pair"])
            if pair is None:
                continue
            order = Order(
                order_id=row["order_id"],
                user_id=row["user_id"],
                pair=pair,
                side=OrderSide(row["side"]),
                price=Decimal(row["price"]),
                quantity=Decimal(row["quantity"]),
                remaining_quantity=Decimal(row["remaining_quantity"]),
                status=OrderStatus(row["status"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                sequence=row["sequence"],
            )
            self._orders[order.order_id] = order
            if order.is_active():
                self._order_book.add(order)

        max_seq = self._conn.execute("SELECT COALESCE(MAX(sequence), 0) FROM orders").fetchone()[0]
        max_order_num = self._conn.execute(
            "SELECT COALESCE(MAX(CAST(SUBSTR(order_id, 2) AS INTEGER)), 0) FROM orders"
        ).fetchone()[0]
        max_trade_num = self._conn.execute(
            "SELECT COALESCE(MAX(CAST(SUBSTR(trade_id, 2) AS INTEGER)), 0) FROM trades"
        ).fetchone()[0]
        self._order_sequence = count(int(max_seq) + 1)
        self._order_id_sequence = count(int(max_order_num) + 1)
        self._trade_id_sequence = count(int(max_trade_num) + 1)

    def _persist_order(self, order: Order) -> None:
        """将订单（含状态更新）写入数据库。"""
        self._conn.execute(
            """INSERT OR REPLACE INTO orders
               (order_id, user_id, pair, side, price, quantity, remaining_quantity, status, created_at, sequence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                order.order_id,
                order.user_id,
                order.pair.symbol,
                order.side.value,
                str(order.price),
                str(order.quantity),
                str(order.remaining_quantity),
                order.status.value,
                order.created_at.isoformat(),
                order.sequence,
            ),
        )

    def _persist_trade(self, trade: Trade) -> None:
        """将成交记录写入数据库。"""
        self._conn.execute(
            """INSERT OR IGNORE INTO trades
               (trade_id, buy_order_id, sell_order_id, buyer_id, seller_id, pair, price, quantity, quote_amount, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                trade.trade_id,
                trade.buy_order_id,
                trade.sell_order_id,
                trade.buyer_id,
                trade.seller_id,
                trade.pair.symbol,
                str(trade.price),
                str(trade.quantity),
                str(trade.quote_amount),
                trade.timestamp.isoformat(),
            ),
        )

    def place_limit_order(
        self,
        user_id: str,
        pair: TradingPair,
        side: OrderSide,
        price: object,
        quantity: object,
    ) -> OrderPlacementResult:
        """提交限价单并自动撮合。

        :return: OrderPlacementResult，包含订单与本次产生的成交列表。
        """
        self._validate_user(user_id)
        self._validate_pair(pair)

        decimal_price = normalize_decimal(price)
        decimal_quantity = normalize_decimal(quantity)
        ensure_positive(decimal_price, "价格")
        ensure_positive(decimal_quantity, "数量")

        order = Order(
            order_id=f"O{next(self._order_id_sequence):06d}",
            user_id=user_id,
            pair=pair,
            side=side,
            price=decimal_price,
            quantity=decimal_quantity,
            remaining_quantity=decimal_quantity,
            status=OrderStatus.OPEN,
            created_at=self._clock(),
            sequence=next(self._order_sequence),
        )

        self._freeze_order_funds(order)
        trades, self_trade_blocked = self._match_order(order)

        if order.is_active():
            self._order_book.add(order)

        self._orders[order.order_id] = order

        if self._conn:
            self._persist_order(order)
            for trade in trades:
                maker_id = (
                    trade.sell_order_id if order.side == OrderSide.BUY else trade.buy_order_id
                )
                self._persist_order(self._orders[maker_id])
                self._persist_trade(trade)
            self._conn.commit()

        return OrderPlacementResult(
            order=order,
            trades=trades,
            self_trade_blocked=self_trade_blocked,
        )

    def get_order(self, order_id: str) -> Order:
        """获取订单详情。"""
        try:
            return self._orders[order_id]
        except KeyError as exc:
            raise ValidationError(f"订单 {order_id} 不存在。") from exc

    def cancel_order(self, user_id: str, order_id: str) -> Order:
        """撤销活跃订单，解冻剩余资金。

        :raises OrderNotFoundError: 订单不存在。
        :raises ValidationError: 不是该用户的订单。
        :raises OrderNotCancellableError: 订单已成交或已撤销。
        """
        order = self._orders.get(order_id)
        if order is None:
            raise OrderNotFoundError(f"订单 {order_id} 不存在。")
        if order.user_id != user_id:
            raise ValidationError(f"订单 {order_id} 不属于用户 {user_id}。")
        if not order.is_active():
            raise OrderNotCancellableError(
                f"订单 {order_id} 当前状态为 {order.status.value}，不可撤销。"
            )

        if order.side == OrderSide.BUY:
            refund_asset = order.pair.quote_asset
            refund_amount = normalize_decimal(order.price * order.remaining_quantity)
        else:
            refund_asset = order.pair.base_asset
            refund_amount = order.remaining_quantity

        if refund_amount > ZERO:
            self._wallet_service.unfreeze(order.user_id, refund_asset, refund_amount)

        self._order_book.remove(order)
        order.status = OrderStatus.CANCELLED

        if self._conn:
            self._persist_order(order)
            self._conn.commit()

        return order

    def get_order_book_snapshot(self, pair: TradingPair) -> dict:
        """获取订单簿快照。"""
        self._validate_pair(pair)
        return self._order_book.snapshot(pair)

    def list_orders(self) -> Dict[str, Order]:
        """返回订单快照。"""
        return dict(self._orders)

    def _validate_user(self, user_id: str) -> None:
        if not self._auth_service.user_exists(user_id):
            raise ValidationError(f"用户 {user_id} 未注册，不能下单。")

    def _validate_pair(self, pair: TradingPair) -> None:
        if pair.base_asset == pair.quote_asset:
            raise UnsupportedTradingPairError("基础币种与计价币种不能相同。")
        if pair.symbol not in self._supported_pairs:
            raise UnsupportedTradingPairError(f"不支持的交易对: {pair.symbol}")

    def _freeze_order_funds(self, order: Order) -> None:
        """在订单进入撮合前冻结所需资金。"""
        if order.side == OrderSide.BUY:
            required_quote = normalize_decimal(order.price * order.quantity)
            self._wallet_service.freeze(order.user_id, order.pair.quote_asset, required_quote)
        else:
            self._wallet_service.freeze(order.user_id, order.pair.base_asset, order.quantity)

    def _match_order(self, taker_order: Order) -> tuple[List[Trade], bool]:
        """执行撮合主循环。"""
        trades: List[Trade] = []
        self_trade_blocked = False
        opposite_side = OrderSide.SELL if taker_order.side == OrderSide.BUY else OrderSide.BUY
        opposite_book = self._order_book.get_orders(taker_order.pair, opposite_side)

        while taker_order.remaining_quantity > ZERO and opposite_book:
            maker_order = opposite_book[0]

            if not self._is_price_crossed(taker_order, maker_order):
                break

            if maker_order.user_id == taker_order.user_id:
                self_trade_blocked = True
                break

            trade_quantity = min(taker_order.remaining_quantity, maker_order.remaining_quantity)
            execution_price = maker_order.price
            trade = self._execute_trade(
                taker_order=taker_order,
                maker_order=maker_order,
                quantity=trade_quantity,
                execution_price=execution_price,
            )
            trades.append(trade)
            self._blockchain.add_trade(trade)

            if maker_order.remaining_quantity == ZERO:
                opposite_book.pop(0)

        taker_order.refresh_status()
        return trades, self_trade_blocked

    @staticmethod
    def _is_price_crossed(taker_order: Order, maker_order: Order) -> bool:
        """判断买卖价格是否可成交。"""
        if taker_order.side == OrderSide.BUY:
            return taker_order.price >= maker_order.price
        return taker_order.price <= maker_order.price

    def _execute_trade(
        self,
        taker_order: Order,
        maker_order: Order,
        quantity: Decimal,
        execution_price: Decimal,
    ) -> Trade:
        """完成一次成交并进行资金结算。"""
        if taker_order.side == OrderSide.BUY:
            buy_order = taker_order
            sell_order = maker_order
        else:
            buy_order = maker_order
            sell_order = taker_order

        quote_amount = normalize_decimal(execution_price * quantity)

        self._wallet_service.consume_frozen(sell_order.user_id, sell_order.pair.base_asset, quantity)
        self._wallet_service.deposit(buy_order.user_id, buy_order.pair.base_asset, quantity)

        self._wallet_service.consume_frozen(buy_order.user_id, buy_order.pair.quote_asset, quote_amount)
        self._wallet_service.deposit(sell_order.user_id, sell_order.pair.quote_asset, quote_amount)

        if buy_order.price > execution_price:
            rebate = normalize_decimal((buy_order.price - execution_price) * quantity)
            if rebate > ZERO:
                self._wallet_service.unfreeze(
                    buy_order.user_id,
                    buy_order.pair.quote_asset,
                    rebate,
                )

        taker_order.remaining_quantity = normalize_decimal(
            taker_order.remaining_quantity - quantity
        )
        maker_order.remaining_quantity = normalize_decimal(
            maker_order.remaining_quantity - quantity
        )

        taker_order.refresh_status()
        maker_order.refresh_status()

        trade = Trade(
            trade_id=f"T{next(self._trade_id_sequence):06d}",
            buy_order_id=buy_order.order_id,
            sell_order_id=sell_order.order_id,
            buyer_id=buy_order.user_id,
            seller_id=sell_order.user_id,
            pair=buy_order.pair,
            price=execution_price,
            quantity=quantity,
            quote_amount=quote_amount,
            timestamp=self._clock(),
        )
        return trade
