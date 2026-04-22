-- 为 products 表添加迅投账号凭证字段
ALTER TABLE products
ADD COLUMN xt_username VARCHAR(100) DEFAULT NULL COMMENT '迅投登录用户名',
ADD COLUMN xt_password VARCHAR(255) DEFAULT NULL COMMENT '迅投登录密码（加密存储）';
