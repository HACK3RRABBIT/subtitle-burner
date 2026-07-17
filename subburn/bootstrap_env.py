import logging
import os
from pathlib import Path

import config as appconfig

log = logging.getLogger("subburn")


def _register_cuda_dll_dirs():
    # On Windows, ctranslate2 (faster-whisper's backend) locates cuBLAS/cuDNN via the
    # standard DLL search path. The pip nvidia-cublas-cu12/nvidia-cudnn-cu12 packages
    # install their DLLs under site-packages, which isn't on that path by default.
    if not hasattr(os, "add_dll_directory"):
        return
    try:
        import nvidia
        bin_dirs = [
            str(bin_dir)
            for pkg_path in nvidia.__path__
            for bin_dir in Path(pkg_path).glob("*/bin")
        ]
        for bin_dir in bin_dirs:
            os.add_dll_directory(bin_dir)
        # ctranslate2 loads some CUDA libraries via a path resolution that only
        # honors the classic PATH search, not os.add_dll_directory - set both.
        os.environ["PATH"] = os.pathsep.join(bin_dirs) + os.pathsep + os.environ.get("PATH", "")
    except Exception as e:
        log.info("Could not register bundled CUDA DLL directories (%s); GPU load may fall back to CPU", e)


def bootstrap_environment():
    config = appconfig.load()
    if config.get("hf_token") and not (os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")):
        os.environ["HF_TOKEN"] = config["hf_token"]

    _register_cuda_dll_dirs()
