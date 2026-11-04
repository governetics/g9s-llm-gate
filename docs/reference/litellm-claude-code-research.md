---
title: LiteLLM как gateway для Claude Code — результаты изысканий
type: research
status: verified-reference
date: 2026-11-04
scope: Claude Code CLI, Kimi, GLM, model-based routing, fallback
---

# LiteLLM как gateway для Claude Code — результаты изысканий

Документ фиксирует результаты изучения официальной документации и локальных
экспериментов. Это не план реализации и не набор предполагаемых архитектурных
решений. Формулировки разделены на подтверждённые документацией возможности,
локально наблюдавшееся поведение и явно обозначенные границы исследования.

## 1. Основные установленные факты

- LiteLLM Proxy предоставляет Anthropic-совместимый endpoint
  `POST /v1/messages` и может возвращать Anthropic-форматированные ответы,
  включая SSE streaming и `tool_use`, даже когда upstream-модель принадлежит
  не Anthropic.
- Claude Code подключается к такому proxy через `ANTHROPIC_BASE_URL` и
  `ANTHROPIC_AUTH_TOKEN`.
- Маршрутизация выполняется по значению поля `model` в запросе. Публичное имя
  `model_name` в конфигурации LiteLLM связывается с конкретным provider/model
  upstream или с несколькими deployments.
- Один и тот же `model_name` может обслуживаться несколькими deployments:
  это используется для балансировки, нескольких ключей, регионов или резервных
  endpoint'ов.
- Fallback может направлять запрос на модель другого провайдера. Для клиента
  успешный fallback прозрачен: повторять запрос или менять модель на стороне
  Claude Code не требуется.
- Публичные алиасы моделей не обязаны совпадать с upstream model ID. Поэтому
  четыре используемых класса — `top`, `optimal`, `fast`, `cheap` — могут быть
  представлены четырьмя независимыми `model_name`. Количество алиасов не
  обязано совпадать с количеством физических моделей или провайдеров.
- Семантическая классификация задачи не является основным механизмом
  маршрутизации LiteLLM. Основной маршрут задаёт клиент через `model`;
  дополнительное поведение определяется deployment-конфигурацией, retries,
  cooldown и fallback-правилами.

## 2. Протоколы и роль LiteLLM

### 2.1 Унифицированный Anthropic `/v1/messages`

Официальная документация описывает унифицированный endpoint как
cross-provider интерфейс: клиент отправляет Anthropic Messages API request,
LiteLLM преобразует его для выбранного upstream и преобразует ответ обратно.

Подтверждены:

- Anthropic-совместимый ответ;
- streaming через SSE;
- tool definitions с `name`, `description`, `input_schema`;
- `tool_choice`;
- `tool_use` в ответе и `stop_reason: tool_use`;
- работа с провайдерами, поддерживаемыми LiteLLM, включая Anthropic, OpenAI,
  Azure, Gemini, Vertex AI и Bedrock;
- cost tracking, logging, end-user tracking, fallbacks, load balancing и
  guardrails.

Это не просто passthrough к Anthropic: upstream может быть моделью другого
вендора.

### 2.2 Отдельный режим native `/v1/messages` passthrough

У LiteLLM также задокументирован native passthrough для OpenAI-compatible
провайдеров, которые сами поддерживают Anthropic Messages API.

В этом режиме документация фиксирует:

- opt-in через `model_info.supported_endpoints`, например:

  ```yaml
  model_info:
    supported_endpoints:
      - /v1/chat/completions
      - /v1/messages
  ```

- передачу Anthropic request body без преобразования на
  `{api_base}/v1/messages`;
- отправку `Authorization: Bearer <api_key>`;
- значение `anthropic-version: 2023-06-01` по умолчанию;
- передачу `anthropic-beta` headers;
- ограничение Anthropic-only расширений `cache_control` до
  `{"type":"ephemeral"}` для строгих провайдеров, если отдельно не включён
  `model_info.cache_control_ttl: true`;
- сохранение `cache_control` без такого ограничения для встроенных
  `anthropic/`, `bedrock/` и `vertex_ai/` providers.

