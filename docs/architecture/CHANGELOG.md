# CHANGELOG — семантический лог архитектуры

Семантический лог архитектуры проекта. Записи — сверху, новые первыми; формат
записи: дата + Added/Changed/Removed по смыслу изменения архитектуры. Одно
изменение — одна запись; ссылка на решение (`D-NNN`), если оно есть.

## 2026-11-25

### Changed

- Routing-политика переведена из запечённого в шаблон `configs.policy_yaml` в
  **per-node файл панели** (`proxy_server_config.yaml`, группа `files`
  заголовка; эталон `deploy/policy.yaml`, локальный override
  `deploy/compose.local.yml`); hash-лейбл ушёл, изменение значения =
  Deploy + Restart (Amendment 5 к D-001; контракт панели — D-002).
- Лёгкие слоты поменяны первичными upstream'ами: `sonnet` = GLM flash → Kimi
  highspeed, `haiku` = Kimi highspeed → GLM flash — классификатор auto mode
  Claude Code (по умолчанию едет на sonnet-слоте) больше не зависит от фаз
  таймаутов Kimi (Amendment 5 к D-001). `opus` → GLM `glm-5.4` (проверено
  живьём на обеих подписках; лёгкого «5.4-flash» у провайдера нет).

## 2026-11-23

### Changed

- Единая раскладка на всех экземплярах шлюза (канон 4 имён): `sonnet`
  возвращён на Kimi `k3.1-pro-highspeed` (fallback `haiku` = GLM flash) —
  осознанная отмена решения 2026-11-05 ради одинаковой раскладки; полка
  `swift` из канона убрана (её upstream и fallback дублируют `sonnet`).
  Policy-YAML очищена от командных имён `iflex-*`: один шаблон на все
  экземпляры. Same-name per-team роутинг на одном экземпляре существует, но
  Enterprise-лицензирован (`team_public_model_name`; чтение исходников
  v1.108.0) — вместо него экземпляр на владельца подписки: контур оператора
  на `g9s-devbox` (`llm-dev.lab.governetics.ru`), контур iflex на
  `minipc-firebat` (Amendment 4 к D-001). Развёрнуто тем же днём: оба
  экземпляра на едином шаблоне; firebat переработан — `iflex-*`
  переименованы в канон с сохранением credentials, core-контур оператора
  снят с firebat (deployments, юзер, команда, VK). Полка `swift` сохранена
  как ручной класс на обоих контурах (на firebat — токен iflex).

### Added

- Команда `iflex`: юзеры `ymakarova-iflex`/`asorin-iflex`, deployment'ы
  `iflex-*` на подписке iflex (Kimi токен жив; Z.ai токен — код 1113, ждёт
  баланса на стороне подписки), ключи с user/team-привязками и максимальными
  лимитами (наблюдение); fallback-пары `iflex-*` в политике. Команда `core`
  (оператор) на основных моделях. Statusline `gate_budget.py`. Same-name
  per-team роутинг невозможен (измерено) — `iflex-*` имена в профилях команды
  (Amendment 3 к D-001).

## 2026-11-05

### Changed

- `sonnet` переведён на GLM `glm-5.3-flash` (таймауты Kimi highspeed в лёгком
  контуре — решение оператора); добавлена полка `swift` = Kimi `k3.1-pro-highspeed`
  как цель fallback'а лёгких слотов; VK-скоп расширены на 5 алиасов
  (Amendment 2 к D-001).

## 2026-11-04

### Changed

- Алиасы моделей переименованы в роли CC-слотов: `fable`/`opus`/`sonnet`/`haiku`
  (вместо `top`/`optimal`/`fast`/`cheap`); primary тяжёлого слота — GLM `glm-5.3`,
  Kimi — рассуждения (`fable`) и быстрый контур (`sonnet`); fallback перекрёстный
  по провайдерам. Решение оператора по эксплуатации и внешним данным
  (Amendment 1 к D-001). Локальный экземпляр стенда оператора снят (сам локальный
  контур остаётся поддерживаемым артефактом).

### Added

- Документационный блок фазы 3: README-оператор (оба контура, эксплуатация, известные
  пределы, troubleshooting); architecture.md as-is (топология, passthrough, владение
  конфигурацией, алиасы/классы, контуры); ADR `D-001` (артефакт: единый шаблон,
  passthrough, владение конфигом) и `D-002` (контракт governetics). Зафиксировано
  завершение фазы 2 — деплой под governetics: edge-маршрут
  `llm-gate.lab.governetics.ru`, модели + virtual key на remote, remote smoke 5/5
  через HTTPS (D-001, D-002).

## 2026-11-04


### Added

- Артефакт развёртывания фазы 1: единый compose-шаблон `deploy/compose.yml`
  (litellm `v1.108.0` + postgres `16.15`, policy-YAML через `configs.content`
  без `model_list` — модели/credentials владеет БД/UI), `.env.example`,
  `.gitignore`; тестовый слой L0–L2 (`tests/`: пины шаблона, `docker compose
  config` fail-loud пробы, парсер governetics). Спайк фазы 0: capture-тест
  upstream-аутентификации, выбор режима native passthrough, серверные model ID
  без `[1m]`, живой fallback по 429. План: design-сессия 261104-01.
- Инициализирован репозиторий и навигационный каркас документации проекта.
