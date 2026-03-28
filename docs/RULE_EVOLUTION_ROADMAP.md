# 规则系统演进路线图

## 📊 当前规则系统的局限性分析

### 现状
当前 CEP 系统支持的规则类型：
```python
# 示例：技术指标组合规则
"当 RSI < 30 且 MACD 金叉时买入"

# AST 结构
LogicalNode(AND)
├── OperatorNode(<)
│   ├── IndicatorNode("RSI", params={"period": 14})
│   └── ConstantNode(30)
└── OperatorNode(>)
    ├── IndicatorNode("MACD", component="DIF")
    └── IndicatorNode("MACD", component="DEA")
```

### 核心问题

#### 1. **单因子规则胜率低**
- **问题**：技术指标本质是价格的滞后函数，单一指标信号噪音大
- **数据**：RSI < 30 买入的胜率通常只有 45-55%（接近随机）
- **原因**：
  - 技术指标已被市场充分定价
  - 缺乏基本面和宏观环境的验证
  - 没有考虑市场状态（牛市/熊市/震荡）

#### 2. **规则表达能力有限**
- **当前能力**：只能表达"条件 → 信号"的简单映射
- **缺失能力**：
  - 无法表达"因子权重"（RSI 重要性 60%，MACD 40%）
  - 无法表达"时间序列依赖"（连续 3 天 RSI < 30）
  - 无法表达"跨品种关系"（沪金涨 + 美元跌 → 买入黄金）
  - 无法表达"状态机"（趋势确认 → 等待回调 → 入场）

#### 3. **缺乏自适应能力**
- **问题**：规则参数固定（RSI 阈值永远是 30）
- **现实**：市场状态变化，最优参数也在变化
  - 牛市：RSI < 40 可能就是超卖
  - 熊市：RSI < 20 才是真正超卖

#### 4. **没有风险控制**
- **问题**：规则只管"买入信号"，不管"止损/止盈"
- **风险**：一次大亏可能抹平 10 次小赚

---

## 🚀 规则演进的 4 个阶段

### **阶段 1：多因子加权模型（3 个月）**

**核心思想**：从"单一指标触发"升级为"多因子加权打分"

#### 1.1 问题定义
```python
# 当前：二元判断（买/不买）
if RSI < 30:
    return "BUY"

# 升级：连续打分（0-100 分）
score = 0.0
score += factor_rsi(rsi) * 0.3      # RSI 因子权重 30%
score += factor_macd(macd) * 0.25   # MACD 因子权重 25%
score += factor_volume(vol) * 0.2   # 成交量因子权重 20%
score += factor_trend(sma) * 0.25   # 趋势因子权重 25%

if score > 70:
    return "STRONG_BUY"
elif score > 50:
    return "BUY"
```

#### 1.2 技术实现

**新增模块**：`factors/factor_engine.py`

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class FactorResult:
    """因子计算结果"""
    name: str           # 因子名称
    value: float        # 原始值
    score: float        # 归一化分数（0-100）
    weight: float       # 因子权重
    contribution: float # 加权贡献度

class BaseFactor(ABC):
    """因子基类"""

    def __init__(self, name: str, weight: float = 1.0):
        self.name = name
        self.weight = weight

    @abstractmethod
    def calculate(self, context: LocalContext) -> float:
        """计算因子原始值"""
        pass

    @abstractmethod
    def normalize(self, value: float) -> float:
        """归一化到 0-100 分"""
        pass

    def evaluate(self, context: LocalContext) -> FactorResult:
        """完整求值流程"""
        value = self.calculate(context)
        score = self.normalize(value)
        contribution = score * self.weight
        return FactorResult(
            name=self.name,
            value=value,
            score=score,
            weight=self.weight,
            contribution=contribution
        )

class RSIFactor(BaseFactor):
    """RSI 因子"""

    def calculate(self, context: LocalContext) -> float:
        return context.rsi

    def normalize(self, value: float) -> float:
        """
        RSI 归一化逻辑：
        - RSI < 30: 超卖，分数高（看涨）
        - RSI > 70: 超买，分数低（看跌）
        """
        if value < 30:
            return 100 - value  # RSI 越低，分数越高
        elif value > 70:
            return 170 - value  # RSI 越高，分数越低
        else:
            return 50  # 中性区域

