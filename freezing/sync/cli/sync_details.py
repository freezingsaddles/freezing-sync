from freezing.sync.cli import BaseCommand
from freezing.sync.data.activity import ActivitySync


class SyncActivityDetails(BaseCommand):
    name = "sync-activity-detail"
    description = "Sync the activity details JSON."

    def build_parser(self):
        parser = super().build_parser()
        parser.add_argument(
            "--athlete-id",
            type=int,
            help="Just sync rides for a specific athlete.",
            metavar="STRAVA_ID",
        )

        parser.add_argument(
            "--activity-id",
            type=int,
            help="Just sync rides for a specific activity.",
        )

        parser.add_argument(
            "--max-records",
            type=int,
            help="Limit number of rides to return.",
            metavar="NUM",
        )

        parser.add_argument(
            "--use-cache",
            action="store_true",
            default=False,
            help="Whether to use cached activities (rather than refetch from server).",
        )

        parser.add_argument(
            "--only-cache",
            action="store_true",
            default=False,
            help="Whether to use only cached activities (rather than fetch anything from server).",
        )

        parser.add_argument(
            "--rewrite",
            action="store_true",
            default=False,
            help="Whether to re-write all activity details.",
        )

        return parser

    def execute(self, args):
        fetcher = ActivitySync(logger=self.logger)
        fetcher.sync_rides_detail(
            athlete_id=args.athlete_id,
            activity_id=args.activity_id,
            rewrite=args.rewrite,
            use_cache=args.use_cache,
            only_cache=args.only_cache,
            max_records=args.max_records,
        )


def main():
    SyncActivityDetails().run()


if __name__ == "__main__":
    main()
