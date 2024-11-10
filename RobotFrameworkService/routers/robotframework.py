from concurrent.futures import Executor
import pathlib

from fastapi import APIRouter, Request, Path, status
from fastapi.responses import HTMLResponse, Response, RedirectResponse
import robot.api
from starlette.responses import JSONResponse

from RobotFrameworkService.Config import Config as RFS_Config
from ..constants import LOGS

import robot

import multiprocessing as mp

import asyncio
import shutil
RESPONSE_FORMAT = RFS_Config().cmd_args.responseformat

router = APIRouter(
    prefix="/robotframework",
    responses={
        404: {
            "description": "Not found: Webservice is either busy or requested endpoint is not supported."
        }
    },
)


is_execution_finished = (
    lambda x: x.is_dir()
              and (x / "report.html").exists()
              and (x / "log.html").exists()
)


async def run_robot_in_background(func, args):
    p = mp.Process(target=func, args=args)
    p.start()
    return p

def _make_result_url(id):
    return f"/logs/{id}/report.html"

def _make_result_data(id, result):
    if result == 0:
        result_message = "PASS"
        status_code = 200
    elif 250 >= result >= 1:
        result_message = f"FAIL: {result} tasks failed"
        status_code = 400
    else:
        result_message = f"FAIL: Errorcode {result}"
        status_code = 500
        
    content = {
        "id": id,
        "result_page": _make_result_url(id),
        "result": result_message
    }
    
    if status_code == 500:
        content["result_page"] = ""
    return (content, status_code)
    
def _make_html_response(id, result):
    content, status_code = _make_result_data(id, result)
    result_page = content["result"]
    result_page += f'<p><a href="{content["result_page"]}">Go to log</a></p>'
    
    return Response(
        content=result_page, media_type="text/html", status_code=status_code
    )

def _make_json_response(id, result):
    content, status_code = _make_result_data(id, result)
    return JSONResponse(
        status_code=status_code,
        content=content
    )
async def run_robot_and_wait(executor: Executor, func, args):
    # run robot concurrently and wait for it.
    loop = asyncio.get_event_loop()
    result: int = await loop.run_in_executor(executor, func, *args)
    id = args[0]

    if RESPONSE_FORMAT == "html":
        return _make_html_response(id, result)
    else:
        return _make_json_response(id, result)




@router.get("/run/all", tags=["execution"])
async def run_all(request: Request):
    """
    Run all task available.
    """
    id = request.headers["request-id"]
    config = RFS_Config().cmd_args
    response = await run_robot_and_wait(
        request.app.state.executor, func=_start_all_robot_tasks, args=[id, config]
    )

    return response


@router.get("/run/all/async", tags=["execution"])
async def run_all_async(request: Request):
    """
    Starts all Robot tasks. Returns execution id and continures to run Robot tasks in background.
    """
    id = request.headers["request-id"]
    config = RFS_Config().cmd_args
    await run_robot_in_background(func=_start_all_robot_tasks, args=[id, config])
    return id


@router.get("/run/{task}", tags=["execution"])
async def run_task(task, request: Request):
    """
    Run a given task.
    """
    id = request.headers["request-id"]
    variables = RequestHelper.parse_variables_from_query(request)
    config = RFS_Config().cmd_args
    response = await run_robot_and_wait(
        request.app.state.executor,
        func=_start_specific_robot_task,
        args=[id, task, variables, config],
    )
    return response


@router.get("/run/{task}/async", tags=["execution"])
async def run_task_async(task, request: Request):
    """
    Start a given task. Returns execution id and continues to run Robot task in background.
    """
    id = request.headers["request-id"]
    variables = RequestHelper.parse_variables_from_query(request)
    config = RFS_Config().cmd_args
    await run_robot_in_background(
        func=_start_specific_robot_task,
        args=[id, task, variables, config]
    )
    return id


@router.get("/run/suite/{suite}", tags=["execution"])
async def run_suite(suite, request: Request):
    """
    Run a given suite.
    """
    id = request.headers["request-id"]
    variables = RequestHelper.parse_variables_from_query(request)
    config = RFS_Config().cmd_args
    response = await run_robot_and_wait(
        request.app.state.executor,
        func=_start_specific_robot_suite,
        args=[id, suite, variables, config],
    )
    return response


@router.get("/run/suite/{suite}/async", tags=["execution"])
async def run_suite_async(suite, request: Request):
    """
    Start a given suite. Returns execution id and continues to run Robot suite in background.
    """
    id = request.headers["request-id"]
    variables = RequestHelper.parse_variables_from_query(request)
    config = RFS_Config().cmd_args
    await run_robot_in_background(
        func=_start_specific_robot_suite,
        args=[id, suite, variables, config]
    )
    return id


