from typing import Annotated

from fastapi import Depends, Request

from backend.files.local import LocalObjectStore


def get_object_store(request: Request) -> LocalObjectStore:
    return request.app.state.object_store


ObjectStore = Annotated[LocalObjectStore, Depends(get_object_store)]