class FactorEngine:
    """多因子引擎"""

    def __init__(self, factors: list[BaseFactor]):
        self.factors = factors
        self._normalize_weights()

    def _normalize_weights(self):
        """归一化权重，确保总和为 1"""
        total = sum(f.weight for f in self.factors)
        for f in self.factors:
            f.weight /= total

    def evaluate(self, context: LocalContext) -> dict:
        """计算所有因子并汇总"""
        results = [f.evaluate(context) for f in self.factors]
        total_score = sum(r.contribution for r in results)

        return {
            "total_score": total_score,
            "factors": results,
            "signal": self._generate_signal(total_score)
        }

    def _generate_signal(self, score: float) -> str:
        """根据总分生成信号"""
        if score > 75:
            return "STRONG_BUY"
        elif score > 60:
            return "BUY"
        elif score > 40:
            return "HOLD"
        elif score > 25:
            return "SELL"
        else:
            return "STRONG_SELL"
```

#### 1.3 因子库扩展

**技术因子**：
- 动量因子：RSI、MACD、KDJ
- 趋势因子：SMA、EMA、ADX
- 波动因子：ATR、布林带宽度
- 成交量因子：量价背离、OBV

**基本面因子**（期货特有）：
- 持仓量变化（OI Delta）
- 基差（现货价 - 期货价）
- 库存数据（如黄金 ETF 持仓）
- 季节性因子（农产品）

**宏观因子**：
- 美元指数（影响商品价格）
- 利率水平（影响债券价格）
- 通胀预期（CPI、PPI）
- 经济景气度（PMI）

#### 1.4 因子有效性检验

**关键指标**：
- **IC（信息系数）**：因子值与未来收益的相关性
- **IR（信息比率）**：IC 均值 / IC 标准差
- **分层回测**：按因子值分 5 组，看收益差异

```python
# factors/factor_validator.py
class FactorValidator:
    """因子有效性检验"""

    def calculate_ic(self, factor_values, future_returns):
        """计算 IC（Spearman 相关系数）"""
        from scipy.stats import spearmanr
        ic, p_value = spearmanr(factor_values, future_returns)
        return ic, p_value

    def calculate_ir(self, ic_series):
        """计算 IR"""
        return ic_series.mean() / ic_series.std()

    def layered_backtest(self, factor_values, returns, n_groups=5):
        """分层回测"""
        # 按因子值分组
        groups = pd.qcut(factor_values, n_groups, labels=False)

        # 计算各组平均收益
        group_returns = {}
        for i in range(n_groups):
            mask = (groups == i)
            group_returns[f"Group_{i+1}"] = returns[mask].mean()

        return group_returns
```

**因子筛选标准**：
- IC 绝对值 > 0.03（有效）
- IC > 0.05（优秀）
- IR > 0.5（稳定）
- 分层回测：最高组 vs 最低组收益差 > 5%

---

### **阶段 2：机器学习增强（6 个月）**

**核心思想**：用机器学习自动发现因子组合和权重

#### 2.1 为什么需要机器学习？

**人工因子的局限**：
- 因子权重靠经验拍脑袋（RSI 30%，MACD 25%）
- 无法捕捉非线性关系（RSI < 30 且成交量暴增才有效）
- 无法处理高维交互（10 个因子的组合爆炸）

**机器学习的优势**：
- 自动学习最优权重
- 捕捉非线性模式
- 处理高维特征

#### 2.2 技术路线

**方案 A：传统机器学习（推荐先做）**

```python
# ml/ml_factor_model.py
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
import xgboost as xgb
import lightgbm as lgb

