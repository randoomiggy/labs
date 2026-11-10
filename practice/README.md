# Practice

Небольшие самостоятельные упражнения, а не готовые production-системы.
`BACKLOG.json` содержит начальные предложения, не список выполненных тем.
Начать с [EP-001: потоковой сводки лога](ep001_log_summary/README.md):
реализация, тесты и подробный разбор кода и устройства проекта.

Будущая задача получает каталог `practice/<slug>/` с:

- README: оригинальное условие своими словами, source/terms, контракт входа и
  выхода, объяснение, run/test commands, ограничения и complexity.
- Полной реализацией с английскими identifiers и синтетическими fixtures.
- `test_*.py` на stdlib `unittest`: normal, boundary и invalid-input cases.
- Честным описанием AI assistance; результаты только реально выполненных тестов.

Первый scope — `practice/ep001_log_summary`: потоковый summary простого
синтетического HTTP-журнала; точный контракт находится в acceptance EP-001.
Все 14 seed-задач проверяются offline, без Docker/cloud/paid APIs/packages.

`depends_on` — педагогические подсказки, не факт approval, публикации или mastery.
Новый пример запрещён, пока более ранние proposals не обработаны и явно не
одобрены для коммита. Pending/rejected/revision_requested блокируют переход;
живой запрос может разрешить доработку активного упражнения. При разрешённом
выборе отсутствующий код включается в самодостаточный bundle, но это не обход
serial gate. Нельзя применять неутверждённый prerequisite как будто он принят.

Подготовка идёт в private `.local/`, не прямо в этой директории. Версия snapshot,
manifest fingerprint, реальные проверки и live decision описаны в
[`docs/WORKFLOW.md`](../docs/WORKFLOW.md). Helper не применяет файлы; будущая
application/publication требует отдельной разрешённой live-процедуры.
