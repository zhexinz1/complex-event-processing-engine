"""
price_service.py — 行情价格服务

从 Redis Pub/Sub 订阅 Market Node 推送的实时行情，维护进程内 Tick 缓存，
为净入金计算、调仓引擎等业务模块提供统一的最新价格查询接口。
"""

import logging
import pickle
import threading
from decimal import Decimal

import redis
from cep.core.events import TickEvent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 全局行情缓存（由 Redis 订阅线程持续填充）
# ---------------------------------------------------------------------------

_tick_cache: dict[str, TickEvent] = {}  # symbol -> 最新 TickEvent
_cum_volume_cache: dict[str, int] = {}  # symbol -> 累计成交量（用于显示）
_tick_cache_lock = threading.Lock()
_subscriber_thread: threading.Thread | None = None


def _on_tick(event: TickEvent) -> None:
    """更新 Tick 缓存（统一存储为原始大小写）"""
    with _tick_cache_lock:
        _tick_cache[event.symbol] = event

        # CTP 和迅投现在都统一推送当日累计成交量，直接覆盖即可
        _cum_volume_cache[event.symbol] = event.volume


def _redis_subscriber_loop(redis_url: str, channel: str):
    """
    Redis Pub/Sub 订阅线程。
    持续接收 Market Node 通过 RedisEventBridge 发布的 TickEvent。
    """
    client = redis.from_url(redis_url)
    pubsub = client.pubsub()
    pubsub.subscribe(channel)
    logger.info(f"[PriceService] Redis 行情订阅已连接: channel={channel}")

    tick_count = 0
    try:
        for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    event = pickle.loads(message["data"])
                    if isinstance(event, TickEvent):
                        _on_tick(event)
                        tick_count += 1
                        if tick_count % 10 == 0:
                            logger.info(
                                f"[PriceService] 已接收 {tick_count} 条 Tick，"
                                f"最新: {event.symbol} @ {event.last_price}"
                            )
                except Exception as e:
                    logger.error(f"[PriceService] 反序列化 Redis 消息失败: {e}")
    except Exception as e:
        logger.error(f"[PriceService] Redis 订阅线程异常退出: {e}")
    finally:
        pubsub.close()
        client.close()


def init_redis_market_subscriber(
    redis_url: str = "redis://localhost:6379/0",
    channel: str = "cep_events",
) -> None:
    """
    启动 Redis 行情订阅守护线程（在 Flask/Web Node 启动时调用）。
    复用 Market Node 已在发布的 cep_events 频道，无需额外配置。
    """
    global _subscriber_thread

    _subscriber_thread = threading.Thread(
        target=_redis_subscriber_loop,
        args=(redis_url, channel),
        daemon=True,
        name="redis-tick-subscriber",
    )
    _subscriber_thread.start()
    logger.info("[PriceService] Redis 行情订阅线程已启动")


def get_latest_price(asset_code: str) -> Decimal:
    """
    从 Tick 缓存获取最新卖1价（优先），无卖1价则用最新价。

    asset_code 可以带交易所后缀（如 "au2609.SHFE"），会自动去掉后缀查找。
    如果缓存里没有数据，抛出 ValueError 拒绝计算，避免用虚假价格生成真实订单。
    """
    # 对于期货，去掉后缀查找；对于股票（.SH/.SZ），保留后缀
    symbol = asset_code
    if not (asset_code.endswith(".SH") or asset_code.endswith(".SZ")):
        symbol = asset_code.split(".")[0]

    with _tick_cache_lock:
        # 尝试精确匹配、小写、大写，以兼容 DB 与 Market Node 大小写不一致的情况
        tick = (
            _tick_cache.get(symbol)
            or _tick_cache.get(symbol.lower())
            or _tick_cache.get(symbol.upper())
        )

    if tick is not None:
        price = tick.ask_prices[0] if tick.ask_prices[0] > 0 else tick.last_price
        logger.debug("使用实时价格: %s = %.2f", asset_code, price)
        return Decimal(str(price))

    raise ValueError(
        f"合约 {asset_code} 暂无实时行情，请确保 Market Node 已启动并正在推送该合约。"
        f"当前缓存中仅有: {list(_tick_cache.keys())}"
    )


def get_cached_symbols() -> list[str]:
    """返回当前缓存中所有已有行情的合约代码（调试用）"""
    with _tick_cache_lock:
        return list(_tick_cache.keys())


def get_tick_cache_detail() -> dict:
    """
    返回 Tick 缓存的详细信息（用于行情健康检查页面）。

    返回格式:
    {
        "subscriber_alive": True/False,
        "symbols": {
            "au2606": {
                "last_price": 1504.1,
                "ask1": 1504.2,
                "bid1": 1504.0,
                "volume": 12345,
                "update_time": "14:25:03",
                "trading_day": "20260422"
            }
        }
    }
    """

    with _tick_cache_lock:
        symbols = {}
        for sym, tick in _tick_cache.items():
            # 从 TickEvent 的 timestamp 提取 update_time 和 trading_day
            update_time = ""
            trading_day = ""
            if tick.timestamp:
                update_time = tick.timestamp.strftime("%H:%M:%S")
                trading_day = tick.timestamp.strftime("%Y%m%d")

            symbols[sym] = {
                "last_price": tick.last_price,
                "ask1": tick.ask_prices[0] if tick.ask_prices else 0,
                "bid1": tick.bid_prices[0] if tick.bid_prices else 0,
                "ask1_vol": tick.ask_volumes[0] if tick.ask_volumes else 0,
                "bid1_vol": tick.bid_volumes[0] if tick.bid_volumes else 0,
                "volume": _cum_volume_cache.get(sym, 0),
                "update_time": update_time,
                "trading_day": trading_day,
            }

    return {
        "subscriber_alive": _subscriber_thread is not None
        and _subscriber_thread.is_alive(),
        "cached_count": len(symbols),
        "symbols": symbols,
    }
