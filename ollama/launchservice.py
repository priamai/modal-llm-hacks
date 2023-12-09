import sys
import time
import subprocess

import modal
from modal import wsgi_app

# Default server port.
OLLAMA_PORT: int = 11434


def _run_subprocess(cmd: list[str], block: bool = True) -> None:
    if block:
        subprocess.run(
            cmd,
            stdout=sys.stdout,
            stderr=sys.stderr,
            check=True,
        )
    else:
        subprocess.Popen(
            cmd,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )


def _is_server_healthy(port: int = OLLAMA_PORT) -> bool:
    url = f"http://localhost:{port}/"
    try:
        response = requests.get(url)
        if response.ok:
            print(f"Successfully made a request to {url}")
            return True
        else:
            print(f"Received a non-success status code from {url}")
            return False
    except requests.RequestException as e:
        print(f"Error making a request to {url}: {e}")
        return False


def download_model():
    _run_subprocess(["ollama", "serve"], block=False)
    while not _is_server_healthy():
        print("waiting for server to start ...")
        time.sleep(1)

    _run_subprocess(["ollama", "pull", "mistral"])


image = (
    modal.Image.from_registry(
        "ollama/ollama",
        add_python="3.11",
    )
    .pip_install("requests")  # for healthchecks
    .pip_install("flask")
    .copy_local_file("./entrypoint.sh", "/opt/entrypoint.sh")
    .dockerfile_commands(
        [
            "RUN chmod a+x /opt/entrypoint.sh",
            'ENTRYPOINT ["/opt/entrypoint.sh"]',
        ]
    )
    .run_function(download_model)
)

stub = modal.Stub("ollama-server", image=image)

with stub.image.run_inside():
    import requests

from modal import Secret, Stub, web_endpoint

from fastapi import Depends, HTTPException, status, Request,Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

auth_scheme = HTTPBearer()


@stub.function(secret=Secret.from_name("ollama-secret"))
@web_endpoint()
async def f(request: Request, token: HTTPAuthorizationCredentials = Depends(auth_scheme)):
    import os

    print(f"AUTH TOKEN: {os.environ['OLLAMA_AUTH_TOKEN']}")
    print("Inbound API request....")
    print(
        f"URL: {request.url} BASE: {request.base_url} PATH PARAMS: {request.path_params} QUERY PARAMS {request.query_params}")


    if token.credentials != os.environ["OLLAMA_AUTH_TOKEN"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    else:


        url = f"http://localhost:{OLLAMA_PORT}/"
        try:
            int_response = requests.get(url)
            return Response(content=int_response.content)
        except Exception:
            raise HTTPException(status_code=int_response.status_code)


@stub.function(image=image)
@wsgi_app()
def flask_app():
    from flask import Flask, request
    import requests

    web_app = Flask(__name__)

    # Start Ollama server.
    _run_subprocess(["ollama", "serve"], block=False)
    while not _is_server_healthy():
        print("waiting for server to start ...")
        time.sleep(1)

    @web_app.get("/")
    def home():
        url = f"http://localhost:{OLLAMA_PORT}/"
        print("Calling internal ollama now ....")
        try:
            ir = requests.get(url)
            return ir.text
        except Exception:
            raise HTTPException(status_code=ir.status_code)

    @web_app.get("/api/tags")
    def api_tags():
        url = f"http://localhost:{OLLAMA_PORT}/api/tags"
        print("Calling internal ollama now ....")
        try:
            ir = requests.get(url)
            if ir.status_code==200:
                return ir.json()
            else:
                raise HTTPException(status_code=ir.status_code)
        except Exception:
            raise HTTPException(status_code=ir.status_code)
    @web_app.post("/echo")
    def echo():
        return request.json

    return web_app


@stub.function()
def serve_tunnel():
    # Start Ollama server.
    _run_subprocess(["ollama", "serve"], block=False)
    while not _is_server_healthy():
        print("waiting for server to start ...")
        time.sleep(1)

    # Serve Ollama forever; expose server via Modal Tunnel.
    with modal.forward(OLLAMA_PORT) as tunnel:
        print(f"tunnel.url        = {tunnel.url}")
        #print(f"tunnel.tls_socket = {tunnel.tls_socket}")
        while True:
            time.sleep(1)


@stub.local_entrypoint()
def run():
    serve_tunnel.remote()