Это отдельный задокументированный режим, не идентичный универсальному
преобразованию протокола из раздела 2.1.

## 3. Подключение Claude Code к LiteLLM

Официальная последовательность из документации LiteLLM:

```bash
uv tool install 'litellm[proxy]'
litellm --config /path/to/config.yaml

export ANTHROPIC_BASE_URL="http://127.0.0.1:4000"
export ANTHROPIC_AUTH_TOKEN="$LITELLM_MASTER_KEY"
```

Установленные особенности:

- `/v1` не добавляется к `ANTHROPIC_BASE_URL`: Claude Code сам обращается к
  `/v1/messages`.
- В `--model`, `/model`, `ANTHROPIC_MODEL` и связанных настройках используется
  публичный `model_name`, а не обязательно provider-qualified upstream ID из
  `litellm_params.model`.
- Master key открывает доступ ко всем моделям proxy. Виртуальные ключи могут
  ограничивать доступные модели и результаты model discovery.

Пример выбора модели:

```bash
claude --model PUBLIC_MODEL_NAME
```

### 3.1 Gateway model discovery

Для Claude Code v2.1.129+ документирован opt-in:

```bash
export CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1
```

После этого Claude Code запрашивает у gateway `GET /v1/models`, а `/model`
может показывать обнаруженные модели без перезапуска.

Особенности discovery, зафиксированные документацией LiteLLM:

- discovery не включён по умолчанию;
- без него picker показывает встроенный Anthropic-набор;
- picker сохраняет gateway ID, содержащие `claude` или `anthropic`; для
  отображения других моделей документация предлагает совместимый routing ID,
  например `kimi-k3-claude-compatible`;
- `model_info.display_name` задаёт человекочитаемое имя, не меняя routing ID;
- явное указание model alias через `--model` или environment variables не
  зависит от отображения модели в picker.

Локально использовалась версия Claude Code `2.1.318`, поэтому требование
версии для discovery выполняется. Сам discovery через LiteLLM локально не
тестировался.

### 3.2 Модельные роли Claude Code

В исследованных конфигурациях Claude Code используются следующие переменные:

- `ANTHROPIC_MODEL`;
- `ANTHROPIC_DEFAULT_FABLE_MODEL`;
- `ANTHROPIC_DEFAULT_OPUS_MODEL`;
- `ANTHROPIC_DEFAULT_SONNET_MODEL`;
- `ANTHROPIC_DEFAULT_HAIKU_MODEL`;
- `CLAUDE_CODE_SUBAGENT_MODEL`;
- `CLAUDE_CODE_AUTO_MODE_MODEL`.

Поскольку LiteLLM маршрутизирует каждый запрос по его `model`, эти роли могут
ссылаться на разные публичные алиасы proxy. Это является механизмом выбора
маршрута по классам моделей, а не встроенной семантической классификацией
задач LiteLLM.

## 4. Конфигурационная модель маршрутизации

Документированная структура связывания:

```yaml
model_list:
  - model_name: PUBLIC_ALIAS
    litellm_params:
      model: PROVIDER_QUALIFIED_UPSTREAM_MODEL
      api_key: os.environ/UPSTREAM_API_KEY
```

Свойства модели:

- `model_name` — имя, которое отправляет клиент;
- `litellm_params.model` — upstream provider/model;
- credentials и другие upstream-параметры принадлежат deployment и не требуются
  Claude Code;
- несколько записей с одинаковым `model_name` образуют группу deployments;
- fallback ссылается на логические `model_name`, а не обязательно на конкретный
  upstream provider.

Для четырёх классов моделей эта модель допускает такие публичные имена, как
`top`, `optimal`, `fast`, `cheap`. Документация не требует, чтобы каждому такому
имени соответствовал уникальный вендор или уникальная физическая модель.

## 5. Fallback: подтверждённое поведение

### 5.1 Общий fallback

Документированный синтаксис:

```yaml
router_settings:
  fallbacks:
    - model-a: ["model-b", "model-c"]
    - model-b: ["model-a"]
  allowed_fails: 3
  cooldown_time: 30

litellm_settings:
  num_retries: 3
  request_timeout: 10
```

