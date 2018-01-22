from freezing.sync.cli import BaseCommand
from freezing.sync.strava.streams import ActivityStreamFetcher


class SyncActivityStreams(BaseCommand):
    name = 'sync-activity-streams'
    description = 'Sync activity streams.'

    def build_parser(self):
        parser = super().build_parser()
        parser.add_argument("--athlete-id", type=int,
                          help="Just sync rides for a specific athlete.",
                          metavar="STRAVA_ID")

        parser.add_argument("--max-records", type=int,
                          help="Limit number of rides to return.",
                          metavar="NUM")

        parser.add_argument("--use-cache", action="store_true", default=False,
                          help="Whether to use cached activities (rather than refetch from server).")

        parser.add_argument("--only-cache", action="store_true", default=False,
                          help="Whether to use only cached activities (rather than fetch anything from server).")

        parser.add_argument("--rewrite", action="store_true", default=False,
                          help="Whether to re-write all activity details.")

        return parser


    def execute(self, args):

        fetcher = ActivityStreamFetcher(logger=self.logger)
        fetcher.execute(athlete_id=args.athlete_id, rewrite=args.rewrite, use_cache=args.use_cache,
                        only_cache=args.only_cache, max_records=args.max_records)

def main():
    SyncActivityStreams().run()


if __name__ == '__main__':
    main()