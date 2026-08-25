import platform
import sys
import os

from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext


class Pybind11BuildExt(build_ext):
    def build_extensions(self):
        import pybind11

        for ext in self.extensions:
            ext.include_dirs.append(pybind11.get_include())
            if sys.platform == "win32":
                ext.extra_compile_args.extend(["/O2", "/std:c++17", "/EHsc"])
            else:
                ext.extra_compile_args.extend(["-O3", "-std=c++17", "-Wno-misleading-indentation"])
        super().build_extensions()

    def build_extension(self, ext):
        # MSVC: compile v2_simd_avx2.cpp separately with /arch:AVX2 because
        # the flag cannot be scoped per-function (MSVC has no equivalent of
        # GCC/Clang's __attribute__((target(...)))). The resulting object is
        # linked into the extension alongside the baseline-compiled sources.
        if self.compiler.compiler_type == "msvc" and any("v2_simd_avx2" in s for s in ext.sources):
            avx2_sources = [s for s in ext.sources if "v2_simd_avx2" in s]
            ext.sources = [s for s in ext.sources if "v2_simd_avx2" not in s]
            # Compile AVX2 TU with /arch:AVX2
            avx2_objects = self.compiler.compile(
                avx2_sources,
                output_dir=os.path.join(self.build_temp, "avx2"),
                include_dirs=ext.include_dirs,
                macros=ext.define_macros,
                extra_postargs=[arg for arg in ext.extra_compile_args if "arch" not in arg]
                    + ["/arch:AVX2"],
                debug=self.debug,
            )
            ext.extra_objects.extend(avx2_objects)
        super().build_extension(ext)


def configure_simd(extension):
    """Opt the v2 core into runtime-dispatched AVX2 kernels.

    GCC and Clang scope the instruction set in-source via per-function
    __attribute__((target("avx2"))), so no compiler flag is needed.
    MSVC requires '/arch:AVX2' on the file that uses AVX2 intrinsics;
    the build_ext class compiles v2_simd_avx2.cpp separately with that
    flag and links the object into the extension. Runtime dispatch
    selects scalar on CPUs without AVX2 regardless of compilation.
    """
    x86_64_machine = platform.machine().lower() in {"amd64", "x86_64"}
    if x86_64_machine:
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
