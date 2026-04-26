<template>
  <main class="signals-page">
    <section class="signals-layout">
      <aside class="card signal-list">
        <div class="panel-head">
          <div>
            <h2>信号定义</h2>
            <p>{{ signals.length }} 个研究员信号</p>
          </div>
          <button class="btn btn-default" @click="newSignal">新建</button>
        </div>
        <button
          v-for="signal in signals"
          :key="signal.id"
          class="signal-row"
          :class="{ active: signal.id === selectedSignal?.id }"
          @click="selectSignal(signal)"
        >
          <span class="signal-title">{{ signal.name }}</span>
          <span class="signal-meta">{{ signal.symbols.join(', ') }} · {{ signal.bar_freq }}</span>
          <span class="badge" :class="signal.status === 'enabled' ? 'badge-vwap' : 'badge-twap'">
            {{ signal.status === 'enabled' ? '监控中' : '已停用' }}
          </span>
        </button>
      </aside>

      <section class="signal-workspace">
        <div class="card editor-panel">
          <div class="panel-head">
            <div>
              <h2>Python 信号</h2>
              <p>按 Signal 合约返回 dict 或 None</p>
            </div>
            <div class="button-row">
              <button class="btn btn-default" :disabled="busy" @click="validateSignal">校验</button>
              <button class="btn btn-primary" :disabled="busy" @click="saveSignal">保存</button>
              <button
                class="btn btn-default"
                :disabled="busy || !form.id"
                @click="toggleSignal"
              >
                {{ form.status === 'enabled' ? '停用' : '启用' }}
              </button>
            </div>
          </div>

          <div class="form-grid">
            <label>
              <span>名称</span>
              <input v-model="form.name" class="inp" />
            </label>
            <label>
              <span>标的</span>
              <input v-model="symbolsText" class="inp" placeholder="au2506, ag2506" />
            </label>
            <label>
              <span>K线周期</span>
              <input v-model="form.bar_freq" class="inp" />
            </label>
            <label>
              <span>创建人</span>
              <input v-model="form.created_by" class="inp" />
            </label>
          </div>

          <textarea v-model="form.source_code" class="code-editor" spellcheck="false" />

          <div v-if="diagnostics.length" class="diagnostics">
            <div v-for="item in diagnostics" :key="item.message + item.line" class="diagnostic-row">
              <strong>{{ item.level }}</strong>
              <span>{{ item.line ? `L${item.line}: ` : '' }}{{ item.message }}</span>
            </div>
          </div>
        </div>

        <div class="card backtest-panel">
          <div class="panel-head">
            <div>
              <h2>回测验证</h2>
              <p>{{ backtestResult ? `${backtestResult.signals.length} 个信号` : '使用 mock 或 Tushare 数据验证' }}</p>
            </div>
            <button class="btn btn-primary" :disabled="busy" @click="runBacktest">运行回测</button>
          </div>
          <div class="form-grid compact">
            <label>
              <span>数据源</span>
              <select v-model="backtestDataSource" class="inp">
                <option value="mock">mock</option>
                <option value="tushare">tushare</option>
              </select>
            </label>
            <label>
              <span>Tushare代码</span>
              <input v-model="backtestTsCode" class="inp" />
            </label>
            <label>
              <span>开始日期</span>
              <input v-model="backtestStartDate" type="date" class="inp" />
            </label>
            <label>
              <span>结束日期</span>
              <input v-model="backtestEndDate" type="date" class="inp" />
            </label>
          </div>

          <div v-if="backtestResult" class="metric-grid signal-metrics">
            <div class="stat-block">
              <span class="stat-label">最终权益</span>
              <span class="stat-value">{{ backtestResult.final_equity.toFixed(2) }}</span>
            </div>
            <div class="stat-block">
              <span class="stat-label">已实现盈亏</span>
              <span class="stat-value">{{ backtestResult.realized_pnl.toFixed(2) }}</span>
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

          <div v-if="sampledEquity.length" class="mini-chart">
            <div
              v-for="point in sampledEquity"
              :key="point.timestamp || String(point.equity)"
              class="chart-bar"
              :style="{ height: `${equityBarHeight(point.equity)}%` }"
            />
          </div>
        </div>

        <div class="card live-panel">
          <div class="panel-head">
            <div>
              <h2>盘中信号</h2>
              <p>{{ liveConnected ? 'SSE 已连接' : '等待连接' }}</p>
            </div>
            <button class="btn btn-default" @click="fetchRecentLiveSignals">刷新</button>
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>时间</th>
                  <th>标的</th>
                  <th>方向</th>
                  <th>价格</th>
                  <th>原因</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="signal in liveSignals" :key="signal.event_id">
                  <td>{{ signal.timestamp }}</td>
                  <td>{{ signal.symbol }}</td>
                  <td>{{ signal.payload.side || 'ALERT' }}</td>
                  <td>{{ signal.payload.price || signal.payload.close || '-' }}</td>
                  <td>{{ signal.payload.reason || signal.rule_id }}</td>
                </tr>
                <tr v-if="liveSignals.length === 0">
                  <td colspan="5" style="color:var(--text-muted);">暂无盘中信号</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue';
