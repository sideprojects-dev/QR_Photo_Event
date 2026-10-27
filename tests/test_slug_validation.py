import asyncio
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException

from routers import events, locations


class SlugValidationTests(unittest.TestCase):
    def test_event_names_without_usable_slug_are_rejected_before_database(self):
        for name in ("!!!", "---", "Master"):
            with self.subTest(name=name):
                with patch.object(events, "get_supabase") as get_supabase:
                    with self.assertRaises(HTTPException) as error:
                        asyncio.run(events.api_create_event(name, "test-location", Mock(), Mock()))
                self.assertEqual(error.exception.status_code, 400)
                get_supabase.assert_not_called()

    def test_location_names_without_usable_slug_are_rejected_before_database(self):
        for name in ("!!!", "---"):
            with self.subTest(name=name):
                with patch.object(locations, "get_supabase") as get_supabase:
                    with self.assertRaises(HTTPException) as error:
                        asyncio.run(locations.create_location(name))
                self.assertEqual(error.exception.status_code, 400)
                get_supabase.assert_not_called()


if __name__ == "__main__":
    unittest.main()
