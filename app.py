import os
import asyncio
from aiohttp import web
import importlib.util
from urllib.parse import urlparse, quote
import asyncio
from lzhaiofetcher import AioFetcher
from dotenv import load_dotenv
import html
from datetime import datetime

load_dotenv()

HOST = os.getenv("HOST", '127.0.0.1')
APP_PATH = os.getenv("APP_PATH", "")
PORT = int(os.getenv("PORT", 8000))
FETCH_TOKEN = os.getenv("FETCH_TOKEN", "")
FETCH_SERVER = os.getenv("FETCH_SERVER", "")
AIOFETCHER_MAX_CONCURRENT = int(os.getenv("AIOFETCHER_MAX_CONCURRENT", 10))
fetcher_semaphore = asyncio.Semaphore(AIOFETCHER_MAX_CONCURRENT)

def timestamp_to_RFC822(ts):
    return datetime.fromtimestamp(ts).strftime('%a, %d %b %Y %H:%M:%S +0000')

def info_to_feed(info):
    feed = f'''<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
    <title>{html.escape(info['title'])}</title>
    <link>{html.escape(info['link'])}</link>
    <description>{html.escape(info['description'])}</description>
    <lastBuildDate>{html.escape(timestamp_to_RFC822(info['lastBuildDate']))}</lastBuildDate>
    <image>
        <ul>{html.escape(info['image']['ul'])}</ul>
        <title>{html.escape(info['image']['title'])}</title>
        <link>{html.escape(info['image']['link'])}</link>
    </image>
'''
    for value in info['item'].values():
        feed += f'''
    <item>
        <title>{html.escape(value['title'])}</title>
        <link>{html.escape(value['link'])}</link>
        <description><![CDATA[{value['description_html']}]]></description>
        <pubDate>{html.escape(timestamp_to_RFC822(value['pubDate']))}</pubDate>
    </item>
'''
    feed += '''
</channel>
</rss>
'''
    return feed

# 动态导入异步解析函数
async def load_parse_function(parser_file):
    # parse_module_path = os.path.join(domain_folder, 'parse.py')
    try:
        spec = importlib.util.spec_from_file_location("parse_module", parser_file)
        parse_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(parse_module)
        return getattr(parse_module, 'parse')
    except Exception as e:
        raise web.HTTPInternalServerError(text=f"Error loading parse function: {e}")

async def handle_query_request(request):
    url = request.query.get('url')
    if not url:
        raise web.HTTPBadRequest(text="Missing 'url' query parameter")

    parsed_url = urlparse(url)
    print(parsed_url)

    domain = parsed_url.netloc
    if not domain:
        raise web.HTTPBadRequest(text="Invalid URL")

    parser_file = os.path.join('parsers', f'{domain}.py')
    if not os.path.exists(parser_file):
        raise web.HTTPNotFound(text="parser file not found")

    # fetch_url = url.replace('javdb.com','javdb457.com') if domain == 'javdb.com' else url

    fetch_url = f"{FETCH_SERVER}/?url={quote(url, safe='')}&token={FETCH_TOKEN}"

    async with fetcher_semaphore:
        fetcher = AioFetcher()
        html = await fetcher.fetch(fetch_url)
        await fetcher.close()

    if not html:
        raise web.HTTPBadRequest(text="Maybe the URL is wrong, please try again later")

    parse_function = await load_parse_function(parser_file)
    if asyncio.iscoroutinefunction(parse_function):
        info = await parse_function(html, url)
    else:
        info = parse_function(html, url)
    feed = info_to_feed(info)
    return web.Response(text=feed, content_type='application/xml')

app = web.Application()
app.router.add_get("/"+APP_PATH, handle_query_request)

if __name__ == "__main__":
    web.run_app(app, host=HOST, port=PORT)
