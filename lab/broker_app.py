"""Separate internal listener: sandboxes cannot reach the workbench API."""
from fastapi import FastAPI
from lab.execution_broker import install


def create_app():
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    install(app)
    return app
