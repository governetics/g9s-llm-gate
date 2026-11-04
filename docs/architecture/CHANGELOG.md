# CHANGELOG — семантический лог архитектуры

Семантический лог архитектуры проекта. Записи — сверху, новые первыми; формат
записи: дата + Added/Changed/Removed по смыслу изменения архитектуры. Одно
изменение — одна запись; ссылка на решение (`D-NNN`), если оно есть.

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
