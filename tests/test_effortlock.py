"""Reasoning depth is a per-chat, start-of-chat decision.

The dial used to be a segmented pill in the composer, changeable between any
two messages of the same conversation. That produced transcripts half reasoned
one way and half the other with nothing on screen to say which reply came from
which. It now lives in Settings, is latched on to the chat at its first
message, and cannot move until a new chat is started."""
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
    return _SRC[i:_SRC.index(end, i + len(sig))]

print("\n== the composer no longer carries the dial ==")
ck("the effort pill widget is gone",
   "self.effort_pill = Gtk.Box" not in _SRC,
   "a reasoning dial one click from the text box invites mid-conversation "
   "changes")
ck("its per-segment buttons are gone", "self._effort_btns[" not in _SRC)
ck("its click handler is gone", "def _on_effort_pick" not in _SRC)
ck("nothing still tries to pack it", "actions.append(self.effort_pill)" not in _SRC)

print("\n== Settings owns it now ==")
ck("there is a reasoning-depth row", "self.effort_row = Adw.ComboRow()" in _SRC)
ck("it is titled for what it does", 'set_title("Reasoning depth")' in _SRC)
_sync = body("    def _sync_effort_row(self, parent):")
ck("the row hides for models without the dial",
   "supports_reasoning_effort(parent._active_model_id())" in _sync,
   "showing a dial that does nothing is worse than showing none")
ck("the row goes insensitive once the chat has started",
   "row.set_sensitive(not locked)" in _sync)
ck("and says why it is locked", "Locked for this chat" in _sync)
ck("and says how to change it", "Start a new chat" in _sync)
_set = body("    def _set_effort(self, level):")
ck("a locked row refuses the write even if driven from code",
   "_effort_locked()" in _set and "return" in _set,
   "an insensitive widget is a UI hint, not an invariant")

print("\n== the latch ==")
_lat = body("    def _latch_effort(self, chat_id):")
ck("latching is once per chat", "if str(chat_id) in m:" in _lat)
ck("it persists", "save_settings(self.settings)" in _lat,
   "a chat reopened after a relaunch has to keep the depth it ran at")
_send = _SRC[_SRC.index("    def _send_user_message(self):"):]
_send = _send[:_send.index("\n    def ", 10)]
ck("the first message of a chat latches the depth",
   "self._latch_effort(cid)" in _send)
ck("it latches BEFORE the message is stored",
   _send.index("_latch_effort(cid)") < _send.index('add_message(cid, "user"'),
   "_effort_locked counts messages, so storing first would lock the chat "
   "before its level was read")

_eff = body("    def _effective_effort(self)")
ck("a started chat reports its latched level",
   "_chat_effort_map().get(str(cid))" in _eff)
ck("an unstarted chat falls back to the settings default",
   'self.settings.get("reasoning_effort"' in _eff)
_lock = body("    def _effort_locked(self)")
ck("a chat with no messages is still choosable",
   "count_messages(cid) > 0" in _lock)

_load = body("    def _load_chat(self, chat_id: int):")
ck("opening a chat points the backend dial at that chat's level",
   "_apply_chat_effort(chat_id)" in _load,
   "otherwise reopening a HIGH chat silently runs it at whatever the last "
   "chat used")
ck("deleting a chat drops its latched level",
   _SRC.count("_forget_chat_effort(") >= 3)

print(f"\neffort lock: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
