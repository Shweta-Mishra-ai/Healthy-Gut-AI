#!/bin/sh
# Railway provides $PORT environment variable
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
