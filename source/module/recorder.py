from asyncio import CancelledError
from contextlib import suppress

from aiosqlite import connect

from ..module import Manager

__all__ = ["IDRecorder", "DataRecorder", ]


class IDRecorder:
    def __init__(self, manager: Manager):
        self.file = manager.root.joinpath("ExploreID.db")
        self.switch = manager.download_record
        self.database = None
        self.cursor = None

    async def _connect_database(self):
        self.database = await connect(self.file)
        self.cursor = await self.database.cursor()
        await self.database.execute("CREATE TABLE IF NOT EXISTS explore_id (ID TEXT PRIMARY KEY);")
        await self.database.commit()

    async def select(self, id_: str):
        if self.switch:
            await self.cursor.execute("SELECT ID FROM explore_id WHERE ID=?", (id_,))
            return await self.cursor.fetchone()

    async def add(self, id_: str) -> None:
        if self.switch:
            await self.database.execute("REPLACE INTO explore_id VALUES (?);", (id_,))
            await self.database.commit()

    async def __delete(self, id_: str) -> None:
        if id_:
            await self.database.execute("DELETE FROM explore_id WHERE ID=?", (id_,))
            await self.database.commit()

    async def delete(self, ids: list[str]):
        if self.switch:
            [await self.__delete(i) for i in ids]

    async def all(self):
        if self.switch:
            await self.cursor.execute("SELECT ID FROM explore_id")
            return [i[0] for i in await self.cursor.fetchmany()]

    async def __aenter__(self):
        await self._connect_database()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        with suppress(CancelledError):
            await self.cursor.close()
        await self.database.close()


class DataRecorder(IDRecorder):
    DATA_TABLE = (
        ("采集时间", "TEXT"),
        ("post_id", "TEXT PRIMARY KEY"),
        ("post_type", "TEXT"),
        ("post_title", "TEXT"),
        ("post_desc", "TEXT"),
        ("作品标签", "TEXT"),
        ("发布时间", "TEXT"),
        ("最后更新时间", "TEXT"),
        ("收藏数量", "TEXT"),
        ("评论数量", "TEXT"),
        ("分享数量", "TEXT"),
        ("点赞数量", "TEXT"),
        ("作者昵称", "TEXT"),
        ("作者ID", "TEXT"),
        ("作者链接", "TEXT"),
        ("post_link", "TEXT"),
        ("media_urls", "TEXT"),
        ("gif_urls", "TEXT"),
    )

    def __init__(self, manager: Manager):
        super().__init__(manager)
        self.file = manager.folder.joinpath("ExploreData.db")
        self.switch = manager.record_data

    async def _connect_database(self):
        self.database = await connect(self.file)
        self.cursor = await self.database.cursor()
        await self.database.execute(f"""CREATE TABLE IF NOT EXISTS explore_data (
        {",".join(" ".join(i) for i in self.DATA_TABLE)}
        );""")
        await self.database.commit()

    async def select(self, id_: str):
        pass

    async def add(self, **kwargs) -> None:
        if self.switch:
            await self.database.execute(f"""REPLACE INTO explore_data (
        {", ".join(i[0] for i in self.DATA_TABLE)}
        ) VALUES (
        {", ".join("?" for _ in kwargs)}
        );""", self.__generate_values(kwargs))
            await self.database.commit()

    async def __delete(self, id_: str) -> None:
        pass

    async def delete(self, ids: list | tuple):
        pass

    async def all(self):
        pass

    def __generate_values(self, data: dict) -> tuple:
        return tuple(data[i] for i, _ in self.DATA_TABLE)
