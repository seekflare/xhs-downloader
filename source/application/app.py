from asyncio import Event
from asyncio import Queue
from asyncio import QueueEmpty
from asyncio import gather
from asyncio import sleep
from contextlib import suppress
from datetime import datetime
from re import compile
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
# from aiohttp import web
from pyperclip import paste
from uvicorn import Config
from uvicorn import Server

from source.expansion import BrowserCookie
from source.expansion import Cleaner
from source.expansion import Converter
from source.expansion import Namespace
from source.expansion import beautify_string
from source.module import DataRecorder
from source.module import ExtractData
from source.module import ExtractParams
from source.module import IDRecorder
from source.module import Manager
from source.module import (
    ROOT,
    ERROR,
    WARNING,
    MASTER,
    REPOSITORY,
    VERSION_MAJOR,
    VERSION_MINOR,
    VERSION_BETA,
)
from source.module import logging
from source.module import sleep_time
from source.translation import switch_language, _
from .download import Download
from .explore import Explore
from .image import Image
from .request import Html
from .video import Video

__all__ = ["XHS"]


def _data_cache(function):
    async def inner(self, data: dict, ):
        if self.manager.record_data:
            download = data["media_urls"]
            lives = data["gif_urls"]
            await function(self, data, )
            data["media_urls"] = download
            data["gif_urls"] = lives

    return inner


