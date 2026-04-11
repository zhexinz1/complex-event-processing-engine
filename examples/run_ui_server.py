"""
run_ui_server.py — 一键启动目标仓位配置大屏

用法：
    uv run -m examples.run_ui_server
    # 或
    python examples/run_ui_server.py

启动后访问 http://43.160.206.71:5000
"""

import logging
import os
import sys
from pathlib import Path

# 确保项目根目录在 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)

from adapters.flask_app import create_app, init_db  # noqa: E402

if __name__ == "__main__":
    try:
        init_db()
        logging.getLogger(__name__).info("数据库初始化成功")
    except Exception as e:
        logging.getLogger(__name__).warning("数据库连接失败（服务仍将启动）: %s", e)

    port = int(os.getenv("PORT", "5000"))
    app = create_app()
    print("\n  CEP 目标仓位配置大屏已启动")
    print(f"  访问地址: http://43.160.206.71:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
