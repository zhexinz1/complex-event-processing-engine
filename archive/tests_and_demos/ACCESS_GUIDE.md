# 访问CEP系统的方法

## 问题原因
服务器的5000端口没有在阿里云安全组中开放，导致无法从外网访问。

## 解决方案

### 方案1：开放安全组端口（推荐）

1. 登录阿里云控制台：https://ecs.console.aliyun.com/
2. 找到实例：43.160.206.71
3. 点击"安全组" → "配置规则"
4. 点击"添加安全组规则"
5. 配置如下：
   - 规则方向：入方向
   - 授权策略：允许
   - 协议类型：TCP
   - 端口范围：5000/5000
   - 授权对象：0.0.0.0/0
   - 描述：CEP系统Web服务
6. 点击"确定"

配置完成后，直接访问：http://43.160.206.71:5000/

### 方案2：SSH端口转发（临时方案）

在你的本地电脑执行：

```bash
ssh -L 5000:localhost:5000 ubuntu@43.160.206.71
```

然后在浏览器访问：http://localhost:5000/

### 方案3：使用Nginx反向代理（生产环境推荐）

如果80端口已开放，可以配置Nginx反向代理：

```bash
# 安装Nginx
sudo apt update
sudo apt install nginx -y

# 配置反向代理
sudo tee /etc/nginx/sites-available/cep << 'EOF'
server {
    listen 80;
    server_name 43.160.206.71;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
EOF

# 启用配置
sudo ln -s /etc/nginx/sites-available/cep /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

然后访问：http://43.160.206.71/

---

## 当前服务状态

✅ Flask服务运行正常（端口5000）
✅ 本地访问正常（http://localhost:5000）
❌ 外网访问被阻止（安全组未开放）

## 访问地址（安全组开放后）

- 目标仓位配置：http://43.160.206.71:5000/
- 净入金录入：http://43.160.206.71:5000/fund-inflow.html
- 订单确认：http://43.160.206.71:5000/order-confirm.html
