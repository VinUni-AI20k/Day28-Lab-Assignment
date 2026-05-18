# Lab #28 — Full Platform Integration Sprint

AI platform với kiến trúc hybrid (Local-first + Kaggle GPU fallback) sử dụng Prefect, Kafka, Qdrant, Prometheus, Grafana, LangSmith.

## Kiến trúc

```
Local (Docker Compose):
  Kafka → Prefect (kafka-to-delta flow) → Delta Lake → Feast (Redis)
                                              │
                                              ▼
                                          Qdrant ← embed-service (sentence-transformers)
                                              │
                                              ▼
                                          API Gateway (FastAPI)
                                              │
                                              ├─→ mock-vllm (OpenAI-compatible fallback)
                                              └─→ vLLM trên Kaggle GPU (nếu tunnel sẵn)
                                              │
                                              ▼
                                          Prometheus → Grafana
                                          LangSmith tracing
```

**Hybrid fallback**: API Gateway gọi `VLLM_URL` từ `.env`. Mặc định trỏ tới `mock-vllm` container chạy local; nếu set sang ngrok URL của Kaggle vLLM thì auto switch sang GPU. Không cần redeploy.

## Yêu cầu

- Docker Desktop (≥8GB RAM allocated)
- Python 3.11 (3.10 OK, 3.12+ chưa test)
- LangSmith API key (free tier OK) — optional, traces sẽ skip nếu không có
- Docker Desktop đang chạy
- Python 3.10+
- Tài khoản Kaggle với GPU đã bật
- **Tunnel service** (chọn 1 trong 2):
  - `ngrok` đã cài và token configured
  - HOẶC `cloudflared` đã cài (`brew install cloudflare/cloudflare/cloudflared`)

## Quick Start (local stack, không cần Kaggle)

### 1. Copy `.env`

```bash
cp .env.example .env
# Mặc định trỏ tới mock-vllm + embed-service local. Điền LANGCHAIN_API_KEY nếu muốn traces.
```

### 2. Khởi động stack

```bash
docker compose up -d --build   # lần đầu ~5 phút (build embed-service tải sentence-transformers)
docker compose ps              # 11/11 services Up
```

**Services & URLs:**
| Service | URL | Mô tả |
|---|---|---|
| Prefect UI | http://localhost:4200 | Flow runs, work pools |
| Grafana | http://localhost:3000 (admin/admin) | Dashboard |
| Prometheus | http://localhost:9090 | Metrics |
| Qdrant | http://localhost:6333/dashboard | Vector store |
| API Gateway | http://localhost:8000/docs | Swagger UI |
| Mock vLLM | http://localhost:8001/v1/models | OpenAI-compatible |
| Embed Service | http://localhost:8002/health | sentence-transformers |

### 3. Tạo venv host (để chạy scripts + tests)

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install "griffe<0.40"   # workaround prefect 2.14
```

### 4. Chạy data pipeline E2E

```bash
# Tạo Kafka topic
docker exec day28-lab-assignment-kafka-1 kafka-topics \
  --create --topic data.raw --bootstrap-server localhost:9092 \
  --partitions 1 --replication-factor 1

# Ingest sample data
python scripts/01_ingest_to_kafka.py

# Prefect flow: Kafka → Delta Lake
PREFECT_API_URL=http://localhost:4200/api \
KAFKA_BOOTSTRAP=localhost:9092 \
DELTA_PATH=./delta-lake/raw \
python prefect/flows/kafka_to_delta.py

# Push features → Feast (Redis)
python scripts/03_delta_to_feast.py

# Embed → Qdrant
EMBED_NGROK_URL=http://localhost:8002 python scripts/05_embed_to_qdrant.py
Tạo Kaggle Notebook với GPU T4 x2, chọn 1 trong 2 option:

**Option A: Single GPU (đơn giản - dùng 1 GPU)**

```python
# Cell 1: Install dependencies
!pip install -q vllm fastapi uvicorn pyngrok mlflow sentence-transformers

# Nếu cài vLLM bị lỗi, dùng fallback:
# !pip install transformers==4.46.3 --quiet
# !pip install vllm==0.7.3 --quiet

# Cell 2: Setup ngrok
from pyngrok import ngrok
ngrok.set_auth_token("YOUR_NGROK_TOKEN")  # lấy tại ngrok.com

# Cell 3: Start vLLM server (single GPU)
import subprocess, threading, time

def run_vllm():
    subprocess.run([
        "python", "-m", "vllm.entrypoints.openai.api_server",
        "--model", "Qwen/Qwen2.5-7B-Instruct-GPTQ-Int4",
        "--port", "8001",
        "--max-model-len", "4096",
        "--gpu-memory-utilization", "0.5"
    ])

thread = threading.Thread(target=run_vllm, daemon=True)
thread.start()
time.sleep(60)
print("vLLM server started")

# Cell 4: Create ngrok tunnel
tunnel = ngrok.connect(8001, "http")
print(f"vLLM URL: {tunnel.public_url}")
```

