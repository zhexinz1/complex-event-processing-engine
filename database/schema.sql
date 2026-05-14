-- CEP 项目数据库表结构
-- 用于净入金触发的增量买入流程

-- 产品信息表
CREATE TABLE IF NOT EXISTS products (
    id INT PRIMARY KEY AUTO_INCREMENT,
    product_name VARCHAR(100) NOT NULL UNIQUE COMMENT '产品名称',
    leverage_ratio DECIMAL(5, 2) NOT NULL COMMENT '杠杆倍数（如 2.00 表示2倍杠杆）',
    fund_account VARCHAR(50) NOT NULL COMMENT '底仓资金账号（真实资金账号ID，用于下单）',
    xt_username VARCHAR(100) COMMENT '迅投登录用户名',
    xt_password VARCHAR(200) COMMENT '迅投登录密码（加密存储）',
    status ENUM('active', 'inactive') DEFAULT 'active' COMMENT '产品状态',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_product_name (product_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='产品配置表';

-- 留白数据表（合约维度的小数部分累积）
CREATE TABLE IF NOT EXISTS fractional_shares (
    id INT PRIMARY KEY AUTO_INCREMENT,
    product_name VARCHAR(100) NOT NULL COMMENT '产品名称',
    asset_code VARCHAR(50) NOT NULL COMMENT '合约代码（如 AU2609）',
    fractional_amount DECIMAL(12, 6) NOT NULL DEFAULT 0.000000 COMMENT '累积的小数手数',
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_product_asset (product_name, asset_code),
    INDEX idx_product_name (product_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='留白数据表（四舍五入后的小数部分）';

-- 待确认订单表
CREATE TABLE IF NOT EXISTS pending_orders (
    id INT PRIMARY KEY AUTO_INCREMENT,
    batch_id VARCHAR(50) NOT NULL COMMENT '批次ID（同一次净入金的所有订单共享）',
    product_name VARCHAR(100) NOT NULL COMMENT '产品名称',
    asset_code VARCHAR(50) NOT NULL COMMENT '合约代码',
    target_market_value DECIMAL(18, 2) NOT NULL COMMENT '目标市值（元）',
    price DECIMAL(18, 4) NOT NULL COMMENT '计算时使用的价格（卖1价）',
    contract_multiplier INT NOT NULL COMMENT '合约乘数',
    theoretical_quantity DECIMAL(12, 6) NOT NULL COMMENT '理论手数（未取整）',
    rounded_quantity INT NOT NULL COMMENT '四舍五入后的手数',
    fractional_part DECIMAL(12, 6) NOT NULL COMMENT '留白部分（小数）',
    final_quantity INT NOT NULL COMMENT '最终确认的手数（可手动调整）',
    status ENUM('pending', 'confirmed', 'cancelled', 'executed', 'failed') DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    confirmed_at TIMESTAMP NULL COMMENT '交易员确认时间',
    executed_at TIMESTAMP NULL COMMENT '订单执行时间',
    error_msg TEXT COMMENT '执行失败时的错误信息',
    xt_order_id BIGINT COMMENT '迅投返回的指令ID',
    xt_status VARCHAR(20) DEFAULT 'not_sent' COMMENT '迅投侧状态（not_sent/send_failed/sent/running/rejected/filled/partial/cancelled/stopped）',
    xt_error_msg TEXT COMMENT 'CTP 驳回原因',
    xt_traded_volume INT DEFAULT 0 COMMENT '迅投回报的成交量',
    xt_traded_price DECIMAL(18, 4) DEFAULT 0.0000 COMMENT '迅投回报的成交均价',
    order_price_type VARCHAR(20) DEFAULT 'limit' COMMENT '下单价格类型（limit/market/best/twap/vwap）',
    direction VARCHAR(20) DEFAULT 'open_long' COMMENT '下单方向（open_long/close_long/open_short/close_short/buy/sell）',
    INDEX idx_batch_id (batch_id),
    INDEX idx_product_name (product_name),
    INDEX idx_status (status),
    INDEX idx_created_at (created_at),
    INDEX idx_xt_order_id (xt_order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='待确认订单表';

-- 净入金记录表
CREATE TABLE IF NOT EXISTS fund_inflows (
    id INT PRIMARY KEY AUTO_INCREMENT,
    batch_id VARCHAR(50) NOT NULL UNIQUE COMMENT '批次ID',
    product_name VARCHAR(100) NOT NULL COMMENT '产品名称',
    net_inflow DECIMAL(18, 2) NOT NULL COMMENT '净入金金额（元）',
    leverage_ratio DECIMAL(5, 2) NOT NULL COMMENT '杠杆倍数',
    leveraged_amount DECIMAL(18, 2) NOT NULL COMMENT '杠杆后金额（元）',
    input_by VARCHAR(50) COMMENT '录入人',
    input_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '录入时间',
    confirmed_by VARCHAR(50) COMMENT '确认人',
    confirmed_at TIMESTAMP NULL COMMENT '确认时间',
    status ENUM('pending', 'confirmed', 'cancelled') DEFAULT 'pending',
    INDEX idx_product_name (product_name),
    INDEX idx_batch_id (batch_id),
    INDEX idx_input_at (input_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='净入金记录表';

-- 插入示例产品数据
INSERT INTO products (product_name, leverage_ratio, fund_account, status) VALUES
('产品A', 2.00, 'XT_ACCOUNT_001', 'active'),
('产品B', 4.00, 'XT_ACCOUNT_002', 'active')
ON DUPLICATE KEY UPDATE updated_at = CURRENT_TIMESTAMP;
