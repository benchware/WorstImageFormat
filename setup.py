from setuptools import setup, Extension
from setuptools.command.build_ext import build_ext
from wheel.bdist_wheel import bdist_wheel
import sys
import os

class Pybind11BuildExt(build_ext):
    def build_extensions(self):
        import pybind11
        for ext in self.extensions:
            ext.include_dirs.append(pybind11.get_include())
            
            arch = os.environ.get('ARCHFLAGS', '')
            import platform
            machine = platform.machine().lower()
            is_arm = 'arm64' in arch or 'aarch64' in arch or machine in ['arm64', 'aarch64']
            
            if sys.platform == 'win32':
                ext.extra_compile_args.extend(['/O2', '/std:c++17'])
                if not is_arm:
                    ext.extra_compile_args.append('/arch:AVX2')
            else:
                ext.extra_compile_args.extend(['-O3', '-std=c++17'])
                if not is_arm:
                    ext.extra_compile_args.extend(['-mavx2', '-mfma'])
        super().build_extensions()

class BdistWheelCommand(bdist_wheel):
    def finalize_options(self):
        super().finalize_options()
        # Use manylinux platform tag instead of linux
        if self.plat_name == 'linux_x86_64':
            self.plat_name = 'manylinux_2_17_x86_64'

ext_modules = [
    Extension(
        "wimf.wimf_cpp",
        ["src/main.cpp"],
        language='c++',
    ),
]

setup(
    name="wimf",
    ext_modules=ext_modules,
    cmdclass={"build_ext": Pybind11BuildExt, "bdist_wheel": BdistWheelCommand},
)
