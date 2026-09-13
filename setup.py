import os
import platform
from setuptools import Extension, setup

flags = ["-O3", "-std=c11", "-Wall", "-Wextra", "-Wno-unused-parameter"]
if platform.system() == "Darwin" and platform.machine() == "arm64":
    flags += ["-mcpu=apple-m1"]
if os.environ.get("TIGHTARRAY_SANITIZE"):
    flags += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
setup(packages=["tightarray"], ext_modules=[Extension(
    "tightarray._core", ["tightarray/_core.c"], depends=["tightarray/_rows.h", "tightarray/_numpy.h"], extra_compile_args=flags,
    extra_link_args=["-fsanitize=address,undefined"] if os.environ.get("TIGHTARRAY_SANITIZE") else [],
)])
