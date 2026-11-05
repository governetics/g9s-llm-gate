# g9s-llm-gate

Docker-шлюз на LiteLLM: единая точка подключения coding-агентов (Claude Code, OpenCode) к
LLM-провайдерам. Начальный контур — провайдеры Kimi и GLM по протоколу Anthropic
(`/v1/messages`). Один и тот же compose-шаблон разворачивается в двух контурах:

- **локальный** — `docker compose` на рабочей машине (публикация `127.0.0.1:4000`);
- **remote** — платформа governetics (панель + edge-прокси, HTTPS
  `llm-gate.lab.governetics.ru`, нода `g9s-minipc-firebat`).

Разделение ответственности — один хозяин на область:

- **модели, ключи провайдеров, virtual keys** — в PostgreSQL через Admin UI (смена модели
  живьём, без правки YAML и рестарта);
- **routing-политика** (fallback между провайдерами, повторы) — в YAML шаблона,
  версионирована вместе с артефактом.

| Сервис | Образ | Назначение |
|---|---|---|
| `litellm` | `ghcr.io/berriai/litellm:v1.108.0` | прокси `/v1/messages` + Admin UI (`:4000`) |
| `db` | `postgres:16.15` | модели/credentials/virtual keys/spend (named volume `db-data`) |

**Статус:** стадия exploration; фазы 0–2 завершены (спайк, локальный стек, деплой под
governetics — remote smoke 5/5); фаза 3 (приёмка, hardening) в работе.

Документация: as-is — [docs/architecture/architecture.md](docs/architecture/architecture.md);
решения — [docs/architecture/decisions/decisions-log.md](docs/architecture/decisions/decisions-log.md);
план реализации — [docs/project/implementation-plan.md](docs/project/implementation-plan.md);
бэклог — [docs/project/backlog.md](docs/project/backlog.md).

---

## 1. Быстрый старт (локальный контур)

1. `cp .env.example .env` и заполнить значения. Команды генерации — в самом
   `.env.example`:

   ```sh
   python3 -c "import secrets; print('sk-' + secrets.token_urlsafe(32))"   # master key
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"           # salt key
   python3 -c "import secrets; print(secrets.token_hex(24))"               # postgres password
   ```

   - master key **обязан** начинаться с `sk-` (см. «Известные пределы»);
   - пароль postgres — только буквы/цифры: значение встраивается в `DATABASE_URL`.

2. `docker compose --env-file .env -f deploy/compose.yml up -d`

   `--env-file` обязателен: compose ищет `.env` в каталоге `deploy/`, а не в корне
   репозитория.

3. Дождаться liveliness (первый старт гоняет Prisma-миграции, `start_period` до 300 с;
   строки «errors» в логе контейнера — имя миграции, не ошибка):

   ```sh
   curl -fsS http://127.0.0.1:4000/health/liveliness   # -> HTTP 200
   ```

## 2. Настройка после старта (Admin UI)

UI: `http://127.0.0.1:4000/ui` — логин `admin`, пароль — master key (до создания
DB-админа; hardening фазы 3 это меняет).

### Модели (5)

Models → Add Model. Ключ провайдера вводится **в определении модели** (поле `api_key` в
`litellm_params`; раздел LLM Credentials в v1.108.0 OpenAI-compatible провайдеров не
знает). Ключи берутся в личных кабинетах подписок (Kimi Coding — kimi.com, Z.ai Coding
— z.ai); одни и те же ключи годятся для обоих контуров. Публичное имя (`model_name`) —
алиас-класс; upstream-модель — серверный ID провайдера:

Алиасы названы по ролям слотов Claude Code (решения оператора 2026-11-04/05:
GLM — рабочая лошадь кодинга и весь лёгкий контур, Kimi — рассуждения;
`swift` — полка Kimi-fast, цель страховки лёгких слотов):

