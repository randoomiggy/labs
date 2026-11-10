# EP-001 — потоковая сводка синтетического журнала

Самостоятельное оригинальное упражнение на Python: строгий разбор строк,
одноразовые iterators, накопление счётчиков и проверяемый контракт API.
Реализация, tests и объяснение подготовлены с AI assistance. Реально выполненные
проверки приведены ниже; это не утверждение о production-опыте или понимании
материала пользователем.

**Результат:** `summarize(lines)` за один проход возвращает обычный `dict` с
числом valid/malformed записей и распределением целочисленных статусов.
Функция не сохраняет историю строк и не читает файлы.

- Код: [`solution.py`](solution.py).
- Tests: [`test_solution.py`](test_solution.py).
- Требования: Python **3.11+**, только standard library, без установки пакетов.
- Это **не** parser настоящих HTTP, nginx или Apache access logs и **не** CLI.
- EP-001 не зависит от реализации других упражнений.

## Содержание

1. [Условие и точный формат](#1-условие-и-точный-формат)
2. [Результат API и ошибки](#2-результат-api-и-ошибки)
3. [Demo и tests: команды запуска](#3-demo-и-tests-команды-запуска)
4. [Трассировка примера](#4-трассировка-примера)
5. [Walkthrough всего solution.py](#5-walkthrough-всего-solutionpy)
6. [Как устроены tests](#6-как-устроены-tests)
7. [Сложность и ограничения](#7-сложность-и-ограничения)
8. [Как устроен весь проект](#8-как-устроен-весь-проект)
9. [Дальнейшая практика и справочники](#9-дальнейшая-практика-и-справочники)

## 1. Условие и точный формат

Реализовать `summarize(lines: Iterable[str]) -> Summary`. Вход — iterable,
который выдаёт **целые текстовые записи**, по одной на элемент. Это может быть
список, iterator или generator; нельзя требовать повторного прохода, длины или
индексации. Не нужно превращать весь вход в `list` и сохранять исходные записи.

У каждой строки разрешено удалить **не более одного** конечного LF (`\n`) или
CRLF (`\r\n`). Затем **вся оставшаяся строка** должна соответствовать грамматике:

```text
[0-9]+ [A-Z]+ /[A-Za-z0-9/_-]* [1-5][0-9]{2}
```

Четыре поля разделяются ровно одним ASCII space (`U+0020`):

```text
timestamp method path status
```

| Поле | Разрешено | Не разрешено / что не проверяется |
| --- | --- | --- |
| `timestamp` | Одна или более ASCII digits `0`–`9`; `0`, `000` допустимы | Знаки, дроби, Unicode digits; это не дата, единицы времени и порядок не интерпретируются |
| `method` | Одна или более ASCII uppercase letters `A`–`Z` | Lowercase, digits, Unicode; allowlist зарегистрированных HTTP methods отсутствует, `X` и `CUSTOM` допустимы |
| `path` | Обязательный `/`, далее любое число ASCII letters, digits, `/`, `_`, `-` | Dots, query string, `%`, backslash, Unicode; `/` и `//` синтаксически допустимы, нормализация пути не выполняется |
| `status` | Ровно три ASCII digits в диапазоне `100`–`599` включительно | `099`, `600`, `20`, `2000`, `+200`; реестр зарегистрированных HTTP statuses не проверяется |

Примеры valid строк: `0 GET / 100`, `000 X /a_Z/09-_ 599`.
Последний элемент без newline допустим; API разрешает отсутствие newline и у
любого другого элемента — оно не означает, что iterator обязательно закончился.

Malformed считаются пустая строка, blank line, bare CR (`\r`), лишние пробелы,
табуляция вместо separator, дополнительные поля, неверные поля и несколько
записей внутри одного элемента. Для такой **строки** увеличивается
`malformed_lines`, после чего обработка продолжается. Ни `strip()`, ни
`rstrip()`, ни universal newline normalization здесь не применяются: иначе
неверный исходный ввод можно было бы незаметно «исправить» до valid.

## 2. Результат API и ошибки

При нормальном завершении возвращается **обычный `dict`**, например:

```python
{
    "valid_lines": 3,
    "malformed_lines": 1,
    "status_counts": {200: 2, 503: 1},
}
```

`Summary` в annotations — `TypedDict`, описание полей для static type checker,
а не dataclass и не runtime-обёртка. Доступ к данным — `result["valid_lines"]`,
не `result.valid_lines`.

| Key | Тип и смысл |
| --- | --- |
| `valid_lines` | Неотрицательный `int`, число строк, прошедших full match |
| `malformed_lines` | Неотрицательный `int`, число строк, не прошедших full match |
| `status_counts` | `dict[int, int]`, status → положительное число valid строк с этим status |

Mapping **sparse**: отсутствующий status не добавляется с нулём. Например,
`result["status_counts"].get(404, 0)` безопасно даёт ноль для отсутствующего key.
Оба возвращаемых dictionaries создаются заново при каждом вызове и mutable;
их последующее изменение вызывающим кодом не влияет на другой вызов.

Для любого нормально обработанного конечного входа выполняются invariants:

```python
valid_lines + malformed_lines == number_of_input_items
sum(status_counts.values()) == valid_lines
```

Каждая valid строка увеличивает ровно один status counter. Пустой iterable
возвращает `{"valid_lines": 0, "malformed_lines": 0, "status_counts": {}}`,
**не `None`**. После ручного изменения возвращённого mapping эти invariants
пользователь, разумеется, может нарушить.

### Malformed строка и ошибка источника — разные случаи

- `"bad"` — `str` неправильного формата: учитывается как malformed.
- Элемент `None`, `200`, `True`, `bytes` или `list` — нарушение API: выбрасывается
  `TypeError("each input item must be a string")`. Это сохраняет поведение
  исходного решения; non-`str` не маскируется под malformed log record.
- `summarize(None)` и другой non-iterable вход приводят к `TypeError` при попытке
  начать `for`. `None` не используется как сокращение пустого потока.
- Если `__iter__()` либо `__next__()` источника выбрасывает исключение, например
  `OSError`, оно распространяется вызывающему коду. Частичная сводка не
  возвращается, уже прочитанные элементы iterator не восстанавливаются.
- Обычный `StopIteration` означает конец входа и штатный возврат результата.

Annotations сами не выполняют runtime validation. Проверка типа элемента есть
в функции явно. `isinstance(line, str)` принимает и subclasses `str`, но ничего
не декодирует и не вызывает `str(line)` для произвольных объектов.

Одна запись передаётся как `["0 GET / 200"]`, а не как `"0 GET / 200"`:
сама строка тоже iterable, но выдаёт отдельные символы, а не записи.

## 3. Demo и tests: команды запуска

Команды ниже предназначены для shell на Linux/macOS. «Корень» — каталог,
содержащий `AGENTS.md`, `practice/`, `tools/` и `Makefile`. Никакие absolute
пути, account-specific settings или внешние сервисы не нужны.

Сначала проверить фактический interpreter:

```sh
python3 --version
```

`-B` в следующих командах запрещает создание bytecode cache (`__pycache__`);
на логику parser и число tests этот flag не влияет.

### Из корня проекта

Tests именно EP-001:

```sh
python3 -B -m unittest discover -s practice/ep001_log_summary -p 'test_*.py' -v
```

Полный synthetic demo:

```sh
python3 -B -c '
from practice.ep001_log_summary.solution import summarize
records = iter([
    "0 GET /health 200\n",
    "1 POST /jobs 503\r\n",
    "not a record\n",
    "2 GET /health 200",
])
print(summarize(records))
'
```

Здесь импорт через `practice.ep001_log_summary` работает из корня как namespace
package; добавлять `__init__.py` или менять глобальный `PYTHONPATH` не требуется.

### Из директории упражнения

```sh
cd practice/ep001_log_summary
python3 -B -m unittest -v test_solution
```

В этой директории импорт короче:

```sh
python3 -B -c '
from solution import summarize
records = iter([
    "0 GET /health 200\n",
    "1 POST /jobs 503\r\n",
    "not a record\n",
    "2 GET /health 200",
])
print(summarize(records))
'
```

Оба demo печатают один и тот же фактический результат:

```text
{'valid_lines': 3, 'malformed_lines': 1, 'status_counts': {200: 2, 503: 1}}
```

Это Python representation, **не JSON**: у `status_counts` именно integer keys.
CLI с arguments, file/stdin input и JSON serialization не входит в EP-001.

### Что реально проверено

Локально на Linux выполнены следующие проверки:

| Проверка | Interpreter | Результат |
| --- | --- | --- |
| `unittest discover` из корня, команда выше | Python 3.14.9 | 23 tests, `OK`, exit code 0 |
| `unittest -v test_solution` из директории упражнения | Python 3.14.9 | 23 tests, `OK`, exit code 0 |
| Оба demo из указанных директорий | Python 3.14.9 | Точный `dict`, приведённый выше, exit code 0 |
| Та же discovery-команда с `python3.11` вместо `python3` | Python 3.11.15 | 23 tests, `OK`, exit code 0 |
| Запуск через существующий `tools/unittest_driver.py` | Python 3.14.9 | `driver_completed=true`, `tests_run=23`, `tests_succeeded=23`, `passed=true`; failures/errors/skips/expected failures/unexpected successes — 0 |

Structured report последнего вида создаётся только после нормального завершения
runner. В этой проверке он сохранён в runtime scratch вне репозитория, без
изменения review state. Здесь не заявляется прогон на всех версиях Python 3.11+
или на других OS. Конкретные timings не являются benchmark и не нужны для
воспроизводимости. Проверки workflow helper — отдельный test suite.

## 4. Трассировка примера

Для demo выше состояние меняется так; `\n` и `\r\n` в таблице обозначают реальные
конечные символы. Строка `not a record` пропускается, но не останавливает поток.
Промежуточные результаты проверены отдельными вызовами на prefixes примера;
сама реализация не пересчитывает prefixes и не хранит эту таблицу.

| Шаг | Полученный элемент | Действие | `valid_lines` | `malformed_lines` | `status_counts` |
| --- | --- | --- | --- | --- | --- |
| Начало | — | Создать пустые counters | 0 | 0 | `{}` |
| 1 | `0 GET /health 200\n` | Удалить один LF; match; status `200` | 1 | 0 | `{200: 1}` |
| 2 | `1 POST /jobs 503\r\n` | Удалить один CRLF; match; status `503` | 2 | 0 | `{200: 1, 503: 1}` |
| 3 | `not a record\n` | Удалить один LF; no match; `continue` | 2 | 1 | `{200: 1, 503: 1}` |
| 4 | `2 GET /health 200` | Не менять ending; match; повторный `200` | 3 | 1 | `{200: 2, 503: 1}` |

Таким образом, четыре элемента дают три valid и один malformed. В сводке нет
списка timestamps, paths, исходных строк или причин каждой отдельной ошибки.

## 5. Walkthrough всего solution.py

Ниже код разобран по смысловым фрагментам в порядке исполнения.
Полный рабочий файл — [`solution.py`](solution.py), а не скрытая зависимость.

### 5.1. Module docstring, imports и compiled regex

```python
"""Summarize the exact EP-001 synthetic log format in one pass.

This module performs no file, network, or subprocess operations.
"""
from collections.abc import Iterable
import re
from typing import TypedDict


_LINE = re.compile(
    r"[0-9]+ [A-Z]+ /[A-Za-z0-9/_-]* (?P<status>[1-5][0-9]{2})"
)
```

- Module docstring формулирует назначение и отсутствие внешних операций.
- `Iterable` описывает объект, у которого можно получить iterator; annotation
  не требует `list` и не означает, что длина входа известна.
- `re` — stdlib regular expression engine. Pattern компилируется один раз при
  импорте модуля, а не заново для каждой строки.
- `TypedDict` нужен только для описания неоднородного результата API.
- Начальный `_` у `_LINE` — соглашение о внутреннем имени модуля.
- Prefix `r` делает literal raw string: backslashes в regex не нужно было бы
  дополнительно экранировать для Python. Здесь грамматика в основном состоит
  из явных character classes.
- `[0-9]+` — ASCII digits, один или более; не `\d`, допускающий Unicode digits.
- Обычные spaces между группами — ровно ASCII spaces, не `\s`.
- `[A-Z]+` — uppercase method без allowlist.
- `/[A-Za-z0-9/_-]*` — начальный slash обязателен, после него допускается пустой
  suffix. Hyphen стоит в конце character class и обозначает literal `-`.
- `(?P<status>...)` — named capture. `[1-5][0-9]{2}` ограничивает status тремя
  digits и диапазоном, прежде чем выполняется `int()`.

В pattern нет anchors `^` и `$`: ниже вызывается `fullmatch`, а не поиск
подстроки. Сам по себе `match()` проверял бы только начало строки; подмена API
могла бы позволить лишний suffix. Особенно важно не полагаться на `$` как на
безусловную проверку отсутствия конечного newline.

### 5.2. `Summary` и сигнатура функции

```python
class Summary(TypedDict):
    """Static shape of the returned dictionary, not a runtime wrapper."""

    valid_lines: int
    malformed_lines: int
    status_counts: dict[int, int]


def summarize(lines: Iterable[str]) -> Summary:
    """Count valid/malformed strings and return sparse integer status counts.

    Remove at most one terminal LF or CRLF, not arbitrary whitespace.
    Non-string items raise TypeError; errors from the input iterator propagate.
    No partial summary is returned if iteration fails.
    """
```

`TypedDict` связывает конкретные string keys с конкретными типами values.
Это точнее, чем `dict[str, int | dict[int, int]]`, где checker не знает, какой
key содержит число, а какой — вложенный dictionary. При этом результат остаётся
обычным `dict`; никакой runtime validation `TypedDict` за нас не делает.

Function docstring отдельно фиксирует newline policy и распространение ошибок.
Сигнатура не обещает «починить» неправильные объекты или вернуть partial result.

### 5.3. Локальные counters, `for` и type check

```python
    valid_lines = 0
    malformed_lines = 0
    status_counts: dict[int, int] = {}

    for line in lines:
        if not isinstance(line, str):
            raise TypeError("each input item must be a string")
```

Counters локальны одному вызову. `{}` находится в теле функции, поэтому между
вызовами нет shared mutable mapping. До конца прохода состояние содержит только
эти counters, текущую строку и данные её текущего match.

Один `for` получает iterator и запрашивает элементы до завершения. Здесь нет
второго `for` по источнику, `len(lines)`, indexing, `list(lines)`, sorting или
чтения всего потока заранее. Iterable может быть one-shot: после первого
вызова generator исчерпан, и второй вызов на **том же** generator вернёт пустую
сводку. Это свойство источника, не потеря счётчиков внутри функции.

Проверка `isinstance` стоит **до** строковых операций. Иначе `None` дал бы
случайный `AttributeError`, а `bytes` мог бы привести к ошибке смешения text и
bytes. Здесь нарушение имеет одну явно заданную ошибку API. Catch-all `except`
нет: ошибка источника или программирования не превращается в «плохой лог».

### 5.4. Удаление одного разрешённого ending

```python
        if line.endswith("\r\n"):
            line = line[:-2]
        elif line.endswith("\n"):
            line = line[:-1]
```

CRLF проверяется первым: это одна разрешённая последовательность из двух
символов, и удалить нужно оба. Если сначала убрать только LF, останется CR и
правильная CRLF-запись ошибочно станет malformed. `elif` исключает повторное
удаление: это не цикл «удалить все переводы строк».

Slice создаёт обработанное значение `line`, исходный объект `str` immutable.
Если ending отсутствует, строка не меняется. Bare CR не удаляется вообще.

| Исходный suffix после `200` | После этого блока | Match |
| --- | --- | --- |
| Нет ending | `200` | Возможен |
| `\n` | `200` | Возможен |
| `\r\n` | `200` | Возможен |
| `\r` | `200\r` | Невозможен |
| `\n\n` | `200\n` | Невозможен |
| `\r\n\r\n` | `200\r\n` | Невозможен |
| ` \n` | `200 ` | Невозможен |

«Возможен» означает, что остальные поля тоже должны быть valid.
`rstrip("\r\n")` здесь неверен: он снимает произвольное количество указанных
символов, а `strip()` дополнительно мог бы скрыть лишние leading/trailing spaces.

### 5.5. `fullmatch`, `None` и malformed counter

```python
        match = _LINE.fullmatch(line)
        if match is None:
            malformed_lines += 1
            continue
```

`fullmatch` требует соответствия всей оставшейся строки. При неудаче результат
равен `None`; это **не** ошибка iterator и **не** итог всей функции. Explicit
`is None` проверяет именно отсутствие match.

`continue` переходит к следующему элементу. У malformed строки не пытаются
извлечь status; в `status_counts` она ничего не добавляет. Поэтому сломанная
строка между двумя valid не обрывает обработку и не считается успешной записью.

### 5.6. Извлечение status, conversion и counters

```python
        status = int(match.group("status"))
        valid_lines += 1
        status_counts[status] = status_counts.get(status, 0) + 1
```

Named group возвращает ровно три уже проверенные ASCII digits. `int()` превращает
их в integer key, например `"503"` → `503`; `ValueError` для обычного valid
match здесь не ожидается. Timestamp не конвертируется: упражнение проверяет
его синтаксис, не вычисляет время. Даже очень длинная последовательность digits
в timestamp не упирается в лимит Python на conversion длинных decimal strings.

`.get(status, 0)` возвращает накопленное значение или ноль для нового key.
Затем присваивание добавляет либо обновляет только этот status. Нет заранее
созданного массива всех возможных значений и нулевых entries для отсутствующих
statuses. `collections.Counter` тоже подходит для подсчёта, но явный `dict` и
одна строка обновления здесь показывают механику без дополнительной абстракции.

### 5.7. Возврат после окончания input

```python
    return {
        "valid_lines": valid_lines,
        "malformed_lines": malformed_lines,
        "status_counts": status_counts,
    }
```

`return` расположен **вне** `for`: возвращается одна итоговая сводка, а не первая
valid запись. На пустом входе тело цикла не исполняется, и возвращаются начальные
нули с пустым mapping. История input в результат не попадает. Сортировки и
JSON serialization здесь нет; потребитель не должен считать порядок keys
отдельным обещанием формата отчёта.

В модуле нет `main`, чтения stdin, `open`, file decoder или argument parser.
Импорт предоставляет функцию; demo выше явно вызывает её через `python -c`.

## 6. Как устроены tests

[`test_solution.py`](test_solution.py) использует stdlib `unittest` и только
синтетические fixtures. `SummaryTests(unittest.TestCase)` объединяет методы с
prefix `test_`; `unittest` обнаруживает их и выполняет assertions. При прямом
запуске файла блок `if __name__ == "__main__": unittest.main()` включает тот же
runner. Tests импортируют `summarize` из локального `solution`.

| Группа / методы | Что защищает |
| --- | --- |
| `test_documented_mixed_example` | Точный demo result, повторный `200`, integer status keys и сумма counts |
| `test_empty_input`, `test_all_malformed` | Пустой input не равен malformed строке; без valid records mapping пуст |
| `test_status_endpoints_and_timestamp_zero`, `test_all_status_values_in_range` | `0`, границы `100`/`599` и каждый status во всём разрешённом диапазоне |
| `test_lf_crlf_and_unterminated_records` | Каждый из трёх разрешённых вариантов ending |
| `test_blank_bare_cr_and_extra_newlines`, `test_rejects_two_records_in_one_item` | Один ending, а не произвольная очистка; внутренние newlines, CR, Unicode line separators и два records не принимаются |
| `test_invalid_statuses`, `test_invalid_timestamps_methods_and_paths`, `test_exact_spaces_and_field_count` | ASCII restrictions, лишние и отсутствующие поля, ровно один space, invalid status width/range |
| `test_method_and_path_follow_grammar_not_http_semantics` | Нельзя незаметно ужесточить synthetic grammar до реестра HTTP methods/statuses |
| `test_malformed_records_do_not_stop_iteration` | После malformed строки последующие valid всё ещё обрабатываются |
| `test_single_pass_iterable_and_generator` | `__iter__` вызывается один раз, длина не запрашивается, generator исчерпывается; повторный вызов на исчерпанном generator пуст |
| `test_very_long_timestamp_is_not_converted_to_integer` | Timestamp из 10 000 digits остаётся syntactic token, не большим вычисляемым числом |
| `test_non_string_items_raise_type_error`, `test_non_string_item_aborts_before_requesting_next_item` | Invalid element type — явный `TypeError`, после него источник не читается дальше |
| `test_non_iterable_input_raises_type_error`, `test_failure_to_create_iterator_propagates`, `test_iterator_errors_propagate` | Ошибки создания/чтения iterator не скрываются и не возвращают partial success |
| `test_calls_do_not_share_result_mappings`, `test_str_subclass_is_accepted` | Независимые dictionaries между вызовами; согласованное поведение `isinstance` |
| `test_output_schema_and_invariants_for_each_prefix` | Точные keys/types, неотрицательные totals, положительные sparse counts, диапазон keys и обе invariants на каждом prefix fixture |

`subTest` позволяет перечислить несколько invalid forms внутри одного test и
увидеть конкретный failing input. Их количество не прибавляется к `tests_run`
как отдельные test methods: здесь runner действительно выполняет **23 tests**.
`type: ignore[arg-type]` встречается только там, где отрицательный test намеренно
передаёт вход против annotation; он не подавляет runtime assertions.

`OnePass` в tests запрещает второй проход и запрос длины. Это практическая
проверка iterator contract, но не memory profiler: отсутствие истории видно
также из самой реализации. Tests не доказывают поведение произвольного
вредоносного subclass/iterator и не являются formal verification.

## 7. Сложность и ограничения

Обозначения:

- `N` — число элементов input;
- `C` — суммарное число символов входных строк;
- `L` — максимальная длина одной строки;
- `U` — число различных valid statuses, присутствующих во входе.

**Время — `O(C + N)`** в обычной модели счётчиков и dictionary operations.
Каждый элемент запрашивается один раз; regex и возможный slice проходят по
текущей строке. Дополнительное `N` учитывает constant work даже для пустых строк.
Фиксированный pattern не содержит nested ambiguous repetitions: field classes
не включают разделяющий space. Timestamp/path могут быть длинными, но
исторические строки не пересканируются.

**Рабочая память — `O(U + L)`**: sparse counters плюс текущая строка, её возможная
копия без ending и текущий match. Aggregation state без текущей строки — `O(U)`.
Вход, уже сохранённый вызывающим кодом в большом `list`, сюда не включается:
функция не создаёт такой list сама. Для finite domain `100`–`599` возможно не
более **500** различных status keys; это ограничение entries, не общий лимит
памяти всех counters и не лимит длины строки.

Оценка использует **unit-cost integer model**. Python `int` имеет arbitrary
precision: при росте input растут bit widths счётчиков и стоимость их обновления.
В строгой bit model нельзя обещать constant bytes на один counter: для
представления значения порядка `N` требуется порядка `log(N + 1)` bits.
Отдельного benchmark, жёсткого resource limit или гарантии latency нет.

Границы задачи:

- Только synthetic text records; не реальные журналы сервиса и не доступность
  настоящего сервиса. Нет employer logs, PII, credentials или network access.
- Нет file I/O, UTF-8 decoder, byte chunk framing, buffering до полного record,
  CLI, JSON schema, stdout/stderr policy или файловых ошибок внутри `summarize`.
  Если caller уже нормализовал newlines при чтении, функция не восстановит
  потерянные исходные CR/LF; transport и decoder policy нужно задать отдельно.
- Нет line length limit; при untrusted input его должен обеспечить caller.
  Infinite iterable никогда не завершит итоговую сводку.
- Нет сохранения sample errors, их номеров, timestamps, paths или причин invalid
  записи; только summary counters. Нет sorting, retry, concurrency и checkpoint.
- Iterator failure распространяется наружу без partial result и без rollback
  уже потреблённого input. Это не отказоустойчивый production ingestion pipeline.

## 8. Как устроен весь проект

EP-001 — небольшая прикладная часть проекта; остальная основа организует
подготовку упражнений, review и честные evidence. Это два разных уровня:
parser работает без helper, Git, cron, Telegram, remote и private state.

### 8.1. Карта репозитория

Все ссылки ниже относительны этому README:

| Путь | Назначение и что из него нельзя заключать |
| --- | --- |
| [`AGENTS.md`](../../AGENTS.md) | Project policy для агента: границы изменений, источники истины, privacy, реальные проверки и approval. Это не task queue и не журнал выполнения |
| [Корневой `README.md`](../../README.md) | English entry point для читателя: цель, layout, команды и границы проекта. Этот русский README подробно разбирает конкретное упражнение и связь с основой |
| [`ROADMAP.md`](../../ROADMAP.md) | Предлагаемая progression: упражнения, затем отдельно выбранные operational labs и возможные CI/IaC. Roadmap не означает уже установленную инфраструктуру |
| [`BACKLOG.json`](../../BACKLOG.json) | Machine-readable предложения EP-001…EP-014: `key`, goal, scope, acceptance, `depends_on`. Очередь описывает будущую работу, а не список завершённых навыков |
| [`docs/WORKFLOW.md`](../../docs/WORKFLOW.md) | Подготовка payload, immutable revisions, проверка, live review, publication gates и ручная пауза. Это инструкция, а не доказательство выполненного remote action |
| [`docs/DECISIONS.md`](../../docs/DECISIONS.md) | Принятые design decisions и оставшиеся выборы. Это не дневник запусков и не замена новому прямому live-разрешению в конкретном scope |
| [`templates/task.md`](../../templates/task.md) | Task card template: identity, условие, полный solution, commands, actual results, ограничения и review. Placeholders не являются реальными pass/count/fingerprint |
| [`practice/`](../README.md) | Малые самостоятельные упражнения. Здесь находится `ep001_log_summary/` с implementation, tests и этим walkthrough |
| [`labs/`](../../labs/README.md) | Место для будущих operational labs с environment, failure scenario, diagnostics, acceptance и cleanup/rollback. Наличие directory не означает реализованный lab |
| [`tools/workflow.py`](../../tools/workflow.py) | Local helper для proposals, state, snapshots, integrity, test evidence и решений. Он не является parser и не применяет/публикует payload |
| [`tools/unittest_driver.py`](../../tools/unittest_driver.py) | Completion driver: запускает `unittest` и после нормального завершения записывает structured counters |
| [`tools/daily_gate.py`](../../tools/daily_gate.py) | Read-only pre-check: вызывает обычный `next`; выдаёт `wakeAgent=false` для blocked очереди и отказывает при повреждённых данных. Локальный scheduler adapter вне Git вызывает этот файл |
| [`tools/report_export.py`](../../tools/report_export.py) | Создаёт новый UTF-8 export с best-effort маскированием; отказывается перезаписывать input, существующий output или immutable snapshot |
| [`tests/test_workflow.py`](../../tests/test_workflow.py) | Tests самого helper: неизменность snapshots, input/path checks, decision gates, реальные test subprocesses и отказные сценарии |
| [`tests/test_daily_gate.py`](../../tests/test_daily_gate.py) | Реальные harmless helper subprocesses: blocked/ready, плохой журнал/JSON, symlinks, отсутствие явного gate и пустой stdout при ошибке |
| [`tests/test_report_export.py`](../../tests/test_report_export.py) | Проверяет маскирование, сохранение hashes/task IDs, strict UTF-8, запрет overwrite/symlinks и неизменность raw evidence |
| [`tests/test_project_metadata.py`](../../tests/test_project_metadata.py) | Consistency checks основы: документы, структура backlog, privacy ignore rules и команды Makefile; не tests EP-001 |
| [`Makefile`](../../Makefile) | `test` — helper/gate/export; `test-ep001` — упражнение; `test-all` — оба suite. Также `status` и `next`; это не отдельная publish система |
| [`.gitignore`](../../.gitignore) | Исключает private state, caches, environments и типовые secrets/output из обычного Git discovery. Ignore не является redaction или запретом принудительного добавления |
| `.local/` | Gitignored private runtime: snapshots, manifests, verification evidence и workflow state. Raw содержимое не предназначено для публикации |

### 8.2. `practice` и `labs`: разный масштаб работы

Упражнение в `practice` имеет небольшой API, полный код, tests, объяснение и
явные non-goals. EP-001 можно понять и воспроизвести без развёртывания сервиса.
Operational lab в `labs` должен отдельно определить среду, риск и реальный
воспроизводимый failure/recovery scenario; Docker/cloud/CI/IaC не появляются
автоматически только потому, что упомянуты в roadmap.

EP-002…EP-005 и остальные backlog entries **не объявляются завершёнными** этим
изменением. Старый pending payload, successful tests внутри него, `depends_on`
или предложение следующего key не доказывают approval, применение, публикацию
или понимание предыдущего материала. Например, EP-002 — отдельное предложение
CLI, а не уже существующий command-line mode этой функции.

### 8.3. Поток предложения, review и применения

Принцип serialized review: пока текущее упражнение не обработано и не получило
необходимого live approval для commit, новое упражнение не выдаётся. Старые
unresolved предложения не исчезают при очередном запуске, молчание не считается
решением, а наличие proposal в истории не означает готовность идти дальше.
Read-only выбор следующей работы и write-path создания draft должны соблюдать
один gate; повторная проверка под lock нужна против двух одновременных запусков.
В текущем JSON от `next` блокировка выражается как `blocked: true`, `task: null`,
список `blockers` и `active_task` с самым ранним нерешённым ID/version. Только
`blocked: false` разрешает новый key. Rejected/revision_requested тоже не дают
перескочить к новой теме. Историческое approved может открыть очередь, но не
подменяет актуальные integrity/base/evidence проверки перед публикацией.
На повреждённом или неполном state нельзя «на всякий случай» выдавать новую
задачу: это **fail-closed**, а не автоматический сброс истории.

В обычном review workflow роли разделены:

1. Сначала читают policy, решения и очередь, затем смотрят фактическое состояние.
   `status` описывает local records; `next` помогает выбрать разрешённую работу
   или сообщает блокировку. Exact interface проверяют через текущий `--help`.
2. `draft` фиксирует точный payload в новой immutable revision. Task key `EP-...`
   задаёт тему; task ID, version и fingerprint обозначают конкретное предложение.
3. Manifest связывает repo-relative destinations, content hashes, base Git
   revision и состояние destinations до изменения. Hash помогает обнаружить
   изменение bytes; это не подпись пользователя и не доказательство GitHub access.
4. `verify` сверяет manifest/payload и актуальность base/destinations;
   `test` проверяет snapshot в отдельной временной копии. Изменённые bytes/base
   требуют новой revision и соответствующего свежего review.
5. Только реальное live user message может разрешить решение по **точной**
   revision. Для карточек helper ожидает согласованные ID/version/fingerprint
   и точное evidence; Telegram authenticity сам CLI проверить не может.
6. `approved` — decision history, не автоматическое применение и не публикация.
   Перед отдельно разрешённым live commit/publication снова проверяют точные
   файлы, валидность текущего approval и tests. Решение не переносится на другой
   diff или новую base. Publication и её evidence находятся вне helper.

Statuses `pending`, `approved`, `rejected`, `revision_requested`, `superseded`
описывают review lifecycle, а не освоение темы. Новый version не переписывает
immutable payload предыдущего version. Прямое live-разрешение на конкретную
реализацию также не превращает старый snapshot с другими bytes в approved.

Автоматика/cron **preparation-only**: разрешённые private proposals и проверки,
но не изменение tracked tree, не `decide`, не commit и не push. Для проекта
указано желаемое время `09:30 America/Vancouver`, однако **документы не доказывают**
ни фактический active schedule, ни доставку сообщения, ни remote/visibility,
ни account attribution, ни публикацию. Это проверяется по отдельным реальным
состояниям соответствующих систем, а не по тексту README.

### 8.4. Почему у проекта два уровня tests

Из корня проекта команды основы:

```sh
make test
make test-ep001
make test-all
make status
make next
```

По [`Makefile`](../../Makefile) это aliases следующих команд:

```sh
python3 -m unittest discover -s tests -v
python3 tools/workflow.py status
python3 tools/workflow.py next
```

`make test` обнаруживает tests в корневом `tests/`, **не** рекурсивно все
упражнения в `practice/`. Поэтому green helper suite не заменяет отдельную
команду EP-001 из раздела 3. Обратное тоже верно: passing parser tests не
доказывают, что workflow gates или scheduler работают правильно.

`unittest_driver.py` нужен основе для machine-readable evidence:

- `TextTestRunner` действительно запускает обнаруженный suite;
- counters записываются после нормального завершения runner, не извлекаются
  regex из произвольного stderr tests;
- printed `OK`, early `sys.exit(0)`, пустой suite или только skipped/expected
  failures не заменяют хотя бы один genuinely successful test;
- structured evidence и его связь с revision проверяются отдельно от статуса
  решения; failed rerun может заблокировать применение исторического approval.

Helper запускает checks в disposable copied workspace, с ограниченным
окружением и timeout. Это снижает некоторые случайные риски, но **не OS security
sandbox**: нельзя считать произвольный Python безопасным только из-за temporary
directory. В EP-001 checks выполняются над просмотренным synthetic кодом;
никакие hostile fixtures или настоящие secrets для них не нужны.

### 8.5. Private `.local/`, evidence и безопасный export

`.local/` отделяет operational records от публичного учебного кода. Внутри
могут быть immutable `payload/`, `manifest.json`, verification reports,
review metadata и state. Конкретные существующие paths следует брать из helper,
а не придумывать по примеру directory tree. Старые snapshots не редактируют
ради нового walkthrough: новая реализация и новый review — отдельные bytes.

Raw reports могут содержать absolute local paths, live decision evidence,
stdout/stderr и другие личные детали. Поэтому:

- `.local/` не копируется в публичную документацию, commit или artifact целиком;
- для внешнего review готовят отдельный **redacted export** с минимальными
  нужными сведениями, без raw state, account data и полного stdout/stderr;
- exact export command/flags следует смотреть в текущем helper `--help`,
  а не предполагать интерфейс по названию функции;
- автоматическая redaction не доказывает отсутствие secrets: нужен content
  review точных экспортируемых файлов;
- `.gitignore` не удаляет уже опубликованное, не шифрует данные и не очищает
  содержимое. «Ignored» и «безопасно поделиться» — разные утверждения.

Базовый интерфейс экспорта — `python3 tools/report_export.py INPUT OUTPUT` из
корня. `OUTPUT` — новый файл вне snapshot, с существующим родительским каталогом;
например, новый файл внутри заранее созданного `.local/exports/`. Дополнительные
личные identifiers можно передать через локальный JSON array с `--sensitive-file`;
сам этот файл никогда не отправляют. Результат маскирования проверяют вручную.

Этот README содержит только synthetic demo, общую архитектуру и реальные
нечувствительные результаты checks. Raw runtime reports не включены в
упражнение; workflow state, решения и публикация этим exercise не изменяются.

## 9. Дальнейшая практика и справочники

Необязательные вопросы для самостоятельной проверки:

1. Почему `rstrip()` нарушит контракт на строке с двумя конечными newlines?
2. Чем `match is None` отличается от `summarize(None)` и пустого input?
3. Почему `timestamp` не стоит превращать в `int`, если он не участвует в расчётах?
4. Что вернёт второй вызов на уже исчерпанном generator и почему?
5. Какие invariants нарушатся, если увеличить `valid_lines` до проверки regex?
6. Почему ограничение числа statuses не означает фиксированное число bytes на
   counters при неограниченно длинном входе?
7. Какие дополнительные ошибки появятся при добавлении UTF-8 reader и CLI?

Следующий возможный шаг — отдельный EP-002 с явными file/stdin input, UTF-8
policy, deterministic JSON, diagnostics в stderr и реальными subprocess tests.
Это **будущая отдельно разрешаемая работа**, не скрытая часть текущей реализации.

Официальные Python справочники для используемых API:

- [`re.Pattern.fullmatch`](https://docs.python.org/3/library/re.html#re.Pattern.fullmatch)
  и [`re.fullmatch`](https://docs.python.org/3/library/re.html#re.fullmatch).
- [`collections.abc.Iterable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterable).
- [`typing.TypedDict`](https://docs.python.org/3/library/typing.html#typing.TypedDict).
- [`unittest`](https://docs.python.org/3/library/unittest.html), включая test
  discovery, assertions и `subTest`.
- [`collections.Counter`](https://docs.python.org/3/library/collections.html#collections.Counter)
  — возможная альтернатива явному status dictionary, не dependency решения.

Условие и solution оригинальные, а не скопированный challenge или fragment
книги. Выбор project license не делается в рамках этого упражнения. AI-generated,
tested, human-reviewed, approved, published и understood — разные состояния;
сам README не подменяет ни одно из них.