class MLFactorModel:
    """机器学习因子模型"""

    def __init__(self, model_type="xgboost"):
        if model_type == "xgboost":
            self.model = xgb.XGBClassifier(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1
            )
        elif model_type == "lightgbm":
            self.model = lgb.LGBMClassifier()
        elif model_type == "random_forest":
            self.model = RandomForestClassifier(n_estimators=100)

    def prepare_features(self, context: LocalContext) -> np.ndarray:
        """特征工程"""
        features = []

        # 技术指标特征
        features.append(context.rsi)
        features.append(context.macd_dif)
        features.append(context.macd_dea)
        features.append(context.kdj_k)
        features.append(context.sma_20)
        features.append(context.ema_12)

        # 价格特征
        features.append(context.close / context.sma_20 - 1)  # 偏离度
        features.append(context.high / context.low - 1)      # 振幅

        # 成交量特征
        features.append(context.volume / context.avg_volume - 1)

        # 时间特征
        features.append(context.bar_time.hour)
        features.append(context.bar_time.weekday())

        return np.array(features).reshape(1, -1)

    def train(self, X_train, y_train):
        """训练模型"""
        self.model.fit(X_train, y_train)

    def predict_proba(self, context: LocalContext) -> float:
        """预测上涨概率"""
        features = self.prepare_features(context)
        proba = self.model.predict_proba(features)[0, 1]  # 上涨概率
        return proba

    def get_feature_importance(self) -> dict:
        """获取特征重要性"""
        if hasattr(self.model, 'feature_importances_'):
            return dict(zip(
                self.feature_names,
                self.model.feature_importances_
            ))
        return {}
```

**标签构造**（关键）：
```python
def create_labels(bars, forward_window=5, threshold=0.02):
    """
    构造训练标签

    Args:
        bars: K 线数据
        forward_window: 未来 N 根 K 线
        threshold: 涨跌阈值（2%）

    Returns:
        labels: 1（上涨）/ 0（下跌）
    """
    labels = []
    for i in range(len(bars) - forward_window):
        current_price = bars[i].close
        future_price = bars[i + forward_window].close

        return_rate = (future_price - current_price) / current_price

        if return_rate > threshold:
            labels.append(1)  # 上涨
        else:
            labels.append(0)  # 下跌或横盘

    return np.array(labels)
```

**方案 B：深度学习（进阶）**

```python
# ml/lstm_model.py
import torch
import torch.nn as nn

class LSTMPricePredictor(nn.Module):
    """LSTM 价格预测模型"""

    def __init__(self, input_size, hidden_size=64, num_layers=2):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=0.2
        )
        self.fc = nn.Linear(hidden_size, 1)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        """
        Args:
            x: (batch, seq_len, input_size)
        Returns:
            proba: (batch, 1) 上涨概率
        """
        lstm_out, _ = self.lstm(x)
        last_hidden = lstm_out[:, -1, :]  # 取最后一个时间步
        logits = self.fc(last_hidden)
        proba = self.sigmoid(logits)
        return proba
```

#### 2.3 模型训练流程

```python
# ml/training_pipeline.py
class TrainingPipeline:
    """模型训练流水线"""

    def __init__(self, symbol, start_date, end_date):
        self.symbol = symbol
        self.start_date = start_date
        self.end_date = end_date

    def run(self):
        """完整训练流程"""
        # 1. 加载历史数据
        bars = self.load_historical_data()

        # 2. 特征工程
        X = self.extract_features(bars)

        # 3. 标签构造
        y = create_labels(bars, forward_window=5, threshold=0.02)

        # 4. 数据集划分（时间序列不能随机打乱）
        split_idx = int(len(X) * 0.8)
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]

        # 5. 训练模型
        model = MLFactorModel(model_type="xgboost")
        model.train(X_train, y_train)

        # 6. 评估模型
        metrics = self.evaluate(model, X_test, y_test)

        # 7. 保存模型
        self.save_model(model, metrics)

        return model, metrics

    def evaluate(self, model, X_test, y_test):
        """模型评估"""
        from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score

        y_pred = model.model.predict(X_test)
        y_proba = model.model.predict_proba(X_test)[:, 1]

        metrics = {
            "accuracy": accuracy_score(y_test, y_pred),
            "precision": precision_score(y_test, y_pred),
            "recall": recall_score(y_test, y_pred),
            "auc": roc_auc_score(y_test, y_proba)
        }

        return metrics
