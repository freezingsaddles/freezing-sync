import os

from datetime import datetime
from logging import Logger, getLogger

from pickle import dump, load, UnpicklingError

from darksky.api import DarkSky
from darksky.types import weather


class HistoDarkSky(object):
    """
    Histomorphic dark sky.
    """

    def __init__(self, api_key: str, cache_dir: str = None, cache_only: bool = False, logger: Logger = None):
        self.logger = logger or getLogger(__name__)
        self.cache_dir = cache_dir
        self.cache_only = cache_only
        self.dark_sky = DarkSky(api_key)
        if cache_only and not cache_dir:
            raise RuntimeError('Cache only but no cache dir 8(')

    def histo_forecast(self, time: datetime, longitude: float, latitude: float):
        return self._get_cached(
            time=time,
            longitude=longitude,
            latitude=latitude,
            fetch=lambda: self.dark_sky.get_time_machine_forecast(
                time=time,
                longitude=longitude,
                latitude=latitude,
                exclude=[weather.MINUTELY, weather.ALERTS]
            )
        )

    def _get_cached(self, time: datetime, longitude: float, latitude: float, fetch):
        if not self.cache_dir:
            return fetch()

        directory = os.path.join(self.cache_dir, f'{longitude}x{latitude}')
        path = os.path.join(directory, f'{time.strftime("%Y-%m-%d")}.pykl')
        if not os.path.exists(directory):
            os.makedirs(directory)

        if os.path.exists(path):
            self.logger.debug(f'Cache hit for {path}')
            try:
                with open(path, 'rb') as file:
                    return load(file)
            except UnpicklingError:
                self.logger.warning(f'Error reading cache file {path}')
                os.remove(path)

        if self.cache_only:
            raise RuntimeError(f'No cache entry for {path} and cache_only is true')

        self.logger.debug(f'Cache miss for {path}')
        data = fetch()
        with open(path, 'wb') as file:
            dump(data, file)
        return data

