from lzhbrowser import Browser
from bs4 import BeautifulSoup, NavigableString
from urllib.parse import urlparse, quote
from datetime import datetime, timedelta
from lzhminifluxapi import pg_get_exist_links_by_site_url
from dotenv import load_dotenv
import os
import re
import asyncio
from aiohttp import ClientSession, ClientTimeout
import random

load_dotenv()
logger = None
browser: Browser = None

JANDANRSS_DB_CONNECTION_STRING = os.getenv('JANDANRSS_DB_CONNECTION_STRING', None)
JANDANRSS_FETCH_FULL_PAGE: bool = os.getenv('JANDANRSS_FETCH_FULL_PAGE', 'False') == 'True'
FILE_CACHE_BASE_URL=os.getenv('FILE_CACHE_BASE_URL', None)
FILE_CACHE_TOKEN=os.getenv('FILE_CACHE_TOKEN', None)
B_MAX_PAGES=int(os.getenv('B_MAX_PAGES', 4))

fetch_full_page_semaphore = asyncio.Semaphore(B_MAX_PAGES)

def parse_time_string(s: str, now: datetime = None) -> datetime:
    if not now:
        now = datetime.now()
    s = s.strip()
    try:
        if s.endswith("分钟前"):
            minutes = int(s[:-3])
            return now - timedelta(minutes=minutes)
        elif s.startswith("今天"):
            time_part = s[2:].strip()
            return datetime.strptime(now.strftime("%Y-%m-%d") + " " + time_part, "%Y-%m-%d %H:%M")
        elif s.startswith("昨天"):
            time_part = s[2:].strip()
            date = now - timedelta(days=1)
            return datetime.strptime(date.strftime("%Y-%m-%d") + " " + time_part, "%Y-%m-%d %H:%M")
        else:
            # 处理格式如 "06/02/ 22:13"
            date_part, time_part = s.split()
            date_part = date_part.strip('/')  # 去掉末尾的 '/'
            month, day = map(int, date_part.split('/'))
            hour, minute = map(int, time_part.split(':'))
            return datetime(now.year, month, day, hour, minute)
    except Exception:
        return datetime(1970, 1, 1)

def html_to_info(html, url):

    info = {}

    parsed = urlparse(url)
    root_url = f"{parsed.scheme}://{parsed.netloc}"
    info['root_url'] = root_url

    info['link'] = url
    # info['title']
    # info['description']
    # info['lastBuildDate']
    info['image']={}
    # info['image']['ul']
    # info['image']['title']
    # info['image']['link']
    info['item']={}
    # info['item']['']={}
    # info['item']['']['title']
    # info['item']['']['link']
    # info['item']['']['description']
    # info['item']['']['pubDate']
    # info['item']['']['guid']

    soup = BeautifulSoup(html, 'html.parser')

    tag = soup.select_one('head > title')
    text = tag.text.strip() if tag else '未知标题'
    tag = soup.find('div',class_="nav-item current")
    text = text + ' | ' + tag.text.strip() if tag else text
    info['title'] = text
    info['description'] = text

    info['image']['url'] = 'https://jandan.net/wp-content/themes/jandan2025/images/logo2025-d.png'
    info['image']['title'] = info['title']
    info['image']['link'] = info['link']

    return info

async def blocks_to_info(blocks, info):

    # if not blocks:
    #     info['lastBuildDate'] = datetime.now().timestamp()

    date_obj_set = set()
    for block in blocks:
        html = await block.inner_html()
        item = BeautifulSoup(html, 'html.parser')
        tag = item.find('a', class_='comment-num')
        tag1 = item.find('span', class_='create-time')
        tag2 = item.find('span', class_='comment-count')
        tag3 = item.find('div', class_='comment-func')
        tag4 = item.find('div', class_='comment-content')
        oo_tag = item.find("span", class_="oo_number")
        xx_tag = item.find("span", class_="xx_number")

        if not tag or not tag1 or not tag2 or not tag2.text.strip().isdigit() or not tag3 or not tag4 or not oo_tag or not xx_tag:
            logger.debug('continue 1')
            continue

        oo = int(oo_tag.text.strip())
        xx = int(xx_tag.text.strip())
        href = tag.get('href', None)

        if not href or xx > oo:
            logger.debug('continue 2')
            continue

        id = tag.text.strip()
        date = tag1.text.strip().strip('@')
        title = re.sub(r'\s+', ' ', tag3.text)
        comment_count = int(tag2.text.strip())

        try:
            date_obj = parse_time_string(date)
        except:
            logger.debug('continue 3')
            continue

        html_block = BeautifulSoup(f'<div></div>', 'html.parser')
        tags = tag4.find_all('div', class_='img-container')
        for tag in tags:
            a = tag.find('a')
            src = a['href'] if a else None
            src = src.replace('.mp4', '.gif') if src else ''
            img = BeautifulSoup(f'<img src="{src}">', 'html.parser')
            html_block.div.append(img)
            tag.decompose()

        title = title + ' ' + tag4.text.strip()

        date_obj_set.add(date_obj)

        info['item'][id]={}
        info['item'][id]['title'] = title
        info['item'][id]['link'] = info['root_url'] + href
        # info['item'][id]['description'] = ''
        info['item'][id]['pubDate'] = date_obj.timestamp()
        info['item'][id]['guid'] = id
        info['item'][id]['comment_count'] = comment_count
        info['item'][id]['description_html'] = str(html_block)
        info['item'][id]['block'] = block

    # if not info.get('item'):
    #     info['lastBuildDate'] = datetime.now().timestamp()
    #     return
        # raise RuntimeError("主tag中没有item")
    latest_date = max(date_obj_set) if date_obj_set else datetime.now()
    info['lastBuildDate'] = latest_date.timestamp()

