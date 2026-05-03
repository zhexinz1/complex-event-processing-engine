<template>
  <section class="backtest-panel">
    <div class="card backtest-card">
      <div class="backtest-header">
        <div class="backtest-heading">
          <h2 class="backtest-title">策略回测</h2>
          <p class="backtest-subtitle">
            选择一个预设策略，使用 mock、Tushare 或主连历史库运行事件驱动回测。
          </p>
        </div>
        <div class="backtest-actions">
          <div class="panel-switcher">
            <button type="button" class="btn" :class="activePanel === 'run' ? 'btn-primary' : 'btn-default'"
              @click="activePanel = 'run'">
              运行回测
            </button>
            <button type="button" class="btn" :class="activePanel === 'history' ? 'btn-primary' : 'btn-default'"
              @click="activePanel = 'history'; $emit('refresh-history')">
              历史记录
            </button>
          </div>
          <button v-if="activePanel === 'run'" class="btn btn-primary" @click="$emit('run')" :disabled="backtestLoading || !selectedStrategyId">
            {{ backtestLoading ? '回测运行中...' : '运行回测' }}
          </button>
          <button v-else class="btn btn-default" @click="$emit('refresh-history')" :disabled="backtestHistoryLoading">
            {{ backtestHistoryLoading ? '刷新中...' : '刷新' }}
          </button>
        </div>
      </div>

      <div v-if="activePanel === 'run'" class="backtest-grid">
        <div>
          <label class="field-label">预设策略</label>
          <select :value="selectedStrategyId" class="inp"
            @change="$emit('update:selectedStrategyId', ($event.target as HTMLSelectElement).value)">
            <option v-for="preset in backtestPresets" :key="preset.id" :value="preset.id">
              {{ preset.name }}
            </option>
          </select>
          <div v-if="selectedPreset" class="preset-summary">
            <div class="muted-copy">
              {{ selectedPreset.description }}
            </div>
            <div class="preset-stat-grid">
              <div>
                <div class="stat-label">数据集</div>
                <div class="stat-text">{{ selectedPreset.dataset }}</div>
              </div>
              <div>
                <div class="stat-label">标的</div>
                <div class="stat-text">{{ formatPresetSymbols(selectedPreset) }}</div>
              </div>
              <div v-for="param in selectedPresetParameters" :key="param.label">
                <div class="stat-label">{{ param.label }}</div>
                <div class="stat-text">{{ param.value }}</div>
              </div>
            </div>
          </div>

          <div class="form-stack">
            <div>
              <label class="field-label">行情数据源</label>
              <select :value="backtestDataSource" class="inp"
                @change="$emit('update:backtestDataSource', ($event.target as HTMLSelectElement).value)">
                <option value="mock">内置 mock 数据</option>
                <option value="tushare" :disabled="!presetSupportsDataSource(selectedPreset, 'tushare')">
                  Tushare A股日线
                </option>
                <option value="adjusted_main_contract" :disabled="!presetSupportsDataSource(selectedPreset, 'adjusted_main_contract')">
                  复权主连 1 分钟库
                </option>
              </select>
            </div>

            <div v-if="backtestDataSource === 'tushare' || backtestDataSource === 'adjusted_main_contract'" class="form-stack compact">
              <div>
                <label class="field-label">{{ backtestDataSource === 'tushare' ? '股票代码' : '主连代码' }}</label>
                <div class="stock-combobox">
                  <input type="text" :value="backtestTsCode" class="inp symbol-input" placeholder="输入代码、简称或公司名"
                    @input="$emit('update:backtestTsCode', ($event.target as HTMLInputElement).value)"
                    @focus="backtestDataSource === 'tushare' && $emit('update:stockSearchOpen', stockSearchResults.length > 0)" @blur="$emit('close-stock-search')"
                    @keyup.enter="backtestDataSource === 'tushare' && $emit('search-stocks')" />
                  <div v-if="stockSearchLoading" class="stock-combobox-status">搜索中...</div>
                  <div v-if="backtestDataSource === 'tushare' && stockSearchOpen" class="stock-combobox-menu">
                    <button v-for="stock in stockSearchResults" :key="stock.ts_code" type="button"
                      class="stock-combobox-option" @mousedown.prevent="$emit('select-stock', stock)">
                      <span class="stock-combobox-row">
                        <span class="stock-combobox-title">{{ stock.ts_code }} · {{ stock.name }}</span>
                        <span class="stock-combobox-meta">{{ stock.exchange }} {{ stock.board }}</span>
                      </span>
                      <span class="stock-combobox-detail">
                        {{ stock.industry || stock.full_name || stock.english_name || '暂无详情' }}
                      </span>
                    </button>
                  </div>
                </div>
              </div>
              <div class="date-grid">
                <div>
                  <label class="field-label">开始日期</label>
                  <input type="date" :value="backtestStartDate" class="inp"
                    @input="$emit('update:backtestStartDate', ($event.target as HTMLInputElement).value)" />
                </div>
                <div>
                  <label class="field-label">结束日期</label>
                  <input type="date" :value="backtestEndDate" class="inp"
                    @input="$emit('update:backtestEndDate', ($event.target as HTMLInputElement).value)" />
                </div>
              </div>
              <div class="field-help">
                {{ backtestDataSource === 'tushare'
                  ? '使用 Tushare daily 未复权日线。需要本机已配置可访问 daily 接口的 token。'
                  : '直接读取本地 adjusted_main_contract CSV 历史数据，代码示例：AU9999.XSGE、IF9999.CCFX。' }}
              </div>
            </div>
          </div>
        </div>

        <div>
          <div v-if="!backtestResult" class="empty-panel">
            运行回测后查看信号、成交和权益结果
          </div>

          <div v-else class="result-stack">
            <div class="metric-grid">
              <div class="stat-block">
                <span class="stat-label">最终权益</span>
                <span class="stat-value">{{ formatMoney(backtestResult.final_equity) }}</span>
              </div>
              <div class="stat-block">
                <span class="stat-label">已实现盈亏</span>
                <span class="stat-value"
                  :style="{ color: backtestResult.realized_pnl >= 0 ? 'var(--success)' : 'var(--danger)' }">
                  {{ formatMoney(backtestResult.realized_pnl) }}
                </span>
              </div>
              <div class="stat-block">
                <span class="stat-label">信号数</span>
                <span class="stat-value">{{ backtestResult.signals.length }}</span>
              </div>
              <div class="stat-block">
                <span class="stat-label">成交数</span>
                <span class="stat-value">{{ backtestResult.trades.length }}</span>
              </div>
            </div>

            <div class="mini-chart">
              <div v-for="(point, idx) in sampledEquityCurve" :key="idx" class="chart-bar"
                :style="{ height: equityBarHeight(point.equity) + '%' }" :title="formatMoney(point.equity)">
              </div>
            </div>

            <div class="table-shell">
              <table>
                <thead>
                  <tr>
                    <th class="type-column">类型</th>
                    <th>时间</th>
                    <th>标的</th>
                    <th>方向</th>
                    <th>价格</th>
                    <th>指标</th>
                    <th>参考</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="signal in backtestResult.signals" :key="signal.timestamp + signal.payload.side">
                    <td>Signal</td>
                    <td class="muted-cell">{{ signal.payload.bar_time }}</td>
                    <td>{{ signal.symbol }}</td>
                    <td>
                      <span class="badge" :class="signal.payload.side === 'BUY' ? 'badge-vwap' : 'badge-twap'">
                        {{ signal.payload.side }}
                      </span>
                    </td>
                    <td>{{ signalPrice(signal) }}</td>
                    <td>{{ signalMetric(signal) }}</td>
                    <td>{{ signalReference(signal) }}</td>
                  </tr>
                  <tr v-if="backtestResult.signals.length === 0">
                    <td colspan="7" class="empty-cell">没有触发信号</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      <div v-else class="backtest-history-grid history-panel">
        <div class="table-shell">
          <table>
            <thead>
              <tr>
                <th>时间</th>
                <th>标的</th>
                <th>最终权益</th>
                <th>成交</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in backtestHistory" :key="item.id" class="history-row"
                :class="{ selected: selectedHistory?.id === item.id }"
                @click="$emit('select-history', item.id)">
                <td>
                  <div class="history-date">{{ formatDateTime(item.created_at) }}</div>
                  <div class="history-file">{{ item.filename }}</div>
                </td>
                <td>{{ formatSymbols(item.symbols) }}</td>
                <td>{{ formatMoney(item.final_equity) }}</td>
                <td>{{ item.trade_count }}</td>
              </tr>
              <tr v-if="!backtestHistory.length">
                <td colspan="4" class="empty-cell">
                  {{ backtestHistoryLoading ? '正在加载历史记录...' : '还没有历史回测日志' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-if="selectedHistory" class="history-detail">
          <div class="metric-grid">
            <div class="stat-block">
              <span class="stat-label">最终权益</span>
              <span class="stat-value">{{ formatMoney(selectedHistory.final_equity) }}</span>
            </div>
            <div class="stat-block">
              <span class="stat-label">总盈亏</span>
              <span class="stat-value">{{ formatMoney(historyTotalPnl(selectedHistory, selectedHistoryDetail)) }}</span>
            </div>
            <div class="stat-block">
              <span class="stat-label">已实现盈亏（平仓）</span>
              <span class="stat-value" :style="{ color: selectedHistory.realized_pnl >= 0 ? 'var(--success)' : 'var(--danger)' }">
                {{ formatMoney(selectedHistory.realized_pnl) }}
              </span>
            </div>
            <div class="stat-block">
              <span class="stat-label">未实现盈亏（持仓）</span>
              <span class="stat-value">{{ formatMoney(historyMetric(selectedHistory.unrealized_pnl)) }}</span>
            </div>
            <div class="stat-block">
              <span class="stat-label">期末现金</span>
              <span class="stat-value">{{ formatMoney(historyMetric(selectedHistory.final_cash)) }}</span>
            </div>
            <div class="stat-block">
              <span class="stat-label">持仓市值</span>
              <span class="stat-value">{{ formatMoney(historyMetric(selectedHistory.final_market_value)) }}</span>
            </div>
            <div class="stat-block">
              <span class="stat-label">信号数</span>
              <span class="stat-value">{{ selectedHistory.signal_count }}</span>
            </div>
            <div class="stat-block">
              <span class="stat-label">成交数</span>
              <span class="stat-value">{{ selectedHistory.trade_count }}</span>
            </div>
            <div class="stat-block">
              <span class="stat-label">未平仓</span>
              <span class="stat-value">{{ historyOpenPositionCount(selectedHistory, selectedHistoryDetail) }}</span>
            </div>
          </div>

          <div class="history-meta-grid">
            <div>
              <div class="stat-label">区间开始</div>
              <div class="stat-text">{{ formatDateTime(selectedHistory.first_timestamp) }}</div>
            </div>
            <div>
              <div class="stat-label">区间结束</div>
              <div class="stat-text">{{ formatDateTime(selectedHistory.last_timestamp) }}</div>
            </div>
            <div>
              <div class="stat-label">日志路径</div>
              <div class="log-path">{{ selectedHistory.path }}</div>
            </div>
          </div>

          <div v-if="historyEquityCurve(selectedHistoryDetail).length" class="mini-chart">
            <div
              v-for="(point, idx) in historyEquityCurve(selectedHistoryDetail)"
              :key="idx"
              class="chart-bar"
              :style="{ height: historyEquityBarHeight(selectedHistoryDetail, point.equity) + '%' }"
              :title="formatMoney(point.equity)"
            >
            </div>
          </div>

          <div class="table-shell">
            <table>
              <thead>
                <tr>
                  <th>时间</th>
                  <th>标的</th>
                  <th>方向</th>
                  <th>数量</th>
                  <th>价格</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(trade, idx) in latestTrades(selectedHistoryDetail)" :key="idx">
                  <td class="muted-cell">{{ formatDateTime(asString(trade.timestamp)) }}</td>
                  <td>{{ trade.symbol }}</td>
                  <td>{{ trade.side }}</td>
                  <td>{{ trade.quantity }}</td>
                  <td>{{ trade.price }}</td>
                </tr>
                <tr v-if="latestTrades(selectedHistoryDetail).length === 0">
                  <td colspan="5" class="empty-cell">
                    {{ backtestHistoryDetailLoading ? '正在加载成交详情...' : '没有成交记录' }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div v-else class="empty-panel">
          选择一条历史记录查看详情
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import type {
  BacktestHistoryDetail,
  BacktestHistoryItem,
  BacktestPreset,
  BacktestResult,
  EquityPoint,
  PresetParameter,
  StockSearchResult,
} from '../types';
import {
  formatMoney,
  formatPresetSymbols,
  presetSupportsDataSource,
  signalMetric,
  signalPrice,
  signalReference,
} from '../utils';

defineProps<{
  backtestPresets: BacktestPreset[];
  selectedStrategyId: string;
  backtestDataSource: string;
  backtestTsCode: string;
  backtestStartDate: string;
  backtestEndDate: string;
  backtestResult: BacktestResult | null;
  backtestHistory: BacktestHistoryItem[];
  selectedHistory: BacktestHistoryItem | null;
  selectedHistoryDetail: BacktestHistoryDetail | null;
  stockSearchResults: StockSearchResult[];
  stockSearchOpen: boolean;
  backtestLoading: boolean;
  backtestHistoryLoading: boolean;
  backtestHistoryDetailLoading: boolean;
  stockSearchLoading: boolean;
  selectedPreset: BacktestPreset | null;
  selectedPresetParameters: PresetParameter[];
  sampledEquityCurve: EquityPoint[];
  equityBarHeight: (equity: number) => number;
}>();

const activePanel = ref<'run' | 'history'>('run');

defineEmits<{
  'update:selectedStrategyId': [value: string];
  'update:backtestDataSource': [value: string];
  'update:backtestTsCode': [value: string];
  'update:backtestStartDate': [value: string];
  'update:backtestEndDate': [value: string];
  'update:stockSearchOpen': [value: boolean];
  run: [];
  'refresh-history': [];
  'select-history': [id: string];
  'search-stocks': [];
  'select-stock': [stock: StockSearchResult];
  'close-stock-search': [];
}>();

function formatDateTime(value?: string | null) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function formatSymbols(symbols: string[]) {
  if (!symbols.length) return '-';
  if (symbols.length <= 2) return symbols.join(', ');
  return `${symbols.slice(0, 2).join(', ')} +${symbols.length - 2}`;
}

function asString(value: unknown) {
  return typeof value === 'string' ? value : undefined;
}

function latestTrades(item: BacktestHistoryDetail | null) {
  if (!item) return [];
  return [...(item.data.trades || [])].slice(-8).reverse();
}

function historyMetric(value: number | null | undefined) {
  return Number(value || 0);
}

function historyTotalPnl(item: BacktestHistoryItem, detail: BacktestHistoryDetail | null) {
  const initialCash = historyMetric(detail?.data.initial_cash ?? item.initial_cash ?? 1_000_000);
  return historyMetric(detail?.data.final_equity ?? item.final_equity) - initialCash;
}

function historyOpenPositionCount(item: BacktestHistoryItem, detail: BacktestHistoryDetail | null) {
  const positions = detail?.data.positions;
  if (positions) return positions.filter((position) => position.quantity !== 0).length;
  return item.position_count;
}

function historyEquityCurve(item: BacktestHistoryDetail | null) {
  const points = item?.data.equity_curve || [];
  if (points.length <= 48) return points;
  const step = Math.ceil(points.length / 48);
  return points.filter((_, index) => index % step === 0 || index === points.length - 1);
}

function historyEquityBarHeight(item: BacktestHistoryDetail | null, equity: number) {
  const points = historyEquityCurve(item);
  if (!points.length) return 4;
  const values = points.map((point) => point.equity);
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (max === min) return 50;
  return 12 + ((equity - min) / (max - min)) * 88;
}
</script>

<style scoped>
.backtest-panel {
  margin: 0 24px 32px;
}

.backtest-card {
  border-radius: 0 0 8px 8px;
  padding: 24px;
}

.backtest-header {
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
  justify-content: space-between;
}

.backtest-heading {
  max-width: 640px;
}

.backtest-title {
  font-size: 18px;
  font-weight: 700;
  margin: 0 0 6px;
}

.backtest-subtitle,
.muted-copy {
  color: var(--text-muted);
  font-size: 13px;
  line-height: 1.6;
  margin: 0;
}

.backtest-actions {
  align-items: flex-start;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.panel-switcher {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  display: inline-flex;
  overflow: hidden;
}

.panel-switcher .btn {
  border: 0;
  border-radius: 0;
  box-shadow: none;
}

.field-label {
  color: var(--text-main);
  display: block;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 6px;
}

.preset-summary {
  background: #f9fafb;
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-top: 16px;
  padding: 16px;
}

.preset-stat-grid,
.date-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: 1fr 1fr;
}

.preset-stat-grid {
  margin-top: 14px;
}

.stat-text {
  font-size: 14px;
  font-weight: 600;
}

.form-stack,
.result-stack,
.history-detail {
  display: flex;
  flex-direction: column;
}

.form-stack {
  gap: 14px;
  margin-top: 18px;
}

.form-stack.compact {
  margin-top: 0;
}

.symbol-input {
  text-transform: uppercase;
}

.field-help {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
}

.empty-panel {
  align-items: center;
  background: #f9fafb;
  border: 1px dashed #d1d5db;
  border-radius: 8px;
  color: var(--text-muted);
  display: flex;
  justify-content: center;
  min-height: 220px;
}

.result-stack {
  gap: 20px;
}

.table-shell {
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow-x: auto;
}

.type-column {
  width: 120px;
}

.muted-cell {
  color: var(--text-muted);
  font-size: 13px;
}

.empty-cell {
  color: var(--text-muted);
  text-align: center;
}

.history-panel {
  margin-top: 24px;
}

.history-row {
  cursor: pointer;
}

.history-row.selected {
  background: #eff6ff;
}

.history-date {
  font-weight: 600;
}

.history-file,
.log-path {
  color: var(--text-muted);
  font-size: 12px;
}

.history-detail {
  gap: 18px;
}

.history-meta-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(3, 1fr);
}

.log-path {
  word-break: break-all;
}

@media (max-width: 720px) {
  .backtest-panel {
    margin: 0 12px 24px;
  }

  .backtest-card {
    padding: 16px;
  }

  .date-grid,
  .history-meta-grid,
  .preset-stat-grid {
    grid-template-columns: 1fr;
  }
}
</style>
