"""Keyboard and focus behaviour: the desktop-app basics this app was missing.

Five window actions were registered with no accelerator, "new chat" was a
click handler on the wordmark rather than an action at all, and Escape was
bound inside the composer's own key controller - so the stop key worked only
while the cursor happened to be in the text box."""
import io, os, sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = io.open(os.path.join(_ROOT, "basilisk.py"), encoding="utf-8").read()

_p = _f = 0
def ck(name, cond, why=""):
    global _p, _f
    if cond: _p += 1; print("  PASS", name)
    else:    _f += 1; print("  FAIL", name, "--", why)

def body(sig, end="\n    def "):
    i = _SRC.index(sig)
    return _SRC[i:_SRC.index(end, i + len(sig))]

print("\n== the actions exist ==")
_wa = body("    def _wire_actions(self):", "\n    # ")
for a in ("new-chat", "focus-composer", "toggle-sidebar", "stop",
          "settings", "rename-chat", "delete-chat", "pin-chat"):
    ck(f'"{a}" is an action', f'add("{a}"' in _wa)

print("\n== and they have the standard bindings ==")
_tbl = _SRC[_SRC.index("_ACCELS = ("):_SRC.index(")\n\n    def _wire_shortcuts")]
for action, key in (("new-chat", "<Primary>n"),
                    ("settings", "<Primary>comma"),
                    ("focus-composer", "<Primary>l"),
                    ("toggle-sidebar", "F9"),
                    ("rename-chat", "F2")):
    ck(f"{action} -> {key}", f'"win.{action}"' in _tbl and f'"{key}"' in _tbl)
ck("Escape is NOT an application accelerator",
   '"win.stop"' not in _tbl,
   "an app accel swallows Escape before dialogs get it, so Escape would "
   "stop a turn instead of closing the Settings dialog on top of it")

print("\n== they still work with no window manager ==")
_wk = body("    def _on_window_key(self, controller, keyval, keycode, state):")
ck("the window handles the same combos itself", "Gdk.KEY_F9" in _wk
   and "Gdk.KEY_n" in _wk and "Gdk.KEY_comma" in _wk and "Gdk.KEY_F2" in _wk,
   "GtkApplication only dispatches accelerators to the ACTIVE window, which "
   "on X11 needs a WM focus-in; without one every binding is dead")
ck("Escape stops a running turn from anywhere", "Gdk.KEY_Escape" in _wk
   and "_request_stop()" in _wk)
ck("Escape when idle is passed on, not swallowed",
   "if self._is_busy():" in _wk and "return False" in _wk,
   "a stop key that sometimes closes the window is a stop key nobody "
   "will press during a long job")
_ctrl = body("    def _wire_shortcuts(self):")
ck("the fallback controller is BUBBLE phase",
   "Gtk.PropagationPhase.BUBBLE" in _ctrl,
   "CAPTURE would take Escape from dialogs and Ctrl+A from the composer")

print("\n== focus goes where typing goes ==")
ck("the composer is focused at launch",
   "GLib.idle_add(self._focus_composer)" in _SRC)
_lc = body("    def _load_chat(self, chat_id: int):")
ck("and again after opening a chat", "_focus_composer" in _lc,
   "selecting a sidebar row left focus on the row, so the next thing "
   "typed went nowhere")

print("\n== the window names the open chat ==")
ck("the title follows the chat", 'self.set_title(f"{chat.title} - {APP_NAME}")' in _SRC,
   "alt-tab and the taskbar showed the same word for every conversation")
ck("and follows an auto-title too",
   'self.set_title(f"{title} - {APP_NAME}")' in _SRC)

print(f"\nshortcuts: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
