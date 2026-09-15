#pragma once

namespace FloorForge {
// Uruchamia osadzony proces FloorForge (Contents/Resources/FloorForge/FloorForge) z env
// wskazującym port JSON tej instancji AC. Drugie wywołanie przy żyjącym procesie → alert.
void LaunchOrFocus ();
}
