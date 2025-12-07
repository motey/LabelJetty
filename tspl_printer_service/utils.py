from typing import Dict
from sqlalchemy.types import TypeDecorator, Text
import json


class SqlJsonText(TypeDecorator):
    """Stores JSON-serializable Python objects as TEXT."""

    impl = Text

    def process_bind_param(self, value: Dict | None, dialect):
        return json.dumps(value) if value is not None else "{}"

    def process_result_value(self, value: str, dialect) -> Dict:
        if value is None:
            return {}
        return json.loads(value)
