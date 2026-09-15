#pragma once

// Wersja wstrzykiwana przez CMake (-DFLOORFORGE_VERSION="v0.7-…"); fallback dla buildów ręcznych.
#ifndef FLOORFORGE_VERSION
#define FLOORFORGE_VERSION "dev"
#endif
#define ADDON_VERSION FLOORFORGE_VERSION
