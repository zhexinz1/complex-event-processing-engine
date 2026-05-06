"""
xt_connection_manager.py — 迅投连接管理器

管理多个迅投账号的连接，支持：
- 为每个账号维护独立的连接
- 连接复用和自动重连
- 线程安全

返回的连接实例同时具备下单和查询能力（多重继承）。
"""

import logging
import threading
from typing import Dict, Optional

from adapters.xuntou.order_service import XtOrderService
from adapters.xuntou.query_service import XtQueryService

logger = logging.getLogger(__name__)


class _XtFullService(XtOrderService, XtQueryService):
    """
    组合服务 — 通过多重继承同时拥有下单和查询能力。

    继承关系：
        XtBaseService (连接管理)
        ├── XtOrderService (下单/撤单)
        └── XtQueryService (查询)
        _XtFullService(XtOrderService, XtQueryService)  ← 两者都有

    外部调用方拿到此实例后可直接调用：
    - service.place_order(...)
    - service.query_instructions(...)
    无需 wrap() 或创建额外对象。
    """

    pass


class XtConnectionManager:
    """迅投连接管理器（单例）"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return

        self._initialized = True
        self._connections: Dict[str, _XtFullService] = {}  # username -> service
        self._conn_lock = threading.Lock()

    def get_connection(
        self,
        username: str,
        password: str,
        account_id: str,
        timeout: float = 30.0,
        dao: object = None,
    ) -> Optional[_XtFullService]:
        """
        获取或创建指定账号的连接

        Args:
            username: 迅投用户名
            password: 迅投密码
            account_id: 资金账号ID
            timeout: 连接超时时间
            dao: 数据库访问层（可选，传入后回调会写 DB）

        Returns:
            具有下单和查询能力的服务实例，失败返回 None
        """
        with self._conn_lock:
            if username in self._connections:
                service = self._connections[username]
                if service._logined:
                    # 更新 DAO（可能首次连接时没传）
                    if dao and service._dao is None:
                        service._dao = dao
                    logger.info("复用已有连接: %s", username)
                    return service
                else:
                    logger.warning("连接已断开，重新连接: %s", username)
                    del self._connections[username]

            logger.info("创建新连接: %s", username)
            service = _XtFullService(username=username, password=password, dao=dao)

            if service.connect(timeout=timeout):
                self._connections[username] = service
                return service
            else:
                logger.error("连接失败: %s", username)
                return None

    def disconnect(self, username: str):
        """断开指定账号的连接"""
        with self._conn_lock:
            if username in self._connections:
                service = self._connections[username]
                service.disconnect()
                del self._connections[username]
                logger.info("已断开连接: %s", username)

    def disconnect_all(self):
        """断开所有连接"""
        with self._conn_lock:
            for username, service in list(self._connections.items()):
                try:
                    service.disconnect()
                except Exception:
                    logger.exception("断开连接失败: %s", username)
            self._connections.clear()
            logger.info("已断开所有连接")


# 全局单例
_manager: Optional[XtConnectionManager] = None


def get_xt_connection_manager() -> XtConnectionManager:
    """获取迅投连接管理器单例"""
    global _manager
    if _manager is None:
        _manager = XtConnectionManager()
    return _manager
