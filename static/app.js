let state = null;
let activeRequests = 0;
let currentOrderType = "LIMIT";
const TOKEN_KEY = "dex_token";
let authToken = localStorage.getItem(TOKEN_KEY) || null;

function setOrderType(type) {
  currentOrderType = type;
  typeLimitBtn.classList.toggle("active", type === "LIMIT");
  typeMarketBtn.classList.toggle("active", type === "MARKET");
  orderPriceField.classList.toggle("hidden", type === "MARKET");
}

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
    const options = { method: payload === null ? "GET" : "POST", headers: {} };
    if (payload !== null) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(payload);
    }
    if (authToken) {
      options.headers["Authorization"] = `Bearer ${authToken}`;
    }
    const response = await fetch(path, options);
    const result = await response.json();
    if (response.status === 401) {
      clearAuth();
      throw new Error(result.error || "登录已失效，请重新登录。");
    }
    if (!result.ok) {
      throw new Error(result.error || "请求失败");
    }
    return result;
  } finally {
    setBusy(false);
  }
}

function setAuth(token) {
  authToken = token;
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}

function clearAuth() {
  setAuth(null);
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
    if (path === "/api/login" && result.token) {
      setAuth(result.token);
    }
    if (path === "/api/logout") {
      clearAuth();
    }
    render();
    setStatus(result.message || fallbackMessage);
  } catch (error) {
    render();
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

function logoutUser() {
  if (!authToken) {
    setStatus("尚未登录。", true);
    return;
  }
  postAction("/api/logout", {}, "已退出登录。");
}

function walletAction(action) {
  if (!authToken) {
    setStatus("请先登录后再进行钱包操作。", true);
    return;
  }
  postAction("/api/wallet", {
    action,
    asset: walletAsset.value,
    amount: walletAmount.value
  }, "钱包操作成功。");
}

function placeOrder() {
  if (!authToken) {
    setStatus("请先登录后再下单。", true);
    return;
  }
  const payload = {
    pair: orderPair.value,
    side: orderSide.value,
    type: currentOrderType,
    quantity: orderQuantity.value
  };
  if (currentOrderType === "LIMIT") {
    payload.price = orderPrice.value;
  }
  postAction("/api/order", payload, "订单提交成功。");
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
  walletAsset.innerHTML = optionList(state.assets);
  orderPair.innerHTML = optionList(state.pairs);
  orderSide.innerHTML = optionList(state.sides);
  keepValue(walletAsset, "USDT");
  keepValue(orderPair, "BTC/USDT");
  keepValue(orderSide, "BUY");

  const me = state.current_user;
  authLoggedIn.classList.toggle("hidden", !me);
  authLoggedOut.classList.toggle("hidden", !!me);
  authLoggedInUser.textContent = me || "-";
  walletOpUser.textContent = me || "未登录";
  orderOpUser.textContent = me || "未登录";

  metricUser.textContent = me || "未登录";
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
    ["订单ID", "用户", "交易对", "类型", "方向", "价格", "数量", "已成交", "剩余", "状态", "操作"],
    state.orders.map(row => [
      row.id,
      row.user,
      row.pair,
      orderTypeCell(row.type),
      sideCell(row.side),
      row.type === "MARKET" ? "市价" : formatDecimal(row.price),
      formatDecimal(row.quantity),
      formatDecimal(row.filled),
      formatDecimal(row.remaining),
      statusCell(row.status),
      (row.status === "OPEN" || row.status === "PARTIALLY_FILLED") && row.user === state.current_user
        ? raw(`<button class="cancel-btn" onclick="cancelOrder('${escapeHTML(row.id)}')">撤单</button>`)
        : ""
    ])
  );
}

function orderTypeCell(type) {
  const klass = type === "MARKET" ? "type-market" : "type-limit";
  const label = type === "MARKET" ? "MARKET" : "LIMIT";
  return raw(`<span class="badge ${klass}">${escapeHTML(label)}</span>`);
}

function cancelOrder(orderId) {
  if (!authToken) {
    setStatus("请先登录后再撤单。", true);
    return;
  }
  postAction("/api/cancel", { order_id: orderId }, "撤单成功。");
}

function renderBooks() {
  const rows = [];
  for (const [pair, book] of Object.entries(state.order_books)) {
    const maxSell = sideMax(book.sell);
    const maxBuy = sideMax(book.buy);
    for (const order of book.sell) {
      rows.push([
        pair,
        sideCell("SELL"),
        order.order_id,
        order.user_id,
        formatDecimal(order.price),
        depthCell(order.remaining_quantity, maxSell, "sell"),
        statusCell(order.status)
      ]);
    }
    for (const order of book.buy) {
      rows.push([
        pair,
        sideCell("BUY"),
        order.order_id,
        order.user_id,
        formatDecimal(order.price),
        depthCell(order.remaining_quantity, maxBuy, "buy"),
        statusCell(order.status)
      ]);
    }
  }
  books.innerHTML = table(["交易对", "方向", "订单ID", "用户", "价格", "剩余数量", "状态"], rows);
}

function sideMax(orders) {
  let max = 0;
  for (const o of orders) {
    const v = Number(o.remaining_quantity);
    if (Number.isFinite(v) && v > max) max = v;
  }
  return max;
}

function depthCell(value, max, side) {
  const num = Number(value);
  const pct = max > 0 && Number.isFinite(num) ? Math.max(6, (num / max) * 100) : 0;
  return raw(
    `<span class="depth-cell ${side}">` +
      `<span class="depth-bar" style="width:${pct.toFixed(2)}%"></span>` +
      `<span class="depth-text">${escapeHTML(formatDecimal(value))}</span>` +
    `</span>`
  );
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
