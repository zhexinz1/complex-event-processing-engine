"""
xt_connection_manager.py — 迅投连接管理器

管理多个迅投账号的连接，支持：
- 为每个账号维护独立的连接
- 连接复用和自动重连
- 线程安全
"""

import logging
import threading
from typing import Dict, Optional, Tuple
from adapters.xt_order_service import XtOrderService

logger = logging.getLogger(__name__)


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
        if hasattr(self, '_initialized'):
            return

        self._initialized = True
        self._connections: Dict[str, XtOrderService] = {}  # username -> service
        self._conn_lock = threading.Lock()

    def get_connection(
        self,
        username: str,
        password: str,
        account_id: str,
        timeout: float = 30.0
    ) -> Optional[XtOrderService]:
        """
        获取或创建指定账号的连接

        Args:
            username: 迅投用户名
            password: 迅投密码
            account_id: 资金账号ID
            timeout: 连接超时时间

        Returns:
            XtOrderService 实例，失败返回 None
        """
        with self._conn_lock:
            # 检查是否已有连接
            if username in self._connections:
                service = self._connections[username]
                if service._logined:
                    logger.info(f"复用已有连接: {username}")
                    return service
                else:
                    logger.warning(f"连接已断开，重新连接: {username}")
                    del self._connections[username]

            # 创建新连接
            logger.info(f"创建新连接: {username}")
            service = self._create_service(username, password, account_id)

            if service.connect(timeout=timeout):
                self._connections[username] = service
                return service
            else:
                logger.error(f"连接失败: {username}")
                return None

    def _create_service(
        self,
        username: str,
        password: str,
        account_id: str
    ) -> XtOrderService:
        """创建新的 XtOrderService 实例"""
        return XtOrderService(username=username, password=password)

    def disconnect(self, username: str):
        """断开指定账号的连接"""
        with self._conn_lock:
            if username in self._connections:
                service = self._connections[username]
                service.disconnect()
                del self._connections[username]
                logger.info(f"已断开连接: {username}")

    def disconnect_all(self):
        """断开所有连接"""
        with self._conn_lock:
            for username, service in list(self._connections.items()):
                try:
                    service.disconnect()
                except Exception as e:
                    logger.exception(f"断开连接失败: {username}")
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
