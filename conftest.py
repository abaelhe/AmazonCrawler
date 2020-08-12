from __future__ import absolute_import

# TODO(dcramer): this heavily inspired by pytest-selenium, and it's possible
# we could simply inherit from the plugin at this point

import logging, os, re, sys, functools, pytest, percy
from contextlib import contextmanager
from datetime import datetime
from six.moves.urllib.parse import quote, urlparse, urlencode, urljoin, urlsplit, quote_plus, unquote_plus

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

logger = logging.getLogger('browser')


# if we're not running in a PR, we kill the PERCY_TOKEN because its a push to a branch,
# and we don't want percy comparing things, we do need to ensure its run on master so that changes get updated
if os.environ.get('TRAVIS_PULL_REQUEST', 'false') == 'false' and os.environ.get('TRAVIS_BRANCH', 'master') != 'master':
    os.environ.setdefault('PERCY_ENABLE', '0')


#"pytest_addoption" MUST in file with name: "conftest.py"
def pytest_addoption(parser):
    parser.addini('selenium_driver', help='selenium driver (chrome, phantomjs, or firefox)')

    group = parser.getgroup('selenium', 'selenium')
    group.addoption(
        '--selenium-driver', dest='selenium_driver', type=str, default='chrome', help='selenium driver (chrome, phantomjs, or firefox)'
    )
    group.addoption(
        '--window-size',
        dest='window_size',
        help='window size (WIDTHxHEIGHT)',
        default='1280x800')
    group.addoption('--phantomjs-path', dest='phantomjs_path', type=str, default=None, help='path to phantomjs driver')
    group.addoption('--chrome-path', dest='chrome_path', type=str, default=None, help='path to google-chrome')
    group.addoption('--chromedriver-path', dest='chromedriver_path', type=str, default=None, help='path to chromedriver')

    group = parser.getgroup('amazon', 'amazon')
    group.addoption("--username", type=str, default=None, help="Amazon Login username")
    group.addoption("--password", type=str, default=None, help="Amazon Login password")
    group.addoption("--timeout", type=float, default=3.0, help="timeout wait until an elements available")


@pytest.fixture(scope='session', autouse=True)
def _environment(request):
    config = request.config
    # add environment details to the pytest-html plugin
    if not hasattr(config, '_environment'):
        config._environment = []
    config._environment.append(('Driver', config.option.selenium_driver))


#Usage:
# @pytest.mark.usefixtures('cmdopt')
@pytest.fixture
def cmdopt(request):
    config = request.config
    config.option.selenium_driver = config.getoption('selenium_driver') or config.getini('selenium_driver') or \
                                    os.getenv('SELENIUM_DRIVER')
    config.option.phantomjs_path = config.getoption("--phantomjs-path")
    config.option.chrome_path = config.getoption("--chrome-path")
    config.option.chromedriver_path = config.getoption("--chromedriver-path")

    config.option.window_size = config.getoption("--window-size")
    config.option.username = config.getoption("--username")
    config.option.password = config.getoption("--password")
    config.option.timeout = config.getoption("--timeout")


class Settings(object):
    def normDir(self, dir):
        dir = os.path.abspath(os.path.expandvars(os.path.expanduser(dir)))
        return dir

    def internalDir(self, dir, rootdir=None, create=True):
        dir = self.normDir(dir)
        dir = os.path.join(rootdir or self.rootdir, dir)
        if not os.path.exists(dir) and create:
            os.makedirs(dir)
        return dir

    def __init__(self, live_server_url):
        rootdir = globals().get("__file__", ".")
        self.rootdir = os.path.abspath(os.path.expandvars(os.path.expanduser(rootdir)))
        self.STATIC_ROOT = self.internalDir("STATIC")
        self.STATIC_URL = "/static"
        self.PERCY_DEFAULT_TESTING_WIDTHS = None
        self.live_server_url = live_server_url


settings = Settings("https://www.amazon.cn")


