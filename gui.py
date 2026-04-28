"""Browser-based GUI for the DEX demo system.

Run with:
    python3 gui.py

The implementation uses only Python standard library modules. It serves a
single-page interface plus small JSON endpoints that call the existing DEX
services.
"""

from __future__ import annotations

import errno
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import urlparse

from app import build_demo_services, build_persistent_services
from exceptions import DEXError, UserAlreadyExistsError, ValidationError
from models import Asset, OrderSide, TradingPair


HOST = "127.0.0.1"
PORT = 8000
MAX_PORT_ATTEMPTS = 20

PAIRS = {
    "BTC/USDT": TradingPair(Asset.BTC, Asset.USDT),
    "ETH/USDT": TradingPair(Asset.ETH, Asset.USDT),
    "ETH/BTC": TradingPair(Asset.ETH, Asset.BTC),
}


class DEXWebState:
    """Owns the SQLite-backed services used by the GUI server."""

    def __init__(self, db_path: str = "dex.db") -> None:
        from database import init_db
        self._db_path = db_path
        self._conn = init_db(db_path)
        self.current_user: str | None = None
        self.last_trade_flow: list[dict[str, Any]] = []
        self._rebuild_services()
        self._seed_demo_accounts()

    def _rebuild_services(self) -> None:
        """用当前 conn 重新创建所有服务实例（init 或 reset 后调用）。"""
        from auth import AuthService
        from blockchain import SimpleBlockchain
        from engine import MatchingEngine
        from wallet import WalletService
        from app import _SUPPORTED_PAIRS

        self.auth_service = AuthService(conn=self._conn)
        self.wallet_service = WalletService(
            supported_assets=[Asset.BTC, Asset.ETH, Asset.USDT], conn=self._conn
        )
        self.blockchain = SimpleBlockchain(block_capacity=2, conn=self._conn)
        self.engine = MatchingEngine(
            auth_service=self.auth_service,
            wallet_service=self.wallet_service,
            blockchain=self.blockchain,
            supported_pairs=_SUPPORTED_PAIRS,
            conn=self._conn,
        )

    def reset(self) -> None:
        from database import clear_db
        clear_db(self._conn)
        self.current_user = None
        self.last_trade_flow = []
        self._rebuild_services()
        self._seed_demo_accounts()

    def _seed_demo_accounts(self) -> None:
        if self.auth_service.list_users():
            return
        for username, password in [
            ("alice", "alice123"),
            ("bob", "bob123"),
            ("carol", "carol123"),
        ]:
            self.auth_service.register(username, password)
            self.wallet_service.create_wallet_for_user(username)

        self.wallet_service.deposit("alice", Asset.USDT, "50000")
        self.wallet_service.deposit("bob", Asset.BTC, "1")
        self.wallet_service.deposit("bob", Asset.ETH, "2")
        self.wallet_service.deposit("carol", Asset.ETH, "5")
        self.wallet_service.deposit("carol", Asset.USDT, "10000")

    def register(self, payload: dict[str, Any]) -> dict[str, Any]:
        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", ""))
        self.auth_service.register(username, password)
        self.wallet_service.create_wallet_for_user(username)
        return {"message": f"用户 {username} 注册成功。"}

    def login(self, payload: dict[str, Any]) -> dict[str, Any]:
        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", ""))
        self.auth_service.login(username, password)
        self.current_user = username
        return {"message": f"用户 {username} 登录成功。", "current_user": username}

    def wallet_action(self, payload: dict[str, Any]) -> dict[str, Any]:
        username = str(payload.get("username", "")).strip()
        self._ensure_registered(username)
        asset = Asset(str(payload.get("asset", "")))
        amount = str(payload.get("amount", "")).strip()
        action = str(payload.get("action", "")).strip()

        if action == "deposit":
            self.wallet_service.deposit(username, asset, amount)
            verb = "充值"
        elif action == "withdraw":
            self.wallet_service.withdraw(username, asset, amount)
            verb = "提现"
        else:
            raise ValidationError("未知钱包操作。")

        return {"message": f"{username} {verb} {amount} {asset.value} 成功。"}

    def place_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        username = str(payload.get("username", "")).strip()
        self._ensure_registered(username)
        pair = PAIRS[str(payload.get("pair", ""))]
        side = OrderSide(str(payload.get("side", "")))
        result = self.engine.place_limit_order(
            user_id=username,
            pair=pair,
            side=side,
            price=str(payload.get("price", "")).strip(),
            quantity=str(payload.get("quantity", "")).strip(),
        )
        self._record_order_flow(result)
        blocked = "，自成交保护已触发" if result.self_trade_blocked else ""
        return {
            "message": (
                f"订单 {result.order.order_id} 提交成功，状态 {result.order.status.value}，"
                f"本次成交 {len(result.trades)} 笔{blocked}。"
            )
        }

    def cancel_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        username = str(payload.get("username", "")).strip()
        order_id = str(payload.get("order_id", "")).strip()
        if not order_id:
            raise ValidationError("订单号不能为空。")
        self._ensure_registered(username)
        order = self.engine.cancel_order(user_id=username, order_id=order_id)
        return {
            "message": (
                f"订单 {order.order_id} 已撤销，剩余 {order.remaining_quantity} "
                f"{order.pair.base_asset.value} 已解冻。"
            )
        }

    def run_demo_flow(self) -> dict[str, Any]:
        """Reset and run the required Bob/Alice/Carol trading scenario."""
        self.reset()
        btc_usdt = PAIRS["BTC/USDT"]
        eth_usdt = PAIRS["ETH/USDT"]

        result_1 = self.engine.place_limit_order(
            user_id="bob",
            pair=btc_usdt,
            side=OrderSide.SELL,
            price="30000",
            quantity="1",
        )
        step_1 = self._flow_step(
            1,
            "Bob 挂出 BTC/USDT 卖单",
            "Bob 冻结 1 BTC，卖单进入 BTC/USDT 卖单簿。",
            result_1,
        )

        result_2 = self.engine.place_limit_order(
            user_id="alice",
            pair=btc_usdt,
            side=OrderSide.BUY,
            price="31000",
            quantity="0.4",
        )
        step_2 = self._flow_step(
            2,
            "Alice 提交 BTC/USDT 买单",
            "Alice 与 Bob 成交 0.4 BTC，Bob 卖单剩余 0.6 BTC。",
            result_2,
        )

        result_3 = self.engine.place_limit_order(
            user_id="alice",
            pair=eth_usdt,
            side=OrderSide.BUY,
            price="2100",
            quantity="2",
        )
        step_3 = self._flow_step(
            3,
            "Alice 提交 ETH/USDT 买单",
            "Alice 冻结 4200 USDT，买单进入 ETH/USDT 买单簿。",
            result_3,
        )

        result_4 = self.engine.place_limit_order(
            user_id="carol",
            pair=eth_usdt,
            side=OrderSide.SELL,
            price="2000",
            quantity="5",
        )
        step_4 = self._flow_step(
            4,
            "Carol 提交 ETH/USDT 卖单",
            "Carol 与 Alice 成交 2 ETH，Carol 卖单剩余 3 ETH。",
            result_4,
        )

        if self.blockchain.pending_transactions:
            self.blockchain.seal_pending_transactions()
        self.blockchain.validate_chain()

        self.last_trade_flow = [step_1, step_2, step_3, step_4]
        return {"message": "已执行 Bob/Alice/Carol 币种交易流程，生成 2 笔成交并完成链校验。"}

    def seal_block(self) -> dict[str, Any]:
        block = self.blockchain.seal_pending_transactions()
        return {"message": f"已封装区块 #{block.index}，包含 {len(block.transactions)} 笔交易。"}

    def validate_chain(self) -> dict[str, Any]:
        self.blockchain.validate_chain()
        return {"message": "区块链完整性校验通过。"}

    def snapshot(self) -> dict[str, Any]:
        users = sorted(self.auth_service.list_users())
        wallets = []
        for username in users:
            snapshot = self.wallet_service.get_wallet_snapshot(username)
            for asset in Asset:
                wallets.append(
                    {
                        "user": username,
                        "asset": asset.value,
                        "available": snapshot["available"][asset.value],
                        "frozen": snapshot["frozen"][asset.value],
                        "total": snapshot["total"][asset.value],
                    }
                )

        orders = []
        for order in sorted(self.engine.list_orders().values(), key=lambda item: item.sequence):
            orders.append(
                {
                    "id": order.order_id,
                    "user": order.user_id,
                    "pair": order.pair.symbol,
                    "side": order.side.value,
                    "price": str(order.price),
                    "quantity": str(order.quantity),
                    "filled": str(order.filled_quantity),
                    "remaining": str(order.remaining_quantity),
                    "status": order.status.value,
                    "sequence": order.sequence,
                }
            )

        order_books = {
            symbol: self.engine.get_order_book_snapshot(pair) for symbol, pair in PAIRS.items()
        }
        chain = self.blockchain.export_chain()
        pending_transactions = self.blockchain.pending_transactions

        return {
            "current_user": self.current_user,
            "users": users,
            "wallets": wallets,
            "orders": orders,
            "order_books": order_books,
            "chain": chain,
            "pending_transactions": pending_transactions,
            "last_trade_flow": self.last_trade_flow,
            "pairs": list(PAIRS),
            "assets": [asset.value for asset in Asset],
            "sides": [side.value for side in OrderSide],
        }

    @staticmethod
    def _flow_step(
        step: int,
        title: str,
        description: str,
        result: Any,
    ) -> dict[str, Any]:
        order = result.order
        return {
            "step": step,
            "title": title,
            "description": description,
            "order_id": order.order_id,
            "user": order.user_id,
            "pair": order.pair.symbol,
            "side": order.side.value,
            "price": str(order.price),
            "quantity": str(order.quantity),
            "filled": str(order.filled_quantity),
            "remaining": str(order.remaining_quantity),
            "status": order.status.value,
            "trade_count": len(result.trades),
            "trades": [trade.to_record() for trade in result.trades],
        }

    def _record_order_flow(self, result: Any) -> None:
        """Append a GUI flow row for a manually submitted order."""
        order = result.order
        side_text = "买单" if order.side is OrderSide.BUY else "卖单"
        trade_count = len(result.trades)
        if trade_count:
            description = f"订单触发撮合，生成 {trade_count} 笔成交。"
        elif result.self_trade_blocked:
            description = "订单遇到同一用户的对手单，自成交保护已触发。"
        else:
            description = "订单已进入订单簿，等待后续撮合。"
        self.last_trade_flow.append(
            self._flow_step(
                len(self.last_trade_flow) + 1,
                f"{order.user_id} 提交 {order.pair.symbol} {side_text}",
                description,
                result,
            )
        )

    def _ensure_registered(self, username: str) -> None:
        if not self.auth_service.user_exists(username):
            raise ValidationError(f"用户 {username} 未注册。")


