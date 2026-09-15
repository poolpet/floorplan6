#include "FloorForgeLauncher.hpp"

#include "APIEnvir.h"
#include "ACAPinc.h"
#include "AddOnVersion.hpp"
#include "ResourceIds.hpp"

#include "DGModule.hpp"

#include "Process.hpp"
#include "ProcessException.hpp"
#include "Location.hpp"
#include "UniString.hpp"

#include <cstdlib>
#include <string>

namespace FloorForge {

static GS::Process gProcess;   // ostatni uruchomiony proces (nieważny = nic nie uruchomiono)

static GS::UniString Str (short index)
{
    return RSGetIndString (ID_LAUNCHER_STRINGS, index, ACAPI_GetOwnResModule ());
}

// ACAPI_GetOwnLocation zwraca lokalizację bundla dodatku (…/FloorForge.bundle).
// Asekuracja: gdyby AC zwrócił binarkę (…/FloorForge.bundle/Contents/MacOS/FloorForge),
// cofamy się w górę aż do komponentu kończącego się na ".bundle".
static bool GetBundleLocation (IO::Location& loc)
{
    if (ACAPI_GetOwnLocation (&loc) != NoError) {
        return false;
    }
    for (short level = 0; level < 4; ++level) {
        IO::Name last;
        if (loc.GetLastLocalName (&last) != NoError) {
            return false;
        }
        if (last.ToString ().EndsWith (GS::UniString (".bundle"))) {
            return true;
        }
        if (loc.DeleteLastLocalName () != NoError) {
            return false;
        }
    }
    return false;
}

static bool GetEmbeddedExecutablePath (GS::UniString& outPath)
{
    IO::Location loc;
    if (!GetBundleLocation (loc)) {
        return false;
    }
    loc.AppendToLocal (IO::Name ("Contents"));
    loc.AppendToLocal (IO::Name ("Resources"));
    loc.AppendToLocal (IO::Name ("FloorForge"));
    loc.AppendToLocal (IO::Name ("FloorForge"));
    return loc.ToPath (&outPath) == NoError;
}

static bool IsRunning ()
{
    // IsTerminated() == true → proces już się zakończył; false = nadal działa.
    return gProcess.IsValid () && !gProcess.IsTerminated ();
}

void LaunchOrFocus ()
{
    if (IsRunning ()) {
        DGAlert (DG_INFORMATION, Str (ID_LAUNCHER_ALREADY_RUNNING_TITLE),
                 Str (ID_LAUNCHER_ALREADY_RUNNING_TEXT), GS::EmptyUniString, Str (ID_LAUNCHER_OK_BUTTON));
        return;
    }

    GS::UniString exePath;
    if (!GetEmbeddedExecutablePath (exePath)) {
        DGAlert (DG_ERROR, Str (ID_LAUNCHER_SPAWN_FAILED_TITLE),
                 GS::UniString::Printf (Str (ID_LAUNCHER_SPAWN_FAILED_TEXT), GS::UniString ("(ACAPI_GetOwnLocation)").ToPrintf ()),
                 GS::EmptyUniString, Str (ID_LAUNCHER_OK_BUTTON));
        return;
    }

    UShort port = 0;
    ACAPI_Command_GetHttpConnectionPort (&port);

    // Proces dziedziczy środowisko AC — ustawiamy zmienne przed spawnem (tylko FLOORFORGE_*).
    setenv ("FLOORFORGE_BETA", "1", 1);
    setenv ("FLOORFORGE_VERSION", ADDON_VERSION, 1);
    setenv ("FLOORFORGE_AC_PORT", std::to_string (port).c_str (), 1);
    setenv ("FLOORFORGE_LAUNCHED_FROM_AC", "1", 1);

    try {
        gProcess = GS::Process::Create (exePath, GS::Array<GS::UniString> (), static_cast<GSFlags> (GS::Process::CreateNoWindow));
    } catch (const GS::Exception&) {
        gProcess = GS::Process ();
    }
    if (!gProcess.IsValid ()) {
        DGAlert (DG_ERROR, Str (ID_LAUNCHER_SPAWN_FAILED_TITLE),
                 GS::UniString::Printf (Str (ID_LAUNCHER_SPAWN_FAILED_TEXT), exePath.ToPrintf ()),
                 GS::EmptyUniString, Str (ID_LAUNCHER_OK_BUTTON));
    }
}

} // namespace FloorForge