class XHS:
    VERSION_MAJOR = VERSION_MAJOR
    VERSION_MINOR = VERSION_MINOR
    VERSION_BETA = VERSION_BETA
    LINK = compile(r"https?://www\.xiaohongshu\.com/explore/\S+")
    SHARE = compile(r"https?://www\.xiaohongshu\.com/discovery/item/\S+")
    SHORT = compile(r"https?://xhslink\.com/\S+")
    ID = compile(r"(?:explore|item)/(\S+)?\?")
    __INSTANCE = None
    CLEANER = Cleaner()

    def __new__(cls, *args, **kwargs):
        if not cls.__INSTANCE:
            cls.__INSTANCE = super().__new__(cls)
        return cls.__INSTANCE

    def __init__(
            self,
            work_path="",
            folder_name="Download",
            name_format="发布时间 作者昵称 post_title",
            user_agent: str = None,
            cookie: str = None,
            proxy: str | dict = None,
            timeout=10,
            chunk=1024 * 1024,
            max_retry=5,
            record_data=False,
            image_format="PNG",
            image_download=True,
            video_download=True,
            live_download=False,
            folder_mode=False,
            download_record=True,
            language="zh_CN",
            read_cookie: int | str = None,
            _print: bool = True,
            *args,
            **kwargs,
    ):
        switch_language(language)
        self.manager = Manager(
            ROOT,
            work_path,
            folder_name,
            name_format,
            chunk,
            user_agent,
            self.read_browser_cookie(read_cookie) or cookie,
            proxy,
            timeout,
            max_retry,
            record_data,
            image_format,
            image_download,
            video_download,
            live_download,
            download_record,
            folder_mode,
            _print,
        )
        self.html = Html(self.manager)
        self.image = Image()
        self.video = Video()
        self.explore = Explore()
        self.convert = Converter()
        self.download = Download(self.manager)
        self.id_recorder = IDRecorder(self.manager)
        self.data_recorder = DataRecorder(self.manager)
        self.clipboard_cache: str = ""
        self.queue = Queue()
        self.event = Event()
        # self.runner = self.init_server()
        # self.site = None
        self.server = None

    def __extract_image(self, container: dict, data: Namespace):
        container["media_urls"], container["gif_urls"] = self.image.get_image_link(
            data, self.manager.image_format)

    def __extract_video(self, container: dict, data: Namespace):
        container["media_urls"] = self.video.get_video_link(data)
        container["gif_urls"] = [None, ]

    async def __download_files(
            self,
            container: dict,
            download: bool,
            index,
            log,
            bar,
    ):
        name = self.__naming_rules(container)
        if (u := container["media_urls"]) and download:
            if await self.skip_download(i := container["post_id"]):
                logging(
                    log, _("作品 {0} 存在下载记录，跳过下载").format(i))
            else:
                path, result = await self.download.run(
                    u,
                    container["gif_urls"],
                    index,
                    name,
                    container["post_type"],
                    log,
                    bar,
                )
                await self.__add_record(i, result)
        elif not u:
            logging(log, _("提取作品文件media_urls失败"), ERROR)
        await self.save_data(container)

    @_data_cache
    async def save_data(self, data: dict, ):
        data["采集时间"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data["media_urls"] = " ".join(data["media_urls"])
        data["gif_urls"] = " ".join(i or "NaN" for i in data["gif_urls"])
        await self.data_recorder.add(**data)

    async def __add_record(self, id_: str, result: list) -> None:
        if all(result):
            await self.id_recorder.add(id_)

    async def extract(
            self,
            url: str,
            download=False,
            index: list | tuple = None,
            log=None,
            bar=None,
            data=True,
    ) -> list[dict]:
        # return  # 调试代码
        urls = await self.extract_links(url, log)
        if not urls:
            logging(log, _("提取小红书post_link失败"), WARNING)
        else:
            logging(
                log, _("共 {0} 个小红书作品待处理...").format(len(urls)))
        # return urls  # 调试代码
        return [await self.__deal_extract(i, download, index, log, bar, data, ) for i in urls]

    async def extract_cli(
            self,
            url: str,
            download=True,
            index: list | tuple = None,
            log=None,
            bar=None,
            data=False,
    ) -> None:
        url = await self.extract_links(url, log)
        if not url:
            logging(log, _("提取小红书post_link失败"), WARNING)
        else:
            await self.__deal_extract(url[0], download, index, log, bar, data, )

    async def extract_links(self, url: str, log) -> list:
        urls = []
        for i in url.split():
            if u := self.SHORT.search(i):
                i = await self.html.request_url(
                    u.group(),
                    False,
                    log,
                )
            if u := self.SHARE.search(i):
                urls.append(u.group())
            elif u := self.LINK.search(i):
                urls.append(u.group())
        return urls

    def extract_id(self, links: list[str]) -> list[str]:
        ids = []
        for i in links:
            if j := self.ID.search(i):
                ids.append(j.group(1))
        return ids

    async def __deal_extract(
            self,
            url: str,
            download: bool,
            index: list | tuple | None,
            log,
            bar,
            data: bool,
            cookie: str = None,
    ):
        if await self.skip_download(i := self.__extract_link_id(url)) and not data:
            msg = _("作品 {0} 存在下载记录，跳过处理").format(i)
            logging(log, msg)
            return {"message": msg}
        logging(log, _("开始处理作品：{0}").format(i))
        html = await self.html.request_url(url, log=log, cookie=cookie, )
        namespace = self.__generate_data_object(html)
        if not namespace:
            logging(log, _("{0} 获取数据失败").format(i), ERROR)
            return {}
        data = self.explore.run(namespace)
        # logging(log, data)  # 调试代码
        if not data:
            logging(log, _("{0} 提取数据失败").format(i), ERROR)
            return {}
        if data["post_type"] == _("视频"):
            self.__extract_video(data, namespace)
        elif data["post_type"] == _("图文"):
            self.__extract_image(data, namespace)
        else:
            data["media_urls"] = []
        await self.__download_files(data, download, index, log, bar)
        logging(log, _("作品处理完成：{0}").format(i))
        await sleep_time()
        return data

    @staticmethod
    def __extract_link_id(url: str) -> str:
        link = urlparse(url)
        return link.path.split("/")[-1]

    def __generate_data_object(self, html: str) -> Namespace:
        data = self.convert.run(html)
        return Namespace(data)

    def __naming_rules(self, data: dict) -> str:
        keys = self.manager.name_format.split()
        values = []
        for key in keys:
            match key:
                case "post_title":
                    values.append(self.__get_name_title(data))
                case _:
                    values.append(data[key])
        return beautify_string(
            self.CLEANER.filter_name(
                self.manager.SEPARATE.join(values),
                default=self.manager.SEPARATE.join((
                    data["post_id"],
                )),
            ),
            length=128,
        )

    def __get_name_title(self, data: dict) -> str:
        return beautify_string(
            self.manager.filter_name(data["post_title"]),
            64,
        ) or data["post_id"]

    async def monitor(
            self,
            delay=1,
            download=False,
            log=None,
            bar=None,
            data=True,
    ) -> None:
        logging(
            None,
            _(
                "程序会自动读取并提取剪贴板中的小红书post_link，并自动下载链接对应的作品文件，如需关闭，请点击关闭按钮，或者向剪贴板写入 “close” 文本！"),
            style=MASTER,
        )
        self.event.clear()
        await gather(self.__push_link(delay), self.__receive_link(delay, download, None, log, bar, data))

    async def __push_link(self, delay: int):
        while not self.event.is_set():
            if (t := paste()).lower() == "close":
                self.stop_monitor()
            elif t != self.clipboard_cache:
                self.clipboard_cache = t
                [await self.queue.put(i) for i in await self.extract_links(t, None)]
            await sleep(delay)

    async def __receive_link(self, delay: int, *args, **kwargs):
        while not self.event.is_set() or self.queue.qsize() > 0:
            with suppress(QueueEmpty):
                await self.__deal_extract(self.queue.get_nowait(), *args, **kwargs)
            await sleep(delay)

    def stop_monitor(self):
        self.event.set()

    async def skip_download(self, id_: str) -> bool:
        return bool(await self.id_recorder.select(id_))

    async def __aenter__(self):
        await self.id_recorder.__aenter__()
        await self.data_recorder.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.id_recorder.__aexit__(exc_type, exc_value, traceback)
        await self.data_recorder.__aexit__(exc_type, exc_value, traceback)
        await self.close()

    async def close(self):
        await self.manager.close()

    @staticmethod
    def read_browser_cookie(value: str | int) -> str:
        return BrowserCookie.get(
            value,
            domains=["xiaohongshu.com", ],
        ) if value else ""

    # @staticmethod
    # async def index(request):
    #     return web.HTTPFound(REPOSITORY)

    # async def handle(self, request):
    #     data = await request.post()
    #     url = data.get("url")
    #     download = data.get("download", False)
    #     index = data.get("index")
    #     skip = data.get("skip", False)
    #     url = await self.__extract_links(url, None)
    #     if not url:
    #         msg = _("提取小红书post_link失败")
    #         data = None
    #     else:
    #         if data := await self.__deal_extract(url[0], download, index, None, None, not skip, ):
    #             msg = _("获取小红书作品数据成功")
    #         else:
    #             msg = _("获取小红书作品数据失败")
    #             data = None
    #     return web.json_response(dict(message=msg, url=url[0], data=data))

    # def init_server(self, ):
    #     app = web.Application(debug=True)
    #     app.router.add_get('/', self.index)
    #     app.router.add_post('/xhs/', self.handle)
    #     return web.AppRunner(app)

    # async def run_server(self, log=None, ):
    #     try:
    #         await self.start_server(log)
    #         while True:
    #             await sleep(3600)  # 保持服务器运行
    #     except (CancelledError, KeyboardInterrupt):
    #         await self.close_server(log)

    # async def start_server(self, log=None, ):
    #     await self.runner.setup()
    #     self.site = web.TCPSite(self.runner, "0.0.0.0")
    #     await self.site.start()
    #     logging(log, _("Web API 服务器已启动！"))
    #     logging(log, _("服务器主机及端口: {0}".format(self.site.name, )))

    # async def close_server(self, log=None, ):
    #     await self.runner.cleanup()
    #     logging(log, _("Web API 服务器已关闭！"))

    async def run_server(self, host="0.0.0.0", port=8000, log_level="info", ):
        self.server = FastAPI(
            debug=self.VERSION_BETA,
            title="XHS-Downloader",
            version=f"{self.VERSION_MAJOR}.{self.VERSION_MINOR}")
        self.setup_routes()
        config = Config(
            self.server,
            host=host,
            port=port,
            log_level=log_level,
        )
        server = Server(config)
        await server.serve()

    def setup_routes(self):
        @self.server.get("/")
        async def index():
            return RedirectResponse(url=REPOSITORY)

        @self.server.post("/xhs/", response_model=ExtractData, )
        async def handle(extract: ExtractParams):
            url = await self.extract_links(extract.url, None)
            if not url:
                msg = _("提取小红书post_link失败")
                data = None
            else:
                if data := await self.__deal_extract(
                        url[0],
                        extract.download,
                        extract.index,
                        None,
                        None,
                        not extract.skip,
                        extract.cookie,
                ):
                    msg = _("获取小红书作品数据成功")
                else:
                    msg = _("获取小红书作品数据失败")
                    data = None
            return ExtractData(
                message=msg,
                url=url[0] if url else extract.url,
                data=data)
