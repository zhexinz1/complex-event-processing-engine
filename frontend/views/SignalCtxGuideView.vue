<template>
  <main class="ctx-guide-page">
    <section class="ctx-guide-shell">
      <div class="ctx-guide-header">
        <div>
          <p class="ctx-guide-eyebrow">Signal Runtime Reference</p>
          <h1>`ctx` 可用字段</h1>
          <p class="ctx-guide-summary">
            {{ schema?.summary || '用户信号里的 self.ctx 是 LocalContext。' }}
          </p>
        </div>
        <router-link to="/signals" class="btn btn-default">返回信号与回测</router-link>
      </div>

      <section class="card ctx-guide-section">
        <h2>最常用的字段</h2>
        <p v-if="loading" class="ctx-guide-note">正在加载 Python 侧 ctx 元数据...</p>
        <p v-else-if="errorText" class="ctx-guide-error">{{ errorText }}</p>
        <div class="ctx-table-wrap">
          <table>
            <thead>
              <tr>
                <th>字段</th>
                <th>类型</th>
                <th>说明</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in schema?.core_fields || []" :key="row.name">
                <td><code>{{ row.name }}</code></td>
                <td>{{ row.type }}</td>
                <td>{{ row.description }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="card ctx-guide-section">
        <h2>默认技术指标</h2>
        <div class="ctx-table-wrap">
          <table>
            <thead>
              <tr>
                <th>字段</th>
                <th>返回值</th>
                <th>说明</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in schema?.indicator_fields || []" :key="row.name">
                <td><code>{{ row.name }}</code></td>
                <td>{{ row.type }}</td>
                <td>{{ row.description }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="ctx-guide-note">
          这些指标通过惰性计算获得。第一次访问时才会计算，新 Bar 到来后缓存会自动失效并重算。
        </p>
      </section>

      <section class="card ctx-guide-section">
        <h2>Bar 透传字段</h2>
        <div class="ctx-table-wrap">
          <table>
            <thead>
              <tr>
                <th>字段</th>
                <th>类型</th>
                <th>来源</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in schema?.bar_fields || []" :key="row.name">
                <td><code>{{ row.name }}</code></td>
                <td>{{ row.type }}</td>
                <td>{{ row.description }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="ctx-guide-note">
          这些值来自最近一根 <code>BarEvent</code>。也就是说 <code>ctx.close</code> 与当前传入的 <code>bar.close</code> 在大多数场景下是一致的。
        </p>
      </section>

      <section class="card ctx-guide-section">
        <h2>Tick 透传字段</h2>
        <div class="ctx-table-wrap">
          <table>
            <thead>
              <tr>
                <th>字段</th>
                <th>类型</th>
                <th>来源</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in schema?.tick_fields || []" :key="row.name">
                <td><code>{{ row.name }}</code></td>
                <td>{{ row.type }}</td>
                <td>{{ row.description }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="ctx-guide-note">
          这些值只会在运行链路注入了最新 Tick 时可用。
        </p>
      </section>

      <section class="card ctx-guide-section">
        <h2>示例</h2>
        <pre class="ctx-code"><code>{{ schema?.example_code || '' }}</code></pre>
      </section>

      <section class="card ctx-guide-section">
        <h2>注意事项</h2>
        <ul class="ctx-guide-list">
          <li v-for="note in schema?.notes || []" :key="note">{{ note }}</li>
        </ul>
      </section>
    </section>
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { CepApi } from '../api';
import type { SignalCtxSchema } from '../types';
import { errorMessage } from '../utils';

const schema = ref<SignalCtxSchema | null>(null);
const loading = ref(true);
const errorText = ref('');

async function loadSchema() {
  loading.value = true;
  errorText.value = '';
  try {
    const json = await CepApi.fetchSignalCtxSchema();
    if (json.success && json.data) {
      schema.value = json.data;
    } else {
      errorText.value = json.message || '未能加载 ctx 元数据';
    }
  } catch (error: unknown) {
    errorText.value = `加载失败: ${errorMessage(error)}`;
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  loadSchema();
});
</script>

<style scoped>
.ctx-guide-page {
  padding: 24px;
}

.ctx-guide-shell {
  display: grid;
  gap: 24px;
}

.ctx-guide-header {
  align-items: flex-start;
  display: flex;
  gap: 16px;
  justify-content: space-between;
}

.ctx-guide-eyebrow {
  color: var(--primary);
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 6px;
}

.ctx-guide-header h1 {
  font-size: 28px;
  margin-bottom: 8px;
}

.ctx-guide-summary {
  color: var(--text-muted);
  max-width: 880px;
}

.ctx-guide-section {
  padding: 20px;
}

.ctx-guide-section h2 {
  font-size: 18px;
  margin-bottom: 14px;
}

.ctx-table-wrap {
  overflow-x: auto;
}

.ctx-guide-note {
  color: var(--text-muted);
  font-size: 13px;
  margin-top: 12px;
}

.ctx-guide-error {
  color: var(--danger);
  font-size: 13px;
  margin-bottom: 12px;
}

.ctx-code {
  background: #111827;
  border: 1px solid #1f2937;
  border-radius: 8px;
  color: #e5e7eb;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 13px;
  line-height: 1.6;
  overflow-x: auto;
  padding: 16px;
  white-space: pre-wrap;
}

.ctx-guide-list {
  color: var(--text-main);
  display: grid;
  gap: 8px;
  padding-left: 18px;
}

code {
  font-family: "SFMono-Regular", Consolas, monospace;
}

@media (max-width: 900px) {
  .ctx-guide-header {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
