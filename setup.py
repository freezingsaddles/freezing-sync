# -*- coding: utf-8 -*-

from setuptools import setup

version = "1.5.2"

long_description = """
freezing-sync is the component responsible for fetching activities, weather data, etc.
"""

install_requires = [
    "APScheduler",
    "GeoAlchemy2",
    "PyMySQL",
    "SQLAlchemy",
    "colorlog",
    "datadog",
    "envparse",
    "freezing-model",
    "greenstalk",
    "polyline",
    "pytz",
    "requests",
    "stravalib",
]

setup(
    name="freezing-sync",
    version=version,
    author="Richard Bullington-McGuire",
    author_email="rbulling@obscure.org",
    url="http://github.com/freezingsaddles/freezing-sync",
    license="Apache",
    description="Freezing Saddles activity and metadata sync.",
    long_description=long_description,
    packages=[
        "freezing.sync",
        "freezing.sync.cli",
        "freezing.sync.data",
        "freezing.sync.utils",
        "freezing.sync.wx",
        "freezing.sync.wx.darksky",
        "freezing.sync.wx.visualcrossing",
        "freezing.sync.wx.wunder",
        "freezing.sync.wx.ncdc",
    ],
    # include_package_data=True,
    # package_data={'stravalib': ['tests/resources/*']},
    install_requires=install_requires,
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
    ],
    entry_points="""
    [console_scripts]
    freezing-sync = freezing.sync.run:main
    freezing-sync-activities = freezing.sync.cli.sync_activities:main
    freezing-sync-detail = freezing.sync.cli.sync_details:main
    freezing-sync-streams = freezing.sync.cli.sync_streams:main
    freezing-sync-photos = freezing.sync.cli.sync_photos:main
    freezing-sync-weather = freezing.sync.cli.sync_weather:main
    freezing-sync-athletes = freezing.sync.cli.sync_athletes:main
    """,
    zip_safe=True,
)
