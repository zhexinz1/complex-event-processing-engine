import { computed, onMounted, ref } from 'vue';
import type {
  AllocationForm,
  AllocationRow,
  Asset,
  CepApiClient,
  ShowToast,
} from '../types';
import { errorMessage } from '../utils';

export function useAllocations(api: CepApiClient, showToast: ShowToast) {
  const rows = ref<AllocationRow[]>([]);
  const products = ref<string[]>([]);
  const allowedAssets = ref<Asset[]>([]);
  const loading = ref(false);
  const dbOk = ref(true);
  const filterDate = ref('');
  const filterProduct = ref('');
  const showModal = ref(false);
  const showAssetModal = ref(false);
  const editingRow = ref<AllocationRow | null>(null);
  const saving = ref(false);
  const addingAsset = ref(false);
  const newAssetCode = ref('');
  const form = ref<AllocationForm>({
    target_date: '',
    product_name: '',
    asset_code: '',
    weight_pct: '',
    algo_type: 'TWAP',
  });

  const filteredRows = computed(() => {
    return rows.value.filter((row) => {
      if (filterDate.value && row.target_date !== filterDate.value) return false;
      if (filterProduct.value && row.product_name !== filterProduct.value) return false;
      return true;
    });
  });

  const productCount = computed(() => new Set(rows.value.map((row) => row.product_name)).size);
  const latestDate = computed(() => (rows.value.length ? rows.value[0].target_date : null));
  const totalPct = computed(() => {
    if (!form.value.product_name || !form.value.target_date) return 0;
    const others = rows.value.filter((row) => (
      row.product_name === form.value.product_name &&
      row.target_date === form.value.target_date &&
      row.asset_code !== form.value.asset_code
    ));
    const otherSum = others.reduce((sum, row) => sum + row.weight_ratio * 100, 0);
    return otherSum + (parseFloat(form.value.weight_pct) || 0);
  });
  const totalWarning = computed(() => totalPct.value > 100);

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
    } catch (error: unknown) {
      dbOk.value = false;
      showToast(`服务器连接断开: ${errorMessage(error)}`, 'error');
    } finally {
      loading.value = false;
    }
  }

  async function fetchProducts() {
    try {
      const json = await api.fetchProducts();
      products.value = json.data || [];
    } catch {
      products.value = [];
    }
  }

  async function fetchAssets() {
    try {
      const json = await api.fetchAssets();
      if (json.success) {
        allowedAssets.value = json.data || [];
      }
    } catch (error: unknown) {
      showToast(`加载目标资产失败: ${errorMessage(error)}`, 'error');
    }
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
    } catch (error: unknown) {
      showToast(`请求异常: ${errorMessage(error)}`, 'error');
    } finally {
      addingAsset.value = false;
    }
  }

  async function deleteAsset(assetCode: string) {
    if (!confirm(`确认删除资产代码 ${assetCode}？删除后将无法在配置中使用该品种。`)) return;
    try {
      const json = await api.deleteAsset(assetCode);
      if (json.success) {
        showToast(`已删除资产代码 ${assetCode}`);
        await fetchAssets();
      } else {
        showToast(json.message || '删除失败', 'error');
      }
    } catch (error: unknown) {
      showToast(`请求异常: ${errorMessage(error)}`, 'error');
    }
  }

  function openModal(row: AllocationRow | null) {
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
      const date = filterDate.value || latestDate.value || new Date().toISOString().slice(0, 10);
      form.value = {
        target_date: date,
        product_name: filterProduct.value,
        asset_code: '',
        weight_pct: '',
        algo_type: 'TWAP',
      };
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
      showToast('请将表单信息填写完整', 'error');
      return;
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
    } catch (error: unknown) {
      showToast(`请求异常: ${errorMessage(error)}`, 'error');
    } finally {
      saving.value = false;
    }
  }

  async function deleteRow(row: AllocationRow) {
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
    } catch (error: unknown) {
      showToast(`请求异常: ${errorMessage(error)}`, 'error');
    }
  }

  onMounted(() => {
    fetchData();
    fetchProducts();
    fetchAssets();
  });

  return {
    rows,
    products,
    allowedAssets,
    loading,
    dbOk,
    filterDate,
    filterProduct,
    showModal,
    showAssetModal,
    editingRow,
    saving,
    addingAsset,
    newAssetCode,
    form,
    filteredRows,
    productCount,
    latestDate,
    totalPct,
    totalWarning,
    fetchData,
    fetchAssets,
    addAsset,
    deleteAsset,
    openModal,
    closeModal,
    saveRow,
    deleteRow,
  };
}
