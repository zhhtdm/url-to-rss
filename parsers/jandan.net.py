from lzhbrowser import Browser
from bs4 import BeautifulSoup, NavigableString
from urllib.parse import urlparse, quote
from datetime import datetime, timedelta
from lzhfreshrssapi import pg_get_guids_by_site_url
from dotenv import load_dotenv
import os
import re
import asyncio

load_dotenv()
logger = None

JANDANRSS_DB_HOST = os.getenv('JANDANRSS_DB_HOST', None)
JANDANRSS_DB_PORT = os.getenv('JANDANRSS_DB_PORT', 5432)
JANDANRSS_DB_USER = os.getenv('JANDANRSS_DB_USER', None)
JANDANRSS_DB_PW = os.getenv('JANDANRSS_DB_PW', None)
JANDANRSS_DB_BASE = os.getenv('JANDANRSS_DB_BASE', None)
JANDANRSS_DB_PREFIX = os.getenv('JANDANRSS_DB_PREFIX', None)
JANDANRSS_FETCH_FULL_PAGE = bool(os.getenv('JANDANRSS_FETCH_FULL_PAGE', True))
RETRIES = int(os.getenv("RETRIES", 2))
JANDANRSS_ITEM_MAX_HEIGHT = os.getenv('JANDANRSS_ITEM_MAX_HEIGHT', '800px')
JANDANRSS_TUCAO_MAX_HEIGHT = os.getenv('JANDANRSS_TUCAO_MAX_HEIGHT', '150px')
JANDANRSS_TUOCAO_MIN_OO = int(os.getenv("JANDANRSS_TUOCAO_MIN_OO", 5))

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

    tags = soup.find_all('div', class_="comment-row p-2")
    if not tags:
        # info['lastBuildDate'] = datetime.now().timestamp()
        # return info
        raise RuntimeError("html中没有主tag")

    date_obj_set = set()
    for item in tags:
        tag = item.find('a', class_='comment-num')
        tag1 = item.find('span', class_='create-time')
        tag2 = item.find('span', class_='comment-count')
        tag3 = item.find('div', class_='comment-func')
        oo = int(item.find("span", class_="oo_number").text.strip())
        xx = int(item.find("span", class_="xx_number").text.strip())

        if not tag or not tag.has_attr('href') or not tag1 or not tag2 or not tag2.text.strip().isdigit() or not tag3 or xx >= oo:
            continue

        id = tag.text.strip()
        href = tag['href']
        date = tag1.text.strip().strip('@')
        comment_count = int(tag2.text.strip())
        title = tag3.text.replace('\n', ' ').strip()

        if not id or not href or not date or not comment_count:
            continue
        try:
            date_obj = parse_time_string(date)
        except:
            continue

        date_obj_set.add(date_obj)

        info['item'][id]={}
        info['item'][id]['title'] = title
        info['item'][id]['link'] = root_url + href
        # info['item'][id]['description'] = ''
        info['item'][id]['pubDate'] = date_obj.timestamp()
        info['item'][id]['guid'] = id
        info['item'][id]['comment_count'] = comment_count

        html_block = BeautifulSoup('<div> </div>', 'html.parser')
        html_block.div.append(item)
        info['item'][id]['description_html'] = str(html_block)

    if not info.get('item'):
        # info['lastBuildDate'] = datetime.now().timestamp()
        # return info
        raise RuntimeError("主tag中没有item")
    latest_date = max(date_obj_set) if date_obj_set else datetime.now()
    info['lastBuildDate'] = latest_date.timestamp()

    return info

async def delete_existing_item(info, url):
    if not info.get('item', {}):
        return
    if JANDANRSS_DB_HOST and JANDANRSS_DB_PORT and JANDANRSS_DB_USER and JANDANRSS_DB_PW and JANDANRSS_DB_BASE and JANDANRSS_DB_PREFIX:
        try:
            db_config = {
                'host': JANDANRSS_DB_HOST,
                'port': JANDANRSS_DB_PORT,
                'user': JANDANRSS_DB_USER,
                'password': JANDANRSS_DB_PW,
                'base': JANDANRSS_DB_BASE,
                'prefix': JANDANRSS_DB_PREFIX,
            }
            ids_existing:set = await pg_get_guids_by_site_url(site_url=url, db_config=db_config)
        except Exception as e:
            raise RuntimeError(f"数据库错误 : {e}")

        ids = set(info['item'].keys())
        ids.intersection_update(ids_existing)
        for id in ids:
            info['item'].pop(id, None)

