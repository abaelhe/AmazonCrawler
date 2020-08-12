import os, sys, re, json, itertools, pytest

sys.path.insert(0, ".")
from conftest import *

# print(driver.driver.get_cookies())
cookies = []
DOUBLE_REGEX = re.compile(r'([0-9]+\.[0-9]+)|(\.[0-9]+)|([0-9]+\.)|([0-9]+)', re.I)


def elem_num_fun(elem_list, default=0.0, sep=''):
    joined_text = ''.join([x.text for x in elem_list])
    matched_nums = [''.join(v) for v in DOUBLE_REGEX.findall(joined_text)]
    joined_match = sep.join(matched_nums)
    return float(joined_match) if len(joined_match) > 0 else default


@pytest.mark.usefixtures('cmdopt')
class TestAmazon(object):
    def login(self, driver, request):
        driver.get('/')
        email = request.config.option.username
        password = request.config.option.password
        driver.css('#nav-link-yourAccount > span.nav-line-2 > span', wait=True, clickable=True, multi=False,
                   error=True).click()

        e = driver.css('#ap_email', wait=True, clickable=True, multi=False, error=True)
        driver.send_keys(e, email + Keys.ENTER)

        e = driver.css('#ap_password', wait=True, clickable=True, multi=False, error=True)
        driver.send_keys(e, password)
        driver.css('input[type=checkbox][name="rememberMe"]', wait=True, clickable=True, multi=False,
                   error=True).click()
        driver.send_keys(e, Keys.ENTER)

        captcha = '#auth-captcha-image'
        e = driver.css(captcha, wait=True, multi=False, error=False)
        if driver.element_exists(captcha):
            e = driver.element('#ap_password')
            driver.send_keys(e, password)
            driver.element('#auth-captcha-guess').click()
            import pdb;pdb.set_trace()

    def loadPurchased(self, driver, request):
        cache_file = './book_asins.csv'

        url_purchased = 'https://www.amazon.cn/hz/mycd/myx?ref_=ya_d_l_manage_kindle#/home/content/booksAll/dateDsc/'
        book_purchased_indexes_set = set([])
        with driver.tab(path=url_purchased):
            show_more_css = 'a.contentTableShowMore_myx.horizontalCenter_myx  > span.myx-button-inner'
            status_css = 'div.contentCount_myx > div:nth-child(1) > div > div > div > div > div > div.ng-binding'

            status_text = driver.css(status_css, wait=True, timeout=10, multi=False).text
            total, _, _ = [''.join(x) for x in DOUBLE_REGEX.findall(status_text)]
            total = int(total)

            if os.path.exists(cache_file) and os.path.isfile(cache_file):
                book_purchased_indexes_cache = open(cache_file, 'r').read().splitlines()
                if len(book_purchased_indexes_cache) == total:
                    return book_purchased_indexes_cache
                else:
                    book_purchased_indexes_set.update(book_purchased_indexes_cache)
                    del book_purchased_indexes_cache

            next_page = True
            scroll_bottom = lambda :driver.exec('window.scrollTo({top:document.body.scrollHeight, left:0, behavior:"smooth"});')
            click_more = lambda :driver.exec("$('a.contentTableShowMore_myx.horizontalCenter_myx  > span.myx-button-inner').click()")
            page_down = lambda : driver.send_keys(driver.element('html'), Keys.PAGE_DOWN)

            def gather_books():
                elem_books = driver.elements('div[name^="contentTabList_"]')
                names=[v.get_attribute('name').split('_',1)[1] for v in elem_books]
                for x in names:
                    if x not in book_purchased_indexes_set:
                        book_purchased_indexes_set.add(x)
                return len(book_purchased_indexes_set)

            while next_page:
                gathered = gather_books()
                #手动加载全部已购买;缓存。
                import pdb;pdb.set_trace()
                if gathered == total:
                    next_page = False
        with open(cache_file, 'wb') as cache_fd:
            cache_fd.write('\n'.join(book_purchased_indexes_set).encode())
        return book_purchased_indexes_set

    def test_amazon(self, driver, request):
        driver.driver.delete_all_cookies()
        map(driver.driver.add_cookie, cookies)
        self.login(driver, request)
        books_purchased = self.loadPurchased(driver, request)

        search_kwargs = dict(
            k="公版", # "AmazonClassics",
            i="stripbooks",
            __mk_zh_CN="亚马逊网站",
        )
        pgno = 0
        next_page = True
        while next_page:
            pgno = pgno + 1
            next_page=self.getPage(books_purchased, driver, pgno, page='%d'%pgno, ref='sr_pg_%d'%pgno, **search_kwargs)

    def getPage(self, books_purchased, driver, pgno, **query_kwargs):
        query_kwargs.update(query_kwargs)
        url_search = driver.route('/s', **query_kwargs)
        pg = driver.get(url_search)
        inspected_css_selector = 'div.s-main-slot.s-search-results > div[data-asin][data-index][data-uuid]'
        elems = driver.css(inspected_css_selector, wait=True, timeout=10, multi=True)
        elem_start_css = 'div.a-section > div.a-row > span[aria-label*="星"]'
        elem_review_css = elem_start_css + ' > span[data-action="a-popover"]'
        books = []
        for index, div in enumerate(elems):
            book_asin = div.get_attribute('data-asin')
            if book_asin in books_purchased:
                continue

            div = div.find_element_by_css_selector('div > span[cel_widget_id="MAIN-SEARCH_RESULTS"] > div > div.a-section.a-spacing-medium')
            try:
                book_star_text = div.find_element_by_css_selector(elem_start_css).get_attribute('aria-label')
                book_review_url = \
                json.loads(div.find_element_by_css_selector(elem_review_css).get_attribute('data-a-popover'))['url']
            except:
                book_star_text = None
                book_review_url = None
            elem_image_span = div.find_element_by_css_selector('span[data-component-type="s-product-image"]')
            elem_image = elem_image_span.find_element_by_css_selector('img.s-image')
            elem_authors = div.find_elements_by_css_selector('div.a-section > div.a-row > span.a-size-base[dir="auto"]')

            url_image = elem_image_span.find_element_by_css_selector('a.a-link-normal').get_attribute('href')
            url_name = div.find_element_by_css_selector('a.a-text-normal').get_attribute('href')

            book_url = url_image or url_name
            book_hashid = book_url
            book_image_link = elem_image.get_attribute('src')
            book_image_name = elem_image.get_attribute('alt')
            book_name = div.find_element_by_css_selector('a.a-text-normal').text
            book_author = ''.join([e.text for e in elem_authors if e.text])

            book_kindle_unlimited = len(div.find_elements_by_css_selector('i.a-icon-kindle-unlimited')) > 0
            if book_kindle_unlimited:
                elem_price = div.find_elements_by_css_selector(
                    'div.a-section:last-child > div.a-row > span[dir="auto"]')
                elem_unlimited = div.find_elements_by_css_selector("span.a-price > span[aria-hidden]")
                book_price = float(elem_num_fun(elem_price))
                book_price_unlimited = float(elem_num_fun(elem_unlimited))
            else:
                elem_price = div.find_elements_by_css_selector("span.a-price > span[aria-hidden]")
                book_price = book_price_unlimited = float(elem_num_fun(elem_price))

            books.append(dict(
                book_asin=book_asin,
                book_url=book_url,
                book_name=book_name,
                book_image_name=book_image_name,
                book_image_link=book_image_link,
                book_author=book_author,
                book_star_text=book_star_text,
                book_review_url=book_review_url,
                book_kindle_unlimited=book_kindle_unlimited,
                book_price=book_price,
                book_price_unlimited=book_price_unlimited,
            ))

        for book in books:
            book_url = book['book_url']
            book_name = book['book_name']
            book_price = book['book_price']
            book_price_unlimited = book['book_price_unlimited']

            msg = "book name:%s, price:%s, unlimited:%s" % (book_name, book_price, book_price_unlimited)
            if "免费" in book_name and book_price == 0.0:
                with driver.tab(path=book_url):
                    if driver.element_exists('#ebooksInstantOrderUpdate_feature_div #ebooksInstantOrderUpdate'):
                        continue
                    try:
                        self.getUrl(driver, book_url)
                        logger.info(msg)
                    except:
                        logger.error(msg)
            else:
                logger.warning("Skip %s", msg)

        next_page = not driver.element_exists('div.s-main-slot > div > span > div > div > ul > li.a-last[class~="a-disabled"]')
        return next_page

    def getUrl(self, driver, url):
        inspected_one_click_selector = '#one-click-button'
        oneClick = driver.css(inspected_one_click_selector, wait=True, multi=False)

        elem_price = driver.elements('tr.kindle-price > td.a-color-price > span.a-color-price')
        elem_kindle_unlimited = driver.elements('#a-autoid-3-announce > span.a-color-base > span.a-color-price')
        book_price = float(elem_num_fun(elem_price))
        book_price_unlimited = float(elem_num_fun(elem_kindle_unlimited))
        kindle_unlimited = driver.element_exists('#a-autoid-3-announce > span.a-color-base > i.a-icon-kindle-unlimited')

        if book_price == 0.0:
            driver.move_to(inspected_one_click_selector)
            oneClick.click()
            inspected_purchased_selector = '#a-page > div.a-container > div > div > div > p:nth-child(4)'
            elems = driver.css(inspected_purchased_selector, wait=True, clickable=True, multi=True, error=False)
            if elems is not None and any([x.text.find("购买过") > 0 for x in elems]):
                pass
        pass
