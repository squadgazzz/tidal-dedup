import pytest
from unittest.mock import AsyncMock
import tidalapi.exceptions
import requests.exceptions

from tidal_dedup.retry import retry_on_rate_limit


@pytest.mark.asyncio
async def test_retry_succeeds_on_first_try():
    func = AsyncMock(return_value="ok")
    result = await retry_on_rate_limit(func, "arg1")
    assert result == "ok"
    func.assert_awaited_once_with("arg1")


@pytest.mark.asyncio
async def test_retry_retries_on_too_many_requests(mocker):
    mocker.patch("tidal_dedup.retry.asyncio.sleep", new_callable=AsyncMock)
    func = AsyncMock(side_effect=[tidalapi.exceptions.TooManyRequests("429"), "ok"])
    result = await retry_on_rate_limit(func)
    assert result == "ok"
    assert func.await_count == 2


@pytest.mark.asyncio
async def test_retry_retries_on_request_exception(mocker):
    mocker.patch("tidal_dedup.retry.asyncio.sleep", new_callable=AsyncMock)
    exc = requests.exceptions.ConnectionError("conn err")
    func = AsyncMock(side_effect=[exc, "ok"])
    result = await retry_on_rate_limit(func)
    assert result == "ok"


@pytest.mark.asyncio
async def test_retry_aborts_after_max_retries(mocker):
    mocker.patch("tidal_dedup.retry.asyncio.sleep", new_callable=AsyncMock)
    func = AsyncMock(side_effect=tidalapi.exceptions.TooManyRequests("429"))
    with pytest.raises(SystemExit):
        await retry_on_rate_limit(func, max_retries=2)
    assert func.await_count == 3  # initial + 2 retries


@pytest.mark.asyncio
async def test_retry_escalating_sleep(mocker):
    sleep_mock = mocker.patch("tidal_dedup.retry.asyncio.sleep", new_callable=AsyncMock)
    func = AsyncMock(side_effect=[
        tidalapi.exceptions.TooManyRequests("429"),
        tidalapi.exceptions.TooManyRequests("429"),
        "ok"
    ])
    await retry_on_rate_limit(func)
    assert sleep_mock.call_args_list[0][0][0] == 1
    assert sleep_mock.call_args_list[1][0][0] == 10
