# Task card — EP-XXX / GH-YYYYMMDD / vN

> Шаблон, не выполненная задача. Заменить placeholders фактическими значениями.
> Не заполнять pass/count/fingerprint без реального вывода инструментов.

## Identity и review bundle

- Task key / topic / slug / scope:
- Task ID (дата America/Vancouver) / immutable version:
- Snapshot path / base Git commit / manifest fingerprint:
- Proposed repo-relative paths (полный список):
- Предыдущая версия, если есть; что изменилось и почему нужно новое согласие:
- Dependencies: педагогические подсказки; доступные проверенные файлы:
- Serial gate: новая задача разрешена только при явном `blocked=false` из `next`;
  для доработки — живой запрос по самой ранней нерешённой задаче:
- При разрешённом выборе и отсутствующем prerequisite: как bundle сделан
  самодостаточным (это не разрешает обходить pending/rejected):

## Задача и контракт

- Зачем это нужно; один небольшой измеримый результат:
- Source: original exercise либо ссылка/книга/глава; проверка terms перед копированием:
- Входной формат, допустимые значения и синтетический пример:
- Выходной формат; ошибки, malformed input, empty/boundary cases:
- Acceptance criteria:
- Non-goals и ограничения:

## Объяснение и полное решение — сразу

- Подход и ключевые решения; альтернативы и trade-offs:
- Полный код/точный diff со всеми нужными файлами; не stub и не только план:
- Как воспроизвести запуск:
- Time/space complexity, когда применимо; почему состояние ограничено или нет:
- AI assistance: что сгенерировано, что проверено человеком/инструментами:

## Реальные проверки

- Snapshot ID/version/fingerprint, к которым относятся результаты:
- Фактическая команда и test start-dir:
- Среда и существенные ограничения проверки:
- Normal cases:
- Boundary и invalid-input cases:
- Фактические test count / exit status / итог; путь к verification evidence:
- Успешно выполненные tests / skips / expected failures / driver_completed:
- verify: integrity / base_matches / test_evidence_valid / local_approval_valid:
- Реальный stdout/stderr или выдержка без PII/секретов:
- Что не проверялось; сбои/timeout/zero tests (это не pass):

## Review

- Краткая Telegram-сводка — один полезный экран без повторения полного решения.
- Полная raw-card/evidence остаётся локально; для отправки создана отдельная копия
  через `tools/report_export.py`, вне immutable snapshot. Проверен готовый export
  на home usernames/персональные пути, контакты, identifiers и секреты; snapshot
  не переписывался. Маскирование best-effort, `.gitignore` не заменяет проверку.
- Текущее состояние helper: pending / approved / rejected /
  revision_requested / superseded — только по фактическому state:
- Сообщение для пользователя: ID, версия, fingerprint, paths, решение и tests:
- Допустимый живой ответ с реальными ID/version:
  `Одобряю GH-YYYYMMDD vN` / `Отклоняю GH-YYYYMMDD vN` /
  `Доработать GH-YYYYMMDD vN`.
- Evidence решения: заполнять только после фактического matching live message,
  никогда из cron/history. До ответа: unresolved, не approval.

`approve` не применяет файлы и не делает commit/push. Публикация и её журнал —
отдельная будущая live-процедура с exact remote readback, не функция helper.
Ни решение, ни публикация сами по себе не подтверждают понимание материала.

## Необязательная личная практика

- Что пользователь хочет воспроизвести/объяснить/изменить самостоятельно:
- Вопросы, наблюдения и follow-up (не объявлять «изучено» за пользователя):
