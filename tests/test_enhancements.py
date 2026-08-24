"""
Unit tests for DirectSiteSearchHub and RelayServer.
"""

import unittest
from core.direct_site_search import DirectSiteSearchHub
from core.relay_server import RelayServer


class TestEnhancements(unittest.TestCase):
    def test_direct_search_endpoints_structure(self):
        hub = DirectSiteSearchHub()
        self.assertGreater(len(hub.SEARCH_ENDPOINTS), 3)
        for cfg in hub.SEARCH_ENDPOINTS:
            self.assertIn("name", cfg)
            self.assertIn("url", cfg)
            self.assertIn("base_url", cfg)

    def test_relay_server_init(self):
        server = RelayServer(port=8765, output_dir="test_downloads")
        self.assertEqual(server.port, 8765)
        self.assertEqual(server.host, "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
