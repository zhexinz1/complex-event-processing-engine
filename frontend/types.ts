export type ToastType = 'success' | 'error';

export type AppTab = string;

export type ShowToast = (message: string, type?: ToastType) => void;

export interface ApiResponse<T = unknown> {
  success: boolean;
  data?: T;
  message?: string;
  total?: number;
  id?: number;
}

export interface AllocationRow {
  id: number;
  target_date: string;
  product_name: string;
  asset_code: string;
  weight_ratio: number;
  created_at?: string;
  updated_at?: string;
}

export interface Asset {
  asset_code: string;
  created_at?: string;
}

export interface AllocationForm {
  target_date: string;
  product_name: string;
  asset_code: string;
  weight_pct: string;
}

export interface SaveWeightPayload {
  target_date: string;
  product_name: string;
  asset_code: string;
  weight_ratio: number;
}

export interface PresetParameter {
  label: string;
  value: unknown;
}

export interface BacktestPreset {
  id: string;
  name: string;
  description: string;
  dataset: string;
  symbol?: string;
  symbols?: string[];
  data_sources?: string[];
  parameter_summary?: PresetParameter[];
  parameters?: Record<string, unknown>;
}

export interface EquityPoint {
  timestamp?: string;
  equity: number;
}

export interface BacktestSignalPayload {
  bar_time?: string;
  side?: string;
  close?: number;
  price?: number;
  score?: number;
  pbx1?: number;
  ma1?: number;
  winner?: string;
  reason?: string;
  [key: string]: unknown;
}

export interface BacktestSignal {
  timestamp: string;
  symbol: string;
  payload: BacktestSignalPayload;
}

export interface BacktestTrade {
  [key: string]: unknown;
}

export interface BacktestPosition {
  symbol: string;
  quantity: number;
  avg_price: number;
  realized_pnl: number;
}

export interface PerformanceMetrics {
  total_return_pct: number;
  annualized_return_pct: number;
  sharpe_ratio: number;
  max_drawdown: number;
  max_drawdown_pct: number;
  win_rate_pct: number | null;
  round_trip_trades: number;
  trade_count: number;
  trading_days: number;
}

export interface BacktestResult {
  initial_cash?: number;
  final_cash?: number;
  final_market_value?: number;
  final_equity: number;
  realized_pnl: number;
  unrealized_pnl?: number;
  equity_curve: EquityPoint[];
  signals: BacktestSignal[];
  trades: BacktestTrade[];
  positions?: BacktestPosition[];
  performance?: PerformanceMetrics;
  total_signals?: number;
  total_trades?: number;
}

export interface BacktestHistoryItem {
  id: string;
  filename: string;
  created_at: string;
  modified_at: string;
  path: string;
  market_events_processed: number;
  initial_cash: number;
  final_cash: number;
  final_market_value: number;
  final_equity: number;
  realized_pnl: number;
  unrealized_pnl: number;
  signal_count: number;
  order_count: number;
  trade_count: number;
  position_count: number;
  symbols: string[];
  equity_curve_count?: number;
  first_timestamp?: string | null;
  last_timestamp?: string | null;
}

export interface BacktestHistoryDetail extends BacktestHistoryItem {
  data: BacktestResult & {
    orders?: Record<string, unknown>[];
    positions?: BacktestPosition[];
  };
}

export interface StockSearchResult {
  ts_code: string;
  name: string;
  exchange?: string;
  board?: string;
  industry?: string;
  full_name?: string;
  english_name?: string;
}

export interface BacktestRequest {
  strategy_id: string;
  data_source: string;
  ts_code?: string;
  start_date?: string;
  end_date?: string;
  write_trade_log?: boolean;
}

export interface SignalDiagnostic {
  level: string;
  message: string;
  line?: number;
  symbol?: string;
  timestamp?: string;
}

