# VM Deployment Guide

Deploy the full stack (FastAPI + PostgreSQL + Ollama) on any Linux VM with Docker.

---

## Prerequisites

- **Linux VM** (Ubuntu 22.04+ recommended) with at least:
  - 4 CPU cores
  - 8GB RAM (16GB+ recommended for LLM)
  - 20GB disk
- **Docker** + **Docker Compose** installed

### Install Docker (Ubuntu)

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Install Docker Compose plugin
sudo apt-get install docker-compose-plugin

# Verify
docker --version
docker compose version
```

---

## Step 1: Upload Project to VM

```bash
# Option A: Git clone
git clone <https://github.com/Abdelhady-22/Interactive_Course-> Interactive_Course
cd Interactive_Course

# Option B: SCP from local machine
scp -r d:\Interactive_Course-\ user@your-vm-ip:~/Interactive_Course
ssh user@your-vm-ip
cd ~/Interactive_Course
```

---

## Step 2: Configure Environment

```bash
cp .env.example .env
nano .env  # or vim .env
```

**Minimum changes:**
```ini
# Change the password for production!
POSTGRES_PASSWORD=your_secure_password_here

# Choose your LLM (Ollama is default, needs 8GB+ RAM)
LLM_MODEL=ollama/llama3
LLM_MODEL_NAME=llama3
```

> **TIP**: If your VM has limited RAM (<8GB), use a cloud LLM instead:
> ```ini
> LLM_MODEL=groq/llama-3.1-70b-versatile
> LLM_API_KEY=your-groq-key
> ```
> And comment out the `ollama` service in `docker-compose.yml`.

---

## Step 3: First-Time Setup

```bash
# Build and start all services
docker compose up -d

# Wait for PostgreSQL and Ollama to be healthy (~30-60 seconds)
docker compose ps

# Run migrations + seed mock data
docker compose run --rm migrate

# Check app is running
curl http://localhost:8000/health
curl http://localhost:8000/health/detailed
```

Expected health response:
```json
{"status": "healthy", "db": "ok", "llm": "ok"}
```

---

## Step 4: Test the Agent

```bash
# Get the course ID from the seed output, or list courses:
curl http://localhost:8000/api/courses/ | python3 -m json.tool

# Process the course (runs AI agent on all 10 paragraphs)
COURSE_ID="<paste-your-course-id>"
curl -X POST "http://localhost:8000/api/courses/$COURSE_ID/process"

# View decisions
curl "http://localhost:8000/api/courses/$COURSE_ID/decisions" | python3 -m json.tool

# Approve + Publish
curl -X POST "http://localhost:8000/api/courses/$COURSE_ID/approve-all"
curl -X POST "http://localhost:8000/api/courses/$COURSE_ID/publish"

# Get playback JSON
curl "http://localhost:8000/api/courses/$COURSE_ID/playback" | python3 -m json.tool
```

---

## Common Commands

```bash
# View logs
docker compose logs app -f

# View app log file
docker compose exec app cat logs/app.log

# Restart app only
docker compose restart app

# Stop everything
docker compose down

# Stop and delete all data (fresh start)
docker compose down -v

# Rebuild after code changes
docker compose build app
docker compose up -d app

# Re-run migrations
docker compose run --rm migrate
```

---

## GPU Support (Optional — for faster Ollama)

If your VM has an NVIDIA GPU:

1. Install [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)

2. Uncomment the GPU section in `docker-compose.yml`:
```yaml
ollama:
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: all
            capabilities: [gpu]
```

3. Restart: `docker compose up -d ollama`

---

## Using Cloud LLM Instead of Ollama

To use Groq, OpenAI, or Anthropic instead of local Ollama:

1. Edit `.env`:
```ini
LLM_MODEL=groq/llama-3.1-70b-versatile
LLM_API_KEY=gsk_your_key_here
```

2. Comment out `ollama` and `ollama-pull` services in `docker-compose.yml`

3. Remove the `ollama` dependency from the `app` service

4. Restart: `docker compose up -d`

---

## Monitoring

- **Swagger UI**: `http://your-vm-ip:8000/docs`
- **Health check**: `http://your-vm-ip:8000/health/detailed`
- **App logs**: `docker compose logs app -f`
- **Log file**: Inside container at `/app/logs/app.log`

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ollama` container keeps restarting | Needs more RAM. Try `--memory=8g` or use cloud LLM |
| Model pull fails | Check internet connectivity: `docker compose logs ollama-pull` |
| Database connection refused | Wait for DB to be healthy: `docker compose ps` |
| Agent returns FALLBACK for all paragraphs | Check LLM is running: `curl http://localhost:11434/api/tags` |
| Permission denied on volumes | Run: `sudo chown -R 1000:1000 ./logs ./uploads` |
