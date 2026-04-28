from __future__ import annotations

from decimal import Decimal
import json
import threading
import unittest
import urllib.error
import urllib.request

import gui
from app import run_demo
from auth import AuthService
from blockchain import SimpleBlockchain
from exceptions import (
    EmptyOrderBookError,
    InvalidCredentialsError,
    UserNotFoundError,
    ValidationError,
)
from gui import DEXWebState
from http.server import ThreadingHTTPServer
from models import Asset, normalize_decimal


def money(value: str) -> Decimal:
    return Decimal(value)


class TradingFlowTest(unittest.TestCase):
    def test_required_btc_and_eth_trading_flow(self) -> None:
        demo = run_demo()
        results = demo["results"]

        bob_sell_btc = results["bob_sell_btc"]
        alice_buy_btc = results["alice_buy_btc"]
        alice_buy_eth = results["alice_buy_eth"]
        carol_sell_eth = results["carol_sell_eth"]

        self.assertEqual(bob_sell_btc["status"], "PARTIALLY_FILLED")
        self.assertEqual(bob_sell_btc["remaining_quantity"], "0.60000000")
        self.assertEqual(alice_buy_btc["status"], "FILLED")
        self.assertEqual(alice_buy_btc["filled_quantity"], "0.40000000")

        btc_trade = alice_buy_btc["trades"][0]
        self.assertEqual(btc_trade["buyer_id"], "alice")
        self.assertEqual(btc_trade["seller_id"], "bob")
        self.assertEqual(btc_trade["pair"], "BTC/USDT")
        self.assertEqual(btc_trade["price"], "30000.00000000")
        self.assertEqual(btc_trade["quantity"], "0.40000000")
        self.assertEqual(btc_trade["quote_amount"], "12000.00000000")

        self.assertEqual(alice_buy_eth["status"], "FILLED")
        self.assertEqual(carol_sell_eth["status"], "PARTIALLY_FILLED")
        self.assertEqual(carol_sell_eth["remaining_quantity"], "3.00000000")

        eth_trade = carol_sell_eth["trades"][0]
        self.assertEqual(eth_trade["buyer_id"], "alice")
        self.assertEqual(eth_trade["seller_id"], "carol")
        self.assertEqual(eth_trade["pair"], "ETH/USDT")
        self.assertEqual(eth_trade["price"], "2100.00000000")
        self.assertEqual(eth_trade["quantity"], "2.00000000")
        self.assertEqual(eth_trade["quote_amount"], "4200.00000000")

        wallets = demo["wallets"]
        self.assertEqual(money(wallets["alice"]["available"]["BTC"]), Decimal("0.40000000"))
        self.assertEqual(money(wallets["alice"]["available"]["ETH"]), Decimal("2.00000000"))
        self.assertEqual(money(wallets["alice"]["available"]["USDT"]), Decimal("33800.00000000"))
        self.assertEqual(money(wallets["bob"]["available"]["USDT"]), Decimal("12000.00000000"))
        self.assertEqual(money(wallets["bob"]["frozen"]["BTC"]), Decimal("0.60000000"))
        self.assertEqual(money(wallets["carol"]["available"]["USDT"]), Decimal("4200.00000000"))
        self.assertEqual(money(wallets["carol"]["frozen"]["ETH"]), Decimal("3.00000000"))

        self.assertTrue(demo["blockchain_valid"])
        self.assertEqual(len(demo["trades"]), 2)
        self.assertEqual(demo["trades"][0]["trade_id"], "T000001")
        self.assertEqual(demo["trades"][1]["trade_id"], "T000002")

        btc_book = demo["order_books"]["BTC/USDT"]
        eth_book = demo["order_books"]["ETH/USDT"]
        self.assertEqual(len(btc_book["sell"]), 1)
        self.assertEqual(btc_book["sell"][0]["user_id"], "bob")
        self.assertEqual(btc_book["sell"][0]["remaining_quantity"], "0.60000000")
        self.assertEqual(len(eth_book["sell"]), 1)
        self.assertEqual(eth_book["sell"][0]["user_id"], "carol")
        self.assertEqual(eth_book["sell"][0]["remaining_quantity"], "3.00000000")

    def test_gui_one_click_demo_flow(self) -> None:
        state = DEXWebState(db_path=":memory:")
        result = state.run_demo_flow()
        snapshot = state.snapshot()

        self.assertIn("生成 2 笔成交", result["message"])
        self.assertEqual(len(snapshot["last_trade_flow"]), 4)
        self.assertEqual(len(snapshot["orders"]), 4)
        self.assertEqual(len(snapshot["chain"]), 2)
        self.assertEqual(snapshot["last_trade_flow"][0]["title"], "Bob 挂出 BTC/USDT 卖单")
        self.assertEqual(snapshot["last_trade_flow"][1]["trade_count"], 1)
        self.assertEqual(snapshot["last_trade_flow"][3]["trade_count"], 1)
        self.assertEqual(snapshot["last_trade_flow"][1]["trades"][0]["buyer_id"], "alice")
        self.assertEqual(snapshot["last_trade_flow"][1]["trades"][0]["seller_id"], "bob")
        self.assertEqual(snapshot["last_trade_flow"][3]["trades"][0]["pair"], "ETH/USDT")

    def test_gui_manual_order_flow_records_trade_details(self) -> None:
        state = DEXWebState(db_path=":memory:")
        state.place_order({
                "pair": "BTC/USDT",
                "side": "SELL",
                "price": "30000",
                "quantity": "1",
            }, user="bob")
        state.place_order({
                "pair": "BTC/USDT",
                "side": "BUY",
                "price": "31000",
                "quantity": "0.4",
            }, user="alice")
        snapshot = state.snapshot()

        self.assertEqual(len(snapshot["last_trade_flow"]), 2)
        self.assertEqual(snapshot["last_trade_flow"][0]["trade_count"], 0)
        self.assertEqual(snapshot["last_trade_flow"][1]["trade_count"], 1)
        trade = snapshot["last_trade_flow"][1]["trades"][0]
        self.assertEqual(trade["trade_id"], "T000001")
        self.assertEqual(trade["buyer_id"], "alice")
        self.assertEqual(trade["seller_id"], "bob")
        self.assertEqual(trade["quantity"], "0.40000000")
        self.assertEqual(trade["quote_amount"], "12000.00000000")

    def test_blockchain_snapshots_do_not_expose_internal_state(self) -> None:
        blockchain = SimpleBlockchain(block_capacity=10)
        transaction = {"trade_id": "T000001", "details": {"quantity": "1"}}

        blockchain.add_transaction(transaction)
        transaction["details"]["quantity"] = "999"
        pending_snapshot = blockchain.pending_transactions
        pending_snapshot[0]["details"]["quantity"] = "888"

        self.assertEqual(
            blockchain.pending_transactions[0]["details"]["quantity"],
            "1",
        )

        sealed_block = blockchain.seal_pending_transactions()
        sealed_block.transactions[0]["details"]["quantity"] = "777"
        chain_snapshot = blockchain.chain
        chain_snapshot[1].transactions[0]["details"]["quantity"] = "666"
        exported_chain = blockchain.export_chain()
        exported_chain[1]["transactions"][0]["details"]["quantity"] = "555"

        self.assertEqual(
            blockchain.export_chain()[1]["transactions"][0]["details"]["quantity"],
            "1",
        )
        self.assertTrue(blockchain.validate_chain())

    def test_decimal_normalization_rejects_non_finite_values(self) -> None:
        for value in ["NaN", "Infinity", "-Infinity"]:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    normalize_decimal(value)

    def test_market_buy_walks_book_across_levels(self) -> None:
        state = DEXWebState(db_path=":memory:")
        state.wallet_service.deposit("alice", Asset.USDT, "20000")
        state.wallet_service.deposit("carol", Asset.BTC, "0.5")
        state.place_order({"pair": "BTC/USDT", "side": "SELL", "price": "30000", "quantity": "0.4"}, user="bob")
        state.place_order({"pair": "BTC/USDT", "side": "SELL", "price": "30100", "quantity": "0.3"}, user="carol")

        result = state.place_order({
                "pair": "BTC/USDT",
                "side": "BUY",
                "type": "MARKET",
                "quantity": "0.5",
            }, user="alice")
        self.assertIn("市价单", result["message"])

        snapshot = state.snapshot()
        alice_orders = [o for o in snapshot["orders"] if o["user"] == "alice"]
        self.assertEqual(len(alice_orders), 1)
        self.assertEqual(alice_orders[0]["type"], "MARKET")
        self.assertEqual(alice_orders[0]["status"], "FILLED")
        self.assertEqual(alice_orders[0]["filled"], "0.50000000")
        self.assertEqual(Decimal(alice_orders[0]["price"]), Decimal("0"))

        # alice 起始 50000 + 充值 20000 = 70000 USDT；
        # 消耗 0.4 @ 30000 + 0.1 @ 30100 = 15010；剩 54990。
        alice_usdt = next(
            row for row in snapshot["wallets"] if row["user"] == "alice" and row["asset"] == "USDT"
        )
        self.assertEqual(Decimal(alice_usdt["available"]), Decimal("54990.00000000"))
        self.assertEqual(Decimal(alice_usdt["frozen"]), Decimal("0"))
        alice_btc = next(
            row for row in snapshot["wallets"] if row["user"] == "alice" and row["asset"] == "BTC"
        )
        self.assertEqual(Decimal(alice_btc["available"]), Decimal("0.50000000"))

        btc_book = snapshot["order_books"]["BTC/USDT"]
        self.assertEqual(len(btc_book["sell"]), 1)
        self.assertEqual(btc_book["sell"][0]["user_id"], "carol")
        self.assertEqual(btc_book["sell"][0]["remaining_quantity"], "0.20000000")

    def test_market_sell_consumes_buy_side_liquidity(self) -> None:
        state = DEXWebState(db_path=":memory:")
        state.place_order({"pair": "BTC/USDT", "side": "BUY", "price": "31000", "quantity": "0.2"}, user="alice")

        state.place_order({
                "pair": "BTC/USDT",
                "side": "SELL",
                "type": "MARKET",
                "quantity": "0.2",
            }, user="bob")

        snapshot = state.snapshot()
        bob_usdt = next(
            row for row in snapshot["wallets"] if row["user"] == "bob" and row["asset"] == "USDT"
        )
        self.assertEqual(Decimal(bob_usdt["available"]), Decimal("6200.00000000"))
        bob_btc = next(
            row for row in snapshot["wallets"] if row["user"] == "bob" and row["asset"] == "BTC"
        )
        self.assertEqual(Decimal(bob_btc["available"]), Decimal("0.80000000"))
        self.assertEqual(Decimal(bob_btc["frozen"]), Decimal("0"))

    def test_market_order_rejects_when_liquidity_insufficient(self) -> None:
        state = DEXWebState(db_path=":memory:")
        state.wallet_service.deposit("alice", Asset.USDT, "20000")
        state.place_order({"pair": "BTC/USDT", "side": "SELL", "price": "30000", "quantity": "0.1"}, user="bob")

        with self.assertRaises(EmptyOrderBookError):
            state.place_order({
                    "pair": "BTC/USDT",
                    "side": "BUY",
                    "type": "MARKET",
                    "quantity": "0.5",
                }, user="alice")

        # 拒绝时不应冻结资金
        snapshot = state.snapshot()
        alice_usdt = next(
            row for row in snapshot["wallets"] if row["user"] == "alice" and row["asset"] == "USDT"
        )
        self.assertEqual(Decimal(alice_usdt["frozen"]), Decimal("0"))
        self.assertEqual(Decimal(alice_usdt["available"]), Decimal("70000.00000000"))

    def test_market_order_skips_self_orders(self) -> None:
        state = DEXWebState(db_path=":memory:")
        state.wallet_service.deposit("alice", Asset.BTC, "1")
        state.wallet_service.deposit("alice", Asset.USDT, "20000")
        state.place_order({"pair": "BTC/USDT", "side": "SELL", "price": "29000", "quantity": "0.1"}, user="alice")
        state.place_order({"pair": "BTC/USDT", "side": "SELL", "price": "30000", "quantity": "0.5"}, user="bob")

        # 市价买单 0.3 BTC：应跳过 alice 自有卖单，全部从 bob 处吃单
        state.place_order({
                "pair": "BTC/USDT",
                "side": "BUY",
                "type": "MARKET",
                "quantity": "0.3",
            }, user="alice")

        snapshot = state.snapshot()
        # alice 自有卖单仍在 bob 卖单之前（价格更低），不应被消耗
        sell_book = snapshot["order_books"]["BTC/USDT"]["sell"]
        alice_sell = next(o for o in sell_book if o["user_id"] == "alice")
        self.assertEqual(alice_sell["remaining_quantity"], "0.10000000")
        bob_sell = next(o for o in sell_book if o["user_id"] == "bob")
        self.assertEqual(bob_sell["remaining_quantity"], "0.20000000")


