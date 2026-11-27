import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tools.nl2sql import sql as module
from tools.nl2sql.contracts import NL2SQLError


async def test_connect_returning_after_deadline_never_executes_sql(source, monkeypatch):
    monkeypatch.setattr(module, "SQL_TIMEOUT", 0.01)
    connection = Mock()
    credential = Mock()
    credential.get_token.return_value = SimpleNamespace(token="token")

    def connect(*args, **kwargs):
        time.sleep(0.03)
        return connection

    executor = module.SQLExecutor(credential, connect=connect)
    try:
        with pytest.raises(NL2SQLError, match="SQL_TIMEOUT"):
            await executor.execute(source, "SELECT 1", "id")
        await executor.close()
        connection.cursor.assert_not_called()
        connection.close.assert_called_once()
    finally:
        await executor.close()
