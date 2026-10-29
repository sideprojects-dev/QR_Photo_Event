import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import deps


class SupabaseClientReuseTests(unittest.TestCase):
    def tearDown(self):
        for name in ("supabase_client", "supabase_config"):
            if hasattr(deps._thread_local, name):
                delattr(deps._thread_local, name)

    def test_reuses_client_within_thread_and_recreates_after_config_change(self):
        with patch.object(deps, "create_client", side_effect=lambda *args: object()) as create:
            with patch.dict(os.environ, {"SUPABASE_URL": "https://one.supabase.co",
                                        "SUPABASE_SERVICE_ROLE_KEY": "key-one"}):
                first = deps.get_supabase()
                self.assertIs(deps.get_supabase(), first)
                self.assertEqual(create.call_count, 1)
            with patch.dict(os.environ, {"SUPABASE_URL": "https://two.supabase.co",
                                        "SUPABASE_SERVICE_ROLE_KEY": "key-two"}):
                second = deps.get_supabase()
                self.assertIsNot(second, first)
                self.assertEqual(create.call_count, 2)

    def test_missing_key_never_returns_cached_client(self):
        with patch.object(deps, "create_client", return_value=object()), \
             patch.dict(os.environ, {"SUPABASE_URL": "https://one.supabase.co",
                                          "SUPABASE_SERVICE_ROLE_KEY": "key-one"}):
            deps.get_supabase()
            del os.environ["SUPABASE_SERVICE_ROLE_KEY"]
            with self.assertRaisesRegex(RuntimeError, "missing"):
                deps.get_supabase()

    def test_concurrent_threads_do_not_share_clients(self):
        created = []
        lock = threading.Lock()
        barrier = threading.Barrier(4)

        def create(*_):
            client = object()
            with lock:
                created.append(client)
            return client

        def request_pair():
            barrier.wait(timeout=5)
            first = deps.get_supabase()
            return first, deps.get_supabase()

        with patch.object(deps, "create_client", side_effect=create), \
             patch.dict(os.environ, {"SUPABASE_URL": "https://one.supabase.co",
                                          "SUPABASE_SERVICE_ROLE_KEY": "key-one"}), \
             ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: request_pair(), range(4)))

        self.assertEqual(len(created), 4)
        self.assertEqual(len({id(pair[0]) for pair in results}), 4)
        self.assertTrue(all(first is second for first, second in results))


if __name__ == "__main__":
    unittest.main()
