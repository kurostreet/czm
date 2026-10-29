# Keep the upstream menu submodule pinned and build local branded source copies.
set(CZM_MENU_SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/3rdparty/mainui_cpp")
set(CZM_MENU_OUTPUT_DIR "${CMAKE_CURRENT_BINARY_DIR}/czm-mainui")
execute_process(
    COMMAND "${Python_EXECUTABLE}"
        "${CMAKE_CURRENT_SOURCE_DIR}/scripts/brand_mainui.py"
        "${CZM_MENU_SOURCE_DIR}" "${CZM_MENU_OUTPUT_DIR}"
    RESULT_VARIABLE CZM_MENU_BRANDING_RESULT
)
if(NOT CZM_MENU_BRANDING_RESULT EQUAL 0)
    message(FATAL_ERROR "Could not prepare Counter Zombie Mobile menu sources")
endif()

get_target_property(CZM_MENU_SOURCES menu SOURCES)
foreach(CZM_MENU_FILE BaseMenu.cpp controls/BackgroundBitmap.cpp menus/Main.cpp font/FontManager.cpp
        menus/ServerBrowser.cpp menus/ConnectionProgress.cpp controls/YesNoMessageBox.cpp udll_int.cpp)
    set(CZM_UPSTREAM_MENU_FILE "${CZM_MENU_SOURCE_DIR}/${CZM_MENU_FILE}")
    list(FIND CZM_MENU_SOURCES "${CZM_UPSTREAM_MENU_FILE}" CZM_MENU_SOURCE_INDEX)
    if(CZM_MENU_SOURCE_INDEX EQUAL -1)
        message(FATAL_ERROR "Upstream menu source missing: ${CZM_MENU_FILE}")
    endif()
    list(REMOVE_ITEM CZM_MENU_SOURCES "${CZM_UPSTREAM_MENU_FILE}")
    list(APPEND CZM_MENU_SOURCES "${CZM_MENU_OUTPUT_DIR}/${CZM_MENU_FILE}")
endforeach()
set_property(TARGET menu PROPERTY SOURCES "${CZM_MENU_SOURCES}")

# Counter Zombie Mobile main screen, menu art and loading screen
target_sources(menu PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/czm/menu/CzmMenu.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/czm/menu/CzmMain.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/czm/menu/CzmSettings.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/czm/menu/CzmTouch.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/czm/menu/CzmShop.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/czm/menu/CzmWheels.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/czm/menu/CzmServerMenu.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/czm/menu/CzmServers.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/czm/menu/CzmJson.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/czm/menu/CzmNet.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/czm/menu/CzmOnline.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/czm/menu/CzmTab.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/czm/menu/CzmMapPics.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/czm/menu/CzmChat.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/czm/menu/CzmSocial.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/czm/menu/CzmLobby.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/czm/menu/CzmLobbyInvites.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/czm/menu/CzmNotice.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/czm/menu/CzmRules.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/czm/menu/CzmModeration.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/czm/menu/CzmTop.cpp"
)
# the menu reaches the Android side (CzmNet.java) through SDL's JNIEnv, found with dlopen;
# menu is defined in the mainui directory, linking it from here needs CMP0079
cmake_policy(SET CMP0079 NEW)
target_link_libraries(menu ${CMAKE_DL_LIBS})
target_include_directories(menu PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/czm/menu")

set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/scripts/brand_mainui.py"
    "${CZM_MENU_SOURCE_DIR}/BaseMenu.cpp"
    "${CZM_MENU_SOURCE_DIR}/controls/BackgroundBitmap.cpp"
    "${CZM_MENU_SOURCE_DIR}/menus/Main.cpp"
    "${CZM_MENU_SOURCE_DIR}/font/FontManager.cpp"
    "${CZM_MENU_SOURCE_DIR}/menus/ServerBrowser.cpp"
    "${CZM_MENU_SOURCE_DIR}/menus/ConnectionProgress.cpp"
    "${CZM_MENU_SOURCE_DIR}/udll_int.cpp"
    "${CZM_MENU_SOURCE_DIR}/controls/YesNoMessageBox.cpp"
)
