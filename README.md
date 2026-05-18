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
