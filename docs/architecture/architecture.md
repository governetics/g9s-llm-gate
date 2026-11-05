# Architecture — as-is

Текущее состояние системы (as-is). Целевое состояние (to-be) — в `vision.md`
(создаётся при появлении); история изменений — [CHANGELOG.md](CHANGELOG.md);
индекс решений — [decisions/decisions-log.md](decisions/decisions-log.md).

Этот файл — **as-is source of truth**: описывает систему как она есть сейчас,
без сессионных нарративов и фазовых статусов (их дом —
`../project/implementation-plan.md` и CHANGELOG).

---

## Обзор

`g9s-llm-gate` — Docker-шлюз на LiteLLM Proxy: единая точка подключения coding-агентов
(Claude Code, OpenCode) к LLM-провайдерам по протоколу Anthropic (`/v1/messages`).
Начальный контур — Kimi и GLM. Один compose-шаблон (`deploy/compose.yml`) разворачивается
в двух контурах без правок: локально (`docker compose --env-file .env`) и на платформе
governetics (панель, Path A). Архитектура артефакта и владение конфигурацией —
[D-001](decisions/D-001-artefakt-llm-gate.md); контракт с панелью —
[D-002](decisions/D-002-kontrakt-governetics.md).

## Компоненты

| Компонент | Что делает |
|---|---|
| `litellm` (`ghcr.io/berriai/litellm:v1.108.0`) | прокси `/v1/messages` (native passthrough), Admin UI на `:4000`, virtual keys, spend tracking. `command: [--config, /app/proxy_server_config.yaml, --port, "4000"]` — без явного `--config` образ стартует с пустым model list. Healthcheck — `/health/liveliness` (без auth, без трат токенов; `/health` шлёт реальные запросы — в пробы запрещён) |
| `db` (`postgres:16.15`) | хранилище моделей (`STORE_MODEL_IN_DB: "True"`), credentials (шифруются salt key), virtual keys, spend. Named volume `db-data`; **без** host-портов — БД отвечает только в compose-сети |
| `policy_yaml` (`configs.content`) | routing-политика: `router_settings.fallbacks` по публичным алиасам + `litellm_settings.num_retries: 2`. Доставляется как `/app/proxy_server_config.yaml`; в контенте нет `$` (compose интерполирует configs, панель стабит `${…}`). Пересоздание контейнера при изменении контента — hash-лейбл `llmgate.policy-sha256` (первые 16 hex sha256 контента; пинится тестом) |

Ключи шаблона (`x-g9s-config`, пять; детали контракта — D-002): `LLM_GATE_BIND`
(адрес публикации), `LLM_GATE_PORT` (порт хоста; порт контейнера всегда 4000),
`LLM_GATE_MASTER_KEY`, `LLM_GATE_SALT_KEY`, `LLM_GATE_POSTGRES_PASSWORD` (invisible;
подстановка fail-loud `${KEY:?…}`). Маппинг на имена образа — через `environment:`
(панельный `env_file` не затеняет). Оба сервиса: `restart: unless-stopped` + ротация
json-file логов; без `depends_on: condition: service_healthy` — litellm, стартующий
раньше готовности db, возвращается restart-политикой.

## Режим passthrough

Модели провайдеров работают в **native `/v1/messages` passthrough**: Anthropic-протокол
проходит шлюз как есть, без конвертации (`model_info.supported_endpoints:
["/v1/messages"]`). Upstream-модель — серверный ID **без суффикса `[1m]`**: суффикс —
клиентская нотация Claude Code (клиент вырезает его до отправки; шлюз о нём не знает),
1M-контекст включается клиентскими env. Провайдеру уходит настроенный ключ модели, не
клиентский Bearer (доказано capture-тестом спайка). Unified-конверсия отвергнута — D-001.

## Владение конфигурацией

Один хозяин на область, dual-write запрещён:

- **БД / Admin UI** — модели (алиасы, upstream, credentials), virtual keys, бюджеты.
  Смена модели — живьём через UI, без правки YAML и рестарта.