Числовые значения воспроизводят пример документации и не являются настройками,
подобранными для coding-агента.

Установлено:

- targets перебираются в указанном порядке;
- fallback target может использовать другого провайдера и другой API key;
- общий fallback выполняется после исчерпания retries для оставшихся ошибок,
  включая rate limit и серверные сбои;
- `num_retries` задаёт retries до general failover;
- `request_timeout` превращает превышение времени ожидания в ошибку;
- `allowed_fails` и `cooldown_time` управляют временным выведением deployment
  из доступных;
- `num_retries: 0` отключает sibling retries, но не order-based или cross-group
  failover.

### 5.2 Специальные fallback-цепочки

| Настройка | Подтверждённое назначение |
|---|---|
| `router_settings.fallbacks` | Общие сбои после retries |
| `litellm_settings.default_fallbacks` | Цепочка по умолчанию при отсутствии model-specific правила |
| `litellm_settings.context_window_fallbacks` | `litellm.ContextWindowExceededError` |
| `litellm_settings.content_policy_fallbacks` | `litellm.ContentPolicyViolationError` |

Дополнительные факты:

- model-specific fallback заменяет `default_fallbacks` для данной модели;
- context-window chain имеет описанный в документации приоритет над более
  поздними order levels и general fallbacks; при исчерпании такой цепочки
  возвращается ошибка;
- локальная pre-call проверка превышения контекста требует
  `router_settings.enable_pre_call_checks: true`; без неё oversized request
  отправляется upstream;
- fallback может ссылаться на конкретный `model_info.id`; документация отдельно
  отмечает пропуск cooldown check для такого fallback deployment;
- клиент может отключить все proxy fallbacks для запроса через
  `disable_fallbacks: true`; аналогичная настройка возможна в key metadata.

### 5.3 Что видит клиент и система наблюдения

При успешном fallback клиент получает ответ резервной модели без собственного
failover loop.

Для диагностики документированы:

- `metadata.attempted_fallbacks`;
- `metadata.original_model_group`;
- response header `x-litellm-model-id` для определения обслужившего deployment.

Проверки доступа и бюджета применяются и к fallback targets. Если target
запрещён для key/team/project или недоступен по бюджету, он пропускается. Если
подходящих targets не остаётся, клиент получает ошибку исходной модели.

Fallback реагирует на технические и явно классифицированные ошибки. HTTP 200 с
низким качеством ответа, нарушенной инструкцией или непригодным tool call сам
по себе не является задокументированным триггером failover.

## 6. Уже установленные параметры Kimi и GLM

Следующие сведения получены из локальных рабочих профилей и экспериментов, а
не из предположения о возможной конфигурации. Секретные ключи в документ не
включены.

| Параметр | Kimi | GLM |
|---|---|---|
| Anthropic-compatible base URL | `https://api.kimi.ai/coding/` | `https://api.z.ai/api/anthropic` |
| Auth-поле в текущем профиле | `ANTHROPIC_API_KEY` | `ANTHROPIC_AUTH_TOKEN` |
| Основная модель | `k3.1-pro[1m]` | `glm-5.3[1m]` |
| Быстрый вариант | `k3.1-pro-highspeed` | `glm-5.3-flash[1m]` |
| Текущий auto mode classifier | `k3.1-pro-highspeed` | `glm-5.3-flash[1m]` |

Локально подтверждено:

- оба endpoint'а используются Claude Code напрямую через Anthropic-compatible
  подключение;
- основные и быстрые model ID принимаются соответствующими endpoint'ами;
- субагенты в текущих профилях направлены на быстрые варианты;
- контекстные настройки профилей включают
  `CLAUDE_CODE_AUTO_COMPACT_WINDOW=1000000` и
  `CLAUDE_CODE_MAX_CONTEXT_TOKENS=1000000`.

В рамках изысканий подтверждены только перечисленные варианты моделей. Данных,
которые однозначно распределяли бы четыре класса `top`, `optimal`, `fast`,
`cheap` между ними, нет. Назначение этих классов не зафиксировано как факт.

### Граница проверенного