export interface UserSignalDefinition {
  id?: number;
  name: string;
  symbols: string[];
  bar_freq: string;
  source_code: string;
  status: 'enabled' | 'disabled';
  created_by: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface UserSignalBacktestRequest {
  signal_id?: number;
  source_code?: string;
  data_source: string;
  backtest_freq?: string;
  ts_code?: string;
  symbols?: string[];
  start_date?: string;
  end_date?: string;
  initial_cash?: number;
  commission_rate?: number;
  write_trade_log?: boolean;
  execution_timing?: 'current_bar' | 'next_bar';
}

export interface LiveSignal {
  event_id: string;
  timestamp: string;
  symbol: string;
  source: string;
  rule_id: string;
  signal_type: string;
  payload: BacktestSignalPayload;
}

export interface SignalCtxFieldDoc {
  name: string;
  type: string;
  description: string;
}

export interface SignalCtxSchema {
  summary: string;
  core_fields: SignalCtxFieldDoc[];
  indicator_fields: SignalCtxFieldDoc[];
  bar_fields: SignalCtxFieldDoc[];
  tick_fields: SignalCtxFieldDoc[];
  notes: string[];
  example_code: string;
}

// ---- Fund Inflow ----

export interface ProductInfo {
  product_name: string;
  leverage_ratio: string | number;
  fund_account: string;
  xt_username?: string;
  xt_password?: string;
  status?: string;
}

export interface FundInflow {
  batch_id: string;
  product_name: string;
  net_inflow: string;
  leverage_ratio: string;
  leveraged_amount: string;
  input_by: string;
  input_at: string;
  confirmed_by: string;
  confirmed_at: string;
  status: string;
}

// ---- Orders ----

export interface PendingOrder {
  id: number;
  batch_id: string;
  asset_code: string;
  price: string;
  target_market_value: string;
  contract_multiplier: string;
  final_quantity: number;
  previous_fractional: string;
  direction: string;
  status: string;
  xt_status: string;
  xt_error_msg: string;
  xt_traded_volume: number;
  xt_traded_price: string;
  order_price_type: string;
  xt_order_id?: number;
  created_at: string;
  // 前端运行时临时字段（非数据库字段）
  user_limit_price?: number;
}

export interface PendingOrdersResponse {
  success: boolean;
  batch_id: string;
  product_name: string;
  net_inflow: string;
  leverage_ratio: string;
  leveraged_amount: string;
  input_by: string;
  input_at: string;
  status: string;
  orders: PendingOrder[];
}

export interface RealtimePrice {
  last_price: number;
  bid1: number;
  ask1: number;
  bid1_vol: number;
  ask1_vol: number;
  update_time: string;
}

// ---- Market Health ----

export interface SymbolHealth {
  symbol: string;
  last_price: number;
  update_time: string;
  age_seconds: number;
  status: string;
}

export interface MarketHealthData {
  status: string;
  total_symbols: number;
  healthy_count: number;
  stale_count: number;
  offline_count: number;
  symbols: SymbolHealth[];
}

export interface CepApiClient {
  requestJson<T = unknown>(url: string, options?: RequestInit): Promise<T>;
  fetchWeights(): Promise<ApiResponse<AllocationRow[]>>;
  fetchProducts(): Promise<ApiResponse<string[]>>;
  fetchAssets(): Promise<ApiResponse<Asset[]>>;
  createAsset(assetCode: string): Promise<ApiResponse>;
  deleteAsset(assetCode: string): Promise<ApiResponse>;
  saveWeight(payload: SaveWeightPayload): Promise<ApiResponse>;
  deleteWeight(recordId: number): Promise<ApiResponse>;
  fetchBacktestPresets(): Promise<ApiResponse<BacktestPreset[]>>;
  fetchBacktestHistory(limit?: number): Promise<ApiResponse<BacktestHistoryItem[]>>;
  fetchBacktestHistoryDetail(id: string, equityPoints?: number): Promise<ApiResponse<BacktestHistoryDetail>>;
  searchStocks(keyword: string, limit?: number): Promise<ApiResponse<StockSearchResult[]>>;
  runBacktest(payload: BacktestRequest): Promise<ApiResponse<BacktestResult>>;
  fetchUserSignals(): Promise<ApiResponse<UserSignalDefinition[]>>;
  createUserSignal(payload: UserSignalDefinition): Promise<ApiResponse<UserSignalDefinition>>;
  updateUserSignal(signalId: number, payload: UserSignalDefinition): Promise<ApiResponse<UserSignalDefinition>>;
  updateUserSignalStatus(signalId: number, status: 'enabled' | 'disabled'): Promise<ApiResponse>;
  validateUserSignal(sourceCode: string): Promise<ApiResponse & { diagnostics: SignalDiagnostic[] }>;
  runUserSignalBacktest(payload: UserSignalBacktestRequest): Promise<ApiResponse<BacktestResult & { diagnostics?: SignalDiagnostic[] }>>;
  fetchRecentLiveSignals(): Promise<ApiResponse<LiveSignal[]>>;
  fetchSignalCtxSchema(): Promise<ApiResponse<SignalCtxSchema>>;
  // Fund Inflow
  fetchProductList(): Promise<ApiResponse & { products: ProductInfo[] }>;
  addProduct(payload: any): Promise<ApiResponse>;
  updateProduct(payload: any): Promise<ApiResponse>;
  submitFundInflow(payload: { product_name: string; net_inflow: number; input_by: string }): Promise<ApiResponse & { batch_id: string }>;
  fetchFundInflows(): Promise<ApiResponse & { inflows: FundInflow[] }>;
  // Orders
  fetchPendingOrders(batchId: string): Promise<PendingOrdersResponse>;
  fetchAllOrders(params?: Record<string, string>): Promise<ApiResponse>;
  updateOrder(orderId: number, finalQuantity: number): Promise<ApiResponse>;
  confirmOrders(batchId: string, confirmedBy: string, priceType: string): Promise<ApiResponse>;
  reconcileOrders(): Promise<ApiResponse>;
  fetchXtCache(): Promise<ApiResponse>;
  // Prices
  fetchRealtimePrices(symbols: string): Promise<ApiResponse & { prices: Record<string, RealtimePrice> }>;
  // Market Health
  fetchMarketHealth(): Promise<ApiResponse & MarketHealthData>;
}
