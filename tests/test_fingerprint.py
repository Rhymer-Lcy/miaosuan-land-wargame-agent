from __future__ import annotations

import json
import unittest

from miaosuan_agent.fingerprint import Detail, digest, fingerprint
from tests.fixtures import synthetic as syn


class RecordAndKeyedTest(unittest.TestCase):
    def test_observation_fields_and_key_kinds(self) -> None:
        node = fingerprint(syn.observation(0))
        self.assertEqual(node["kind"], "record")
        self.assertEqual(set(node["fields"]), set(syn.observation(0)))
        valid = node["fields"]["valid_actions"]
        self.assertEqual((valid["kind"], valid["key_kinds"]), ("keyed", ["int"]))
        self.assertEqual(valid["values"]["key_kinds"], ["int"])

    def test_json_round_trip_changes_key_kind(self) -> None:
        node = fingerprint(syn.json_round_trip(syn.observation(0)))
        self.assertEqual(node["fields"]["valid_actions"]["key_kinds"], ["numeric-str"])
        self.assertNotEqual(digest(node), digest(fingerprint(syn.observation(0))))

    def test_interface_values_only(self) -> None:
        node = fingerprint(syn.observation(0, stage=2))
        self.assertEqual(node["fields"]["time"]["fields"]["stage"], {"kind": "int", "value": 2})
        seat = node["fields"]["role_and_grouping_info"]["values"]
        self.assertEqual(seat["fields"]["end_deployment"], {"kind": "bool", "value": True})
        self.assertEqual(node["fields"]["scenario_id"], {"kind": "int"})


class PrivacyTest(unittest.TestCase):
    def test_no_identifiers_names_or_positions_leak(self) -> None:
        for detail in Detail:
            text = json.dumps(fingerprint(syn.observation(-1), detail))
            with self.subTest(detail=detail.value):
                for secret in (syn.RED_UNIT, syn.BLUE_UNIT, 900000 + syn.RED_SEAT, 900000 + syn.BLUE_SEAT, syn.SCENARIO_ID,
                               syn.TERRAIN_ID, 1203, 1407, 1305):
                    self.assertNotIn(str(secret), text)
                self.assertNotIn("synthetic-red", text)
                self.assertNotIn("synthetic objective", text)

    def test_public_detail_reduces_unit_records_to_a_count(self) -> None:
        public = fingerprint(syn.observation(0), Detail.PUBLIC)["fields"]["operators"]["items"]
        private = fingerprint(syn.observation(0), Detail.PRIVATE)["fields"]["operators"]["items"]
        self.assertEqual(public, {"kind": "record", "field_count": len(syn.unit(1, 0, 1))})
        self.assertIn("obj_id", private["fields"])


class MergeAndDigestTest(unittest.TestCase):
    def test_merge_reports_values_optional_fields_and_emptiness(self) -> None:
        raw = syn.observation(-1)
        raw["role_and_grouping_info"][syn.BLUE_SEAT]["end_deployment"] = True
        del raw["role_and_grouping_info"][syn.BLUE_SEAT]["user_id"]
        raw["role_and_grouping_info"][syn.BLUE_SEAT]["operators"] = []
        seat = fingerprint(raw)["fields"]["role_and_grouping_info"]["values"]
        self.assertEqual(seat["fields"]["end_deployment"], {"kind": "bool", "values": [False, True]})
        self.assertEqual(seat["optional"], ["user_id"])
        self.assertEqual(seat["fields"]["operators"]["empty"], [False, True])

    def test_mixed_item_types_become_a_union(self) -> None:
        node = fingerprint([1, "a"])
        self.assertEqual(node["items"]["kind"], "union")

    def test_digest_is_order_independent_and_type_sensitive(self) -> None:
        a = syn.observation(0)
        b = dict(reversed(list(a.items())))
        self.assertEqual(digest(fingerprint(a)), digest(fingerprint(b)))
        c = syn.observation(0)
        c["terrain_id"] = str(c["terrain_id"])
        self.assertNotEqual(digest(fingerprint(a)), digest(fingerprint(c)))


if __name__ == "__main__":
    unittest.main()