```

**模型评估标准**：
- 准确率 > 55%（超过随机）
- AUC > 0.6（有区分能力）
- 精确率 > 60%（减少假信号）
- 回测夏普比率 > 1.0

#### 2.4 在线预测集成

```python
# triggers/ml_trigger.py
class MLTrigger(BaseTrigger):
    """机器学习触发器"""

    def __init__(self, event_bus, trigger_id, model_path, local_context):
        super().__init__(event_bus, trigger_id)
        self.model = self.load_model(model_path)
        self.local_context = local_context

    def register(self):
        self.event_bus.subscribe(BarEvent, self.on_event, symbol=self.local_context.symbol)

    def on_event(self, event: BarEvent):
        # 更新上下文
        self.local_context.update_bar(event)

        # 模型预测
        proba = self.model.predict_proba(self.local_context)

        # 阈值判断
        if proba > 0.7:  # 70% 概率上涨
            self._emit_signal(
                symbol=event.symbol,
                signal_type=SignalType.TRADE_OPPORTUNITY,
                payload={
                    "proba": proba,
                    "model": "xgboost_v1",
                    "confidence": "HIGH"
                }
            )
```

---

### **阶段 3：状态机与策略组合（9 个月）**

**核心思想**：从"单次信号"升级为"多阶段策略"

#### 3.1 问题定义

**当前问题**：
```python
# 当前：一次性信号
if rsi < 30:
    return "BUY"  # 立即买入，没有后续跟踪
```

**现实需求**：
```python
# 理想：多阶段策略
状态 1: 趋势确认（等待 SMA 金叉）
  ↓
状态 2: 等待回调（RSI < 40）
  ↓
状态 3: 入场信号（MACD 金叉）
  ↓
状态 4: 持仓管理（移动止损）
  ↓
状态 5: 出场信号（止盈/止损）
```

#### 3.2 状态机实现

**新增模块**：`strategies/strategy_state_machine.py`

```python
from enum import Enum
from dataclasses import dataclass
from typing import Optional

class StrategyState(Enum):
    """策略状态"""
    IDLE = "IDLE"                    # 空闲，等待入场条件
    TREND_CONFIRMED = "TREND_CONFIRMED"  # 趋势确认
    WAITING_PULLBACK = "WAITING_PULLBACK"  # 等待回调
    ENTRY_SIGNAL = "ENTRY_SIGNAL"    # 入场信号
    IN_POSITION = "IN_POSITION"      # 持仓中
    STOP_LOSS = "STOP_LOSS"          # 止损出场
    TAKE_PROFIT = "TAKE_PROFIT"      # 止盈出场

@dataclass
class StrategyContext:
    """策略上下文（状态机的记忆）"""
    current_state: StrategyState
    entry_price: Optional[float] = None
    entry_time: Optional[datetime] = None
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    highest_price: Optional[float] = None  # 持仓期间最高价（用于移动止损）