class Browser(object):
    def __init__(self, driver, percy, live_server_url, timeout=3):
        self.driver = driver
        self.live_server_url = live_server_url
        self.domain = urlparse(self.live_server_url).hostname
        self._has_initialized_cookie_store = False
        self.percy = percy
        self.timeout = timeout
        self.tabs = []

    def exec(self, js, error=True):
        try:
            self.driver.execute_script(js)
        except:
            exc = sys.exc_info()
            if error is not True:
                return exc
            raise

    def send_keys(self, element, keys):
        element.click()
        element.send_keys(keys)

    def css(self, inspected_css_selector, wait=False, clickable=False, timeout=0, multi=True, error=True, flags=re.M):
        timeout = self.timeout if timeout in (0, None) else timeout

        if multi:
            general_css_selector, _ = re.subn(r":nth-child\([0-9]+\)", "", inspected_css_selector, count=0, flags=flags)
        else:
            general_css_selector = inspected_css_selector

        if wait:
            try:
                self.wait_until(selector=general_css_selector, clickable=clickable, timeout=timeout)
            except TimeoutException as e:
                if error:
                    raise
                return
            return self.elements(general_css_selector) if multi is True else self.element(general_css_selector)

        return general_css_selector

    def tab_new(self, title=None, path=None, *args, **kwargs):
        if self.driver.current_window_handle not in self.tabs:
            self.tabs.append(self.driver.current_window_handle)

        url = self.route(path, *args, **kwargs)
        self.exec("window.open('" + url + "', '" + (title or "") + "');window.scrollTo(0,0)")
        if self.driver.current_window_handle != self.driver.window_handles[-1]:
            self.driver.switch_to.window(self.driver.window_handles[-1])
        else:
            self.driver.switch_to.window(self.driver.current_window_handle)

        if self.driver.current_window_handle not in self.tabs:
            self.tabs.append(self.driver.current_window_handle)

    def tab_push(self, hash=None):
        hash = hash or self.driver.current_window_handle
        self.tabs.append(hash)
        self.driver.switch_to.window(self.tabs[-1])

    def tab_pop(self, hash=None, close=True):
        hash = hash or self.driver.current_window_handle
        assert hash in self.tabs, "pop a non-exist browser tab: %s" % (hash,)
        self.tabs.remove(hash)
        if close:
            self.tab_close(hash=hash)
        self.driver.switch_to.window(self.tabs[-1] if len(self.tabs) > 0 else self.driver.window_handles[0])

    def tab_close(self, hash=None):
        hash = hash or self.driver.current_window_handle
        if hash in self.tabs:
            self.tabs.remove(hash)
        self.exec("window.close()")
        self.driver.switch_to.window(self.tabs[-1] if len(self.tabs) > 0 else self.driver.window_handles[0])

    @contextmanager
    def tab(self, path=None, title=None):
        try:
            self.tab_new(title=title, path=path)
            yield self
        except:
            exc_type, exc_val, exc_tb = sys.exc_info()
            import traceback
            traceback.print_exception(exc_type, exc_val, exc_tb)
            sys.exit(-1)
        finally:
            try:
                self.tab_pop()
            except:
                pass

    def __getattr__(self, attr):
        return getattr(self.driver, attr)

    def url_quote(self, url):
        return quote_plus(unquote_plus(url))

    def route(self, path, *args, **kwargs):
        """
        Return the absolute URI for a given route in Sentry.
        """
        if path.startswith('http://') or path.startswith('https://'):
            url = path % args if len(args)>0 else path
        elif path.startswith('//'):
            url = urljoin(self.live_server_url, path % args if len(args)>0 else path)
        else:
            url = u'{}/{}'.format(self.live_server_url, path.lstrip('/') % args if len(args)>0 else path)

        url = url.rstrip('?')
        args_index = url.find('?')
        params = '&'.join(["%s=%s"%(k,v) for k,v in kwargs.items()])
        url = (url + '?' + params) if args_index < 0 else url.replace('?', '?' + params + '&')
        return url

    def get(self, path, *args, **kwargs):
        self.driver.get(self.route(path), *args, **kwargs)
        self._has_initialized_cookie_store = True
        return self

    def post(self, path, *args, **kwargs):
        self.driver.post(self.route(path), *args, **kwargs)
        self._has_initialized_cookie_store = True
        return self

    def put(self, path, *args, **kwargs):
        self.driver.put(self.route(path), *args, **kwargs)
        self._has_initialized_cookie_store = True
        return self

    def delete(self, path, *args, **kwargs):
        self.driver.delete(self.route(path), *args, **kwargs)
        self._has_initialized_cookie_store = True
        return self

    def element(self, selector):
        return self.driver.find_element_by_css_selector(selector)

    def elements(self, selector):
        return self.driver.find_elements_by_css_selector(selector)

    def element_exists(self, selector):
        try:
            self.element(selector)
        except NoSuchElementException:
            return False
        return True

    def click(self, selector):
        self.element(selector).click()

    def click_when_visible(self, selector=None, timeout=0):
        """
        Waits until ``selector`` is available to be clicked before attempting to click
        """
        timeout = self.timeout if timeout in (0, None) else timeout

        if selector:
            self.wait_until_clickable(selector, timeout)
            self.click(selector)
        else:
            raise ValueError

        return self

    def move_to(self, selector=None):
        """
        Mouse move to ``selector``
        """
        if selector:
            actions = ActionChains(self.driver)
            actions.move_to_element(self.element(selector)).perform()
        else:
            raise ValueError

        return self

    def wait_until_clickable(self, selector=None, timeout=0):
        """
        Waits until ``selector`` is visible and enabled to be clicked, or until ``timeout``
        is hit, whichever happens first.
        """
        timeout = self.timeout if timeout in (0, None) else timeout

        from selenium.webdriver.common.by import By

        if selector:
            condition = expected_conditions.element_to_be_clickable((By.CSS_SELECTOR, selector))
        else:
            raise ValueError

        WebDriverWait(self.driver, timeout).until(condition)

        return self

    def wait_until(self, selector=None, title=None, clickable=False, timeout=0):
        """
        Waits until ``selector`` is found in the browser, or until ``timeout``
        is hit, whichever happens first.
        """
        timeout = self.timeout if timeout in (0, None) else timeout

        from selenium.webdriver.common.by import By

        if selector:
            condition = expected_conditions.presence_of_element_located((By.CSS_SELECTOR, selector))
        elif title:
            condition = expected_conditions.title_is(title)
        elif clickable:
            condition = expected_conditions.element_to_be_clickable((By.CSS_SELECTOR, selector))
        else:
            raise ValueError

        WebDriverWait(self.driver, timeout).until(condition)

        return self

    def wait_until_not(self, selector=None, title=None, clickable=False, timeout=0):
        """
        Waits until ``selector`` is NOT found in the browser, or until
        ``timeout`` is hit, whichever happens first.
        """
        timeout = self.timeout if timeout in (0, None) else timeout

        from selenium.webdriver.common.by import By

        if selector:
            condition = expected_conditions.presence_of_element_located((By.CSS_SELECTOR, selector))
        elif title:
            condition = expected_conditions.title_is(title)
        elif clickable:
            condition = expected_conditions.element_to_be_clickable((By.CSS_SELECTOR, selector))
        else:
            raise

        WebDriverWait(self.driver, timeout).until_not(condition)

        return self

    @property
    def switch_to(self):
        return self.driver.switch_to

    def implicitly_wait(self, duration):
        """
        An implicit wait tells WebDriver to poll the DOM for a certain amount of
        time when trying to find any element (or elements) not immediately
        available. The default setting is 0. Once set, the implicit wait is set
        for the life of the WebDriver object.
        """
        self.driver.implicitly_wait(duration)

    def snapshot(self, name):
        """
        Capture a screenshot of the current state of the page.
        """
        self.percy.snapshot(name=name)
        return self

    def cookies_get(self):
        return self.driver.get_cookies()

    def cookies_set(self, cookies):
        map(self.driver.add_cookie, cookies)

    def cookie_save(self, name, value, domain=None, path='/',
                    expires='Tue, 20 Jun 2025 19:07:44 GMT', max_age=None, secure=None):
        cookie = {
            'name': name,
            'value': value,
            'expires': expires,
            'path': path,
            'domain': domain or self.domain,
            'max-age': max_age,
            'secure': secure,
        }

        # XXX(dcramer): the cookie store must be initialized via a URL
        if not self._has_initialized_cookie_store:
            logger.info('selenium.initialize-cookies')
            self.get('/')

        # XXX(dcramer): PhantomJS does not let us add cookies with the native
        # selenium API because....
        # http://stackoverflow.com/questions/37103621/adding-cookies-working-with-firefox-webdriver-but-not-in-phantomjs

        # TODO(dcramer): this should be escaped, but idgaf
        logger.info(u'selenium.set-cookie.{}'.format(name), extra={
            'value': value,
        })
        if isinstance(self.driver, webdriver.PhantomJS):
            self.driver.execute_script(
                u"document.cookie='{name}={value}; path={path}; domain={domain}; expires={expires}'; max-age={max_age}\n".format(
                    **cookie)
            )
        else:
            self.driver.add_cookie(cookie)