Прямая работа Claude Code с этими endpoint'ами не является тестом их работы
через LiteLLM. Конкретный `litellm_params.model`, adapter/passthrough-режим и
полный upstream YAML для подписочных Kimi Coding и Z.ai Coding endpoint'ов в
ходе изысканий не запускались и не проверялись. Поэтому такие значения здесь
не выдумываются и не представляются как установленные.

## 7. Auto mode и специфика Anthropic-функций

Исследование auto mode установило:

- server-side classifier review использует Anthropic-специфичные поля
  `safeguards` и `safeguard_results`;
- произвольный Anthropic-compatible endpoint не обязан реализовывать эту
  серверную функциональность;
- в локальных профилях Kimi и GLM применяется
  `CLAUDE_CODE_AUTO_MODE_SERVER=0`, переводящий проверку на отдельные клиентские
  запросы классификатора;
- `CLAUDE_CODE_AUTO_MODE_MODEL` задаёт модель для этих отдельных запросов;
- GLM-flash в локальных тестах формировал allow и контекстно обоснованный deny;
- Kimi показал allow, deny и эскалацию к пользователю; также наблюдались
  временные classifier timeouts и `Stage 2 classifier error`, которые
  блокировали действие fail-closed.

Совместная работа auto mode через LiteLLM не тестировалась. Документированная
маршрутизация LiteLLM по `model` и локальная работа клиентского classifier —
подтверждены независимо; их совместная интеграция не входит в список
проверенных фактов.

## 8. Context window и metadata модели

Документация LiteLLM разделяет две области:

- `model_info.max_input_tokens` влияет на metadata LiteLLM и pre-call checks;
- отображаемый Claude Code context window и его compaction behavior этим полем
  не настраиваются.

Для Claude Code в документации LiteLLM названы
`CLAUDE_CODE_AUTO_COMPACT_WINDOW` и `autoCompactWindow` как отдельные настройки.
Это согласуется с тем, что текущие локальные профили задают context-related
переменные независимо от model ID.

## 9. Применение за пределами Claude Code

Установлено, что LiteLLM является общим LLM gateway, а не только адаптером для
Claude Code:

- Anthropic Messages API используется Claude Code и другими
  Anthropic-compatible клиентами;
- OpenAI-compatible API может обслуживать desktop, mobile, web UI и
  собственные клиенты;
- виртуальные ключи позволяют разграничивать модели и бюджеты;
- model aliases скрывают upstream provider/model от клиента;
- общие fallback и observability действуют на уровне gateway.

При этом заявленная клиентом «OpenAI-compatible» поддержка не означает
поддержку всего OpenAI API. В исследовании основным общим форматом назван
`POST /v1/chat/completions`; Responses API, файлы, audio, embeddings и другие
возможности являются отдельными поверхностями совместимости.

## 10. Источники

Официальная документация:

1. [LiteLLM — Use Claude Code with non-Anthropic models](https://docs.litellm.ai/docs/tutorials/claude_non_anthropic_models)
2. [LiteLLM — unified Anthropic `/v1/messages`](https://docs.litellm.ai/docs/anthropic_unified/)
3. [LiteLLM — native `/v1/messages` passthrough](https://docs.litellm.ai/docs/anthropic_unified/native_passthrough)
4. [LiteLLM — Reliable AI Gateway: fallbacks, retries, timeouts](https://docs.litellm.ai/docs/proxy/reliability)
5. [LiteLLM — routing and load balancing](https://docs.litellm.ai/docs/routing)
6. [LiteLLM — proxy `config.yaml`](https://docs.litellm.ai/docs/proxy/configs)
7. [Claude Code — permission modes и classifier review](https://code.claude.com/docs/en/permission-modes)
8. [Claude Code — auto mode classifier requests](https://code.claude.com/docs/en/auto-mode-classifier-billing)

Локальные свидетельства от 2026-11-04:

- `~/.claude/settings.kimi.json` и `~/.claude/settings.glm.json` (использовались
  только endpoint/model/auth-field names, без переноса секретов);
- Claude Code `2.1.318`;
- локальные проверки direct-подключений и auto mode classifier для Kimi/GLM.