| Алиас | Upstream (`model`) | `api_base` | Режим |
|---|---|---|---|
| `fable` | `k3.1-pro` | `https://api.kimi.ai/coding/` | passthrough |
| `opus` | `glm-5.3` | `https://api.z.ai/api/anthropic` | passthrough |
| `sonnet` | `glm-5.3-flash` | `https://api.z.ai/api/anthropic` | passthrough |
| `swift` | `k3.1-pro-highspeed` | `https://api.kimi.ai/coding/` | passthrough |
| `haiku` | `glm-5.3-flash` | `https://api.z.ai/api/anthropic` | passthrough |

Режим passthrough: `supported_endpoints: ["/v1/messages"]` — шлюз переводит
Anthropic-протокол как есть, без конвертации. Вписывается в поле **Model Info (JSON)**
формы Add Model целиком объектом:
`{"supported_endpoints": ["/v1/messages"]}`.

> **Модельные ID — без суффикса `[1m]`.** Суффикс `[1m]` — клиентская нотация Claude Code
> (см. раздел 3); серверных моделей с `[1m]` не существует, шлюз о нём не знает.

### Virtual key для Claude Code

Virtual Keys → Create Key: scope — все 5 алиасов (включая `swift`: без него fallback лёгких слотов будет молча пропускаться — LiteLLM проверяет scope у fallback-целей), бюджет/лимиты по желанию. Ключ
`sk-…` показывается один раз — сохранить. Клиент получает **virtual key**, не master.

### Классы и fallback

Fallback между провайдерами настраивается в `deploy/compose.yml` (`configs.policy_yaml`)
и ссылается на алиасы:

| Класс | Primary | Fallback |
|---|---|---|
| `fable` (рассуждения/анализ/ревью) | Kimi `k3.1-pro` | `opus` = GLM `glm-5.3` |
| `opus` (основная работа) | GLM `glm-5.3` | `fable` = Kimi `k3.1-pro` |
| `sonnet` (быстрый лёгкий контур) | GLM `glm-5.3-flash` | `swift` = Kimi `k3.1-pro-highspeed` |
| `haiku` (субагенты/auto/механика) | GLM `glm-5.3-flash` | `swift` = Kimi `k3.1-pro-highspeed` |
| `swift` (полка страховки, вручную) | Kimi `k3.1-pro-highspeed` | `sonnet` = GLM `glm-5.3-flash` |

## 3. Подключение Claude Code

Профиль (settings-файл или env сессии):

| Переменная | Значение |
|---|---|
| `ANTHROPIC_BASE_URL` | `http://127.0.0.1:4000` (локально; без `/v1`) · `https://llm-gate.lab.governetics.ru` (remote) |
| `ANTHROPIC_AUTH_TOKEN` | virtual key `sk-…` |
| `ANTHROPIC_MODEL` | `opus` |
| `ANTHROPIC_DEFAULT_FABLE_MODEL` | `fable` |
| `ANTHROPIC_DEFAULT_OPUS_MODEL` | `opus` |
| `ANTHROPIC_DEFAULT_SONNET_MODEL` | `sonnet` |
| `ANTHROPIC_DEFAULT_HAIKU_MODEL` | `haiku` |
| `CLAUDE_CODE_SUBAGENT_MODEL` | `haiku` (важные ревью — явный `--model fable`) |
| `CLAUDE_CODE_AUTO_MODE_MODEL` | `haiku` (клиентский классификатор) |
| `CLAUDE_CODE_AUTO_COMPACT_WINDOW` / `CLAUDE_CODE_MAX_CONTEXT_TOKENS` | `1000000` — 1M-контекст |
| `CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY` | `1` — пикер `/model` покажет алиасы (CC ≥ 2.1.129) |

- **1M-контекст — две равнозначные клиентские ручки:** env выше или суффикс `[1m]` в
  селекте модели (`opus[1m]`). Claude Code вырезает суффикс до отправки — шлюз получает
  голый алиас, серверной роли у суффикса нет.
- Не полагайтесь на пикер `/model` как на основной канал выбора: по документации
  LiteLLM ID без `claude`/`anthropic` в имени могут не сохраняться выбором — основная
  модель задаётся env профиля, пикер вторичен.