def html_to_description(html, comment_count:int, link):
    soup = BeautifulSoup(html, 'html.parser')
    tag = soup.find('div', class_='comment-row')
    if comment_count > 0 and not tag:
        raise RuntimeError('No comment')

    tag = soup.find('div', class_='post-content')
    tag['style'] = 'display:flex;flex-direction:column;justify-content:center;align-items:center;'
    title = ''
    for elem in list(tag.contents):
        if isinstance(elem, NavigableString):
            title = title + ' ' + elem.extract().strip()
    title = title.replace('\n', ' ').strip()

    html_block = BeautifulSoup(f'<div style="max-height:{JANDANRSS_ITEM_MAX_HEIGHT};overflow-y:auto;"></div>', 'html.parser')
    html_block.div.append(tag)

    tag = soup.find('div', class_='tucao-container')
    for sub in tag.find_all('div', class_='tucao-hot'):
        sub.decompose()
    comment_rows = tag.find_all('div', class_='comment-row')
    filtered_rows = []
    for row in comment_rows:
        oo = int(row.find("span", class_="oo_number").text.strip())
        xx = int(row.find("span", class_="xx_number").text.strip())
        if oo >= JANDANRSS_TUOCAO_MIN_OO and oo > xx:
            filtered_rows.append((oo, xx, row))

    if not filtered_rows:
        return html_block, title
    filtered_rows.sort(key=lambda x: x[0], reverse=True)
    table = BeautifulSoup(f'<div style="max-height:{JANDANRSS_TUCAO_MAX_HEIGHT};overflow-y:auto;border:1px solid #888;display:flex;flex-direction:column;justify-content:center;align-items:center;"><table></table></div>', 'html.parser')
    for oo, xx, row in filtered_rows:
        floor = row.find('span', class_='floor').text.strip().strip('#').strip('楼')
        content = row.find('div', class_='comment-content').text.strip()
        if len(content) >= 3:
            href = f'{link}#:~:text={quote(content[:1],safe='')}-,{quote(content[1:-1],safe='')},-{quote(content[-1:],safe='')}'
        else:
            href = f'{link}#:~:text=%23-,{floor},-%E6%A5%BC'

        tr = BeautifulSoup(f'<tr><td>{content}</td><td><a href="{href}">{oo}</a></td><td>{xx}</td></tr>', 'html.parser')
        table.div.table.append(tr)

    html_block.div.append(table)

    return html_block, title

def html_to_date(html):
    soup = BeautifulSoup(html, 'html.parser')
    date = None
    text = soup.select_one('.post-meta').text
    match = re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}', text)
    if match:
        time_str = match.group()
        dt = datetime.strptime(time_str, '%Y-%m-%d %H:%M')
        date_obj = dt + timedelta(hours=9) if dt else None
        date = date_obj.timestamp() if date_obj else None
    return date

async def update_item(items, id, browser):
    error = ''
    link = items[id]['link']
    comment_count = items[id]['comment_count']
    for attempt in range(1, RETRIES + 2):
        try :
            html = await browser.fetch(link)
            if not html:
                raise RuntimeError("No html")
            html_block, title = html_to_description(html, comment_count, link)
            date = html_to_date(html)
            items[id]['description_html'] = str(html_block)
            if date:
                items[id]['pubDate'] = date
            if title:
                items[id]['title'] = items[id]['title'] + ' ' + title
            break
        except Exception as e:
            error = error + f"Error on attempt {attempt} for {link} : {e} \n"
            if attempt > RETRIES:
                logger.error(f"Error : \n{error}")
                items[id]['description_html'] = error
                return
            await asyncio.sleep(1)

async def parse(url:str, browser:Browser, _logger):
    global logger
    logger = _logger
    html = await browser.fetch(url)
    if not html:
        raise RuntimeError("url没有下载到html")
    info = html_to_info(html, url)
    await delete_existing_item(info, url)
    items = info.get('item', {})
    if not JANDANRSS_FETCH_FULL_PAGE or not items:
        return info
    await asyncio.gather(*[update_item(items, id, browser) for id in items.keys()])

    return info
