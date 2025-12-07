from typing import Annotated
from fastapi import FastAPI, File, UploadFile
from api_app import FastApiAppContainer
import uvicorn
import asyncio
from uvicorn.config import LOGGING_CONFIG
from print_service import PrintServiceManager


def start():
    from config import Config
    from log import get_logger, get_uvicorn_loglevel

    config = Config()
    log = get_logger()
    log.info(f"LOG_LEVEL: {config.LOG_LEVEL}")
    log.info(f"UVICORN_LOG_LEVEL: {get_uvicorn_loglevel()}")
    event_loop = asyncio.get_event_loop()
    uvicorn_log_config: Dict = LOGGING_CONFIG
    fast_api_container = FastApiAppContainer()
    uvicorn_config = uvicorn.Config(
        app=fast_api_container.app,
        host=config.SERVER_LISTENING_HOST,
        port=config.SERVER_LISTENING_PORT,
        log_level=get_uvicorn_loglevel(),
        log_config=uvicorn_log_config,
        loop=event_loop,
        lifespan="on",
    )
    uvicorn_server = uvicorn.Server(config=uvicorn_config)
    print_service = PrintServiceManager()
    fast_api_container.add_startup_callback(print_service.start)
    fast_api_container.add_shutdown_callback(print_service.shutdown)
    try:
        log.debug("Start uvicorn server...")
        event_loop.run_until_complete(uvicorn_server.serve())
    except (KeyboardInterrupt, Exception) as e:
        if isinstance(e, KeyboardInterrupt):
            log.info("KeyboardInterrupt shutdown...")
        if isinstance(e, Exception):
            log.info("Panic shutdown...")
        if isinstance(e, Exception):
            raise e


start()
