from concurrent.futures import ProcessPoolExecutor
from contextlib import asynccontextmanager
import os
import pathlib
import sys
import uuid
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from uvicorn import Server
from uvicorn.config import Config

from RobotFrameworkService.Config import Config as RFS_Config
from RobotFrameworkService.routers import robotframework, robotframework_run
from RobotFrameworkService.version import get_version
from .constants import APP_NAME, LOGS


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.executor = ProcessPoolExecutor()
    yield
    app.state.executor.shutdown()


pathlib.Path(LOGS).mkdir(exist_ok=True)
app = FastAPI(title=APP_NAME, version=get_version(), lifespan=lifespan)
app.include_router(robotframework.router)
app.include_router(robotframework_run.router)
app.mount(f"/{LOGS}", StaticFiles(directory=LOGS), name="robotlog")


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())

    request.headers.__dict__["_list"].append(
        ("request-id".encode(), request_id.encode())
    )
    try:
        response = await call_next(request)

    except Exception as ex:
        response = JSONResponse(content={"success": False}, status_code=500)
        print(ex)

    finally:
        response.headers["X-Request-ID"] = request_id
        return response


@app.get("/")
async def greetings(request: Request):
    return "web service for starting robot tasks"


@app.get("/status/")
async def server_status():
    status = {
        "python version": sys.version,
        "platform": sys.platform,
        "arguments": sys.argv,
        "application": APP_NAME,
    }
    return status


def get_config():
    return args


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-t",
        "--taskfolder",
        default="tasks",
        help="Folder with tasks service will executed",
    )
    parser.add_argument(
        "-r",
        "--reponseformat",
        default="json",
        help="Response format json or html",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"Robot Framework Webservice {get_version()}",
    )
    parser.add_argument(
        "-p",
        "--port",
        default=os.environ.get("RFS_PORT", default=5003),
        type=int,
        help="Port of Robot Framework Webservice",
    )
    parser.add_argument(
        "-V",
        "--variablefiles",
        nargs="*",
        default=None,
        help="List of files containing variables",
    )
    parser.add_argument("-b", "--debugfile", default=None, help="Debug output file")
    parser.add_argument(
        "--removekeywords",
        default="tag:secret",
        help="Remove keyword details from reports",
    )
    args = parser.parse_args()

    RFS_Config().cmd_args = args

    server = Server(
        config=(Config(app=app, loop="asyncio", host="0.0.0.0", port=args.port))
    )
    server.run()