async def delete_existing_item(info, url):
    if not info.get('item', {}) or not JANDANRSS_DB_CONNECTION_STRING:
        return
    id_links = [(id, val.get('link', '')) for id, val in info['item'].items()]
    links = [link for _, link in id_links]
    try:
        links_existing = await pg_get_exist_links_by_site_url(site_url=url, links=links, connection_string=JANDANRSS_DB_CONNECTION_STRING)
    except Exception as e:
        raise RuntimeError(f"数据库错误 : {e}")
    ids = [id for id, link in id_links if link in links_existing]
    for id in ids:
        info['item'].pop(id, None)

async def update_item(val):
    async with fetch_full_page_semaphore:
        html_block = BeautifulSoup(val['description_html'], 'html.parser')

        if FILE_CACHE_BASE_URL:
            for sub in html_block.find_all(src=True):
                url = quote(sub['src'], safe='')
                src = f'{FILE_CACHE_BASE_URL}{url}'
                sub['src'] = src
                src = f'{src}&token={FILE_CACHE_TOKEN}'
                timeout = ClientTimeout(total=10)
                async with ClientSession(timeout=timeout) as session:
                    async with session.get(src) as resp:
                        resp.raise_for_status()
        val['description_html'] = str(html_block)

        if val['comment_count'] < 1:
            return

        try :
            block = val['block']
            button = await block.query_selector('div.comment-func > span:nth-child(3)')
            await button.click()
            tucao = await block.wait_for_selector('div.tucao-container')
            await asyncio.sleep(0.5)
            tucao_hot = await tucao.query_selector('div.tucao-hot')
            html = await tucao_hot.inner_html() if tucao_hot else None
            if not html:
                return

            soup = BeautifulSoup(html, 'html.parser')
            comment_rows = soup.find_all('div', class_='comment-row')
            filtered_rows = []
            for row in comment_rows:
                div = row.find('div', class_='comment-content')
                parts = []
                for child in div.children:
                    if isinstance(child, NavigableString):
                        parts.append(child.strip())
                    else:
                        parts.append(child.get_text(strip=True))
                content = ' '.join(filter(None, parts))
                oo = int(row.find("span", class_="oo_number").text.strip())
                xx = int(row.find("span", class_="xx_number").text.strip())
                filtered_rows.append((oo, xx, content))

            table = BeautifulSoup(f'<table></table>', 'html.parser')
            link = val['link']
            for oo, xx, content in filtered_rows:
                if len(content) >= 3:
                    href = f'{link}#:~:text={quote(content[:1],safe='')}-,{quote(content[1:-1],safe='')},-{quote(content[-1:],safe='')}'
                else:
                    href = f'{link}'
                tr = BeautifulSoup(f'<tr><td>{content}</td><td><a href="{href}">{oo}</a></td><td>{xx}</td></tr>', 'html.parser')
                table.table.append(tr)

            html_block.div.append(table)

        except Exception as e:
            error = BeautifulSoup(f'<div>{e}</div>', 'html.parser')
            html_block.div.append(error)

        finally:
            val['description_html'] = str(html_block)

async def close_page_later(page, delay=2):
    try:
        await asyncio.sleep(delay)
        await page.close()
    except Exception as e:
        logger.error(f"Error closing page: {e}")

async def parse(request):
    global logger
    global browser
    browser = request.app["browser"]
    logger = request.app["logger"]

    url = request.query.get('url')

    page = await browser.context_direct.new_page()

    await page.goto(url=url)

    html = await page.content()

    info = html_to_info(html, url)

    try:
        await page.wait_for_selector('div.comment-row')
        await page.wait_for_timeout(500)
    except Exception as e:
        logger.error(e)
        asyncio.create_task(close_page_later(page, delay= 1 + 6 * random.random()))
        return info

    blocks = await page.query_selector_all('div.comment-row')
    logger.debug(len(blocks))

    await blocks_to_info(blocks, info)

    if JANDANRSS_FETCH_FULL_PAGE:
        await delete_existing_item(info, url)
        await asyncio.gather(*[update_item(val) for val in info.get('item', {}).values()])

    for val in info.get('item', {}).values():
        val.pop('block', None)

    asyncio.create_task(close_page_later(page, delay= 1 + 6 * random.random()))

    return info
