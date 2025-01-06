from freezing.sync.data.photos import PhotoSync

from . import BaseCommand


class SyncPhotosScript(BaseCommand):
    """
    Sync ride photos.
    """

    name = "sync-photos"
    description = "Sync ride photos."

    def execute(self, args):
        """
        Perform actual implementation for this command.

        :param args: The parsed options/args from argparse.
        """
        fetcher = PhotoSync()
        fetcher.sync_photos()


def main():
    SyncPhotosScript().run()


if __name__ == "__main__":
    main()
