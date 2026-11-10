"""Offline tests using only original synthetic EP-001 records."""
import unittest

from solution import summarize


class SummaryTests(unittest.TestCase):
    def test_documented_mixed_example(self):
        lines = iter([
            "0 GET /health 200\n",
            "1 POST /jobs 503\r\n",
            "not a record\n",
            "2 GET /health 200",
        ])
        result = summarize(lines)
        self.assertEqual(result, {
            "valid_lines": 3,
            "malformed_lines": 1,
            "status_counts": {200: 2, 503: 1},
        })
        self.assertEqual(sum(result["status_counts"].values()), result["valid_lines"])
        self.assertTrue(all(type(status) is int for status in result["status_counts"]))

    def test_empty_input(self):
        self.assertEqual(summarize(iter(())), {
            "valid_lines": 0, "malformed_lines": 0, "status_counts": {},
        })

    def test_status_endpoints_and_timestamp_zero(self):
        self.assertEqual(summarize(["0 GET / 100", "0 GET / 599"]), {
            "valid_lines": 2, "malformed_lines": 0,
            "status_counts": {100: 1, 599: 1},
        })

    def test_lf_crlf_and_unterminated_records(self):
        for ending in ("\n", "\r\n", ""):
            with self.subTest(ending=repr(ending)):
                self.assertEqual(summarize(["1 GET /health 204" + ending]), {
                    "valid_lines": 1, "malformed_lines": 0,
                    "status_counts": {204: 1},
                })

    def test_all_status_values_in_range(self):
        lines = (f"0 GET / {status}" for status in range(100, 600))
        expected = {status: 1 for status in range(100, 600)}
        self.assertEqual(summarize(lines), {
            "valid_lines": len(expected), "malformed_lines": 0,
            "status_counts": expected,
        })

    def test_method_and_path_follow_grammar_not_http_semantics(self):
        self.assertEqual(summarize(["000 X / 200", "1 CUSTOM /a_Z/09-_ 201"]), {
            "valid_lines": 2, "malformed_lines": 0,
            "status_counts": {200: 1, 201: 1},
        })

    def test_invalid_statuses(self):
        for status in ("099", "600", "000", "999", "20", "2000", "+200", "2O0", "２００"):
            with self.subTest(status=status):
                self.assertEqual(summarize([f"0 GET / {status}"]), {
                    "valid_lines": 0, "malformed_lines": 1, "status_counts": {},
                })

    def test_invalid_timestamps_methods_and_paths(self):
        invalid = [
            "-1 GET / 200", "+1 GET / 200", "1.0 GET / 200", "١ GET / 200",
            "1 get / 200", "1 G3T / 200", "1 GÉT / 200",
            "1 GET health 200", "1 GET /a.b 200", "1 GET /x?y 200",
            "1 GET /café 200", "1 GET /../x 200", "1 GET /a\\b 200",
            " GET / 200", "1  / 200", "1 GET  200",
        ]
        for line in invalid:
            with self.subTest(line=line):
                self.assertEqual(summarize([line]), {
                    "valid_lines": 0, "malformed_lines": 1, "status_counts": {},
                })

    def test_exact_spaces_and_field_count(self):
        invalid = [
            " 1 GET / 200", "1 GET / 200 ", "1  GET / 200",
            "1 GET  / 200", "1 GET /  200", "1\tGET / 200",
            "1 GET\t/ 200", "1 GET /\t200", "1\u00a0GET / 200",
            "1 GET /", "1 GET / 200 extra", "1 GET 200",
        ]
        for line in invalid:
            with self.subTest(line=line):
                self.assertEqual(summarize([line]), {
                    "valid_lines": 0, "malformed_lines": 1, "status_counts": {},
                })

    def test_blank_bare_cr_and_extra_newlines(self):
        invalid = [
            "", "\n", "\r\n", "\r", " ", "\t",
            "1 GET / 200\r", "1 GET / 200\n\n", "1 GET / 200\r\n\r\n",
            "1 GET / 200\r\r\n", "1 GET / 200\n\r", "1 GET /\n 200",
            "1 GET / 200\r\n\n", "1 GET / 200\n\r\n",
            "1 GET / 200\v", "1 GET / 200\f", "1 GET / 200\x00",
            "1 GET / 200\u0085", "1 GET / 200\u2028", "1 GET / 200\u2029",
        ]
        for line in invalid:
            with self.subTest(line=repr(line)):
                self.assertEqual(summarize([line]), {
                    "valid_lines": 0, "malformed_lines": 1, "status_counts": {},
                })

    def test_rejects_two_records_in_one_item(self):
        self.assertEqual(summarize(["1 GET / 200\n2 GET / 503\n"]), {
            "valid_lines": 0, "malformed_lines": 1, "status_counts": {},
        })

    def test_malformed_records_do_not_stop_iteration(self):
        self.assertEqual(summarize(["bad", "1 GET / 200", "", "2 GET / 503", "bad"]), {
            "valid_lines": 2, "malformed_lines": 3,
            "status_counts": {200: 1, 503: 1},
        })

    def test_all_malformed(self):
        self.assertEqual(summarize(["bad", "", "\r"]), {
            "valid_lines": 0, "malformed_lines": 3, "status_counts": {},
        })

    def test_single_pass_iterable_and_generator(self):
        class OnePass:
            def __init__(self):
                self.iterations = 0

            def __iter__(self):
                self.iterations += 1
                if self.iterations != 1:
                    raise AssertionError("input was iterated more than once")
                yield "1 GET / 200"
                yield "bad"
                yield "2 GET / 503"

            def __len__(self):
                raise AssertionError("input length must not be requested")

        source = OnePass()
        self.assertEqual(summarize(source), {
            "valid_lines": 2, "malformed_lines": 1,
            "status_counts": {200: 1, 503: 1},
        })
        self.assertEqual(source.iterations, 1)
        generator = (f"{number} GET /same 200" for number in range(37))
        self.assertEqual(summarize(generator), {
            "valid_lines": 37, "malformed_lines": 0, "status_counts": {200: 37},
        })
        self.assertEqual(list(generator), [])
        self.assertEqual(summarize(generator), {
            "valid_lines": 0, "malformed_lines": 0, "status_counts": {},
        })

    def test_very_long_timestamp_is_not_converted_to_integer(self):
        line = "9" * 10_000 + " GET / 200"
        self.assertEqual(summarize([line]), {
            "valid_lines": 1, "malformed_lines": 0, "status_counts": {200: 1},
        })

    def test_non_string_items_raise_type_error(self):
        for item in (None, 200, True, b"1 GET / 200", []):
            with self.subTest(item=repr(item)):
                with self.assertRaisesRegex(TypeError, "each input item must be a string"):
                    summarize(iter([item]))  # type: ignore[arg-type] -- intentional invalid input

    def test_iterator_errors_propagate(self):
        def broken_stream():
            yield "1 GET / 200"
            raise OSError("synthetic stream failure")

        with self.assertRaisesRegex(OSError, "synthetic stream failure"):
            summarize(broken_stream())

    def test_calls_do_not_share_result_mappings(self):
        first = summarize(["1 GET / 200"])
        second = summarize(["2 GET / 503"])
        self.assertIsNot(first, second)
        self.assertIsNot(first["status_counts"], second["status_counts"])
        first["status_counts"][200] = 99
        self.assertEqual(second, {
            "valid_lines": 1, "malformed_lines": 0, "status_counts": {503: 1},
        })
        self.assertEqual(summarize([]), {
            "valid_lines": 0, "malformed_lines": 0, "status_counts": {},
        })

    def test_output_schema_and_invariants_for_each_prefix(self):
        lines = [
            "bad", "0 GET / 200", "1 POST /jobs 503\r\n",
            "2 GET / 200\n", "", "3 X / 100", "4 CUSTOM /x 599",
        ]
        for stop in range(len(lines) + 1):
            with self.subTest(prefix_length=stop):
                result = summarize(iter(lines[:stop]))
                self.assertIs(type(result), dict)
                self.assertEqual(set(result), {
                    "valid_lines", "malformed_lines", "status_counts",
                })
                self.assertIs(type(result["valid_lines"]), int)
                self.assertIs(type(result["malformed_lines"]), int)
                self.assertIs(type(result["status_counts"]), dict)
                self.assertGreaterEqual(result["valid_lines"], 0)
                self.assertGreaterEqual(result["malformed_lines"], 0)
                self.assertEqual(result["valid_lines"] + result["malformed_lines"], stop)
                self.assertEqual(sum(result["status_counts"].values()), result["valid_lines"])
                for status, count in result["status_counts"].items():
                    self.assertIs(type(status), int)
                    self.assertIs(type(count), int)
                    self.assertTrue(100 <= status <= 599)
                    self.assertGreater(count, 0)

    def test_non_iterable_input_raises_type_error(self):
        for source in (None, 200, True):
            with self.subTest(source=source):
                with self.assertRaises(TypeError):
                    summarize(source)  # type: ignore[arg-type] -- intentional invalid input

    def test_failure_to_create_iterator_propagates(self):
        class BrokenIterable:
            def __iter__(self):
                raise RuntimeError("synthetic iterator creation failure")

        with self.assertRaisesRegex(RuntimeError, "synthetic iterator creation failure"):
            summarize(BrokenIterable())

    def test_non_string_item_aborts_before_requesting_next_item(self):
        def stream():
            yield "0 GET / 200"
            yield None
            raise AssertionError("input must stop after a non-string item")

        with self.assertRaisesRegex(TypeError, "each input item must be a string"):
            summarize(stream())  # type: ignore[arg-type] -- intentional invalid input

    def test_str_subclass_is_accepted(self):
        class Record(str):
            pass

        self.assertEqual(summarize([Record("0 GET / 200")]), {
            "valid_lines": 1, "malformed_lines": 0, "status_counts": {200: 1},
        })


if __name__ == "__main__":
    unittest.main()
