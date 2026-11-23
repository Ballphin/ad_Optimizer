import base64
import hashlib
import hmac
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import envfile  # noqa: E402
import naver_searchad as ns  # noqa: E402
import coupang_api as cp  # noqa: E402


class EnvTest(unittest.TestCase):
    def test_parses_values_and_ignores_comments(self):
        f = tempfile.NamedTemporaryFile("w", suffix=".env", delete=False)
        f.write("# comment\nA=1\nB= two  # trailing\nC=\nD=\"q\"\n")
        f.close()
        env = envfile.load(f.name)
        self.assertEqual(env["A"], "1")
        self.assertEqual(env["B"], "two")
        self.assertEqual(env["C"], "")
        self.assertEqual(env["D"], "q")


class NaverSignTest(unittest.TestCase):
    def test_signature_matches_spec(self):
        # 스펙: base64(HMAC-SHA256(secret, "{timestamp}.{METHOD}.{uri}"))
        expected = base64.b64encode(
            hmac.new(b"secret", b"1700000000000.GET./ncc/campaigns", hashlib.sha256).digest()
        ).decode()
        self.assertEqual(ns.sign("1700000000000", "GET", "/ncc/campaigns", "secret"), expected)

    def test_headers(self):
        h = ns.headers("GET", "/ncc/campaigns", "key", "secret", "123", ts="1700000000000")
        self.assertEqual(h["X-API-KEY"], "key")
        self.assertEqual(h["X-Customer"], "123")
        self.assertEqual(h["X-Timestamp"], "1700000000000")
        self.assertEqual(h["X-Signature"], ns.sign("1700000000000", "GET", "/ncc/campaigns", "secret"))

    def test_client_refuses_write_methods(self):
        c = ns.Client("k", "s", "1")
        with self.assertRaises(PermissionError):
            c.request("PUT", "/ncc/keywords/abc")
        with self.assertRaises(PermissionError):
            c.request("POST", "/ncc/keywords")


class KeywordLockTest(unittest.TestCase):
    def test_only_userlock_field_is_sent(self):
        c = ns.Client("k", "s", "1")
        calls = []
        c.get = lambda uri, **p: {"nccKeywordId": "nkw-1", "nccAdgroupId": "grp-1", "bidAmt": 70, "userLock": False}
        c._send = lambda method, uri, params=None, body=None, raw=False: calls.append((method, uri, params, body)) or body
        c.set_keyword_lock("nkw-1", True)
        method, uri, params, body = calls[0]
        self.assertEqual((method, uri, params), ("PUT", "/ncc/keywords/nkw-1", {"fields": "userLock"}))
        self.assertEqual(body, {"nccKeywordId": "nkw-1", "nccAdgroupId": "grp-1", "userLock": True})

    def test_rejects_non_keyword_ids(self):
        c = ns.Client("k", "s", "1")
        with self.assertRaises(ValueError):
            c.set_keyword_lock("grp-a001-01-000000001", True)


class BidChangeTest(unittest.TestCase):
    def _client(self, current):
        c = ns.Client("k", "s", "1")
        c.calls = []
        c.get = lambda uri, **p: dict(current)
        c._send = lambda method, uri, params=None, body=None, raw=False: c.calls.append((method, uri, params, body)) or body
        return c

    def test_keyword_bid_sends_only_bid_fields_and_disables_group_bid(self):
        c = self._client({"nccKeywordId": "nkw-1", "nccAdgroupId": "grp-1", "bidAmt": 70, "useGroupBidAmt": True,
                          "userLock": False, "keyword": "x"})
        c.set_keyword_bid("nkw-1", 300)
        method, uri, params, body = c.calls[0]
        self.assertEqual((method, uri, params), ("PUT", "/ncc/keywords/nkw-1", {"fields": "bidAmt"}))
        self.assertEqual(body, {"nccKeywordId": "nkw-1", "nccAdgroupId": "grp-1", "bidAmt": 300,
                                "useGroupBidAmt": False})

    def test_adgroup_bid_changes_only_bid(self):
        cur = {"nccAdgroupId": "grp-1", "nccCampaignId": "cmp-1", "bidAmt": 1200, "dailyBudget": 20000, "name": "g"}
        c = self._client(cur)
        c.set_adgroup_bid("grp-1", 600)
        method, uri, params, body = c.calls[0]
        self.assertEqual((method, uri, params), ("PUT", "/ncc/adgroups/grp-1", {"fields": "bidAmt"}))
        self.assertEqual(body, {**cur, "bidAmt": 600})

    def test_bid_limits_and_id_formats(self):
        c = self._client({"nccKeywordId": "nkw-1", "nccAdgroupId": "grp-1"})
        for bad in (60, 1501, 305):  # 최소 70원, 안전 상한 1,500원, 10원 단위
            with self.assertRaises(ValueError):
                c.set_keyword_bid("nkw-1", bad)
        with self.assertRaises(ValueError):
            c.set_keyword_bid("grp-1", 300)
        with self.assertRaises(ValueError):
            c.set_adgroup_bid("nkw-1", 300)
        self.assertEqual(c.calls, [])


class CoupangSignTest(unittest.TestCase):
    def test_authorization_header(self):
        dt = "261122T120000Z"
        path, query = "/v2/providers/openapi/apis/api/v4/vendors/A1/ordersheets", "status=ACCEPT"
        sig = hmac.new(b"sk", (dt + "GET" + path + query).encode(), hashlib.sha256).hexdigest()
        self.assertEqual(
            cp.authorization("GET", path, query, "ak", "sk", signed_date=dt),
            f"CEA algorithm=HmacSHA256, access-key=ak, signed-date={dt}, signature={sig}",
        )


if __name__ == "__main__":
    unittest.main()
