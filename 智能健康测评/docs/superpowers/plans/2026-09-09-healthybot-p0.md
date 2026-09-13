# HealthyBot P0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing FastAPI + Vue3 nutrition assessment app into a SiliconFlow-backed P0 HealthyBot demo with user profiles, routed multi-agent chat, meal photo analysis, and confirmed daily meal records.

**Architecture:** Add focused SQLAlchemy models and services beside the existing assessment/knowledge/graph modules. SiliconFlow remains the only LLM/vision provider; chat routing is deterministic and bounded to one specialist response per request, with database-backed conversation history and graceful vision fallback. Vue adds one Health Assistant workspace while preserving the existing tabs.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic v2, OpenAI-compatible SiliconFlow API, Vue 3, Axios, Vite, pytest.

**Spec:** User-approved A scope in chat and `需求评审_健康营养AI助手_v1.1.md` (YOLO tongue detection, Dify, and Ollama explicitly excluded).

## Global Constraints

- Use SiliconFlow configured in `backend/.env`; do not add Dify or Ollama.
- Do not implement YOLO tongue detection or tongue diagnosis.
- Health output is observational guidance only and must include a medical disclaimer.
- Chat routing must cap specialist hops at 4 and retain a bounded context window.
- Meal analysis failures return editable pending data instead of blocking record creation.

---

### Task 1: Domain models and service contracts

**Files:**
- Create: `backend/app/models/assistant.py`
- Create: `backend/app/models/meal.py`
- Create: `backend/app/schemas/assistant.py`
- Create: `backend/app/schemas/meal.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/core/database.py`
- Test: `backend/tests/test_domain_contracts.py`

- [ ] Write failing tests for profile defaults, agent route names, and meal nutrition aggregation.
- [ ] Run `pytest backend/tests/test_domain_contracts.py -q` and observe missing modules.
- [ ] Add SQLAlchemy tables `user_profiles`, `assistant_conversations`, `assistant_messages`, and `meal_records` plus Pydantic request/response types.
- [ ] Export models and import them during `init_db`.
- [ ] Run the focused tests and confirm they pass.

### Task 2: Assistant routing and profile APIs

**Files:**
- Create: `backend/app/services/assistant_service.py`
- Create: `backend/app/routers/assistant.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/services/llm_client.py`
- Test: `backend/tests/test_assistant_service.py`

- [ ] Write failing tests for nutrition/运动/睡眠/健康 routing, four-hop cap, and LLM failure fallback.
- [ ] Run the focused tests and confirm the expected failures.
- [ ] Implement keyword routing, bounded DB context, profile upsert, and SiliconFlow prompt generation with disclaimer.
- [ ] Add `/api/assistant/profile/{user_id}`, `/api/assistant/chat`, and `/api/assistant/conversations/{id}`.
- [ ] Run focused tests and a FastAPI import check.

### Task 3: Meal vision analysis and daily records

**Files:**
- Create: `backend/app/services/meal_service.py`
- Create: `backend/app/routers/meals.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_meal_service.py`

- [ ] Write failing tests for normalized meal payloads, nutrition totals, and vision failure pending state.
- [ ] Run the focused tests and confirm the expected failures.
- [ ] Implement SiliconFlow vision parsing with strict JSON extraction and deterministic fallback; add analyze/confirm/daily endpoints.
- [ ] Run focused tests and validate endpoint schemas.

### Task 4: Vue Health Assistant workspace

**Files:**
- Create: `frontend/src/views/AssistantPage.vue`
- Modify: `frontend/src/api.js`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/style.css`

- [ ] Add API wrappers for profile, chat, meal analyze/confirm/daily.
- [ ] Build the assistant workspace with conversation panel, profile editor, meal upload/confirmation, and daily summary.
- [ ] Add responsive styles and disclaimer/error/loading states consistent with existing UI.
- [ ] Run `npm run build`.

### Task 5: Verification and operator docs

**Files:**
- Modify: `README.md`
- Create: `backend/tests/conftest.py` (only if needed by integration tests)

- [ ] Run all backend tests and `npm run build`.
- [ ] Start FastAPI and Vite, call `/api/health`, `/api/assistant/profile`, and `/api/meals/daily` for smoke verification.
- [ ] Document new routes, SiliconFlow configuration, and explicitly excluded features.

