# url to rss
网址转`RSS`文档
## API
```
http(s)://service.domain/path?url=
```
`url`参数需要编码转义:
```JavaScript
// js
encodeURIComponent(url)
```
```python
# python
import urllib.parse
urllib.parse.quote(url, safe='')
```
- 也可以再接自定义参数，如`&pages=`以控制抓取多少页(需要在[解析函数](#解析函数)中实现)

## 流程
1. 收到请求后取得`url`:包含原查询参数的完整网址
2. 根据`url`的域名，动态加载对应的解析函数
3. 使用[带 cookie 的浏览器模块](https://github.com/zhhtdm/pypi-browser)，得到这个页面的`html`内容
4. 解析`html`
5. 生成`RSS`文档返回

## 解析函数
- 主函数是固定的，解析函数根据业务需求增加，为每个需要生成`RSS`的网址域名编写一个与域名同名的`.py`解析函数文件放在目录`/parsers/`下
- 解析函数文件中需要定义一个名为`parse()`的函数做为入口，同步异步均可
- `parse()`函数接收`request`，返回如下格式统一的字典给主函数，主函数由此生成`RSS`文档
-
    ```python
    info={}
    info['link']
	info['title']
	info['description']
	info['lastBuildDate']
	info['image']={}
	info['image']['ul']
	info['image']['title']
	info['image']['link']
	info['item']={}
    #下面子字典中 [''] 内的空缺没填的是每个条目的 key，每加一个条目加一个这样的子字典
	info['item']['']={}
	info['item']['']['title']
	info['item']['']['link']
	info['item']['']['description']
	info['item']['']['pubDate']
    ```

## 项目环境变量（.env）
可在.env文件中配置的项和其默认值

```python
HOST = os.getenv("HOST", '127.0.0.1')
APP_PATH = os.getenv("APP_PATH", "")
PORT = int(os.getenv("PORT", 8000))
B_PROXY_SERVER = os.getenv("B_PROXY_SERVER", "socks5://127.0.0.1:1080")
B_MAX_PAGES = int(os.getenv("B_MAX_PAGES", 4))
RSS_BASE_URL = os.getenv("RSS_BASE_URL", '')
RETRIES = int(os.getenv("RETRIES", 2))
USERNAME = os.getenv("USERNAME", None)
PASSWORD = os.getenv("PASSWORD", None)
```
- `USERNAME`: 如果非空，则开启 http 认证


