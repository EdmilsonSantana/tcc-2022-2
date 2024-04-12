import os
from modal import Image, Secret, Stub, enter, gpu, method

MODEL_DIR = "/model"
BASE_MODEL = "internlm/internlm2-chat-7b"

def download_model_to_folder():
    from huggingface_hub import snapshot_download
    from transformers.utils import move_cache

    os.makedirs(MODEL_DIR, exist_ok=True)

    snapshot_download(
        BASE_MODEL,
        local_dir=MODEL_DIR,
        token=os.environ["HF_TOKEN"],
        ignore_patterns=["*.pt", "*.gguf"],
    )
    move_cache()

image = (
    Image.from_registry(
        "nvidia/cuda:12.1.1-devel-ubuntu22.04", add_python="3.10"
    )
    .pip_install(
        "vllm==0.3.2",
        "huggingface_hub==0.19.4",
        "hf-transfer==0.1.4",
        "torch==2.1.2",
        "accelerate",
        "einops"
    )
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
    .run_function(
        download_model_to_folder,
        secrets=[Secret.from_name("huggingface-secret")],
        timeout=60 * 20,
    )
)

stub = Stub("llm-inference", image=image)
GPU_CONFIG = gpu.A100(count=1)

@stub.cls(gpu=GPU_CONFIG, secrets=[Secret.from_name("huggingface-secret")])
class Model:
    @enter()
    def load(self):
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch
    
        self.model = AutoModelForCausalLM.from_pretrained(
            MODEL_DIR,
            torch_dtype=torch.float16,
            trust_remote_code=True
        ).cuda()
        self.model = self.model.eval()
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR, trust_remote_code=True)

    @method()
    def generate(self, prompt):
        import time

        start = time.monotonic_ns()

        response, _ = self.model.chat(self.tokenizer, prompt, history=[])
   
        duration_s = (time.monotonic_ns() - start) / 1e9

        print(f"Duration: {duration_s}")

        return response