import { CepApi } from '../api';
import type {
  BacktestResult,
  EquityPoint,
  LiveSignal,
  SignalDiagnostic,
  UserSignalDefinition,
} from '../types';
import { errorMessage, toTushareDate } from '../utils';
import { useToast } from '../composables/useToast';

const sampleCode = `class Signal:
    name = "沪金RSI超卖"
    symbols = ["au2506"]
    bar_freq = "1m"

    def __init__(self, ctx):
        self.ctx = ctx

    def on_bar(self, bar):
        if self.ctx.rsi is not None and self.ctx.rsi < 30:
            return {
                "side": "BUY",
                "reason": "rsi_oversold",
                "price": bar.close,
            }
        return None
`;

const { showToast } = useToast();
const signals = ref<UserSignalDefinition[]>([]);
const selectedSignal = ref<UserSignalDefinition | null>(null);
const diagnostics = ref<SignalDiagnostic[]>([]);
const backtestResult = ref<(BacktestResult & { diagnostics?: SignalDiagnostic[] }) | null>(null);
const liveSignals = ref<LiveSignal[]>([]);
const liveConnected = ref(false);
const busy = ref(false);
const backtestDataSource = ref('mock');
const backtestTsCode = ref('000001.SZ');
const backtestStartDate = ref('2024-01-01');
const backtestEndDate = ref(new Date().toISOString().slice(0, 10));
let eventSource: EventSource | null = null;

const form = reactive<UserSignalDefinition>({
  name: '沪金RSI超卖',
  symbols: ['au2506'],
  bar_freq: '1m',
  source_code: sampleCode,
  status: 'disabled',
  created_by: 'research',
});

const symbolsText = computed({
  get: () => form.symbols.join(', '),
  set: (value: string) => {
    form.symbols = value.split(',').map((item) => item.trim()).filter(Boolean);
  },
});

const sampledEquity = computed(() => {
  const points = backtestResult.value?.equity_curve || [];
  if (points.length <= 48) return points;
  const step = Math.ceil(points.length / 48);
  return points.filter((_, index) => index % step === 0 || index === points.length - 1);
});

function equityBarHeight(equity: number) {
  const points: EquityPoint[] = sampledEquity.value;
  if (!points.length) return 4;
  const values = points.map((point) => point.equity);
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (max === min) return 50;
  return 12 + ((equity - min) / (max - min)) * 88;
}

function applySignal(signal: UserSignalDefinition) {
  Object.assign(form, {
    ...signal,
    symbols: [...signal.symbols],
  });
  selectedSignal.value = signal;
  diagnostics.value = [];
}

function newSignal() {
  Object.assign(form, {
    id: undefined,
    name: '沪金RSI超卖',
    symbols: ['au2506'],
    bar_freq: '1m',
    source_code: sampleCode,
    status: 'disabled',
    created_by: 'research',
  });
  selectedSignal.value = null;
  diagnostics.value = [];
  backtestResult.value = null;
}

function selectSignal(signal: UserSignalDefinition) {
  applySignal(signal);
}

async function fetchSignals() {
  const json = await CepApi.fetchUserSignals();
  if (json.success) {
    signals.value = json.data || [];
    if (!selectedSignal.value && signals.value.length) applySignal(signals.value[0]);
  } else {
    showToast(json.message || '加载信号失败', 'error');
  }
}

async function validateSignal() {
  busy.value = true;
  try {
    const json = await CepApi.validateUserSignal(form.source_code);
    diagnostics.value = json.diagnostics || [];
    showToast(json.message || '校验通过', json.success ? 'success' : 'error');
  } catch (error: unknown) {
    showToast(`校验失败: ${errorMessage(error)}`, 'error');
  } finally {
    busy.value = false;
  }
}

