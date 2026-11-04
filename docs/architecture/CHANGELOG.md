# CHANGELOG — семантический лог архитектуры

Семантический лог архитектуры проекта. Записи — сверху, новые первыми; формат
записи: дата + Added/Changed/Removed по смыслу изменения архитектуры. Одно
изменение — одна запись; ссылка на решение (`D-NNN`), если оно есть.

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
