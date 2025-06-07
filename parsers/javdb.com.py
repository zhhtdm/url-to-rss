from bs4 import BeautifulSoup
import re
from datetime import datetime
from urllib.parse import urlparse
from camo_sign import create_signed_url
from dotenv import load_dotenv
import os
from lzhbrowser import Browser

load_dotenv()
logger = None

CAMO_KEY=bytes(os.getenv("CAMO_KEY", None).encode("utf-8"))
CAMO_ENDPOINT=os.getenv("CAMO_ENDPOINT", None)

def camo(url:str) -> str :
    return url
    if CAMO_ENDPOINT and CAMO_KEY:
        return create_signed_url(CAMO_ENDPOINT,CAMO_KEY,url)
    else :
        return url

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
    tags2 = soup.find_all('span', class_="section-meta")
    tag2 = soup.find('span', class_="actor-section-name")
    tags3 = soup.find_all('div',class_='tag is-info')
    tags4 = soup.find_all(['a','div'],class_='tag is-medium is-link')
    texts2 = [t.text.strip() for t in tags2]
    texts3 = [t.text.strip() for t in tags3]
    texts4 = [t.text.strip() for t in tags4]
    text = tag.text.strip().replace(' | JavDB 成人影片數據庫','') if tag else '未知标题'
    text2 = tag2.text.strip() + ' | ' + ' | '.join(texts2) + ' | ' + ', '.join(texts4) if tag2 else ''
    if '分類篩選' in text:
        text = text.replace('分類篩選', '')
        text = text + ' | ' + ', '.join(texts3) if texts3 else text + ' | 全部'
        text2 = text
    elif '排行 - ' in text:
        text = text.replace('排行 - ',' - ')
        text2 = text
    info['title'] = text
    info['description'] = text2.strip(' | ')

    image_url = 'https://c0.jdbstatic.com/images/logo_120x120.png'
    span = soup.find('span', class_='avatar')
    link = soup.find('link', rel='icon')
    if span and span.has_attr('style'):
        style = span['style']
        # 用正则提取出 url(...) 里面的内容
        match = re.search(r'url\((.*?)\)', style)
        if match:
            image_url = match.group(1)
    elif link and link.has_attr('href'):
        href = link['href']
        image_url = root_url + href
    info['image']['ul'] = image_url
    info['image']['title'] = info['title']
    info['image']['link'] = info['link']

    tags = soup.find_all('div', class_='item')
    if not tags:
        return None

    date_obj_set = set()
    for item in tags:
        tag = item.find('div',class_='video-title')
        tag1 = item.find('a', class_='box')
        date_tag = item.find('div', class_='meta')
        if not tag or not tag1 or not date_tag:
            continue
        tag3 = tag.find('strong')
        if not tag3 or not tag1.has_attr('href') or not tag1.has_attr('title'):
            continue
        id = tag3.text.strip()
        href = tag1['href']
        title = tag1['title']
        date = date_tag.text.strip()
        if not id or not href or not title or not date:
            continue
        try:
            date_obj = datetime.strptime(date, '%Y-%m-%d')
        except:
            continue

        info['item'][id]={}
        info['item'][id]['title'] = title
        info['item'][id]['link'] = root_url + href
        # info['item'][id]['description'] = ''
        info['item'][id]['pubDate'] = date_obj.timestamp()
        info['item'][id]['guid'] = id
        date_obj_set.add(date_obj)

        html_block = BeautifulSoup('<div> </div>', 'html.parser')
        img_tag = item.find('img')
        if img_tag:
            # 创建一个新的img标签，只保留src属性
            new_img_tag = html_block.new_tag('img', src=camo(img_tag['src']))
            html_block.div.append(new_img_tag)
        html_block.div.append(date_tag)
        html_block_str = str(html_block)

        info['item'][id]['description_html'] = html_block_str

    if not info.get('item'):
        return None
    latest_date = max(date_obj_set) if date_obj_set else datetime.now()
    info['lastBuildDate'] = latest_date.timestamp()

    return info

async def parse(url:str, browser:Browser, _logger):
    global logger
    logger = _logger
    html = await browser.fetch(url, wait_until='domcontentloaded')
    if not html:
        return None
    return html_to_info(html, url)
