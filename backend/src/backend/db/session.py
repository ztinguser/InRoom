from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    # 正常结束：提交。
    # 中途抛异常：回滚。
    # 结束后：归还数据库连接
    async with request.app.state.sessions.begin() as session:
        yield session


DB = Annotated[
    AsyncSession,
    Depends(get_db, scope="function"),
]