**Option B: Multi-GPU (nâng cao - dùng 2 GPUs)**

```python
# Cell 1: Install dependencies
!pip install -q vllm fastapi uvicorn pyngrok mlflow sentence-transformers

# Nếu cài vLLM bị lỗi, dùng fallback:
# !pip install transformers==4.46.3 --quiet
# !pip install vllm==0.7.3 --quiet

# Cell 2: Setup ngrok
from pyngrok import ngrok
ngrok.set_auth_token("YOUR_NGROK_TOKEN")  # lấy tại ngrok.com

# Cell 3: Start vLLM server (multi-GPU)
import subprocess
import os
import time
import requests
import threading

MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct-GPTQ-Int4"

def start_server(gpu_id, port):
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = str(gpu_id)

    proc = subprocess.Popen(
        [
            "vllm", "serve", MODEL_NAME,
            "--dtype", "float16",
            "--max-model-len", "8192",
            "--host", "0.0.0.0",
            "--port", str(port),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env
    )

    def stream_logs():
        for line in proc.stdout:
            print(f"[GPU {gpu_id}] {line.decode()}", end="")

    threading.Thread(target=stream_logs, daemon=True).start()

    return proc

print("Starting Server on GPU 0 (Port 8000)")
proc1 = start_server(0, 8000)

print("Starting Server on GPU 1 (Port 8001)")
proc2 = start_server(1, 8001)

def wait_for_server(port):
    print(f" Waiting for server on port {port}...")
    for _ in range(60):
        try:
            r = requests.get(f"http://localhost:{port}/health")
            if r.status_code == 200:
                print(f"Server on port {port} is ready!")
                return
        except:
            time.sleep(5)
    raise RuntimeError(f"Server on port {port} failed to start.")

wait_for_server(8000)
wait_for_server(8001)

# Cell 4: Create ngrok tunnel
print("Creating ngrok tunnels...")
tunnel1 = ngrok.connect(8000, "http")
tunnel2 = ngrok.connect(8001, "http")

print(f"GPU 0 URL: {tunnel1.public_url}")
print(f"GPU 1 URL: {tunnel2.public_url}")
# Có thể dùng 1 trong 2 hoặc cả 2 cho load balancing
```

**Option C: Dùng cloudflared (Single GPU)**

```python
# Cell 1: Install dependencies
!pip install -q vllm fastapi uvicorn cloudflared mlflow sentence-transformers

# Nếu cài vLLM bị lỗi, dùng fallback:
# !pip install transformers==4.46.3 --quiet
# !pip install vllm==0.7.3 --quiet

# Cell 2: Start vLLM server (single GPU)
import subprocess, threading, time

def run_vllm():
    subprocess.run([
        "python", "-m", "vllm.entrypoints.openai.api_server",
        "--model", "Qwen/Qwen2.5-7B-Instruct-GPTQ-Int4",
        "--port", "8001",
        "--max-model-len", "4096",
        "--gpu-memory-utilization", "0.5"
    ])

thread = threading.Thread(target=run_vllm, daemon=True)
thread.start()
time.sleep(60)
print("vLLM server started")

# Cell 3: Create cloudflare tunnel
import subprocess
tunnel = subprocess.run(["cloudflared", "tunnel", "--url", "http://localhost:8001"], capture_output=True, text=True)
print(tunnel.stdout)  # URL sẽ hiển thị
```

**Option D: Dùng cloudflared (Multi-GPU)**

```python
# Cell 1: Install dependencies
!pip install -q vllm fastapi uvicorn cloudflared mlflow sentence-transformers

# Nếu cài vLLM bị lỗi, dùng fallback:
# !pip install transformers==4.46.3 --quiet
# !pip install vllm==0.7.3 --quiet

# Cell 2: Start vLLM server (multi-GPU)
import subprocess
import os
import time
import requests
import threading

MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct-GPTQ-Int4"

def start_server(gpu_id, port):
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = str(gpu_id)

    proc = subprocess.Popen(
        [
            "vllm", "serve", MODEL_NAME,
            "--dtype", "float16",
            "--max-model-len", "8192",
            "--host", "0.0.0.0",
            "--port", str(port),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env
    )

    def stream_logs():
        for line in proc.stdout:
            print(f"[GPU {gpu_id}] {line.decode()}", end="")

    threading.Thread(target=stream_logs, daemon=True).start()

    return proc

print("Starting Server on GPU 0 (Port 8000)")
proc1 = start_server(0, 8000)

print("Starting Server on GPU 1 (Port 8001)")
proc2 = start_server(1, 8001)

def wait_for_server(port):
    print(f" Waiting for server on port {port}...")
    for _ in range(60):
        try:
            r = requests.get(f"http://localhost:{port}/health")
            if r.status_code == 200:
                print(f"Server on port {port} is ready!")
                return
        except:
            time.sleep(5)
    raise RuntimeError(f"Server on port {port} failed to start.")

wait_for_server(8000)
wait_for_server(8001)

# Cell 3: Create cloudflare tunnel
import subprocess
print("Creating cloudflare tunnels...")
tunnel1 = subprocess.run(["cloudflared", "tunnel", "--url", "http://localhost:8000"], capture_output=True, text=True)
tunnel2 = subprocess.run(["cloudflared", "tunnel", "--url", "http://localhost:8001"], capture_output=True, text=True)
print(f"GPU 0 URL (copy from output):")
print(tunnel1.stdout)
print(f"GPU 1 URL (copy from output):")
print(tunnel2.stdout)
# Có thể dùng 1 trong 2 hoặc cả 2 cho load balancing
```

