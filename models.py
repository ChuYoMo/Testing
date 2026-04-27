
"""核心数据模型定义。

设计说明：
1. 仅承载数据与少量无副作用方法，避免业务逻辑耦合。
2. 使用 dataclass / Enum / Decimal，便于单元测试与状态断言。
3. 通过标准化 Decimal 精度，规避 float 带来的金额误差。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from enum import Enum
import hashlib
import json
from typing import Any, Dict, List

from exceptions import ValidationError

DECIMAL_SCALE = Decimal("0.00000001")
ZERO = Decimal("0")


def normalize_decimal(value: Any) -> Decimal:
    """将输入转换为 Decimal，并统一量化到 8 位小数。

    :param value: 可被 Decimal 解析的值。
    :return: 标准化 Decimal。
    :raises ValidationError: 输入无法转换为合法 Decimal。
    """
    try:
        decimal_value = Decimal(str(value))
        if not decimal_value.is_finite():
            raise InvalidOperation
        return decimal_value.quantize(DECIMAL_SCALE, rounding=ROUND_DOWN)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValidationError(f"非法数值输入: {value!r}") from exc


def ensure_positive(value: Decimal, field_name: str) -> None:
    """校验 Decimal 值必须大于 0。"""
    if value <= ZERO:
        raise ValidationError(f"{field_name} 必须大于 0。")


class Asset(str, Enum):
    """系统支持的币种枚举。"""

    BTC = "BTC"
    ETH = "ETH"
    USDT = "USDT"


class OrderSide(str, Enum):
    """订单方向枚举。"""

    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    """订单状态枚举。"""

    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class TradingPair:
    """交易对定义，例如 BTC/USDT。"""

    base_asset: Asset
    quote_asset: Asset

    @property
    def symbol(self) -> str:
        """返回形如 BTC/USDT 的字符串表示。"""
        return f"{self.base_asset.value}/{self.quote_asset.value}"

    def __str__(self) -> str:
        return self.symbol


@dataclass
class User:
    """用户实体。"""

    username: str
    password_hash: str
    password_salt: str
    created_at: datetime


@dataclass
class Wallet:
    """钱包实体，区分可用余额与冻结余额。"""

    owner: str
    balances: Dict[Asset, Decimal] = field(
        default_factory=lambda: {asset: ZERO for asset in Asset}
    )
    frozen_balances: Dict[Asset, Decimal] = field(
        default_factory=lambda: {asset: ZERO for asset in Asset}
    )

    def snapshot(self) -> Dict[str, Dict[str, str]]:
        """返回当前钱包快照，便于测试断言或演示输出。"""
        available = {
            asset.value: str(self.balances.get(asset, ZERO)) for asset in Asset
        }
        frozen = {
            asset.value: str(self.frozen_balances.get(asset, ZERO)) for asset in Asset
        }
        total = {
            asset.value: str(
                self.balances.get(asset, ZERO) + self.frozen_balances.get(asset, ZERO)
            )
            for asset in Asset
        }
        return {
            "owner": self.owner,
            "available": available,
            "frozen": frozen,
            "total": total,
        }


@dataclass
class Order:
    """限价订单实体。"""

    order_id: str
    user_id: str
    pair: TradingPair
    side: OrderSide
    price: Decimal
    quantity: Decimal
    remaining_quantity: Decimal
    status: OrderStatus
    created_at: datetime
    sequence: int

    @property
    def filled_quantity(self) -> Decimal:
        """已成交数量。"""
        return self.quantity - self.remaining_quantity

    def refresh_status(self) -> None:
        """根据剩余数量刷新订单状态。"""
        if self.remaining_quantity == ZERO:
            self.status = OrderStatus.FILLED
        elif self.remaining_quantity < self.quantity:
            self.status = OrderStatus.PARTIALLY_FILLED
        else:
            self.status = OrderStatus.OPEN

    def is_active(self) -> bool:
        """订单是否仍在订单簿中活跃。"""
        return self.status in {OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED}


@dataclass
class Trade:
    """成交记录实体。"""

    trade_id: str
    buy_order_id: str
    sell_order_id: str
    buyer_id: str
    seller_id: str
    pair: TradingPair
    price: Decimal
    quantity: Decimal
    quote_amount: Decimal
    timestamp: datetime

    def to_record(self) -> Dict[str, str]:
        """转换为可写入区块的数据字典。"""
        return {
            "trade_id": self.trade_id,
            "buy_order_id": self.buy_order_id,
            "sell_order_id": self.sell_order_id,
            "buyer_id": self.buyer_id,
            "seller_id": self.seller_id,
            "pair": self.pair.symbol,
            "price": str(self.price),
            "quantity": str(self.quantity),
            "quote_amount": str(self.quote_amount),
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class Block:
    """区块定义。"""

    index: int
    timestamp: datetime
    previous_hash: str
    transactions: List[Dict[str, Any]]
    block_hash: str = ""

    def payload(self) -> Dict[str, Any]:
        """区块哈希计算所使用的原始载荷。"""
        return {
            "index": self.index,
            "timestamp": self.timestamp.isoformat(),
            "previous_hash": self.previous_hash,
            "transactions": self.transactions,
        }

    def compute_hash(self) -> str:
        """计算区块哈希值。"""
        serialized = json.dumps(self.payload(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass
class OrderPlacementResult:
    """下单结果。"""

    order: Order
    trades: List[Trade]
    self_trade_blocked: bool = False
