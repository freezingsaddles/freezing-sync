from freezing.sync.data.weather import WeatherSync

from . import BaseCommand


class SyncWeatherScript(BaseCommand):
    """
    Synchronize rides from data with the database.
    """

    name = "sync-weather"

    description = "Sync wunderground.com weather data."

    def build_parser(self):
        """
        Build the argument parser for the command.

        :return: The argument parser.
        """
        parser = super().build_parser()

        parser.add_argument(
            "--clear",
            action="store_true",
            default=False,
            help="Whether to clear data before fetching.",
        )

        parser.add_argument(
            "--cache-only",
            action="store_true",
            default=False,
            help="Whether to only use existing cache.",
        )

        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Limit how many rides are processed (e.g. during development)",
        )

        return parser

    def execute(self, args):
        """
        Perform actual implementation for this command.

        :param args: The parsed options/args from argparse.
        """
        fetcher = WeatherSync(logger=self.logger)
        fetcher.sync_weather(
            clear=args.clear, cache_only=args.cache_only, limit=args.limit
        )


def main():
    SyncWeatherScript().run()


if __name__ == "__main__":
    main()