- OpenCode: `model` = `opus` (тяжёлые задачи — `fable`), `small_model` = `haiku`.

Проверка: `claude -p 'Reply with exactly: pong' --model opus` — ответ приходит через шлюз.

## 4. Remote-контур (панель governetics)

Панель governetics — внутренняя платформа управления узлами команды (доступ — у
оператора; README предполагает, что вы в ней уже работаете).

1. Проект панели: `compose_template` = содержимое [deploy/compose.yml](deploy/compose.yml)
   целиком (`project_type` docker-compose).
2. Шаг Configure — 5 ключей:
   - `LLM_GATE_BIND` — адрес узла, достижимый для edge (`10.0.0.110`; host-loopback из
     edge недостижим);
   - `LLM_GATE_PORT` — `4000`;
   - `LLM_GATE_MASTER_KEY` / `LLM_GATE_SALT_KEY` / `LLM_GATE_POSTGRES_PASSWORD` —
     секреты remote-контура, **отдельные** от локального (у каждого контура свой salt).
3. Маршрут g9s-edge (настраивает оператор edge): host-based
   `llm-gate.lab.governetics.ru` → `reverse_proxy 10.0.0.110:4000` (не path-based).
4. Deploy → `converged`. Холодный старт с Prisma-миграциями переживается самим деплоем.
5. **Повторить раздел 2 против remote-контура**: у ноды своя пустая БД — 4 модели и
   virtual key заводятся в Admin UI `https://llm-gate.lab.governetics.ru/ui` (логин —
   remote master key) отдельно от локального контура. Smoke ниже требует именно
   remote-virtual key.
6. Smoke:

   ```sh
   SMOKE_KEY=sk-… scripts/smoke.sh
   ```

   5 шагов через `https://llm-gate.lab.governetics.ru`: auth-negative, models, messages,
   SSE, tool_use. Для локального стека: `BASE_URL=http://127.0.0.1:4000 SMOKE_KEY=… scripts/smoke.sh`.

## 5. Эксплуатация

### Бэкап / восстановление

```sh
scripts/backup.sh                          # дамп ./backups/llm-gate-<ts>.sql.gz (gitignored)
scripts/restore.sh <файл.sql.gz> --yes     # restore ПОВЕРХ живой БД
```

- `DB_CONTAINER` — имя db-контейнера (умолчание `deploy-db-1` — локальный контур; на
  ноде панели имя другое — переопределить).
- Дамп **не самодостаточен**: credentials в нём зашифрованы `LLM_GATE_SALT_KEY` (не
  ротируется, потеря = потеря всех credentials), UI-логин — `LLM_GATE_MASTER_KEY`.
  Хранить оба ключа вместе с дампом (backup.sh напоминает в каждом прогоне).
- Дамп несёт `DROP … IF EXISTS` (`--clean --if-exists`): restore срабатывает и по пустой,
  и по живой БД; `ON_ERROR_STOP` роняет restore при первой SQL-ошибке, полувосстановление
  исключено.

### Обслуживание

- **Обновление пина LiteLLM** — процедура: бэкап → смена тега в шаблоне → up → проверка
  (на старте гоняются Prisma-миграции). Никакого `latest`.
- **«Снять с узла» в панели** удаляет named volume — это потеря всей БД (модели, ключи,
  spend). Бэкап заранее.
- **Смена модели/перевода upstream** — через UI живьём, без правки YAML. Но:
  - fallback-политика YAML ссылается на **имена алиасов**: переименование алиаса = правка
    `policy_yaml` в шаблоне + пересчёт hash-лейбла `llmgate.policy-sha256`, иначе
    fallback молча теряет цель. Пересчёт (первые 16 hex sha256 контента) — прогон
    `python3 -m pytest tests` подскажет ожидаемое значение ассерта; либо посчитать:

    ```sh
    python3 -c "import hashlib,yaml,pathlib; c=yaml.safe_load(pathlib.Path('deploy/compose.yml').read_text())['configs']['policy_yaml']['content']; print(hashlib.sha256(c.encode()).hexdigest()[:16])"
    ```
  - UI-переименование алиаса обновляет scope существующих virtual keys; API-путь
    delete+new — нет (ключ остаётся на старом имени → 403; лечится `/key/update`).

