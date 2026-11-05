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
- Алиасы (роли CC-слотов; 2026-11-05: `sonnet` переведён на GLM flash по
  таймаутам Kimi-highspeed — решение оператора): `fable`=Kimi k3.1-pro ·
  `opus`=GLM glm-5.3 (primary тяжёлого) · `sonnet`=`haiku`=GLM glm-5.3-flash ·
  `swift`=Kimi highspeed (полка страховки лёгких); fallback перекрёстный.
- Тесты: pytest + PyYAML (L0 пины → L1 compose config → L2 парсер панели).

## Фазы

| Фаза | Описание | Статус | Дата |
|---|---|---|---|
| 0 | Протокольный spike: режим passthrough/unified, upstream-auth capture, модельные ID, живой fallback | DONE (Kimi-пробы — до отпущения лимита, оговорка в impl-сессии 261104-01) | 2026-11-04 |
| 1 | Core-стек локально: compose-артефакт, UI-настройка моделей/ключей, virtual key, gates (restart, YAML↔DB связка, discovery, auto mode) | DONE (все gates живьём: 4 модели + VK через UI/API; restart-персистентность; fallback top→optimal при индуцированном 401; scope VK 403; связка YAML↔DB; CC через шлюз «pong» + beta-запросы 200. Оговорки: auto mode и discovery-пикер — живой CC-сессией в эксплуатации/фазе 3; Kimi ID `k3.1-pro` подтверждён после отпущения окна) | 2026-11-04 |
| 2 | Деплой под governetics (upstream+route, Preview → узел → Deploy → `converged`), remote smoke через HTTPS. **Gate до Deploy:** живой прогон `tests/test_platform_parser.py` с `GOVERNETICS_ROOT` — панельные гейты (env_precedence, bind_mounts, tag-pattern на оба семейства тегов) локальным прогоном не покрыты (skip без checkout'а). Решение оператора 2026-11-04: держать здесь, не в backlog | DONE (gate закрыт: живой прогон с `GOVERNETICS_ROOT` поймал падение на document order — фикс `sorted()`-сравнения, `a12cfd9`; скрипты smoke/backup/restore + пины, ревью R6, 40 passed; Deploy `converged`, холодный старт с Prisma пережит самим деплоем; edge-маршрут `llm-gate.lab.governetics.ru` (BIND 10.0.0.110); 4/4 модели + VK `claude-code` через remote-master; remote smoke 5/5 через HTTPS; A8-цикл round-trip restore в probe-БД ×2 (пустая + поверх непустой). Перенесено в фазу 3: policy-YAML через панель, backup/restore живьём на ноде) | 2026-11-04 |
| 3 | Приёмка (CC-сессии через оба контура, индуцированный fallback), hardening (DB-admin, disable_env_credential_login, admin_only), доки (README-оператор, architecture.md, ADR D-001/D-002, release-config) | DONE по доступному объёму 2026-11-04: индуцированный fallback на контуре узла (битый ключ top → 200 от glm-5.3); доки — README-оператор, architecture as-is, D-001/D-002, CHANGELOG (0172ef8; ревью фокус + reader-test); release-config в доме. A9 переопределён решением оператора: стенд — master-логин сохранён, DB-admin `gateadmin` создан (UI Reset password; read-API юзера — баг v1.108.0, юзер функционален). Остатки в эксплуатации: полные CC-сессии, policy-YAML-изменение через панель, backup/restore на ноде, release-тег v0.1.0 (verify готов) | 2026-11-04 |

> Статусы: `TODO` / `IN PROGRESS` / `DONE (YYYY-MM-DD)`. Одна фаза — один
> vertical-slice; каждая закрывается docs-before-commit + real-env валидацией
> до деплой-тега.