class TrendFollowingStrategy:
    """趋势跟踪策略（状态机实现）"""

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.context = StrategyContext(current_state=StrategyState.IDLE)

    def on_bar(self, bar: BarEvent, local_context: LocalContext):
        """K 线更新时的状态转移"""

        if self.context.current_state == StrategyState.IDLE:
            # 状态 1: 等待趋势确认
            if self._check_trend_confirmed(local_context):
                self.context.current_state = StrategyState.TREND_CONFIRMED
                logger.info(f"[{self.symbol}] 趋势确认，等待回调")

        elif self.context.current_state == StrategyState.TREND_CONFIRMED:
            # 状态 2: 等待回调
            if self._check_pullback(local_context):
                self.context.current_state = StrategyState.WAITING_PULLBACK
                logger.info(f"[{self.symbol}] 回调到位，等待入场信号")

        elif self.context.current_state == StrategyState.WAITING_PULLBACK:
            # 状态 3: 等待入场信号
            if self._check_entry_signal(local_context):
                self.context.current_state = StrategyState.ENTRY_SIGNAL
                self.context.entry_price = bar.close
                self.context.entry_time = bar.bar_time
                self.context.stop_loss_price = bar.close * 0.98  # 2% 止损
                self.context.take_profit_price = bar.close * 1.06  # 6% 止盈
                self.context.highest_price = bar.close

                # 发射买入信号
                return SignalEvent(
                    symbol=self.symbol,
                    signal_type=SignalType.TRADE_OPPORTUNITY,
                    payload={
                        "action": "BUY",
                        "entry_price": self.context.entry_price,
                        "stop_loss": self.context.stop_loss_price,
                        "take_profit": self.context.take_profit_price
                    }
                )

        elif self.context.current_state == StrategyState.IN_POSITION:
            # 状态 4: 持仓管理
            self._update_trailing_stop(bar)

            # 检查止损
            if bar.close <= self.context.stop_loss_price:
                self.context.current_state = StrategyState.STOP_LOSS
                return self._exit_position(bar, "STOP_LOSS")

            # 检查止盈
            if bar.close >= self.context.take_profit_price:
                self.context.current_state = StrategyState.TAKE_PROFIT
                return self._exit_position(bar, "TAKE_PROFIT")

    def _check_trend_confirmed(self, ctx: LocalContext) -> bool:
        """趋势确认条件"""
        return (
            ctx.sma_20 > ctx.sma_60 and  # 短期均线上穿长期均线
            ctx.close > ctx.sma_20 and   # 价格在均线之上
            ctx.adx > 25                 # ADX > 25 表示趋势强劲
        )

    def _check_pullback(self, ctx: LocalContext) -> bool:
        """回调条件"""
        return (
            ctx.rsi < 40 and             # RSI 回调到 40 以下
            ctx.close > ctx.sma_20       # 但仍在均线之上（浅回调）
        )

    def _check_entry_signal(self, ctx: LocalContext) -> bool:
        """入场信号"""
        return (
            ctx.macd_dif > ctx.macd_dea and  # MACD 金叉
            ctx.volume > ctx.avg_volume * 1.2  # 成交量放大
        )

    def _update_trailing_stop(self, bar: BarEvent):
        """移动止损"""
        if bar.high > self.context.highest_price:
            self.context.highest_price = bar.high
            # 止损价跟随最高价上移（保护利润）
            new_stop = self.context.highest_price * 0.95  # 5% 回撤止损
            if new_stop > self.context.stop_loss_price:
                self.context.stop_loss_price = new_stop
                logger.info(f"[{self.symbol}] 移动止损至 {new_stop:.2f}")

    def _exit_position(self, bar: BarEvent, reason: str):
        """出场"""
        pnl = (bar.close - self.context.entry_price) / self.context.entry_price

        signal = SignalEvent(
            symbol=self.symbol,
            signal_type=SignalType.TRADE_OPPORTUNITY,
            payload={
                "action": "SELL",
                "exit_price": bar.close,
                "entry_price": self.context.entry_price,
                "pnl": pnl,
                "reason": reason
            }
        )

        # 重置状态
        self.context = StrategyContext(current_state=StrategyState.IDLE)

        return signal
```

#### 3.3 策略组合（多策略并行）

**问题**：单一策略在某些市场环境下会失效
- 趋势策略在震荡市亏损
- 均值回归策略在趋势市亏损

**解决方案**：多策略组合 + 动态权重

```python
# strategies/strategy_ensemble.py
class StrategyEnsemble:
    """策略组合"""

    def __init__(self, strategies: list[BaseStrategy], weights: list[float]):
        self.strategies = strategies
        self.weights = weights
        self._normalize_weights()

    def _normalize_weights(self):
        """归一化权重"""
        total = sum(self.weights)
        self.weights = [w / total for w in self.weights]

    def on_bar(self, bar: BarEvent, local_context: LocalContext):
        """汇总所有策略的信号"""
        signals = []

        for strategy, weight in zip(self.strategies, self.weights):
            signal = strategy.on_bar(bar, local_context)
            if signal:
                signals.append((signal, weight))

        # 加权投票
        if signals:
            return self._aggregate_signals(signals)

    def _aggregate_signals(self, signals):
        """信号聚合"""
        buy_score = 0.0
        sell_score = 0.0

        for signal, weight in signals:
            if signal.payload.get("action") == "BUY":
                buy_score += weight
            elif signal.payload.get("action") == "SELL":
                sell_score += weight

        # 阈值判断
        if buy_score > 0.6:  # 60% 以上策略看多
            return SignalEvent(
                symbol=signals[0][0].symbol,
                signal_type=SignalType.TRADE_OPPORTUNITY,
                payload={
                    "action": "BUY",
                    "confidence": buy_score,
                    "strategies": [s[0].source for s in signals]
                }
            )
        elif sell_score > 0.6:
            return SignalEvent(
                symbol=signals[0][0].symbol,
                signal_type=SignalType.TRADE_OPPORTUNITY,
                payload={
                    "action": "SELL",
                    "confidence": sell_score,
                    "strategies": [s[0].source for s in signals]
                }
            )
