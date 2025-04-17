from json import dump
from json import load
from pathlib import Path
import codecs
from io import BytesIO
import sys
import os

# 解决相对导入
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(os.path.dirname(current_dir))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from source.module.static import ROOT
from source.module.static import USERAGENT

__all__ = ['Settings']


class Settings:
    default = {
        "work_path": "",
        "folder_name": "Download",
        "name_format": "发布时间 作者昵称 post_title",
        "user_agent": USERAGENT,
        "cookie": "",
        "proxy": None,
        "timeout": 10,
        "chunk": 1024 * 1024 * 2,
        "max_retry": 5,
        "record_data": False,
        "image_format": "PNG",
        "image_download": True,
        "video_download": True,
        "live_download": False,
        "folder_mode": False,
        "download_record": True,
        "language": "zh_CN",
    }
    encode = "utf-8"  # 统一使用utf-8格式

    def __init__(self, root: Path = ROOT):
        self.file = root.joinpath("./settings.json")

    def run(self):
        return self.read() if self.file.is_file() else self.create()

    def read(self) -> dict:
        try:
            # 先尝试使用utf-8-sig读取，这样可以自动处理BOM
            with self.file.open("r", encoding="utf-8-sig") as f:
                return load(f)
        except ValueError:
            # 处理JSON解析错误，尝试手动处理BOM
            with open(self.file, 'rb') as f:
                content = f.read()
                # 如果文件以BOM开头，则去除BOM
                if content.startswith(codecs.BOM_UTF8):
                    content = content[len(codecs.BOM_UTF8):]
                # 使用正确的BytesIO从io模块
                return load(BytesIO(content))
        except Exception as e:
            # 如果所有尝试都失败，创建一个新的配置文件
            print(f"读取配置文件失败: {e}，将创建新配置文件")
            return self.create()

    def create(self) -> dict:
        # 创建时使用utf-8无BOM
        with self.file.open("w", encoding=self.encode) as f:
            dump(self.default, f, indent=4, ensure_ascii=False)
            return self.default

    def update(self, data: dict):
        # 更新时使用utf-8无BOM
        with self.file.open("w", encoding=self.encode) as f:
            dump(data, f, indent=4, ensure_ascii=False)

    @classmethod
    def check_keys(
            cls,
            data: dict,
            callback: callable,
            *args,
            **kwargs,
    ) -> dict:
        needful_keys = set(cls.default.keys())
        given_keys = set(data.keys())
        if not needful_keys.issubset(given_keys):
            callback(*args, **kwargs)
            return cls.default
        return data
