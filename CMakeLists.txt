cmake_minimum_required(VERSION 3.16)
project(wimf VERSION 2.2.0 LANGUAGES C CXX)

include(GNUInstallDirs)
include(CMakePackageConfigHelpers)

add_library(wimf src/wimf_c.cpp src/v2_core.cpp
    src/v2_simd.cpp src/v2_simd_avx2.cpp src/v2_simd_neon.cpp src/v2_simd_crc.cpp
    third_party/zstd/zstd.c)
add_library(WIMF::wimf ALIAS wimf)
target_compile_features(wimf PUBLIC cxx_std_17)
target_include_directories(wimf
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/src>
        $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>
    PRIVATE third_party/zstd)
set_target_properties(wimf PROPERTIES
    C_VISIBILITY_PRESET hidden
    CXX_VISIBILITY_PRESET hidden
    VISIBILITY_INLINES_HIDDEN YES
    VERSION ${PROJECT_VERSION}
    SOVERSION 1)
if(BUILD_SHARED_LIBS)
    target_compile_definitions(wimf PRIVATE WIMF_C_BUILDING_DLL PUBLIC WIMF_C_SHARED)
endif()
# SIMD kernels are runtime-dispatched: ISA-specific code lives in dedicated
# translation units and is selected at run time (CPUID/XGETBV on x86-64,
# getauxval(AT_HWCAP) for the ARM CRC extension). Any compiler flags that
# enable an instruction set are therefore scoped to individual source files,
# keeping the rest of the library baseline-portable on every host CPU.
include(CheckCXXCompilerFlag)
if(NOT EMSCRIPTEN AND CMAKE_SYSTEM_PROCESSOR MATCHES "^(AMD64|x86_64|i[3-6]86|x86)$")
    if(MSVC)
        set_source_files_properties(src/v2_simd_avx2.cpp PROPERTIES
            COMPILE_OPTIONS "/arch:AVX2"
            COMPILE_DEFINITIONS "WIMF_SIMD_ENABLE_AVX2")
    elseif(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
        # GCC/Clang also enable AVX2 in-source via '#pragma GCC target'; the
        # flag below is belt-and-braces for toolchains with partial support.
        set_source_files_properties(src/v2_simd_avx2.cpp PROPERTIES
            COMPILE_DEFINITIONS "WIMF_SIMD_ENABLE_AVX2")
        check_cxx_compiler_flag("-mavx2" WIMF_COMPILER_HAS_MAVX2)
        if(WIMF_COMPILER_HAS_MAVX2)
            set_property(SOURCE src/v2_simd_avx2.cpp APPEND PROPERTY COMPILE_OPTIONS "-mavx2")
        endif()
    endif()
elseif(NOT EMSCRIPTEN AND CMAKE_SYSTEM_PROCESSOR MATCHES "^(aarch64|ARM64|arm64)$")
    if(NOT APPLE AND CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
        check_cxx_compiler_flag("-march=armv8-a+crc" WIMF_COMPILER_HAS_ARM_CRC)
        if(WIMF_COMPILER_HAS_ARM_CRC)
            set_source_files_properties(src/v2_simd_crc.cpp PROPERTIES
                COMPILE_OPTIONS "-march=armv8-a+crc")
        endif()
    endif()
endif()
if(WIN32)
    set(WIMF_RESOURCE_FILE_TYPE VFT_DLL)
    set(WIMF_RESOURCE_DESCRIPTION "WIMF native library")
    configure_file(cmake/wimf_version.rc.in wimf_dll_version.rc @ONLY)
    set(WIMF_RESOURCE_FILE_TYPE VFT_APP)
    set(WIMF_RESOURCE_DESCRIPTION "WIMF native command-line tool")
    configure_file(cmake/wimf_version.rc.in wimf_exe_version.rc @ONLY)
    target_sources(wimf PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/wimf_dll_version.rc)
endif()

option(WIMF_BUILD_TESTS "Build standalone native tests" ON)
option(WIMF_BUILD_TOOLS "Build dependency-free native conversion tools" ON)
option(WIMF_BUILD_WINDOWS_SHELL "Build Windows Explorer thumbnail and preview providers" OFF)
option(WIMF_BUILD_IMAGEMAGICK "Build the ImageMagick 7 WIMF decoder module" OFF)
if(WIMF_BUILD_TOOLS)
    add_executable(wimf_native tools/wimf_native.c)
    if(WIN32)
        target_sources(wimf_native PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/wimf_exe_version.rc)
    endif()
    set_target_properties(wimf_native PROPERTIES OUTPUT_NAME wimf-native)
    target_link_libraries(wimf_native PRIVATE WIMF::wimf)
    install(TARGETS wimf_native RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})
endif()
if(WIMF_BUILD_IMAGEMAGICK)
    find_package(PkgConfig REQUIRED)
    pkg_check_modules(MAGICKCORE REQUIRED IMPORTED_TARGET MagickCore-7.Q16HDRI)
    add_library(wimf_imagemagick MODULE integrations/imagemagick/wimf.c)
    target_link_libraries(wimf_imagemagick PRIVATE WIMF::wimf PkgConfig::MAGICKCORE)
    set_target_properties(wimf_imagemagick PROPERTIES PREFIX "" OUTPUT_NAME "wimf")
endif()
if(WIN32 AND WIMF_BUILD_WINDOWS_SHELL)
    add_library(wimf_thumbnail SHARED
        integrations/windows/wimf_thumbnail.cpp
        integrations/windows/wimf-thumbnail.def)
    target_sources(wimf_thumbnail PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/wimf_dll_version.rc)
    target_compile_features(wimf_thumbnail PRIVATE cxx_std_17)
    target_link_libraries(wimf_thumbnail PRIVATE WIMF::wimf ole32 uuid gdi32 user32)
    set_target_properties(wimf_thumbnail PROPERTIES PREFIX "" OUTPUT_NAME "wimf-thumbnail")
    install(TARGETS wimf_thumbnail RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})
    install(FILES integrations/windows/register-thumbnail.ps1
                  integrations/windows/unregister-thumbnail.ps1
            DESTINATION ${CMAKE_INSTALL_DATADIR}/wimf/windows)
