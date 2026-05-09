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
import os
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from exceptions import DEXError, ValidationError
from models import Asset, OrderSide, OrderType, TradingPair


HOST = "127.0.0.1"
PORT = 8000
MAX_PORT_ATTEMPTS = 20

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
STATIC_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".ico": "image/x-icon",
    ".svg": "image/svg+xml",
    ".png": "image/png",
}

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
        token = self.auth_service.login(username, password)
        return {
            "message": f"用户 {username} 登录成功。",
            "current_user": username,
            "token": token,
        }

    def logout(self, *, token: str) -> dict[str, Any]:
        self.auth_service.logout(token)
        return {"message": "已退出登录。"}

    def wallet_action(self, payload: dict[str, Any], *, user: str) -> dict[str, Any]:
        asset = Asset(str(payload.get("asset", "")))
        amount = str(payload.get("amount", "")).strip()
        action = str(payload.get("action", "")).strip()

        if action == "deposit":
            self.wallet_service.deposit(user, asset, amount)
            verb = "充值"
        elif action == "withdraw":
            self.wallet_service.withdraw(user, asset, amount)
            verb = "提现"
        else:
            raise ValidationError("未知钱包操作。")

        return {"message": f"{user} {verb} {amount} {asset.value} 成功。"}

    def place_order(self, payload: dict[str, Any], *, user: str) -> dict[str, Any]:
        pair = PAIRS[str(payload.get("pair", ""))]
        side = OrderSide(str(payload.get("side", "")))
        order_type = OrderType(str(payload.get("type", "LIMIT")).upper() or "LIMIT")
        quantity = str(payload.get("quantity", "")).strip()

        if order_type == OrderType.MARKET:
            result = self.engine.place_market_order(
                user_id=user,
                pair=pair,
                side=side,
                quantity=quantity,
            )
        else:
            result = self.engine.place_limit_order(
                user_id=user,
                pair=pair,
                side=side,
                price=str(payload.get("price", "")).strip(),
                quantity=quantity,
            )
        self._record_order_flow(result)
        blocked = "，自成交保护已触发" if result.self_trade_blocked else ""
        type_label = "市价单" if order_type == OrderType.MARKET else "限价单"
        return {
            "message": (
                f"{type_label} {result.order.order_id} 提交成功，状态 {result.order.status.value}，"
                f"本次成交 {len(result.trades)} 笔{blocked}。"
            )
        }

    def cancel_order(self, payload: dict[str, Any], *, user: str) -> dict[str, Any]:
        order_id = str(payload.get("order_id", "")).strip()
        if not order_id:
            raise ValidationError("订单号不能为空。")
        order = self.engine.cancel_order(user_id=user, order_id=order_id)
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

    def snapshot(self, current_user: str | None = None) -> dict[str, Any]:
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
                    "type": order.order_type.value,
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
            "current_user": current_user,
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
            "order_types": [order_type.value for order_type in OrderType],
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
            "type": order.order_type.value,
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
        type_text = "市价" if order.order_type is OrderType.MARKET else "限价"
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
                f"{order.user_id} 提交 {order.pair.symbol} {type_text}{side_text}",
                description,
                result,
            )
        )

STATE = DEXWebState()