@pytest.fixture(scope='session')
def percy(request):
    import percy

    # Initialize Percy.
    loader = percy.ResourceLoader(
        root_dir=settings.STATIC_ROOT,
        base_url=quote(settings.STATIC_URL),
    )
    percy_config = percy.Config(default_widths=settings.PERCY_DEFAULT_TESTING_WIDTHS)
    percy = percy.Runner(loader=loader, config=percy_config)
    percy.initialize_build()

    request.addfinalizer(percy.finalize_build)
    return percy


@pytest.fixture(scope='function')
def driver(request, percy):
    window_size = request.config.option.window_size
    window_width, window_height = list(map(int, window_size.split('x', 1)))

    driver_type = request.config.option.selenium_driver
    if driver_type == 'chrome':
        options = webdriver.ChromeOptions()
        # options.add_argument('headless')
        options.add_argument('disable-gpu')
        options.add_argument(u'window-size={}'.format(window_size))
        chrome_path = request.config.option.chrome_path
        if chrome_path:
            options.binary_location = chrome_path
        chromedriver_path = request.config.option.chromedriver_path
        if chromedriver_path:
            driver = webdriver.Chrome(
                executable_path=chromedriver_path,
                options=options,
            )
        else:
            driver = webdriver.Chrome(
                options=options,
            )
    elif driver_type == 'firefox':
        driver = webdriver.Firefox()
    elif driver_type == 'phantomjs':
        phantomjs_path = request.config.option.phantomjs_path
        if not phantomjs_path:
            phantomjs_path = os.path.join(
                'node_modules',
                'phantomjs-prebuilt',
                'bin',
                'phantomjs',
            )
        driver = webdriver.PhantomJS(executable_path=phantomjs_path)
    else:
        raise pytest.UsageError('--driver must be specified')

    driver.set_window_size(window_width, window_height)

    def fin():
        # Teardown Selenium.
        try:
            driver.quit()
        except Exception:
            pass

    request.node._driver = driver
    request.addfinalizer(fin)

    driver = Browser(driver, percy, settings.live_server_url, timeout=request.config.option.timeout)

    if getattr(request, 'cls', None):
        request.cls.driver = driver
    request.node.driver = driver

    # bind webdriver to percy for snapshots
    percy.loader.webdriver = driver

    return driver


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    summary = []
    extra = getattr(report, 'extra', [])
    driver = getattr(item, '_driver', None)
    if driver is not None:
        _gather_url(item, report, driver, summary, extra)
        _gather_screenshot(item, report, driver, summary, extra)
        _gather_html(item, report, driver, summary, extra)
        _gather_logs(item, report, driver, summary, extra)
    if summary:
        report.sections.append(('selenium', '\n'.join(summary)))
    report.extra = extra


