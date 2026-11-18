#!/bin/bash
set -e

APP_DIR="/var/www/getway"
NGINX_CONF="/etc/nginx/sites-available/gmail-gateway"
NGINX_ENABLED="/etc/nginx/sites-enabled/gmail-gateway"

echo "=== FamPay UPI Gateway VPS Deployment Script by @enzosrs (https://t.me/devcommunityx) ==="
echo "Updating packages..."
sudo apt update

echo "Installing system dependencies..."
sudo apt install -y python3 python3-pip python3-venv nginx curl git

if ! command -v pm2 &> /dev/null; then
    echo "Installing Node.js and PM2..."
    curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
    sudo apt install -y nodejs
    sudo npm install -g pm2
fi

echo "Setting up application directory at $APP_DIR..."
sudo mkdir -p $APP_DIR
sudo chown -R $USER:$USER $APP_DIR

echo "Copying files to $APP_DIR..."
cp -r * $APP_DIR/ 2>/dev/null || true

cd $APP_DIR

echo "Creating python virtual environment..."
python3 -m venv .venv
source .venv/bin/activate

echo "Installing requirements..."
pip install --upgrade pip
pip install -r requirements.txt

if [ ! -f .env ] && [ -f .env.example ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
fi

DOMAIN_NAME=$(grep -E '^APP_URL=' .env | cut -d'=' -f2- | sed -E 's/https?:\/\///' | sed 's/\/.*//' | tr -d '\r')
if [ -z "$DOMAIN_NAME" ]; then
    DOMAIN_NAME="localhost"
fi

sudo tee $NGINX_CONF > /dev/null <<EOT
server {
    listen 80;
    server_name $DOMAIN_NAME;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOT

sudo ln -sf $NGINX_CONF $NGINX_ENABLED
sudo rm -f /etc/nginx/sites-enabled/default || true
sudo systemctl restart nginx

echo "Deployment setup completed."