### 3. Cập nhật Environment Variables

```bash
# Copy và chỉnh sửa file .env
cp .env.example .env
# Thay VLLM_NGROK_URL với URL từ Kaggle (ngrok hoặc cloudflared)
# Thay EMBED_NGROK_URL nếu có embedding service
# Thay LANGCHAIN_API_KEY với key của bạn
```

### 5. Smoke Tests

```bash
pytest smoke-tests/ -v
```

Kỳ vọng: **8/8 PASSED** (5 test journey classes).

### 6. Production Readiness Check

```bash
python scripts/production_readiness_check.py
```

Kỳ vọng: **Score 10/10 = 100%**.

### 7. Verify Observability

```bash
LANGCHAIN_API_KEY=lsv2_pt_... python scripts/09_verify_observability.py
```

Kỳ vọng: Prometheus OK + LangSmith có traces (sau khi đã gọi `/api/v1/chat`).

## Tùy chọn: Bật Kaggle vLLM thật

Trong Kaggle Notebook (GPU T4 x2):

```python
!pip install -q vllm pyngrok
from pyngrok import ngrok; ngrok.set_auth_token("YOUR_TOKEN")
import subprocess, threading, os
def run_vllm():
    env = os.environ.copy(); env["VLLM_USE_V1"] = "0"   # T4 workaround
    subprocess.run(["python","-m","vllm.entrypoints.openai.api_server",
        "--model","Qwen/Qwen2.5-7B-Instruct-GPTQ-Int4","--port","8001",
        "--max-model-len","4096","--quantization","gptq","--enforce-eager"], env=env)
threading.Thread(target=run_vllm, daemon=True).start()
print(ngrok.connect(8001, "http").public_url)
```

Sửa `.env` → `VLLM_NGROK_URL=https://xxxx.ngrok-free.app` → `docker compose up -d --force-recreate api-gateway`. Stack route sang Kaggle GPU thay vì mock.

## Scripts

| Script | Mô tả |
|---|---|
| `scripts/01_ingest_to_kafka.py` | Ingest sample data vào Kafka |
| `scripts/03_delta_to_feast.py` | Load Delta → push features Redis |
| `scripts/05_embed_to_qdrant.py` | Embed text → store vectors Qdrant |
| `scripts/09_verify_observability.py` | Verify Prometheus + LangSmith |
| `scripts/production_readiness_check.py` | 10-check readiness |

## API Gateway

```bash
curl http://localhost:8000/health
# {"status":"ok","langsmith":true}

curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"query":"What is platform engineering?","embedding":[0.1,0.2,0.3]}'
```

## Troubleshooting

**Prefect worker exits ngay sau khi start** — race condition. Restart: `docker compose up -d prefect-worker`.

**embed-service báo `Numpy is not available`** — torch/numpy ABI mismatch. Đã pin `numpy==1.26.4` trong `embed-service/requirements.txt`.

**API gateway port conflict** — kill process khác đang giữ 8000: `lsof -ti:8000 | xargs kill`.

**Kafka topic không tồn tại** — script `01_ingest_to_kafka.py` cần topic `data.raw`. Tạo bằng `kafka-topics --create`.

## Nộp Bài

Xem [SUBMISSION.md](SUBMISSION.md) cho artifact list và [SUBMISSION_ANSWERS.md](SUBMISSION_ANSWERS.md) cho 5 câu trả lời essay.

**Lưu ý cấu trúc**: SUBMISSION.md mô tả cấu trúc `lab28_submission_xxx/lab28/...` với code trong subdirectory. Repo này đặt code ở **root** thay vì subdirectory để giữ git history sạch — toàn bộ repo này tương đương với phần `lab28/` trong template. Screenshots cần upload vào folder `screenshots/` ở root.

## License

Edu
Xem `SUBMISSION.md` ở thư mục gốc project.
