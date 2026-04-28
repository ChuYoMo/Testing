# 简单去中心化加密货币交易所（DEX）核心系统与可视化 GUI

一个用于《软件测试》课程实验的简化去中心化交易所原型。项目使用 Python 标准库实现用户认证、多币种钱包、限价单与市价单撮合、订单撤销、成交结算、链式账本记录、SQLite 持久化、浏览器 GUI 和自动化测试，适合用于课程演示、测试设计和软件文档编写。

本项目是教学演示系统，不连接真实区块链网络，不管理真实私钥，不处理真实资金。

## 目录

- [功能概览](#功能概览)
- [项目结构](#项目结构)
- [运行环境](#运行环境)
- [快速开始](#快速开始)
- [命令行演示](#命令行演示)
- [浏览器 GUI](#浏览器-gui)
- [JSON API](#json-api)
- [自动化测试](#自动化测试)
- [核心设计](#核心设计)
- [课程文档](#课程文档)
- [实现边界](#实现边界)
- [后续扩展](#后续扩展)

## 功能概览

| 模块 | 已实现能力 |
| --- | --- |
| 用户认证 | 注册、登录、登出、token 校验、PBKDF2-HMAC-SHA256 密码哈希 |
| 钱包账户 | 支持 `BTC`、`ETH`、`USDT`；充值、提现、冻结、解冻、成交扣减冻结余额 |
| 订单撮合 | 限价单、市价单、订单簿、价格优先、时间优先、部分成交、完全成交、自成交保护、订单撤销 |
| 市价单 | 预走对手簿精确冻结、流动性不足直接拒绝、自动跳过自身挂单 |
| 成交结算 | 买方获得基础资产，卖方获得计价资产；买单限价高于成交价时返还差额 |
| 链式账本 | 创世区块、成交记录待打包、达到容量自动封块、手动封块、链完整性校验 |
| 持久化 | SQLite 单文件存储用户、钱包、订单、成交、区块、待打包交易；幂等 schema 迁移 |
| 命令行演示 | `app.py::run_demo()` 运行固定交易流程并返回结构化结果 |
| 浏览器 GUI | 基于 `http.server` 的单页界面和 JSON API，可完成注册、登录、钱包、限价/市价下单、撤单、封块、校验、重置和一键交易流程；订单簿带深度条；改动 `.py` 自动重启 |
| 自动化测试 | 使用 `unittest` 覆盖核心交易流程、市价单、GUI 流程、区块链快照隔离和金额合法性校验 |

## 项目结构

```text
dexproj/
├── __init__.py
├── app.py                         # 命令行演示入口与服务构建
├── auth.py                        # 用户认证与密码哈希
├── blockchain.py                  # 简化链式账本
├── database.py                    # SQLite 连接、schema 初始化与迁移
├── engine.py                      # 订单簿与撮合引擎（限价/市价/撤单）
├── exceptions.py                  # 统一异常体系
├── gui.py                         # 浏览器 GUI、JSON API 与自动重启
├── models.py                      # 枚举、数据类和金额工具
├── wallet.py                      # 钱包账户服务
├── tests/
│   ├── __init__.py
│   └── test_trading_flow.py       # 自动化测试用例
├── README.md
├── 测试用例表.md
├── 软件设计说明书.md
└── generate_document_package.py   # 课程文档合集生成脚本
```

目录中还包含若干 IEEE 模板 PDF、缓存文件和系统附加文件，它们不影响核心程序运行。

## 运行环境

- Python：3.8 或更高版本。
- 第三方依赖：无，仅使用 Python 标准库。
- 推荐执行位置：项目根目录。
- 适用系统：Windows、Linux、macOS。

确认 Python 版本：

```bash
python3 --version
```

如果系统中 `python` 指向 Python 3，也可以将下文命令中的 `python3` 替换为 `python`。

## 快速开始

进入项目目录：

```bash
cd /path/to/dexproj
```

运行命令行演示：

```bash
python3 app.py
```

运行浏览器 GUI：

```bash
python3 gui.py
```

执行自动化测试：

```bash
python3 -m unittest discover -v
```

## 命令行演示

执行：

```bash
python3 app.py
```

`app.py` 会运行一组固定交易流程：

1. 注册 `alice`、`bob`、`carol`。
2. Alice 充值 `50000 USDT`。
3. Bob 充值 `1 BTC`。
4. Carol 充值 `5 ETH`。
5. Bob 挂出 `BTC/USDT` 卖单，价格 `30000`，数量 `1 BTC`。
6. Alice 提交 `BTC/USDT` 买单，价格 `31000`，数量 `0.4 BTC`，与 Bob 成交。
7. Alice 挂出 `ETH/USDT` 买单，价格 `2100`，数量 `2 ETH`。
8. Carol 提交 `ETH/USDT` 卖单，价格 `2000`，数量 `5 ETH`，与 Alice 成交。
9. 两笔成交写入链式账本，区块链完整性校验通过。

关键结果：

| 项目 | 结果 |
| --- | --- |
| BTC 成交 | `T000001`，Alice 从 Bob 买入 `0.40000000 BTC`，成交价 `30000.00000000`，成交额 `12000.00000000 USDT` |
| ETH 成交 | `T000002`，Alice 从 Carol 买入 `2.00000000 ETH`，成交价 `2100.00000000`，成交额 `4200.00000000 USDT` |
| Alice 最终可用余额 | `0.40000000 BTC`、`2.00000000 ETH`、`33800.00000000 USDT` |
| Bob 剩余冻结 | `0.60000000 BTC` |
| Carol 剩余冻结 | `3.00000000 ETH` |

## 浏览器 GUI

启动：

```bash
python3 gui.py
```

默认访问地址：

```text
http://127.0.0.1:8000
```

如果 `8000` 端口被占用，程序会在 `8000` 到 `8019` 范围内自动选择下一个可用端口，终端会打印实际地址。

GUI 启动后会自动创建示例账户：

| 用户 | 初始资产 |
| --- | --- |
| `alice` | `50000 USDT` |
| `bob` | `1 BTC`、`2 ETH` |
| `carol` | `5 ETH`、`10000 USDT` |

GUI 支持的操作：

- 注册和登录用户。
- 对指定用户执行充值、提现。
- 提交 `BTC/USDT`、`ETH/USDT`、`ETH/BTC` 订单，支持限价单与市价单切换。
- 撤销自己未完全成交的挂单。
- 查看订单簿（带买卖深度条可视化）、用户、钱包、订单、交易流程、待打包交易和区块链。
- 一键执行 Bob/Alice/Carol 演示交易流程。
- 手动封装待打包交易。
- 校验区块链完整性。
- 重置演示状态。

### 自动重启

`python3 gui.py` 会启动一个后台 watcher 线程，轮询项目内所有 `.py` 文件的 mtime，发现变更时打印日志并通过 `os.execv` 在原进程内重启服务，浏览器刷新即可看到新代码。如需关闭该行为，启动时附加 `--no-reload`：

```bash
python3 gui.py --no-reload
```

### 数据持久化

GUI 默认使用项目根目录下的 `dex.db`（SQLite）存储所有状态。删除该文件可获得全新空库；点击 GUI 中"重置"按钮等价于清空所有表后重新种入示例账户。

## JSON API

`gui.py` 在本地提供以下接口：

| 方法 | 路径 | 功能 |
| --- | --- | --- |
| `GET` | `/` | 返回单页 HTML |
| `GET` | `/api/state` | 获取系统快照 |
| `POST` | `/api/register` | 注册用户 |
| `POST` | `/api/login` | 登录用户 |
| `POST` | `/api/wallet` | 充值或提现 |
| `POST` | `/api/order` | 提交订单（限价或市价） |
| `POST` | `/api/cancel` | 撤销自己的未完全成交订单 |
| `POST` | `/api/seal` | 手动封块 |
| `POST` | `/api/validate` | 校验区块链 |
| `POST` | `/api/demo-flow` | 重置并执行固定交易流程 |
| `POST` | `/api/reset` | 重置演示状态 |

成功响应统一包含 `ok: true`，失败响应包含 `ok: false` 和 `error`。业务异常会转换为 HTTP 400，未知接口返回 HTTP 404。

示例：注册用户。

```bash
curl -X POST http://127.0.0.1:8000/api/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"dave","password":"dave123"}'
```

示例：充值。

```bash
curl -X POST http://127.0.0.1:8000/api/wallet \
  -H 'Content-Type: application/json' \
  -d '{"username":"dave","asset":"USDT","amount":"10000","action":"deposit"}'
```

示例：提交限价买单。

```bash
curl -X POST http://127.0.0.1:8000/api/order \
  -H 'Content-Type: application/json' \
  -d '{"username":"dave","pair":"BTC/USDT","side":"BUY","price":"30000","quantity":"0.1","type":"LIMIT"}'
```

示例：提交市价买单（不需要 `price` 字段）。

```bash
curl -X POST http://127.0.0.1:8000/api/order \
  -H 'Content-Type: application/json' \
  -d '{"username":"dave","pair":"BTC/USDT","side":"BUY","quantity":"0.1","type":"MARKET"}'
```

示例：撤销订单。

```bash
curl -X POST http://127.0.0.1:8000/api/cancel \
  -H 'Content-Type: application/json' \
  -d '{"username":"dave","order_id":"O000005"}'
```

示例：获取系统快照。

```bash
curl http://127.0.0.1:8000/api/state
```

## 自动化测试

执行全部测试：

```bash
python3 -m unittest discover -v
```

当前测试用例：

| 测试函数 | 覆盖内容 |
| --- | --- |
| `test_required_btc_and_eth_trading_flow` | 核心交易流程、订单状态、钱包余额、订单簿、成交记录和链校验 |
| `test_gui_one_click_demo_flow` | GUI 一键交易流程对应的后端状态 |
| `test_gui_manual_order_flow_records_trade_details` | GUI 手工下单时的交易流程记录和成交明细 |
| `test_blockchain_snapshots_do_not_expose_internal_state` | 区块链待打包交易、封块结果、链快照和导出结果不暴露内部可变状态 |
| `test_decimal_normalization_rejects_non_finite_values` | 金额标准化拒绝 `NaN`、`Infinity`、`-Infinity` |
| `test_market_buy_walks_book_across_levels` | 市价买单跨多档对手簿成交、计价资产精确扣减 |
| `test_market_sell_consumes_buy_side_liquidity` | 市价卖单吃买盘流动性、基础资产扣减与计价资产入账 |
| `test_market_order_rejects_when_liquidity_insufficient` | 流动性不足时市价单直接拒绝、不冻结资金 |
| `test_market_order_skips_self_orders` | 市价单跳过自身挂单、与他人订单成交 |

期望结果：

```text
Ran 9 tests
OK
```

## 核心设计

### 模块依赖

```text
app.py / gui.py
 ├── database.init_db        # SQLite 连接与 schema
 ├── AuthService
 ├── WalletService
 ├── SimpleBlockchain
 └── MatchingEngine
       ├── AuthService       校验用户
       ├── WalletService     冻结资金与成交结算
       ├── SimpleBlockchain  记录成交
       └── OrderBook         管理买卖盘
```

### 金额处理

所有价格、数量和余额使用 `Decimal`。`models.normalize_decimal()` 会将输入转换为 `Decimal`，拒绝非有限数值，并统一量化到 8 位小数，避免使用 `float` 带来的金额精度问题。

### 撮合规则

- 支持限价单与市价单。
- 买单按照价格从高到低排序，同价按提交顺序排序。
- 卖单按照价格从低到高排序，同价按提交顺序排序。
- 成交价使用 maker 订单价格。
- 买方限价高于成交价时，差额会从冻结余额中解冻返还。
- 限价单遇到自身挂单时触发自成交保护，本轮撮合停止；市价单遇到自身挂单时直接跳过该 maker 继续撮合。
- 市价单提交前先预走对手簿计算精确所需冻结额（买单冻结 USDT，卖单冻结基础资产），流动性不足时抛出 `EmptyOrderBookError` 且不冻结任何资金。

### 订单撤销

- `MatchingEngine.cancel_order(user_id, order_id)` 仅允许订单所有者撤单。
- 已完全成交或已撤销的订单会抛出 `OrderNotCancellableError`。
- 撤单时按照订单方向解冻剩余资金（买单解冻剩余计价资产、卖单解冻剩余基础资产），并将订单状态置为 `CANCELLED`。

### 钱包冻结与结算

- 限价买单提交时冻结 `价格 * 数量` 的计价资产；市价买单按预走对手簿后的精确总额冻结。
- 卖单提交时冻结基础资产数量。
- 成交时扣减卖方冻结基础资产，并给买方增加基础资产。
- 成交时扣减买方冻结计价资产，并给卖方增加计价资产。
- 未成交的剩余订单继续保留在订单簿中，对应资金保持冻结，直至成交或被撤销。

### 链式账本

`SimpleBlockchain` 用于教学演示链式不可篡改思想：

- 初始化时创建创世区块。
- 每笔成交通过 `Trade.to_record()` 转为交易记录。
- 交易先进入待打包区。
- 待打包交易数达到 `block_capacity` 时自动封块。
- 每个新区块保存前一区块哈希。
- `validate_chain()` 会校验区块哈希、创世区块和前后链接。
- 链、待打包交易和导出结果均通过深拷贝返回，避免外部代码直接篡改内部状态。

### 持久化层

`database.py` 提供 SQLite 连接初始化、schema 创建和幂等增量迁移：

- 启动时调用 `init_db(db_path)` 打开（或新建）数据库，开启 `WAL` 与 `FOREIGN KEYS`。
- 创建 `users`、`sessions`、`wallets`、`orders`、`trades`、`blocks`、`pending_transactions` 七张表。
- `_migrate_schema()` 通过 `PRAGMA table_info` 检查列是否存在，对老库做向后兼容的 `ALTER TABLE`（例如新增 `order_type` 列）。
- `clear_db(conn)` 清空全部数据但保留 schema，供 GUI 的"重置"按钮使用。

### 异常体系

项目通过 `exceptions.py` 统一定义业务异常，主要包括：

- `ValidationError`：通用参数校验错误。
- `AuthError` 及其子类：用户认证错误。
- `WalletError` 及其子类：钱包、余额、冻结余额错误。
- `TradingPairError`：交易对错误。
- `OrderError` 及其子类：非法订单、自成交保护、订单不存在、订单不可撤销、流动性不足。
- `BlockchainError` 及其子类：空区块、非法区块、链校验错误。

GUI 层会将这些业务异常转换为 JSON 错误响应。

## 课程文档

项目根目录包含两份主要课程文档：

| 文档 | 说明 |
| --- | --- |
| `软件设计说明书.md` | 按 IEEE 1016 思想整理系统设计、模块、接口、数据结构、流程和实现边界 |
| `测试用例表.md` | 整理核心交易流程、GUI 流程、模块级补充测试点和当前自动化测试对应关系 |

可使用以下脚本生成课程项目文档合集：

```bash
python3 generate_document_package.py
```

脚本会在项目根目录生成 `软件测试课程项目文档合集/` 和 `软件测试课程项目文档合集.zip`。

## 实现边界

- 状态保存在 SQLite 文件（默认 `dex.db`）中；删除该文件即清空所有数据。
- 没有真实区块链网络、共识、P2P 通信和链上签名。
- 没有真实钱包地址和私钥管理。
- 没有手续费模型。
- 没有并发锁或事务机制（SQLite 提供基本的写锁，未做多进程协调）。
- GUI 中钱包和下单操作通过用户名指定用户，没有完整权限隔离模型。
- JSON API 中登录会生成 token，但当前 GUI 操作接口未强制要求 token。

## 后续扩展

建议优先补充以下内容：

1. 认证模块独立单元测试：重复注册、错误密码、无效 token、登出。
2. 钱包模块独立单元测试：余额不足、冻结不足、非法金额、不支持币种。
3. 撮合模块独立单元测试：价格优先、时间优先、自成交保护、不支持交易对、撤单边界。
4. 区块链模块独立单元测试：空封块、自动封块、篡改交易、篡改哈希。
5. 功能扩展：手续费、历史订单查询、止损/止盈单、深度图。
6. API 扩展：基于 token 的权限校验、用户只能操作自己的钱包和订单。
