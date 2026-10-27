import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException
from httpx import ConnectError

from routers import locations


class AdminLocationsTests(unittest.TestCase):
    def test_connection_failure_is_reported_without_credentials(self):
        supabase = Mock()
        query = supabase.table.return_value.select.return_value.order.return_value
        query.execute.side_effect = ConnectError("private connection details")

        with patch.object(locations, "get_supabase", return_value=supabase):
            with self.assertRaises(HTTPException) as error:
                locations.get_locations()

        self.assertEqual(error.exception.status_code, 503)
        self.assertIn("Supabase", error.exception.detail)
        self.assertNotIn("private connection details", error.exception.detail)


if __name__ == "__main__":
    unittest.main()
