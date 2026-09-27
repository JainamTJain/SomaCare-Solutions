"""Process entry for Render and local runs.

Start command, with the working directory set to backend/:

    uvicorn main:app --host 0.0.0.0 --port $PORT
"""

from turnwise.main import app

__all__ = ["app"]
