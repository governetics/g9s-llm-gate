# Implementation Plan — статус фаз

Текущее состояние реализации по фазам — **дом фазовых статусов и прогресса**: ни as-is, ни летопись их не держат.

История изменений — `../architecture/CHANGELOG.md`; as-is — `../architecture/architecture.md`.

## Стадия проекта

exploration — дата установки: 2026-11-04

## Tech Stack

- LiteLLM Proxy `v1.108.0` (ghcr.io/berriai/litellm; native `/v1/messages`
  passthrough — спайк 261104-01 фаза 0), встроенный Admin UI, модели в
  PostgreSQL 16.15 (`STORE_MODEL_IN_DB`).
- Docker Compose — единый шаблон `deploy/compose.yml` (local + governetics).
- Тесты: pytest + PyYAML (L0 пины → L1 compose config → L2 парсер панели).

## Фазы

| Фаза | Описание | Статус | Дата |
|---|---|---|---|
| 0 | Протокольный spike: режим passthrough/unified, upstream-auth capture, модельные ID, живой fallback | DONE (Kimi-пробы — до отпущения лимита, оговорка в impl-сессии 261104-01) | 2026-11-04 |
| 1 | Core-стек локально: compose-артефакт, UI-настройка моделей/ключей, virtual key, gates (restart, YAML↔DB связка, discovery, auto mode) | IN PROGRESS (артефакт + тесты готовы, ревью пройдено; живые gates — впереди) | 2026-11-04 — |
| 2 | Деплой под governetics (upstream+route, Preview → узел → Deploy → `converged`), remote smoke через HTTPS. **Gate до Deploy:** живой прогон `tests/test_platform_parser.py` с `GOVERNETICS_ROOT` — панельные гейты (env_precedence, bind_mounts, tag-pattern на оба семейства тегов) локальным прогоном не покрыты (skip без checkout'а). Решение оператора 2026-11-04: держать здесь, не в backlog | TODO | |
| 3 | Приёмка (CC-сессии через оба контура, индуцированный fallback), hardening (DB-admin, disable_env_credential_login, admin_only), доки (README-оператор, architecture.md, ADR D-001/D-002, release-config) | TODO | |

> Статусы: `TODO` / `IN PROGRESS` / `DONE (YYYY-MM-DD)`. Одна фаза — один
> vertical-slice; каждая закрывается docs-before-commit + real-env валидацией
> до деплой-тега.
