#pragma once

#ifdef _WIN32
#include <Windows.h>
#include <Shlwapi.h>
#include <string.h>

// no unicode!
inline bool get_dll_path (char *res)
{
    WCHAR path[MAX_PATH];
    HMODULE hm;
    if (GetModuleHandleExW (
            GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
            (LPWSTR)&get_dll_path, &hm))
    {
        GetModuleFileNameW (hm, path, sizeof (path));
        PathRemoveFileSpecW (path);
        
        // Convert wide string to narrow string
        int len = WideCharToMultiByte(CP_UTF8, 0, path, -1, NULL, 0, NULL, NULL);
        if (len > 0) {
            WideCharToMultiByte(CP_UTF8, 0, path, -1, res, len, NULL, NULL);
            // Ensure path ends with backslash
            if (res[len-2] != '\\') {
                res[len-1] = '\\';
                res[len] = '\0';
            }
            return true;
        }
    }
    return false;
}

#else
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <dlfcn.h>
#include <string.h>
#include <string>

inline bool get_dll_path (char *res)
{
    Dl_info dl_info;
    if (dladdr ((void *)get_dll_path, &dl_info))
    {
        std::string full_path = dl_info.dli_fname;
        std::string dir_path = full_path.substr (0, full_path.find_last_of ("/") + 1);
        strcpy (res, dir_path.c_str ());
        return true;
    }
    return false;
}
#endif