STATE = DEXWebState()


class DEXRequestHandler(BaseHTTPRequestHandler):
    """HTTP handler for the browser GUI."""

    server_version = "DEXGui/1.0"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._send_html(INDEX_HTML)
        elif path == "/api/state":
            self._send_json({"ok": True, "data": STATE.snapshot()})
        else:
            self._send_json({"ok": False, "error": "接口不存在。"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        routes: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "/api/register": STATE.register,
            "/api/login": STATE.login,
            "/api/wallet": STATE.wallet_action,
            "/api/order": STATE.place_order,
            "/api/cancel": STATE.cancel_order,
        }
        no_payload_routes: dict[str, Callable[[], dict[str, Any]]] = {
            "/api/seal": STATE.seal_block,
            "/api/validate": STATE.validate_chain,
            "/api/demo-flow": STATE.run_demo_flow,
            "/api/reset": self._reset_state,
        }

        path = urlparse(self.path).path
        try:
            if path in routes:
                result = routes[path](self._read_json())
            elif path in no_payload_routes:
                result = no_payload_routes[path]()
            else:
                self._send_json({"ok": False, "error": "接口不存在。"}, HTTPStatus.NOT_FOUND)
                return
        except DEXError as exc:
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        except (KeyError, ValueError) as exc:
            self._send_json({"ok": False, "error": f"非法请求参数: {exc}"}, HTTPStatus.BAD_REQUEST)
            return

        self._send_json({"ok": True, **result, "data": STATE.snapshot()})

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValidationError("请求体必须是 JSON 对象。")
        return data

    def _reset_state(self) -> dict[str, Any]:
        STATE.reset()
        return {"message": "系统已重置并载入示例账户。"}

    def _send_html(self, html: str) -> None:
        payload = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_json(self, data: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DEX 核心系统可视化</title>
  <style>
    :root {
      --bg: #eef1f4;
      --panel: #ffffff;
      --ink: #1d232b;
      --muted: #66717f;
      --line: #dce2e8;
      --blue: #215b8f;
      --blue-dark: #17446e;
      --green: #19715a;
      --red: #b13b3c;
      --gold: #ad7a20;
      --shadow: 0 10px 26px rgba(32, 38, 46, .07);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Arial, "Microsoft YaHei", sans-serif;
      color: var(--ink);
      background: var(--bg);
    }
    .app {
      min-height: 100vh;
      display: grid;
      grid-template-columns: 360px minmax(0, 1fr);
      gap: 16px;
      padding: 16px;
    }
    aside, main section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }
    aside {
      align-self: start;
      max-height: calc(100vh - 32px);
      overflow: auto;
      padding: 16px;
      position: sticky;
      top: 16px;
    }
    .brand {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
    }
    h1 {
      margin: 0;
      font-size: 22px;
      letter-spacing: 0;
    }
    h2 {
      margin: 0 0 12px;
      font-size: 15px;
      letter-spacing: 0;
    }
    .control-panel {
      padding: 14px 0 16px;
      border-top: 1px solid var(--line);
    }
    .control-panel:first-of-type {
      border-top: 0;
      padding-top: 0;
    }
    .field-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
    }
    .field-grid .wide {
      grid-column: 1 / -1;
    }
    label {
      display: block;
      margin: 0 0 5px;
      color: var(--muted);
      font-size: 13px;
    }
    input, select {
      width: 100%;
      height: 36px;
      padding: 6px 9px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fbfcfd;
      color: var(--ink);
      font-size: 14px;
    }
    input:focus, select:focus {
      border-color: var(--blue);
      box-shadow: 0 0 0 3px rgba(33, 91, 143, .14);
      outline: 0;
    }
    button {
      width: 100%;
      height: 36px;
      border: 0;
      border-radius: 6px;
      background: var(--blue);
      color: #fff;
      font-weight: 700;
      cursor: pointer;
      transition: background .15s ease, transform .15s ease, opacity .15s ease;
    }
    button:hover { background: var(--blue-dark); }
    button:active { transform: translateY(1px); }
    button:disabled { cursor: wait; opacity: .62; }
    button.secondary { background: #4d5a67; }
    button.success { background: var(--green); }
    button.warning { background: var(--gold); }
    button.danger { background: var(--red); }
    button.cancel-btn {
      width: auto;
      height: 26px;
      padding: 0 12px;
      font-size: 12px;
      background: var(--red);
    }
    button.cancel-btn:hover { background: #b13a3a; }
    .row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-top: 10px;
    }
    .stack {
      display: grid;
      gap: 10px;
    }
    .status {
      min-height: 42px;
      margin-top: 14px;
      padding: 10px;
      border: 1px solid var(--line);
      border-left: 4px solid var(--blue);
      border-radius: 6px;
      background: #f8fafb;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }
    .status.error {
      border-left-color: var(--red);
      background: #fff7f7;
      color: var(--red);
    }
    .status.ok {
      border-left-color: var(--green);
      background: #f5fbf8;
      color: #245e4d;
    }
    main {
      min-width: 0;
      display: grid;
      grid-template-rows: auto minmax(0, 1fr) minmax(0, .9fr);
      gap: 14px;
    }
    .metrics {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }
    .metric {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      box-shadow: var(--shadow);
    }
    .metric span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }
    .metric strong {
      display: block;
      margin-top: 6px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 23px;
    }
    section {
      min-width: 0;
      padding: 14px;
      overflow: hidden;
    }
    .section-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 10px;
    }
    .section-head h2 {
      margin: 0;
      font-size: 16px;
    }
    .tabs {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }
    .tabs button {
      width: auto;
      padding: 0 12px;
      background: #e7ebef;
      color: var(--ink);
      font-weight: 600;
    }
    .tabs button.active {
      background: var(--blue);
      color: #fff;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      padding: 2px 8px;
      border-radius: 999px;
      background: #eef2f5;
      color: #384451;
      font-size: 12px;
      font-weight: 700;
    }
    .badge.open { background: #eef6ff; color: var(--blue); }
    .badge.filled { background: #edf8f3; color: var(--green); }
    .badge.partial { background: #fff8e6; color: var(--gold); }
    .table-wrap {
      width: 100%;
      max-height: 44vh;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 760px;
      background: #fff;
    }
    th, td {
      padding: 9px 10px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      white-space: nowrap;
      font-size: 13px;
    }
    th {
      background: #eef2f5;
      color: #384451;
      font-weight: 700;
      position: sticky;
      top: 0;
      z-index: 1;
    }
    tbody tr:hover td { background: #f8fafc; }
    tr:last-child td { border-bottom: 0; }
    .buy, .sell {
      display: inline-flex;
      align-items: center;
      min-width: 46px;
      justify-content: center;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
    }
    .buy { background: #edf8f3; color: var(--green); }
    .sell { background: #fff0f0; color: var(--red); }
    .hash { font-family: Consolas, Monaco, monospace; }
    .empty-state {
      min-height: 84px;
      display: grid;
      place-items: center;
      color: var(--muted);
      font-size: 13px;
    }
    .flow-detail {
      min-width: 340px;
      max-width: 620px;
      white-space: normal;
      line-height: 1.45;
    }
    .flow-note {
      color: var(--muted);
      margin-bottom: 4px;
    }
    .trade-detail + .trade-detail {
      margin-top: 4px;
    }
    .hidden { display: none; }
    @media (max-width: 920px) {
      .app { grid-template-columns: 1fr; padding: 10px; }
      aside { position: static; max-height: none; }
      main { grid-template-rows: auto auto auto; }
      .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .section-head { align-items: flex-start; flex-direction: column; }
      .table-wrap { max-height: none; }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside>
      <div class="brand">
        <h1>DEX 操作台</h1>
        <span class="badge" id="pendingBadge">0 待打包</span>
      </div>

      <div class="control-panel">
        <h2>用户认证</h2>
        <div class="field-grid">
          <div>
            <label for="authUser">用户名</label>
            <input id="authUser" value="alice">
          </div>
          <div>
            <label for="authPass">密码</label>
            <input id="authPass" type="password" value="alice123">
          </div>
        </div>
        <div class="row">
          <button onclick="registerUser()">注册</button>
          <button class="success" onclick="loginUser()">登录</button>
        </div>
      </div>

      <div class="control-panel">
        <h2>钱包操作</h2>
        <div class="field-grid">
          <div class="wide">
            <label for="walletUser">用户</label>
            <select id="walletUser"></select>
          </div>
          <div>
            <label for="walletAsset">币种</label>
            <select id="walletAsset"></select>
          </div>
          <div>
            <label for="walletAmount">金额</label>
            <input id="walletAmount" value="1000">
          </div>
        </div>
        <div class="row">
          <button class="success" onclick="walletAction('deposit')">充值</button>
          <button class="warning" onclick="walletAction('withdraw')">提现</button>
        </div>
      </div>

      <div class="control-panel">
        <h2>限价下单</h2>
        <div class="field-grid">
          <div class="wide">
            <label for="orderUser">用户</label>
            <select id="orderUser"></select>
          </div>
          <div>
            <label for="orderPair">交易对</label>
            <select id="orderPair"></select>
          </div>
          <div>
            <label for="orderSide">方向</label>
            <select id="orderSide"></select>
          </div>
          <div>
            <label for="orderPrice">价格</label>
            <input id="orderPrice" value="31000">
          </div>
          <div>
            <label for="orderQuantity">数量</label>
            <input id="orderQuantity" value="0.1">
          </div>
        </div>
        <button style="margin-top:10px" onclick="placeOrder()">提交订单</button>
      </div>

      <div class="control-panel">
        <h2>系统操作</h2>
        <div class="stack">
          <button class="success" onclick="runDemoFlow()">执行交易流程</button>
          <div class="row">
            <button class="secondary" onclick="sealBlock()">封装区块</button>
            <button class="secondary" onclick="validateChain()">校验链</button>
          </div>
          <div class="row">
            <button class="danger" onclick="resetDemo()">重置</button>
            <button class="secondary" onclick="loadState()">刷新</button>
          </div>
        </div>
      </div>
      <div class="status" id="status">正在加载系统状态...</div>
    </aside>

    <main>
      <div class="metrics">
        <div class="metric"><span>当前用户</span><strong id="metricUser">未登录</strong></div>
        <div class="metric"><span>用户数</span><strong id="metricUsers">0</strong></div>
        <div class="metric"><span>订单数</span><strong id="metricOrders">0</strong></div>
        <div class="metric"><span>区块数</span><strong id="metricBlocks">0</strong></div>
      </div>

      <section>
        <div class="section-head">
          <h2>业务数据</h2>
          <div class="tabs">
            <button class="active" onclick="showTab('wallets', this)">钱包</button>
            <button onclick="showTab('orders', this)">订单</button>
            <button onclick="showTab('books', this)">订单簿</button>
            <button onclick="showTab('flow', this)">交易流程</button>
          </div>
        </div>
        <div id="wallets" class="table-wrap"></div>
        <div id="orders" class="table-wrap hidden"></div>
        <div id="books" class="table-wrap hidden"></div>
        <div id="flow" class="table-wrap hidden"></div>
      </section>

      <section>
        <div class="section-head">
          <h2>链式账本</h2>
          <span id="pendingInfo"></span>
        </div>
        <div id="chain" class="table-wrap"></div>
      </section>
    </main>
  </div>

  <script>
    let state = null;
    let activeRequests = 0;

    function setStatus(message, failed = false) {
      const box = document.getElementById("status");
      box.textContent = message;
      box.classList.toggle("error", failed);
      box.classList.toggle("ok", !failed);
    }

    function optionList(values) {
      return values
        .map(value => `<option value="${escapeHTML(value)}">${escapeHTML(value)}</option>`)
        .join("");
    }

    function escapeHTML(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    }

    function raw(value) {
      return { raw: String(value) };
    }

    function setBusy(busy) {
      activeRequests += busy ? 1 : -1;
      const disabled = activeRequests > 0;
      for (const button of document.querySelectorAll("button")) {
        button.disabled = disabled;
      }
    }

    async function api(path, payload = null) {
      setBusy(true);
      try {
        const options = { method: payload === null ? "GET" : "POST" };
        if (payload !== null) {
          options.headers = { "Content-Type": "application/json" };
          options.body = JSON.stringify(payload);
        }
        const response = await fetch(path, options);
        const result = await response.json();
        if (!result.ok) {
          throw new Error(result.error || "请求失败");
        }
        return result;
      } finally {
        setBusy(false);
      }
    }

    async function loadState() {
      try {
        const result = await api("/api/state");
        state = result.data;
        render();
        setStatus("系统状态已刷新。");
      } catch (error) {
        setStatus(error.message, true);
      }
    }

    async function postAction(path, payload, fallbackMessage) {
      try {
        const result = await api(path, payload);
        state = result.data;
        if (path === "/api/login" && state.current_user) {
          walletUser.dataset.value = state.current_user;
          orderUser.dataset.value = state.current_user;
        }
        render();
        setStatus(result.message || fallbackMessage);
      } catch (error) {
        setStatus(error.message, true);
      }
    }

    function registerUser() {
      postAction("/api/register", {
        username: authUser.value,
        password: authPass.value
      }, "注册成功。");
    }

    function loginUser() {
      postAction("/api/login", {
        username: authUser.value,
        password: authPass.value
      }, "登录成功。");
    }

    function walletAction(action) {
      postAction("/api/wallet", {
        action,
        username: walletUser.value,
        asset: walletAsset.value,
        amount: walletAmount.value
      }, "钱包操作成功。");
    }

    function placeOrder() {
      postAction("/api/order", {
        username: orderUser.value,
        pair: orderPair.value,
        side: orderSide.value,
        price: orderPrice.value,
        quantity: orderQuantity.value
      }, "订单提交成功。");
    }

    function sealBlock() {
      postAction("/api/seal", {}, "区块封装成功。");
    }

    function validateChain() {
      postAction("/api/validate", {}, "区块链完整性校验通过。");
    }

    function runDemoFlow() {
      postAction("/api/demo-flow", {}, "交易流程执行完成。");
    }

    function resetDemo() {
      postAction("/api/reset", {}, "系统已重置。");
    }

    function showTab(id, button) {
      for (const panel of ["wallets", "orders", "books", "flow"]) {
        document.getElementById(panel).classList.toggle("hidden", panel !== id);
      }
      for (const tab of button.parentElement.querySelectorAll("button")) {
        tab.classList.toggle("active", tab === button);
      }
    }

    function render() {
      if (!state) return;
      walletUser.innerHTML = optionList(state.users);
      orderUser.innerHTML = optionList(state.users);
      walletAsset.innerHTML = optionList(state.assets);
      orderPair.innerHTML = optionList(state.pairs);
      orderSide.innerHTML = optionList(state.sides);
      const defaultUser = state.current_user || state.users[0] || "";
      keepValue(walletUser, defaultUser);
      keepValue(orderUser, defaultUser);
      keepValue(walletAsset, "USDT");
      keepValue(orderPair, "BTC/USDT");
      keepValue(orderSide, "BUY");

      metricUser.textContent = state.current_user || "未登录";
      metricUsers.textContent = state.users.length;
      metricOrders.textContent = state.orders.length;
      metricBlocks.textContent = state.chain.length;
      pendingInfo.textContent = `待打包交易 ${state.pending_transactions.length} 笔`;
      pendingBadge.textContent = `${state.pending_transactions.length} 待打包`;

      renderWallets();
      renderOrders();
      renderBooks();
      renderFlow();
      renderChain();
    }

    function keepValue(select, fallback) {
      if ([...select.options].some(option => option.value === select.dataset.value)) {
        select.value = select.dataset.value;
      } else {
        select.value = fallback;
      }
      select.onchange = () => { select.dataset.value = select.value; };
    }

    function renderWallets() {
      wallets.innerHTML = table(
        ["用户", "币种", "可用余额", "冻结余额", "总余额"],
        state.wallets.map(row => [
          row.user,
          row.asset,
          formatDecimal(row.available),
          formatDecimal(row.frozen),
          formatDecimal(row.total)
        ])
      );
    }

    function renderOrders() {
      orders.innerHTML = table(
        ["订单ID", "用户", "交易对", "方向", "价格", "数量", "已成交", "剩余", "状态", "操作"],
        state.orders.map(row => [
          row.id,
          row.user,
          row.pair,
          sideCell(row.side),
          formatDecimal(row.price),
          formatDecimal(row.quantity),
          formatDecimal(row.filled),
          formatDecimal(row.remaining),
          statusCell(row.status),
          (row.status === "OPEN" || row.status === "PARTIALLY_FILLED")
            ? `<button class="cancel-btn" onclick="cancelOrder('${row.id}','${row.user}')">撤单</button>`
            : ""
        ])
      );
    }

    function cancelOrder(orderId, owner) {
      const username = (state.current_user || owner || "").trim();
      if (!username) {
        setStatus("请先登录后再撤单。", true);
        return;
      }
      postAction("/api/cancel", { username, order_id: orderId }, "撤单成功。");
    }

    function renderBooks() {
      const rows = [];
      for (const [pair, book] of Object.entries(state.order_books)) {
        for (const order of book.sell) {
          rows.push([pair, sideCell("SELL"), order.order_id, order.user_id, formatDecimal(order.price), formatDecimal(order.remaining_quantity), statusCell(order.status)]);
        }
        for (const order of book.buy) {
          rows.push([pair, sideCell("BUY"), order.order_id, order.user_id, formatDecimal(order.price), formatDecimal(order.remaining_quantity), statusCell(order.status)]);
        }
      }
      books.innerHTML = table(["交易对", "方向", "订单ID", "用户", "价格", "剩余数量", "状态"], rows);
    }

    function renderFlow() {
      flow.innerHTML = table(
        ["步骤", "动作", "说明/成交明细", "用户", "交易对", "方向", "价格", "数量", "已成交", "剩余", "状态", "成交数"],
        state.last_trade_flow.map(row => [
          row.step,
          row.title,
          flowDetailCell(row),
          row.user,
          row.pair,
          sideCell(row.side),
          formatDecimal(row.price),
          formatDecimal(row.quantity),
          formatDecimal(row.filled),
          formatDecimal(row.remaining),
          statusCell(row.status),
          row.trade_count
        ])
      );
    }

    function flowDetailCell(row) {
      const note = row.description
        ? `<div class="flow-note">${escapeHTML(row.description)}</div>`
        : "";
      const trades = row.trades || [];
      if (!trades.length) {
        return raw(`<div class="flow-detail">${note || "暂无成交，订单正在等待撮合。"}</div>`);
      }
      const details = trades.map(trade => {
        const [base, quote] = escapeHTML(trade.pair).split("/");
        return (
          `<div class="trade-detail">` +
          `${escapeHTML(trade.trade_id)}：${escapeHTML(trade.buyer_id)} 从 ${escapeHTML(trade.seller_id)} 买入 ` +
          `${escapeHTML(formatDecimal(trade.quantity))} ${base}，成交价 ${escapeHTML(formatDecimal(trade.price))} ${quote}/${base}，` +
          `成交额 ${escapeHTML(formatDecimal(trade.quote_amount))} ${quote}。` +
          `</div>`
        );
      }).join("");
      return raw(`<div class="flow-detail">${note}${details}</div>`);
    }

    function renderChain() {
      const rows = state.chain.map(block => [
        block.index,
        block.transactions.length,
        hashCell(block.previous_hash),
        hashCell(block.block_hash),
        block.timestamp
      ]);
      if (state.pending_transactions.length) {
        rows.push(["待打包", state.pending_transactions.length, "-", "-", "尚未封装"]);
      }
      chain.innerHTML = table(["区块", "交易数", "前一区块哈希", "当前哈希", "时间"], rows);
    }

    function table(headers, rows) {
      const head = headers.map(item => `<th>${escapeHTML(item)}</th>`).join("");
      const body = rows.length
        ? rows.map(row => `<tr>${row.map(cell => `<td>${cellHTML(cell)}</td>`).join("")}</tr>`).join("")
        : `<tr><td colspan="${headers.length}"><div class="empty-state">暂无数据</div></td></tr>`;
      return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
    }

    function cellHTML(cell) {
      if (cell && typeof cell === "object" && Object.prototype.hasOwnProperty.call(cell, "raw")) {
        return cell.raw;
      }
      return escapeHTML(cell);
    }

    function sideCell(side) {
      const klass = side === "BUY" ? "buy" : "sell";
      return raw(`<span class="${klass}">${escapeHTML(side)}</span>`);
    }

    function statusCell(status) {
      const klass = status === "FILLED"
        ? "filled"
        : status === "PARTIALLY_FILLED"
          ? "partial"
          : "open";
      return raw(`<span class="badge ${klass}">${escapeHTML(status)}</span>`);
    }

    function formatDecimal(value) {
      const text = String(value);
      if (!/^-?\d+(\.\d+)?(e-?\d+)?$/i.test(text)) {
        return text;
      }
      const number = Number(text);
      if (!Number.isFinite(number)) {
        return text;
      }
      return number.toFixed(8);
    }

    function hashCell(value) {
      const text = value.length > 18 ? `${value.slice(0, 10)}...${value.slice(-6)}` : value;
      return raw(`<span class="hash" title="${escapeHTML(value)}">${escapeHTML(text)}</span>`);
    }

    loadState();
  </script>
</body>
</html>
"""


def main() -> None:
    server = _build_server()
    print(f"DEX GUI running at http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _build_server() -> ThreadingHTTPServer:
    """Bind to PORT, or the next available local port."""
    global PORT
    for port in range(PORT, PORT + MAX_PORT_ATTEMPTS):
        try:
            server = ThreadingHTTPServer((HOST, port), DEXRequestHandler)
        except OSError as exc:
            if exc.errno != errno.EADDRINUSE:
                raise
            continue
        PORT = port
        return server
    raise OSError(f"无法在 {HOST}:{PORT}-{PORT + MAX_PORT_ATTEMPTS - 1} 范围内启动 GUI。")


if __name__ == "__main__":
    main()
