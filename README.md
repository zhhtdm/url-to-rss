# html to rss
网页内容转`RSS`文档
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
## 流程
1. 收到请求后取得`url`:包含原查询参数的完整网址
2. 根据`url`的域名，动态加载对应的解析函数
3. 将`url`转发给[浏览器服务](https://github.com/zhhtdm/fetch-with-cookie)，得到这个页面的`html`内容
4. 解析`html`
5. 生成`RSS`文档返回
## [浏览器服务](https://github.com/zhhtdm/fetch-with-cookie)
- 此`RSS`服务并不直接抓取网页，考虑到大部分网页需要在登录状态下才能访问，所以此服务要搭配[可以保存`cookie`的浏览器服务](https://github.com/zhhtdm/fetch-with-cookie)才是完全体
- 因为还有别的服务也会用到这个浏览器服务，或者浏览器服务可能会单独部署到多个地区，所以两个服务分离开了
## 解析函数
- 主函数是固定的，解析函数根据业务需求增加，为每个需要生成`RSS`的网址域名编写一个与域名同名的`.py`解析函数文件放在目录`/parsers/`下
- 解析函数文件中需要定义一个名为`parse()`的函数做为入口，同步异步均可
- `parse()`函数接收`html`，返回如下格式统一的字典给主函数，主函数由此生成`RSS`文档
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

在项目根目录下创建 .env 文件，`FETCH_SERVER`与`FETCH_TOKEN`两项必须配置，其他项可以省略，示例:
```
FETCH_SERVER=https://example.com
FETCH_TOKEN=abcdef
AIOFETCHER_MAX_CONCURRENT=10
PORT=8000
APP_PATH=""
HOST=127.0.0.1
```

- `FETCH_SERVER`: 浏览器服务地址
- `FETCH_TOKEN`: 浏览器服务`API`令牌
- `AIOFETCHER_MAX_CONCURRENT`: 最大任务并发数，默认为 `10`
- `PORT`: 服务监听端口，默认为 8000
- `APP_PATH`: 服务路径，默认为空
- `HOST`: 默认绑定内网 `127.0.0.1`