def _gather_url(item, report, driver, summary, extra):
    try:
        url = driver.current_url
    except Exception as e:
        summary.append(u'WARNING: Failed to gather URL: {0}'.format(e))
        return
    pytest_html = item.config.pluginmanager.getplugin('html')
    if pytest_html is not None:
        # add url to the html report
        extra.append(pytest_html.extras.url(url))
    summary.append(u'URL: {0}'.format(url))


def _gather_screenshot(item, report, driver, summary, extra):
    try:
        screenshot = driver.get_screenshot_as_base64()
    except Exception as e:
        summary.append(u'WARNING: Failed to gather screenshot: {0}'.format(e))
        return
    pytest_html = item.config.pluginmanager.getplugin('html')
    if pytest_html is not None:
        # add screenshot to the html report
        extra.append(pytest_html.extras.image(screenshot, 'Screenshot'))


def _gather_html(item, report, driver, summary, extra):
    try:
        html = driver.page_source.encode('utf-8')
    except Exception as e:
        summary.append(u'WARNING: Failed to gather HTML: {0}'.format(e))
        return
    pytest_html = item.config.pluginmanager.getplugin('html')
    if pytest_html is not None:
        # add page source to the html report
        extra.append(pytest_html.extras.text(html, 'HTML'))


def _gather_logs(item, report, driver, summary, extra):
    try:
        types = driver.log_types
    except Exception as e:
        # note that some drivers may not implement log types
        summary.append(u'WARNING: Failed to gather log types: {0}'.format(e))
        return
    for name in types:
        try:
            log = driver.get_log(name)
        except Exception as e:
            summary.append(u'WARNING: Failed to gather {0} log: {1}'.format(name, e))
            return
        pytest_html = item.config.pluginmanager.getplugin('html')
        if pytest_html is not None:
            extra.append(pytest_html.extras.text(format_log(log), '%s Log' % name.title()))


def format_log(log):
    timestamp_format = '%Y-%m-%d %H:%M:%S.%f'
    entries = [
        u'{0} {1[level]} - {1[message]}'.format(
            datetime.utcfromtimestamp(
                entry['timestamp'] / 1000.0).strftime(timestamp_format), entry
        ).rstrip() for entry in log
    ]
    log = '\n'.join(entries)
    log = log.encode('utf-8')
    return log
