from pathlib import Path
from re import compile
from re import sub
from shutil import move
from shutil import rmtree

from httpx import AsyncClient
from httpx import AsyncHTTPTransport
from httpx import HTTPStatusError
from httpx import RequestError
from httpx import TimeoutException
from httpx import get

from source.expansion import remove_empty_directories
from .static import HEADERS
from .static import USERAGENT
from .static import WARNING
from .tools import logging
from ..translation import _

__all__ = ["Manager"]


class Manager:
    NAME = compile(r"[^\u4e00-\u9fffa-zA-Z0-9-_！？，。；：""（）《》]")
    NAME_KEYS = (
        "Post ID",
        "Post Title",
        "Post Description",
        "Post Type",
    )
    NO_PROXY = {
        "http://": None,
        "https://": None,
    }
    SEPARATE = "_"
    WEB_ID = r"(?:^|; )webId=[^;]+"
    WEB_SESSION = r"(?:^|; )web_session=[^;]+"

    def __init__(
            self,
            root: Path,
            path: str,
            folder: str,
            name_format: str,
            chunk: int,
            user_agent: str,
            cookie: str,
            proxy: str | dict,
            timeout: int,
            retry: int,
            record_data: bool,
            image_format: str,
            image_download: bool,
            video_download: bool,
            live_download: bool,
            download_record: bool,
            folder_mode: bool,
            _print: bool,
    ):
        self.root = root
        self.temp = root.joinpath("./temp")
        self.path = self.__check_path(path)
        self.folder = self.__check_folder(folder)
        self.blank_headers = HEADERS | {
            'user-agent': user_agent or USERAGENT,
        }
        self.headers = self.blank_headers | {
            'cookie': cookie,
        }
        self.retry = retry
        self.chunk = chunk
        self.name_format = self.__check_name_format(name_format)
        self.record_data = self.check_bool(record_data, False)
        self.image_format = self.__check_image_format(image_format)
        self.folder_mode = self.check_bool(folder_mode, False)
        self.download_record = self.check_bool(download_record, True)
        self.proxy_tip = None
        self.proxy = self.__check_proxy(proxy)
        self.print_proxy_tip(_print, )
        self.request_client = AsyncClient(
            headers=self.headers | {
                'referer': 'https://www.xiaohongshu.com/',
            },
            timeout=timeout,
            verify=False,
            follow_redirects=True,
            mounts={
                "http://": AsyncHTTPTransport(proxy=self.proxy),
                "https://": AsyncHTTPTransport(proxy=self.proxy),
            },
        )
        self.download_client = AsyncClient(
            headers=self.blank_headers,
            timeout=timeout,
            verify=False,
            follow_redirects=True,
            mounts={
                "http://": AsyncHTTPTransport(proxy=self.proxy),
                "https://": AsyncHTTPTransport(proxy=self.proxy),
            },
        )
        self.image_download = self.check_bool(image_download, True)
        self.video_download = self.check_bool(video_download, True)
        self.live_download = self.check_bool(live_download, True)

    def __check_path(self, path: str) -> Path:
        if not path:
            return self.root
        if (r := Path(path)).is_dir():
            return r
        return r if (r := self.__check_root_again(r)) else self.root

    def __check_folder(self, folder: str) -> Path:
        folder = self.path.joinpath(folder or "Download")
        folder.mkdir(exist_ok=True)
        self.temp.mkdir(exist_ok=True)
        return folder

    @staticmethod
    def __check_root_again(root: Path) -> bool | Path:
        if root.resolve().parent.is_dir():
            root.mkdir()
            return root
        return False

    @staticmethod
    def __check_image_format(image_format) -> str:
        if image_format in {"png", "PNG", "webp", "WEBP"}:
            return image_format.lower()
        return "png"

    @staticmethod
    def is_exists(path: Path) -> bool:
        return path.exists()

    @staticmethod
    def delete(path: Path):
        if path.exists():
            path.unlink()

    @staticmethod
    def archive(root: Path, name: str, folder_mode: bool) -> Path:
        return root.joinpath(name) if folder_mode else root

    @staticmethod
    def move(temp: Path, path: Path):
        move(temp.resolve(), path.resolve())

    def __clean(self):
        rmtree(self.temp.resolve())

    def filter_name(self, name: str) -> str:
        name = self.NAME.sub("_", name)
        return sub(r"_+", "_", name).strip("_")

    @staticmethod
    def check_bool(value: bool, default: bool) -> bool:
        return value if isinstance(value, bool) else default

    async def close(self):
        await self.request_client.aclose()
        await self.download_client.aclose()
        # self.__clean()
        remove_empty_directories(self.root)
        remove_empty_directories(self.folder)

    def __check_name_format(self, format_: str) -> str:
        keys = format_.split()
        return next(
            (
                "post_title"
                for key in keys
                if key not in self.NAME_KEYS
            ),
            format_,
        )

    def __check_proxy(
            self,
            proxy: str,
            url="https://www.xiaohongshu.com/explore",
    ) -> str | None:
        if proxy:
            try:
                response = get(
                    url,
                    proxy=proxy,
                    timeout=10,
                    headers={
                        "User-Agent": USERAGENT,
                    }
                )
                response.raise_for_status()
                self.proxy_tip = (_("Proxy {0} test successful").format(proxy),)
                return proxy
            except TimeoutException:
                self.proxy_tip = (
                    _("Proxy {0} test timeout").format(proxy),
                    WARNING,
                )
            except (
                    RequestError,
                    HTTPStatusError,
            ) as e:
                self.proxy_tip = (
                    _("Proxy {0} test failed: {1}").format(
                        proxy,
                        e,
                    ),
                    WARNING,
                )

    def print_proxy_tip(self, _print: bool = True, log=None, ) -> None:
        if _print and self.proxy_tip:
            logging(log, *self.proxy_tip)

    @classmethod
    def clean_cookie(cls, cookie_string: str) -> str:
        return cls.delete_cookie(
            cookie_string,
            (
                cls.WEB_ID,
                cls.WEB_SESSION,
            ),
        )

    @classmethod
    def delete_cookie(cls, cookie_string: str, patterns: list | tuple) -> str:
        for pattern in patterns:
            # Replace matched parts with empty string
            cookie_string = sub(pattern, "", cookie_string)
        # Remove extra semicolons and spaces
        cookie_string = sub(r';\s*$', "", cookie_string)  # Delete semicolons and spaces at the end
        cookie_string = sub(r';\s*;', ";", cookie_string)  # Delete extra spaces after semicolons in the middle
        return cookie_string.strip('; ')
