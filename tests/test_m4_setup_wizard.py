"""M4: except narrowing tests for setup_wizard.py"""

import sys

import pytest

from modules.core.errors import ErrorCode, ZettarancError


class TestSetupWizardConnectionFallback:
    """`test_baostock_connection` 在连通性测试抛错时返回 False"""

    def test_returns_false_on_os_error(self, monkeypatch):
        from modules import setup_wizard as sw

        def failing_get_client():
            raise OSError("network down")

        monkeypatch.setattr("modules.baostock_client.get_client", failing_get_client)
        assert sw.test_baostock_connection() is False

    def test_returns_false_on_connection_error(self, monkeypatch):
        from modules import setup_wizard as sw

        def failing_get_client():
            raise ConnectionError("connection refused")

        monkeypatch.setattr("modules.baostock_client.get_client", failing_get_client)
        assert sw.test_baostock_connection() is False


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
