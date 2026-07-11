from PyInstaller import compat
from PyInstaller.utils.hooks import (
    PY_DYLIB_PATTERNS,
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)


def _include_torch_module(name: str) -> bool:
    blocked_prefixes = (
        "torch.testing._internal",
        "torch.testing._utils",
        "torch.distributed._",
        "torch.distributed.algorithms",
        "torch.distributed.autograd",
        "torch.distributed.checkpoint",
        "torch.distributed.elastic",
        "torch.distributed.fsdp",
        "torch.distributed.launcher",
        "torch.distributed.nn",
        "torch.distributed.optim",
        "torch.distributed.pipeline",
        "torch.distributed.rpc",
        "torch.distributed.run",
        "torch.distributed.tensor",
        "torch.utils.tensorboard",
        "torch.onnx",
        "torch._inductor",
        "torch._dynamo",
        "torch._export",
        "torch.fx.experimental",
        "torch.ao",
        "torch.quantization",
    )
    return not any(name.startswith(prefix) for prefix in blocked_prefixes)


module_collection_mode = "pyz+py"
warn_on_missing_hiddenimports = False

datas = collect_data_files(
    "torch",
    excludes=[
        "**/*.h",
        "**/*.hpp",
        "**/*.cuh",
        "**/*.lib",
        "**/*.cpp",
        "**/*.pyi",
        "**/*.cmake",
    ],
)

hiddenimports = collect_submodules("torch", filter=_include_torch_module, on_error="ignore")
binaries = collect_dynamic_libs(
    "torch",
    search_patterns=PY_DYLIB_PATTERNS + ["*.so.*"],
)

if compat.is_win:
    bindepend_symlink_suppression = []
