import platform
import sys

from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext


class Pybind11BuildExt(build_ext):
    def build_extensions(self):
        import pybind11

        is_x86 = platform.machine().lower() in {"amd64", "x86_64"}
        for ext in self.extensions:
            ext.include_dirs.append(pybind11.get_include())
            if sys.platform == "win32":
                ext.extra_compile_args.extend(["/O2", "/std:c++17"])
                if ext.name == "wimf.wimf_cpp" and is_x86:
                    ext.extra_compile_args.append("/arch:AVX2")
            else:
                ext.extra_compile_args.extend(["-O3", "-std=c++17"])
                if ext.name == "wimf.wimf_cpp" and is_x86:
                    ext.extra_compile_args.extend(["-mavx2", "-mfma"])
        super().build_extensions()


ext_modules = [
    Extension(
        "wimf.wimf_cpp",
        ["src/main.cpp"],
        language="c++",
    ),
    Extension(
        "wimf.wimf_v2_cpp",
        ["src/v2_core.cpp", "src/v2_bindings.cpp"],
        language="c++",
    ),
]

setup(
    name="wimf",
    ext_modules=ext_modules,
    cmdclass={"build_ext": Pybind11BuildExt},
)
