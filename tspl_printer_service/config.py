import os
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings
from typing import Literal, Optional

env_file_path = os.environ.get(
    "TSPL_PRINTER_WEBAPI_DOT_ENV_FILE", Path(__file__).parent / ".env"
)


class Config(BaseSettings):
    APP_NAME: str = "TSPL Printer WebAPI"
    LOG_LEVEL: Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"] = Field(
        default="DEBUG"
    )
    LOG_DISABLE_COLORS: bool = False
    UVICORN_LOG_LEVEL: Optional[str] = Field(
        default=None,
        description="The log level of the uvicorn server. If not defined it will be the same as LOG_LEVEL.",
    )
    SERVER_LISTENING_PORT: int = Field(default=8888)
    SERVER_LISTENING_HOST: str = Field(
        default="localhost",
        examples=["0.0.0.0", "localhost", "127.0.0.1", "176.16.8.123"],
    )
    SQLITE_PATH: str = Field(default="./printjobs.sqlite")
    ###### CONFIG END ######
    # "class Config:" is a pydantic-settings pre-defined config class to control the behaviour of our settings model
    # you could call it a "meta config" class
    # if you dont know what this is you can ignore it.
    # https://docs.pydantic.dev/latest/api/base_model/#pydantic.main.BaseModel.model_config

    class Config:
        env_nested_delimiter = "__"
        env_file = env_file_path
        env_file_encoding = "utf-8"
        extra = "ignore"