class AuthServiceTest(unittest.TestCase):
    def test_login_returns_token_and_resolves_user(self) -> None:
        service = AuthService()
        service.register("dave", "dave-secret")
        token = service.login("dave", "dave-secret")

        self.assertTrue(service.is_authenticated(token))
        self.assertEqual(service.get_user_by_token(token).username, "dave")

    def test_logout_invalidates_token(self) -> None:
        service = AuthService()
        service.register("dave", "dave-secret")
        token = service.login("dave", "dave-secret")

        service.logout(token)

        self.assertFalse(service.is_authenticated(token))
        with self.assertRaises(InvalidCredentialsError):
            service.get_user_by_token(token)

    def test_login_with_wrong_password_raises(self) -> None:
        service = AuthService()
        service.register("dave", "dave-secret")

        with self.assertRaises(InvalidCredentialsError):
            service.login("dave", "wrong-password")

    def test_login_with_unknown_user_raises(self) -> None:
        service = AuthService()
        with self.assertRaises(UserNotFoundError):
            service.login("ghost", "irrelevant")


class HttpAuthIntegrationTest(unittest.TestCase):
    """启动一个真正的 ThreadingHTTPServer 测试鉴权链路。"""

    def setUp(self) -> None:
        gui.STATE = DEXWebState(db_path=":memory:")
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), gui.DEXRequestHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        host, port = self._server.server_address
        self._base = f"http://{host}:{port}"

    def tearDown(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)

    def _request(
        self,
        path: str,
        payload: dict | None = None,
        token: str | None = None,
        method: str | None = None,
    ) -> tuple[int, dict]:
        body = None
        headers = {}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(
            self._base + path,
            data=body,
            headers=headers,
            method=method or ("POST" if payload is not None else "GET"),
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def _login(self, username: str, password: str) -> str:
        status, body = self._request("/api/login", {"username": username, "password": password})
        self.assertEqual(status, 200)
        return body["token"]

    def test_protected_route_without_token_returns_401(self) -> None:
        status, body = self._request(
            "/api/wallet",
            {"asset": "USDT", "amount": "1", "action": "deposit"},
        )
        self.assertEqual(status, 401)
        self.assertIn("Authorization", body["error"])

    def test_protected_route_with_invalid_token_returns_401(self) -> None:
        status, body = self._request(
            "/api/wallet",
            {"asset": "USDT", "amount": "1", "action": "deposit"},
            token="not-a-real-token",
        )
        self.assertEqual(status, 401)
        self.assertIn("会话令牌", body["error"])

    def test_login_returns_token_and_wallet_works_with_it(self) -> None:
        token = self._login("alice", "alice123")
        status, body = self._request(
            "/api/wallet",
            {"asset": "USDT", "amount": "100", "action": "deposit"},
            token=token,
        )
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["current_user"], "alice")

    def test_wallet_uses_token_user_not_body_username(self) -> None:
        """请求体里夹带 username 不应改变操作主体——以 token 解析的用户为准。"""
        alice_token = self._login("alice", "alice123")
        status, body = self._request(
            "/api/wallet",
            {
                "username": "bob",
                "asset": "USDT",
                "amount": "100",
                "action": "deposit",
            },
            token=alice_token,
        )
        self.assertEqual(status, 200)
        self.assertIn("alice 充值", body["message"])
        alice_usdt = next(
            row
            for row in body["data"]["wallets"]
            if row["user"] == "alice" and row["asset"] == "USDT"
        )
        bob_usdt = next(
            row
            for row in body["data"]["wallets"]
            if row["user"] == "bob" and row["asset"] == "USDT"
        )
        self.assertEqual(Decimal(alice_usdt["available"]), Decimal("50100.00000000"))
        self.assertEqual(Decimal(bob_usdt["available"]), Decimal("0"))

    def test_logout_invalidates_token_for_subsequent_requests(self) -> None:
        token = self._login("alice", "alice123")
        status, _ = self._request("/api/logout", {}, token=token)
        self.assertEqual(status, 200)

        status, body = self._request(
            "/api/wallet",
            {"asset": "USDT", "amount": "1", "action": "deposit"},
            token=token,
        )
        self.assertEqual(status, 401)
        self.assertIn("会话令牌", body["error"])


if __name__ == "__main__":
    unittest.main()
