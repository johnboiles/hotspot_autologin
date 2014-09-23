Hotspot Autologin Script
========================
Script to automatically log into wifi hotspots that redirect to an agreement page before they will give you access. I use this script on my Raspberry Pi to automatically log me into the wifi at the Berkeley Marina, but it should be easy to adapt to other hotspots that use the common redirect->agree->connect pattern. Tested on Python2.7, but may work on other versions.

Features
--------
* Login to hotspots from the command line without a web browser
* Option to automatically cron itself to happen in another 24 hours
* Retries with exponential backoff

Requirements
------------
* Python 2.7
* (optional) `python-crontab` for the cron feature (`sudo easy_install python-crontab`)

Run
---
Nothing fancy here, just run it like you'd run any old script.

    python hotspot_autologin.py

OR

    ./hotspot_autologin.py
