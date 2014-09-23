#!/usr/bin/env python
from StringIO import StringIO
from time import sleep
import argparse
import cookielib
import datetime
import gzip
import inspect
import logging
import math
import os
import re
import sys
import urllib
import urllib2


# URL to test whether we're logged in. This needs to be a URL that doesn't result in a redirect.
TEST_URL = 'http://www.apple.com'
# Content in the TEST_URL, to make sure we ultimately loaded the real thing and not a redirect.
TEST_URL_CONTENT = r'<meta name="Author" content="Apple Inc." />'
# Regex for finding the login URL from the login page
LOGIN_URL_REGEX = r'<div id="button_content"><a href="(.*)" title="Continue to the Internet" id="continue_link">Continue to the Internet</a></div>'
# Some headers to impersonate a browser. It seems like without these, the server doesn't trust us.
HEADERS = \
(('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/33.0.1750.152 Safari/537.36'),
('Accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'),
('Accept-Encoding', 'gzip,deflate,sdch'),
('Accept-Language', 'en-US,en;q=0.8'),
('Connection', 'keep-alive'))
DEFAULT_WAIT_TIME = 15


class NoRedirectHandler(urllib2.HTTPRedirectHandler):
    def __init__(self):
        self.got_redirect = False

    def http_error_302(self, req, fp, code, msg, headers):
        infourl = urllib.addinfourl(fp, headers, req.get_full_url())
        infourl.status = code
        infourl.code = code
        logging.debug('NoRedirectHandler got redirect to + ' + headers['Location'])
        self.got_redirect = True
        return infourl

    http_error_300 = http_error_302
    http_error_301 = http_error_302
    http_error_303 = http_error_302
    http_error_307 = http_error_302


def get_login_page_url_from_redirect():
    no_redirect_handler = NoRedirectHandler()
    handlers = [
        no_redirect_handler,
    ]
    opener = urllib2.build_opener(*handlers)
    req = urllib2.Request(TEST_URL)
    response = opener.open(req)
    return response.headers.get('Location')


def uncompress_possibly_gzipped_response(response):
    if response.info().get('Content-Encoding') == 'gzip':
        buf = StringIO(response.read())
        f = gzip.GzipFile(fileobj=buf)
        response_string = f.read()
    else:
        response_string = response.read()
    return response_string


def get_cookies_and_login_url_from_login_page(login_page_url):
    cookies = cookielib.LWPCookieJar()
    handlers = [
        urllib2.HTTPSHandler(),
        urllib2.HTTPCookieProcessor(cookies),
        ]
    opener = urllib2.build_opener(*handlers)

    req = urllib2.Request(login_page_url)
    response = opener.open(req)

    response_string = uncompress_possibly_gzipped_response(response)

    login_url = re.findall(LOGIN_URL_REGEX, response_string)

    logging.debug(cookies)

    return cookies, login_url[0]


def login(login_url, cookies, referrer):
    handlers = [
        urllib2.HTTPSHandler(),
        urllib2.HTTPCookieProcessor(cookies),
        ]
    opener = urllib2.build_opener(*handlers)

    for name, value in HEADERS:
        opener.addheaders.append((name, value))

    opener.addheaders.append(('Referer', referrer))

    req = urllib2.Request(login_url)
    response = opener.open(req)

    response_string = uncompress_possibly_gzipped_response(response)
    logging.debug('Response from Login: %s' % response_string)
    logging.debug('Cookies after login: %s' % cookies)

    results = re.findall(TEST_URL_CONTENT, response_string)
    return len(results) > 0


def login_to_wifi():
    """Returns True if login was needed and completed successfully. Returns false if login was unnecessary or failed."""
    logging.info('Checking for login redirect (trying %s)' % TEST_URL)
    login_page_url = get_login_page_url_from_redirect()
    if not login_page_url:
        logging.info("Looks like we're already logged in!")
        return False

    logging.info('Loading login page (%s)' % login_page_url)
    cookies, login_url = get_cookies_and_login_url_from_login_page(login_page_url)

    logging.info('Attempting to login (%s)' % login_url)
    logged_in = login(login_url, cookies, login_page_url)

    if logged_in:
        logging.info('Successfully redirected to %s. We are now logged in.' % TEST_URL)

    # Sanity check: make sure we don't get another redirect
    login_page_url = get_login_page_url_from_redirect()
    if login_page_url:
        logging.warn('Still getting redirect when accessing %s' % TEST_URL)
        return False

    return True


def get_script_path_and_name():
    filename = inspect.getfile(inspect.currentframe()) # script filename (usually with path)
    path = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe()))) # script directory
    return path, os.path.split(filename)[1]


def cron_thyself(original_arguments=[]):
    # Get the current time
    now = datetime.datetime.now()
    path, filename = get_script_path_and_name()
    from crontab import CronTab
    logging.info('Cron scheduling %s to happen in 24 hours (minute: %d hour: %d)' % (filename, now.minute, now.hour))
    cron = CronTab(user=True)
    jobs = cron.find_command(filename)
    jobs = [job for job in jobs]
    logging.debug('Existing cron jobs are: %s' % jobs)
    # If no job already exists, create one
    if not jobs:
        command = os.path.join(path, filename) + ' ' + ' '.join(original_arguments[1:])
        logging.info("No existing job detected. Creating a new one")
        job = cron.new(command, "Automatically log into hotspot every 24 hours.")
    else:
        if len(jobs) > 1:
            logging.warn("More than 1 cron lines for %s. Using the first one." % filename)
        job = jobs[0]
    job.minute.on(now.minute)
    job.hour.on(now.hour)
    logging.info('Writing Cron job: %s' % job)
    cron.write()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Automatically logs into hotspots that have a login/agreement page.', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--log', help='Set log level to DEBUG, INFO, WARNING, or ERROR', default='INFO')
    parser.add_argument('--retries', help='Number of times to retry.', type=int, default=0)
    parser.add_argument('--noexpwait', help="Don't exponentially increase the retry time.", action='store_true')
    parser.add_argument('--retrytime', help='Time to wait between retries (in seconds). Unless --noexpwait is specified, this is only the wait time for the first retry.', type=int, default=DEFAULT_WAIT_TIME)
    parser.add_argument('--cron', help="If provided, the script will automatically attempt to re-cron itself after 24 hours.", action='store_true')
    args = parser.parse_args()
    log_level = args.log
    retries = args.retries
    total_retries = retries
    no_exp_wait = args.noexpwait
    retry_time = args.retrytime
    cron = args.cron

    numeric_log_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_log_level, int):
        raise ValueError('Invalid log level: %s' % log_level)
    logging.basicConfig(level=numeric_log_level, format='%(asctime)s %(levelname)s:%(message)s')

    while True:
        try:
            logged_in = login_to_wifi()
            if logged_in:
                if cron:
                    cron_thyself(sys.argv)
                break
        except Exception as error:
            logging.error(error)

        if retries > 0:
            if no_exp_wait:
                sleep_time = retry_time
            else:
                sleep_time = retry_time * math.pow(2, total_retries - retries)
            logging.info("Waiting %d seconds before retrying (%d retries remaining)" % (sleep_time, retries))
            retries -= 1
            sleep(sleep_time)
        else:
            break
