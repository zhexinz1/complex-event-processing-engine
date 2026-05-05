import { computed, onMounted, onUnmounted, ref, watch, markRaw } from 'vue';
import type {
  BacktestHistoryDetail,
  BacktestPreset,
  BacktestHistoryItem,
  BacktestRequest,
  BacktestResult,
  CepApiClient,
  PresetParameter,
  ShowToast,
  StockSearchResult,
} from '../types';
import {
  errorMessage,
  isTushareCode,
  presetSupportsDataSource,
  toTushareDate,
} from '../utils';

interface UseBacktestOptions {
  enabled?: boolean;
}

export function useBacktest(api: CepApiClient, showToast: ShowToast, options: UseBacktestOptions = {}) {
  const enabled = options.enabled ?? true;
  const backtestPresets = ref<BacktestPreset[]>([]);
  const selectedStrategyId = ref('pbx_ma');
  const backtestDataSource = ref('tushare');
  const backtestTsCode = ref('000001.SZ');
  const backtestStartDate = ref('2024-01-01');
  const backtestEndDate = ref(new Date().toISOString().slice(0, 10));
  const backtestResult = ref<BacktestResult | null>(null);
  const backtestHistory = ref<BacktestHistoryItem[]>([]);
  const selectedHistoryId = ref('');
  const selectedHistoryDetail = ref<BacktestHistoryDetail | null>(null);
  const stockSearchResults = ref<StockSearchResult[]>([]);
  const stockSearchOpen = ref(false);
  const backtestLoading = ref(false);
  const backtestHistoryLoading = ref(false);
  const backtestHistoryDetailLoading = ref(false);
  const stockSearchLoading = ref(false);

  let stockSearchTimer: ReturnType<typeof setTimeout> | undefined;
  let stockSearchRequestId = 0;
  let historyDetailRequestId = 0;
  let selectedStockCode = backtestTsCode.value;

  const selectedPreset = computed(() => {
    return backtestPresets.value.find((preset) => preset.id === selectedStrategyId.value) || null;
  });

  const selectedPresetParameters = computed<PresetParameter[]>(() => {
    const preset = selectedPreset.value;
    if (!preset) return [];
    if (Array.isArray(preset.parameter_summary)) return preset.parameter_summary;
    return Object.entries(preset.parameters || {}).map(([label, value]) => ({ label, value }));
  });

  const sampledEquityCurve = computed(() => {
    if (!backtestResult.value || !backtestResult.value.equity_curve) return [];
    const points = backtestResult.value.equity_curve;
    if (points.length <= 48) return points;
    const step = Math.ceil(points.length / 48);
    return points.filter((_, index) => index % step === 0 || index === points.length - 1);
  });

  const selectedHistory = computed(() => {
    if (!selectedHistoryId.value) return null;
    return backtestHistory.value.find((item) => item.id === selectedHistoryId.value) || null;
  });

  function equityBarHeight(equity: number) {
    const points = sampledEquityCurve.value;
    if (!points.length) return 4;
    const values = points.map((point) => point.equity);
    const min = Math.min(...values);
    const max = Math.max(...values);
    if (max === min) return 50;
    return 12 + ((equity - min) / (max - min)) * 88;
  }

  async function fetchBacktestPresets() {
    if (!enabled) return;
    try {
      const json = await api.fetchBacktestPresets();
      if (json.success) {
        backtestPresets.value = json.data || [];
        if (!selectedStrategyId.value && backtestPresets.value.length) {
          selectedStrategyId.value = backtestPresets.value[0].id;
        }
      } else {
        showToast(json.message || '加载回测策略失败', 'error');
      }
    } catch (error: unknown) {
      showToast(`加载回测策略失败: ${errorMessage(error)}`, 'error');
    }
  }

  async function fetchBacktestHistory() {
    if (!enabled) return;
    backtestHistoryLoading.value = true;
    try {
      const json = await api.fetchBacktestHistory(100);
      if (json.success) {
        backtestHistory.value = json.data || [];
        if (selectedHistoryId.value && !backtestHistory.value.some((item) => item.id === selectedHistoryId.value)) {
          selectedHistoryId.value = '';
          selectedHistoryDetail.value = null;
        }
      } else {
        showToast(json.message || '加载回测历史失败', 'error');
      }
    } catch (error: unknown) {
      showToast(`加载回测历史失败: ${errorMessage(error)}`, 'error');
    } finally {
      backtestHistoryLoading.value = false;
    }
  }

  async function fetchBacktestHistoryDetail(id: string) {
    if (!enabled || !id) {
      selectedHistoryDetail.value = null;
      return;
    }
    backtestHistoryDetailLoading.value = true;
    if (selectedHistoryDetail.value?.id !== id) {
      selectedHistoryDetail.value = null;
    }
    const requestId = ++historyDetailRequestId;
    try {
      const json = await api.fetchBacktestHistoryDetail(id, 48);
      if (requestId !== historyDetailRequestId) return;
      if (json.success) {
        selectedHistoryDetail.value = json.data ? markRaw(json.data) : null;
      } else {
        selectedHistoryDetail.value = null;
        showToast(json.message || '加载回测详情失败', 'error');
      }
    } catch (error: unknown) {
      if (requestId !== historyDetailRequestId) return;
      selectedHistoryDetail.value = null;
      showToast(`加载回测详情失败: ${errorMessage(error)}`, 'error');
    } finally {
      if (requestId === historyDetailRequestId) {
        backtestHistoryDetailLoading.value = false;
      }
    }
  }

  function selectBacktestHistory(id: string) {
    if (selectedHistoryId.value === id) {
      fetchBacktestHistoryDetail(id);
      return;
    }
    selectedHistoryId.value = id;
  }

  async function runBacktest() {
    if (!enabled) return;
    if (!selectedStrategyId.value) {
      showToast('请选择预设策略', 'error');
      return;
    }
    if (
      (backtestDataSource.value === 'tushare' || backtestDataSource.value === 'adjusted_main_contract')
      && (!backtestTsCode.value || !backtestStartDate.value || !backtestEndDate.value)
    ) {
      showToast('请填写标的代码和日期范围', 'error');
      return;
    }
    if (backtestDataSource.value === 'tushare' && !isTushareCode(backtestTsCode.value)) {
      showToast('请选择搜索结果，或输入 6 位股票代码 / 完整 ts_code', 'error');
      return;
    }

    backtestLoading.value = true;
    try {
      const payload: BacktestRequest = {
        strategy_id: selectedStrategyId.value,
        data_source: backtestDataSource.value,
      };
      if (backtestDataSource.value === 'tushare' || backtestDataSource.value === 'adjusted_main_contract') {
        payload.ts_code = backtestTsCode.value.trim().toUpperCase();
        payload.start_date = toTushareDate(backtestStartDate.value);
        payload.end_date = toTushareDate(backtestEndDate.value);
      }
      const json = await api.runBacktest(payload);
      if (json.success) {
        backtestResult.value = json.data ? markRaw(json.data) : null;
        fetchBacktestHistory();
        showToast('回测完成');
      } else {
        showToast(json.message || '回测失败', 'error');
      }
    } catch (error: unknown) {
      showToast(`回测请求失败: ${errorMessage(error)}`, 'error');
    } finally {
      backtestLoading.value = false;
    }
  }

  async function searchStocks({ silent = false }: { silent?: boolean } = {}) {
    if (!enabled) return;
    const keyword = backtestTsCode.value.trim();
    if (!keyword) {
      stockSearchResults.value = [];
      stockSearchOpen.value = false;
      if (!silent) showToast('请输入股票代码或名称关键词', 'error');
      return;
    }

    stockSearchLoading.value = true;
    const requestId = ++stockSearchRequestId;
    try {
      const json = await api.searchStocks(keyword, 20);
      if (requestId !== stockSearchRequestId) return;
      if (json.success) {
        stockSearchResults.value = json.data || [];
        stockSearchOpen.value = stockSearchResults.value.length > 0;
        if (!silent && stockSearchResults.value.length === 0) {
          showToast('没有找到匹配股票', 'error');
        }
      } else {
        stockSearchResults.value = [];
        stockSearchOpen.value = false;
        if (!silent) showToast(json.message || '股票搜索失败', 'error');
      }
    } catch (error: unknown) {
      if (requestId !== stockSearchRequestId) return;
      stockSearchResults.value = [];
      stockSearchOpen.value = false;
      if (!silent) showToast(`股票搜索请求失败: ${errorMessage(error)}`, 'error');
    } finally {
      if (requestId === stockSearchRequestId) {
        stockSearchLoading.value = false;
      }
    }
  }

  function selectStock(stock: StockSearchResult) {
    stockSearchRequestId += 1;
    stockSearchLoading.value = false;
    selectedStockCode = stock.ts_code;
    backtestTsCode.value = stock.ts_code;
    stockSearchResults.value = [];
    stockSearchOpen.value = false;
  }

  function closeStockSearchSoon() {
    setTimeout(() => {
      stockSearchOpen.value = false;
    }, 160);
  }

  if (enabled) {
    watch([backtestTsCode, backtestDataSource], ([query, dataSource]) => {
      clearTimeout(stockSearchTimer);
      if (dataSource !== 'tushare') {
        stockSearchRequestId += 1;
        stockSearchLoading.value = false;
        stockSearchResults.value = [];
        stockSearchOpen.value = false;
        return;
      }

      const keyword = query.trim();
      if (keyword === selectedStockCode) return;
      selectedStockCode = '';
      if (keyword.length < 2) {
        stockSearchRequestId += 1;
        stockSearchLoading.value = false;
        stockSearchResults.value = [];
        stockSearchOpen.value = false;
        return;
      }

      stockSearchTimer = setTimeout(() => {
        searchStocks({ silent: true });
      }, 350);
    });

    watch(selectedStrategyId, () => {
      if (!presetSupportsDataSource(selectedPreset.value, backtestDataSource.value)) {
        backtestDataSource.value = 'mock';
      }
    });

    watch(selectedHistoryId, (id) => {
      fetchBacktestHistoryDetail(id);
    });

    onMounted(() => {
      fetchBacktestPresets();
      fetchBacktestHistory();
    });
  }

  onUnmounted(() => {
    clearTimeout(stockSearchTimer);
  });

  return {
    backtestPresets,
    selectedStrategyId,
    backtestDataSource,
    backtestTsCode,
    backtestStartDate,
    backtestEndDate,
    backtestResult,
    backtestHistory,
    selectedHistoryId,
    selectedHistoryDetail,
    stockSearchResults,
    stockSearchOpen,
    backtestLoading,
    backtestHistoryLoading,
    backtestHistoryDetailLoading,
    stockSearchLoading,
    selectedPreset,
    selectedPresetParameters,
    selectedHistory,
    sampledEquityCurve,
    fetchBacktestPresets,
    fetchBacktestHistory,
    fetchBacktestHistoryDetail,
    selectBacktestHistory,
    runBacktest,
    searchStocks,
    selectStock,
    closeStockSearchSoon,
    equityBarHeight,
  };
}
