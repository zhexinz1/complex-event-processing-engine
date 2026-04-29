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
          :class="{ active: signal.id === selectedSignalId }"
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
              <router-link class="btn btn-default" to="/signals/ctx-guide">ctx 字段说明</router-link>
              <button class="btn btn-default" :disabled="busy || !activeTab" @click="validateSignal">校验</button>
              <button class="btn btn-primary" :disabled="busy || !activeTab" @click="saveSignal">保存</button>
              <button
                class="btn btn-default"
                :disabled="busy || !activeTab?.draft.id"
                @click="toggleSignal"
              >
                {{ activeTab?.draft.status === 'enabled' ? '停用' : '启用' }}
              </button>
            </div>
          </div>

          <div v-if="tabs.length" class="editor-tabs">
            <button
              v-for="tab in tabs"
              :key="tab.key"
              class="editor-tab"
              :class="{ active: tab.key === activeTabKey }"
              @click="setActiveTab(tab.key)"
            >
              <span class="editor-tab-label">{{ tab.draft.name || '未命名信号' }}</span>
              <span
                v-if="tabs.length > 1"
                class="editor-tab-close"
                @click.stop="closeTab(tab.key)"
              >
                x
              </span>
            </button>
          </div>

          <div v-if="activeTab" class="form-grid">
            <label>
              <span>名称</span>
              <input v-model="activeTab.draft.name" class="inp" />
            </label>
            <label>
              <span>创建人</span>
              <input v-model="activeTab.draft.created_by" class="inp" />
            </label>
          </div>

          <textarea
            v-if="activeTab"
            v-model="activeTab.draft.source_code"
            class="code-editor"
            spellcheck="false"
          />

          <div v-if="activeTab && activeTab.diagnostics.length" class="diagnostics">
            <div
              v-for="item in activeTab.diagnostics"
              :key="item.message + item.line"
              class="diagnostic-row"
            >
              <strong>{{ item.level }}</strong>
              <span>{{ item.line ? `L${item.line}: ` : '' }}{{ item.message }}</span>
            </div>
          </div>
        </div>

        <div class="card backtest-panel">
          <div class="panel-head">
            <div>
              <h2>回测验证</h2>
              <p>{{ activeTab?.backtestResult ? `${activeTab.backtestResult.signals.length} 个信号` : '使用 mock、Tushare 或主连历史库验证' }}</p>
            </div>
            <button class="btn btn-primary" :disabled="busy || !activeTab" @click="runBacktest">运行回测</button>
          </div>
          <div class="form-grid compact">
            <label>
              <span>数据源</span>
              <select v-model="backtestDataSource" class="inp">
                <option value="mock">mock</option>
                <option value="tushare">tushare</option>
                <option value="adjusted_main_contract">adjusted_main_contract</option>
              </select>
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

          <div v-if="activeTab?.backtestResult" class="metric-grid signal-metrics">
            <div class="stat-block">
              <span class="stat-label">最终权益</span>
              <span class="stat-value">{{ activeTab.backtestResult.final_equity.toFixed(2) }}</span>
            </div>
            <div class="stat-block">
              <span class="stat-label">已实现盈亏</span>
              <span class="stat-value">{{ activeTab.backtestResult.realized_pnl.toFixed(2) }}</span>
            </div>
            <div class="stat-block">
              <span class="stat-label">信号数</span>
              <span class="stat-value">{{ activeTab.backtestResult.signals.length }}</span>
            </div>
            <div class="stat-block">
              <span class="stat-label">成交数</span>
              <span class="stat-value">{{ activeTab.backtestResult.trades.length }}</span>
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
import { computed, onMounted, onUnmounted, ref } from 'vue';
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
const liveSignals = ref<LiveSignal[]>([]);
const liveConnected = ref(false);
const busy = ref(false);
const backtestDataSource = ref('mock');
const backtestStartDate = ref('2024-01-01');
const backtestEndDate = ref(new Date().toISOString().slice(0, 10));
let eventSource: EventSource | null = null;

interface SignalEditorTab {
  key: string;
  signalId?: number;
  draft: UserSignalDefinition;
  diagnostics: SignalDiagnostic[];
  backtestResult: (BacktestResult & { diagnostics?: SignalDiagnostic[] }) | null;
}

const tabs = ref<SignalEditorTab[]>([]);
const activeTabKey = ref('');
let draftCounter = 0;

function createDefaultSignal(): UserSignalDefinition {
  return {
    id: undefined,
    name: '沪金RSI超卖',
    symbols: ['au2506'],
    bar_freq: '1m',
    source_code: sampleCode,
    status: 'disabled',
    created_by: 'research',
  };
}

function cloneSignal(signal: UserSignalDefinition): UserSignalDefinition {
  return {
    ...signal,
    symbols: [...signal.symbols],
  };
}

function createDraftTab(signal?: UserSignalDefinition): SignalEditorTab {
  const draft = signal ? cloneSignal(signal) : createDefaultSignal();
  draftCounter += 1;
  return {
    key: signal?.id ? `signal-${signal.id}` : `draft-${draftCounter}`,
    signalId: signal?.id,
    draft,
    diagnostics: [],
    backtestResult: null,
  };
}

const activeTab = computed(() => tabs.value.find((tab) => tab.key === activeTabKey.value) || null);
const selectedSignalId = computed(() => activeTab.value?.signalId);

