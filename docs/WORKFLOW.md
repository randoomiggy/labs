# Workflow

## Границы и источники истины

Живой пользователь отдельно разрешил проверенную основу проекта, workflow и EP-001
публиковать в существующий `randoomiggy/labs` с текущими Git name/email.
Это не разрешение на установку, global Git config, смену visibility, другой remote
или будущие автоматические коммиты. Разрешение и выполненная публикация — разные факты.
Нет команды `apply`, `commit`, `push` или `publish`; helper не копирует payload
в tracked tree. Scaffold пока uncommitted и требует отдельного review.

После разового согласования назначения, авторства и режима публикации точный
живой ответ «Одобряю ID vN» разрешает commit + push именно показанного payload.
Повторное одобрение того же diff не требуется, если его содержимое, база и
согласованные условия не изменились. Helper лишь записывает решение;
действия с Git выполняет live assistant, никогда не утренний cron.

`AGENTS.md` — политика; `ROADMAP.md` — план; `BACKLOG.json` — очередь предложений.
Приватные snapshots, фактические проверки и решения — в gitignored `.local/`.
Helper записывает `pending`, `approved`, `rejected`, `revision_requested`,
`superseded`, но не `pushed` и не evidence публикации. В будущем live assistant
проверяет точный remote и отдельно журналирует настоящую публикацию.

## Каждый ежедневный запуск

Требуемое расписание: **09:30 local America/Vancouver**, по действующим правилам
этого часового пояса, не фиксированный UTC offset. Настройки задания находятся вне репозитория; документация сама
не подтверждает active schedule или доставку.

- `workdir` — корень проекта: это включает обычное обнаружение project context.
  `.hermes.md` / `HERMES.md` и `AGENTS.override.md` могут заменить `AGENTS.md`;
  проверить фактически загруженный контекст.
- Cron всё равно запускает свежую agent session. Skills:
  `igor-work-protocol`, `github`, `it-systems-coding-research`.
  `attach_to_session: true` помогает живому продолжению, `continuity: true`
  передаёт предыдущий вывод; ни одно не заменяет state или согласие.
- Явно прочитать `AGENTS.md`, этот документ, `docs/DECISIONS.md`, `ROADMAP.md`
  и `BACKLOG.json`; затем выполнить `status` и `next`.
- Сначала выполнить `next`: новый payload разрешён только при явном `blocked=false`,
  `blockers=[]` и выбранном `task`. Pending/revision_requested/rejected и неизвестные
  или повреждённые решения блокируют новые темы. При блокировке `task=null`;
  `blockers` перечисляет актуальные нерешённые версии. Молчание ничего не закрывает.
  Live assistant может доработать самую раннюю нерешённую задачу по прямому запросу.
  Старые pending не удаляются и не одобряются для расчистки очереди.
- `tools/daily_gate.py` вызывается scheduler adapter до модели. Пока очередь
  заблокирована, выдаёт `wakeAgent=false`: без новой задачи и без ежедневного
  повторения напоминания. Missing/corrupt journal или несовместимый helper —
  ошибка, а не разрешение. `draft` повторно проверяет выбор под write lock,
  поэтому один лишь обход prompt не позволяет создать новую тему.
- `depends_on` — педагогические подсказки, не доказательство одобрения,
  публикации или понимания. Проверить реальные доступные файлы и тесты.
  При разрешённом выборе и отсутствующем коде сделать bundle самодостаточным;
  это не исключение из serial approval gate. Старый неутверждённый код не применять.

## Подготовка и реальные проверки

Все команды ниже запускаются из корня проекта. `--root ROOT` при необходимости
ставится перед subcommand; без него root определяется по местоположению script.

```sh
python3 tools/workflow.py init-state
python3 tools/workflow.py status
python3 tools/workflow.py next
```

`init-state` — только локальная инициализация. Автоматически разрешены создание
private pending payload/snapshot и тестирование, но не изменения tracked files
или Git. Из команд helper только `init-state`, `draft`, `test`, `decide` меняют
private `.local/`; `status`, `next`, `verify` — read-only. `decide` cron запрещён.

1. Составить задачу по `templates/task.md`: условие своими словами, объяснение,
   полное решение, normal/boundary/invalid tests, ограничения и источники.
2. Подготовить source directory в `.local/` с **точными будущими repo-relative
   путями**. Например, внутри него `practice/ep001_log_summary/README.md`,
   реализация и `test_*.py`. Никаких секретов, employer data или скрытых правок
   инструкций/backlog. Изменения docs/policy — отдельные согласуемые diffs.
3. Передать абсолютный путь source directory. В следующем примере
   `PAYLOAD_DIR` задан агентом как абсолютный путь; ID/version берутся из вывода,
   а не из выдуманного примера:

```sh
python3 tools/workflow.py draft --task-key EP-001 --source "$PAYLOAD_DIR"
python3 tools/workflow.py verify --task-id "$TASK_ID" --version "$VERSION"
python3 tools/workflow.py test --task-id "$TASK_ID" --version "$VERSION" --start-dir practice/ep001_log_summary
```

`draft` допускает `--task-id GH-YYYYMMDD`; обычно ID создаётся по дате
`America/Vancouver`. `GH-YYYYMMDD`, `v1` и `HEX` в описании интерфейса —
шаблоны, не заранее существующие задача, версия или fingerprint.
Для иной задачи `--start-dir` указывает её реальный relative test directory.

Snapshot содержит `payload/`, `manifest.json` и после проверки
`verification.json`. Путь snapshot брать из CLI. Manifest связывает task
ID/key/version, base Git commit, repo-relative пути, SHA-256 содержимого и
SHA-256 существующего destination content. Fingerprint вычисляется как:

