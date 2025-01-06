"""Test that we can load the PhotoSync class with related libraries.

This services Instagram sync, which is likely obsolete, but running
freezing-sync-photos was bombing so this test makes sure that
the libraries needed are all in place."""

from freezing.sync.data.photos import PhotoSync


def test_phtosync_instantiation():
    ps = PhotoSync()
    assert ps is not None
