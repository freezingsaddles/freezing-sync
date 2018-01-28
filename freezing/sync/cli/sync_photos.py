from freezing.sync.data.photos import PhotosSync

from . import BaseCommand


class SyncPhotosScript(BaseCommand):

    name = 'sync-photos'
    description = 'Sync ride photos.'

    def execute(self, args):

        fetcher = PhotosSync()
        fetcher.sync_photos()


def main():
    SyncPhotosScript().run()


if __name__ == '__main__':
    main()