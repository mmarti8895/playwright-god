// Prevents an additional console window on Windows release builds. Does
// nothing on macOS / Linux.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    playwright_god_desktop_lib::run();
}
