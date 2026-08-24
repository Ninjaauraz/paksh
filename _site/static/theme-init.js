// Paper-white only (6.3B.4): the dark-mode toggle was removed from the UI, so this no
// longer applies a remembered choice or the OS preference before first paint - doing so
// would strand a visitor with a dark-mode OS setting in dark mode with no way back, since
// there's no control left to switch away from it. Kept as a file (not inlined) only so
// nothing else needs to change about how index.html loads it.
(function () {})();