```

**策略库**：
1. **趋势跟踪策略**：适合单边行情
2. **均值回归策略**：适合震荡行情
3. **突破策略**：适合放量突破
4. **套利策略**：跨品种价差
5. **事件驱动策略**：宏观数据发布

#### 3.4 市场状态识别

**关键**：根据市场状态动态调整策略权重

```python
# strategies/market_regime.py
class MarketRegimeDetector:
    """市场状态识别"""

    def detect_regime(self, bars: list[BarEvent]) -> str:
        """
        识别市场状态

        Returns:
            "TRENDING_UP"    - 上升趋势
            "TRENDING_DOWN"  - 下降趋势
            "RANGING"        - 震荡
            "HIGH_VOLATILITY" - 高波动
        """
        # 计算 ADX（趋势强度）
        adx = self._calculate_adx(bars)

        # 计算波动率
        volatility = self._calculate_volatility(bars)

        # 计算趋势方向
        sma_20 = self._calculate_sma(bars, 20)
        sma_60 = self._calculate_sma(bars, 60)

        # 状态判断
        if adx > 25:  # 趋势明显
            if sma_20 > sma_60:
                return "TRENDING_UP"
            else:
                return "TRENDING_DOWN"
        elif volatility > 0.03:  # 日波动率 > 3%
            return "HIGH_VOLATILITY"
        else:
            return "RANGING"

# 动态权重调整
class AdaptiveStrategyEnsemble(StrategyEnsemble):
    """自适应策略组合"""

    def __init__(self, strategies, regime_detector):
        super().__init__(strategies, weights=[1.0] * len(strategies))
        self.regime_detector = regime_detector

        # 不同市场状态下的策略权重配置
        self.regime_weights = {
            "TRENDING_UP": [0.7, 0.2, 0.1],    # 趋势策略权重高
            "TRENDING_DOWN": [0.7, 0.2, 0.1],
            "RANGING": [0.2, 0.7, 0.1],        # 均值回归权重高
            "HIGH_VOLATILITY": [0.3, 0.3, 0.4] # 均衡配置
        }

    def on_bar(self, bar: BarEvent, local_context: LocalContext):
        # 识别市场状态
        regime = self.regime_detector.detect_regime(local_context.bar_window)

        # 动态调整权重
        self.weights = self.regime_weights[regime]

        # 执行策略
        return super().on_bar(bar, local_context)
```

---

### **阶段 4：强化学习与自适应（12 个月）**

**核心思想**：让系统自己学会交易

#### 4.1 为什么需要强化学习？

**传统方法的局限**：
- 规则固定，无法适应市场变化
- 机器学习只能预测，不能决策
- 无法学习"序列决策"（何时买、何时卖、何时观望）

**强化学习的优势**：
- 自动学习最优交易策略
- 考虑长期收益（不只看单次交易）
- 适应市场变化（在线学习）

#### 4.2 技术实现

**方案 A：DQN（Deep Q-Network）**

```python
# rl/dqn_agent.py
import torch
import torch.nn as nn
import numpy as np
from collections import deque
import random

class DQNNetwork(nn.Module):
    """DQN 网络"""

    def __init__(self, state_dim, action_dim):
        super().__init__()
        self.fc1 = nn.Linear(state_dim, 128)
        self.fc2 = nn.Linear(128, 128)
        self.fc3 = nn.Linear(128, action_dim)

    def forward(self, state):
        x = torch.relu(self.fc1(state))
        x = torch.relu(self.fc2(x))
        q_values = self.fc3(x)
        return q_values

