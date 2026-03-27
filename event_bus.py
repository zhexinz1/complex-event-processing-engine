"""
event_bus.py — 全局事件总线（发布/订阅模式）

EventBus 是系统的神经中枢，所有模块通过它解耦通信。
设计原则：
  1. 同步优先：当前实现为同步调用，保证事件处理的确定性顺序。
  2. 异步预留：接口设计兼容 asyncio，未来可无缝升级为异步总线。
  3. 类型安全：订阅时指定事件类型，发布时自动路由到对应 Handler。
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Callable, Type, TypeVar

from events import BaseEvent

# ---------------------------------------------------------------------------
# 类型别名
# ---------------------------------------------------------------------------

EventT = TypeVar("EventT", bound=BaseEvent)
EventHandler = Callable[[EventT], None]  # 同步 Handler 签名
# AsyncEventHandler = Callable[[EventT], Awaitable[None]]  # 异步预留


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# EventBus 核心实现
# ---------------------------------------------------------------------------

class EventBus:
    """
    全局事件总线，基于发布/订阅模式实现模块间解耦通信。

    核心方法：
      - subscribe(event_type, handler):  订阅某类事件。
      - unsubscribe(event_type, handler): 取消订阅。
      - publish(event):                  发布事件，同步调用所有订阅者。

    线程安全性：
      当前实现为单线程同步模型，若需多线程需加锁保护 _subscribers。
    """

    def __init__(self) -> None:
        """
        初始化事件总线。

        _subscribers: 二维字典结构为 {EventType: {symbol: set[ref]}}
                      使用 Multi-level dict 避免 O(N) 的全量遍历漏洞。
                      弱引用集合避免忘记取消订阅导致的内存泄漏。
        """
        from collections import defaultdict
        self._subscribers: dict[Type[BaseEvent], dict[str, set[Any]]] = defaultdict(lambda: defaultdict(set))
        logger.info("EventBus initialized with Topic(Symbol) routing and WeakRefs.")

    # -----------------------------------------------------------------------
    # 订阅管理
    # -----------------------------------------------------------------------

    def subscribe(
        self,
        event_type: Type[EventT],
        handler: EventHandler[EventT],
        symbol: str = "",
    ) -> None:
        """
        订阅指定类型的事件进行精准路由。

        Args:
            event_type: 事件类（如 TickEvent, BarEvent）。
            handler:    回调函数，签名为 (event: EventT) -> None。
            symbol:     标的代码（空字符串表示全局订阅）。
        """
        import weakref
        
        # 将方法封装为 WeakMethod，将普通函数封装为 ref
        if hasattr(handler, '__self__'):
            ref = weakref.WeakMethod(handler)
        else:
            ref = weakref.ref(handler)
            
        subs = self._subscribers[event_type][symbol]
        # 防止重复订阅
        if not any(r() == handler for r in subs if r() is not None):
            subs.add(ref)
            handler_name = getattr(handler, '__name__', str(handler))
            logger.debug(
                f"Subscribed {handler_name} to {event_type.__name__} (symbol='{symbol}')"
            )
        else:
            handler_name = getattr(handler, '__name__', str(handler))
            logger.warning(
                f"Handler {handler_name} already subscribed to {event_type.__name__} (symbol='{symbol}')"
            )

    def unsubscribe(
        self,
        event_type: Type[EventT],
        handler: EventHandler[EventT],
        symbol: str = "",
    ) -> None:
        """
        取消订阅指定类型的事件。

        Args:
            event_type: 事件类。
            handler:    要移除的回调函数。
            symbol:     标的代码订阅项。
        """
        subs = self._subscribers[event_type][symbol]
        to_remove = [r for r in subs if r() == handler]
        if to_remove:
            for r in to_remove:
                subs.remove(r)
            handler_name = getattr(handler, '__name__', str(handler))
            logger.debug(
                f"Unsubscribed {handler_name} from {event_type.__name__} (symbol='{symbol}')"
            )
        else:
            handler_name = getattr(handler, '__name__', str(handler))
            logger.warning(
                f"Handler {handler_name} not found in {event_type.__name__} (symbol='{symbol}') subscribers"
            )

    # -----------------------------------------------------------------------
    # 事件发布
    # -----------------------------------------------------------------------

    def publish(self, event: BaseEvent) -> None:
        """
        发布事件，精准路由调用相关的 Handler。

        处理流程：
          1. 提取事件的类型与 Symbol。
          2. 从二维字典 O(1) 取出对应的 Symbol 订阅群及全局订阅群。
          3. 按订阅顺序依次调用 Handler（同步阻塞）。
          4. 垃圾回收死掉的 weakref 订阅者。
        """
        event_type = type(event)
        symbol = getattr(event, "symbol", "")
        
        # 匹配精准 symbol 级别，以及全局订阅级别 (symbol="")
        target_refs = set()
        if symbol in self._subscribers[event_type]:
            target_refs.update(self._subscribers[event_type][symbol])
        if "" in self._subscribers[event_type]:
            target_refs.update(self._subscribers[event_type][""])

        if not target_refs:
            logger.debug(
                f"No subscribers for {event_type.__name__} (symbol='{symbol}', event_id={event.event_id})"
            )
            return

        dead_refs = []
        handlers_to_call = []
        for ref in target_refs:
            handler = ref()
            if handler is None:
                dead_refs.append(ref)
            else:
                handlers_to_call.append(handler)
                
        # 清理失效的弱引用
        for ref in dead_refs:
            for s in [symbol, ""]:
                if s in self._subscribers[event_type] and ref in self._subscribers[event_type][s]:
                    self._subscribers[event_type][s].remove(ref)

        logger.debug(
            f"Publishing {event_type.__name__} (symbol='{symbol}') to {len(handlers_to_call)} handler(s) "
            f"(event_id={event.event_id})"
        )

        for handler in handlers_to_call:
            try:
                handler(event)
            except Exception as e:
                handler_name = getattr(handler, '__name__', str(handler))
                logger.exception(
                    f"Handler {handler_name} failed on {event_type.__name__}: {e}"
                )
                # 继续执行后续 Handler，保证系统鲁棒性

    # -----------------------------------------------------------------------
    # 工具方法
    # -----------------------------------------------------------------------

    def clear_all_subscriptions(self) -> None:
        """
        清空所有订阅关系（主要用于单元测试的 teardown）。
        """
        self._subscribers.clear()
        logger.info("All subscriptions cleared.")

    def get_subscriber_count(self, event_type: Type[BaseEvent]) -> int:
        """
        获取某事件类型的订阅者数量（用于监控和调试）。

        Args:
            event_type: 事件类。

        Returns:
            订阅者数量。
        """
        return len(self._subscribers.get(event_type, []))


# ---------------------------------------------------------------------------
# 全局单例（可选）
# ---------------------------------------------------------------------------

# 若系统采用全局单例模式，可在此处实例化：
# global_event_bus = EventBus()
#
# 使用方式：
#   from event_bus import global_event_bus
#   global_event_bus.subscribe(TickEvent, my_handler)
#
# 注意：单例模式便于使用，但会增加测试难度（需 mock 全局状态）。
# 推荐使用依赖注入（Dependency Injection）方式传递 EventBus 实例。
