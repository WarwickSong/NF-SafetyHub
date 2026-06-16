import asyncio

import pytest

from main import periodic_rules_reload


class ReloadCounter:
    def __init__(self):
        self.count = 0

    async def reload_all(self):
        self.count += 1
        if self.count >= 2:
            raise asyncio.CancelledError


@pytest.mark.asyncio
async def test_periodic_rules_reload_calls_reload_all(monkeypatch):
    counter = ReloadCounter()

    async def fast_sleep(interval):
        return None

    monkeypatch.setattr(asyncio, "sleep", fast_sleep)

    with pytest.raises(asyncio.CancelledError):
        await periodic_rules_reload(counter, 0)

    assert counter.count == 2
