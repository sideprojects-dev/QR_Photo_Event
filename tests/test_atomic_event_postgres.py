"""Opt-in PostgreSQL integration tests; never connect to a remote database.

Run with H6_PG_CONTAINER=qr-h6-pg-test against an isolated, networkless Docker
container. The fixture uses only columns referenced by this repository. The
production column types and constraints still require a manual schema check.
"""

import json
import os
import subprocess
import unittest
from pathlib import Path


CONTAINER = "qr-h6-pg-test"
MIGRATION = Path(__file__).resolve().parents[1] / "20261029_ATOMIC_EVENT_ACTIVATION.sql"
SCHEMA = """
CREATE TABLE public.locations (
    id bigint, slug text, name text,
    folder_id text, created_at timestamp
);
CREATE TABLE public.events (
    id bigint, slug text CONSTRAINT events_slug_unique UNIQUE, name text,
    folder_id text, created_at timestamp, status text,
    location_id bigint
);
"""
ROLES = """
DO $roles$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        CREATE ROLE anon NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        CREATE ROLE authenticated NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
        CREATE ROLE service_role NOLOGIN;
    END IF;
END;
$roles$;
GRANT USAGE ON SCHEMA public TO service_role;
GRANT SELECT, UPDATE ON public.locations, public.events TO service_role;
"""
SEED = """
TRUNCATE public.events, public.locations;
INSERT INTO public.locations (id, slug) VALUES (1, 'venue-a'), (2, 'venue-b');
INSERT INTO public.events (id, slug, status, location_id) VALUES
 (11, 'a1', 'active', 1), (12, 'a2', 'archived', 1),
 (13, 'a3', 'archived', 1), (21, 'b1', 'active', 2),
 (22, 'b2', 'archived', 2);
"""


def psql(database, sql, *, check=True):
    result = subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "psql", "-X", "-qAt",
         "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", database],
        input=sql, text=True, capture_output=True, timeout=30,
    )
    if check and result.returncode:
        raise AssertionError(result.stderr)
    return result


def start_sql(database, sql):
    process = subprocess.Popen(
        ["docker", "exec", "-i", CONTAINER, "psql", "-X", "-qAt",
         "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", database],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
    )
    process.stdin.write(sql)
    process.stdin.close()
    process.stdin = None
    return process


def wait_for_lock_marker(process):
    # psql can emit an empty line for BEGIN before the SELECT result.
    for _ in range(4):
        if process.stdout.readline().strip() == "LOCKED":
            return
    raise AssertionError("The local PostgreSQL lock was not acquired")


@unittest.skipUnless(os.getenv("H6_PG_CONTAINER") == CONTAINER,
                     "Set H6_PG_CONTAINER for the isolated local PostgreSQL test")
class AtomicEventPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        details = subprocess.run(
            ["docker", "inspect", CONTAINER], text=True, capture_output=True,
            timeout=10, check=True,
        )
        container = json.loads(details.stdout)[0]
        host = container["HostConfig"]
        mounts = container.get("Mounts", [])
        anonymous_data_volume = (
            len(mounts) == 1
            and mounts[0].get("Type") == "volume"
            and mounts[0].get("Destination") == "/var/lib/postgresql/data"
            and not host.get("Binds")
        )
        if (container["Config"]["Image"] != "postgres:16-alpine"
                or host["NetworkMode"] != "none"
                or not anonymous_data_volume
                or any(host.get("PortBindings") or {})):
            raise RuntimeError("Refusing a container with network, ports, or mounts")

        cls.database = f"h6_test_{os.getpid()}"
        cls.bad_database = f"h6_bad_{os.getpid()}"
        for database in (cls.database, cls.bad_database):
            psql("postgres", f"CREATE DATABASE {database};")
            psql(database, SCHEMA)
        psql(cls.database, ROLES)
        psql(cls.database, MIGRATION.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        for database in (cls.database, cls.bad_database):
            psql("postgres", f"DROP DATABASE IF EXISTS {database} WITH (FORCE);")

    def setUp(self):
        psql(self.database, SEED)

    def active(self, location_id):
        return psql(self.database, f"""
            SELECT slug FROM public.events
            WHERE location_id = {location_id} AND status = 'active' ORDER BY slug;
        """).stdout.strip().splitlines()

    def activate(self, slug, location):
        return psql(self.database,
                    f"SELECT public.activate_event_atomic('{slug}', '{location}');"
                    ).stdout.strip()

    def test_activation_without_previous_event(self):
        psql(self.database, "UPDATE public.events SET status='archived' WHERE slug='a1';")
        self.assertIn("activated", self.activate("a2", "venue-a"))
        self.assertEqual(self.active(1), ["a2"])
        self.assertEqual(self.active(2), ["b1"])

    def test_replacement_and_repeat_are_predictable(self):
        self.assertIn("activated", self.activate("a2", "venue-a"))
        self.assertEqual(self.active(1), ["a2"])
        before_xmin = psql(self.database,
                           "SELECT xmin::text FROM public.events WHERE slug='a2';").stdout
        self.assertIn("already_active", self.activate("a2", "venue-a"))
        after_xmin = psql(self.database,
                          "SELECT xmin::text FROM public.events WHERE slug='a2';").stdout
        self.assertEqual(before_xmin, after_xmin)
        self.assertEqual(self.active(2), ["b1"])

    def test_missing_and_wrong_location_leave_active_event_unchanged(self):
        self.assertIn("event_not_found", self.activate("missing", "venue-a"))
        self.assertIn("location_mismatch", self.activate("a2", "venue-b"))
        self.assertEqual(self.active(1), ["a1"])
        self.assertEqual(self.active(2), ["b1"])

    def test_error_after_archiving_rolls_back_previous_active_event(self):
        psql(self.database, """
            CREATE FUNCTION public.h6_reject_a2() RETURNS trigger
            LANGUAGE plpgsql AS $body$
            BEGIN
                IF NEW.slug = 'a2' AND NEW.status = 'active' THEN
                    RAISE EXCEPTION 'simulated activation failure';
                END IF;
                RETURN NEW;
            END;
            $body$;
            CREATE TRIGGER h6_reject_a2 BEFORE UPDATE ON public.events
            FOR EACH ROW EXECUTE FUNCTION public.h6_reject_a2();
        """)
        try:
            result = psql(self.database,
                          "SELECT public.activate_event_atomic('a2', 'venue-a');",
                          check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(self.active(1), ["a1"])
        finally:
            psql(self.database, "DROP TRIGGER h6_reject_a2 ON public.events; "
                                "DROP FUNCTION public.h6_reject_a2();")

    def test_unique_index_rejects_second_active_event(self):
        existing_slug_constraint = psql(self.database, """
            SELECT count(*) FROM pg_constraint
            WHERE conname='events_slug_unique';
        """).stdout.strip()
        redundant_slug_index = psql(self.database, """
            SELECT count(*) FROM pg_indexes
            WHERE schemaname='public' AND indexname='events_slug_unique_idx';
        """).stdout.strip()
        self.assertEqual(existing_slug_constraint, "1")
        self.assertEqual(redundant_slug_index, "0")
        result = psql(self.database,
                      "UPDATE public.events SET status='active' WHERE slug='a2';",
                      check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.active(1), ["a1"])

    def test_two_simultaneous_activations_same_location_end_with_one_active(self):
        blocker = start_sql(self.database, """
            BEGIN;
            SELECT 'LOCKED' FROM public.locations WHERE id=1 FOR UPDATE;
            SELECT pg_sleep(2);
            COMMIT;
        """)
        try:
            wait_for_lock_marker(blocker)
            first = start_sql(self.database,
                              "SELECT public.activate_event_atomic('a2','venue-a');")
            second = start_sql(self.database,
                               "SELECT public.activate_event_atomic('a3','venue-a');")
            first_out, first_err = first.communicate(timeout=10)
            second_out, second_err = second.communicate(timeout=10)
            self.assertEqual(first.returncode, 0, first_err)
            self.assertEqual(second.returncode, 0, second_err)
            self.assertIn("activated", first_out)
            self.assertIn("activated", second_out)
            self.assertEqual(len(self.active(1)), 1)
            self.assertIn(self.active(1)[0], ("a2", "a3"))
            self.assertEqual(self.active(2), ["b1"])
        finally:
            blocker.communicate(timeout=10)

    def test_different_location_is_not_blocked_by_location_row_lock(self):
        blocker = start_sql(self.database, """
            BEGIN;
            SELECT 'LOCKED' FROM public.locations WHERE id=1 FOR UPDATE;
            SELECT pg_sleep(3);
            COMMIT;
        """)
        try:
            wait_for_lock_marker(blocker)
            other = start_sql(self.database,
                              "SELECT public.activate_event_atomic('b2','venue-b');")
            out, err = other.communicate(timeout=2)
            self.assertEqual(other.returncode, 0, err)
            self.assertIn("activated", out)
            self.assertEqual(self.active(2), ["b2"])
        finally:
            blocker.communicate(timeout=10)

    def test_function_privileges_are_enforced_for_non_superuser_roles(self):
        privileges = psql(self.database, """
            SELECT has_function_privilege('anon',
                'public.activate_event_atomic(text,text)', 'EXECUTE'),
                   has_function_privilege('authenticated',
                'public.activate_event_atomic(text,text)', 'EXECUTE'),
                   has_function_privilege('service_role',
                'public.activate_event_atomic(text,text)', 'EXECUTE');
        """).stdout.strip()
        self.assertEqual(privileges, "f|f|t")
        for role in ("anon", "authenticated"):
            result = psql(self.database,
                          f"SET ROLE {role}; SELECT public.activate_event_atomic('a2','venue-a');",
                          check=False)
            self.assertNotEqual(result.returncode, 0)
        result = psql(self.database,
                      "SET ROLE service_role; "
                      "SELECT public.activate_event_atomic('a2','venue-a');")
        self.assertIn("activated", result.stdout)
        self.assertEqual(self.active(1), ["a2"])

    def test_duplicate_active_data_aborts_entire_migration_without_changes(self):
        psql(self.bad_database, """
            INSERT INTO public.locations (id, slug) VALUES (1, 'venue-a');
            INSERT INTO public.events (id, slug, status, location_id) VALUES
                (11, 'a1', 'active', 1), (12, 'a2', 'active', 1);
        """)
        migration = psql(self.bad_database,
                         MIGRATION.read_text(encoding="utf-8"), check=False)
        self.assertNotEqual(migration.returncode, 0)
        count = psql(self.bad_database,
                     "SELECT count(*) FROM public.events WHERE status='active';").stdout.strip()
        self.assertEqual(count, "2")
        function = psql(self.bad_database,
                        "SELECT to_regprocedure('public.activate_event_atomic(text,text)');"
                        ).stdout.strip()
        self.assertEqual(function, "")
        indexes = psql(self.bad_database,
                       "SELECT count(*) FROM pg_indexes WHERE schemaname='public' "
                       "AND indexname='events_one_active_per_location_idx';"
                       ).stdout.strip()
        self.assertEqual(indexes, "0")


if __name__ == "__main__":
    unittest.main()
