import arrow
from freezing.model import meta, orm
from pytz import utc
from sqlalchemy import and_

from freezing.sync.config import config
from freezing.sync.data.activity import ActivitySync

from . import BaseCommand


class SyncActivitiesScript(BaseCommand):
    """
    Synchronize rides from data with the database.
    """

    name = "sync-activities"
    description = "Syncs all activities for registered athletes."

    def build_parser(self):
        parser = super(SyncActivitiesScript, self).build_parser()

        parser.add_argument(
            "--start-date",
            dest="start_date",
            help="Date to begin fetching (default is to fetch all since configured start date)",
            default=config.START_DATE,
            type=lambda v: arrow.get(v).datetime,
            metavar="YYYY-MM-DD",
        )

        parser.add_argument(
            "--athlete-id",
            dest="athlete_id",
            type=int,
            nargs="+",
            help="Just sync rides for a specific athlete(s).",
            metavar="STRAVA_ID",
        )

        parser.add_argument(
            "--rewrite",
            action="store_true",
            default=False,
            help="Whether to rewrite the ride data already in database (does not incur additional API calls).",
        )

        parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Whether to force the sync (e.g. if after competition end).",
        )

        return parser

    def execute(self, args):
        fetcher = ActivitySync(logger=self.logger)
        fetcher.sync_rides(
            start_date=args.start_date,
            athlete_ids=args.athlete_id,
            rewrite=args.rewrite,
            force=args.force,
        )


def main():
    SyncActivitiesScript().run()


if __name__ == "__main__":
    main()