const sampledEquity = computed(() => {
  const points = activeTab.value?.backtestResult?.equity_curve || [];
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

function deriveSignalConfig(draft: UserSignalDefinition) {
  const source = draft.source_code;

  const symbolsMatch = source.match(/symbols\s*=\s*\[(.*?)\]/s);
  const symbols = symbolsMatch
    ? Array.from(symbolsMatch[1].matchAll(/["']([^"'\\]+)["']/g), (match) => match[1].trim()).filter(Boolean)
    : draft.symbols;

  const barFreqMatch = source.match(/bar_freq\s*=\s*["']([^"'\\]+)["']/);
  const barFreq = barFreqMatch?.[1]?.trim() || draft.bar_freq;

  return {
    symbols,
    bar_freq: barFreq,
  };
}

function newSignal() {
  const tab = createDraftTab();
  tabs.value.push(tab);
  activeTabKey.value = tab.key;
}

function openSignalTab(signal: UserSignalDefinition) {
  const existing = tabs.value.find((tab) => tab.signalId === signal.id);
  if (existing) {
    activeTabKey.value = existing.key;
    return;
  }
  const tab = createDraftTab(signal);
  tabs.value.push(tab);
  activeTabKey.value = tab.key;
}

function setActiveTab(tabKey: string) {
  activeTabKey.value = tabKey;
}

function closeTab(tabKey: string) {
  const tabIndex = tabs.value.findIndex((tab) => tab.key === tabKey);
  if (tabIndex === -1) return;
  const wasActive = activeTabKey.value === tabKey;
  tabs.value.splice(tabIndex, 1);
  if (!tabs.value.length) {
    const nextTab = createDraftTab();
    tabs.value.push(nextTab);
    activeTabKey.value = nextTab.key;
    return;
  }
  if (wasActive) {
    const fallbackIndex = Math.max(0, tabIndex - 1);
    activeTabKey.value = tabs.value[fallbackIndex].key;
  }
}

function selectSignal(signal: UserSignalDefinition) {
  openSignalTab(signal);
}

async function fetchSignals() {
  const json = await CepApi.fetchUserSignals();
  if (json.success) {
    signals.value = json.data || [];
    if (!tabs.value.length) {
      if (signals.value.length) {
        openSignalTab(signals.value[0]);
      } else {
        newSignal();
      }
    }
  } else {
    showToast(json.message || '加载信号失败', 'error');
  }
}

async function validateSignal() {
  if (!activeTab.value) return;
  busy.value = true;
  try {
    const json = await CepApi.validateUserSignal(activeTab.value.draft.source_code);
    activeTab.value.diagnostics = json.diagnostics || [];
    showToast(json.message || '校验通过', json.success ? 'success' : 'error');
  } catch (error: unknown) {
    showToast(`校验失败: ${errorMessage(error)}`, 'error');
  } finally {
    busy.value = false;
  }
}

async function saveSignal() {
  if (!activeTab.value) return;
  busy.value = true;
  try {
    const derivedConfig = deriveSignalConfig(activeTab.value.draft);
    const payload = {
      ...activeTab.value.draft,
      ...derivedConfig,
      symbols: [...derivedConfig.symbols],
    };
    const json = activeTab.value.draft.id
      ? await CepApi.updateUserSignal(activeTab.value.draft.id, payload)
      : await CepApi.createUserSignal(payload);
    if (json.success && json.data) {
      activeTab.value.signalId = json.data.id;
      activeTab.value.draft = cloneSignal(json.data);
      activeTab.value.key = `signal-${json.data.id}`;
      activeTab.value.diagnostics = [];
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
  if (!activeTab.value?.draft.id) return;
  const nextStatus = activeTab.value.draft.status === 'enabled' ? 'disabled' : 'enabled';
  busy.value = true;
  try {
    const json = await CepApi.updateUserSignalStatus(activeTab.value.draft.id, nextStatus);
    if (json.success) {
      activeTab.value.draft.status = nextStatus;
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
  if (!activeTab.value) return;
  busy.value = true;
  try {
    const derivedConfig = deriveSignalConfig(activeTab.value.draft);
    const json = await CepApi.runUserSignalBacktest({
      signal_id: activeTab.value.draft.id,
      source_code: activeTab.value.draft.id ? undefined : activeTab.value.draft.source_code,
      data_source: backtestDataSource.value,
      symbols: derivedConfig.symbols,
      start_date: toTushareDate(backtestStartDate.value),
      end_date: toTushareDate(backtestEndDate.value),
    });
    if (json.success) {
      activeTab.value.backtestResult = json.data || null;
      activeTab.value.diagnostics = json.data?.diagnostics || [];
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

.editor-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  overflow-x: auto;
  padding-bottom: 4px;
}

.editor-tab {
  align-items: center;
  background: #f3f4f6;
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text-main);
  cursor: pointer;
  display: inline-flex;
  flex: 0 0 auto;
  gap: 10px;
  max-width: 220px;
  padding: 8px 12px;
}

.editor-tab.active {
  background: #eff6ff;
  border-color: var(--primary);
}

.editor-tab-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.editor-tab-close {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1;
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
  grid-template-columns: repeat(2, minmax(180px, 1fr));
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
