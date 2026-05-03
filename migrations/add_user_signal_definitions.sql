CREATE TABLE IF NOT EXISTS user_signal_definitions (
    id           INT PRIMARY KEY AUTO_INCREMENT,
    name         VARCHAR(120) NOT NULL,
    symbols      JSON         NOT NULL,
    bar_freq     VARCHAR(20)  NOT NULL DEFAULT '1m',
    source_code  MEDIUMTEXT   NOT NULL,
    status       VARCHAR(20)  NOT NULL DEFAULT 'disabled',
    created_by   VARCHAR(100) NOT NULL DEFAULT 'system',
    created_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
