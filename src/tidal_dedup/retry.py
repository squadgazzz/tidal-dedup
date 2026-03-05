import asyncio
import sys
import traceback

import requests.exceptions
import tidalapi.exceptions

SLEEP_SCHEDULE = {5: 1, 4: 10, 3: 60, 2: 5 * 60, 1: 10 * 60}


async def retry_on_rate_limit(func, *args, max_retries=5, **kwargs):
    """Call an async function with escalating backoff on rate limit / request errors."""
    remaining = max_retries
    while True:
        try:
            return await func(*args, **kwargs)
        except (
            tidalapi.exceptions.TooManyRequests,
            requests.exceptions.RequestException,
        ) as e:
            if remaining <= 0:
                print(f"{e} could not be recovered after {max_retries} retries. Aborting.")
                print(traceback.format_exc())
                sys.exit(1)
            sleep_time = SLEEP_SCHEDULE.get(remaining, 1)
            print(f"{e} — retrying in {sleep_time}s ({remaining} retries left)")
            await asyncio.sleep(sleep_time)
            remaining -= 1
