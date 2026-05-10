from typing import Any

class XtError:
    def __init__(self, *args: Any) -> None: ...
    def isSuccess(self) -> bool: ...
    def errorMsg(self) -> str: ...

class XtTraderApiCallback:
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

class XtTraderApi:
    @classmethod
    def createXtTraderApi(cls, address: str) -> Any: ...

class EBrokerLoginStatus:
    BROKER_LOGIN_STATUS_OK: int
    BROKER_LOGIN_STATUS_CLOSED: int

class COrdinaryOrder:
    def __setattr__(self, name: str, value: Any) -> None: ...
    def __getattr__(self, name: str) -> Any: ...

class CIntelligentAlgorithmOrder:
    def __setattr__(self, name: str, value: Any) -> None: ...
    def __getattr__(self, name: str) -> Any: ...

class EPriceType:
    PRTP_FIX: int
    PRTP_MARKET: int
    PRTP_MARKET_BEST: int

class EOperationType:
    OPT_BUY: int
    OPT_SELL: int
    OPT_OPEN_LONG: int
    OPT_CLOSE_LONG_TODAY: int
    OPT_OPEN_SHORT: int
    OPT_CLOSE_SHORT_TODAY: int

class CSubscribData:
    m_nPlatformID: int
    m_strExchangeID: str
    m_strInstrumentID: str
    m_eOfferStatus: int
    def __setattr__(self, name: str, value: Any) -> None: ...
    def __getattr__(self, name: str) -> Any: ...

class EXTOfferStatus:
    XT_OFFER_STATUS_SP: int
