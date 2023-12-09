import modal
from modal import Image, Stub, web_endpoint
from pydantic import BaseModel
from fastapi.responses import HTMLResponse

#TODO: waiting for fix from Modal team
def download_model():
    import gpt4all
    print("Pre download the model...")
    #you can use any model from https://gpt4all.io/models/models2.json
    model = gpt4all.GPT4All("mistral-7b-openorca.Q4_0.gguf")

image = modal.Image.from_registry("ubuntu:22.04", add_python="3.11").pip_install("gpt4all").run_function(download_model)
stub = modal.Stub("gpt4all", image=image)
@stub.cls(keep_warm=1)
class GPT4AllChat:
    def __enter__(self):
        import gpt4all
        print("Downloading model")
        self.model = gpt4all.GPT4All("mistral-7b-openorca.Q4_0.gguf")
        print("Loaded model")

    @modal.method()
    def generate(self,query="The capital of France is "):
        output = self.model.generate(query, max_tokens=10)
        return output

@stub.function()
@web_endpoint(method="GET")
def chat():
    gpt = GPT4AllChat()
    respond = gpt.generate.remote()
    # do things with boto3...
    return HTMLResponse(f"<html>{respond}</html>")

@stub.local_entrypoint()
def main_old():
    model = GPT4AllChat()
    for i in range(3):
        print(model.generate.remote())