- **YAML шаблона** — routing-политика (fallbacks, retries) и, по мере hardening,
  `general_settings`. С v1.103.0 YAML-ключи приоритетнее UI-правок этих областей.

Связка областей: fallbacks ссылаются на `model_name` из БД — доказано живьём
(индуцированный отказ primary → ответ от fallback-провайдера). Следствие: переименование
алиаса тянет за собой YAML (fallback-цели) и scope существующих ключей (UI-переименование
обновляет scope, API delete+new — нет).

## Алиасы и fallback

Публичные имена моделей — семантические классы; набор живёт в БД и не заморожен
артефактом. Начальные значения и fallback-политика (перекрёстная, по классам):

| Класс | Семантика | Primary | Fallback |
|---|---|---|---|
| `fable` | топовая: рассуждения, анализ репо, ревью, vision | Kimi `k3.1-pro` | `opus` (GLM) |
| `opus` | оптимальная: основная работа | GLM `glm-5.3` | `fable` (Kimi) |
| `sonnet` | быстрая: лёгкий интерактив | GLM `glm-5.3-flash` | `swift` (Kimi) |
| `haiku` | дешёвая: субагенты, auto, механика | GLM `glm-5.3-flash` | `swift` (Kimi) |
| `swift` | полка: Kimi-fast, цель страховки лёгких | Kimi `k3.1-pro-highspeed` | `sonnet` (GLM) |

Переключение — только при ошибке **до начала ответа**; mid-stream fallback —
именованный предел, не обещание. Клиент получает scoped virtual key (5 алиасов, вкл. swift), не
master key.

## Контуры развёртывания

- **Локальный:** `.env` (gitignored, из `.env.example`) +
  `docker compose --env-file .env -f deploy/compose.yml up -d`; публикация
  `127.0.0.1:4000`.
- **governetics:** проект панели с тем же шаблоном в `compose_template`; ключи — на шаге
  Configure (`LLM_GATE_BIND` = адрес узла `10.0.0.110`, достижимый для edge); внешний
  HTTPS — host-based маршрут g9s-edge `llm-gate.lab.governetics.ru` →
  `reverse_proxy 10.0.0.110:4000` (нода `g9s-minipc-firebat`); прямой порт 4000 из LAN
  отвечает by design; из интернета узел за NAT по топологии сети (не проба шлюза —
  топологический факт). Секреты контуров независимы (у
  каждого свой salt).

## Подключение клиентов

Claude Code: `ANTHROPIC_BASE_URL` (без `/v1`) + `ANTHROPIC_AUTH_TOKEN` = virtual key +
модельные env по ролям (`ANTHROPIC_MODEL=opus`, Fable=`fable`, Sonnet=`sonnet`,
Haiku/субагенты/auto=`haiku`), контекстные 1M-переменные — на клиенте.
Discovery (`CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1`) отдаёт алиасы шлюза в
пикер `/model`. OpenCode: `model`=`opus`/`fable`, `small_model`=`haiku`.
Операторские детали (профили, ловушка cwd-перехвата) — README.

## Скрипты

| Скрипт | Назначение |
|---|---|
| `scripts/smoke.sh` | real-env smoke (5 шагов: auth-negative, models, messages, SSE, tool_use); `BASE_URL` (умолчание — remote FQDN), `SMOKE_KEY` — virtual key |
| `scripts/backup.sh` | `pg_dump --clean --if-exists` в gzip + проверка целостности архива; напоминание хранить salt/master с дампом |
| `scripts/restore.sh` | restore поверх живой БД, `ON_ERROR_STOP`, подтверждение `--yes`/`RESTORE_YES=1` |

## Тестовый слой

pytest: L0 — пины шаблона (ключи/инварианты/hash-лейбл/gitignore); L1 — рендер
`docker compose config` (fail-loud подстановки); L2 — панельный парсер governetics
(прогоняется при `GOVERNETICS_ROOT`, без него skip). Реестр прогонов — сессии impl.