```python
hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=False).encode('utf-8')).hexdigest()
```

`verify` проверяет manifest/payload и точный base. Не редактировать snapshots:
любое изменение — новая версия, новые проверки и новое согласие; старое
согласие не переносится на другие bytes/base. Изменение destination content
также требует повторной проверки перед любой отдельно разрешённой application.

`test` запускает настоящий `unittest` в disposable copied workspace с
sanitized environment и timeout **60 секунд**. Это **не OS security sandbox**:
не запускать hostile/unreviewed код как будто сеть и файловая система недоступны.
`tools/unittest_driver.py` записывает структурированные счётчики только после
нормального завершения unittest runner. Напечатанный в stderr текст «OK» или
ранний `sys.exit(0)` не заменяют этот отчёт. При timeout завершается группа
тестового процесса и её обычные потомки; намеренно отделившиеся процессы не
покрываются этой гарантией. Фиксируются реальные outputs, exit status, test count и skips. Ноль успешно
выполненных тестов, только skips/expected failures, timeout или failure — не pass.
`make test` проверяет helper; это не замена тестам payload.

`verify.integrity` относится к payload/manifest, а `status=approved` — к истории
живого решения. `verify.test_evidence_valid` отдельно проверяет текущий отчёт
и runner; `verify.local_approval_valid` дополнительно требует актуальную
одобренную версию и неизменную базу. Перед application этот флаг должен быть
`true`; сам он не доказывает готовность аккаунта/прав GitHub. Сбой повторного
прогона или порча evidence блокирует применимость решения, не стирая историю.
Хеш проверок на момент approve сохраняется в decision; повторный успешный
прогон неизменного payload не требует лишнего одобрения того же diff.

## Telegram review и решение — только live

На первом экране Telegram — кратко: task key/ID/version, цель, fingerprint,
точные paths, **реальный** итог тестов и требуемое решение. Полное условие,
объяснение, solution/diff, base, команды и доказательства — в отдельной карточке.
Если тесты не выполнялись, сказать именно это. Offline fixture eval не benchmark
настоящей модели и не production-метрика.

Сначала сохранить raw review/evidence локально. Затем сделать ОТДЕЛЬНУЮ очищенную
копию, не меняя immutable snapshot. Из корня проекта:

```sh
python3 tools/report_export.py INPUT OUTPUT
```

`INPUT` — существующая UTF-8 карточка, `OUTPUT` — новый файл вне snapshot/payload,
например в `.local/exports/`. Экспорт не должен перезаписывать исходник. Проверить
готовую копию на home usernames, персональные пути, контакты, account identifiers
и credentials; известные остаточные чувствительные значения блокируют отправку.
Использовать repo-relative paths/placeholders. Не прикладывать raw execution.json
или verification.json. Маскирование best-effort и не гарантирует обнаружение любой
PII; `.gitignore` не обезличивает вложение. Cron не меняет skills ради этой проверки.

Пользователь отвечает дословно, с фактическими ID и версией:

```text
Одобряю GH-YYYYMMDD v1
Отклоняю GH-YYYYMMDD v1
Доработать GH-YYYYMMDD v1
```

Только live assistant после соответствующего нового сообщения в Telegram
может передать его **без нормализации** как evidence. Пример для approve:

```sh
python3 tools/workflow.py decide --task-id "$TASK_ID" --version "$VERSION" --fingerprint "$FINGERPRINT" --action approve --evidence "$LIVE_USER_TEXT"
```

Для `reject`/`revise` action и точный глагол evidence должны соответствовать.
CLI не аутентифицирует Telegram: история, цитата, cron output и молчание не
заменяют live user decision. `approve` требует текущую pending version, точный
fingerprint, неизменный base и passing nonzero tests. Решение записывается,
но никакие proposed files не применяются и Git не меняется.

## Позднейшая application/publication — отдельная живая работа

Требуются отдельное разрешение и проверки: authenticated account, repository
access, destination, visibility, intended author, точные paths/diff, отсутствие
секретов. Global Git author fields не доказывают account attribution.
Повторно проверить snapshot/base/destination и реальные тесты перед application.
Существенные постоянные workflow changes отдельно согласовать и локально.

Stage только согласованные paths, не `git add .`. Первый task commit не должен
молча включать весь uncommitted scaffold. После отдельно разрешённого push
проверить точный remote ref/commit/content и отдельно записать publication
journal; текущий helper этого не реализует. Не заявлять «published» по approve.

## Ручная пауза и удаление / revert

- Отдельно найти нужное задание через `hermes cron list`, затем вручную
  `hermes cron pause <job_id>`. Пауза останавливает будущие fires, не текущий run;
  при необходимости отдельно `hermes cron cancel <job_id>` и проверить состояние.
- После подтверждённой остановки можно вручную сохранить нужные данные и удалить
  именно эту локальную основу. `.local/` содержит private решения/evidence;
  не удалять её без осознанного согласия и не сбрасывать очередь молча.
- Uncommitted scaffold не имеет remote effects. Его удаление не требует remote
  rollback и само по себе не выключает cron. Не использовать широкие clean/reset
  команды и не затрагивать чужие изменения.
- Если в будущем что-то опубликовано, удаление локальных файлов не отменяет
  публикацию: нужен отдельный согласованный revert и проверка remote.

## Проверенные источники Hermes

- [Context Files](https://hermes-agent.nousresearch.com/docs/user-guide/features/context-files):
  discovery по workdir и priority/override context files.
- [Scheduled Tasks](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron):
  fresh sessions, workdir, timezone, continuity, continuable delivery и pause/cancel.