### Проверки разработки

```sh
python3 -m pytest tests                                        # без панельного парсера (skip)
GOVERNETICS_ROOT=<checkout governetics> python3 -m pytest tests  # полный прогон
```

`<checkout governetics>` — локальный checkout репозитория платформы (приватный,
есть у команды) с его `.venv`; без него тест парсера честно скипается — панельные
гейты (`env_precedence`, `bind_mounts`, tag-pattern) проверяет только полный
прогон; перед деплоем панели он обязателен.

Имя db-контейнера на ноде панели отличается от локального `deploy-db-1`; узнать:
`docker ps | grep db` на самой ноде, и передать в `DB_CONTAINER=… backup.sh`.

## 6. Известные пределы и якоря

- **Master key требует префикса `sk-`** — LiteLLM его проверяет, панель нет: ключ без
  `sk-` проходит Configure/Deploy, но UI-логин после этого молча не работает.
- **`SMOKE_KEY` виден в argv curl** (список процессов узла). Single-user-окружение —
  приемлемо; multi-user — передавать заголовок файлом (curl `-H @file`).
- **`visibility: invisible` не защищает от `docker inspect`** на узле — предел платформы.
- **Mid-stream fallback не обещаем** — переключение только при ошибке до начала ответа.
- **`PROXY_BASE_URL` не задан** — нужен только SSO/OAuth-MCP-фичам LiteLLM; появится
  потребность — добавить ключ в шаблон.
- **Auto mode** — классификатор клиентский, его таймауты шлюзом не настраиваются;
  подтверждение живой CC-сессией — приёмка фазы 3.
- **Прямой доступ к 4000 из LAN на remote — by design** (BIND публикует адрес для edge);
  из интернета узел закрыт NAT по топологии сети (знание оператора о своей сети;
  эмпирически из внешней точки эта сессия не проверяла).

## 7. Troubleshooting

- **Claude Code уходит мимо шлюза.** При старте CC в домашнем каталоге файл
  `~/.claude/settings.json` действует как **проектный** settings (cwd-правило
  `<dir>/.claude/`), и его env перекрывает shell-env профиля. Лечится: чистый cwd при
  запуске, изоляция `CLAUDE_CONFIG_DIR` в песочницах, боевой отдельный профиль.
- **Test Connection в UI красный.** Кнопка шлёт `chat/completions`-пробу; для
  passthrough-моделей (`/v1/messages`) она всегда красная и **не показатель**. Проверка —
  реальный запрос `/v1/messages` (smoke-скрипт или CC).
- **`/health/liveliness` vs `/health`.** Liveliness/readiness — без авторизации и без
  трат токенов, годятся в пробы; `/health` шлёт реальные запросы провайдерам — в пробы не
  ставить.
- **«Invalid model name» / пустой `/v1/models`.** Образ LiteLLM без явного `--config`
  стартует с пустым model list; в нашем шаблоне `command: [--config, …]` уже есть —
  симптом актуален только при ручных запусках образа мимо шаблона.

## 8. Документация

- Текущее состояние — [docs/architecture/architecture.md](docs/architecture/architecture.md).
- Решения: [D-001](docs/architecture/decisions/D-001-artefakt-llm-gate.md) (артефакт) ·
  [D-002](docs/architecture/decisions/D-002-kontrakt-governetics.md) (контракт governetics) ·
  [индекс](docs/architecture/decisions/decisions-log.md).
- План реализации — [docs/project/implementation-plan.md](docs/project/implementation-plan.md).
- Бэклог — [docs/project/backlog.md](docs/project/backlog.md).