@router.get("/run_and_show/{task}", tags=["execution"], response_class=HTMLResponse)
async def start_robot_task_and_show_log(task: str, request: Request):
    """
    Run a given task with variables and return log.html
    """
    id = request.headers["request-id"]
    variables = RequestHelper.parse_variables_from_query(request)
    config = RFS_Config().cmd_args
    await run_robot_and_wait(
        request.app.state.executor,
        func=_start_specific_robot_task,
        args=[id, task, variables, config],
    )
    return RedirectResponse(f"/logs/{id}/log.html")


@router.get(
    "/run_and_show_report/{task}", tags=["execution"], response_class=HTMLResponse
)
async def start_robot_task_and_show_report(task: str, request: Request):
    """
    Run a given task with variables and return report.html
    """
    id = request.headers["request-id"]
    variables = RequestHelper.parse_variables_from_query(request)
    config = RFS_Config().cmd_args
    await run_robot_and_wait(
        request.app.state.executor,
        func=_start_specific_robot_task,
        args=[id, task, variables, config],
    )
    return RedirectResponse(f"/logs/{id}/report.html")


@router.get("/show_log/{executionid}", tags=["reporting"], response_class=HTMLResponse)
async def show_log(
    executionid: str = Path(
        title="ID of a previous request",
        description="Insert here the value of a previous response header field 'x-request-id'",
    )
):
    """
    Show most recent log.html from a given execution
    """
    return RedirectResponse(f"/logs/{executionid}/log.html")


@router.get(
    "/show_report/{executionid}", tags=["reporting"], response_class=HTMLResponse
)
async def show_report(
    executionid: str = Path(
        title="ID of a previous request",
        description="Insert here the value of a previous response header field 'x-request-id'",
    )
):
    """
    Show most recent report.html from a given execution
    """
    return RedirectResponse(f"/logs/{executionid}/report.html")


@router.get(
    "/show_output/{executionid}", tags=["reporting"], response_class=HTMLResponse
)
async def show_raw_output(
    executionid: str = Path(
        title="ID of a previous request",
        description="Insert here the value of a previous response header field 'x-request-id'",
    )
):
    """
    Show most recent report.html from a given execution
    """
    return RedirectResponse(f"/logs/{executionid}/output.xml")


@router.get("/executions", tags=["execution"], response_class=JSONResponse)
async def show_execution_ids():
    """
    get all execution ids for the finished tasks
    """
    logs = pathlib.Path(f"./{LOGS}")
    return [log.stem for log in logs.iterdir() if is_execution_finished(log)]


@router.delete(
    "/logs/{executionid}",
    tags=["reporting"],
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_204_NO_CONTENT: {
            "description": "The logs have been deleted",
        },
        status.HTTP_404_NOT_FOUND: {
            "content": {"text/html": {}},
            "description": "The logs not existing or being generating",
        }
    },
)
async def delete_logs(
    executionid: str = Path(
        description="Insert here the value of a previous response header field 'x-request-id' which you want delete logs",
    )
):
    log = pathlib.Path(f"./{LOGS}/{executionid}")
    if is_execution_finished(log):
        shutil.rmtree(log, ignore_errors=True)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    else:
        return Response(
            content=f"The logs {executionid} not existing or being generating",
            media_type="text/html",
            status_code=status.HTTP_404_NOT_FOUND
        )


def _start_all_robot_tasks(id: str, config) -> int:
    if config.variablefiles is None:
        variablefiles = []
    else:
        variablefiles = config.variablefiles

    return robot.run(
        config.taskfolder,
        outputdir=f"logs/{id}",
        debugfile=config.debugfile,
        variablefile=variablefiles,
        consolewidth=120,
    )


def _start_specific_robot_suite(id: str, suite: str, variables: list, config) -> int:
    if config.variablefiles is None:
        variablefiles = []
    else:
        variablefiles = config.variablefiles

    return robot.run(
        config.taskfolder,
        suite=suite,
        outputdir=f"logs/{id}",
        debugfile=config.debugfile,
        variable=variables,
        variablefile=variablefiles,
        consolewidth=120,
    )


def _start_specific_robot_task(id: str, task: str, variables: list, config) -> int:
    if config.variablefiles is None:
        variablefiles = []
    else:
        variablefiles = config.variablefiles

    return robot.run(
        config.taskfolder,
        task=task,
        outputdir=f"logs/{id}",
        debugfile=config.debugfile,
        variable=variables,
        variablefile=variablefiles,
        consolewidth=120,
    )


class RequestHelper:
    @staticmethod
    def parse_variables_from_query(arguments: Request) -> list:
        return [f"{k}:{v}" for k, v in arguments.query_params.items()]
