"""Build the disposable prototype into --build-lib; never install production."""

from pathlib import Path

import blosc2
from setuptools import Extension, setup

root = Path(blosc2.__file__).parent
setup(
    name="ta-ccontext-experiment",
    ext_modules=[
        Extension(
            "ta_ccontext",
            [str(Path(__file__).with_name("context.c"))],
            include_dirs=[str(root / "include")],
            library_dirs=[str(root / "lib")],
            libraries=["blosc2"],
            extra_compile_args=[
                "-O3",
                "-std=c11",
                "-Wall",
                "-Wextra",
                "-Wno-unused-parameter",
            ],
            extra_link_args=[f"-Wl,-rpath,{root / 'lib'}"],
        )
    ],
    packages=[],
)