async function saveSignal() {
  busy.value = true;
  try {
    const payload = { ...form, symbols: [...form.symbols] };
    const json = form.id
      ? await CepApi.updateUserSignal(form.id, payload)
      : await CepApi.createUserSignal(payload);
    if (json.success && json.data) {
      applySignal(json.data);
      await fetchSignals();
      showToast(json.message || '信号已保存');
    } else {
      showToast(json.message || '保存失败', 'error');
    }
  } catch (error: unknown) {
    showToast(`保存失败: ${errorMessage(error)}`, 'error');
  } finally {
    busy.value = false;
  }
}

async function toggleSignal() {
  if (!form.id) return;
  const nextStatus = form.status === 'enabled' ? 'disabled' : 'enabled';
  busy.value = true;
  try {
    const json = await CepApi.updateUserSignalStatus(form.id, nextStatus);
    if (json.success) {
      form.status = nextStatus;
      await fetchSignals();
      showToast(json.message || '状态已更新');
    } else {
      showToast(json.message || '状态更新失败', 'error');
    }
  } finally {
    busy.value = false;
  }
}

async function runBacktest() {
  busy.value = true;
  try {
    const json = await CepApi.runUserSignalBacktest({
      signal_id: form.id,
      source_code: form.id ? undefined : form.source_code,
      data_source: backtestDataSource.value,
      ts_code: backtestTsCode.value,
      symbols: form.symbols,
      start_date: toTushareDate(backtestStartDate.value),
      end_date: toTushareDate(backtestEndDate.value),
    });
    if (json.success) {
      backtestResult.value = json.data || null;
      diagnostics.value = json.data?.diagnostics || [];
      showToast('回测完成');
    } else {
      showToast(json.message || '回测失败', 'error');
    }
  } catch (error: unknown) {
    showToast(`回测失败: ${errorMessage(error)}`, 'error');
  } finally {
    busy.value = false;
  }
}

async function fetchRecentLiveSignals() {
  const json = await CepApi.fetchRecentLiveSignals();
  if (json.success) liveSignals.value = json.data || [];
}

function connectLiveStream() {
  eventSource = new EventSource('/api/signals/live/stream');
  eventSource.onopen = () => {
    liveConnected.value = true;
  };
  eventSource.onerror = () => {
    liveConnected.value = false;
  };
  eventSource.onmessage = (event) => {
    const signal = JSON.parse(event.data) as LiveSignal;
    liveSignals.value = [signal, ...liveSignals.value].slice(0, 100);
  };
}

onMounted(() => {
  fetchSignals();
  fetchRecentLiveSignals();
  connectLiveStream();
});

onUnmounted(() => {
  eventSource?.close();
});
</script>

<style scoped>
.signals-page {
  padding: 24px;
}

.signals-layout {
  display: grid;
  gap: 24px;
  grid-template-columns: 320px 1fr;
}

.signal-list,
.editor-panel,
.backtest-panel,
.live-panel {
  padding: 20px;
}

.signal-workspace {
  display: grid;
  gap: 24px;
}

.panel-head {
  align-items: center;
  display: flex;
  gap: 16px;
  justify-content: space-between;
  margin-bottom: 16px;
}

.panel-head h2 {
  font-size: 18px;
  font-weight: 700;
}

.panel-head p {
  color: var(--text-muted);
  font-size: 13px;
  margin-top: 4px;
}

.button-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}

.signal-row {
  background: #ffffff;
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: pointer;
  display: grid;
  gap: 6px;
  margin-top: 10px;
  padding: 12px;
  text-align: left;
  width: 100%;
}

.signal-row.active {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}

.signal-title {
  font-size: 14px;
  font-weight: 700;
}

.signal-meta {
  color: var(--text-muted);
  font-size: 12px;
}

.form-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(4, minmax(140px, 1fr));
  margin-bottom: 16px;
}

.form-grid.compact {
  grid-template-columns: repeat(4, minmax(120px, 1fr));
}

label span {
  color: var(--text-muted);
  display: block;
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 6px;
}

.code-editor {
  background: #111827;
  border: 1px solid #1f2937;
  border-radius: 8px;
  color: #e5e7eb;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 13px;
  line-height: 1.6;
  min-height: 360px;
  outline: none;
  padding: 16px;
  resize: vertical;
  width: 100%;
}

.diagnostics {
  display: grid;
  gap: 8px;
  margin-top: 12px;
}

.diagnostic-row {
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 6px;
  color: #991b1b;
  display: flex;
  gap: 10px;
  padding: 8px 10px;
}

.signal-metrics {
  margin: 16px 0;
}

.table-wrap {
  overflow-x: auto;
}

@media (max-width: 1100px) {
  .signals-layout,
  .form-grid,
  .form-grid.compact {
    grid-template-columns: 1fr;
  }
}
</style>
