from lzhbrowser import Browser
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from datetime import datetime, timedelta
from lzhfreshrssapi import pg_get_guids_by_site_url
from dotenv import load_dotenv
import os

load_dotenv()
logger = None

JANDANRSS_DB_HOST = os.getenv('JANDANRSS_DB_HOST', None)
JANDANRSS_DB_PORT = os.getenv('JANDANRSS_DB_PORT', 5432)
JANDANRSS_DB_USER = os.getenv('JANDANRSS_DB_USER', None)
JANDANRSS_DB_PW = os.getenv('JANDANRSS_DB_PW', None)
JANDANRSS_DB_BASE = os.getenv('JANDANRSS_DB_BASE', None)
JANDANRSS_DB_PREFIX = os.getenv('JANDANRSS_DB_PREFIX', None)

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

    info['image']['ul'] = 'https://jandan.net/wp-content/themes/jandan2025/images/logo2025-d.png'
    info['image']['title'] = info['title']
    info['image']['link'] = info['link']

    tags = soup.find_all('div',class_="comment-row p-2")
    if not tags:
        raise RuntimeError("html中没有主tag")

    date_obj_set = set()
    for item in tags:
        tag = item.find('a', class_='comment-num')
        tag1 = item.find('span', class_='create-time')
        if not tag or not tag.has_attr('href') or not tag1:
            continue

        id = tag.text.strip()
        href = tag['href']
        date = tag1.text.strip().strip('@')

        if not id or not href or not date:
            continue
        try:
            date_obj = parse_time_string(date)
        except:
            continue
        date_obj_set.add(date_obj)

        info['item'][id]={}
        info['item'][id]['title'] = id
        info['item'][id]['link'] = root_url + href
        # info['item'][id]['description'] = ''
        info['item'][id]['pubDate'] = date_obj.timestamp()
        info['item'][id]['guid'] = id

        html_block = BeautifulSoup('<div> </div>', 'html.parser')
        html_block.div.append(item)
        info['item'][id]['description_html'] = str(html_block)

    if not info.get('item'):
        raise RuntimeError("主tag中没有item")
    latest_date = max(date_obj_set) if date_obj_set else datetime.now()
    info['lastBuildDate'] = latest_date.timestamp()

    return info

async def delete_existing_item(info, url):
    if not info or not info.get('item', {}):
        return info
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
    return info

async def parse(url:str, browser:Browser, _logger):
    global logger
    logger = _logger
    html = await browser.fetch(url)
    if not html:
        raise RuntimeError("url没有下载到html")
    info = html_to_info(html, url)
    info = await delete_existing_item(info, url)
    return info
