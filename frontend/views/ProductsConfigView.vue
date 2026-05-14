<template>
  <div style="max-width:1400px; margin:0 auto; padding:24px;">
    <!-- Header -->
    <div class="card" style="padding:16px 20px; margin-bottom:16px; display:flex; justify-content:space-between; align-items:center;">
      <h2 style="font-size:20px; font-weight:700;">产品配置</h2>
      <button class="btn btn-primary" @click="openModal()">+ 添加产品</button>
    </div>

    <!-- Products List -->
    <div class="card" style="padding:20px;">
      <div v-if="alertMsg" :class="['alert-box', alertType]" style="margin-bottom:16px;">{{ alertMsg }}</div>
      
      <div v-if="loading" style="text-align:center; padding:40px; color:var(--text-muted);">加载中...</div>
      
      <div v-else>
        <div v-if="products.length === 0" style="text-align:center; padding:40px; color:var(--text-muted);">暂无产品数据</div>
        <table v-else>
          <thead>
            <tr>
              <th>产品名称</th>
              <th>杠杆倍数</th>
              <th>底仓资金账号</th>
              <th>状态</th>
              <th style="width:120px; text-align:center;">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="product in products" :key="product.product_name">
              <td><strong>{{ product.product_name }}</strong></td>
              <td>{{ product.leverage_ratio }}</td>
              <td><code>{{ product.fund_account || '—' }}</code></td>
              <td>
                <span :class="product.status === 'active' ? 'status-badge st-green' : 'status-badge st-gray'">
                  {{ product.status === 'active' ? '活跃' : '停用' }}
                </span>
              </td>
              <td style="text-align:center;">
                <button class="action-btn text-blue" @click="openModal(product)">编辑</button>
                <button class="action-btn text-red" @click="deleteProduct(product.product_name)" style="margin-left:8px;">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Add/Edit Modal -->
    <div v-if="showModal" class="modal-overlay" @click.self="closeModal">
      <div class="modal-content">
        <h3 style="margin-top:0; margin-bottom:20px; font-size:18px;">{{ isEdit ? '编辑产品' : '添加产品' }}</h3>
        
        <div class="form-group">
          <label>产品名称 <span style="color:#ef4444">*</span></label>
          <select v-if="!isEdit" v-model="form.product_name" class="inp" :disabled="loadingXt">
            <option value="" disabled>{{ loadingXt ? '正在加载迅投产品...' : '请选择产品' }}</option>
            <option v-for="p in availableXtProducts" :key="p.product_id" :value="p.product_name">
              {{ p.product_name }} ({{ p.product_code }})
            </option>
          </select>
          <input v-else v-model="form.product_name" type="text" class="inp" disabled />
          <small v-if="isEdit" style="color:var(--text-muted); display:block; margin-top:4px;">产品名称作为唯一标识，不可修改</small>
        </div>
        
        <div class="form-group">
          <label>杠杆倍数 <span style="color:#ef4444">*</span></label>
          <input v-model.number="form.leverage_ratio" type="number" class="inp" step="0.1" placeholder="例如: 2.0" />
        </div>
        
        <div class="form-group">
          <label>底仓资金账号 <span style="color:#ef4444">*</span></label>
          <input v-model="form.fund_account" type="text" class="inp" placeholder="用于迅投SDK下单" />
        </div>
        
        <div class="form-group">
          <label>迅投登录用户名</label>
          <input v-model="form.xt_username" type="text" class="inp" placeholder="选填" />
        </div>
        
        <div class="form-group">
          <label>迅投登录密码</label>
          <input v-model="form.xt_password" type="password" class="inp" placeholder="选填，若不修改请留空" />
        </div>

        <div style="display:flex; justify-content:flex-end; gap:12px; margin-top:24px;">
          <button class="btn btn-default" @click="closeModal" :disabled="saving">取消</button>
          <button class="btn btn-primary" @click="saveProduct" :disabled="saving">
            {{ saving ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { CepApi } from '../api';

const products = ref<any[]>([]);
const availableXtProducts = ref<any[]>([]);
const loading = ref(true);
const loadingXt = ref(false);
const alertMsg = ref('');
const alertType = ref<'success' | 'error'>('success');

const showModal = ref(false);
const isEdit = ref(false);
const saving = ref(false);

const form = ref({
  product_name: '',
  leverage_ratio: 1,
  fund_account: '',
  xt_username: '',
  xt_password: '',
});

async function loadProducts() {
  loading.value = true;
  try {
    const data = await CepApi.fetchProductList();
    if (data.success) {
      products.value = data.products || [];
    } else {
      alertMsg.value = '加载失败: ' + (data.message || '');
      alertType.value = 'error';
    }
  } catch (e: any) {
    alertMsg.value = '请求异常: ' + e.message;
    alertType.value = 'error';
  }
  loading.value = false;
}

async function loadXtProducts() {
  if (availableXtProducts.value.length > 0) return;
  loadingXt.value = true;
  try {
    const data: any = await CepApi.fetchXtCache();
    if (data.success) {
      availableXtProducts.value = data.products || [];
    }
  } catch (e) {
    console.error('加载迅投产品失败:', e);
  }
  loadingXt.value = false;
}

function openModal(product?: any) {
  loadXtProducts();
  if (product) {
    isEdit.value = true;
    form.value = {
      product_name: product.product_name,
      leverage_ratio: parseFloat(product.leverage_ratio || '1'),
      fund_account: product.fund_account || '',
      xt_username: product.xt_username || '',
      xt_password: product.xt_password || '',
    };
  } else {
    isEdit.value = false;
    form.value = {
      product_name: '',
      leverage_ratio: 1,
      fund_account: '',
      xt_username: '',
      xt_password: '',
    };
  }
  showModal.value = true;
}

function closeModal() {
  showModal.value = false;
}

async function saveProduct() {
  if (!form.value.product_name.trim()) {
    alert('产品名称不能为空');
    return;
  }
  if (!form.value.fund_account.trim()) {
    alert('底仓资金账号不能为空');
    return;
  }
  
  saving.value = true;
  try {
    let data;
    if (isEdit.value) {
      data = await CepApi.updateProduct(form.value);
    } else {
      data = await CepApi.addProduct(form.value);
    }
    
    if (data.success) {
      closeModal();
      await loadProducts();
      alertMsg.value = isEdit.value ? '产品修改成功' : '产品添加成功';
      alertType.value = 'success';
      setTimeout(() => alertMsg.value = '', 3000);
    } else {
      alert('保存失败: ' + (data.message || ''));
    }
  } catch (e: any) {
    alert('请求异常: ' + e.message);
  }
  saving.value = false;
}

async function deleteProduct(productName: string) {
  if (!confirm(`确定要停用产品 "${productName}" 吗？此操作不会删除历史数据，但会在列表中隐藏。`)) return;
  
  try {
    // We soft-delete by setting status to inactive
    const data = await CepApi.updateProduct({ product_name: productName, status: 'inactive' });
    if (data.success) {
      await loadProducts();
      alertMsg.value = `产品 ${productName} 已停用`;
      alertType.value = 'success';
      setTimeout(() => alertMsg.value = '', 3000);
    } else {
      alert('停用失败: ' + (data.message || ''));
    }
  } catch (e: any) {
    alert('请求异常: ' + e.message);
  }
}

onMounted(() => {
  loadProducts();
});
</script>

<style scoped>
.alert-box { padding: 12px 16px; border-radius: 6px; font-size: 14px; }
.alert-box.success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
.alert-box.error { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }

.status-badge { display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: 500; }
.st-green { background: #d4edda; color: #155724; }
.st-gray { background: #e2e3e5; color: #383d41; }

.action-btn { background: none; border: none; cursor: pointer; font-size: 13px; font-weight: 500; padding: 4px 8px; border-radius: 4px; transition: background 0.2s; }
.action-btn:hover { background: #f3f4f6; }
.text-blue { color: #2563eb; }
.text-red { color: #dc2626; }

/* Modal styles */
.modal-overlay {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
}
.modal-content {
  background: white; border-radius: 8px; padding: 24px;
  width: 480px; max-width: 90vw;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
}
.form-group { margin-bottom: 16px; }
.form-group label { display: block; margin-bottom: 6px; font-size: 13px; font-weight: 500; color: #374151; }
.form-group .inp { width: 100%; box-sizing: border-box; }
.form-group .inp:disabled { background: #f3f4f6; color: #9ca3af; cursor: not-allowed; }
</style>
