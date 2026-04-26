"""测试 ZMQ 发布 Tick 数据"""
import zmq
import pickle
from datetime import datetime
from cep.core.events import TickEvent

# 创建模拟 Tick
tick = TickEvent(
    symbol="au2606",
    last_price=560.50,
    bid_prices=(560.40, 560.30, 560.20, 560.10, 560.00),
    bid_volumes=(10, 20, 30, 40, 50),
    ask_prices=(560.60, 560.70, 560.80, 560.90, 561.00),
    ask_volumes=(15, 25, 35, 45, 55),
    volume=100,
    turnover=56050.0,
    timestamp=datetime.now()
)

# 发布到 ZMQ
context = zmq.Context()
publisher = context.socket(zmq.PUB)
publisher.connect("tcp://localhost:5555")  # 连接到 ctp_market_service

print("等待 1 秒让连接建立...")
import time
time.sleep(1)

print(f"发布模拟 Tick: {tick.symbol} @ {tick.last_price}")
data = pickle.dumps(tick)
publisher.send_multipart([b"tick", data])

print("已发送，等待 2 秒...")
time.sleep(2)

publisher.close()
context.term()
print("完成")
