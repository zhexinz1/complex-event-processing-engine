"""
contract_config.py — 合约配置与标准化工具

提供合约乘数查询、交易所映射、资产代码标准化等功能。
所有查找均使用小写匹配，保留输入的原始大小写。
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 合约乘数静态映射（小写品种前缀）
# ---------------------------------------------------------------------------

CONTRACT_MULTIPLIERS: dict[str, int] = {
    "au": 1000,   # 黄金
    "ag": 15,     # 白银
    "cu": 5,      # 铜
    "al": 5,      # 铝
    "zn": 5,      # 锌
    "pb": 5,      # 铅
    "ni": 1,      # 镍
    "sn": 1,      # 锡
    "rb": 10,     # 螺纹钢
    "hc": 10,     # 热卷
    "ss": 5,      # 不锈钢
    "fu": 10,     # 燃料油
    "bu": 10,     # 沥青
    "ru": 10,     # 橡胶
    "nr": 10,     # 20号胶
    "sp": 10,     # 纸浆
    "sc": 1000,   # 原油
    "lu": 10,     # 低硫燃油
    "bc": 5,      # 国际铜
    "c":  10,     # 玉米
    "cs": 10,     # 玉米淀粉
    "a":  10,     # 豆一
    "b":  10,     # 豆二
    "m":  10,     # 豆粕
    "y":  10,     # 豆油
    "p":  10,     # 棕榈油
    "jd": 10,     # 鸡蛋
    "l":  5,      # 塑料
    "v":  5,      # PVC
    "pp": 5,      # 聚丙烯
    "j":  100,    # 焦炭
    "jm": 60,     # 焦煤
    "i":  100,    # 铁矿石
    "eg": 10,     # 乙二醇
    "eb": 5,      # 苯乙烯
    "pg": 20,     # LPG
    "lh": 16,     # 生猪
    "cf": 5,      # 棉花
    "sr": 10,     # 白糖
    "ta": 5,      # PTA
    "ma": 10,     # 甲醇
    "fg": 20,     # 玻璃
    "sa": 20,     # 纯碱
    "rm": 10,     # 菜粕
    "oi": 10,     # 菜油
    "ap": 10,     # 苹果
    "ur": 20,     # 尿素
    "pf": 5,      # 短纤
    "pk": 5,      # 花生
    "if": 300,    # 沪深300股指
    "ic": 200,    # 中证500股指
    "ih": 300,    # 上证50股指
    "im": 200,    # 中证1000股指
    "t":  10000,  # 10年国债
    "tf": 10000,  # 5年国债
    "ts": 20000,  # 2年国债
}

# ---------------------------------------------------------------------------
# 期货品种 → 交易所映射（小写品种前缀）
# ---------------------------------------------------------------------------

FUTURES_EXCHANGE_MAP: dict[str, str] = {
    # 上期所 SHFE
    "cu": "SHFE", "al": "SHFE", "zn": "SHFE", "pb": "SHFE", "ni": "SHFE",
    "sn": "SHFE", "au": "SHFE", "ag": "SHFE", "rb": "SHFE", "wr": "SHFE",
    "hc": "SHFE", "ss": "SHFE", "fu": "SHFE", "bu": "SHFE", "ru": "SHFE",
    "nr": "SHFE", "sp": "SHFE",
    # 上海国际能源交易中心 INE
    "sc": "INE", "lu": "INE", "bc": "INE",
    # 大商所 DCE
    "c": "DCE", "cs": "DCE", "a": "DCE", "b": "DCE", "m": "DCE", "y": "DCE",
    "p": "DCE", "fb": "DCE", "bb": "DCE", "jd": "DCE", "rr": "DCE", "l": "DCE",
    "v": "DCE", "pp": "DCE", "j": "DCE", "jm": "DCE", "i": "DCE", "eg": "DCE",
    "eb": "DCE", "pg": "DCE", "lh": "DCE",
    # 郑商所 CZCE
    "wh": "CZCE", "pm": "CZCE", "cf": "CZCE", "cy": "CZCE", "sr": "CZCE",
    "ta": "CZCE", "oi": "CZCE", "ri": "CZCE", "ma": "CZCE", "fg": "CZCE",
    "rs": "CZCE", "rm": "CZCE", "zc": "CZCE", "jr": "CZCE", "lr": "CZCE",
    "sf": "CZCE", "sm": "CZCE", "ap": "CZCE", "cj": "CZCE", "ur": "CZCE",
    "sa": "CZCE", "pf": "CZCE", "pk": "CZCE",
    # 中金所 CFFEX
    "if": "CFFEX", "ic": "CFFEX", "ih": "CFFEX", "im": "CFFEX",
    "t": "CFFEX", "tf": "CFFEX", "ts": "CFFEX", "tl": "CFFEX",
}


def get_contract_multiplier(asset_code: str) -> int:
    """
    根据合约代码前缀查找合约乘数，找不到返回 1。
    使用小写匹配，不改变输入大小写。
    """
    code = asset_code.split('.')[0]
    # 从最长前缀开始匹配（如 "jm" 优先于 "j"）
    for length in (3, 2, 1):
        prefix = code[:length].lower()
        if prefix in CONTRACT_MULTIPLIERS:
            return CONTRACT_MULTIPLIERS[prefix]
    return 1


def normalize_asset_code(asset_code: str) -> str:
    """
    标准化资产代码，自动为期货合约添加交易所后缀。

    - 如果已经包含交易所后缀（如 "ag2606.SHFE"），直接返回
    - 如果是期货合约（如 "ag2606"），自动添加交易所后缀
    - 如果是股票（如 "600519"），添加 .SH 或 .SZ 后缀

    返回: 标准化后的资产代码（如 "ag2606.SHFE"），保留原始大小写
    """
    code = asset_code.strip()

    # 已经包含交易所后缀
    if '.' in code:
        return code

    # 提取品种代码（去掉数字部分）
    match = re.match(r'^([a-zA-Z]+)', code)
    if not match:
        # 纯数字，可能是股票代码
        if code.isdigit():
            if code.startswith('6'):
                return f"{code}.SH"
            elif code.startswith(('0', '3')):
                return f"{code}.SZ"
        return code

    variety = match.group(1)

    # 小写匹配查找期货交易所
    if variety.lower() in FUTURES_EXCHANGE_MAP:
        exchange = FUTURES_EXCHANGE_MAP[variety.lower()]
        return f"{code}.{exchange}"

    # 股票代码
    if code.isdigit():
        if code.startswith('6'):
            return f"{code}.SH"
        elif code.startswith(('0', '3')):
            return f"{code}.SZ"

    # 无法识别，返回原值
    return code
