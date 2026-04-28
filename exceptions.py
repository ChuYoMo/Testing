
"""自定义异常体系，统一承载 DEX 核心系统的错误语义。"""


class DEXError(Exception):
    """DEX 系统基础异常。"""


class ValidationError(DEXError):
    """通用参数校验异常。"""


class AuthError(DEXError):
    """认证相关异常。"""


class UserAlreadyExistsError(AuthError):
    """重复注册用户异常。"""


class UserNotFoundError(AuthError):
    """用户不存在异常。"""


class InvalidCredentialsError(AuthError):
    """用户名或密码错误异常。"""


class WalletError(DEXError):
    """钱包/账户相关异常。"""


class UnsupportedAssetError(WalletError):
    """不支持的币种异常。"""


class InsufficientBalanceError(WalletError):
    """可用余额不足异常。"""


class InsufficientFrozenBalanceError(WalletError):
    """冻结余额不足异常。"""


class TradingPairError(DEXError):
    """交易对相关异常。"""


class UnsupportedTradingPairError(TradingPairError):
    """不支持的交易对异常。"""


class OrderError(DEXError):
    """订单/撮合相关异常。"""


class InvalidOrderError(OrderError):
    """非法订单参数异常。"""


class SelfTradePreventedError(OrderError):
    """自成交保护触发异常。"""


class OrderNotFoundError(OrderError):
    """订单不存在异常。"""


class OrderNotCancellableError(OrderError):
    """订单状态不允许撤单（已成交或已撤销）异常。"""


class BlockchainError(DEXError):
    """区块链/链式账本相关异常。"""


class EmptyBlockError(BlockchainError):
    """空区块异常。"""


class InvalidBlockError(BlockchainError):
    """非法区块异常。"""


class ChainValidationError(BlockchainError):
    """链完整性校验失败异常。"""