class DEXRequestHandler(BaseHTTPRequestHandler):
    """HTTP handler for the browser GUI."""

    server_version = "DEXGui/1.0"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._send_static("index.html")
        elif path.startswith("/static/"):
            self._send_static(path[len("/static/"):])
        elif path == "/api/state":
            current_user = self._try_resolve_user()
            self._send_json({"ok": True, "data": STATE.snapshot(current_user=current_user)})
        else:
            self._send_json({"ok": False, "error": "接口不存在。"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            payload = self._read_json()
            if path == "/api/register":
                result = STATE.register(payload)
                snapshot_user = self._try_resolve_user()
            elif path == "/api/login":
                result = STATE.login(payload)
                snapshot_user = result["current_user"]
            elif path == "/api/logout":
                user_token = self._authenticate_or_fail()
                if user_token is None:
                    return
                _, token = user_token
                result = STATE.logout(token=token)
                snapshot_user = None
            elif path == "/api/wallet":
                user_token = self._authenticate_or_fail()
                if user_token is None:
                    return
                user, _ = user_token
                result = STATE.wallet_action(payload, user=user)
                snapshot_user = user
            elif path == "/api/order":
                user_token = self._authenticate_or_fail()
                if user_token is None:
                    return
                user, _ = user_token
                result = STATE.place_order(payload, user=user)
                snapshot_user = user
            elif path == "/api/cancel":
                user_token = self._authenticate_or_fail()
                if user_token is None:
                    return
                user, _ = user_token
                result = STATE.cancel_order(payload, user=user)
                snapshot_user = user
            elif path == "/api/seal":
                result = STATE.seal_block()
                snapshot_user = self._try_resolve_user()
            elif path == "/api/validate":
                result = STATE.validate_chain()
                snapshot_user = self._try_resolve_user()
            elif path == "/api/demo-flow":
                result = STATE.run_demo_flow()
                snapshot_user = self._try_resolve_user()
            elif path == "/api/reset":
                result = self._reset_state()
                snapshot_user = None
            else:
                self._send_json({"ok": False, "error": "接口不存在。"}, HTTPStatus.NOT_FOUND)
                return
        except DEXError as exc:
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        except (KeyError, ValueError) as exc:
            self._send_json({"ok": False, "error": f"非法请求参数: {exc}"}, HTTPStatus.BAD_REQUEST)
            return

        self._send_json({
            "ok": True,
            **result,
            "data": STATE.snapshot(current_user=snapshot_user),
        })

    def _authenticate_or_fail(self) -> tuple[str, str] | None:
        """Resolve bearer token to user, or send 401 and return None."""
        token = self._extract_bearer_token()
        if token is None:
            self._send_json(
                {"ok": False, "error": "缺少 Authorization 头。"},
                HTTPStatus.UNAUTHORIZED,
            )
            return None
        try:
            user = STATE.auth_service.get_user_by_token(token)
        except DEXError:
            self._send_json(
                {"ok": False, "error": "会话令牌无效或已过期。"},
                HTTPStatus.UNAUTHORIZED,
            )
            return None
        return user.username, token

    def _try_resolve_user(self) -> str | None:
        """Return the bearer-token user if present and valid, else None."""
        token = self._extract_bearer_token()
        if token is None:
            return None
        try:
            return STATE.auth_service.get_user_by_token(token).username
        except DEXError:
            return None

    def _extract_bearer_token(self) -> str | None:
        header = self.headers.get("Authorization", "")
        prefix = "Bearer "
        if not header.startswith(prefix):
            return None
        token = header[len(prefix):].strip()
        return token or None

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

    def _send_static(self, rel_path: str) -> None:
        safe = os.path.normpath(rel_path).lstrip(os.sep)
        abs_path = os.path.realpath(os.path.join(STATIC_DIR, safe))
        if os.path.commonpath([abs_path, STATIC_DIR]) != STATIC_DIR:
            self._send_json({"ok": False, "error": "非法静态路径。"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            with open(abs_path, "rb") as fh:
                payload = fh.read()
        except FileNotFoundError:
            self._send_json({"ok": False, "error": "文件不存在。"}, HTTPStatus.NOT_FOUND)
            return
        ext = os.path.splitext(abs_path)[1].lower()
        content_type = STATIC_CONTENT_TYPES.get(ext, "application/octet-stream")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
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


def main() -> None:
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, OSError):
        pass
    reload_enabled = "--no-reload" not in sys.argv
    server = _build_server()
    reload_event = threading.Event()
    if reload_enabled:
        watcher = threading.Thread(
            target=_watch_sources, args=(server, reload_event), daemon=True
        )
        watcher.start()
        print(f"DEX GUI running at http://{HOST}:{PORT}  (auto-reload on .py change)")
    else:
        print(f"DEX GUI running at http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

    if reload_event.is_set():
        print("代码已变更，正在重启服务器...")
        os.execv(sys.executable, [sys.executable, *sys.argv])


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


def _source_signature() -> dict[str, float]:
    """Snapshot mtime of every .py under the project directory."""
    project_dir = os.path.dirname(os.path.abspath(__file__))
    sigs: dict[str, float] = {}
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
        for fname in files:
            if fname.endswith(".py"):
                path = os.path.join(root, fname)
                try:
                    sigs[path] = os.path.getmtime(path)
                except OSError:
                    pass
    return sigs


def _watch_sources(server: ThreadingHTTPServer, reload_event: threading.Event) -> None:
    """轮询源文件 mtime，发现改动则触发服务器关闭并设置 reload 标志。"""
    initial = _source_signature()
    while not reload_event.is_set():
        time.sleep(0.8)
        current = _source_signature()
        changed = [
            path
            for path in set(initial) | set(current)
            if initial.get(path) != current.get(path)
        ]
        if changed:
            rels = [os.path.basename(path) for path in changed[:3]]
            extra = "" if len(changed) <= 3 else f" 等 {len(changed)} 个文件"
            print(f"检测到代码变更：{', '.join(rels)}{extra}")
            reload_event.set()
            server.shutdown()
            return


if __name__ == "__main__":
    main()
