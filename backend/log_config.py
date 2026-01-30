import logging
import sys
from pathlib import Path

from loguru import Record, logger

# Remove default handler
logger.remove()


# Configure Loguru with a format that separates module name from message
def add_module_name(record: Record) -> bool:
    """Ensure every record has module_name in extra."""
    if "module_name" not in record["extra"]:
        record["extra"]["module_name"] = f"{record['name']}:{record['line']}"
    return True


logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <5}</level> | <cyan>{extra[module_name]}</cyan> - {message}",
    level="INFO",
    colorize=True,
    filter=add_module_name,
)


# Intercept standard logging
class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        # Get corresponding Loguru level if it exists
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Get the module name correctly
        if record.name == "root":
            module_name = record.module
        elif "." in record.name:
            module_name = record.name  # Use full path for properly named loggers
        else:
            module_path = Path(record.pathname)
            module_name = module_path.stem  # Get filename without extension

        # Include line number in module name
        module_with_line = f"{module_name}:{record.lineno}"

        # Log using the extra parameter for module name to ensure proper coloring
        logger.bind(module_name=module_with_line).log(level, record.getMessage())


# Replace default logging handler
logging.getLogger().handlers = [InterceptHandler()]
logging.getLogger().setLevel(logging.INFO)

# Intercept all other loggers
for name in ["uvicorn", "uvicorn.access", "fastapi"]:
    logging.getLogger(name).handlers = [InterceptHandler()]
