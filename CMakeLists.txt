cmake_minimum_required(VERSION 3.16)
project(wimf VERSION 2.2.0 LANGUAGES C CXX)

include(GNUInstallDirs)
include(CMakePackageConfigHelpers)

add_library(wimf src/wimf_c.cpp src/v2_core.cpp third_party/zstd/zstd.c)
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

option(WIMF_BUILD_TESTS "Build standalone native tests" ON)
if(WIMF_BUILD_TESTS)
    enable_testing()
    add_executable(wimf_c_api_test tests/cpp/test_c_api.c)
    target_link_libraries(wimf_c_api_test PRIVATE WIMF::wimf)
    add_test(NAME wimf_c_api_roundtrip COMMAND wimf_c_api_test)
endif()

install(TARGETS wimf EXPORT WIMFTargets
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})
install(FILES src/wimf_c.h DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
install(EXPORT WIMFTargets NAMESPACE WIMF:: DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/WIMF)
write_basic_package_version_file(${CMAKE_CURRENT_BINARY_DIR}/WIMFConfigVersion.cmake
    VERSION ${PROJECT_VERSION} COMPATIBILITY SameMajorVersion)
configure_package_config_file(cmake/WIMFConfig.cmake.in ${CMAKE_CURRENT_BINARY_DIR}/WIMFConfig.cmake
    INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/WIMF)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/WIMFConfig.cmake
              ${CMAKE_CURRENT_BINARY_DIR}/WIMFConfigVersion.cmake
        DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/WIMF)
