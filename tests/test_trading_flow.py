from __future__ import annotations

from decimal import Decimal
import unittest

from app import run_demo
from blockchain import SimpleBlockchain
from exceptions import ValidationError
from gui import DEXWebState
from models import normalize_decimal


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
        state = DEXWebState()
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
        state = DEXWebState()
        state.place_order(
            {
                "username": "bob",
                "pair": "BTC/USDT",
                "side": "SELL",
                "price": "30000",
                "quantity": "1",
            }
        )
        state.place_order(
            {
                "username": "alice",
                "pair": "BTC/USDT",
                "side": "BUY",
                "price": "31000",
                "quantity": "0.4",
            }
        )
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


if __name__ == "__main__":
    unittest.main()
