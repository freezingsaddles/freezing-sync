from freezing.model import meta, orm

from freezing.sync.data.athlete import AthleteSync

from . import BaseCommand


class SyncAthletesScript(BaseCommand):
    """
    Updates the athlete records, and associates with teams.

    (Designed to be run periodically to ensure that things like names and team
    membership are kept in sync w/ Strava.)
    """

    name = 'sync-athletes'

    description = 'Sync all athletes.'

    def build_parser(self):
        parser = super().build_parser()

        parser.add_argument("--max-records", type=int,
                            help="Limit number of rides to return.",
                            metavar="NUM")

        return parser

    def execute(self, args):
        fetcher = AthleteSync(logger=self.logger)
        fetcher.sync_athletes(max_records=args.max_records)


def main():
    SyncAthletesScript().run()


if __name__ == '__main__':
    main()