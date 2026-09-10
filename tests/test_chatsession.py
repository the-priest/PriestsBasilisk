"""Per-chat session isolation: the state that must not follow the operator
from one chat into another."""
import io, os, re, sys
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = io.open(os.path.join(_ROOT, "basilisk.py"), encoding="utf-8").read()

_p = _f = 0
def ck(name, cond, why=""):
    global _p, _f
    if cond: _p += 1; print("  PASS", name)
    else:    _f += 1; print("  FAIL", name, "--", why)

def body(sig, end="\n    def "):
    i = _SRC.index(sig)
    j = _SRC.index(end, i + len(sig))
    return _SRC[i:j]

print("\n== each chat carries its own session ==")
ck("the session field table exists", "_SESSION_FIELDS = (" in _SRC)
_tbl = _SRC[_SRC.index("_SESSION_FIELDS = ("):_SRC.index(")\n\n    def _session_defaults")]
for f in ("_unleashed", "_mission_active", "_mission_objective",
          "_tool_chain_depth", "_recent_commands", "_error_retries",
          "_bad_propose_retries", "_tools_locked"):
    ck(f"{f} is per-chat", f'"{f}"' in _tbl,
       "a window-global copy is what leaked the previous chat's session")

ck("Unleash starts stood down on a new chat",
   '("_unleashed",                 False),' in _tbl,
   "arming is a decision about one engagement, not about the app")
ck("Unleash is no longer restored from settings at startup",
   'self.settings.get("unleashed"' not in _SRC,
   "a saved global meant a relaunch came up armed with no chat in front of it")

print("\n== switching chats ends the run it belonged to ==")
_sw = body("    def _switch_session(self, new_chat_id):")
ck("the switch stops an in-flight turn", "self._request_stop()" in _sw,
   "otherwise the previous chat's turn keeps streaming after you leave it")
ck("it snapshots the chat being left", "_session_snapshot()" in _sw)
ck("it restores the chat being entered", "_session_restore(" in _sw)
ck("a chat with no saved session starts from the defaults",
   "_session_defaults()" in _sw)
ck("a no-op switch does nothing", "if prev == new_chat_id:" in _sw)

_lc = body("    def _load_chat(self, chat_id: int):")
ck("_load_chat swaps sessions before it touches the message list",
   _lc.index("_switch_session") < _lc.index("self.msg_box"),
   "the stop path still holds streaming_msg_widget, which the clear-out "
   "unparents")

print("\n== the snapshot cannot alias the live containers ==")
_sn = body("    def _session_snapshot(self)")
ck("lists are copied", "val = list(val)" in _sn,
   "handing over the live list lets the next chat append into the last "
   "chat's loop history")
ck("sets are copied", "frozenset(val)" in _sn)

print("\n== redrawing a session is not arming it ==")
_re_ = body("    def _session_restore(self, state: Dict[str, Any]):")
ck("the restore guards the toggle handlers", "_restoring_session = True" in _re_)
ck("and always clears the guard", "finally:" in _re_)
_ut = body("    def _on_unleash_toggled(self, btn):")
ck("the Unleash handler bails out during a restore",
   "if self._restoring_session:" in _ut,
   "set_active() fires it, and it toasts, saves and stands missions down")
ck("painting the button is separate from arming it",
   "def _paint_unleash" in _SRC and "self._paint_unleash(btn" in _ut)
ck("arming still does not kick a turn",
   "_kick_assistant_turn()" not in _ut)
ck("arming still does not latch a mission from stale history",
   "_mission_active = True" not in _ut)

print("\n== deleted chats do not leave sessions behind ==")
ck("delete drops the session", _SRC.count("_forget_session(") >= 3)

print(f"\nsession: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