class DQNAgent:
    """DQN 交易智能体"""

    def __init__(self, state_dim, action_dim=3):
        """
        Args:
            state_dim: 状态维度（特征数量）
            action_dim: 动作维度（3: BUY, SELL, HOLD）
        """
        self.state_dim = state_dim
        self.action_dim = action_dim

        # Q 网络
        self.q_network = DQNNetwork(state_dim, action_dim)
        self.target_network = DQNNetwork(state_dim, action_dim)
        self.target_network.load_state_dict(self.q_network.state_dict())

        # 优化器
        self.optimizer = torch.optim.Adam(self.q_network.parameters(), lr=0.001)

        # 经验回放缓冲区
        self.replay_buffer = deque(maxlen=10000)

        # 超参数
        self.gamma = 0.99  # 折扣因子
        self.epsilon = 1.0  # 探索率
        self.epsilon_decay = 0.995
        self.epsilon_min = 0.01
        self.batch_size = 64

    def get_state(self, context: LocalContext) -> np.ndarray:
        """构造状态向量"""
        state = []

        # 技术指标
        state.append(context.rsi / 100)  # 归一化到 [0, 1]
        state.append((context.macd_dif + 10) / 20)  # 归一化
        state.append(context.close / context.sma_20 - 1)  # 偏离度

        # 持仓状态
        state.append(self.position)  # -1, 0, 1
        state.append(self.unrealized_pnl)  # 浮动盈亏

        return np.array(state, dtype=np.float32)

    def select_action(self, state):
        """选择动作（ε-greedy）"""
        if random.random() < self.epsilon:
            # 探索：随机动作
            return random.randint(0, self.action_dim - 1)
        else:
            # 利用：选择 Q 值最大的动作
            with torch.no_grad():
                state_tensor = torch.FloatTensor(state).unsqueeze(0)
                q_values = self.q_network(state_tensor)
                return q_values.argmax().item()

    def store_transition(self, state, action, reward, next_state, done):
        """存储经验"""
        self.replay_buffer.append((state, action, reward, next_state, done))

    def train(self):
        """训练网络"""
        if len(self.replay_buffer) < self.batch_size:
            return

        # 采样 batch
        batch = random.sample(self.replay_buffer, self.batch_size)
        states, actions, rewards, next_states, dones = zip(*batch)

        states = torch.FloatTensor(states)
        actions = torch.LongTensor(actions)
        rewards = torch.FloatTensor(rewards)
        next_states = torch.FloatTensor(next_states)
        dones = torch.FloatTensor(dones)

        # 计算当前 Q 值
        current_q = self.q_network(states).gather(1, actions.unsqueeze(1))

        # 计算目标 Q 值
        with torch.no_grad():
            next_q = self.target_network(next_states).max(1)[0]
            target_q = rewards + (1 - dones) * self.gamma * next_q

        # 损失函数
        loss = nn.MSELoss()(current_q.squeeze(), target_q)

        # 反向传播
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

        # 衰减探索率
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)

    def update_target_network(self):
        """更新目标网络"""
        self.target_network.load_state_dict(self.q_network.state_dict())
```

**奖励函数设计**（关键）：

```python
def calculate_reward(self, action, prev_price, current_price, position):
    """
    计算奖励

    Args:
        action: 0=HOLD, 1=BUY, 2=SELL
        prev_price: 上一时刻价格
        current_price: 当前价格
        position: 当前持仓（-1, 0, 1）

    Returns:
        reward: 奖励值
    """
    price_change = (current_price - prev_price) / prev_price

    # 持仓收益
    if position == 1:  # 持有多头
        reward = price_change * 100  # 价格上涨获得正奖励
    elif position == -1:  # 持有空头
        reward = -price_change * 100  # 价格下跌获得正奖励
    else:  # 空仓
        reward = 0

    # 交易成本惩罚
    if action != 0:  # 买入或卖出
        reward -= 0.001  # 手续费 0.1%

    # 风险惩罚（最大回撤）
    if self.current_drawdown > 0.1:  # 回撤超过 10%
        reward -= 10

    return reward
