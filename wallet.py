
"""钱包/账户模块。

职责：
1. 余额查询；
2. 充值 / 提现；
3. 冻结 / 解冻 / 消耗冻结余额。

测试友好性设计：
- 全部接口为纯业务方法，不依赖 I/O；
- 冻结与可用余额分开，便于撮合过程断言；
- 对外统一返回快照数据，便于单元测试比对。
"""

from __future__ import annotations

from typing import Dict, Iterable

from exceptions import (
    InsufficientBalanceError,
    InsufficientFrozenBalanceError,
    UnsupportedAssetError,
    ValidationError,
)
from models import Asset, Wallet, ensure_positive, normalize_decimal


class WalletService:
    """内存钱包服务。"""

    def __init__(self, supported_assets: Iterable[Asset]) -> None:
        self._supported_assets = set(supported_assets)
        self._wallets: Dict[str, Wallet] = {}

    def create_wallet_for_user(self, user_id: str) -> Wallet:
        """为用户创建钱包；若已存在则直接返回。"""
        if user_id not in self._wallets:
            self._wallets[user_id] = Wallet(owner=user_id)
        return self._wallets[user_id]

    def get_wallet(self, user_id: str) -> Wallet:
        """获取指定用户钱包，不存在则自动创建。"""
        return self.create_wallet_for_user(user_id)

    def _validate_asset(self, asset: Asset) -> None:
        """校验币种是否受支持。"""
        if asset not in self._supported_assets:
            raise UnsupportedAssetError(f"不支持的币种: {asset}")

    def get_available_balance(self, user_id: str, asset: Asset) -> str:
        """查询可用余额。"""
        self._validate_asset(asset)
        wallet = self.get_wallet(user_id)
        return str(wallet.balances[asset])

    def get_frozen_balance(self, user_id: str, asset: Asset) -> str:
        """查询冻结余额。"""
        self._validate_asset(asset)
        wallet = self.get_wallet(user_id)
        return str(wallet.frozen_balances[asset])

    def get_wallet_snapshot(self, user_id: str) -> dict:
        """返回用户钱包快照。"""
        return self.get_wallet(user_id).snapshot()

    def deposit(self, user_id: str, asset: Asset, amount: object) -> None:
        """充值。"""
        self._validate_asset(asset)
        decimal_amount = normalize_decimal(amount)
        ensure_positive(decimal_amount, "充值金额")
        wallet = self.get_wallet(user_id)
        wallet.balances[asset] += decimal_amount

    def withdraw(self, user_id: str, asset: Asset, amount: object) -> None:
        """提现。"""
        self._validate_asset(asset)
        decimal_amount = normalize_decimal(amount)
        ensure_positive(decimal_amount, "提现金额")
        wallet = self.get_wallet(user_id)
        if wallet.balances[asset] < decimal_amount:
            raise InsufficientBalanceError("可用余额不足，无法提现。")
        wallet.balances[asset] -= decimal_amount

    def freeze(self, user_id: str, asset: Asset, amount: object) -> None:
        """冻结可用余额。"""
        self._validate_asset(asset)
        decimal_amount = normalize_decimal(amount)
        ensure_positive(decimal_amount, "冻结金额")
        wallet = self.get_wallet(user_id)
        if wallet.balances[asset] < decimal_amount:
            raise InsufficientBalanceError("可用余额不足，无法冻结。")
        wallet.balances[asset] -= decimal_amount
        wallet.frozen_balances[asset] += decimal_amount

    def unfreeze(self, user_id: str, asset: Asset, amount: object) -> None:
        """解冻冻结余额。"""
        self._validate_asset(asset)
        decimal_amount = normalize_decimal(amount)
        ensure_positive(decimal_amount, "解冻金额")
        wallet = self.get_wallet(user_id)
        if wallet.frozen_balances[asset] < decimal_amount:
            raise InsufficientFrozenBalanceError("冻结余额不足，无法解冻。")
        wallet.frozen_balances[asset] -= decimal_amount
        wallet.balances[asset] += decimal_amount

    def consume_frozen(self, user_id: str, asset: Asset, amount: object) -> None:
        """消耗冻结余额，用于成交结算。"""
        self._validate_asset(asset)
        decimal_amount = normalize_decimal(amount)
        ensure_positive(decimal_amount, "消耗冻结金额")
        wallet = self.get_wallet(user_id)
        if wallet.frozen_balances[asset] < decimal_amount:
            raise InsufficientFrozenBalanceError("冻结余额不足，无法扣减。")
        wallet.frozen_balances[asset] -= decimal_amount

    def assert_user_has_wallet(self, user_id: str) -> None:
        """显式校验钱包是否存在。"""
        if user_id not in self._wallets:
            raise ValidationError(f"用户 {user_id} 尚未创建钱包。")
