# VPS Deployment Guide

One-time setup for a new customer deployment on a Hostinger (or any Ubuntu) VPS.

---

## 1. Provision the VPS

- Ubuntu 22.04 LTS, minimum 2GB RAM (4GB recommended for Open WebUI)
- Open ports: 22 (SSH), 80 (HTTP), 443 (HTTPS)

---

## 2. Install dependencies

```bash
# Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Nginx + Certbot
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx git
```

---

## 3. Deploy the app

```bash
# Clone the repo
git clone https://github.com/your-repo/agent-one-api.git /opt/agent-one
cd /opt/agent-one

# Set up environment
cp .env.example .env
nano .env   # fill in all values for this customer

# Start containers
docker compose up -d

# Verify both containers are running
docker compose ps
```

---

## 4. Set up Nginx + SSL

```bash
# Copy nginx config
sudo cp nginx.conf /etc/nginx/sites-available/agent-one

# Edit the domain name
sudo nano /etc/nginx/sites-available/agent-one
# Replace 'your-domain.com' with the actual domain

# Enable the site
sudo ln -s /etc/nginx/sites-available/agent-one /etc/nginx/sites-enabled/
sudo nginx -t  # test config
sudo systemctl reload nginx

# Issue SSL certificate (free, auto-renews)
sudo certbot --nginx -d your-domain.com

# Reload nginx with SSL
sudo systemctl reload nginx
```

---

## 5. Set up Supabase tables

Run the SQL in `sql/conversations_schema.sql` once in the Supabase SQL editor for this customer's project.

---

## 6. Verify

```bash
# Check containers are running
docker compose ps

# Check API health
curl https://your-domain.com/api/health -H "X-API-Key: your-key"
# Expected: {"status":"ok","documents":N,"chunks":N}

# Open the chat UI
# Visit https://your-domain.com in a browser
```

---

## Day-to-day operations

```bash
# View live logs
docker compose logs -f

# Restart after a code update
git pull
docker compose up -d --build

# Stop everything
docker compose down

# Clear a customer's chat history (replace SESSION_ID)
curl -X DELETE https://your-domain.com/api/sessions/SESSION_ID \
  -H "X-API-Key: your-key"
```

---

## Updating a customer deployment

```bash
cd /opt/agent-one
git pull
docker compose up -d --build
```

That's it. Zero downtime on the Open WebUI container since only the API rebuilds.
