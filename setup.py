import platform
import sys

from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext


class Pybind11BuildExt(build_ext):
    def build_extensions(self):
        import pybind11

        for ext in self.extensions:
            ext.include_dirs.append(pybind11.get_include())
            if sys.platform == "win32":
                ext.extra_compile_args.extend(["/O2", "/std:c++17"])
            else:
                ext.extra_compile_args.extend(["-O3", "-std=c++17", "-Wno-misleading-indentation"])
        super().build_extensions()


def configure_simd(extension):
    """Opt the v2 core into runtime-dispatched AVX2 kernels.

    GCC and Clang scope the instruction set in-source via '#pragma GCC
    target', so no compiler flag is needed. MSVC requires '/arch:AVX2',
    which setuptools cannot apply per file; Windows wheels therefore keep
    the portable scalar paths (kernels compiled out, results identical).
    """
    non_windows_platform = sys.platform not in {"win32", "cygwin", "emscripten"}
    x86_64_machine = platform.machine().lower() in {"amd64", "x86_64"}
    if non_windows_platform and x86_64_machine:
        extension.define_macros.append(("WIMF_SIMD_ENABLE_AVX2", None))


v2_extension = Extension(
    "wimf.wimf_v2_cpp",
    [
        "src/v2_core.cpp",
        "src/v2_bindings.cpp",
        "src/v2_simd.cpp",
        "src/v2_simd_avx2.cpp",
        "src/v2_simd_neon.cpp",
        "src/v2_simd_crc.cpp",
        "src/zstd_vendor.cpp",
    ],
    include_dirs=["third_party/zstd"],
    language="c++",
)
configure_simd(v2_extension)

ext_modules = [
    Extension(
        "wimf.wimf_cpp",
        ["src/main.cpp"],
        language="c++",
    ),
    v2_extension,
]

setup(
    name="wimf",
    ext_modules=ext_modules,
    cmdclass={"build_ext": Pybind11BuildExt},
)
