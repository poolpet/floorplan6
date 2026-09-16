#include "AboutDialog.hpp"

#include "AddOnVersion.hpp"
#include "ResourceIds.hpp"
#include "MigrationHelper.hpp"

#include "ACAPinc.h"

AboutDialog::AboutDialog () :
    DG::ModalDialog (ACAPI_GetOwnResModule (), ID_ABOUT_DIALOG, ACAPI_GetOwnResModule ()),
    okButton (GetReference (), 1),
    versionText (GetReference (), 4)
{
    AttachToAllItems (*this);
    Attach (*this);

    // Port bierzemy tylko wtedy, gdy AC faktycznie go oddał. Bez sprawdzenia zwrotu
    // dialog pokazywał „JSON port: 0" — a to dla testera wygląda jak prawdziwy port.
    GS::UShort portNumber = 0;
    GS::UniString portString ("n/a");
    if (ACAPI_Command_GetHttpConnectionPort (&portNumber) == NoError && portNumber != 0) {
        portString = GS::ValueToUniString (portNumber);
    }

    GS::UniString versionTextContent = versionText.GetText ();
    GS::UniString versionTextNewContent = GS::UniString::SPrintf (
        versionTextContent,
        GS::UniString (ADDON_VERSION).ToPrintf (),
        portString.ToPrintf ()
    );
    versionText.SetText (versionTextNewContent);
}

void AboutDialog::ButtonClicked (const DG::ButtonClickEvent& ev)
{
    if (ev.GetSource () == &okButton) {
        PostCloseRequest (DG::ModalDialog::Accept);
    }
}
