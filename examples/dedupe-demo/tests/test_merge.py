"""受入基準。デモを解く際はこのファイルを変更しない。"""

import copy
import unittest

from src.merge import merge_records


class MergeContractTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(merge_records([], []), [])

    def test_new_records_append(self):
        self.assertEqual(
            merge_records([{"id": "a", "text": "old"}], [{"id": "b", "text": "new"}]),
            [{"id": "a", "text": "old"}, {"id": "b", "text": "new"}],
        )

    def test_same_input_twice_is_idempotent(self):
        records = [{"id": "a", "text": "alpha"}, {"id": "b", "text": "beta"}]
        first = merge_records([], records)
        self.assertEqual(merge_records(first, records), first)

    def test_last_value_wins_but_first_position_is_preserved(self):
        existing = [{"id": "a", "text": "old"}, {"id": "b", "text": "B"}]
        incoming = [{"id": "c", "text": "C"}, {"id": "a", "text": "new"}]
        self.assertEqual(
            merge_records(existing, incoming),
            [{"id": "a", "text": "new"}, {"id": "b", "text": "B"}, {"id": "c", "text": "C"}],
        )

    def test_duplicates_inside_each_input_are_normalized(self):
        self.assertEqual(
            merge_records(
                [{"id": "a", "text": "1"}, {"id": "a", "text": "2"}],
                [{"id": "b", "text": "3"}, {"id": "b", "text": "4"}],
            ),
            [{"id": "a", "text": "2"}, {"id": "b", "text": "4"}],
        )

    def test_later_record_replaces_whole_record(self):
        self.assertEqual(
            merge_records([{"id": "a", "removed": True}], [{"id": "a", "text": "最新"}]),
            [{"id": "a", "text": "最新"}],
        )

    def test_inputs_are_not_modified(self):
        old = [{"id": "a", "text": "before"}]
        new = [{"id": "a", "text": "after"}]
        before = copy.deepcopy([old, new])
        merge_records(old, new)
        self.assertEqual([old, new], before)

    def test_invalid_ids_raise_value_error(self):
        for record in [{}, {"id": ""}, {"id": None}, {"id": 1}, {"id": "   "}]:
            with self.subTest(record=record):
                with self.assertRaises(ValueError):
                    merge_records([], [record])
                with self.assertRaises(ValueError):
                    merge_records([record], [])

    def test_distinct_ids_are_not_trimmed(self):
        self.assertEqual(
            merge_records([], [{"id": "a"}, {"id": " a "}]),
            [{"id": "a"}, {"id": " a "}],
        )


if __name__ == "__main__":
    unittest.main()
