# Architecture Decision Records — Index

Навигационный индекс ADR. Каждое решение = отдельный файл в этом каталоге
(`D-NNN-<slug>.md`); non-md артефакты решения — в sidecar-директории `D-NNN/`.
Новое решение = новый файл + новая строка ниже.

Политика индекса — **prune разрешён**: SUPERSEDED ADR удаляется из таблицы с
пометкой в git-истории; сам файл может остаться (на него смотрят cross-ref).
Амендменты живут append-only секциями `## Amendment A-N` внутри файла ADR.

## Активные

| ID | Дата | Статус | Решение (1 строка) | Амендменты | Файл |
|---|---|---|---|---|---|
| D-001 | 2026-11-04 | ACTIVE | Артефакт: единый compose-шаблон (litellm+db), native `/v1/messages` passthrough, владение конфигом БД/UI vs YAML (dual-write запрещён) | — | [D-001-artefakt-llm-gate.md](D-001-artefakt-llm-gate.md) |
| D-002 | 2026-11-04 | ACTIVE | Контракт governetics: x-g9s-config 5 ключей, fail-loud `${KEY:?}`, invisible-секреты, content-only configs, db без host-портов, restart вместо depends_on | — | [D-002-kontrakt-governetics.md](D-002-kontrakt-governetics.md) |

## Superseded / dropped

| ID | Дата | Кем заменён | Файл |
|---|---|---|---|
| _(пусто)_ | | | |
