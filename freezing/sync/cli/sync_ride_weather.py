from freezing.sync.data.weather import SyncRideWeather

from . import BaseCommand


class SyncRideWeatherScript(BaseCommand):
    """
    Synchronize rides from data with the database.
    """

    name = 'sync-weather'

    description = 'Sync wunderground.com weather data.'

    def build_parser(self):
        parser = super().build_parser()

        parser.add_argument("--clear", action="store_true", default=False,
                          help="Whether to clear data before fetching.")

        parser.add_argument("--cache-only", action="store_true", default=False,
                          help="Whether to only use existing cache.")

        parser.add_argument("--limit", type=int, default=0,
                          help="Limit how many rides are processed (e.g. during development)")

        return parser

    def execute(self, args):
        fetcher = SyncRideWeather(logger=self.logger)
        fetcher.sync_weather(clear=args.clear, cache_only=args.cache_only, limit=args.limit)


def main():
    SyncRideWeatherScript().run()


if __name__ == '__main__':
    main()
