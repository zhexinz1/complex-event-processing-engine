const CepApi = {
  async requestJson(url, options = {}) {
    const response = await fetch(url, options);
    return response.json();
  },

  fetchWeights() {
    return this.requestJson('/api/weights');
  },

  fetchProducts() {
    return this.requestJson('/api/products');
  },

  fetchAssets() {
    return this.requestJson('/api/assets');
  },

  createAsset(assetCode) {
    return this.requestJson('/api/assets', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ asset_code: assetCode }),
    });
  },

  deleteAsset(assetCode) {
    return this.requestJson(`/api/assets/${assetCode}`, { method: 'DELETE' });
  },

  saveWeight(payload) {
    return this.requestJson('/api/weights', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },

  deleteWeight(recordId) {
    return this.requestJson(`/api/weights/${recordId}`, { method: 'DELETE' });
  },

  fetchBacktestPresets() {
    return this.requestJson('/api/backtests/presets');
  },

  searchStocks(keyword, limit = 20) {
    const params = new URLSearchParams({ q: keyword, limit: String(limit) });
    return this.requestJson(`/api/stocks/search?${params.toString()}`);
  },

  runBacktest(payload) {
    return this.requestJson('/api/backtests/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },
};

window.CepApi = CepApi;