```

#### 4.3 训练流程

```python
# rl/training_loop.py
class RLTrainingLoop:
    """强化学习训练循环"""

    def __init__(self, agent, env, episodes=1000):
        self.agent = agent
        self.env = env
        self.episodes = episodes

    def train(self):
        """训练循环"""
        for episode in range(self.episodes):
            state = self.env.reset()
            total_reward = 0
            done = False

            while not done:
                # 选择动作
                action = self.agent.select_action(state)

                # 执行动作
                next_state, reward, done, info = self.env.step(action)

                # 存储经验
                self.agent.store_transition(state, action, reward, next_state, done)

                # 训练网络
                self.agent.train()

                state = next_state
                total_reward += reward

            # 定期更新目标网络
            if episode % 10 == 0:
                self.agent.update_target_network()

            # 记录日志
            logger.info(f"Episode {episode}: Total Reward = {total_reward:.2f}, Epsilon = {self.agent.epsilon:.3f}")
```

---

## 📊 四个阶段对比总结

| 阶段 | 核心能力 | 胜率提升 | 技术难度 | 开发周期 |
|------|---------|---------|---------|---------|
| **阶段 1：多因子** | 因子加权打分 | 50% → 55% | ⭐⭐ | 3 个月 |
| **阶段 2：机器学习** | 自动学习权重 | 55% → 60% | ⭐⭐⭐ | 6 个月 |
| **阶段 3：状态机** | 多阶段策略 | 60% → 65% | ⭐⭐⭐⭐ | 9 个月 |
| **阶段 4：强化学习** | 自适应决策 | 65% → 70%+ | ⭐⭐⭐⭐⭐ | 12 个月 |

---

## 🎯 推荐实施路径

### **优先级 P0（立即做）**
1. **多因子框架**：搭建因子引擎基础架构
2. **因子库扩展**：实现 10-15 个常用因子
3. **因子有效性检验**：IC/IR 计算，分层回测

### **优先级 P1（3 个月内）**
4. **机器学习模型**：XGBoost/LightGBM 预测
5. **特征工程**：构造 50+ 特征
6. **模型评估**：准确率、AUC、夏普比率

### **优先级 P2（6 个月内）**
7. **状态机策略**：实现 3-5 个经典策略
8. **策略组合**：多策略并行 + 动态权重
9. **市场状态识别**：趋势/震荡/高波动

### **优先级 P3（12 个月内）**
10. **强化学习**：DQN/PPO 智能体
11. **在线学习**：模型持续更新
12. **自适应优化**：参数自动调优

---

## 💡 关键成功因素

### 1. **数据质量**
- 高频 Tick 数据（毫秒级）
- 完整的历史数据（至少 3 年）
- 宏观数据对接（Wind、Tushare）

### 2. **回测框架**
- 避免未来函数（Look-Ahead Bias）
- 考虑滑点和手续费
- 分周期回测（牛市/熊市/震荡）

### 3. **风险控制**
- 单笔止损 < 2%
- 最大回撤 < 15%
- 夏普比率 > 1.5

### 4. **持续迭代**
- 每月评估因子有效性
- 淘汰失效因子
- 新增有效因子

---

## 📚 学习资源

### 书籍
1. **《量化投资：策略与技术》** - 丁鹏
2. **《机器学习与量化投资》** - 陈蓉
3. **《强化学习在金融中的应用》** - Stefan Jansen

### 开源项目
1. **Qlib**（微软）：AI 量化投资平台
2. **FinRL**：金融强化学习库
3. **Backtrader**：Python 回测框架

### 论文
1. **101 Formulaic Alphas** - WorldQuant
2. **Deep Reinforcement Learning for Trading** - JPMorgan
3. **Attention Is All You Need** - Transformer 在时间序列预测中的应用

---

## 🚨 风险提示

1. **过拟合风险**：模型在训练集表现好，实盘失效
2. **市场变化**：历史规律可能失效
3. **黑天鹅事件**：极端行情下模型崩溃
4. **技术债务**：系统复杂度指数增长

**建议**：
- 从简单开始，逐步迭代
- 保持模型可解释性
- 设置严格的风控机制
- 小资金实盘验证后再放大

---

**文档版本**：v1.0
**最后更新**：2026-03-28
**作者**：CEP 开发团队
