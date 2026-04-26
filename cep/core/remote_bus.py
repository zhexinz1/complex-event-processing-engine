"""
remote_bus.py - 跨进程分布式 EventBus 桥接器 (Redis Streams / PubSub)

提供将内存级 EventBus 桥接到 Redis 消息队列的能力，实现 CTP 与 迅投 真正意义上的物理进程隔离。
使用了极致高效的 Pickle 直接序列化 Dataclass，省去 JSON 编解码的性能损耗。
"""

import logging
import pickle
import threading
from typing import Any

import redis
from cep.core.event_bus import EventBus

logger = logging.getLogger(__name__)

class RedisEventBridge:
    def __init__(self, local_bus: EventBus, redis_url: str = "redis://localhost:6379/0", channel: str = "cep_events"):
        self.local_bus = local_bus
        self.channel = channel
        self.redis_client = redis.from_url(redis_url)
        self.pubsub = self.redis_client.pubsub()
        self._running = False
        self._thread = None
        
    def start_publishing(self, event_types: list[type]):
        """
        作为【发送方/Market Node】启动：
        监听本地 EventBus 的特定事件，转推到 Redis 远端。
        """
        for etype in event_types:
            self.local_bus.subscribe(etype, self._on_local_event)
        logger.info(f"[RedisBridge Publisher] Ready to relay events: {[t.__name__ for t in event_types]}")
            
    def _on_local_event(self, event: Any):
        """本地产生事件 -> 序列化为字节 -> Redis Pub"""
        try:
            data = pickle.dumps(event)
            self.redis_client.publish(self.channel, data)
        except Exception as e:
            logger.error(f"发布事件到 Redis 失败: {e}")

    def start_consuming(self):
        """
        作为【接收方/Trading Node】启动：
        订阅 Redis 通道，收到字节流后立刻反序列化并注入到本进程的 EventBus 中。
        """
        self.pubsub.subscribe(**{self.channel: self._on_redis_message})
        self._running = True
        self._thread = threading.Thread(target=self._run_consumer, daemon=True, name="RedisConsumerWorker")
        self._thread.start()
        logger.info(f"[RedisBridge Consumer] Started listening to remote channel: {self.channel}")
        
    def _run_consumer(self):
        try:
            for message in self.pubsub.listen():
                if not self._running:
                    break
        except Exception as e:
            logger.error(f"Redis 消费线程异常退出: {e}")
            
    def _on_redis_message(self, message):
        """核心流转逻辑：Redis 收到二进制流 -> 反序列化为 Dataclass -> 触发本地 EventBus"""
        if message['type'] == 'message':
            try:
                event = pickle.loads(message['data'])
                # 把网络事件当成本地事件投递给后端的引擎执行
                self.local_bus.publish(event)
            except Exception as e:
                logger.error(f"解析跨进程事件包失败: {e}")
                
    def stop(self):
        """优雅退出"""
        self._running = False
        try:
            self.pubsub.close()
            self.redis_client.close()
        except:
            pass
