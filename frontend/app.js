const { createApp, ref, computed, onMounted, onUnmounted, watch } = Vue;
const api = window.CepApi;

createApp({
  setup() {
    const activeTab = ref('allocations');
    const rows = ref([]);
    const products = ref([]);
    const allowedAssets = ref([]);
    const backtestPresets = ref([]);
    const selectedStrategyId = ref('pbx_ma');
    const backtestDataSource = ref('tushare');
    const backtestTsCode = ref('000001.SZ');
    const backtestStartDate = ref('2024-01-01');
    const backtestEndDate = ref(new Date().toISOString().slice(0, 10));
    const backtestResult = ref(null);
    const stockSearchResults = ref([]);
    const stockSearchOpen = ref(false);
    const loading = ref(false);
    const backtestLoading = ref(false);
    const stockSearchLoading = ref(false);
    const dbOk = ref(true);
    const filterDate = ref('');
    const filterProduct = ref('');
    const showModal = ref(false);
    const showAssetModal = ref(false);
    const editingRow = ref(null);
    const saving = ref(false);
    const addingAsset = ref(false);
    const newAssetCode = ref('');
    const currentTime = ref('');
    const toast = ref({ show: false, message: '', type: 'success' });

    const form = ref({
      target_date: '',
      product_name: '',
      asset_code: '',
      weight_pct: '',
      algo_type: 'TWAP',
    });

    // ── computed ──
    const filteredRows = computed(() => {
      return rows.value.filter(r => {
        if (filterDate.value && r.target_date !== filterDate.value) return false;
        if (filterProduct.value && r.product_name !== filterProduct.value) return false;
        return true;
      });
    });

    const productCount = computed(() => new Set(rows.value.map(r => r.product_name)).size);
    const latestDate = computed(() => rows.value.length ? rows.value[0].target_date : null);
    const selectedPreset = computed(() => {
      return backtestPresets.value.find(p => p.id === selectedStrategyId.value) || null;
    });
    const selectedPresetParameters = computed(() => {
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

    // total pct for warning
    const totalPct = computed(() => {
      if (!form.value.product_name || !form.value.target_date) return 0;
      const others = rows.value.filter(r =>
        r.product_name === form.value.product_name &&
        r.target_date === form.value.target_date &&
        r.asset_code !== form.value.asset_code
      );
      const otherSum = others.reduce((s, r) => s + r.weight_ratio * 100, 0);
      return otherSum + (parseFloat(form.value.weight_pct) || 0);
    });
    const totalWarning = computed(() => totalPct.value > 100);

    // ── helpers ──
    function weightBarStyle(ratio) {
      const pct = Math.min(ratio * 100, 100);
      // Corporate blue gradient
      let bg = 'linear-gradient(90deg, #3b82f6, #2563eb)';
      return { width: pct + '%', background: bg };
    }

    function showToast(message, type = 'success') {
      toast.value = { show: true, message, type };
      setTimeout(() => { toast.value.show = false; }, 3000);
    }

    function formatMoney(value) {
      return Number(value || 0).toLocaleString('zh-CN', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
    }

    function equityBarHeight(equity) {
      const points = sampledEquityCurve.value;
      if (!points.length) return 4;
      const values = points.map(p => p.equity);
      const min = Math.min(...values);
      const max = Math.max(...values);
      if (max === min) return 50;
      return 12 + ((equity - min) / (max - min)) * 88;
    }

    function formatPresetSymbols(preset) {
      if (!preset) return '';
      if (Array.isArray(preset.symbols)) return preset.symbols.join(', ');
      return preset.symbol || '';
    }

    function presetSupportsDataSource(preset, dataSource) {
      if (!preset || !Array.isArray(preset.data_sources)) return true;
      return preset.data_sources.includes(dataSource);
    }

    function signalPrice(signal) {
      return Number(signal.payload.close || signal.payload.price || 0).toFixed(2);
    }

    function signalMetric(signal) {
      const payload = signal.payload || {};
      if (payload.score !== undefined) return Number(payload.score).toFixed(4);
      if (payload.pbx1 !== undefined) return Number(payload.pbx1).toFixed(2);
      return '-';
    }

    function signalReference(signal) {
      const payload = signal.payload || {};
      if (payload.winner) return payload.winner;
      if (payload.ma1 !== undefined) return Number(payload.ma1).toFixed(2);
      return payload.reason || '-';
    }

    function isTushareCode(value) {
      return /^(\d{6}|\d{6}\.(SZ|SH|BJ))$/i.test(value.trim());
    }

    function toTushareDate(value) {
      return String(value || '').replaceAll('-', '');
    }

    // ── API ──
    async function fetchData() {
      loading.value = true;
      try {
        const json = await api.fetchWeights();
        if (json.success) {
          rows.value = json.data || [];
          dbOk.value = true;
        } else {
          dbOk.value = false;
          showToast(json.message || '加载配置数据失败', 'error');
        }
      } catch (e) {
        dbOk.value = false;
        showToast('服务器连接断开: ' + e.message, 'error');
      } finally {
        loading.value = false;
      }
    }

    async function fetchProducts() {
      try {
        const json = await api.fetchProducts();
        products.value = json.data || [];
      } catch { }
    }

    async function fetchAssets() {
      try {
        const json = await api.fetchAssets();
        if (json.success) {
          allowedAssets.value = json.data || [];
        }
      } catch (e) {
        showToast('加载目标资产失败: ' + e.message, 'error');
      }
    }

    async function fetchBacktestPresets() {
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
      } catch (e) {
        showToast('加载回测策略失败: ' + e.message, 'error');
      }
    }

    async function runBacktest() {
      if (!selectedStrategyId.value) {
        showToast('请选择预设策略', 'error');
        return;
      }
      if (backtestDataSource.value === 'tushare' && (!backtestTsCode.value || !backtestStartDate.value || !backtestEndDate.value)) {
        showToast('请填写股票代码和日期范围', 'error');
        return;
      }
      if (backtestDataSource.value === 'tushare' && !isTushareCode(backtestTsCode.value)) {
        showToast('请选择搜索结果，或输入 6 位股票代码 / 完整 ts_code', 'error');
        return;
      }
      backtestLoading.value = true;
      try {
        const payload = {
          strategy_id: selectedStrategyId.value,
          data_source: backtestDataSource.value,
        };
        if (backtestDataSource.value === 'tushare') {
          payload.ts_code = backtestTsCode.value.trim().toUpperCase();
          payload.start_date = toTushareDate(backtestStartDate.value);
          payload.end_date = toTushareDate(backtestEndDate.value);
        }
        const json = await api.runBacktest(payload);
        if (json.success) {
          backtestResult.value = json.data;
          showToast('回测完成');
        } else {
          showToast(json.message || '回测失败', 'error');
        }
      } catch (e) {
        showToast('回测请求失败: ' + e.message, 'error');
      } finally {
        backtestLoading.value = false;
      }
    }

    async function searchStocks({ silent = false } = {}) {
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
      } catch (e) {
        if (requestId !== stockSearchRequestId) return;
        stockSearchResults.value = [];
        stockSearchOpen.value = false;
        if (!silent) showToast('股票搜索请求失败: ' + e.message, 'error');
      } finally {
        if (requestId === stockSearchRequestId) {
          stockSearchLoading.value = false;
        }
      }
    }

    function selectStock(stock) {
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

    async function addAsset() {
      const code = newAssetCode.value.trim().toUpperCase();
      if (!code) {
        showToast('请输入资产代码', 'error');
        return;
      }
      addingAsset.value = true;
      try {
        const json = await api.createAsset(code);
        if (json.success) {
          showToast(`已添加资产代码 ${code}`);
          newAssetCode.value = '';
          await fetchAssets();
        } else {
          showToast(json.message || '添加失败', 'error');
        }
      } catch (e) {
        showToast('请求异常: ' + e.message, 'error');
      } finally {
        addingAsset.value = false;
      }
    }

    async function deleteAsset(assetCode) {
      if (!confirm(`确认删除资产代码 ${assetCode}？删除后将无法在配置中使用该品种。`)) return;
      try {
        const json = await api.deleteAsset(assetCode);
        if (json.success) {
          showToast(`已删除资产代码 ${assetCode}`);
          await fetchAssets();
        } else {
          showToast(json.message || '删除失败', 'error');
        }
      } catch (e) {
        showToast('请求异常: ' + e.message, 'error');
      }
    }

    function openModal(row) {
      editingRow.value = row;
      if (row) {
        form.value = {
          target_date: row.target_date,
          product_name: row.product_name,
          asset_code: row.asset_code,
          weight_pct: (row.weight_ratio * 100).toFixed(4),
          algo_type: row.algo_type,
        };
      } else {
        // Find latest date to prefill if exists
        const d = filterDate.value || latestDate.value || new Date().toISOString().slice(0, 10);
        form.value = { target_date: d, product_name: filterProduct.value, asset_code: '', weight_pct: '', algo_type: 'TWAP' };
      }
      showModal.value = true;
    }

    function closeModal() {
      showModal.value = false;
      editingRow.value = null;
    }

    async function saveRow() {
      const { target_date, product_name, asset_code, weight_pct, algo_type } = form.value;
      if (!target_date || !product_name || !asset_code || weight_pct === '') {
        showToast('请将表单信息填写完整', 'error'); return;
      }
      saving.value = true;
      try {
        const json = await api.saveWeight({
          target_date,
          product_name,
          asset_code: asset_code.toUpperCase(),
          weight_ratio: parseFloat(weight_pct) / 100,
          algo_type,
        });
        if (json.success) {
          showToast('成功更新仓位配置');
          closeModal();
          await fetchData();
          await fetchProducts();
        } else {
          showToast(json.message || '配置记录保存失败', 'error');
        }
      } catch (e) {
        showToast('请求异常: ' + e.message, 'error');
      } finally {
        saving.value = false;
      }
    }

    async function deleteRow(row) {
      if (!confirm(`正在删除 ${row.product_name} / ${row.asset_code} 的记录，不可撤销，确认继续？`)) return;
      try {
        const json = await api.deleteWeight(row.id);
        if (json.success) {
          showToast('已删除记录');
          await fetchData();
          await fetchProducts();
        } else {
          showToast(json.message || '删除请求失败', 'error');
        }
      } catch (e) {
        showToast('请求异常: ' + e.message, 'error');
      }
    }

    // ── clock ──
    let clockTimer;
    let stockSearchTimer;
    let stockSearchRequestId = 0;
    let selectedStockCode = backtestTsCode.value;

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

    function updateClock() {
      const now = new Date();
      const options = { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false };
      currentTime.value = now.toLocaleString('zh-CN', options).replace(/\//g, '-');
    }

    onMounted(() => {
      fetchData();
      fetchProducts();
      fetchAssets();
      fetchBacktestPresets();
      updateClock();
      clockTimer = setInterval(updateClock, 1000);
    });

    onUnmounted(() => {
      clearInterval(clockTimer);
      clearTimeout(stockSearchTimer);
    });

    return {
      activeTab, rows, products, allowedAssets, backtestPresets, selectedStrategyId,
      backtestDataSource, backtestTsCode, backtestStartDate, backtestEndDate,
      backtestResult, stockSearchResults, stockSearchOpen,
      loading, backtestLoading, stockSearchLoading, dbOk, filterDate, filterProduct,
      showModal, showAssetModal, editingRow, saving, addingAsset, newAssetCode,
      form, currentTime, toast,
      filteredRows, productCount, latestDate, selectedPreset, selectedPresetParameters,
      sampledEquityCurve,
      totalPct, totalWarning,
      fetchData, openModal, closeModal, saveRow, deleteRow,
      fetchAssets, addAsset, deleteAsset, fetchBacktestPresets, runBacktest,
      searchStocks, selectStock, closeStockSearchSoon,
      weightBarStyle, formatMoney, equityBarHeight, formatPresetSymbols,
      presetSupportsDataSource, signalPrice, signalMetric, signalReference,
    };
  }
}).mount('#app');
