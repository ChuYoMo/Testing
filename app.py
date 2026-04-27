
"""应用入口模块。

说明：
- 本文件只负责演示流程，不承载核心业务规则；
- 便于后续替换为 unittest、pytest、CLI 或 GUI；
- 通过 run_demo() 返回结构化结果，方便测试。
"""

from __future__ import annotations

from pprint import pprint
from typing import Iterable

from auth import AuthService
from blockchain import SimpleBlockchain
from engine import MatchingEngine
from models import Asset, OrderPlacementResult, OrderSide, TradingPair
from wallet import WalletService


def build_demo_services() -> tuple[AuthService, WalletService, SimpleBlockchain, MatchingEngine]:
    """构造演示用服务实例。"""
    auth_service = AuthService()
    wallet_service = WalletService(supported_assets=[Asset.BTC, Asset.ETH, Asset.USDT])
    blockchain = SimpleBlockchain(block_capacity=2)

    supported_pairs = [
        TradingPair(Asset.BTC, Asset.USDT),
        TradingPair(Asset.ETH, Asset.USDT),
        TradingPair(Asset.ETH, Asset.BTC),
    ]
    engine = MatchingEngine(
        auth_service=auth_service,
        wallet_service=wallet_service,
        blockchain=blockchain,
        supported_pairs=supported_pairs,
    )
    return auth_service, wallet_service, blockchain, engine


def _serialize_order_result(result: OrderPlacementResult) -> dict:
    """将下单结果转换为便于演示和测试断言的字典。"""
    order = result.order
    return {
        "order_id": order.order_id,
        "user_id": order.user_id,
        "pair": order.pair.symbol,
        "side": order.side.value,
        "price": str(order.price),
        "quantity": str(order.quantity),
        "filled_quantity": str(order.filled_quantity),
        "remaining_quantity": str(order.remaining_quantity),
        "status": order.status.value,
        "self_trade_blocked": result.self_trade_blocked,
        "trades": [trade.to_record() for trade in result.trades],
    }


def _collect_wallets(wallet_service: WalletService, users: Iterable[str]) -> dict:
    """收集多个用户的钱包快照。"""
    return {user: wallet_service.get_wallet_snapshot(user) for user in users}


def run_demo() -> dict:
    """运行一段完整业务流程演示。

    交易场景：
    1. Bob 挂出 BTC/USDT 卖单；
    2. Alice 提交 BTC/USDT 买单，与 Bob 部分成交；
    3. Alice 提交 ETH/USDT 买单；
    4. Carol 提交 ETH/USDT 卖单，与 Alice 成交。
    """
    auth_service, wallet_service, blockchain, engine = build_demo_services()

    for username, password in [
        ("alice", "alice123"),
        ("bob", "bob123"),
        ("carol", "carol123"),
    ]:
        auth_service.register(username, password)
        wallet_service.create_wallet_for_user(username)

    alice_token = auth_service.login("alice", "alice123")
    bob_token = auth_service.login("bob", "bob123")
    carol_token = auth_service.login("carol", "carol123")

    wallet_service.deposit("alice", Asset.USDT, "50000")
    wallet_service.deposit("bob", Asset.BTC, "1")
    wallet_service.deposit("carol", Asset.ETH, "5")

    btc_usdt = TradingPair(Asset.BTC, Asset.USDT)
    eth_usdt = TradingPair(Asset.ETH, Asset.USDT)

    result_1 = engine.place_limit_order(
        user_id="bob",
        pair=btc_usdt,
        side=OrderSide.SELL,
        price="30000",
        quantity="1",
    )
    step_1_result = _serialize_order_result(result_1)
    result_2 = engine.place_limit_order(
        user_id="alice",
        pair=btc_usdt,
        side=OrderSide.BUY,
        price="31000",
        quantity="0.4",
    )
    step_2_result = _serialize_order_result(result_2)
    result_3 = engine.place_limit_order(
        user_id="alice",
        pair=eth_usdt,
        side=OrderSide.BUY,
        price="2100",
        quantity="2",
    )
    step_3_result = _serialize_order_result(result_3)
    result_4 = engine.place_limit_order(
        user_id="carol",
        pair=eth_usdt,
        side=OrderSide.SELL,
        price="2000",
        quantity="5",
    )
    step_4_result = _serialize_order_result(result_4)

    if blockchain.pending_transactions:
        blockchain.seal_pending_transactions()

    serialized_results = {
        "bob_sell_btc": _serialize_order_result(result_1),
        "alice_buy_btc": _serialize_order_result(result_2),
        "alice_buy_eth": _serialize_order_result(result_3),
        "carol_sell_eth": _serialize_order_result(result_4),
    }
    trade_flow = [
        {
            "step": 1,
            "title": "Bob 挂出 BTC/USDT 卖单",
            "description": "Bob 冻结 1 BTC，卖单进入 BTC/USDT 卖单簿等待成交。",
            "result": step_1_result,
        },
        {
            "step": 2,
            "title": "Alice 提交 BTC/USDT 买单，与 Bob 部分成交",
            "description": "Alice 买入 0.4 BTC，Bob 的 1 BTC 卖单剩余 0.6 BTC。",
            "result": step_2_result,
        },
        {
            "step": 3,
            "title": "Alice 提交 ETH/USDT 买单",
            "description": "Alice 冻结 4200 USDT，买单进入 ETH/USDT 买单簿等待成交。",
            "result": step_3_result,
        },
        {
            "step": 4,
            "title": "Carol 提交 ETH/USDT 卖单，与 Alice 成交",
            "description": "Carol 卖出 2 ETH 给 Alice，Carol 的 5 ETH 卖单剩余 3 ETH。",
            "result": step_4_result,
        },
    ]
    all_trades = [
        trade
        for result in serialized_results.values()
        for trade in result["trades"]
    ]

    return {
        "sessions": {
            "alice": alice_token,
            "bob": bob_token,
            "carol": carol_token,
        },
        "trade_flow": trade_flow,
        "results": serialized_results,
        "trades": all_trades,
        "wallets": _collect_wallets(wallet_service, ["alice", "bob", "carol"]),
        "order_books": {
            "BTC/USDT": engine.get_order_book_snapshot(btc_usdt),
            "ETH/USDT": engine.get_order_book_snapshot(eth_usdt),
        },
        "blockchain_valid": blockchain.validate_chain(),
        "blockchain": blockchain.export_chain(),
    }


def main() -> None:
    """命令行演示入口。"""
    demo_result = run_demo()
    pprint(demo_result)


if __name__ == "__main__":
    main()
