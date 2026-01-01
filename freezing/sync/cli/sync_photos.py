from freezing.sync.data.photos import PhotoSync

from . import BaseCommand


class SyncPhotosScript(BaseCommand):
    name = "sync-photos"
    description = "Sync ride photos."

    def build_parser(self):
        parser = super().build_parser()
        parser.add_argument(
            "--athlete-id",
            type=int,
            help="Just sync photos for a specific athlete.",
        )
        parser.add_argument(
            "--activity-id",
            type=int,
            help="Just sync photos for a specific activity.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Force re-sync.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            default=False,
            help="Log response.",
        )
        return parser

    def execute(self, args):
        fetcher = PhotoSync()
        fetcher.sync_photos(
            athlete_id=args.athlete_id,
            activity_id=args.activity_id,
            force=args.force,
            verbose=args.verbose,
        )


def main():
    SyncPhotosScript().run()


if __name__ == "__main__":
    main()
