import unittest
from urllib.parse import parse_qs, urlsplit

from datalake.identity import digest
from datalake.wb_advanced import data_records, later_pages, metadata_codes, reference_locations, select_indicators


def envelope(value=0, creditor="001"):
    # A structural fixture, not an acquired financial observation.
    return {"page":1,"pages":1,"source":{"id":"6","data":[{"variable":[
        {"concept":"Counterpart-Area","id":creditor,"value":"Creditor label"},
        {"concept":"Series","id":"DT.DOD.BLAT.CD","value":"Series label"},
        {"concept":"Time","id":"YR2020","value":"2020"},
        {"concept":"Country","id":"AGO","value":"Angola"}],"value":value}]}}


class AdvancedWorldBankTests(unittest.TestCase):
    def test_dimensions_are_named_and_creditor_identity_keeps_leading_zeroes(self):
        row = next(data_records(envelope()))
        self.assertEqual(row["dimensions"]["country"], "AGO")
        self.assertEqual(row["dimensions"]["counterpart_area"], "001")
        self.assertEqual(row["period"], "2020")

    def test_creditor_is_part_of_series_identity(self):
        a = next(data_records(envelope(creditor="001")))["dimensions"]
        b = next(data_records(envelope(creditor="002")))["dimensions"]
        self.assertNotEqual(digest(a), digest(b))

    def test_zero_missing_and_unexpected_dimensions_are_preserved(self):
        self.assertEqual(next(data_records(envelope(0)))["value"], 0)
        self.assertIsNone(next(data_records(envelope(None)))["value"])
        obj = envelope(); obj["source"]["data"][0]["variable"].append({"concept":"Extra Dimension","id":"A","value":"A"})
        self.assertEqual(next(data_records(obj))["dimensions"]["extra_dimension"], "A")

    def test_missing_creditor_and_numeric_code_are_rejected(self):
        obj = envelope(); obj["source"]["data"][0]["variable"].pop(0)
        with self.assertRaises(ValueError): list(data_records(obj))
        with self.assertRaises(ValueError): list(data_records(envelope(creditor=1)))

    def test_valid_empty_is_distinct_from_error_or_absent_data(self):
        obj = envelope(); obj["source"]["data"] = []
        self.assertEqual(list(data_records(obj)), [])
        obj["source"]["data"] = None; obj["total"] = 0
        self.assertEqual(list(data_records(obj)), [])
        for bad in [{"message":[{"id":"120"}]},{"source":{"id":"6"}},{"source":{"id":"2","data":[]}}]:
            with self.assertRaises(ValueError): list(data_records(bad))

    def test_conflicting_period_and_repeated_concept_are_rejected(self):
        obj = envelope(); obj["source"]["data"][0]["variable"][2]["value"] = "2019"
        with self.assertRaises(ValueError): list(data_records(obj))
        obj = envelope(); obj["source"]["data"][0]["variable"].append(obj["source"]["data"][0]["variable"][0])
        with self.assertRaises(ValueError): list(data_records(obj))

    def test_pagination_keeps_last_page_and_query_filters(self):
        urls = later_pages("https://api.worldbank.org/v2/sources/6/country/AGO?format=json&per_page=20000&page=1", {"page":1,"pages":3})
        self.assertEqual([parse_qs(urlsplit(u).query)["page"][0] for u in urls], ["2","3"])
        self.assertTrue(all(parse_qs(urlsplit(u).query)["per_page"] == ["20000"] for u in urls))
        self.assertEqual(later_pages(urls[0], {"page":2,"pages":3}), [])

    def test_metadata_source_and_labels_are_checked(self):
        obj = {"source":[{"id":"6","concept":[{"id":"Counterpart-Area","variable":[{"id":"001","value":"Austria"}]}]}]}
        self.assertEqual(metadata_codes(obj, "counterpart-area"), {"001":"Austria"})
        obj["source"][0]["id"] = "2"
        with self.assertRaises(ValueError): metadata_codes(obj, "counterpart-area")

    def test_reference_encoding_namespaces_and_label_padding(self):
        raw = 'locationName,debtorCode,creditorCode\r\nBank\xa0\xa0,,901\r\nAlbania,ALB,071\r\n'.encode('cp1252')
        result = reference_locations(raw)
        self.assertEqual(result["creditors"]["071"]["debtorCode"], "ALB")
        self.assertEqual(result["creditors"]["901"]["locationName"], "Bank\xa0\xa0")
        self.assertEqual(result["creditors"]["901"]["display_label"], "Bank")
        self.assertNotIn("901", result["debtors"])

    def test_duplicate_reference_codes_are_rejected(self):
        raw = b'locationName,debtorCode,creditorCode\r\nOne,AAA,001\r\nTwo,BBB,001\r\n'
        with self.assertRaises(ValueError): reference_locations(raw)

    def test_only_catalogued_indicators_are_selected(self):
        catalog = {"DT.DOD.BLAT.CD":{},"DT.AMT.PCBK.CD":{},"UNRELATED":{}}
        self.assertEqual(select_indicators(catalog), ["DT.DOD.BLAT.CD"])
        self.assertEqual(select_indicators(catalog, full=True), ["DT.AMT.PCBK.CD","DT.DOD.BLAT.CD"])


if __name__ == "__main__":
    unittest.main()