endif()
if(WIMF_BUILD_TESTS)
    enable_testing()
    add_executable(wimf_c_api_test tests/cpp/test_c_api.c)
    target_link_libraries(wimf_c_api_test PRIVATE WIMF::wimf)
    add_test(NAME wimf_c_api_roundtrip COMMAND wimf_c_api_test)
    add_executable(wimf_simd_test tests/cpp/test_v2_simd.cpp)
    target_link_libraries(wimf_simd_test PRIVATE WIMF::wimf)
    target_compile_features(wimf_simd_test PRIVATE cxx_std_17)
    add_test(NAME wimf_simd_kernels COMMAND wimf_simd_test)
    if(WIMF_BUILD_TOOLS)
        add_test(NAME wimf_native_version COMMAND wimf_native --version)
        add_test(NAME wimf_native_ppm_roundtrip
            COMMAND ${CMAKE_COMMAND}
                -DTOOL=$<TARGET_FILE:wimf_native>
                -DWORK=${CMAKE_CURRENT_BINARY_DIR}/native-tool-test
                -P ${CMAKE_CURRENT_SOURCE_DIR}/tests/cmake/native_tool_roundtrip.cmake)
    endif()
endif()

install(TARGETS wimf EXPORT WIMFTargets
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})
install(FILES src/wimf_c.h DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
install(FILES LICENSE DESTINATION ${CMAKE_INSTALL_DATADIR}/wimf)
install(FILES third_party/zstd/LICENSE DESTINATION ${CMAKE_INSTALL_DATADIR}/wimf/licenses
        RENAME Zstandard-LICENSE)
if(UNIX AND NOT APPLE)
    install(FILES integrations/linux/wimf.xml
            DESTINATION ${CMAKE_INSTALL_DATADIR}/mime/packages)
    install(FILES integrations/linux/wimf.thumbnailer
            DESTINATION ${CMAKE_INSTALL_DATADIR}/thumbnailers)
    install(FILES integrations/linux/wimf-studio.desktop
            DESTINATION ${CMAKE_INSTALL_DATADIR}/applications)
endif()
install(EXPORT WIMFTargets NAMESPACE WIMF:: DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/WIMF)
write_basic_package_version_file(${CMAKE_CURRENT_BINARY_DIR}/WIMFConfigVersion.cmake
    VERSION ${PROJECT_VERSION} COMPATIBILITY SameMajorVersion)
configure_package_config_file(cmake/WIMFConfig.cmake.in ${CMAKE_CURRENT_BINARY_DIR}/WIMFConfig.cmake
    INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/WIMF)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/WIMFConfig.cmake
              ${CMAKE_CURRENT_BINARY_DIR}/WIMFConfigVersion.cmake
        DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/WIMF)

set(CPACK_PACKAGE_NAME "WIMF-SDK")
set(CPACK_PACKAGE_VENDOR "WIMF contributors")
set(CPACK_PACKAGE_VERSION ${PROJECT_VERSION})
set(CPACK_PACKAGE_FILE_NAME "WIMF-SDK-${PROJECT_VERSION}-${CMAKE_SYSTEM_NAME}-${CMAKE_SYSTEM_PROCESSOR}")
set(CPACK_RESOURCE_FILE_LICENSE "${CMAKE_CURRENT_SOURCE_DIR}/LICENSE")
if(WIN32)
    set(CPACK_GENERATOR ZIP)
else()
    set(CPACK_GENERATOR TGZ)
endif()
include(CPack)
