import os
import asyncio
from aiohttp import web
import importlib.util
from urllib.parse import urlparse, quote
import asyncio
from dotenv import load_dotenv
import html
from datetime import datetime
from lzhbrowser import Browser
import logging
from lzhgetlogger import get_logger
import uuid

load_dotenv()

logger = get_logger(logging.INFO)

HOST = os.getenv("HOST", '127.0.0.1')
APP_PATH = os.getenv("APP_PATH", "")
PORT = int(os.getenv("PORT", 8000))
B_PROXY_SERVER = os.getenv("B_PROXY_SERVER", "socks5://127.0.0.1:1080")
B_MAX_PAGES:int = int(os.getenv("B_MAX_PAGES", 8))
RSS_BASE_URL = os.getenv("RSS_BASE_URL", '')
RETRIES = int(os.getenv("RETRIES", 2))

def timestamp_to_RFC822(ts:float):
    try :
        return datetime.fromtimestamp(ts).strftime('%a, %d %b %Y %H:%M:%S +0900')
    except:
        return datetime.fromtimestamp(0.0).strftime('%a, %d %b %Y %H:%M:%S +0900')

def info_to_feed(info):
    image = info.get('image',{})
    feed = f'''<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
    <atom:link href="{RSS_BASE_URL}{quote(info.get('link',''), safe='')}" rel="self" type="application/rss+xml" />
    <title>{html.escape(info.get('title',''))}</title>
    <link>{html.escape(info.get('link',''))}</link>
    <description>{html.escape(info.get('description',''))}</description>
    <lastBuildDate>{html.escape(timestamp_to_RFC822(info.get('lastBuildDate',0.0)))}</lastBuildDate>
    <image>
        <url>{html.escape(image.get('ul',''))}</url>
        <title>{html.escape(image.get('title',''))}</title>
        <link>{html.escape(image.get('link',''))}</link>
    </image>
'''
    values = info.get('item',{}).values()
    for value in values:
        feed += f'''
    <item>
        <title>{html.escape(value.get('title',''))}</title>
        <link>{html.escape(value.get('link',''))}</link>
        <description><![CDATA[{value.get('description_html','')}]]></description>
        <pubDate>{html.escape(timestamp_to_RFC822(value.get('pubDate',0.0)))}</pubDate>
        <guid isPermaLink="false">{html.escape(value.get('guid',value.get('link',str(uuid.uuid4()))))}</guid>
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
        logger.error(f"Error loading parse function: {e}")
        raise web.HTTPInternalServerError(text=f"Error loading parse function: {e}")

async def handle_query_request(request):
    url = request.query.get('url')

    if not url:
        logger.warning(f"Missing 'url' query parameter")
        raise web.HTTPBadRequest(text="Missing 'url' query parameter")

    parsed_url = urlparse(url)
    print(parsed_url)

    domain = parsed_url.netloc
    if not domain:
        logger.warning(f"Invalid URL {url}")
        raise web.HTTPBadRequest(text="Invalid URL")

    parser_file = os.path.join('parsers', f'{domain}.py')
    if not os.path.exists(parser_file):
        logger.error(f"parser file not found {url}")
        raise web.HTTPNotFound(text="parser file not found")

    browser: Browser = request.app["browser"]

    parse_function = await load_parse_function(parser_file)
    error = ''
    for attempt in range(1, RETRIES + 2):
        try:
            if asyncio.iscoroutinefunction(parse_function):
                info = await parse_function(url, browser, logger)
            else:
                info = parse_function(url, browser, logger)
            if not info:
                raise RuntimeError(f"No info")
            break
        except Exception as e:
            error = error + f"Error on attempt {attempt} for {url} : {e} \n"
            if attempt >= RETRIES + 1:
                logger.warning(f"Error : \n{error}")
                raise web.HTTPBadRequest(text=f"Error : \n{error}")
            await asyncio.sleep(1)

    feed = info_to_feed(info)
    logger.info(f"Got {len(info.get('item'))} items - {url}")
    return web.Response(text=feed, content_type='application/xml')

async def create_app():
    logger.info("brower initing ...")
    browser = await Browser.create(
        headless=False,
        max_pages=B_MAX_PAGES,
        proxy={"server":B_PROXY_SERVER},
        logging_level=logging.INFO
    )
    logger.info("brower inited")
    app = web.Application()
    app["browser"] = browser
    app.router.add_get("/" + APP_PATH, handle_query_request)
    async def on_cleanup(app):
        await app["browser"].close()
    app.on_cleanup.append(on_cleanup)
    return app

if __name__ == "__main__":
    async def main():
        app = await create_app()
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner=runner, host=HOST, port=PORT)
        await site.start()
        logger.info(f"Running on http://{HOST}:{PORT}")
        while True:
            await asyncio.sleep(3600)

    asyncio.run(main())

