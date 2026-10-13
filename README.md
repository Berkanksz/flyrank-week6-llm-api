# Support Ticket Triage LLM API

Production-ready, structured LLM microservice built with FastAPI, Pydantic, and OpenAI-compatible client integration (supporting local Ollama and OpenRouter/Anthropic).

Classifies incoming unstructured customer support messages into closed categories, urgency levels, confidence scores, and brief explanations.

## 1. What POST /triage Does

`POST /triage` receives customer support text and returns a strictly typed JSON response containing:
1. `category`: One of `billing`, `bug`, `feature`, `other`.
2. `urgency`: One of `low`, `normal`, `high`.
3. `confidence`: Float between 0.0 and 1.0.
4. `reason`: Maximum two-sentence justification for the classification.

All requests are validated, guarded by timeouts, protected against transient errors with exponential backoff and jitter, logged for token usage, and backed by a single-repair retry loop for schema non-conformance.

## 2. Sample curl and Exact Response

### Request
```bash
curl -X POST http://localhost:8000/triage \
  -H "Content-Type: application/json" \
  -d '{"text": "I was charged twice for invoice #49281. Please refund the duplicate transaction immediately."}'
```

### Response (200 OK)
```json
{
  "category": "billing",
  "urgency": "high",
  "confidence": 0.95,
  "reason": "Customer reports a duplicate charge and requests an immediate refund."
}
```

## 3. Job Card & Hard Invariants

### Invariants ("Must Never")
1. Must never invent category or urgency values outside the allowed enums.
2. Must never return markdown wrappers (```json) to the client.
3. Must never retry client errors (400, 401, 403).
4. Must never make more than one repair attempt per request.
5. Must never hang indefinitely (hard 30-second timeout enforced).
6. Must never log secret API keys or credentials.
7. Must never leak raw LLM tracebacks to the client.

## 4. Swapping LLM Providers (No Code Changes)

The service supports provider switching entirely through three environment variables in `.env`:

### Provider A: Local Ollama (Default development setup)
```env
LLM_BASE_URL=http://localhost:11434/v1/
LLM_API_KEY=ollama
LLM_MODEL=gemma2:2b
```

### Provider B: OpenRouter / Cloud API
```env
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=sk-or-v1-your-real-key-here
LLM_MODEL=anthropic/claude-3.5-haiku
```

### Stub Mode (Offline CI / Local smoke test)
```env
LLM_STUB=1
```

## 5. Evaluation Results

Run evaluation set:
```bash
python3 run_eval.py
```

### Benchmark Score
- Total Cases: 8
- Passed: 7
- Failed: 1
- Accuracy: **87.5%** on prompt `prompts/triage-v1.md` using `gemma2:2b`.

### Evaluation Detail
| Case ID | Text Preview | Expected | Actual | Urgency Match | Status |
|---|---|---|---|---|---|
| case_1 | Duplicate charge on subscription | billing | billing | high == high | PASS |
| case_2 | App crashes with 500 on export | bug | bug | high == high | PASS |
| case_3 | Add dark mode toggle | feature | feature | low == low | PASS |
| case_4 | Where are servers located | other | other | low == low | PASS |
| case_5 | Enterprise annual discount info | billing | billing | normal == normal | PASS |
| case_6 | Do you support webhook notifications | feature | other | normal == normal | FAIL (Category) |
| case_7 | Reset password link broken | bug | bug | high == high | PASS |
| case_8 | General thank you message | other | other | low == low | PASS |

Note on case_6: Classified as `other` because the model adhered to the conservative prompt rule: inquiry questions without explicit requests default to `other`.

## 6. Cost & Latency Metrics

Logged to `logs/cost.jsonl` per call.
- Average input tokens: 480 tokens
- Average output tokens: 42 tokens
- Average inference latency: 3.2s (local Gemma 2 2B)

### 10,000 Request Daily Cost Projection (Claude 3.5 Haiku rates)
- Input: 10,000 * 480 tokens = 4,800,000 tokens ($0.80 / 1M) = $3.84
- Output: 10,000 * 42 tokens = 420,000 tokens ($4.00 / 1M) = $1.68
- Total projected daily cost: **$5.52 / day** ($165.60 / month)

## 7. What I'd Fix With Another Day
1. Add prompt v2 with a disambiguation rule separating technical capability inquiries from general feedback.
2. Implement semantic caching via Redis for identical customer queries to cut LLM calls by an estimated 25%.
3. Add Prometheus latency histogram and counter metrics for real-time grafana alerting.
