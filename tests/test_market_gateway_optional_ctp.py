import builtins
import importlib.util
import sys
import uuid
from pathlib import Path

from cep.core.event_bus import EventBus


MODULE_PATH = Path(__file__).resolve().parent.parent / "adapters" / "market_gateway.py"


def _load_market_gateway_with_import_error(exc: Exception):
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "openctp_ctp":
            raise exc
        return real_import(name, globals, locals, fromlist, level)

    module_name = f"test_market_gateway_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    builtins.__import__ = fake_import
    try:
        spec.loader.exec_module(module)
    finally:
        builtins.__import__ = real_import
        sys.modules.pop(module_name, None)

    return module


def test_market_gateway_module_loads_when_ctp_native_import_raises_oserror() -> None:
    module = _load_market_gateway_with_import_error(OSError("wrong architecture"))

    assert module._CTP_AVAILABLE is False
    assert isinstance(module._CTP_IMPORT_ERROR, OSError)
    assert module.CTPMdSpi.__mro__[1] is object


def test_ctp_market_gateway_connect_returns_false_when_ctp_unavailable() -> None:
    module = _load_market_gateway_with_import_error(OSError("wrong architecture"))

    gateway = module.CTPMarketGateway(
        event_bus=EventBus(),
        front_addr="tcp://example:1234",
        broker_id="0000",
        user_id="demo",
        password="secret",
    )

    assert gateway.connect() is False
