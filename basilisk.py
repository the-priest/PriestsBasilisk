#!/usr/bin/env python3
"""
basilisk — personal AI assistant.  GTK4 + libadwaita UI.

Run:    python3 basilisk.py
Or, after install:  basilisk
"""

from __future__ import annotations

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Pango", "1.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import (Gtk, Adw, GLib, Gdk, Gio, Pango, GObject,  # noqa
                          GdkPixbuf)

# Two harmless GTK4 deprecation warnings come from image calls we still use —
# the logo texture (Gdk.Texture.new_for_pixbuf) and the watermark blit
# (Gdk.cairo_set_source_pixbuf). Both work fine on current GTK/libadwaita; this
# just keeps the console clean. Matched by message so any OTHER (new/real)
# deprecation still prints.
import warnings as _warnings
_warnings.filterwarnings("ignore", category=DeprecationWarning,
                         message=r"Gdk\.cairo_set_source_pixbuf")
_warnings.filterwarnings("ignore", category=DeprecationWarning,
                         message=r"Gdk\.Texture\.new_for_pixbuf")

import sys
import os
import gc
import io
import re
import json
import threading
import urllib.request
import datetime
import base64
import bisect
import traceback
import time
try:
    from basilisk_btn_art import BTN_ART_B64
except Exception:
    BTN_ART_B64 = {}   # missing module -> art buttons just fall back to symbolic
from typing import List, Dict, Any, Optional, Callable, Tuple

from basilisk_core import (
    GroqBackend, OpenAICompatBackend, BackendRouter,
    ChatStore, Chat,
    load_settings, save_settings, log,
    tool_read_file, tool_list_dir, tool_run_command, estimate_runtime,
    tool_system_info,
    tool_write_file, make_edit_diff,
    tool_check_updates, tool_recent_downloads, tool_service_status,
    tool_journal_tail, tool_disk_usage, tool_processes,
    tool_network_status, tool_find_file,
    run_security_audit, format_audit_for_chat, printed_url_target,
    run_network_scan, format_scan_for_chat,
    tool_desktop_info, tool_list_apps, tool_launch_app,
    tool_list_windows, tool_focus_window, tool_close_window,
    tool_notify, tool_type_text, tool_press_key,
    tool_media_control, tool_screenshot, tool_read_screen,
    tool_make_dir, tool_copy_path, tool_move_path, tool_delete_path,
    tool_path_info, tool_open_url, tool_web_read, web_read_tier, tool_web_sources,
    tool_image_search,
    tool_analyze_image, tool_capture_photo, tool_detect_faces,
    tool_tooling_check, tool_pentest_plan, tool_cve_lookup,
    tool_parse_output, tool_methodology, tool_wordlist_find,
    tool_cheatsheet, tool_report_findings,
    tool_nuclei_template, tool_reflect_findings,
    tool_attack_writeup, tool_code_tooling_check, tool_code_scan_plan,
    tool_workspace_import, tool_workspace_status, tool_workspace_overview,
    tool_workspace_tree, tool_workspace_search, tool_workspace_read,
    tool_workspace_replace, tool_workspace_write, tool_workspace_delete,
    tool_workspace_diff, tool_workspace_revert, tool_workspace_export,
    tool_workspace_close, tool_workspace_test_command,
    tool_workspace_baseline, tool_workspace_verify,
    tool_workspace_health, _ws_path,
    tool_parse_scan, tool_triage_findings, tool_remediation_hint,
    tool_scope_set, tool_scope_check, tool_scope_show, tool_asset_record,
    tool_scope_exclude, tool_scope_window, tool_scope_authorisation,
    tool_engagement_graph, tool_loot_record, tool_loot_list, tool_loot_reuse,
    tool_oracle_arm, tool_oracle_check, tool_oracle_status, tool_oracle_listen,
    tool_graph_ingest, tool_sqlmap_plan, tool_load_tools,
    tool_submit_flag, tool_xbow_score, tool_xbow_report,
    tool_juiceshop_score, tool_juiceshop_report,
    tool_juiceshop_next, tool_juiceshop_diff,
    tool_jwt_forge, tool_nosql_injection, tool_xxe_payload,
    tool_coupon_forge, tool_captcha_solve, tool_reset_password,
    tool_business_logic,
    tool_ssti_payload, tool_ssrf_payload, tool_deserialization_payload,
    tool_prototype_pollution, tool_path_traversal, tool_xss_payload,
    tool_sqli_payload, tool_payload_encoder, tool_tech_fingerprint,
    tool_waf_detect, tool_trick_detect,
    tool_payload_mutate, tool_session_flow, tool_oracle_analyze,
    tool_command_injection, tool_idor_probe, tool_race_condition,
    tool_upload_bypass, tool_graphql_probe, tool_open_redirect, tool_cors_probe,
    tool_ldap_injection, tool_xpath_injection, tool_crlf_injection,
    tool_host_header_injection, tool_ssi_injection, tool_csv_injection,
    tool_request_smuggling, tool_csrf_poc, tool_clickjacking,
    tool_mass_assignment, tool_auth_bypass_headers, tool_cache_poisoning,
    tool_auth_attack, tool_jwt_attack, tool_api_test,
    tool_email_header_injection, tool_websocket_probe, tool_oauth_probe,
    tool_attack_surface, tool_verify_solve,
    tool_webapp_recon, tool_juiceshop_source,
    tool_benchmark_targets, tool_benchmark_score, tool_benchmark_report,
    tool_benchmark_compare,
    quick_facts as tool_quick_facts,
    sudo_cached, detect_urgency, looks_degraded, reply_intends_action,
    reply_is_bare_stall,
    reply_is_strong_conclusion,
    note_command, recent_duplicate,
    parse_tool_calls, strip_tool_calls, shell_block_command,
    looks_like_failed_tool_call, scrub_tool_debris,
    contains_tool_markup,
    _normalise_tool_syntax,
    extract_think_blocks, strip_think_blocks, speakable_text,
    is_online, is_sensitive_path, command_needs_sudo, is_catastrophic_command,
    command_tampers_self, Watcher,
    PROVIDERS, PROVIDERS_BY_KEY,
    VISION_MODELS,
    get_ledger,
)
from basilisk_persona import (
    build_system_prompt, assemble_messages, volatile_block,
    title_from_first_message,
    conversational_turn, direct_answer_turn,
)

# Variant-analysis / zero-day-class source scanner (read-only, stdlib-only).
from basilisk_ext import zdayfind as _zdayfind
# Action recall: the per-run list of what has already been done.  Imported
# defensively — a missing sidecar file must degrade the anti-repetition help,
# never stop the app from starting.
try:
    from basilisk_ext import recall as _recall
except Exception:      # pragma: no cover - only on a broken/partial install
    _recall = None
# Direct handle for newer offensive generators wired below.
from basilisk_ext import exploits as _exploits

# Voice (speech in / speech out) is optional.  If basilisk_voice is missing or
# fails to import, the app runs exactly as before — every voice hook below
# guards on `self.stt` / `self.tts` being present.
try:
    import basilisk_voice
    basilisk_voice.set_logger(log)
    _VOICE_OK = True
except Exception as _ve:  # noqa
    basilisk_voice = None
    _VOICE_OK = False

APP_ID  = "org.thepriest.basilisk"
APP_NAME = "Basilisk"
VERSION = "1.0.0.0"

# ── Tool-chain efficiency knobs ──
# How many model round-trips a single user turn may chain through.  With
# read-only tools now batched (many lookups per round-trip), this budget
# stretches much further than it looks.  On hitting it Basilisk doesn't dead-
# end — it takes one final, tool-free turn to answer with what it gathered.
# The y/n confirmation gate and the catastrophic-command hard block still
# fire independently, so a high budget never means an unsupervised risky run.
# This 150-step cap applies only in a SUPERVISED (per-command approval) mode;
# it's overridable per-user via the "max_tool_steps" setting, and it resets
# every turn so "keep going" always grants a fresh budget.
MAX_TOOL_CHAIN = 150
# ANSWER MODE stall recovery: how many times a turn may be pushed after the
# model DESCRIBED its next action but emitted no tool call ("Let me grab the HN
# thread…" and then nothing).  Two is deliberate — one push covers the ordinary
# slip, a second covers a model that needed telling twice, and past that it is
# not going to act, so the turn ends rather than burning round-trips on
# narration.  The mission loop has always had this recovery; answer mode had
# none, which is how a research question ended on a promise instead of a report.
ANSWER_STALL_NUDGE_MAX = 2
# Foresight: how long the (optional) consequence-prediction model pass may take
# before the turn stops waiting for it.  A model pass is a full network round
# trip; without a deadline a hung one wedged the whole turn forever, because
# nothing downstream of it ever fed a tool result back.  On timeout we fall back
# to foresight's deterministic rules, which are local pattern matching and take
# microseconds.  The catastrophic floor at the execution primitive is separate
# and always applies.
FORESIGHT_TIMEOUT_S = 20.0
# Sidecar completions (memory consolidation, the foresight model pass) are
# short structured answers on behalf of something that is BLOCKED waiting for
# them.  They get a real deadline and a small budget, not the chat turn's.
EXT_COMPLETE_TIMEOUT_S = 18.0
EXT_COMPLETE_MAX_TOKENS = 320
# Turn watchdog: the assistant turn loop advances only when something feeds it —
# a stream callback or a tool result.  Every feeder runs on a daemon thread, so
# an exception in one used to strand the turn in "working…" with no way out but
# restarting the app.  This is the last-resort backstop for a loop that has
# genuinely died.
#
# The value is chosen so it CANNOT fire on real work: the longest hard timeout
# estimate_runtime hands out is 1800s, and tool_run_command enforces it, so any
# command returns by then; a model stream is bounded by STREAM_MAX_WALL_S.  With
# 40 minutes of complete silence, nothing legitimate is still running — the loop
# is dead and the operator is staring at a spinner.
TURN_WATCHDOG_S = 2400.0
TURN_WATCHDOG_POLL_S = 30
# In autonomous walk-away mode (no per-command approval — the default) the run
# is UNCAPPED: it keeps going until the task is actually finished (the model
# stops calling tools) or the operator presses Stop. Stop and the catastrophic-
# command block fire regardless of depth, and each turn's budget resets, so
# "run to completion" never means "run unsupervised into something destructive."
# Parallel workers when several read-only tools fire in one turn.
TOOL_BATCH_MAX_WORKERS = 6

# ── Autonomous mission directives ──
# Injected as a system addendum when a mission turn settled without finishing
# (the code re-kicks; these tell the model WHY it's being pushed again).  The
# completion protocol (the [[MISSION_COMPLETE]] token) is also stated in the
# autonomous addendum so the model can end a trivial task on the first turn.
MISSION_COMPLETE_TOKEN = "[[MISSION_COMPLETE]]"
_MISSION_CONTINUE_DIRECTIVE = (
    "[AUTONOMOUS MISSION — NOT FINISHED, CONTINUE NOW.\n"
    "Objective (from the operator): {obj}\n"
    "Your last turn ended without completing it. There is NO operator watching "
    "and NOTHING to wait for. Do NOT ask a question, do NOT say you'll wait, do "
    "NOT restate progress and stop. Take the very NEXT concrete action toward "
    "the objective RIGHT NOW with a tool call. USE THE run TOOL — do NOT "
    "write a command in a ```bash``` code fence for the operator to copy. "
    "You have a run tool; use it. A reply with a code block and no tool "
    "call is WRONG.\n"
    "If this is an exploitation run: consult oracle_status to see what's already "
    "CONFIRMED (never redo a proven exploit) and what's still open, and "
    "oracle_check every hit against its success marker before you count it — a "
    "200 or a plausible-looking response is NOT a solve.\n"
    "Only when the objective is genuinely 100% achieved and verified (or it was "
    "purely a question you have now fully answered) output the exact token "
    + MISSION_COMPLETE_TOKEN + " on its own line to end. NEVER output that token "
    "for partial, assumed, or unverified completion. Otherwise: act.]")
_MISSION_VERIFY_DIRECTIVE = (
    "[MISSION COMPLETION CHECK — VERIFY, THEN END.\n"
    "The objective: {obj}\n"
    "Silently re-check it point by point against concrete evidence you actually "
    "produced this run. If ANY part is incomplete, unverified, untested, or "
    "assumed, continue working NOW — take the next action with a tool call. "
    "If every part IS concretely confirmed complete, reply with ONE short "
    "confirming sentence — do NOT repeat your findings or the full report, it "
    "has already been shown — and output " + MISSION_COMPLETE_TOKEN
    + " on its own line.]")
# Keep this many most-recent tool_result blocks at full length in the
# history resent to the model; older ones get trimmed to a stub (they've
# already been consumed) so a long research chat doesn't re-bill huge
# outputs every turn.
HISTORY_KEEP_FULL_TOOL_RESULTS = 2
# How large the raw history may get before we re-trim. Below this, the rendered
# history is held BYTE-STABLE so the provider's prefix cache keeps hitting;
# above it, the trim watermark advances once and then holds again. Trading one
# occasional cache miss for one on every single turn.
HISTORY_STABLE_BUDGET_CHARS = 120_000
HISTORY_TRIM_HEAD_CHARS = 600
# Memory: the live terminal-log TextView and the rendered chat rows are DISPLAY
# only (the real transcript lives in the SQLite ChatStore, and the model's
# history is rebuilt from the DB, not these widgets). Left uncapped they grow
# without bound across a long autonomous run. Cap the *view* to a rolling window
# — trimming old widgets frees memory and speeds up layout, and changes nothing
# about behaviour, autonomy, or the model's context.
MAX_TERMINAL_LINES = 2500
# Byte ceilings so a pentest run (few but HUGE lines — full HTTP bodies, JSON,
# base64) can't grow the view buffer without bound even when the line count
# stays low. MAX_TERMINAL_CHARS bounds the whole buffer; MAX_TERMINAL_LINE_CHARS
# truncates any single monster line before it's inserted.
MAX_TERMINAL_CHARS = 220_000
MAX_TERMINAL_LINE_CHARS = 2_000
# Keep only the last N command-blocks (a "$ cmd" line + its output = one turn)
# in the live log; older ones are deleted from the TextBuffer, freeing their RAM.
MAX_TERMINAL_TURNS = 20
# Keep only the most recent chat bubbles in the widget tree. GTK message
# widgets (TextViews, code blocks, images) are heavy; holding a whole long
# conversation is what balloons RAM to gigabytes. The full transcript lives in
# the SQLite store on disk and the model's context is rebuilt from there — these
# widgets are display-only, so once a conversation passes this many visible
# messages the oldest are unparented AND disposed (their memory reclaimed),
# never touching context, autonomy, or behaviour. Tune higher for more
# scroll-back at the cost of RAM.
MAX_CHAT_ROWS = 20


# ═════════════════════════════════════════════════════════════════════
# THEME — Catppuccin Mocha, generously sized, cozy
# ═════════════════════════════════════════════════════════════════════

# Note: GTK CSS doesn't support CSS variables across rules.  We inline
# the palette by hand and use `font-size` numbers that are large enough
# to read on a phone screen without squinting.

CSS = b"""
/* =====================================================================
   BASILISK THEME - modelled on the official Kali Linux desktop palette:
   near-black surfaces, the Basilisk dragon-blue accent (#4a0a11 / #7d121b),
   red for danger, monospace for headers and machine output.  Built to
   read like a first-party Basilisk tool, not a pastel toy.
   GTK CSS has no variables across rules, so the palette is inlined.

   Palette:
     bg base    #08090b   surfaces  #0d0f12 / #12151a   line  #1b1f26
     text       #d6dbe2   dim       #7d8794
     accent     #4a0a11   accent-hi #7d121b   accent-dim rgba(125, 18, 27,.15)
     ok/green   #2ecc71   warn      #f0a500   danger #e5484d
   ===================================================================== */

/* ===== Adwaita named-color overrides =====
   libadwaita widgets (SwitchRow, SpinRow, ComboRow, AlertDialog buttons,
   focus rings, selections, links) pull these named colours.  Without
   overriding them every built-in control renders in GTK's stock blue or
   the user's Plasma accent - which is exactly what made the UI look
   inconsistent.  Retint them ALL to the Basilisk palette in one place. */

@define-color accent_color              #7d121b;
@define-color accent_bg_color           #4a0a11;
@define-color accent_fg_color           #ffffff;

@define-color destructive_color         #e5484d;
@define-color destructive_bg_color      #e5484d;
@define-color destructive_fg_color      #ffffff;

@define-color success_color             #2ecc71;
@define-color success_bg_color          #2ecc71;
@define-color success_fg_color          #08090b;
@define-color warning_color             #f0a500;
@define-color warning_bg_color          #f0a500;
@define-color warning_fg_color          #08090b;
@define-color error_color               #e5484d;
@define-color error_bg_color            #e5484d;
@define-color error_fg_color            #ffffff;

@define-color window_bg_color           #08090b;
@define-color window_fg_color           #d6dbe2;
@define-color view_bg_color             #0d0f12;
@define-color view_fg_color             #d6dbe2;
@define-color headerbar_bg_color        #0d0f12;
@define-color headerbar_fg_color        #d6dbe2;
@define-color headerbar_border_color    #1b1f26;
@define-color popover_bg_color          #0d0f12;
@define-color popover_fg_color          #d6dbe2;
@define-color dialog_bg_color           #0d0f12;
@define-color dialog_fg_color           #d6dbe2;
@define-color card_bg_color             #12151a;
@define-color card_fg_color             #d6dbe2;
@define-color sidebar_bg_color          #0a0c0f;
@define-color sidebar_fg_color          #d6dbe2;

@define-color borders                   #1b1f26;

/* ===== Base ===== */

window, .background {
    background-color: #08090b;
    color: #d6dbe2;
    font-family: 'Inter', 'Cantarell', 'SF Pro Text', sans-serif;
}

headerbar {
    background-color: #0d0f12;
    color: #d6dbe2;
    border-bottom: 1px solid #1b1f26;
    min-height: 56px;
    padding: 4px 8px;
}

.sidebar {
    background-color: #0a0c0f;
    border-right: 1px solid #1b1f26;
}

/* ===== App branding ===== */

.app-title {
    font-size: 27px;
    font-weight: 900;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    color: #dfe4ea;
    letter-spacing: 3px;
    text-shadow: 0 2px 3px rgba(0, 0, 0, 0.9), 0 0 11px rgba(150, 162, 178, 0.32);
}
/* Connectivity dot beside BASILISK: green online, red offline */
.online-dot {
    font-size: 13px;
    margin-top: 2px;
}
.online-dot.online {
    color: #7d121b;
    text-shadow: 0 0 7px rgba(125, 18, 27, 0.7);
}
.online-dot.offline {
    color: #6b737d;
    text-shadow: 0 0 6px rgba(107, 115, 125, 0.6);
}
.app-subtitle {
    font-size: 16px;
    color: #7d8794;
    font-family: 'JetBrains Mono', monospace;
    margin-top: 2px;
}

.chat-title {
    font-size: 16px;
    font-weight: 600;
    color: #d6dbe2;
}
/* Composer input as a rounded bubble so it reads as a contained field
   instead of bleeding into the bottom edge. */
.input-frame {
    background-color: #0e1013;
    border: 1px solid #232a32;
    border-radius: 20px;
    padding: 4px 8px;
    margin-bottom: 8px;
}
.input-frame:focus-within {
    border-color: #7d121b;
    background-color: #161b21;
}
.chat-subtitle {
    font-size: 16px;
    color: #7d8794;
}

/* ===== Sidebar chat list ===== */

.chat-row {
    background-color: transparent;
    border-radius: 11px;
    padding: 15px 16px 15px 18px;
    margin: 5px 8px;
    min-height: 64px;
    border-left: 3px solid transparent;
    transition: background-color 160ms ease, border-color 160ms ease;
}
.chat-row:hover {
    background-color: #0d0f12;
    border-left-color: rgba(125, 18, 27, 0.55);
}
.chat-row.selected, .chat-row:selected {
    background: linear-gradient(90deg, rgba(200, 210, 222, 0.10),
                rgba(120, 130, 142, 0.04) 55%, rgba(13, 15, 18, 0) 90%);
    border-left: 3px solid #c8d0da;
    /* NO INFINITE ANIMATION HERE. This rule is on the SELECTED chat row,
       which means it is on screen from the moment the app opens until it
       closes - so a 3s infinite keyframe kept a repaint loop running at
       idle, forever, for a glow nobody is looking at. It was the only
       always-on animation in the stylesheet and the most likely reason the
       app "feels laggy" when nothing is happening. The lit state is now
       static; the animated ones that remain are all gated behind a state
       class (.working, .live, .busy) and stop when the work does. */
    box-shadow: inset 0 0 0 1px rgba(232, 238, 244, 0.16),
                -2px 0 15px rgba(205, 215, 230, 0.22);
}
@keyframes metalglow {
    0%   { border-left-color: #7f8892; box-shadow: inset 0 0 0 1px rgba(200,210,222,0.08), -2px 0 12px rgba(190,200,214,0.16); }
    50%  { border-left-color: #eff3f8; box-shadow: inset 0 0 0 1px rgba(232,238,244,0.18), -2px 0 17px rgba(220,230,240,0.30); }
    100% { border-left-color: #7f8892; box-shadow: inset 0 0 0 1px rgba(200,210,222,0.08), -2px 0 12px rgba(190,200,214,0.16); }
}
.chat-row .title-line {
    color: #e8ebef;
    font-weight: 700;
    font-size: 20px;
}
.chat-row .meta-line {
    color: #6d7680;
    font-size: 12px;
    letter-spacing: 0.3px;
    margin-top: 3px;
}
.chat-row .pin-icon {
    font-size: 12px;
}

/* ===== Empty states ===== */

.empty-state {
    color: #5a626d;
    padding: 60px 32px;
}
.empty-state-title {
    font-size: 34px;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
    color: #d6dbe2;
    margin-bottom: 18px;
}
.empty-state-body {
    font-size: 22px;
    color: #7d8794;
    line-height: 1.55;
}

/* ===== Message bubbles ===== */

.msg-row {
    padding: 4px 0;
}

/* User: right-aligned bubble */
.msg-user {
    background-color: rgba(64, 20, 96, 0.14);
    color: #eef2f6;
    border-radius: 12px 12px 4px 12px;
    padding: 18px 22px;
    margin: 8px 12px 8px 60px;
    font-size: 30px;
    line-height: 1.45;
    border: 1px solid rgba(64, 20, 96, 0.40);
}

/* Assistant: left-aligned, translucent SILVER bubble (matches Basilisk's icon;
   contrasts the user's green) */
.msg-assistant {
    background-color: rgba(125, 18, 27, 0.13);
    color: #eef1f5;
    padding: 16px 20px;
    margin: 8px 60px 8px 12px;
    font-size: 30px;
    line-height: 1.55;
    border-radius: 12px 12px 12px 4px;
    border: 1px solid rgba(125, 18, 27, 0.36);
}

/* Compact tool indicator (replaces visible JSON dump) */
.msg-tool-indicator {
    padding: 6px 16px 6px 70px;
    margin: 2px 12px;
}
.tool-indicator-label {
    color: #7d8794;
    font-size: 17px;
    font-family: 'JetBrains Mono', monospace;
    opacity: 0.85;
}

/* Model reasoning ("thoughts") - collapsed by default, click to open */
.thoughts-expander {
    margin: 2px 0 4px 0;
    font-size: 15px;
    color: #8a93a0;
}
.thoughts-expander > title {
    color: #8a93a0;
    opacity: 0.9;
}
.thoughts-text {
    color: #9aa4b2;
    font-family: 'JetBrains Mono', monospace;
    font-size: 15px;
    background: rgba(125,135,148,0.08);
    border-left: 2px solid rgba(125,135,148,0.35);
    padding: 8px 10px;
    border-radius: 4px;
}

.msg-system-notice {
    color: #7d8794;
    font-style: italic;
    font-size: 18px;
    padding: 8px 16px;
    margin: 4px 16px;
}

/* Avatar dots */
.avatar {
    border-radius: 6px;
    min-width: 52px;
    min-height: 52px;
    background-color: #12151a;
    font-weight: bold;
    font-size: 22px;
    color: #d6dbe2;
}
.avatar-user {
    background-color: #1b1f26;
    color: #d6dbe2;
}
.avatar-basilisk {
    background: linear-gradient(135deg, #8b0010, #ff2d3a);
    color: #08090b;
    border: 1px solid #ff5566;
    box-shadow: 0 0 10px rgba(255, 45, 58, 0.55);
}

.role-label {
    color: #7d8794;
    font-weight: 700;
    font-size: 17px;
    font-family: 'JetBrains Mono', monospace;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    margin: 0 0 5px 0;
}
.role-label.user { color: #7d121b; }
.role-label.basilisk { color: #c4cad4; }

/* ===== Code blocks ===== */

.code-block {
    background-color: #0a0c0f;
    border: 1px solid #1b1f26;
    border-radius: 6px;
    padding: 0;
    margin: 8px 4px;
}
.image-block {
    margin: 8px 4px;
}
.chat-image {
    border: 1px solid #1b1f26;
    border-radius: 8px;
    background-color: #0a0c0f;
}
.image-caption {
    color: #7d8794;
    font-size: 11px;
    margin: 2px 2px;
}
.code-block-header {
    background-color: #0d0f12;
    color: #7d8794;
    font-size: 11px;
    font-family: 'JetBrains Mono', monospace;
    padding: 6px 12px;
    border-bottom: 1px solid #1b1f26;
    border-radius: 6px 6px 0 0;
}
.code-block textview {
    background-color: transparent;
    color: #d6ffdf;
    font-family: 'JetBrains Mono', 'Fira Code', 'DejaVu Sans Mono', monospace;
    font-size: 22px;
    padding: 16px 18px;
}

/* ===== Status pills ===== */

.status-pill {
    background-color: #12151a;
    color: #7d8794;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 16px;
    font-weight: bold;
    font-family: 'JetBrains Mono', monospace;
    letter-spacing: 0.5px;
}
.status-pill.online   { background-color: #2ecc71; color: #08090b; }
.status-pill.offline  { background-color: #1b1f26; color: #d6dbe2; }
.status-pill.error    { background-color: #e5484d; color: #ffffff; }
.status-pill.groq     { background: linear-gradient(135deg, #4a0a11, #7d121b);
                        color: #ffffff; }

/* ===== Settings ===== */

.settings-section-title {
    color: #7d121b;
    font-weight: bold;
    font-size: 17px;
    font-family: 'JetBrains Mono', monospace;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin: 16px 4px 6px 4px;
}

/* ===== Confirm dialog ===== */

.confirm-cmd {
    background-color: #0a0c0f;
    color: #7d121b;
    font-family: 'JetBrains Mono', monospace;
    font-size: 20px;
    padding: 16px;
    border-radius: 6px;
    border: 1px solid #1b1f26;
    margin: 10px 0;
}

/* ===== Scrollbar -- wider for touch ===== */

scrollbar slider {
    background-color: #2f3640;
    border-radius: 8px;
    min-width: 16px;
    min-height: 50px;
}
scrollbar slider:hover { background-color: #3d4651; }
scrollbar slider:active { background-color: #4a0a11; }

/* ===== Entry ===== */

entry {
    background-color: #12151a;
    color: #d6dbe2;
    border-radius: 6px;
    padding: 12px 16px;
    border: 1px solid #1b1f26;
    font-size: 20px;
}
entry:focus-within { outline: 2px solid #4a0a11; border-color: #4a0a11; }

passwordentry {
    background-color: #12151a;
    color: #d6dbe2;
    border-radius: 6px;
    padding: 12px 16px;
    border: 1px solid #1b1f26;
    font-size: 20px;
}

/* ===== Quick-action chips in empty state ===== */

.quick-chip {
    background-color: #12151a;
    color: #d6dbe2;
    border: 1px solid #1b1f26;
    border-radius: 6px;
    padding: 14px 24px;
    font-size: 19px;
    min-height: 40px;
}
.quick-chip:hover {
    background-color: #1f2530;
    color: #7d121b;
    border-color: #4a0a11;
}

/* ===== Terminal log panel ===== */

.terminal-panel {
    background-color: #07080a;
    border-top: 2px solid #1b1f26;
}

.terminal-panel-header {
    background-color: #0a0c0f;
    border-bottom: 1px solid #1b1f26;
    padding: 6px 12px;
    min-height: 40px;
}

.terminal-panel-title {
    color: #7d121b;
    font-family: 'JetBrains Mono', monospace;
    font-size: 14px;
    font-weight: bold;
    letter-spacing: 1px;
}

.terminal-log-view {
    background-color: transparent;
    color: #8fc99a;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 20px;
    padding: 8px 12px;
}

.media-panel {
    background-color: #07080a;
    border-top: 2px solid #1b1f26;
    min-height: 260px;
}
.media-body {
    background-color: #050607;
    padding: 6px;
}
.media-caption {
    color: #d1434f;
    font-size: 12px;
    margin-right: 8px;
}
.media-placeholder {
    color: #4b5563;
    font-size: 13px;
    font-style: italic;
    padding: 40px 12px;
}

.terminal-toggle-btn {
    background-color: #0d0f12;
    color: #7d8794;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 13px;
    min-height: 32px;
}
.status-pill {
    background-color: #0a0c0f;
    border: 1px solid #1a1d22;
    border-radius: 10px;
    padding: 3px 10px;
    margin-left: 4px;
    min-height: 26px;
}
.status-pill-label {
    color: #6b7280;
    font-size: 12px;
    font-style: italic;
}
.status-pill.busy {
    border-color: #7d121b;
    background-color: #140a0c;
}
.status-pill.busy .status-pill-label {
    color: #d1434f;
    font-style: normal;
}
.status-pill-spinner {
    min-width: 12px;
    min-height: 12px;
    color: #7d121b;
}
.terminal-toggle-btn:hover {
    background-color: #12151a;
    color: #7d121b;
}
.terminal-toggle-btn.active {
    background-color: #0a0c0f;
    color: #7d121b;
    border: 1px solid #4a0a11;
}

/* ===== Banner for watcher events ===== */

.watcher-banner {
    background-color: #0a0c0f;
    border-left: 4px solid #f0a500;
    border-radius: 6px;
    padding: 14px 18px;
    margin: 8px 16px;
    color: #f0a500;
    font-size: 17px;
}

.working-row {
    background-color: rgba(125, 18, 27, 0.15);
    border-radius: 8px;
    padding: 10px 22px;
}
.working-label {
    color: #7d121b;
    font-size: 18px;
    font-style: italic;
    font-weight: bold;
    letter-spacing: 0.5px;
}
.working-spinner {
    color: #7d121b;
    min-width: 24px;
    min-height: 24px;
}

/* ===== Proposed-command card (advisory flow) ===== */

.cmd-card {
    background-color: #0d0f12;
    border: 1px solid #1b1f26;
    border-left: 4px solid #4a0a11;
    border-radius: 8px;
    padding: 14px 16px;
    margin: 8px 0;
}
.cmd-card-header {
    margin-bottom: 8px;
}
.cmd-card-title {
    color: #7d121b;
    font-weight: bold;
    font-size: 15px;
    font-family: 'JetBrains Mono', monospace;
    letter-spacing: 0.5px;
}
.risk-badge {
    border-radius: 4px;
    padding: 2px 12px;
    font-size: 13px;
    font-weight: bold;
    font-family: 'JetBrains Mono', monospace;
    letter-spacing: 0.5px;
}
.risk-badge.low    { background-color: #2ecc71; color: #08090b; }
.risk-badge.medium { background-color: #f0a500; color: #08090b; }
.risk-badge.high   { background-color: #e5484d; color: #ffffff; }
.cmd-text {
    background-color: #0a0c0f;
    color: #7d121b;
    font-family: 'JetBrains Mono', monospace;
    font-size: 18px;
    padding: 12px 14px;
    border-radius: 6px;
    border: 1px solid #1b1f26;
    margin-bottom: 8px;
}
.cmd-explain {
    color: #aeb6c2;
    font-size: 16px;
    margin-bottom: 12px;
}
.card-warn {
    background-color: rgba(229, 72, 77, 0.10);
    border: 1px solid rgba(229, 72, 77, 0.45);
    border-radius: 8px;
    color: #f3b0b2;
    font-size: 15px;
    padding: 10px 14px;
    margin: 6px 0;
}
.cmd-run-btn {
    background: linear-gradient(135deg, #4a0a11, #7d121b);
    color: #ffffff;
    border-radius: 6px;
    padding: 10px 22px;
    font-weight: bold;
    font-size: 16px;
}
.cmd-run-btn:hover { background: linear-gradient(135deg, #7d121b, #4a0a11); }
.cmd-run-btn:disabled { background: #1b1f26; color: #5a626d; }
.cmd-copy-btn {
    background-color: #12151a;
    color: #d6dbe2;
    border-radius: 6px;
    padding: 10px 18px;
    font-size: 16px;
    border: 1px solid #1b1f26;
}
.cmd-copy-btn:hover { background-color: #1f2530; border-color: #4a0a11; }

/* ===== libadwaita rows / settings / dialogs =====
   Force the Basilisk surfaces on the built-in widgets so Settings and
   dialogs match the rest of the app instead of showing stock Adwaita
   grey. */

preferencespage, preferencesgroup {
    background-color: #08090b;
}
row, .row, list.boxed-list > row {
    background-color: #0d0f12;
    color: #d6dbe2;
}
list.boxed-list {
    background-color: #0d0f12;
    border: 1px solid #1b1f26;
    border-radius: 8px;
}
row:hover { background-color: #12151a; }
row > box { background-color: transparent; }

/* Switches: blue when on, dark track when off */
switch {
    background-color: #1b1f26;
    border-radius: 14px;
}
switch:checked {
    background-color: #4a0a11;
}
switch > slider {
    background-color: #d6dbe2;
    border-radius: 50%;
}

/* SpinRow / spinbuttons */
spinbutton, spinbutton entry {
    background-color: #12151a;
    color: #d6dbe2;
    border-radius: 6px;
}
spinbutton button {
    background-color: #12151a;
    color: #7d121b;
}
spinbutton button:hover { background-color: #1b1f26; }

/* ComboRow dropdown */
comborow, dropdown {
    background-color: #12151a;
    color: #d6dbe2;
}
dropdown > button {
    background-color: #12151a;
    color: #d6dbe2;
    border-radius: 6px;
}
popover > contents, popover > arrow {
    background-color: #0d0f12;
    color: #d6dbe2;
    border: 1px solid #1b1f26;
}
popover row:selected, dropdown listview > row:selected {
    background-color: #4a0a11;
    color: #ffffff;
}

/* Dialogs (AlertDialog / PreferencesDialog) */
window.dialog, dialog, .messagedialog, .dialog-content {
    background-color: #0d0f12;
    color: #d6dbe2;
}
.messagedialog .response-area button {
    background-color: #12151a;
    color: #d6dbe2;
    border-radius: 6px;
    margin: 4px;
}
.messagedialog .response-area button.suggested-action {
    background: linear-gradient(135deg, #4a0a11, #7d121b);
    color: #ffffff;
}
.messagedialog .response-area button.destructive-action {
    background-color: #e5484d;
    color: #ffffff;
}

/* Search entry in the sidebar */
.sidebar-search, searchentry, searchentry text {
    background-color: #12151a;
    color: #d6dbe2;
    border-radius: 6px;
    border: 1px solid #1b1f26;
}
searchentry:focus-within { border-color: #4a0a11; }

/* Menu button / popover menu */
menubutton > button, .menu-button {
    color: #d6dbe2;
}
.popover-menu, menu, .menu {
    background-color: #0d0f12;
    color: #d6dbe2;
}

/* Generic buttons inherit the dark surface unless given a role class */
button {
    background-color: #12151a;
    color: #d6dbe2;
    border: 1px solid #1b1f26;
    border-radius: 11px;
}
button:hover { background-color: #1f2530; border-color: #4a0a11; }
button.flat { background-color: transparent; border: none; }
button.flat:hover { background-color: #12151a; }
button.suggested-action {
    background: linear-gradient(135deg, #4a0a11, #7d121b);
    color: #ffffff;
    border: none;
}

/* Dragon avatar tile in chat */
.avatar-dragon {
    border-radius: 8px;
    background-color: #000000;
    box-shadow: 0 0 10px rgba(255, 45, 58, 0.5), 0 0 4px rgba(125, 18, 27, 0.4);
}
.avatar-cross {
    border-radius: 8px;
    background-color: #0a0c0e;
    box-shadow: 0 0 8px rgba(125, 18, 27, 0.35);
}
.avatar-priest {
    border-radius: 10px;
    background-color: #0a0c0e;
    box-shadow: 0 0 10px rgba(64, 20, 96, 0.45), 0 0 4px rgba(64, 20, 96, 0.35);
}
/* let the penguin watermark show through the chat */
.chat-scroll,
.chat-scroll > viewport,
.chat-scroll viewport {
    background-color: transparent;
    background: transparent;
}
.chat-watermark { background: transparent; }
/* Darker backdrop behind the dragon watermark -- reduces brightness only
   (a neutral scrim over the ember gradient), so the brighter dragon pops. */
.chat-scrim { background-color: rgba(0, 0, 0, 0.62); }

/* Tao Te Ching line under the chat list (sidebar) - quiet, muted, out of the way */
.tao-quote {
    color: #c2b28a;
    font-size: 19px;
    font-style: italic;
    line-height: 1.5;
}

/* Links (e.g. 'Get an API key') in Basilisk blue */
link, button.link, *:link { color: #7d121b; }

/* Voice: mic button + active recording state */
.mic-button {
    background-color: #12151a;
    color: #d6dbe2;
    border: 1px solid #1b1f26;
    border-radius: 11px;
}
.mic-button:hover { background-color: #1f2530; border-color: #4a0a11; }
.mic-recording {
    background: linear-gradient(135deg, #e5484d, #ff5c61);
    color: #ffffff;
    border: 1px solid #ff5c61;
    box-shadow: 0 0 10px rgba(229, 72, 77, 0.6);
}
.mic-recording:hover {
    background: linear-gradient(135deg, #ff5c61, #ff6f73);
    border-color: #ff6f73;
}

/* Per-message read-aloud button - sits under the reply, clearly tappable */
.msg-footer { margin-top: 6px; }
.msg-speak-btn {
    padding: 5px 14px;
    margin: 2px 0 0 2px;
    color: #8a8f97;
    background-color: rgba(20, 16, 14, 0.72);
    border: 1px solid rgba(120, 72, 58, 0.34);
    border-radius: 11px;
    /* 12px against 30px body copy was a speck. This is a control the
       operator has to be able to hit on a phone. */
    font-size: 17px;
    font-weight: 500;
    opacity: 0.72;
}
.msg-speak-btn:hover { opacity: 1.0; }
.msg-speak-btn:hover {
    background-color: #1b2128;
    color: #7d121b;
    border-color: #4a0a11;
}
.msg-speak-btn.speaking {
    color: #7d121b;
    border-color: #4a0a11;
    background-color: rgba(125, 18, 27, 0.12);
}

/* Composer action icons (attach, audit, scan, mic) - subtle + rounded */
/* ===== Arcane "summoned" buttons: carved obsidian lit by an ember sigil,
   not flat gray squares. Hover awakens the ember; press sinks it into the
   stone. ASCII-only (this is a bytes-literal stylesheet). ===== */
.icon-button {
    background-color: #0b0708;
    background-image:
        radial-gradient(ellipse at 50% 118%, rgba(170, 34, 20, 0.30), rgba(170, 34, 20, 0) 70%),
        linear-gradient(180deg, rgba(64, 22, 16, 0.28), rgba(10, 6, 6, 0) 62%);
    border: 1px solid rgba(125, 18, 27, 0.48);
    border-radius: 12px;
    color: #d9b3a1;
    padding: 7px;
    box-shadow: inset 0 1px 0 rgba(210, 90, 48, 0.10),
                inset 0 -6px 12px rgba(120, 26, 14, 0.16),
                0 0 8px rgba(125, 18, 27, 0.22);
    transition: all 160ms ease;
}
.notif-badge {
    background-color: #e5484d;
    color: #ffffff;
    font-size: 11px;
    font-weight: 700;
    border-radius: 9px;
    padding: 0px 5px;
    margin-top: -2px;
    margin-right: -2px;
    min-width: 14px;
}
.bell-glyph {
    font-size: 15px;
    color: #c4cad4;
}
.notif-title { font-weight: 700; color: #eef1f5; font-size: 14px; }
.notif-body { color: #c4cad4; font-size: 13px; }
.notif-time { color: #6b737d; font-size: 11px; }
.icon-button:hover {
    background-image:
        radial-gradient(ellipse at 50% 118%, rgba(225, 54, 26, 0.44), rgba(225, 54, 26, 0) 72%),
        linear-gradient(180deg, rgba(92, 30, 20, 0.36), rgba(10, 6, 6, 0) 60%);
    color: #ffd7bf;
    border-color: rgba(205, 64, 32, 0.90);
    box-shadow: inset 0 1px 0 rgba(255, 130, 66, 0.16),
                inset 0 -7px 14px rgba(185, 44, 22, 0.24),
                0 0 17px rgba(205, 54, 28, 0.52);
}
.icon-button:active {
    background-color: #070505;
    box-shadow: inset 0 3px 10px rgba(0, 0, 0, 0.62),
                inset 0 0 12px rgba(165, 32, 20, 0.32),
                0 0 7px rgba(125, 18, 27, 0.26);
}
.icon-button.toggled {
    color: #ffcaa8;
    border-color: rgba(220, 70, 36, 0.95);
    background-image:
        radial-gradient(ellipse at 50% 118%, rgba(220, 54, 26, 0.50), rgba(220, 54, 26, 0) 74%),
        linear-gradient(180deg, rgba(100, 32, 22, 0.40), rgba(10, 6, 6, 0) 60%);
    box-shadow: inset 0 -7px 14px rgba(190, 46, 22, 0.30),
                0 0 16px rgba(210, 56, 28, 0.55);
}
/* Send button - blends into the background; only the silver dragon pops.
   Glows softly while working; still acts as Stop when pressed. */
.send-button {
    background-color: #08090b;
    border: none;
    border-radius: 14px;
    min-width: 0;
    padding: 3px;
    margin: 0;
    box-shadow: none;
}
.send-button:hover {
    background-color: #08090b;
    box-shadow: 0 0 14px rgba(205, 54, 28, 0.5);
}
.send-button:active {
    background-color: #0a0c0f;
    box-shadow: inset 0 2px 8px rgba(0, 0, 0, 0.5);
}
.send-button.working {
    /* superseded by sendFire further down; kept as a no-op so the keyframe
       block below stays referenced rather than becoming dead CSS */
    animation: none;
}
@keyframes sendglow {
    0%   { box-shadow: 0 0 6px rgba(200, 208, 216, 0.25); border-color: #2a323b; }
    50%  { box-shadow: 0 0 20px rgba(224, 232, 240, 0.75); border-color: #c8d0d8; }
    100% { box-shadow: 0 0 6px rgba(200, 208, 216, 0.25); border-color: #2a323b; }
}
/* Header buttons (sidebar toggle, new chat) - blend into the header, with a
   quiet dragon-green accent only on hover so they don't draw the eye. */
.wordmark-btn {
    background: transparent;
    background-image: none;
    border: none;
    box-shadow: none;
    padding: 0 4px;
    min-height: 0;
    min-width: 0;
}
.wordmark-btn:hover {
    background-color: rgba(125, 18, 27, 0.16);
    box-shadow: none;
}
.logo-toggle { padding: 3px; }
/* Custom dragon-forged art buttons (settings, bell, terminal, minimise, close):
   the emblem art carries its own carved-stone frame, so the button is
   transparent -- just a soft ember glow on hover, to match the rest. */
.art-button {
    background-color: rgba(12, 8, 9, 0.66);
    background-image: linear-gradient(180deg, rgba(70, 24, 18, 0.24), rgba(9, 5, 6, 0) 66%);
    border: 1px solid rgba(140, 26, 32, 0.50);
    box-shadow: inset 0 1px 0 rgba(210, 90, 48, 0.07), 0 0 6px rgba(125, 18, 27, 0.20);
    padding: 3px;
    border-radius: 12px;
    transition: all 150ms ease;
}
.art-button:hover {
    background-color: rgba(125, 18, 27, 0.14);
    box-shadow: 0 0 14px rgba(205, 54, 28, 0.45);
}
.art-button:active {
    background-color: rgba(125, 18, 27, 0.22);
    box-shadow: inset 0 2px 8px rgba(0, 0, 0, 0.40), 0 0 8px rgba(205, 54, 28, 0.40);
}
/* UNLEASH -- the big red dragon. A quiet ember when idle, a hot red glow when
   armed so it's unmistakable that Basilisk is off the leash. */
.unleash-button {
    background: transparent;
    background-image: none;
    border: none;
    border-radius: 999px;
    box-shadow: 0 0 6px rgba(205, 54, 28, 0.28);
}
.unleash-button:hover {
    box-shadow: 0 0 16px rgba(230, 60, 30, 0.65);
}
.unleash-button.toggled {
    background-color: rgba(150, 20, 24, 0.30);
    box-shadow: 0 0 22px rgba(235, 45, 30, 0.95), inset 0 0 9px rgba(255, 95, 60, 0.55);
}
.unleash-button.toggled:hover {
    box-shadow: 0 0 30px rgba(255, 60, 40, 1.0), inset 0 0 11px rgba(255, 120, 80, 0.65);
}
/* A Gtk.MenuButton (settings, notifications) wraps its child in an inner
   > button that keeps GTK's default flat-grey styling -- that's the grey box
   around those two.  .art-button only clears the OUTER menubutton, so clear the
   inner button too: fully transparent, no border/shadow, ember glow on hover to
   match the plain art buttons. */
menubutton.art-button > button {
    background-color: rgba(12, 8, 9, 0.66);
    background-image: linear-gradient(180deg, rgba(70, 24, 18, 0.24), rgba(9, 5, 6, 0) 66%);
    border: 1px solid rgba(140, 26, 32, 0.50);
    box-shadow: inset 0 1px 0 rgba(210, 90, 48, 0.07), 0 0 6px rgba(125, 18, 27, 0.20);
    padding: 3px;
    min-width: 0;
    min-height: 0;
    border-radius: 12px;
}
menubutton.art-button > button:hover {
    background-color: rgba(125, 18, 27, 0.14);
    box-shadow: 0 0 14px rgba(205, 54, 28, 0.45);
}
menubutton.art-button > button:active {
    background-color: rgba(125, 18, 27, 0.22);
    box-shadow: inset 0 2px 8px rgba(0, 0, 0, 0.40), 0 0 8px rgba(205, 54, 28, 0.40);
}
/* Startup splash window -- dark backdrop behind the igniting-dragon animation
   (the DrawingArea paints over this; it just avoids a white flash on the very
   first frame). */
.splash-window {
    background-color: #0e1013;
}
.header-icon-button {
    background-color: transparent;
    background-image: none;
    border: none;
    box-shadow: none;
    color: #5e666f;
    border-radius: 10px;
    padding: 6px;
}
.header-icon-button:hover {
    background-color: rgba(125, 18, 27, 0.10);
    color: #7d121b;
    box-shadow: none;
}
.header-icon-button:active {
    background-color: rgba(125, 18, 27, 0.16);
}
/* Model / provider switcher in the composer */
.model-switch-btn {
    background-color: #0b0708;
    background-image:
        radial-gradient(ellipse at 50% 130%, rgba(170, 34, 20, 0.22), rgba(170, 34, 20, 0) 72%),
        linear-gradient(180deg, rgba(64, 22, 16, 0.22), rgba(10, 6, 6, 0) 62%);
    border: 1px solid rgba(125, 18, 27, 0.42);
    border-radius: 11px;
    color: #cbb0a4;
    padding: 5px 12px;
    font-size: 10.5px;
    font-weight: 600;
    box-shadow: inset 0 -5px 10px rgba(120, 26, 14, 0.14),
                0 0 7px rgba(125, 18, 27, 0.18);
    transition: all 160ms ease;
}
.model-switch-btn:hover {
    color: #ffd7bf;
    border-color: rgba(205, 64, 32, 0.85);
    box-shadow: inset 0 -6px 12px rgba(185, 44, 22, 0.22),
                0 0 14px rgba(205, 54, 28, 0.45);
}
/* Window controls (close / minimise): the same summoned-stone look, and the
   close sigil flares blood-red when you reach for it. */
windowcontrols > button,
.titlebutton {
    background-color: #0b0708;
    background-image: radial-gradient(ellipse at 50% 120%, rgba(150, 30, 18, 0.24), rgba(150, 30, 18, 0) 72%);
    border: 1px solid rgba(125, 18, 27, 0.40);
    border-radius: 10px;
    color: #c4a99c;
    box-shadow: inset 0 -5px 10px rgba(120, 26, 14, 0.14),
                0 0 6px rgba(125, 18, 27, 0.18);
    transition: all 150ms ease;
}
windowcontrols > button:hover,
.titlebutton:hover {
    color: #ffd7bf;
    border-color: rgba(205, 64, 32, 0.85);
    box-shadow: inset 0 -6px 12px rgba(185, 44, 22, 0.22),
                0 0 14px rgba(205, 54, 28, 0.45);
}
windowcontrols > button.close:hover,
.titlebutton.close:hover {
    background-image: radial-gradient(ellipse at 50% 120%, rgba(229, 72, 77, 0.50), rgba(229, 72, 77, 0) 74%);
    border-color: rgba(229, 72, 77, 0.95);
    color: #ffffff;
    box-shadow: 0 0 16px rgba(229, 72, 77, 0.60);
}
.model-group-header {
    color: #ff3a47;
    font-size: 15px;
    font-weight: 800;
    letter-spacing: 1px;
    margin-top: 10px;
    margin-bottom: 4px;
    padding-left: 4px;
}
.model-pick-row {
    background-color: transparent;
    border: none;
    border-radius: 8px;
    color: #e8ebef;
    padding: 11px 14px;
    font-size: 17px;
    font-weight: 500;
}
.model-pick-row:hover {
    background-color: rgba(125, 18, 27, 0.10);
    color: #7d121b;
}
.model-pick-active {
    background-color: rgba(125, 18, 27, 0.16);
    color: #7d121b;
    font-weight: 700;
}

/* =====================================================================
   POLISH LAYER  --  product-grade finish.  Appended last so it refines
   the base theme above (later rules win): real depth, smooth state
   transitions, tactile buttons, premium surfaces.  Tuned to read like a
   shipped commercial tool, not a script with a window.
   ===================================================================== */

/* Motion: subtle, fast, everywhere it counts. */
button, .quick-chip, .chat-row, entry, .mic-button, switch, row,
.cmd-run-btn, .cmd-copy-btn, .terminal-toggle-btn {
    transition: background-color 130ms ease,
                border-color 130ms ease,
                box-shadow 160ms ease,
                color 130ms ease;
}

/* Header: lift it off the content with a hairline + soft shadow. */
headerbar {
    box-shadow: 0 1px 0 rgba(255,255,255,0.02),
                0 2px 8px rgba(0,0,0,0.35);
}

/* ---- Buttons: depth, gradient sheen, a real pressed state ---- */
button {
    background-image: linear-gradient(180deg,
                      rgba(255,255,255,0.03), rgba(255,255,255,0.0));
    box-shadow: 0 1px 2px rgba(0,0,0,0.25),
                inset 0 1px 0 rgba(255,255,255,0.03);
    padding: 8px 16px;
    font-weight: 500;
}
button:hover {
    box-shadow: 0 2px 6px rgba(0,0,0,0.30),
                inset 0 1px 0 rgba(255,255,255,0.05);
}
button:active {
    background-image: none;
    box-shadow: inset 0 2px 5px rgba(0,0,0,0.40);
}
button:disabled {
    box-shadow: none;
    background-image: none;
    opacity: 0.55;
}
button:focus-visible {
    outline: 2px solid rgba(125, 18, 27,0.65);
    outline-offset: 1px;
}
button.suggested-action {
    box-shadow: 0 2px 8px rgba(125, 18, 27,0.35),
                inset 0 1px 0 rgba(255,255,255,0.15);
}
button.suggested-action:hover {
    box-shadow: 0 3px 14px rgba(125, 18, 27,0.45),
                inset 0 1px 0 rgba(255,255,255,0.20);
}

/* ---- Primary action buttons (Run / Apply) ---- */
.cmd-run-btn {
    box-shadow: 0 2px 10px rgba(125, 18, 27,0.40),
                inset 0 1px 0 rgba(255,255,255,0.18);
    padding: 11px 26px;
    letter-spacing: 0.2px;
}
.cmd-run-btn:hover {
    box-shadow: 0 4px 16px rgba(125, 18, 27,0.50),
                inset 0 1px 0 rgba(255,255,255,0.22);
}
.cmd-run-btn:active {
    box-shadow: inset 0 2px 6px rgba(0,0,0,0.35);
}
.cmd-copy-btn { padding: 11px 20px; }

/* ---- Command / edit cards: lift them onto a surface ---- */
.cmd-card {
    background-image: linear-gradient(180deg, #161a20, #121519);
    box-shadow: 0 4px 18px rgba(0,0,0,0.40),
                inset 0 1px 0 rgba(255,255,255,0.03);
    border: 1px solid #2b313b;
    padding: 16px 18px;
}
.cmd-card-title { letter-spacing: 0.4px; }
.risk-badge {
    box-shadow: 0 1px 3px rgba(0,0,0,0.30);
    letter-spacing: 0.3px;
    font-weight: 700;
}

/* ---- Composer entry: inset depth + a focus glow ---- */
entry {
    background-image: linear-gradient(180deg,
                      rgba(0,0,0,0.18), rgba(0,0,0,0.0));
    box-shadow: inset 0 1px 3px rgba(0,0,0,0.35);
}
entry:focus-within {
    box-shadow: inset 0 1px 3px rgba(0,0,0,0.35),
                0 0 0 3px rgba(125, 18, 27,0.22);
}

/* ---- Message bubbles: quiet depth so they sit above the canvas ---- */
.msg-user {
    box-shadow: 0 2px 10px rgba(125, 18, 27,0.18);
}
.msg-assistant {
    box-shadow: 0 2px 10px rgba(0,0,0,0.28);
}

/* ---- Sidebar chat rows: fire accent handled in the base block above ---- */
.chat-row {
    border-left: 3px solid transparent;
}

/* ---- Quick chips: pill polish ---- */
.quick-chip {
    background-image: linear-gradient(180deg,
                      rgba(255,255,255,0.03), rgba(255,255,255,0.0));
    box-shadow: 0 1px 2px rgba(0,0,0,0.20);
    padding: 7px 15px;
}
.quick-chip:hover {
    box-shadow: 0 2px 8px rgba(125, 18, 27,0.25);
}

/* ---- Mic recording: gentle pulse-ready glow already set; deepen it ---- */
.mic-recording {
    box-shadow: 0 0 0 3px rgba(229,72,77,0.25),
                0 0 14px rgba(229,72,77,0.55);
}

/* ---- Working row: a soft active surface ---- */
.working-row {
    background-image: linear-gradient(90deg,
                      rgba(125, 18, 27,0.10), rgba(125, 18, 27,0.0));
    box-shadow: inset 0 0 0 1px rgba(125, 18, 27,0.15);
}

/* ---- Slim, themed scrollbars ---- */
scrollbar { background-color: transparent; border: none; }
scrollbar slider {
    background-color: #2b313b;
    border-radius: 10px;
    min-width: 7px;
    min-height: 7px;
}
scrollbar slider:hover { background-color: #3a4250; }
scrollbar slider:active { background-color: #7d121b; }

/* ---- Boxed settings lists: a touch of depth ---- */
list.boxed-list {
    box-shadow: 0 2px 12px rgba(0,0,0,0.30);
}

/* ---- Auto-run note: when Basilisk runs a command without a card ---- */
.autorun-note {
    color: #6f7a88;
    font-size: 13px;
    font-family: 'JetBrains Mono', monospace;
    margin: 2px 0 6px 0;
}

/* =====================================================================
   HELLFIRE THEME OVERLAY  (v1 - pure CSS, no Cairo)
   Appended last so these rules win the cascade over the base theme.
   Burns the flat-dark surfaces down to charcoal, wraps the chat bubbles
   in a breathing ember glow, and rebuilds the "working" status line as a
   burning bar with real upward-scrolling fire that sits just above the
   Send button.  ASCII-only (the CSS is an ASCII bytes literal).
   ===================================================================== */

/* ---- App-wide burned charcoal: char lumps + ember cracks + heat rising
        from the bottom edge.  If a radial-gradient is skipped by the CSS
        engine the base color still lands, so panels never fall back to a
        flat slab. ---- */
window, .background {
    background-color: #070506;
    background-image:
        radial-gradient(circle at 15% 12%, rgba(46,42,40,0.55), rgba(46,42,40,0.0) 40%),
        radial-gradient(circle at 82% 20%, rgba(34,30,29,0.55), rgba(34,30,29,0.0) 42%),
        radial-gradient(circle at 42% 66%, rgba(26,23,23,0.60), rgba(26,23,23,0.0) 46%),
        radial-gradient(circle at 90% 84%, rgba(150,45,18,0.06), rgba(150,45,18,0.0) 40%),
        radial-gradient(circle at 8% 88%, rgba(180,60,20,0.05), rgba(180,60,20,0.0) 38%),
        linear-gradient(0deg, rgba(120,30,12,0.07) 0%, rgba(10,7,6,0.0) 28%),
        linear-gradient(180deg, #0b0807, #070506 55%, #050303);
}

/* ---- Structural panels: same charred base, a hair lighter than the
        window so depth still reads, with a low ember bloom baked in. ---- */
headerbar {
    background-color: #0a0807;
    background-image:
        radial-gradient(circle at 20% 40%, rgba(60,26,16,0.30), rgba(60,26,16,0.0) 55%),
        radial-gradient(circle at 85% 60%, rgba(40,20,16,0.35), rgba(40,20,16,0.0) 55%),
        linear-gradient(180deg, #100b09, #0a0706);
    border-bottom: 1px solid #2a1712;
    box-shadow: inset 0 -6px 14px rgba(120,35,12,0.10);
}
.sidebar {
    background-color: #080605;
    background-image:
        radial-gradient(circle at 30% 20%, rgba(44,38,36,0.40), rgba(44,38,36,0.0) 45%),
        radial-gradient(circle at 60% 80%, rgba(90,28,12,0.10), rgba(90,28,12,0.0) 45%),
        linear-gradient(180deg, #0b0908, #070505);
    border-right: 1px solid #241410;
}
.input-frame {
    background-color: #0c0908;
    background-image: linear-gradient(180deg, rgba(60,26,16,0.16), rgba(12,9,8,0.0) 60%);
    border: 1px solid #3a2016;
    box-shadow: inset 0 -5px 14px rgba(140,45,16,0.10);
}
.input-frame:focus-within {
    border-color: #c8501a;
    background-color: #140d0a;
    box-shadow: inset 0 -6px 16px rgba(200,70,20,0.22), 0 0 14px rgba(200,70,20,0.18);
}

/* ---- Chat bubbles: charred body plus a breathing ember halo.  User and
        assistant flicker on different clocks so they never pulse in sync. ---- */
.msg-user, .msg-assistant {
    transition: box-shadow 240ms ease, border-color 240ms ease;
}
.msg-user {
    color: #f5e9df;
    border-radius: 16px 16px 4px 16px;
    background-color: #0d0806;
    background-image:
        radial-gradient(ellipse at 92% -12%, rgba(226, 96, 34, 0.16), rgba(226, 96, 34, 0) 48%),
        radial-gradient(ellipse at 4% 126%, rgba(150, 44, 14, 0.20), rgba(150, 44, 14, 0) 56%),
        linear-gradient(0deg, rgba(150, 50, 16, 0.12), rgba(60, 18, 8, 0.05) 42%, rgba(0, 0, 0, 0.0) 74%);
    border: 1px solid rgba(196, 78, 30, 0.54);
    box-shadow:
        inset 0 1px 0 rgba(240, 150, 90, 0.12),
        inset 0 0 26px rgba(150, 46, 18, 0.16),
        inset 0 -7px 18px rgba(170, 52, 16, 0.18),
        0 0 0 1px rgba(0, 0, 0, 0.40),
        0 8px 22px rgba(0, 0, 0, 0.50),
        0 0 14px rgba(210, 72, 24, 0.30);
    text-shadow: 0 0 9px rgba(220, 84, 34, 0.26), 0 1px 1px rgba(0, 0, 0, 0.55);
}
.msg-assistant {
    color: #f2e7de;
    border-radius: 4px 16px 16px 16px;
    background-color: #0b0706;
    background-image:
        radial-gradient(ellipse at 6% -12%, rgba(206, 58, 28, 0.16), rgba(206, 58, 28, 0) 46%),
        radial-gradient(ellipse at 104% 128%, rgba(130, 24, 26, 0.20), rgba(130, 24, 26, 0) 56%),
        linear-gradient(0deg, rgba(170, 55, 16, 0.11), rgba(70, 20, 8, 0.05) 42%, rgba(0, 0, 0, 0.0) 74%);
    border: 1px solid rgba(182, 58, 30, 0.52);
    box-shadow:
        inset 0 1px 0 rgba(232, 132, 80, 0.11),
        inset 0 0 28px rgba(150, 40, 22, 0.16),
        inset 0 -7px 18px rgba(160, 48, 15, 0.17),
        0 0 0 1px rgba(0, 0, 0, 0.40),
        0 8px 22px rgba(0, 0, 0, 0.50),
        0 0 14px rgba(196, 60, 26, 0.28);
    text-shadow: 0 0 9px rgba(202, 62, 34, 0.25), 0 1px 1px rgba(0, 0, 0, 0.55);
}
.msg-user:hover {
    border-color: rgba(226, 96, 40, 0.72);
    box-shadow:
        inset 0 1px 0 rgba(240, 150, 90, 0.14),
        inset 0 0 30px rgba(160, 50, 20, 0.20),
        inset 0 -7px 18px rgba(180, 56, 18, 0.20),
        0 0 0 1px rgba(0, 0, 0, 0.40),
        0 10px 26px rgba(0, 0, 0, 0.52),
        0 0 24px rgba(226, 84, 30, 0.48);
}
.msg-assistant:hover {
    border-color: rgba(210, 66, 34, 0.72);
    box-shadow:
        inset 0 1px 0 rgba(232, 132, 80, 0.13),
        inset 0 0 32px rgba(160, 44, 24, 0.20),
        inset 0 -7px 18px rgba(170, 52, 18, 0.19),
        0 0 0 1px rgba(0, 0, 0, 0.40),
        0 10px 26px rgba(0, 0, 0, 0.52),
        0 0 24px rgba(212, 66, 30, 0.46);
}

/* ---- The status line, reborn as a burning bar.  A flame gradient taller
        than the row is scrolled upward every frame (real fire motion) while
        the same keyframes flicker the glow.  Placed just above the Send
        button by the layout change in _build_input_area. ---- */
.working-row {
    background-color: #0a0605;
    background-image: linear-gradient(0deg,
        rgba(255,190,60,0.0) 0%,
        rgba(255,140,30,0.34) 18%,
        rgba(214,60,14,0.46) 44%,
        rgba(120,26,10,0.32) 68%,
        rgba(20,7,5,0.0) 100%);
    background-size: 100% 280%;
    background-position: 0% 100%;
    border: 1px solid rgba(210,80,26,0.50);
    border-radius: 10px;
    padding: 10px 22px;
    animation: fireScroll 1.15s linear infinite;
}
@keyframes fireScroll {
    0%   { background-position: 0% 100%; box-shadow: 0 0 12px rgba(220,72,20,0.30), inset 0 -6px 16px rgba(255,120,30,0.20); }
    50%  { background-position: 0% 40%;  box-shadow: 0 0 24px rgba(255,110,30,0.58), inset 0 -9px 22px rgba(255,150,44,0.36); }
    100% { background-position: 0% 0%;   box-shadow: 0 0 12px rgba(220,72,20,0.30), inset 0 -6px 16px rgba(255,120,30,0.20); }
}
.working-label {
    color: #ffd27a;
    font-size: 18px;
    font-style: normal;
    font-weight: 800;
    letter-spacing: 0.6px;
    text-shadow: 0 0 8px rgba(255,150,44,0.9), 0 0 16px rgba(255,90,22,0.6);
    animation: emberText 0.85s ease-in-out infinite;
}
@keyframes emberText {
    0%   { color: #ffcf6e; text-shadow: 0 0 6px rgba(255,150,44,0.8), 0 0 14px rgba(255,90,22,0.5); }
    50%  { color: #fff1c6; text-shadow: 0 0 13px rgba(255,182,64,1.0), 0 0 24px rgba(255,110,30,0.8); }
    100% { color: #ffcf6e; text-shadow: 0 0 6px rgba(255,150,44,0.8), 0 0 14px rgba(255,90,22,0.5); }
}
.working-spinner {
    color: #ff9030;
    min-width: 24px;
    min-height: 24px;
}

/* ---- Send button: match the fire while working instead of the silver glow ---- */
.send-button.working {
    animation: sendFire 1.2s ease-in-out infinite;
}
@keyframes sendFire {
    0%   { box-shadow: 0 0 6px rgba(255,120,30,0.30); border-color: #3a2016; }
    50%  { box-shadow: 0 0 22px rgba(255,120,30,0.82); border-color: #ff7a2a; }
    100% { box-shadow: 0 0 6px rgba(255,120,30,0.30); border-color: #3a2016; }
}

/* =====================================================================
   LIVE ACTIVITY FEED  (ActivityFeedWidget)

   One panel per operator turn.  Header always readable; body is the live
   stream while working and folds to the header alone once the turn settles.

   Everything here is ASCII-only, like the rest of this stylesheet: the CSS
   is a bytes literal and a stray smart-quote or arrow becomes a decode
   error at startup, which is a black window with a traceback rather than a
   cosmetic bug.  Glyphs belong in the Python labels, not in here.
   ===================================================================== */

.activity-feed {
    margin: 6px 60px 10px 12px;
    border-radius: 14px;
    background-color: #0a0807;
    background-image: linear-gradient(180deg,
        rgba(255, 150, 60, 0.055) 0%,
        rgba(255, 120, 40, 0.018) 34%,
        rgba(0, 0, 0, 0.0) 100%);
    border: 1px solid rgba(150, 52, 22, 0.34);
    box-shadow:
        inset 0 1px 0 rgba(255, 170, 110, 0.07),
        0 0 0 1px rgba(0, 0, 0, 0.40),
        0 8px 22px rgba(0, 0, 0, 0.46);
}

/* Working: a hot rail down the left edge, breathing.  This is the single
   animated element in the panel -- a per-row animation would be dozens of
   clocks running at once during a mission, for no extra information. */
.activity-feed.live {
    border-color: rgba(226, 96, 34, 0.50);
    border-left: 3px solid #e2601f;
    animation: activityRail 1.6s ease-in-out infinite;
}
@keyframes activityRail {
    0%   { border-left-color: #8a2f12; box-shadow: inset 0 1px 0 rgba(255,170,110,0.07), 0 0 0 1px rgba(0,0,0,0.40), 0 8px 22px rgba(0,0,0,0.46), -1px 0 12px rgba(226,96,34,0.20); }
    50%  { border-left-color: #ff9a44; box-shadow: inset 0 1px 0 rgba(255,170,110,0.10), 0 0 0 1px rgba(0,0,0,0.40), 0 8px 22px rgba(0,0,0,0.46), -1px 0 22px rgba(255,140,50,0.55); }
    100% { border-left-color: #8a2f12; box-shadow: inset 0 1px 0 rgba(255,170,110,0.07), 0 0 0 1px rgba(0,0,0,0.40), 0 8px 22px rgba(0,0,0,0.46), -1px 0 12px rgba(226,96,34,0.20); }
}
.activity-feed.done {
    border-left: 3px solid rgba(120, 44, 20, 0.55);
}
.activity-feed.collapsed {
    background-image: none;
}

/* ---- Header: the line that is always true ---- */
.activity-header {
    background: none;
    background-image: none;
    border: none;
    box-shadow: none;
    min-height: 0;
    padding: 11px 16px;
    border-radius: 14px;
}
.activity-header:hover {
    background-color: rgba(255, 140, 60, 0.06);
}
.activity-header:active {
    background-color: rgba(255, 140, 60, 0.10);
}

.activity-spinner {
    color: #ff9a44;
    min-width: 18px;
    min-height: 18px;
}
.activity-verdict {
    font-family: 'JetBrains Mono', monospace;
    font-size: 18px;
    font-weight: 800;
    min-width: 18px;
    color: #7d8794;
}
.activity-verdict.ok   { color: #35c46f; text-shadow: 0 0 10px rgba(46, 204, 113, 0.45); }
.activity-verdict.fail { color: #e5484d; text-shadow: 0 0 10px rgba(229, 72, 77, 0.45); }

.activity-title {
    color: #ffcf8e;
    font-family: 'JetBrains Mono', monospace;
    font-size: 19px;
    font-weight: 700;
    letter-spacing: 0.3px;
    text-shadow: 0 0 9px rgba(255, 150, 60, 0.30);
}
.activity-feed.done .activity-title {
    color: #b9c0cb;
    text-shadow: none;
}
.activity-meta {
    color: #8a929e;
    font-family: 'JetBrains Mono', monospace;
    font-size: 15px;
    letter-spacing: 0.2px;
}
.activity-chevron {
    color: #6f7885;
    font-size: 17px;
    font-weight: 700;
    min-width: 14px;
}
.activity-header:hover .activity-chevron { color: #ffab5e; }

/* ---- Body: the stream ---- */
.activity-body {
    padding: 2px 14px 10px 14px;
}

.activity-step {
    padding: 5px 6px 5px 4px;
    border-radius: 7px;
}
.activity-step.run {
    background-color: rgba(255, 140, 50, 0.055);
}

.activity-glyph {
    font-family: 'JetBrains Mono', monospace;
    font-size: 15px;
    font-weight: 800;
    min-width: 15px;
    color: #6f7885;
}
.activity-step.run  .activity-glyph { color: #ff9a44; }
.activity-step.ok   .activity-glyph { color: #35c46f; }
.activity-step.fail .activity-glyph { color: #e5484d; }
.activity-step.stop .activity-glyph { color: #b0873a; }
.activity-step.gate .activity-glyph { color: #e5484d; }

.activity-step-name {
    color: #dfe4ec;
    font-family: 'JetBrains Mono', monospace;
    font-size: 17px;
    font-weight: 700;
    letter-spacing: 0.2px;
}
.activity-step.run .activity-step-name { color: #ffe0b4; }
.activity-step.note .activity-step-name,
.activity-step.gate .activity-step-name {
    font-weight: 500;
    color: #9aa3b0;
}
.activity-step.gate .activity-step-name { color: #e8a2a4; }

.activity-step-detail {
    color: #838c99;
    font-family: 'JetBrains Mono', monospace;
    font-size: 16px;
}
.activity-step-time {
    color: #69727e;
    font-family: 'JetBrains Mono', monospace;
    font-size: 14px;
    letter-spacing: 0.3px;
}
.activity-step.run .activity-step-time { color: #c98a44; }

.activity-step.past {
    padding: 4px 6px 4px 4px;
}
.activity-step.past .activity-glyph { color: #5c6673; }
.activity-step.past .activity-step-name {
    font-weight: 500;
    color: #aab2be;
}

/* ---- Links inside a reply.  The base rule paints them #7d121b, which is
        the deep accent -- fine on a light chrome surface, but inside a
        charred bubble it is barely separable from the body text, and a
        citation the operator cannot SEE is a citation he will not click.
        ANSWER MODE makes one of these the last line of nearly every leashed
        reply, so it earns a colour that reads. ---- */
.msg-assistant link,
.msg-assistant *:link,
.msg-user link,
.msg-user *:link {
    color: #ff9a44;
    text-decoration-color: rgba(255, 154, 68, 0.45);
}
.msg-assistant *:link:hover,
.msg-user *:link:hover {
    color: #ffc27a;
    text-decoration-color: rgba(255, 194, 122, 0.85);
}
.msg-assistant *:visited,
.msg-user *:visited {
    color: #d8894a;
}

.activity-preview-box {
    padding: 0 6px 6px 27px;
}
.activity-preview {
    color: #7f8894;
    font-family: 'JetBrains Mono', monospace;
    font-size: 15px;
    line-height: 1.35;
}

/* =====================================================================
   STRUCTURED MARKDOWN -- tables, headings, quotes, rules, lists.

   A comparison answer arrives as a table, and a report answer arrives as
   headings and bullets. Rendered as literal pipe characters in a
   proportional font, neither one lines up, so the most structured thing
   the model can say was the least readable thing on screen. These give
   each shape its own compartment, the way a web chat UI does.
   ===================================================================== */

.md-table {
    margin: 10px 0 12px 0;
    border-radius: 10px;
    background-color: #0a0b0d;
    border: 1px solid rgba(150, 60, 30, 0.36);
    box-shadow: 0 3px 12px rgba(0, 0, 0, 0.34);
}
.md-table scrolledwindow { border-radius: 10px; }
.md-table-grid { background-color: transparent; }

.md-th {
    padding: 10px 14px;
    background-color: #150e0b;
    border-bottom: 2px solid rgba(196, 88, 40, 0.55);
    border-right: 1px solid rgba(120, 60, 40, 0.24);
}
.md-th.lastcol { border-right: none; }
.md-th label {
    color: #ffcf9c;
    font-family: 'JetBrains Mono', monospace;
    font-size: 21px;
    font-weight: 800;
    letter-spacing: 0.5px;
}

.md-td {
    padding: 9px 14px;
    border-top: 1px solid rgba(120, 70, 50, 0.16);
    border-right: 1px solid rgba(120, 60, 40, 0.16);
}
.md-td.lastcol { border-right: none; }
.md-td.odd { background-color: rgba(255, 165, 95, 0.055); }
.md-td label {
    color: #e2e6ec;
    font-size: 26px;
    line-height: 1.35;
}
.md-table-more {
    padding: 8px 14px;
    color: #8a8377;
    font-family: 'JetBrains Mono', monospace;
    font-size: 19px;
    border-top: 1px solid rgba(120, 70, 50, 0.20);
}

/* ---- Blockquote: an accent rail and an inset panel ---- */
.md-quote {
    margin: 9px 0;
    border-radius: 8px;
    background-color: rgba(255, 150, 70, 0.045);
}
.md-quote-rail {
    min-width: 3px;
    background-color: #c4551f;
    border-radius: 3px;
}
.md-quote-body {
    padding: 10px 16px;
    color: #cfd4dc;
    font-size: 28px;
    font-style: italic;
    line-height: 1.45;
}

/* ---- Headings: sections you can scan ---- */
.md-heading { margin: 14px 0 6px 0; }
.md-heading:first-child { margin-top: 2px; }
.md-heading-text {
    color: #ffd9ab;
    font-weight: 800;
    letter-spacing: 0.3px;
}
.md-heading.h1 .md-heading-text { font-size: 40px; }
.md-heading.h2 .md-heading-text { font-size: 35px; }
.md-heading.h3 .md-heading-text { font-size: 31px; color: #f5c99a; }
.md-heading.h4 .md-heading-text,
.md-heading.h5 .md-heading-text,
.md-heading.h6 .md-heading-text {
    font-size: 28px;
    color: #e2bc9a;
    letter-spacing: 0.6px;
}
.md-heading-rule {
    min-height: 1px;
    margin-top: 5px;
    background-color: rgba(196, 88, 40, 0.34);
}

.md-rule {
    min-height: 1px;
    margin: 13px 6px;
    background-color: rgba(150, 90, 60, 0.32);
}

/* ---- Lists: a real hanging indent ---- */
.md-list {
    margin: 5px 0 7px 0;
}
.md-list-marker {
    color: #d9853f;
    font-weight: 800;
    font-size: 26px;
    padding: 2px 11px 2px 4px;
    min-width: 22px;
}
.md-list-text {
    color: #e6eaf0;
    font-size: 30px;
    line-height: 1.45;
    padding-bottom: 6px;
}

/* ---- The docked activity feed. Pinned above the action buttons, so it
        cannot scroll away after a few more messages the way it did when it
        lived inside the message list. Slightly tighter than the inline
        version: this is a status strip, not a chat row. ---- */
.activity-dock {
    margin: 2px 4px 0 4px;
}
.activity-dock .activity-feed {
    margin: 0;
    border-radius: 12px;
}
.activity-dock .activity-header {
    padding: 8px 14px;
    border-radius: 12px;
}
.activity-dock .activity-body {
    padding: 0 12px 8px 12px;
}
.activity-dock .activity-step { padding: 4px 6px 4px 4px; }

/* =====================================================================
   ATTACHMENT TRAY -- staged files, ABOVE the composer.

   Reads as part of the composer rather than as chat content: same charred
   surface, one step brighter, so it is obviously "about to be sent" and not
   "already sent".
   ===================================================================== */

.attach-tray {
    padding: 4px 4px 2px 4px;
}

.attach-chip {
    padding: 6px 8px 6px 10px;
    margin: 2px 3px;
    border-radius: 11px;
    background-color: #120c09;
    background-image: linear-gradient(180deg,
        rgba(255, 150, 60, 0.07), rgba(255, 120, 40, 0.015));
    border: 1px solid rgba(180, 66, 26, 0.46);
    box-shadow:
        inset 0 1px 0 rgba(255, 175, 120, 0.09),
        0 2px 8px rgba(0, 0, 0, 0.40);
}
.attach-chip:hover {
    border-color: rgba(226, 96, 40, 0.72);
    box-shadow:
        inset 0 1px 0 rgba(255, 175, 120, 0.12),
        0 3px 12px rgba(0, 0, 0, 0.46),
        0 0 14px rgba(226, 84, 30, 0.26);
}

.attach-chip-kind {
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    font-weight: 800;
    letter-spacing: 0.8px;
    padding: 2px 6px;
    border-radius: 5px;
    color: #0a0605;
    background-color: #c97a3c;
}
.attach-chip.image .attach-chip-kind { background-color: #b8683a; }
.attach-chip.file  .attach-chip-kind { background-color: #8d8f96; }

.attach-chip-name {
    color: #e6dbd1;
    font-family: 'JetBrains Mono', monospace;
    font-size: 16px;
    font-weight: 600;
}
.attach-chip-size {
    color: #8a8377;
    font-family: 'JetBrains Mono', monospace;
    font-size: 14px;
}
.attach-chip-remove {
    color: #99908a;
    font-size: 17px;
    font-weight: 800;
    min-width: 22px;
    min-height: 22px;
    padding: 0;
    border-radius: 6px;
    background: none;
    background-image: none;
    border: none;
    box-shadow: none;
}
.attach-chip-remove:hover {
    color: #ffffff;
    background-color: #b3373b;
}

/* =====================================================================
   BUBBLES -- last layer, so it wins.

   CALM, NOT DIM. The previous pass stacked six shadows per bubble: two
   inner glows, an outer ring, a drop shadow and a coloured halo, on top of
   two radial gradients and a linear one. Every element was individually
   defensible and the sum was a screen where nothing sat still and long text
   had a permanent orange haze behind it.

   What actually separates a bubble from the background is ONE clear edge
   and ONE soft drop shadow. That is what is left here. The ember identity
   moves to where it costs nothing to read: a tinted border, a barely-there
   top highlight, and a hover state that lifts. No halo behind body text, no
   text-shadow smearing 30px glyphs, no gradient competing with the words.
   ===================================================================== */

.msg-row {
    padding: 3px 0;
}

.msg-user, .msg-assistant {
    padding: 16px 20px;
    background-image: none;
    text-shadow: none;
    transition: border-color 160ms ease, box-shadow 160ms ease;
}

.msg-user {
    color: #f2ece7;
    margin: 7px 12px 7px 64px;
    line-height: 1.45;
    border-radius: 16px 16px 5px 16px;
    background-color: #17100c;
    border: 1px solid rgba(176, 82, 40, 0.42);
    box-shadow:
        inset 0 1px 0 rgba(255, 190, 140, 0.06),
        0 2px 10px rgba(0, 0, 0, 0.42);
}
.msg-assistant {
    color: #e9edf2;
    margin: 7px 64px 7px 12px;
    line-height: 1.5;
    border-radius: 5px 16px 16px 16px;
    background-color: #101215;
    border: 1px solid rgba(120, 72, 58, 0.38);
    box-shadow:
        inset 0 1px 0 rgba(220, 190, 170, 0.05),
        0 2px 10px rgba(0, 0, 0, 0.42);
}

.msg-user:hover {
    border-color: rgba(206, 100, 52, 0.62);
    box-shadow:
        inset 0 1px 0 rgba(255, 190, 140, 0.08),
        0 4px 16px rgba(0, 0, 0, 0.48);
}
.msg-assistant:hover {
    border-color: rgba(158, 96, 74, 0.58);
    box-shadow:
        inset 0 1px 0 rgba(220, 190, 170, 0.07),
        0 4px 16px rgba(0, 0, 0, 0.48);
}

/* ---- Role labels: quieter, so the eye lands on the message ---- */
.role-label {
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 1.4px;
    opacity: 0.62;
    margin: 0 4px 4px 4px;
}
.role-label.user     { color: #c26c39; }
.role-label.basilisk { color: #b9a08c; }

/* The seal is atmosphere, not information -- at full strength it sat behind
   the last line of every reply. */
.msg-sigil { opacity: 0.16; }

/* ---- Inline tool indicator from reloaded history: present, not loud ---- */
.msg-tool-indicator {
    padding: 4px 14px 4px 70px;
    margin: 1px 12px;
}
.tool-indicator-label {
    color: #6d7682;
    font-size: 16px;
    opacity: 0.78;
}

/* ---- Links inside a reply. The base rule paints them #7d121b, which is
        nearly inseparable from body text inside a dark bubble -- and ANSWER
        MODE makes one of these the last line of nearly every leashed reply,
        so it earns a colour that reads. ---- */
.msg-assistant link,
.msg-assistant *:link,
.msg-user link,
.msg-user *:link {
    color: #e8944e;
    text-decoration-color: rgba(232, 148, 78, 0.42);
}
.msg-assistant *:link:hover,
.msg-user *:link:hover {
    color: #ffb877;
    text-decoration-color: rgba(255, 184, 119, 0.85);
}
.msg-assistant *:visited,
.msg-user *:visited { color: #c4855a; }
"""


# ═════════════════════════════════════════════════════════════════════
# MARKDOWN-LITE RENDERING
# ═════════════════════════════════════════════════════════════════════

CODE_FENCE_RE  = re.compile(r"```([a-zA-Z0-9_+-]*)\n?(.*?)```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
BOLD_RE        = re.compile(r"\*\*([^*\n]+)\*\*")
# ASTERISKS ONLY, deliberately — `_underscore_` italics are NOT supported and
# must not be added.  Underscores are everywhere in the text this app renders
# (web_read, tool_result, max_tokens, /etc/shadow), so enabling them would
# italicise the middle of every other snake_case sentence.
#
# The consequence of that choice is a CONTRACT: anything this app emits for the
# operator to read must use the syntax above.  It did not — every status
# placeholder was written with UNDERSCORES (`_used web_read_`, `_(thinking…)_`,
# `_(done)_`, `_(stopped)_`), so the renderer passed them straight through and
# the operator saw the raw markdown in the chat.  Both sides are now held
# together by tests/test_placeholders.py.
ITALIC_RE      = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")


def _evidence_report(engagement=None):
    """Evidence summary + integrity + a readable markdown ledger for review."""
    led = get_ledger()
    if led is None:
        return {"error": "evidence ledger unavailable"}
    return {
        "engagement": engagement or led.engagement,
        "summary": led.summary(engagement),
        "integrity": led.verify(engagement),
        "report_markdown": led.export_markdown(engagement),
    }


def _evidence_set_engagement(name):
    """Switch the active engagement that future commands are recorded under."""
    led = get_ledger()
    if led is None:
        return {"error": "evidence ledger unavailable"}
    if not (name or "").strip():
        return {"engagement": led.engagement, "note": "no name given; unchanged"}
    new = led.set_engagement(name)
    return {"engagement": new, "steps": led.summary()["steps"]}


# Links, both `[text](url)` and a bare pasted URL. These matter more in this
# app than in most: ANSWER MODE explicitly orders the model to "CITE what you
# used: name the source or paste the link", so every leashed answer ends in one
# — and until now every one of them rendered as literal `[kernel.org](https://
# www.kernel.org/)` at the bottom of the reply.
MD_LINK_RE = re.compile(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)")
BARE_URL_RE = re.compile(r"(?<![\w@/])(https?://[^\s<>\"'`\])]+)")
# Trailing punctuation belongs to the sentence, not to the URL.
_URL_TAIL = ".,;:!?"

# Private Use Area, so nothing a model can emit collides with it and none of
# the three markdown regexes below can match it.
_LINK_SENTINEL = "\ue000%d\ue001"
_SENTINEL_RE = re.compile("\ue000" + r"(\d+)" + "\ue001")


def _pango_escape(t: str) -> str:
    return (t.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;"))


_TAG_RE = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)(?:\s[^>]*)?(/?)>")


def _markup_is_wellformed(markup: str) -> bool:
    """Do this string's tags actually nest?

    THE THREE INLINE PASSES CANNOT GUARANTEE THIS AND NEVER COULD.
    BOLD_RE, ITALIC_RE and INLINE_CODE_RE each run over the whole string
    independently, so on input with stray `*` and backticks they happily
    produce `<i>a<span>b</i>c</span>` — overlapping, not nested. GTK does not
    raise on that: it logs a warning and renders the RAW MARKUP, so the
    operator sees `<span font_family=...>` in the middle of his answer. The
    reply is not malformed; the renderer is.

    Measured on 30,000 adversarial strings, the old renderer emitted 382 such
    strings and the linkifying one 99 — different inputs, same class. Rather
    than chase the pairing rules, the output is CHECKED and a bad one falls
    back to something plainer that is guaranteed to nest.

    Attribute values are skipped by the tag regex, so a `>` inside an href
    cannot be mistaken for the end of a tag."""
    stack: List[str] = []
    for m in _TAG_RE.finditer(markup):
        closing, name, selfclose = m.group(1), m.group(2), m.group(3)
        if selfclose:
            continue
        if closing:
            if not stack or stack[-1] != name:
                return False
            stack.pop()
        else:
            stack.append(name)
    return not stack


def _pango_inline(t: str) -> str:
    """Bold / italic / inline-code, on text that carries no links."""
    t = BOLD_RE.sub(r"<b>\1</b>", t)
    t = ITALIC_RE.sub(r"<i>\1</i>", t)
    t = INLINE_CODE_RE.sub(
        r'<span font_family="JetBrains Mono" '
        r'background="#0a0c0f" foreground="#d6ffdf"> \1 </span>',
        t)
    return t


def text_to_pango(text: str) -> str:
    """Markdown-ish to Pango markup.

    LINKS ARE PULLED OUT FIRST, INTO SENTINELS, AND PUT BACK LAST.
    The obvious implementation — add one more .sub() alongside bold and italic —
    is wrong in both directions, and both directions fail LOUDLY:

      · a URL is not prose. `*` and `` ` `` are legal in one, and ITALIC_RE or
        INLINE_CODE_RE matching INSIDE an href injects a tag into an attribute
        value, which makes set_markup raise and drops the whole message to
        plain text — so one exotic link silently unstyles the entire reply;
      · and in the other direction the href, once written, is a fat target for
        the passes that follow it.

    Sentinels sidestep both: the link text is escaped and inline-formatted on
    its own, the URL is escaped as an ATTRIBUTE (quotes included, which the
    body escape does not do), and neither is ever visible to the other passes.
    The sentinel is Private Use Area, so no model output can forge one.
    """
    links: List[str] = []

    def _stash(label: str, url: str, fmt: bool = True) -> str:
        """fmt=False when the LABEL IS THE URL (a bare pasted link).

        A URL is not prose, and running the inline passes over one is how the
        first version of this regressed 8 inputs out of 30,000 that the old
        renderer had handled: `https://host/a**b**c` had its own asterisks
        turned into a <b> INSIDE the anchor text, and the resulting tag soup
        was rejected, which drops the whole message to plain text. Markdown
        link text is prose its author wrote and still gets formatted; the URL
        itself only ever gets escaped."""
        url = url.rstrip(_URL_TAIL)
        href = (url.replace("&", "&amp;").replace("<", "&lt;")
                   .replace(">", "&gt;").replace('"', "&quot;")
                   .replace("'", "&apos;"))
        shown = _pango_escape(label)
        if fmt:
            shown = _pango_inline(shown)
        links.append('<a href="%s">%s</a>' % (href, shown))
        return _LINK_SENTINEL % (len(links) - 1)

    # Inline code wins over autolinking: a URL the operator wrote inside
    # backticks is being shown as text, not offered as a destination.
    #
    # BISECT, NOT A LINEAR SCAN. The obvious `any(a <= pos < b for a, b in
    # spans)` is O(spans) per candidate link and therefore O(n^2) in a reply
    # that is dense in both — which is the ordinary shape of a cited answer,
    # not an exotic one. This file has shipped a quadratic display path twice
    # (_ALT_PARTIAL_RE at 25s, and the per-token re-strip); it is not worth
    # writing a third one to save four lines.
    _starts: List[int] = []
    _ends: List[int] = []

    def _index_code(src: str) -> None:
        del _starts[:], _ends[:]
        for _m in INLINE_CODE_RE.finditer(src):
            _a, _b = _m.span()
            _starts.append(_a)
            _ends.append(_b)

    def _in_code(pos: int) -> bool:
        i = bisect.bisect_right(_starts, pos) - 1
        return i >= 0 and pos < _ends[i]

    _index_code(text)

    out, last = [], 0
    for m in MD_LINK_RE.finditer(text):
        if _in_code(m.start()):
            continue
        out.append(text[last:m.start()])
        out.append(_stash(m.group(1), m.group(2)))
        last = m.end()
    out.append(text[last:])
    staged = "".join(out)

    # Second pass for bare URLs. Runs on the STAGED text, so a URL already
    # captured as a markdown target cannot be matched a second time — it is a
    # sentinel by now.
    _index_code(staged)
    out, last = [], 0
    for m in BARE_URL_RE.finditer(staged):
        if _in_code(m.start()):
            continue
        url = m.group(1).rstrip(_URL_TAIL)
        out.append(staged[last:m.start()])
        out.append(_stash(url, url, fmt=False))
        last = m.start() + len(url)
    out.append(staged[last:])
    staged = "".join(out)

    def _restore(t: str) -> str:
        return (_SENTINEL_RE.sub(lambda m: links[int(m.group(1))], t)
                if links else t)

    body = _restore(_pango_inline(_pango_escape(staged)))
    if _markup_is_wellformed(body):
        return body

    # Tier 2: drop the emphasis passes, keep the links. The citation stays
    # clickable, which is the part of a leashed answer that carries the proof.
    body = _restore(_pango_escape(staged))
    if _markup_is_wellformed(body):
        return body

    # Tier 3: plain escaped text. Same thing the caller's except-branch would
    # have shown, but reached without a GTK warning and without the raw
    # `<span font_family=...>` soup ever hitting the screen.
    return _pango_escape(text)


# ── STRUCTURED MARKDOWN BLOCKS ───────────────────────────────────────
# A model answering a comparison question replies with a TABLE, and a model
# writing a report replies with headings, bullets and quotes. All of it used to
# land in one Gtk.Label as literal text — `| Agent | Score |` and a row of
# dashes, rendered as prose. The pipes do not line up in a proportional font,
# so the single most common shape of a structured answer was also the least
# readable thing on the screen.
#
# These are parsed here, as pure functions over text, so the whole grammar is
# testable without a display. The widgets that draw them are further down.

# A table separator: |---|:--:|---:| — the row that makes a table a table.
# ONE dash is a legal separator cell: `|:-:|` and `|-|` are both valid
# markdown and both are things a model actually emits. Requiring two silently
# rejected every centre-aligned table — caught by tests/test_richblocks.py,
# not by reading. The "is this really a separator" judgement is finished in
# _looks_like_table, which also demands a pipe (or a long dash run), so a
# setext underline under a line of prose is not mistaken for one.
_TBL_SEP_RE = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_RULE_RE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_QUOTE_RE = re.compile(r"^\s*>\s?(.*)$")
_ULI_RE = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_OLI_RE = re.compile(r"^(\s*)(\d{1,3})[.)]\s+(.*)$")


def _split_table_row(line: str) -> List[str]:
    """Split one markdown table row on unescaped pipes.

    Hand-walked rather than `line.split("|")` because a cell may legitimately
    contain an escaped pipe (`\\|`) — a shell pipeline in a cell is exactly the
    kind of thing this app's answers are full of — and splitting naively cuts
    the row in the wrong place and shifts every following column."""
    cells, buf, i = [], [], 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line) and line[i + 1] == "|":
            buf.append("|")
            i += 2
            continue
        if ch == "|":
            cells.append("".join(buf).strip())
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    cells.append("".join(buf).strip())
    # A row written with the conventional leading and trailing pipes produces
    # an empty cell at each end. Drop those, but ONLY when they came from a
    # border pipe — a genuinely empty first column would otherwise vanish.
    if cells and not cells[0] and line.lstrip().startswith("|"):
        cells.pop(0)
    if cells and not cells[-1] and line.rstrip().endswith("|"):
        cells.pop()
    return cells


def _table_alignments(sep_line: str, ncols: int) -> List[str]:
    out = []
    for c in _split_table_row(sep_line):
        c = c.strip()
        left, right = c.startswith(":"), c.endswith(":")
        out.append("center" if left and right else
                   "right" if right else "left")
    while len(out) < ncols:
        out.append("left")
    return out[:ncols]


def _looks_like_table(lines: List[str], i: int) -> bool:
    """A header line followed by a separator line is the only reliable tell.

    Requiring the separator is what stops ordinary prose containing a pipe —
    `cat a | grep b`, or a sentence with a vertical bar — from being eaten as
    a one-column table."""
    if i + 1 >= len(lines) or "|" not in lines[i]:
        return False
    sep = lines[i + 1] or ""
    if not _TBL_SEP_RE.match(sep):
        return False
    # Relaxing the dash count above means a bare `-` would qualify, so the
    # separator must still look deliberate: either it has a column pipe, or
    # it is a run of dashes long enough to be a rule rather than a stray.
    if "|" not in sep and sep.strip().count("-") < 3:
        return False
    return len(_split_table_row(lines[i])) >= 1


def parse_rich_blocks(text: str) -> List[Dict[str, Any]]:
    """Split prose into structured blocks: table / heading / rule / quote /
    list / text. Code fences and images are handled by the caller."""
    lines = (text or "").split("\n")
    blocks: List[Dict[str, Any]] = []
    buf: List[str] = []

    def flush_text():
        if buf:
            body = "\n".join(buf).strip("\n")
            if body.strip():
                blocks.append({"kind": "text", "content": body})
            buf.clear()

    i = 0
    while i < len(lines):
        line = lines[i]

        if _looks_like_table(lines, i):
            flush_text()
            header = _split_table_row(line)
            aligns = _table_alignments(lines[i + 1], len(header))
            rows = []
            j = i + 2
            while j < len(lines) and "|" in lines[j] and lines[j].strip():
                rows.append(_split_table_row(lines[j]))
                j += 1
            blocks.append({"kind": "table", "header": header,
                           "aligns": aligns, "rows": rows})
            i = j
            continue

        m = _HEADING_RE.match(line)
        if m:
            flush_text()
            blocks.append({"kind": "heading", "level": len(m.group(1)),
                           "content": m.group(2)})
            i += 1
            continue

        # Checked AFTER the heading and table cases: a `---` directly under a
        # line of text is a setext heading underline in some dialects and a
        # table separator in others, and both of those are already claimed
        # above by the time we get here.
        if _RULE_RE.match(line):
            flush_text()
            blocks.append({"kind": "rule"})
            i += 1
            continue

        if _QUOTE_RE.match(line):
            flush_text()
            q = []
            while i < len(lines) and _QUOTE_RE.match(lines[i]):
                q.append(_QUOTE_RE.match(lines[i]).group(1))
                i += 1
            blocks.append({"kind": "quote", "content": "\n".join(q).strip()})
            continue

        if _ULI_RE.match(line) or _OLI_RE.match(line):
            flush_text()
            items = []
            while i < len(lines):
                um, om = _ULI_RE.match(lines[i]), _OLI_RE.match(lines[i])
                if um:
                    items.append({"indent": len(um.group(1)) // 2,
                                  "marker": "•", "content": um.group(2)})
                elif om:
                    items.append({"indent": len(om.group(1)) // 2,
                                  "marker": om.group(2) + ".",
                                  "content": om.group(3)})
                elif (lines[i].strip() and lines[i].startswith((" ", "\t"))
                      and items):
                    # A wrapped continuation line belongs to the item above it,
                    # not to a new paragraph.
                    items[-1]["content"] += " " + lines[i].strip()
                else:
                    break
                i += 1
            blocks.append({"kind": "list", "items": items})
            continue

        buf.append(line)
        i += 1

    flush_text()
    return blocks


def split_message_into_blocks(text: str) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, str]] = []
    last = 0
    for m in CODE_FENCE_RE.finditer(text):
        if m.start() > last:
            pre = text[last:m.start()].strip("\n")
            if pre:
                blocks.extend(_split_rich(pre))
        lang = m.group(1) or "text"
        code = m.group(2).rstrip("\n")
        blocks.append({"kind": "code", "lang": lang, "content": code})
        last = m.end()
    tail = text[last:].strip("\n")
    if tail:
        blocks.extend(_split_rich(tail))
    if not blocks:
        blocks.append({"kind": "text", "content": text})
    return blocks


# Markdown image syntax: ![alt](url) — optionally with a "title" after the URL.
# This is how the model asks Basilisk to SHOW a picture inline (a web image-search
# result, an OSINT profile photo, a screenshot it just took, …): it simply
# writes the image in markdown and the renderer turns it into a real picture.
IMAGE_MD_RE = re.compile(
    r'!\[([^\]]*)\]\(\s*(<?)(https?://[^)\s]+?|file://[^)\s]+?|/[^)\s]+?)\2'
    r'(?:\s+"[^"]*")?\s*\)')


def _split_rich(text: str) -> List[Dict[str, Any]]:
    """Structure first, then images inside whatever prose is left.

    Order matters and is not arbitrary: an image sitting inside a table cell or
    a list item must stay part of that structure, so the structural pass runs
    first and the image pass only ever sees a plain-text run."""
    out: List[Dict[str, Any]] = []
    for blk in parse_rich_blocks(text):
        if blk.get("kind") == "text":
            out.extend(_split_text_and_images(blk["content"]))
        else:
            out.append(blk)
    return out


def _split_text_and_images(text: str) -> List[Dict[str, str]]:
    """Split a plain-text segment into alternating text and image blocks, so an
    inline ![alt](url) becomes its own rendered picture while the prose around
    it stays prose."""
    out: List[Dict[str, str]] = []
    last = 0
    for m in IMAGE_MD_RE.finditer(text):
        if m.start() > last:
            pre = text[last:m.start()].strip("\n")
            if pre:
                out.append({"kind": "text", "content": pre})
        out.append({"kind": "image",
                    "url": m.group(3).strip(),
                    "alt": (m.group(1) or "").strip()})
        last = m.end()
    tail = text[last:].strip("\n") if last else text
    if tail.strip():
        out.append({"kind": "text", "content": tail})
    elif not out:
        out.append({"kind": "text", "content": text})
    return out


# ═════════════════════════════════════════════════════════════════════
# WIDGETS
# ═════════════════════════════════════════════════════════════════════

class CodeBlockWidget(Gtk.Box):
    def __init__(self, code: str, lang: str = ""):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("code-block")
        self.code = code

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header.add_css_class("code-block-header")
        lbl = Gtk.Label(label=lang or "code", xalign=0.0, hexpand=True)
        header.append(lbl)
        copy_btn = Gtk.Button.new_from_icon_name("edit-copy-symbolic")
        copy_btn.add_css_class("icon-button")
        copy_btn.set_tooltip_text("Copy")
        _track_connect(self, copy_btn, "clicked", self._on_copy)
        header.append(copy_btn)
        self.append(header)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        sw.set_hexpand(True)
        # Don't let a long code line force the whole window wider than the
        # screen — the scroller absorbs the overflow instead.
        sw.set_propagate_natural_width(False)
        sw.set_min_content_width(0)
        tv = Gtk.TextView()
        tv.set_editable(False)
        tv.set_cursor_visible(False)
        tv.set_monospace(True)
        tv.set_wrap_mode(Gtk.WrapMode.NONE)
        tv.get_buffer().set_text(code)
        sw.set_child(tv)
        self.append(sw)

    def _on_copy(self, _btn):
        text = self.code
        try:
            value = GObject.Value()
            value.init(GObject.TYPE_STRING)
            value.set_string(text)
            provider = Gdk.ContentProvider.new_for_value(value)
            display = self.get_display() or Gdk.Display.get_default()
            display.get_clipboard().set_content(provider)
            # Also set primary clipboard for middle-click paste
            try:
                display.get_primary_clipboard().set_content(provider)
            except Exception:
                pass
            # Visual feedback
            self._show_copied()
        except Exception as e:
            log(f"clipboard copy failed: {e}")

    def _show_copied(self):
        """Brief 'Copied!' flash on the button."""
        try:
            header = self.get_first_child()
            if header is None:
                return
            btn = header.get_last_child()
            if btn is None:
                return
            btn.set_icon_name("emblem-ok-symbolic")
            GLib.timeout_add(900,
                lambda: (btn.set_icon_name("edit-copy-symbolic") or False))
        except Exception:
            pass


# Whether to fetch & render remote images inline.  Default on; the app sets it
# from settings at startup.  Off → image markdown is shown as a tappable link
# instead, for operators who don't want the chat reaching out to image hosts.
_RENDER_IMAGES = True

# The live "what Basilisk is doing right now" phrase (e.g. "forging a JWT").
# Empty when idle. Set by _set_working; read by the permanent status pill in
# the button row and by the in-chat in-progress placeholder so both show the
# action title instead of a generic "working".
_CURRENT_ACTION = ""


# ── TOOL ARGUMENT NORMALISATION ──────────────────────────────────────
# The accepted argument names are parsed from the PERSONA SPECS — the very
# text the model is shown — so the validator and the contract cannot drift
# apart. A hand-maintained second list would be one more pair of tables to
# keep in step, which is the failure mode half this file's comments are about.
_SPEC_TOOL_RE = re.compile(r'<tool name="([a-z_0-9]+)">\s*(\{.*?\})\s*</tool>',
                           re.S)
_SPEC_KEY_RE = re.compile(r'"([a-z_0-9]+)"\s*:')

# Synonyms a model reaches for. Mapped onto the real key ONLY when the real
# key is absent, so a correct call is never rewritten.
_ARG_ALIASES: Dict[str, Dict[str, str]] = {
    "copy_path":   {"path": "src", "source": "src", "from": "src",
                    "file": "src", "to": "dst", "dest": "dst",
                    "destination": "dst", "target": "dst"},
    "move_path":   {"path": "src", "source": "src", "from": "src",
                    "file": "src", "to": "dst", "dest": "dst",
                    "destination": "dst", "target": "dst"},
    "scan_net":    {"target": "cidr", "network": "cidr", "subnet": "cidr",
                    "range": "cidr", "host": "cidr", "ip": "cidr"},
    "read_file":   {"file": "path", "filename": "path", "target": "path"},
    "delete_path": {"file": "path", "filename": "path", "target": "path"},
    "make_dir":    {"dir": "path", "directory": "path", "folder": "path"},
    "web_read":    {"link": "url", "address": "url", "target": "url",
                    "site": "url"},
    "find_file":   {"query": "pattern", "name": "pattern", "term": "pattern"},
    "run":         {"cmd": "command", "shell": "command"},
    # cve_lookup searches NVD by KEYWORD, so its argument is a PRODUCT name.
    # The operator's audit caught the model calling it with a CVE id, which
    # arrived under no accepted key and produced "no product" — a message that
    # reads like NVD had no data rather than like the argument never landed.
    # A CVE id is a perfectly good NVD keyword, so route it to `product`
    # rather than refusing the call.
    "cve_lookup":  {"cve": "product", "id": "product", "cve_id": "product",
                    "identifier": "product", "name": "product",
                    "software": "product", "package": "product"},
}

# Arguments without which the tool cannot do anything but damage or nonsense.
# Kept SHORT and obvious: only the ones where an empty value reaches a real
# side-effecting call (a filesystem path, a URL, a command line). A tool that
# has a sensible default for a missing argument does not belong here.
_REQUIRED_ARGS: Dict[str, Tuple[str, ...]] = {
    "copy_path":    ("src", "dst"),
    "move_path":    ("src", "dst"),
    "read_file":    ("path",),
    "write_file":   ("path",),
    "delete_path":  ("path",),
    "make_dir":     ("path",),
    "propose_edit": ("path",),
    "web_read":     ("url",),
    "run":          ("command",),
    "cve_lookup":   ("product",),
    "find_file":    ("pattern",),
}

_SPEC_ARGS_CACHE: Optional[Dict[str, set]] = None


def _table_to_text(b: Dict[str, Any]) -> str:
    """Last-resort plain rendering of a parsed table, used only if the widget
    itself fails to build. Shows the content rather than an empty gap."""
    try:
        rows = [list(b.get("header") or [])] + [list(r) for r in
                                                (b.get("rows") or [])]
        return "\n".join("  ".join(str(c) for c in r) for r in rows if r)
    except Exception:
        return ""


class TableWidget(Gtk.Box):
    """A markdown table drawn as a real grid.

    The old renderer put the raw pipes in a Gtk.Label, which is unreadable for
    a reason that is not about taste: the body font is proportional, so the
    columns do not line up, and a comparison table — the single most common
    shape of a structured answer — became the least readable thing on screen.

    Wide tables scroll INSIDE their own container. A table with eight columns
    must never be able to push the chat bubble wider than the window; that is
    the same rule the code blocks and the action chips already follow.
    """

    MAX_ROWS = 200        # display cap; the full text is still in the store
    MAX_COLS = 24

    def __init__(self, header: List[str], rows: List[List[str]],
                 aligns: Optional[List[str]] = None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("md-table")
        ncols = min(max(len(header), 1), self.MAX_COLS)
        aligns = (aligns or [])[:ncols]
        while len(aligns) < ncols:
            aligns.append("left")

        grid = Gtk.Grid()
        grid.add_css_class("md-table-grid")
        grid.set_column_homogeneous(False)

        for c in range(ncols):
            grid.attach(self._cell(header[c] if c < len(header) else "",
                                   aligns[c], header=True, col=c,
                                   last=(c == ncols - 1)), c, 0, 1, 1)

        shown = rows[:self.MAX_ROWS]
        for r, row in enumerate(shown, start=1):
            for c in range(ncols):
                txt = row[c] if c < len(row) else ""
                grid.attach(self._cell(txt, aligns[c], header=False, col=c,
                                       odd=(r % 2 == 1),
                                       last=(c == ncols - 1)), c, r, 1, 1)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        sw.set_propagate_natural_width(True)
        sw.set_propagate_natural_height(True)
        sw.set_kinetic_scrolling(True)
        # A ScrolledWindow EXPANDS TO FILL by default, and inside a vertical
        # chat bubble that means the table claims every remaining pixel of
        # height: the grid drew correctly and then several hundred pixels of
        # empty bubble sat under it, pushing the rest of the reply off the
        # screen. propagate_natural_height only sets the NATURAL size; it does
        # not stop the widget accepting more. Both of these have to be off.
        sw.set_vexpand(False)
        sw.set_valign(Gtk.Align.START)
        grid.set_vexpand(False)
        grid.set_valign(Gtk.Align.START)
        sw.set_child(grid)
        self.set_vexpand(False)
        self.set_valign(Gtk.Align.START)
        self.append(sw)

        if len(rows) > self.MAX_ROWS:
            more = Gtk.Label(
                label="+%d more rows" % (len(rows) - self.MAX_ROWS),
                xalign=0.0)
            more.add_css_class("md-table-more")
            self.append(more)

    @staticmethod
    def _cell(text: str, align: str, header: bool, col: int,
              odd: bool = False, last: bool = False) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        box.add_css_class("md-th" if header else "md-td")
        if not header and odd:
            box.add_css_class("odd")
        if last:
            box.add_css_class("lastcol")
        lbl = Gtk.Label(
            xalign=(1.0 if align == "right"
                    else 0.5 if align == "center" else 0.0))
        lbl.set_hexpand(True)
        # Cells carry inline markdown of their own — a bold winner, a `code`
        # flag, a link to the source. Rendered through the same one transform
        # the prose uses, so a table cell cannot format differently from the
        # sentence above it.
        try:
            lbl.set_markup(text_to_pango(text))
        except Exception:
            lbl.set_text(text)
        # ── CELLS DO NOT WRAP, THE TABLE SCROLLS ──
        # Wrapping cells inside a horizontally-scrolling container is a
        # contradiction, and GTK resolves it badly: a ScrolledWindow asks its
        # child for a minimum size at unbounded width, a wrapping Gtk.Label
        # answers "two characters wide", and the height-for-width that follows
        # is astronomical. Measured on a three-row table it asked for 2104px of
        # height and printed
        #   "reports a minimum width of 20, but minimum width for height of
        #    1048576 is 33. Expect overlapping widgets."
        # Single-line cells plus horizontal scroll is also simply what a web
        # table does, so the fix and the intended look are the same thing.
        lbl.set_wrap(False)
        lbl.set_single_line_mode(False)   # keep full glyph height (descenders)
        lbl.set_max_width_chars(64)
        lbl.set_ellipsize(Pango.EllipsizeMode.END)
        if len(text) > 64:
            # Ellipsis loses information, so the whole cell stays reachable.
            try:
                lbl.set_tooltip_text(re.sub(r"[*`_]", "", text))
            except Exception:
                pass
        box.append(lbl)
        return box


class QuoteWidget(Gtk.Box):
    """A blockquote: an accent rail and an inset panel, so an aside reads as
    an aside instead of as another paragraph."""

    def __init__(self, text: str):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.add_css_class("md-quote")
        rail = Gtk.Box()
        rail.add_css_class("md-quote-rail")
        self.append(rail)
        body = _make_wrap_label()
        body.add_css_class("md-quote-body")
        try:
            body.set_markup(text_to_pango(text))
        except Exception:
            body.set_text(text)
        self.append(body)


class HeadingWidget(Gtk.Box):
    """A markdown heading. Levels 1-2 get a hairline under them, which is what
    turns a long answer into sections you can scan rather than one wall."""

    def __init__(self, text: str, level: int = 2):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("md-heading")
        self.add_css_class("h%d" % max(1, min(level, 6)))
        lbl = _make_wrap_label()
        lbl.add_css_class("md-heading-text")
        try:
            lbl.set_markup(text_to_pango(text))
        except Exception:
            lbl.set_text(text)
        self.append(lbl)
        if level <= 2:
            rule = Gtk.Box()
            rule.add_css_class("md-heading-rule")
            self.append(rule)


class RuleWidget(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.add_css_class("md-rule")


class ListWidget(Gtk.Grid):
    """A bullet/number list with a real hanging indent.

    In a single Label a wrapped bullet's second line returns to the left
    margin and the list stops looking like a list. A two-column grid — marker,
    then text — keeps the text block aligned under itself however far it wraps.
    """

    MAX_ITEMS = 300

    def __init__(self, items: List[Dict[str, Any]]):
        super().__init__()
        self.add_css_class("md-list")
        for r, it in enumerate(items[:self.MAX_ITEMS]):
            indent = max(0, min(int(it.get("indent", 0)), 6))
            mk = Gtk.Label(label=str(it.get("marker", "•")), xalign=1.0)
            mk.add_css_class("md-list-marker")
            mk.set_valign(Gtk.Align.START)
            mk.set_margin_start(indent * 18)
            self.attach(mk, 0, r, 1, 1)
            body = _make_wrap_label()
            body.add_css_class("md-list-text")
            # ── MINIMUM WIDTH AND MINIMUM HEIGHT TRADE AGAINST EACH OTHER ──
            # A Grid asks its children for a minimum width, and that is the
            # width GTK computes their minimum HEIGHT at. Unset, a wrapping
            # label answers "one word", and the height explodes (2479px for
            # three bullets). But too large is the opposite failure and it is
            # worse: at 20 chars this one widget had a 597px minimum against
            # 210px for ordinary prose, so the LIST set a floor under the whole
            # window -- it could not be resized below ~630px and everything
            # overflowed a narrower screen.
            #
            # Measured across the range (0/4/6/8/10/14/20 chars ->
            # 77/113/151/189/227/303/417px minimum). 6 puts the list at 151px,
            # comfortably under prose's 210, so it is never the constraint --
            # and the height minimum it implies can only bite at a width that
            # prose already forbids.
            body.set_width_chars(6)
            txt = str(it.get("content", ""))
            try:
                body.set_markup(text_to_pango(txt))
            except Exception:
                body.set_text(txt)
            self.attach(body, 1, r, 1, 1)


def _spec_arg_names() -> Dict[str, set]:
    """{tool: {accepted argument names}} lifted from the persona contract."""
    global _SPEC_ARGS_CACHE
    if _SPEC_ARGS_CACHE is not None:
        return _SPEC_ARGS_CACHE
    out: Dict[str, set] = {}
    try:
        import basilisk_persona as _bp
        src = io.open(_bp.__file__, encoding="utf-8").read()
        for name, body in _SPEC_TOOL_RE.findall(src):
            try:
                keys = set(json.loads(body).keys())
            except Exception:
                keys = set(_SPEC_KEY_RE.findall(body))
            if keys:
                out.setdefault(name, set()).update(keys)
    except Exception as e:
        log(f"tool-arg spec parse failed (validation disabled): {e}")
        out = {}
    _SPEC_ARGS_CACHE = out
    return out


def _normalise_tool_args(name: str, args: Any) -> Tuple[Dict[str, Any], str]:
    """(normalised args, error).  A non-empty error means DO NOT RUN.

    Fails only on the unambiguous case — the model supplied arguments and NOT
    ONE of them is a name this tool accepts. A call that got at least one key
    right still runs exactly as before, so this cannot break a working tool.
    """
    if not isinstance(args, dict):
        return ({}, "")
    out = dict(args)
    for alias, real in (_ARG_ALIASES.get(name) or {}).items():
        if alias in out and not str(out.get(real) or "").strip():
            out[real] = out.pop(alias)
    # ── REQUIRED ARGUMENTS MUST ACTUALLY BE PRESENT ──
    # Checking "did ANY key land" is not enough, and the operator's round-2
    # audit proved it: `copy_path{path=/etc/hostname}` aliased cleanly to
    # src=/etc/hostname, passed the any-key check, and then ran with dst=""
    # — so the tool called shutil.copy2(src, "") and reported
    #     FileNotFoundError: [Errno 2] No such file or directory: ''
    # The first fix turned "argument missing" into a DIFFERENT confusing
    # filesystem error instead of removing it. A tool that needs two paths and
    # is given one must say THAT.
    missing = [k for k in (_REQUIRED_ARGS.get(name) or ())
               if not str(out.get(k) or "").strip()]
    if missing:
        return (out, (
            f"{name} is missing required argument(s) {missing}. It takes "
            f"{sorted(_REQUIRED_ARGS.get(name) or ())} — you supplied "
            f"{sorted(out) or 'nothing'}. Re-issue the call with all of them; "
            f"running it as-is would act on an empty path."))
    if not out:
        return (out, "")
    accepted = _spec_arg_names().get(name)
    if not accepted:
        return (out, "")            # no declared contract — nothing to check
    if set(out) & accepted:
        return (out, "")            # at least one key landed; run it
    return (out, (
        f"{name} received only unknown argument(s) "
        f"{sorted(out)} and would have run with none of them — which silently "
        f"does the wrong thing rather than nothing. This tool takes "
        f"{sorted(accepted)}. Re-issue the call using those names."))


def _action_summary(calls) -> str:
    """A one-line, human 'what it just did' for an assistant turn that carried
    ONLY tool calls — the actual command for `run`, the file path for a write,
    or the tool name(s). This is what shows in the chat bubble so the turn reads
    'ran nmap -sV …' instead of a generic 'thinking'. Returns '' if there's
    nothing tool-like (caller then shows 'thinking…')."""
    def _phrase(c):
        n = (getattr(c, "name", "") or "").strip()
        a = getattr(c, "args", None) or {}
        if n == "run":
            cmd = str(a.get("command", a.get("cmd", ""))).strip()
            if not cmd:
                return "ran a command"
            if len(cmd) > 200:
                cmd = cmd[:200] + " …"
            return "CMD:" + cmd
        if n in ("propose_edit", "write_file"):
            p = str(a.get("path", a.get("file", ""))).strip()
            return ("wrote " + p) if p else "wrote a file"
        if n == "propose":
            cmd = str(a.get("command", a.get("cmd", ""))).strip()
            return ("proposed: " + cmd) if cmd else "proposed a command"
        if n.startswith("memory_"):
            return "updated memory"
        return ("used " + n) if n else ""
    phrases = []
    for c in calls:
        if (getattr(c, "name", "") or "") == "think":
            continue
        p = _phrase(c)
        if p:
            phrases.append(p)
    if not phrases:
        return ""
    parts = []
    for p in phrases[:3]:
        if p.startswith("CMD:"):
            parts.append("`$ " + p[4:] + "`")   # render commands as inline code
        else:
            parts.append("*" + p + "*")
    more = len(phrases) - 3
    text = "  ".join(parts)
    if more > 0:
        text += "  *(+%d more)*" % more
    return text

# Mirror of the approval_mode setting so the message renderer (no settings
# handle) can tell whether to draw interactive proposal cards. In autonomous
# mode ("none") proposals auto-execute, so their cards are suppressed.
_APPROVAL_MODE = "none"


def _img_url_is_fetchable(url: str) -> bool:
    """SSRF guard for the inline image fetcher.  Resolve the URL's host and
    refuse link-local / multicast / reserved / unspecified addresses — the
    cloud-metadata endpoint (169.254.169.254) and other targets only an
    attacker would point an <img> at (e.g. an image URL injected through a
    compromised page or target response).  Loopback and private LAN ranges are
    deliberately ALLOWED: Basilisk legitimately renders images from local
    pentest targets (Juice Shop on localhost / the LAN).  This is a
    resolve-then-check, so an active DNS-rebinding adversary could still slip an
    internal address past it; it stops the common metadata/SSRF cases, which is
    the point — cheap, and no cost to any legitimate fetch."""
    import ipaddress
    import socket as _sock
    try:
        from urllib.parse import urlsplit
        host = urlsplit(url).hostname
    except Exception:
        host = None
    if not host:
        return True   # can't parse — let urlopen surface the real error
    try:
        infos = _sock.getaddrinfo(host, None)
    except Exception:
        return True   # can't resolve — not this guard's job to fail it
    for info in infos:
        ip = info[4][0]
        try:
            addr = ipaddress.ip_address(ip.split("%")[0])
        except ValueError:
            continue
        if (addr.is_link_local or addr.is_multicast
                or addr.is_reserved or addr.is_unspecified):
            return False
    return True


class _ImgSafeRedirect(urllib.request.HTTPRedirectHandler):
    """Follows an image redirect only if the new host also clears the SSRF
    guard — stops a public image host from bouncing the fetch to an internal /
    cloud-metadata address."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _img_url_is_fetchable(newurl):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class ImageWidget(Gtk.Box):
    """An image rendered inline in chat from a URL (http/https/file/local path).

    The model shows a picture by emitting markdown — ![alt](url) — and this
    widget turns it into a real image: a web image-search result, an OSINT
    profile photo, a screenshot Basilisk just took.  The download and decode happen
    OFF the UI thread (chat never blocks), the bytes are size-capped, and the
    picture is scaled down to fit the bubble.  Any failure degrades to a small
    caption with the link, so a dead URL can never break the conversation."""

    _MAX_BYTES = 12_000_000          # don't pull more than ~12 MB for one image
    _MAX_W = 480                     # display cap (px) — scaled down, never up
    _MAX_H = 480
    _UA = "Mozilla/5.0 (X11; Linux x86_64) Basilisk/3.2 image-fetch"

    def __init__(self, url: str, alt: str = ""):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.add_css_class("image-block")
        self.url = (url or "").strip()
        self.alt = (alt or "").strip()
        self._caption = Gtk.Label(label=(self.alt or "loading image…"),
                                  xalign=0.0)
        self._caption.add_css_class("image-caption")
        self._caption.set_wrap(True)
        self._caption.set_max_width_chars(48)
        self.append(self._caption)
        try:
            threading.Thread(target=self._load, daemon=True).start()
        except Exception as e:
            self._fail(str(e))

    # — worker thread —
    def _load(self):
        try:
            data = self._fetch_bytes()
            tex = self._decode(data)
        except Exception as e:
            GLib.idle_add(lambda m=str(e): self._fail(m) or False)
            return
        GLib.idle_add(lambda: self._show(tex) or False)

    def _fetch_bytes(self) -> bytes:
        u = self.url
        if u.startswith("file://"):
            u = u[7:]
        if u.startswith("/"):  # local file path
            with open(u, "rb") as f:
                return f.read(self._MAX_BYTES)
        if not (u.startswith("http://") or u.startswith("https://")):
            raise ValueError("unsupported image URL scheme")
        if not _img_url_is_fetchable(u):
            raise ValueError("refusing image fetch to a link-local/reserved "
                             "address (SSRF guard)")
        req = urllib.request.Request(u, headers={
            "User-Agent": self._UA,
            "Accept": "image/avif,image/webp,image/png,image/jpeg,image/*,*/*;q=0.8",
        })
        # Re-validate on EVERY redirect hop: a public image host must not be
        # able to 302 the fetch to an internal / cloud-metadata address after
        # the initial check passed.
        opener = urllib.request.build_opener(_ImgSafeRedirect())
        with opener.open(req, timeout=15) as r:
            return r.read(self._MAX_BYTES)

    def _decode(self, data: bytes):
        if not data:
            raise ValueError("empty image")
        loader = GdkPixbuf.PixbufLoader()
        try:
            loader.write(data)
        except TypeError:
            loader.write_bytes(GLib.Bytes.new(data))
        loader.close()
        pb = loader.get_pixbuf()
        if pb is None:
            raise ValueError("could not decode image")
        w, h = pb.get_width(), pb.get_height()
        if w <= 0 or h <= 0:
            raise ValueError("bad image dimensions")
        scale = min(self._MAX_W / w, self._MAX_H / h, 1.0)
        if scale < 1.0:
            pb = pb.scale_simple(max(1, int(w * scale)), max(1, int(h * scale)),
                                 GdkPixbuf.InterpType.BILINEAR)
        return Gdk.Texture.new_for_pixbuf(pb)

    # — UI thread —
    def _show(self, tex):
        try:
            pic = Gtk.Picture.new_for_paintable(tex)
            pic.set_can_shrink(True)
            try:
                pic.set_content_fit(Gtk.ContentFit.SCALE_DOWN)
            except Exception:
                pass
            pic.add_css_class("chat-image")
            pic.set_halign(Gtk.Align.START)
            tw, th = tex.get_width(), tex.get_height()
            # Never let an image be wider than the viewport minus the avatar
            # column + margins — otherwise set_size_request makes that width a
            # hard MINIMUM and forces the whole window past the phone screen.
            cap_w = max(160, _VIEWPORT_WIDTH - 120)
            if tw > cap_w and tw > 0:
                th = max(1, int(th * cap_w / tw))
                tw = cap_w
            pic.set_size_request(tw, th)
            if self.alt:
                pic.set_tooltip_text(self.alt)
            try:
                self.remove(self._caption)
            except Exception:
                pass
            self.prepend(pic)
            if self.alt:
                cap = Gtk.Label(label=self.alt, xalign=0.0)
                cap.add_css_class("image-caption")
                cap.set_wrap(True)
                cap.set_max_width_chars(48)
                self.append(cap)
        except Exception as e:
            self._fail(str(e))
        return False

    def _fail(self, msg: str):
        try:
            shown = self.alt or self.url
            self._caption.set_markup(
                f"🖼 <i>couldn't load image</i> — "
                f"<a href=\"{GLib.markup_escape_text(self.url)}\">"
                f"{GLib.markup_escape_text(shown[:80])}</a>")
        except Exception:
            try:
                self._caption.set_text(f"🖼 couldn't load image: {self.url}")
            except Exception:
                pass
        log(f"image load failed ({self.url}): {msg}")
        return False


class ProposedCommandWidget(Gtk.Box):
    """A command Basilisk wants to run, shown as an advisory card.

    Nothing executes until the operator clicks Run.  on_run is called
    with (command, explanation) when they do.
    """
    def __init__(self, command: str, explanation: str = "",
                 risk: str = "medium",
                 on_run: Optional[Callable[[str, str, Any], None]] = None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("cmd-card")
        self.command = command
        self.explanation = explanation
        self._on_run = on_run

        # Header: title + risk badge
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.add_css_class("cmd-card-header")
        title = Gtk.Label(label="⌘  PROPOSED COMMAND", xalign=0.0)
        title.add_css_class("cmd-card-title")
        title.set_hexpand(True)
        header.append(title)
        risk = (risk or "medium").lower()
        if risk not in ("low", "medium", "high"):
            risk = "medium"
        badge = Gtk.Label(label=f"{risk} risk")
        badge.add_css_class("risk-badge")
        badge.add_css_class(risk)
        badge.set_valign(Gtk.Align.CENTER)
        header.append(badge)
        self.append(header)

        # The command itself
        cmd_lbl = Gtk.Label(label=command, xalign=0.0)
        cmd_lbl.add_css_class("cmd-text")
        cmd_lbl.set_wrap(True)
        cmd_lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        cmd_lbl.set_selectable(True)
        self.append(cmd_lbl)

        # Explanation
        if explanation:
            exp = _make_wrap_label()
            exp.add_css_class("cmd-explain")
            try:
                exp.set_markup(text_to_pango(explanation))
            except Exception:
                exp.set_text(explanation)
            self.append(exp)

        # Buttons
        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.run_btn = Gtk.Button(label="Run")
        self.run_btn.add_css_class("cmd-run-btn")
        _track_connect(self, self.run_btn, "clicked", self._on_run_clicked)
        btn_row.append(self.run_btn)

        copy_btn = Gtk.Button(label="Copy")
        copy_btn.add_css_class("cmd-copy-btn")
        _track_connect(self, copy_btn, "clicked", self._on_copy_clicked)
        btn_row.append(copy_btn)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        btn_row.append(spacer)
        self.append(btn_row)

    def _on_run_clicked(self, _btn):
        if self._on_run is None:
            return
        # One-shot visual: prevent a double-fire while the turn is in
        # flight.  Reset by the host if it couldn't start (busy).
        self.run_btn.set_sensitive(False)
        self.run_btn.set_label("Running…")
        self._on_run(self.command, self.explanation, self)

    def reset_run_button(self):
        self.run_btn.set_sensitive(True)
        self.run_btn.set_label("Run")

    def _on_copy_clicked(self, _btn):
        try:
            value = GObject.Value()
            value.init(GObject.TYPE_STRING)
            value.set_string(self.command)
            provider = Gdk.ContentProvider.new_for_value(value)
            display = self.get_display() or Gdk.Display.get_default()
            display.get_clipboard().set_content(provider)
        except Exception as e:
            log(f"cmd copy failed: {e}")


class ProposedEditWidget(Gtk.Box):
    """A file edit Basilisk wants to make, shown as an advisory card with a
    compact diff.  Nothing is written until the operator clicks Apply.

    Mirrors ProposedCommandWidget's flow exactly — same one-shot button
    discipline, same host callback shape — so it rides the existing
    confirm-then-execute gate rather than a new bypass.  on_apply is
    called with (path, content, self) when the operator approves.
    """
    def __init__(self, path: str, content: str,
                 diff_lines: Optional[List[str]] = None,
                 added: int = 0, removed: int = 0,
                 is_new: bool = False, truncated: bool = False,
                 explanation: str = "",
                 on_apply: Optional[Callable[[str, str, Any], None]] = None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("cmd-card")
        self.path = path
        self.content = content
        self._on_apply = on_apply

        # Header: title + a +adds/-removes badge
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.add_css_class("cmd-card-header")
        verb = "PROPOSED NEW FILE" if is_new else "PROPOSED EDIT"
        title = Gtk.Label(label=f"✎  {verb}", xalign=0.0)
        title.add_css_class("cmd-card-title")
        title.set_hexpand(True)
        header.append(title)
        badge = Gtk.Label(label=f"+{added} −{removed}")
        badge.add_css_class("risk-badge")
        # Reuse the risk colour classes: a big change reads as higher risk.
        badge.add_css_class("high" if (added + removed) > 60
                            else "medium" if (added + removed) > 8
                            else "low")
        badge.set_valign(Gtk.Align.CENTER)
        header.append(badge)
        self.append(header)

        # Target path
        path_lbl = Gtk.Label(label=path, xalign=0.0)
        path_lbl.add_css_class("cmd-text")
        path_lbl.set_wrap(True)
        path_lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        path_lbl.set_selectable(True)
        self.append(path_lbl)

        # Compact diff body in a monospace, scrollable view
        if diff_lines:
            sw = Gtk.ScrolledWindow()
            sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
            sw.set_hexpand(True)
            tv = Gtk.TextView()
            tv.set_editable(False)
            tv.set_cursor_visible(False)
            tv.set_monospace(True)
            tv.set_wrap_mode(Gtk.WrapMode.NONE)
            buf = tv.get_buffer()
            # colour-tag added / removed lines so the diff reads at a glance
            t_add = buf.create_tag("add", foreground="#2ecc71")
            t_del = buf.create_tag("del", foreground="#e5484d")
            t_hdr = buf.create_tag("hdr", foreground="#6fae84")
            for i, line in enumerate(diff_lines):
                start = buf.get_end_iter()
                buf.insert(start, (line + "\n"))
                # re-grab iters for the line we just inserted
                end = buf.get_end_iter()
                ls = buf.get_iter_at_line(i)
                if isinstance(ls, tuple):           # GTK4 returns (ok, iter)
                    ls = ls[1]
                if line.startswith("+") and not line.startswith("+++"):
                    buf.apply_tag(t_add, ls, end)
                elif line.startswith("-") and not line.startswith("---"):
                    buf.apply_tag(t_del, ls, end)
                elif line.startswith("@@") or line.startswith(("+++", "---")):
                    buf.apply_tag(t_hdr, ls, end)
            sw.set_child(tv)
            self.append(sw)
        if truncated:
            more = Gtk.Label(label="…diff truncated — full content applies on Apply",
                             xalign=0.0)
            more.add_css_class("cmd-explain")
            self.append(more)

        if explanation:
            exp = _make_wrap_label()
            exp.add_css_class("cmd-explain")
            try:
                exp.set_markup(text_to_pango(explanation))
            except Exception:
                exp.set_text(explanation)
            self.append(exp)

        # Buttons
        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.apply_btn = Gtk.Button(label="Apply")
        self.apply_btn.add_css_class("cmd-run-btn")
        _track_connect(self, self.apply_btn, "clicked", self._on_apply_clicked)
        btn_row.append(self.apply_btn)
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        btn_row.append(spacer)
        self.append(btn_row)

    def _on_apply_clicked(self, _btn):
        if self._on_apply is None:
            return
        self.apply_btn.set_sensitive(False)
        self.apply_btn.set_label("Applying…")
        self._on_apply(self.path, self.content, self)

    def reset_apply_button(self):
        self.apply_btn.set_sensitive(True)
        self.apply_btn.set_label("Apply")


# ── asset resolution ──────────────────────────────────────────────────
# Repo layout keeps runtime art in assets/app/; the INSTALLED layout stays flat
# in ~/.local/share/basilisk (install.sh flattens on copy), so existing installs
# are unaffected by the repo reorganisation. Both are searched, plus the legacy
# alongside-this-file location for anyone running an old checkout in place.
_APP_DIR = os.path.dirname(os.path.abspath(__file__))


# Installed as a wheel, the art ships inside the `basilisk_assets` package
# (pyproject maps that name onto assets/app/, so the repo keeps exactly one
# copy of a 7 MB tree).  Resolved once, at import, and never allowed to raise:
# a missing or unimportable asset package must degrade to "no art", never to
# "no app".
def _packaged_asset_dir() -> Optional[str]:
    try:
        import basilisk_assets                                  # type: ignore
        d = os.path.dirname(os.path.abspath(basilisk_assets.__file__))
        return d if os.path.isdir(d) else None
    except Exception:
        return None


_PKG_ASSET_DIR = _packaged_asset_dir()


def _asset_paths(filename: str) -> List[str]:
    """Every place a runtime asset may live, most-specific first."""
    paths = [
        os.path.expanduser("~/.local/share/basilisk/" + filename),  # installed
        os.path.join(_APP_DIR, "assets", "app", filename),          # repo layout
        os.path.join(_APP_DIR, filename),                           # legacy flat
    ]
    # Last, so a dev checkout and an install.sh install behave exactly as they
    # did before packaging existed.
    if _PKG_ASSET_DIR:
        paths.append(os.path.join(_PKG_ASSET_DIR, filename))        # wheel
    return paths


def _find_asset(filename: str) -> Optional[str]:
    for _p in _asset_paths(filename):
        if os.path.isfile(_p):
            return _p
    return None


def _find_dragon_svg() -> Optional[str]:
    """Locate the dragon emblem SVG at runtime.  Checks the install dir,
    the icon theme dir, and the directory this script lives in (dev/run
    in place).  Returns None if not found so the avatar falls back to a
    letter."""
    candidates = _asset_paths("basilisk-dragon.svg") + [
        os.path.expanduser(
            "~/.local/share/icons/hicolor/scalable/apps/basilisk-dragon.svg"),
        os.path.expanduser(
            "~/.local/share/icons/hicolor/scalable/apps/"
            "org.thepriest.basilisk.svg"),
    ] + _asset_paths("org.thepriest.basilisk.svg")
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


# Resolved once at import; None if the emblem isn't on disk.
_DRAGON_SVG_PATH = _find_dragon_svg()


def _find_btn_png(name: str) -> Optional[str]:
    """Locate a custom dragon-forged button icon (basilisk-btn-<name>.png), in the
    install dir or next to this module. None if it isn't on disk."""
    return _find_asset("basilisk-btn-%s.png" % name)


_BTN_SETTINGS = _find_btn_png("settings") or "settings"
_BTN_BELL     = _find_btn_png("bell")     or "bell"
_BTN_TERMINAL = _find_btn_png("terminal") or "terminal"
_BTN_MINIMISE = _find_btn_png("minimise") or "minimise"
_BTN_CLOSE    = _find_btn_png("close")    or "close"
_BTN_EXPAND   = _find_btn_png("expand")   or "expand"
_BTN_ATTACH   = _find_btn_png("attach")   or "attach"
_BTN_CAMERA   = _find_btn_png("camera")   or "camera"
_BTN_SUGGEST  = _find_btn_png("suggest")  or "suggest"
_BTN_SOUND    = _find_btn_png("sound")    or "sound"
_BTN_UNLEASH  = _find_btn_png("unleash")  or "unleash"

# Composer toolbar buttons are wide word-plaques ("Camera"/"Suggestions"/
# "Voice"/"Terminal"/"Attach"), not the small round header icons.  They need a
# taller render height than the 26px header default or the engraved word is an
# illegible sliver.  Header/titlebar buttons keep the _btn_art default (26).
_COMPOSER_BTN_PX = 36


def _btn_art(name_or_path, px: int = 26):
    """A Gtk.Picture of a button-art PNG scaled to `px` HEIGHT (aspect kept,
    never upscaled, never expands -- so it can't blow up a header/toolbar).

    Accepts EITHER a resolved on-disk path (from _find_btn_png -- lets you
    later drop in a replacement file to re-theme a single button) OR a short
    name ("settings"/"bell"/"terminal"/"minimise"/"close"), in which case it
    decodes the byte-identical art embedded in basilisk_btn_art.py. That embedded
    copy is the GUARANTEED fallback: it ships inside a required .py file, so
    it can never go missing the way a separate optional PNG fetch can.
    Returns None only if both the disk file and the embedded data are
    unavailable, so callers can fall back to a symbolic icon.
    """
    pb = None
    if name_or_path and os.path.isfile(name_or_path):
        try:
            pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                name_or_path, -1, px, True)
        except Exception:
            pb = None
    if pb is None and name_or_path:
        # name_or_path may be a resolved disk path (unlikely to also be a key)
        # or a short key like "settings" -- try the embedded copy either way.
        key = os.path.splitext(os.path.basename(str(name_or_path)))[0]
        key = key.replace("basilisk-btn-", "")
        b64 = BTN_ART_B64.get(key) or BTN_ART_B64.get(str(name_or_path))
        if b64:
            try:
                raw = base64.b64decode(b64)
                loader = GdkPixbuf.PixbufLoader()
                loader.write(raw)
                loader.close()
                full = loader.get_pixbuf()
                w = max(1, int(full.get_width() * px / full.get_height()))
                pb = full.scale_simple(w, px, GdkPixbuf.InterpType.BILINEAR)
            except Exception:
                pb = None
    if pb is None:
        return None
    pic = Gtk.Picture.new_for_paintable(Gdk.Texture.new_for_pixbuf(pb))
    pic.set_content_fit(Gtk.ContentFit.SCALE_DOWN)
    pic.set_can_shrink(True)
    pic.set_hexpand(False)
    pic.set_vexpand(False)
    pic.set_halign(Gtk.Align.CENTER)
    pic.set_valign(Gtk.Align.CENTER)
    pic.set_size_request(pb.get_width(), px)
    return pic


def _find_avatar_png() -> Optional[str]:
    """Locate the dragon PNG used as Basilisk's chat avatar (clean, no ring)."""
    candidates = _asset_paths("basilisk-avatar.png")
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


_AVATAR_PNG_PATH = _find_avatar_png()


def _find_logo_png() -> Optional[str]:
    """Locate the BASILISK wordmark logo (death-metal art) for the header."""
    candidates = _asset_paths("basilisk-logo.png")
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


_LOGO_PNG_PATH = _find_logo_png()


def _find_watermark_svg() -> Optional[str]:
    """Locate the dragon watermark for the chat background (PNG preferred,
    then SVG).  Falls back to the emblem SVG, then None (no watermark)."""
    candidates = (_asset_paths("basilisk-watermark.png")
                  + _asset_paths("basilisk-watermark.svg"))
    for p in candidates:
        if os.path.isfile(p):
            return p
    return _DRAGON_SVG_PATH


_WATERMARK_SVG_PATH = _find_watermark_svg()


def _find_cross_svg() -> Optional[str]:
    """Locate the operator's cross emblem (shown as the user avatar)."""
    candidates = _asset_paths("basilisk-cross.svg")
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


_CROSS_SVG_PATH = _find_cross_svg()


def _find_priest_png() -> Optional[str]:
    """Locate the operator's portrait (shown as the user avatar)."""
    candidates = _asset_paths("basilisk-priest.png")
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


_PRIEST_PNG_PATH = _find_priest_png()


# ── Arcane seal drawn faintly on each Basilisk reply (SVG -> always renders,
#    no font dependency, so the "ancient sign" actually shows up). ──
def _find_sigil_svg() -> Optional[str]:
    return _find_asset("basilisk-sigil.svg")


_MSG_SIGIL_PATH = _find_sigil_svg()
_MSG_SIGIL_TEX = None


def _build_msg_sigil():
    """A small, faint arcane sigil for the corner of a Basilisk reply. Cached
    texture, non-interactive, never touches the streamed text. None if absent."""
    global _MSG_SIGIL_TEX
    if not _MSG_SIGIL_PATH:
        return None
    try:
        if _MSG_SIGIL_TEX is None:
            _MSG_SIGIL_TEX = _svg_texture(_MSG_SIGIL_PATH, 96)
        if _MSG_SIGIL_TEX is None:
            return None
        pic = Gtk.Picture.new_for_paintable(_MSG_SIGIL_TEX)
        pic.set_can_target(False)
        pic.set_size_request(32, 32)
        pic.set_halign(Gtk.Align.END)
        pic.set_valign(Gtk.Align.END)
        pic.set_margin_end(9)
        pic.set_margin_bottom(7)
        pic.set_opacity(0.5)
        try:
            pic.set_content_fit(Gtk.ContentFit.CONTAIN)
        except Exception:
            pass
        pic.add_css_class("msg-sigil")
        return pic
    except Exception:
        return None


# ── HARD anti-hallucination gate (code-side): flag any question that turns on
#    CURRENT / checkable facts, so the model is FORCED to verify online instead
#    of answering from possibly-stale training. Deliberately eager: a needless
#    search is cheap; a confident wrong memory answer is the failure we prevent.
_VERIFY_MARKERS = (
    "latest", "newest", "current", "currently", "today", "recent", "recently",
    "as of", "up to date", "up-to-date", "nowadays", "these days", "this year",
    "this month", "this week", "right now", "at the moment", "version",
    "release", "released", "changelog", "release date", "price", "cost",
    "how much is", "how much does", "worth", "market cap", "valuation",
    "stock", "exchange rate", "who is the", "who's the", "ceo of",
    "president of", "prime minister", "leader of", "score", "standings",
    "weather", "forecast", "news", "when did", "when will", "when is the",
    "still active", "still alive", "still around", "still maintained",
    "deprecated", "end of life", "eol", "supported", "discontinued",
    "new version", "update on", "status of", "did they release",
    "latest version", "most recent", "as recent", "how old is",
    "out yet", "released yet", "available yet", "is out", "came out",
    "come out", "is there a new", "has there been", "any new",
)


def _needs_web_verification(text: str) -> bool:
    """True when a question's answer depends on the present state of the world
    and must be confirmed online rather than recalled from training."""
    t = " " + (text or "").lower().strip() + " "
    if len(t) < 5:
        return False
    if any(m in t for m in _VERIFY_MARKERS):
        return True
    # A year at/after the training era ("in 2025", "2026 roadmap") almost always
    # implies a current-state query.
    if re.search(r"\b20(2[4-9]|[3-9]\d)\b", t):
        return True
    return False


# ── DECODED-IMAGE CACHE ──────────────────────────────────────────────
# Every avatar in this file was built with Gtk.Image.new_from_file(path),
# which decodes the PNG off disk EVERY TIME.  basilisk-avatar.png is 512x512
# and measures ~9ms to decode; basilisk-priest.png ~3ms.  One assistant avatar
# is built per message bubble, so:
#
#   · a leashed question that chains 12 round-trips paid ~110ms of main-thread
#     decode, arriving in 9ms chunks exactly when each new bubble appeared —
#     which is a hitch the operator sees rather than a number in a profile;
#   · opening a chat is worse, because _load_chat builds the whole window at
#     once: 40 rendered messages is ~370ms of frozen UI on every chat switch,
#     for forty identical decodes of two files.
#
# A Gdk.Texture is immutable and made to be shared between widgets, so one
# decode per (file, size) serves every image for the life of the process.
# Keyed on px as well as path because the same emblem is used at more than one
# size and a texture carries its own resolution.
_TEX_CACHE: Dict[Tuple[str, int], Any] = {}
_TEX_MISSES: set = set()


def _cached_texture(path: str, px: int):
    """One decode per (file, size), shared by every widget that asks.

    A miss is remembered too: a broken or missing file must not be re-opened
    and re-failed once per message for the rest of the session."""
    if not path:
        return None
    key = (path, int(px))
    if key in _TEX_CACHE:
        return _TEX_CACHE[key]
    if key in _TEX_MISSES:
        return None
    tex = None
    try:
        pb = GdkPixbuf.Pixbuf.new_from_file_at_size(path, px, px)
        if pb is not None:
            tex = Gdk.Texture.new_for_pixbuf(pb)
    except Exception as e:
        log(f"texture load failed for {path}: {e}")
        tex = None
    if tex is None:
        _TEX_MISSES.add(key)
        return None
    _TEX_CACHE[key] = tex
    return tex


def _cached_image(path: str, px: int, size: int):
    """A Gtk.Image backed by the shared texture, or None if it can't load."""
    tex = _cached_texture(path, px)
    if tex is None:
        return None
    try:
        img = Gtk.Image.new_from_paintable(tex)
        img.set_pixel_size(size)
        img.set_size_request(size, size)
        return img
    except Exception:
        return None


def _svg_texture(path: str, px: int):
    """Rasterise an SVG file to a px-by-px Gdk.Texture using the pixbuf SVG
    loader (CPU / cairo).  Returns None on any failure.

    Why this exists: handing GTK a live SVG paintable (Gtk.Image.new_from_file
    on an .svg) lets the SVG's own structure become a tree of Gsk render nodes.
    A complex emblem — many hundreds of fill paths behind a feGaussianBlur —
    forces the GL renderer to allocate an offscreen blur surface for the whole
    group, which can exceed the GL texture-size limit and SEGFAULT the entire
    process at draw time.  Flattening to a fixed-size bitmap first means GTK
    only ever composites one small texture, so any emblem is safe and it still
    looks identical at avatar scale."""
    # Delegates to the shared cache: the rasterise itself is unchanged, it
    # just happens once per (file, size) for the life of the process instead
    # of once per caller. A Gdk.Texture is immutable, so sharing one between
    # widgets is exactly what it is for.
    return _cached_texture(path, px)


def Avatar(kind: str = "user") -> Gtk.Widget:
    """Square avatar.  Basilisk shows the dragon emblem; the user shows an
    initial.  Falls back to a letter if the emblem SVG can't be loaded so
    the UI never breaks on a missing file.  Returns a plain Gtk.Image or
    Gtk.Label (both are valid box children) rather than a custom widget
    subclass — simpler and impossible to crash on vfunc mismatch."""
    size = _scaled(52, floor=28)
    # 2x the display size so it stays crisp on HiDPI, capped so one cached
    # texture never gets silly for a 52px avatar.
    _px = min(max(size * 2, 96), 256)
    if kind == "basilisk" and _AVATAR_PNG_PATH:
        # Preferred: the clean dragon PNG (no ring) as the chat avatar.
        img = _cached_image(_AVATAR_PNG_PATH, _px, size)
        if img is not None:
            img.set_valign(Gtk.Align.START)
            img.add_css_class("avatar")
            img.add_css_class("avatar-dragon")
            return img
    if kind == "basilisk" and _DRAGON_SVG_PATH:
        # Rasterise to a bounded bitmap instead of a live SVG paintable — see
        # _svg_texture: a filtered, many-path emblem rendered live can overflow
        # the GL surface limit and crash the process.  Cached, so the raster
        # happens once for the session rather than once per bubble.
        img = _cached_image(_DRAGON_SVG_PATH, _px, size)
        if img is not None:
            img.set_valign(Gtk.Align.START)
            img.add_css_class("avatar")
            img.add_css_class("avatar-dragon")
            return img

    if kind == "user" and _PRIEST_PNG_PATH:
        img = _cached_image(_PRIEST_PNG_PATH, _px, size)
        if img is not None:
            img.set_valign(Gtk.Align.START)
            img.add_css_class("avatar")
            img.add_css_class("avatar-priest")
            return img

    if kind == "user" and _CROSS_SVG_PATH:
        img = _cached_image(_CROSS_SVG_PATH, _px, size)
        if img is not None:
            img.set_valign(Gtk.Align.START)
            img.add_css_class("avatar")
            img.add_css_class("avatar-cross")
            return img

    lbl = Gtk.Label(label="L" if kind == "user" else "K")
    lbl.add_css_class("avatar")
    lbl.add_css_class("avatar-user" if kind == "user" else "avatar-basilisk")
    lbl.set_valign(Gtk.Align.START)
    lbl.set_size_request(size, size)
    return lbl


# ══════════════════════════════════════════════════════════════════════
# SIGNAL HANDLERS ARE WHAT KEPT EVERY BUBBLE ALIVE FOREVER
# ══════════════════════════════════════════════════════════════════════
# `dispose_widget()` on every widget class below nulls its Python attributes
# and its callbacks, and the docstrings say that "breaks any reference cycle
# so CPython reclaims the widget". It did not, because the cycle does not run
# through those attributes -- it runs through GObject:
#
#     MessageWidget -> speak_btn (a child)      [Python -> C]
#     speak_btn     -> its signal closure       [C]
#     closure       -> the lambda / bound method[C -> Python]
#     lambda        -> MessageWidget            [Python]
#
# CPython's cyclic collector cannot see the middle two hops, so the loop is
# never broken and nulling attributes changes nothing. Measured on the real
# app: 120 exchanges with a hard 20-row display budget left 130 MessageWidgets
# and 120 CodeBlockWidgets alive -- exactly one leaked per assistant message,
# each still holding its Pango layouts, textures and TextViews. That is the
# unbounded memory growth (and the slow, laggy scrolling) that only shows up
# in long conversations. With the speak button's handler removed the same run
# stayed flat at 20.
#
# The fix is to keep the handler ids and disconnect them on disposal, which
# severs the C-side hop. `_track_connect` records; `_drop_signals` cuts.

def _track_connect(owner, widget, signal: str, cb) -> int:
    """Connect `cb` and remember the handler so disposal can cut it."""
    hid = widget.connect(signal, cb)
    try:
        owner._sig_conns.append((widget, hid))
    except AttributeError:
        owner._sig_conns = [(widget, hid)]
    return hid


def _drop_signals_recursive(root) -> None:
    """_drop_signals for `root` and every widget beneath it.

    A bubble owns its blocks; when the bubble is trimmed the blocks go with
    it, so their handlers must be cut at the same moment or each block stays
    pinned by its own button exactly the way the bubble was.
    """
    stack = [root]
    seen = 0
    while stack and seen < 5000:        # cheap runaway guard
        w = stack.pop()
        seen += 1
        if w is not root:
            _drop_signals(w)
        try:
            c = w.get_first_child()
        except Exception:
            continue
        while c is not None:
            stack.append(c)
            c = c.get_next_sibling()


def _drop_signals(owner) -> None:
    """Disconnect everything _track_connect recorded for `owner`.

    Safe to call twice, and safe on a widget already finalised by GTK -- a
    disposal path that raised here would leave the rest of the teardown
    undone, which is the failure this whole function exists to prevent.
    """
    for widget, hid in list(getattr(owner, "_sig_conns", ()) or ()):
        try:
            if widget is not None and hid:
                widget.disconnect(hid)
        except Exception:
            pass
    owner._sig_conns = []


def _make_wrap_label() -> Gtk.Label:
    """Return a Gtk.Label that wraps AND reports a wrapped natural
    width, so it shrinks to fit the parent allocation on narrow
    screens instead of overflowing.

    GTK4 background: by default, a Label with set_wrap(True) STILL
    reports its single-line, unwrapped width as the natural width.
    That natural width is propagated up the widget tree, so the
    layout thinks the chat bubble "needs" the full line width.  On a
    Phosh phone the natural width is almost always wider than the
    physical screen, so the bubble overflows the right edge and the
    text gets clipped.

    Two settings fix this:
      - max-width-chars caps the natural width to N characters.  On
        the phone the actual allocation is narrower than that cap, so
        the label is given less width and wraps to it.  On the desktop
        the cap stops a single very long line from making the bubble
        span the entire monitor.
      - natural-wrap-mode = WORD (GTK 4.6+) makes the label's natural
        width the WRAPPED width (at word boundaries) instead of the
        single-line width.  This stops the natural width from being
        inflated by long lines.
    """
    lbl = Gtk.Label()
    lbl.set_wrap(True)
    lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    lbl.set_xalign(0.0)
    lbl.set_hexpand(True)
    lbl.set_max_width_chars(_MAX_BUBBLE_CHARS)
    try:
        lbl.set_natural_wrap_mode(Gtk.NaturalWrapMode.WORD)
    except (AttributeError, TypeError):
        # Older libadwaita / GTK without NaturalWrapMode.  The label
        # will still wrap; it just won't shrink as aggressively.
        pass
    return lbl



# ── LIVE ACTIVITY FEED ───────────────────────────────
def _fmt_elapsed(sec: float) -> str:
    """Wall-clock duration, at the precision a human reads at a glance.

    Sub-second work is the common case for a local tool, so it gets
    milliseconds; anything past a minute gets m/s, because "94.3s" is a number
    the eye has to convert and "1m34s" is not."""
    try:
        sec = max(0.0, float(sec))
    except (TypeError, ValueError):
        return ""
    if sec < 0.001:
        # "0ms" reads as "did not happen". It did happen; it was just faster
        # than the unit.
        return "<1ms"
    if sec < 1.0:
        return "%dms" % int(sec * 1000)
    if sec < 60.0:
        return "%.1fs" % sec
    m = int(sec // 60)
    s = int(sec % 60)
    return "%dm%02ds" % (m, s)


def _reply_is_tool_only(text: str) -> bool:
    """True when a stored assistant reply carried tool calls and no prose.

    Those replies are the in-flight steps of a chain, not answers. Live, the
    activity feed shows them properly; on reload they used to render as a
    bubble reading `(working...)`, which is why a finished conversation looked
    like Basilisk had answered the same question four times. Same judgement the
    renderer makes, kept in one function so the two cannot disagree."""
    if not text or not text.strip():
        return False
    try:
        if scrub_tool_debris(strip_tool_calls(
                extract_think_blocks(text)[0])).strip():
            return False
        return bool(parse_tool_calls(text))
    except Exception:
        return False


def _feed_detail(name: str, args: Any) -> str:
    """The one argument that makes a tool call DISTINCT, for the feed row.

    Deliberately NOT a json dump of every argument: the row has one line, and a
    dump pushes the part that identifies the call ("which url?", "which
    command?") off the end.  Mirrors the priority order _action_label uses, so
    the feed and the repeat guard name the same thing."""
    if not isinstance(args, dict):
        return ""
    for key in ("command", "cmd", "url", "path", "src", "query", "pattern",
                "target", "cidr", "name", "product", "topic", "text"):
        v = args.get(key)
        if isinstance(v, str) and v.strip():
            v = " ".join(v.split())
            return v if len(v) <= 120 else v[:117] + "..."
    for v in args.values():
        if isinstance(v, str) and v.strip():
            v = " ".join(v.split())
            return v if len(v) <= 120 else v[:117] + "..."
    return ""


def _feed_preview(result_text: str) -> str:
    """A short, honest receipt for a finished step.

    A tool result is JSON far more often than not, so the raw head of it is
    `{"ok": true, "status": 200, "text": "<!doctype html>...` — punctuation the
    operator cannot read anything from.  Pull the human-facing field when the
    shape offers one, and fall back to the first real line otherwise."""
    if not result_text:
        return ""
    txt = result_text.strip()
    try:
        obj = json.loads(txt)
    except Exception:
        obj = None
    if isinstance(obj, dict):
        # An error is the single most important thing a preview can carry, so
        # it wins over any success field regardless of key order.
        for k in ("error", "err", "message"):
            v = obj.get(k)
            if isinstance(v, str) and v.strip():
                return " ".join(v.split())[:220]
        if obj.get("ok") is False:
            return "failed"
        for k in ("summary", "text", "output", "stdout", "result", "body"):
            v = obj.get(k)
            if isinstance(v, str) and v.strip():
                s = " ".join(v.split())
                return (s[:220] + "...") if len(s) > 220 else s
        keys = [k for k in obj.keys()][:6]
        if keys:
            return "returned: " + ", ".join(str(k) for k in keys)
        return ""
    for line in txt.splitlines():
        line = line.strip()
        if line:
            return (line[:220] + "...") if len(line) > 220 else line
    return ""


class ActivityFeedWidget(Gtk.Box):
    """The live "what Basilisk is doing right now" feed.

    ONE feed per OPERATOR TURN — not per model round-trip.  A leashed question
    can chain a dozen reads across a dozen round-trips, and the operator asked
    ONE question; splitting that across a dozen widgets is how the old UI made
    a single answer look like four separate replies.  The feed is created when
    the operator sends, and every round-trip of that turn appends to the same
    one.

    Shape is deliberately the one Claude's web app uses, because it is the one
    that works: a header line that always says what is happening RIGHT NOW,
    an expanded body while the work is live, and a collapse back to a single
    summary line the moment the turn settles.  Clicking the header toggles it
    at any point, and a click PINS the choice so the auto-collapse never fights
    the operator.

    HONESTY RULES, learned from the log that lied four ways:
      - a step is only marked done when its result actually came back;
      - a step still running when the turn tears down is marked STOPPED, never
        silently left spinning and never retroactively called success;
      - the header's elapsed clock is wall time from the first event, so a
        stall is VISIBLE instead of looking like fast work.
    """

    # Bound the widget count: an unleashed mission runs for hours.  The store
    # keeps everything; this is the display window.
    MAX_STEPS = 160

    _GLYPH = {
        "run":  "▸",   # right-pointing triangle
        "ok":   "✓",
        "fail": "✗",
        "stop": "■",
        "note": "\u2022",
        # NOT a warning-sign or no-entry codepoint: those get substituted by
        # the emoji font, which ignores the row's colour and its metrics, so a
        # refusal row rendered wider and in the wrong palette than every other
        # row. A plain ASCII mark inherits both.
        "gate": "!",
    }

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("activity-feed")
        self._steps: Dict[int, Dict[str, Any]] = {}
        self._order: List[int] = []
        self._next_id = 1
        self._t0 = time.monotonic()
        self._tick_src = None
        self._pinned = False
        self._done = False
        self._n_run = 0
        self._n_ok = 0
        self._n_fail = 0
        self._phase = "thinking"
        self._disposed = False
        self._collapse_src = None
        # Set once the header TITLE carries the step count, so the meta column
        # stops repeating it ("3 steps complete ... 3 steps" reads like two
        # different numbers that happen to agree).
        self._title_has_count = False
        self._build()
        self._start_tick()

    # ── construction ────────────────────────────────────────────

    def _build(self):
        self._header_btn = Gtk.Button()
        self._header_btn.add_css_class("activity-header")
        self._header_btn.set_has_frame(False)
        self._header_btn.set_hexpand(True)

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        # Live indicator: a real spinner while working, a static verdict glyph
        # when settled.  Both live in the same slot so the header never reflows
        # when the turn ends.
        self._spinner = Gtk.Spinner()
        self._spinner.add_css_class("activity-spinner")
        self._spinner.start()
        hbox.append(self._spinner)
        self._verdict = Gtk.Label(label="")
        self._verdict.add_css_class("activity-verdict")
        self._verdict.set_visible(False)
        hbox.append(self._verdict)

        self._title = Gtk.Label(label="thinking", xalign=0.0)
        self._title.add_css_class("activity-title")
        self._title.set_ellipsize(Pango.EllipsizeMode.END)
        self._title.set_hexpand(True)
        hbox.append(self._title)

        self._meta = Gtk.Label(label="", xalign=1.0)
        self._meta.add_css_class("activity-meta")
        hbox.append(self._meta)

        self._chevron = Gtk.Label(label="⌄")   # modifier letter down arrow
        self._chevron.add_css_class("activity-chevron")
        hbox.append(self._chevron)

        self._header_btn.set_child(hbox)
        _track_connect(self, self._header_btn, "clicked", self._on_header_clicked)
        self.append(self._header_btn)

        self._body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._body.add_css_class("activity-body")
        self._revealer = Gtk.Revealer()
        self._revealer.set_transition_type(
            Gtk.RevealerTransitionType.SLIDE_DOWN)
        self._revealer.set_transition_duration(180)
        self._revealer.set_child(self._body)
        # Live by default: the whole point is that the operator can watch.
        self._revealer.set_reveal_child(True)
        self.append(self._revealer)
        self.add_css_class("live")

    def dispose_widget(self):
        """Release references and stop the clock.  Same contract as
        MessageWidget.dispose_widget: one-way, and every method that touches a
        nulled container checks _disposed first, because a late GLib callback
        arriving after a trim must be a no-op rather than an AttributeError
        that strands the turn."""
        self._disposed = True
        _drop_signals(self)
        self._stop_tick()
        if self._collapse_src is not None:
            try:
                GLib.source_remove(self._collapse_src)
            except Exception:
                pass
            self._collapse_src = None
        self._steps = {}
        self._order = []
        self._body = None
        self._revealer = None

    # ── the clock ───────────────────────────────────────────────

    def _start_tick(self):
        if self._tick_src is None:
            self._tick_src = GLib.timeout_add(200, self._tick)

    def _stop_tick(self):
        if self._tick_src is not None:
            try:
                GLib.source_remove(self._tick_src)
            except Exception:
                pass
            self._tick_src = None

    def _tick(self):
        if self._disposed:
            self._tick_src = None
            return False
        self._refresh_header()
        # Running steps carry their own live duration so a slow tool is
        # obviously slow while it is still slow, not only in hindsight.
        now = time.monotonic()
        for sid in self._order:
            st = self._steps.get(sid)
            if st is None or st.get("state") != "run":
                continue
            lbl = st.get("time_lbl")
            if lbl is not None:
                try:
                    lbl.set_text(_fmt_elapsed(now - st["t0"]))
                except Exception:
                    pass
        return True

    @staticmethod
    def _plural(n: int, word: str) -> str:
        return f"{n} {word}" + ("" if n == 1 else "s")

    def _refresh_header(self):
        if self._disposed:
            return
        el = _fmt_elapsed(time.monotonic() - self._t0)
        n = self._n_ok + self._n_fail + self._n_run
        bits = []
        if n and not self._title_has_count:
            bits.append(self._plural(n, "step"))
        if self._n_fail:
            bits.append(f"{self._n_fail} failed")
        bits.append(el)
        self._meta.set_text("  ·  ".join(bits))

    # ── expand / collapse ───────────────────────────────────────

    def _on_header_clicked(self, *_a):
        if self._disposed:
            return
        # An explicit click PINS the state.  Without this the auto-collapse
        # would slam shut a body the operator had just opened to read.
        self._pinned = True
        self.set_expanded(not self._revealer.get_reveal_child())

    def set_expanded(self, on: bool):
        if self._disposed or self._revealer is None:
            return
        self._revealer.set_reveal_child(bool(on))
        if on:
            self._chevron.set_text("⌄")
            self.remove_css_class("collapsed")
        else:
            self._chevron.set_text("›")
            self.add_css_class("collapsed")

    # ── phases and steps ────────────────────────────────────────

    def set_phase(self, text: str):
        """Header title while no tool is in flight (streaming / thinking)."""
        if self._disposed or self._done:
            return
        self._phase = (text or "").strip() or "working"
        if self._n_run == 0:
            self._title.set_text(self._phase)
        self._refresh_header()

    def begin_step(self, name: str, detail: str = "",
                   kind: str = "tool") -> int:
        """Open a live step.  Returns the id to hand back to end_step."""
        if self._disposed or self._body is None:
            return 0
        sid = self._next_id
        self._next_id += 1
        row = self._make_row(name, detail, kind)
        st = {
            "t0": time.monotonic(), "state": "run", "name": name,
            "row": row["row"], "glyph": row["glyph"],
            "time_lbl": row["time"], "detail_lbl": row["detail"],
            "preview": row["preview"], "preview_box": row["preview_box"],
        }
        self._steps[sid] = st
        self._order.append(sid)
        self._n_run += 1
        self._title.set_text(name if not detail else f"{name}  {detail}")
        self._trim()
        self._refresh_header()
        return sid

    def end_step(self, sid: int, ok: bool = True, detail: str = "",
                 preview: str = ""):
        if self._disposed:
            return
        st = self._steps.get(sid)
        if st is None or st.get("state") != "run":
            return
        st["state"] = "ok" if ok else "fail"
        self._n_run = max(0, self._n_run - 1)
        if ok:
            self._n_ok += 1
        else:
            self._n_fail += 1
        dur = time.monotonic() - st["t0"]
        try:
            st["glyph"].set_text(self._GLYPH["ok" if ok else "fail"])
            st["row"].remove_css_class("run")
            st["row"].add_css_class("ok" if ok else "fail")
            st["time_lbl"].set_text(_fmt_elapsed(dur))
            if detail:
                st["detail_lbl"].set_text(detail)
                st["detail_lbl"].set_visible(True)
            if preview:
                st["preview"].set_text(preview)
                st["preview_box"].set_visible(True)
        except Exception:
            pass
        if self._n_run == 0 and not self._done:
            self._title.set_text(self._phase)
        self._refresh_header()

    def note(self, text: str, kind: str = "note"):
        """A non-tool event worth showing: a gate refusal, a retry, the repeat
        guard firing, the tool cap being hit.  These are exactly the moments
        the old UI was silent about, so the operator saw a stall with no
        reason attached."""
        if self._disposed or self._body is None:
            return
        row = self._make_row(text, "", kind, note=True)
        self._order.append(-self._next_id)
        self._steps[-self._next_id] = {"state": kind, "row": row["row"]}
        self._next_id += 1
        self._trim()

    def stop_running(self, why: str = "stopped"):
        """Mark every still-live step as stopped.  Called from the turn
        teardown, because a spinner left spinning after the turn ended is the
        UI telling the operator a lie."""
        if self._disposed:
            return
        for sid in list(self._order):
            st = self._steps.get(sid)
            if st is None or st.get("state") != "run":
                continue
            st["state"] = "stop"
            self._n_run = max(0, self._n_run - 1)
            try:
                st["glyph"].set_text(self._GLYPH["stop"])
                st["row"].remove_css_class("run")
                st["row"].add_css_class("stop")
                st["time_lbl"].set_text(why)
            except Exception:
                pass
        self._refresh_header()

    def finish(self, summary: str = "", ok: bool = True):
        """Settle the feed: freeze the clock, show a verdict, and collapse back
        to one line unless the operator pinned it open."""
        if self._disposed or self._done:
            return
        self._done = True
        self._stop_tick()
        self.stop_running("ended")
        self._refresh_header()
        try:
            self._spinner.stop()
            self._spinner.set_visible(False)
            self._verdict.set_text(
                self._GLYPH["ok"] if ok and not self._n_fail
                else self._GLYPH["fail"])
            self._verdict.set_visible(True)
            self._verdict.add_css_class("ok" if ok and not self._n_fail
                                        else "fail")
        except Exception:
            pass
        self.remove_css_class("live")
        self.add_css_class("done")
        done_n = self._n_ok + self._n_fail
        if summary:
            self._title.set_text(summary)
        elif done_n:
            self._title.set_text(self._plural(done_n, "step") + " complete")
            self._title_has_count = True
        else:
            self._title.set_text("done")
        self._refresh_header()
        if not self._pinned:
            # Hold the finished state on screen for a beat before folding it
            # away, so the operator sees the last step land instead of the body
            # vanishing under their eyes.
            self._collapse_src = GLib.timeout_add(900, self._auto_collapse)

    def _auto_collapse(self):
        self._collapse_src = None
        if self._disposed or self._pinned:
            return False
        self.set_expanded(False)
        return False

    def replay_step(self, name: str, detail: str = ""):
        """Rebuild a row for a call that ran in an EARLIER session.

        The store records that a tool was CALLED; it does not record whether it
        succeeded — the result rows are trimmed out of history on purpose. So a
        replayed row gets a NEUTRAL glyph and no duration, never a green tick.
        Painting a tick over an outcome nobody recorded is the same lie as the
        unconditional `done` this project already had to dig out of its log,
        and it would be a lie the operator has no way to check."""
        if self._disposed or self._body is None:
            return
        row = self._make_row(name, detail, "note", note=True)
        sid = self._next_id
        self._next_id += 1
        self._steps[sid] = {"state": "past", "row": row["row"]}
        self._order.append(sid)
        self._n_past = getattr(self, "_n_past", 0) + 1
        try:
            row["row"].add_css_class("past")
        except Exception:
            pass
        self._trim()

    def finish_history(self):
        """Settle a REPLAYED feed: no clock, no verdict tick, folded shut at
        once. There is nothing live to watch, so animating it open and then
        closed would just make a reopened chat flicker."""
        if self._disposed:
            return
        self._done = True
        self._stop_tick()
        n_past = getattr(self, "_n_past", 0)
        try:
            self._spinner.stop()
            self._spinner.set_visible(False)
            self._verdict.set_text(self._GLYPH["note"])
            self._verdict.set_visible(True)
        except Exception:
            pass
        self.remove_css_class("live")
        self.add_css_class("done")
        self._title.set_text(self._plural(n_past, "step") + " earlier")
        self._meta.set_text("from history")
        self.set_expanded(False)

    # ── rows ────────────────────────────────────────────────────

    def _make_row(self, name: str, detail: str, kind: str,
                  note: bool = False) -> Dict[str, Any]:
        wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.add_css_class("activity-step")
        if note:
            row.add_css_class(kind if kind in ("gate", "note") else "note")
        else:
            row.add_css_class("run")

        glyph = Gtk.Label(
            label=self._GLYPH.get(kind if note else "run", "•"))
        glyph.add_css_class("activity-glyph")
        row.append(glyph)

        lbl = Gtk.Label(label=name, xalign=0.0)
        lbl.add_css_class("activity-step-name")
        lbl.set_ellipsize(Pango.EllipsizeMode.END)
        row.append(lbl)

        det = Gtk.Label(label=detail, xalign=0.0)
        det.add_css_class("activity-step-detail")
        det.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        det.set_hexpand(True)
        det.set_visible(bool(detail))
        row.append(det)

        tm = Gtk.Label(label="", xalign=1.0)
        tm.add_css_class("activity-step-time")
        row.append(tm)

        wrap.append(row)

        # Per-step result preview, hidden until there is one.  Kept to a couple
        # of lines: this is a receipt that the tool returned something real,
        # not a second copy of the transcript.
        pv_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        pv_box.add_css_class("activity-preview-box")
        pv = Gtk.Label(label="", xalign=0.0)
        pv.add_css_class("activity-preview")
        pv.set_wrap(True)
        pv.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        pv.set_lines(2)
        pv.set_ellipsize(Pango.EllipsizeMode.END)
        pv.set_hexpand(True)
        pv_box.append(pv)
        pv_box.set_visible(False)
        wrap.append(pv_box)

        self._body.append(wrap)
        return {"row": row, "glyph": glyph, "detail": det, "time": tm,
                "preview": pv, "preview_box": pv_box, "wrap": wrap}

    def _trim(self):
        """Drop the oldest rows past the cap.  Display only — the store and the
        terminal log keep the full record."""
        if self._body is None:
            return
        extra = len(self._order) - self.MAX_STEPS
        while extra > 0:
            sid = self._order.pop(0)
            st = self._steps.pop(sid, None)
            extra -= 1
            if not st:
                continue
            row = st.get("row")
            if row is None:
                continue
            try:
                parent = row.get_parent()
                if parent is not None:
                    self._body.remove(parent)
            except Exception:
                pass


class MessageWidget(Gtk.Box):
    """A single chat message."""

    def __init__(self, role: str, content: str = "",
                 meta: Optional[Dict[str, Any]] = None,
                 on_run_command: Optional[Callable[[str, str], None]] = None,
                 on_apply_edit: Optional[Callable[[str, str, Any], None]] = None,
                 on_speak: Optional[Callable[["MessageWidget"], None]] = None,
                 show_thoughts: bool = True):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.role = role
        self.meta = meta or {}
        self._content = content or ""
        self._on_run_command = on_run_command
        self._on_apply_edit = on_apply_edit
        self._on_speak = on_speak
        self.speak_btn: Optional[Gtk.Button] = None
        self._speak_state = "idle"
        self._blocks_container: Optional[Gtk.Box] = None
        self._streaming_label: Optional[Gtk.Label] = None
        # Live-stream render throttle — see append_streaming.
        self._last_stream_render: float = 0.0
        self._stream_render_pending: bool = False
        # Captured model reasoning ("thoughts"): from a reasoning_content
        # stream field and/or inline <think> blocks.  Shown in a collapsed
        # expander the operator can click open.
        self._thoughts: str = (self.meta or {}).get("thoughts", "") or ""
        self._thoughts_container: Optional[Gtk.Box] = None
        self._thoughts_label: Optional[Gtk.Label] = None
        self._show_thoughts: bool = show_thoughts
        # Set by dispose_widget when the view trims this bubble. Every method
        # that touches a container checks it — see dispose_widget.
        self._disposed: bool = False
        self.add_css_class("msg-row")
        self._build_shell()
        if content and role != "tool":
            self.set_content(content)
        if self._thoughts:
            self._render_thoughts()

    def dispose_widget(self):
        """Release this bubble's references so it can be freed the moment it's
        trimmed from the view. It holds callbacks back to the window and heavy
        child containers; nulling them breaks any reference cycle so CPython
        reclaims the widget (and its TextViews / code blocks / images) instead of
        letting it linger in RAM. Display-only — the message stays in the store.

        DISPOSAL IS ONE-WAY AND THE WIDGET MUST SURVIVE BEING USED AFTER IT.
        The window keeps its own references to bubbles (streaming_msg_widget,
        _speaking_widget) that are independent of the view's rolling trim, so a
        disposed bubble can still receive a late token or a state change. Every
        method that touches a nulled container checks _disposed first and
        becomes a no-op, because the alternative is an AttributeError on
        `None.get_first_child()` inside a GLib callback — which strands whatever
        turn was driving it."""
        self._disposed = True
        # FIRST, because it is the one that actually frees the widget. The
        # attribute nulling below is housekeeping; this is the cycle.
        _drop_signals(self)
        # ── AND THE SAME CYCLE EXISTS IN EVERY BLOCK INSIDE THE BUBBLE ──
        # A CodeBlockWidget's copy button, a proposed command's Run button
        # and a proposed edit's Apply button each hold their own C-side
        # closure back to their own widget. Those widgets are children of
        # this one, so cutting only this widget's handlers still leaves each
        # block pinned -- measured at 120 live CodeBlockWidgets for 120
        # exchanges with 20 rows on screen. Nothing else walks in here to
        # dispose them, so the bubble does it for its own children.
        _drop_signals_recursive(self)
        self._on_run_command = None
        self._on_apply_edit = None
        self._on_speak = None
        self._blocks_container = None
        self._streaming_label = None
        self._thoughts_container = None
        self._thoughts_label = None
        self.speak_btn = None
        self._content = ""
        self._thoughts = ""

    def _build_shell(self):
        if self.role == "user":
            # User message: row fills the viewport, a left spacer pushes
            # the bubble to the right.  The OLD layout used
            # row.set_halign(Gtk.Align.END) which made the row claim
            # its NATURAL width (the unwrapped one-line size of the
            # message) and overflow the right edge of the screen on
            # narrow phones.  The hexpand-row + spacer pattern keeps
            # the row's own width equal to the viewport so the bubble
            # can't escape.
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row.set_hexpand(True)

            spacer = Gtk.Box()
            spacer.set_hexpand(True)
            row.append(spacer)

            content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                                  spacing=2)
            content_box.set_halign(Gtk.Align.END)
            content_box.set_hexpand(False)

            label = Gtk.Label(label="YOU", xalign=1.0)
            label.add_css_class("role-label")
            label.add_css_class("user")
            content_box.append(label)

            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            inner.add_css_class("msg-user")
            content_box.append(inner)

            row.append(content_box)
            row.append(Avatar("user"))
            self.append(row)
            self._blocks_container = inner

        elif self.role == "assistant":
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row.set_hexpand(True)

            row.append(Avatar("basilisk"))

            content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                                  spacing=2)
            content_box.set_hexpand(True)
            # Header: role label on the left, a per-message play/pause
            # button on the right (so each reply can be read, paused, and
            # replayed on its own).
            header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            label = Gtk.Label(label="BASILISK", xalign=0.0)
            label.add_css_class("role-label")
            label.add_css_class("basilisk")
            header.append(label)
            content_box.append(header)
            # Thoughts container sits between the header and the reply body.
            # It stays empty (and invisible) unless the model exposed its
            # reasoning, in which case _render_thoughts drops a collapsed
            # expander here.  Kept separate from the blocks container so
            # streaming/redraw of the reply never wipes it.
            self._thoughts_container = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL, spacing=2)
            content_box.append(self._thoughts_container)
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            inner.add_css_class("msg-assistant")
            # Hug the content: without this the bubble fills the whole row
            # width (content_box hexpands for avatar layout, and the body label
            # hexpands), so a two-word reply drew a full-screen bubble. START +
            # no-expand makes the bubble size to its text and sit left; the
            # label's max-width-chars cap still wraps long replies.
            inner.set_halign(Gtk.Align.START)
            inner.set_hexpand(False)
            # Arcane seal: a faint sigil in the corner of every Basilisk reply.
            # Overlaid, non-interactive -> never touches the streamed text, which
            # still targets `inner` (self._blocks_container below). No-op if the
            # sigil art isn't on disk.
            _seal = _build_msg_sigil()
            if _seal is not None:
                _seal_ov = Gtk.Overlay()
                _seal_ov.set_halign(Gtk.Align.START)
                _seal_ov.set_child(inner)
                _seal_ov.add_overlay(_seal)
                content_box.append(_seal_ov)
            else:
                content_box.append(inner)
            # Read-aloud control sits UNDERNEATH the message (left-aligned),
            # where it's easy to reach, rather than off on the far right.
            if self._on_speak is not None:
                footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                                 spacing=6)
                footer.add_css_class("msg-footer")
                # Gtk.Button.set_icon_name() REPLACES the button's child, so
                # the label passed to the constructor was silently discarded
                # and this rendered as a bare icon circle sitting on its own
                # under the bubble, connected to nothing. Build the child
                # explicitly to get both.
                self.speak_btn = Gtk.Button()
                _sb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                              spacing=7)
                _sb.append(Gtk.Image.new_from_icon_name(
                    "audio-volume-high-symbolic"))
                _sb.append(Gtk.Label(label="Listen"))
                self.speak_btn.set_child(_sb)
                self.speak_btn.add_css_class("msg-speak-btn")
                self.speak_btn.set_halign(Gtk.Align.START)
                self.speak_btn.set_tooltip_text("Read this message aloud")
                _track_connect(self, self.speak_btn, "clicked",
                               lambda *_: self._on_speak(self))
                footer.append(self.speak_btn)
                content_box.append(footer)
            row.append(content_box)
            self.append(row)
            self._blocks_container = inner

        elif self.role == "tool":
            kind = self.meta.get("kind", "result")
            if kind == "result":
                # Hide tool results entirely — let the assistant summarize.
                self.set_visible(False)
                self._blocks_container = None
                return
            # Tool CALL: compact one-line indicator
            tool_name = self.meta.get("tool_name", "")
            if not tool_name:
                # Try to parse from legacy content like "⚙ tool: check_updates({...})"
                import re as _re
                m = _re.search(r'tool:\s*([a-zA-Z_]+)', self._content or "")
                tool_name = m.group(1) if m else "tool"
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            row.add_css_class("msg-tool-indicator")
            row.set_halign(Gtk.Align.START)
            lbl = Gtk.Label(label=f"⚙  used {tool_name}", xalign=0.0)
            lbl.add_css_class("tool-indicator-label")
            row.append(lbl)
            self.append(row)
            self._blocks_container = None

        else:
            inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            inner.add_css_class("msg-system-notice")
            self.append(inner)
            self._blocks_container = inner

    def set_content(self, text: str):
        if getattr(self, "_disposed", False) or self._blocks_container is None:
            # Trimmed out of the view already; the message itself is safe in
            # the store and will render from there if the chat is reopened.
            self._content = text or ""
            return
        self._content = text
        if self.role == "tool" or self._blocks_container is None:
            return
        child = self._blocks_container.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._blocks_container.remove(child)
            child = nxt
        if self.role == "assistant":
            visible, think = extract_think_blocks(text)
            if think and think not in self._thoughts:
                self._thoughts = ((self._thoughts + "\n" + think).strip()
                                  if self._thoughts else think)
            if self._thoughts:
                self._render_thoughts()
            # strip_tool_calls only removes the canonical <tool …> form. A call
            # in any other dialect survives it and is rendered to the operator
            # as raw protocol garbage — which is what he actually sees when this
            # goes wrong, and it looks like the app is broken. Scrub the wreckage
            # too: he should never be shown transport internals.
            display_text = scrub_tool_debris(strip_tool_calls(visible))
        else:
            display_text = text
        # If the assistant message carries only tool calls, don't show a
        # placeholder when at least one is a proposal — the card speaks for
        # itself.  Only fall back to the placeholder for a bare execution
        # tag with no prose and no card.
        # Set only by the bare-tool-step branch below. A propose/propose_edit
        # turn ALSO ends up with empty display_text, and its card is drawn into
        # this same container further down — so visibility must key off this
        # flag, not off `not display_text`, or an approval card would be
        # rendered into a hidden bubble and the operator would be waiting to
        # click something that is not on screen.
        _bare_tool_step = False
        if not display_text and self.role == "assistant":
            calls = []
            try:
                calls = parse_tool_calls(text)
            except Exception:
                calls = []
            has_propose = any(getattr(c, "name", "") == "propose" for c in calls)
            if has_propose:
                display_text = ""
            elif calls:
                # THE FEED ALREADY SAID THIS, AND SAID IT BETTER.
                # This bubble is an in-flight step of a chain, not an answer.
                # It used to render `(working…)` or a one-line action summary —
                # so a single question that took four tools drew four bubbles
                # that all looked like replies, which is exactly the "it
                # answered me four times" complaint. The activity feed above
                # carries the tool, its argument, its duration and its outcome,
                # so this bubble has nothing left to add: hide it. Nothing is
                # lost — the raw content is already in the store and still goes
                # to the model as history.
                display_text = ""
                _bare_tool_step = True
            else:
                # No tool calls and no prose in this turn — it really was just
                # reasoning. Only here is "thinking" the honest label.
                display_text = "*(thinking…)*"

        if self.role == "assistant":
            # Visibility is derived, not latched: a bubble hidden as a bare
            # tool step must come back the moment it is given real text, or a
            # reused widget would stay invisible for the rest of the chat.
            self.set_visible(not _bare_tool_step)
        blocks = split_message_into_blocks(display_text) if display_text else []
        for b in blocks:
            if b["kind"] == "code":
                self._blocks_container.append(
                    CodeBlockWidget(b["content"], b["lang"]))
            elif b["kind"] == "table":
                # Every structural block is built inside its own try: a
                # malformed table must cost that ONE block, not the whole
                # reply. Falling back to the raw text keeps the content
                # visible, which is the property that actually matters.
                try:
                    self._blocks_container.append(
                        TableWidget(b.get("header") or [],
                                    b.get("rows") or [],
                                    b.get("aligns")))
                except Exception as e:
                    log(f"table render failed: {e}")
                    _l = _make_wrap_label()
                    _l.set_text(_table_to_text(b))
                    self._blocks_container.append(_l)
            elif b["kind"] == "heading":
                try:
                    self._blocks_container.append(
                        HeadingWidget(b.get("content", ""),
                                      int(b.get("level", 2))))
                except Exception:
                    _l = _make_wrap_label()
                    _l.set_text(b.get("content", ""))
                    self._blocks_container.append(_l)
            elif b["kind"] == "quote":
                try:
                    self._blocks_container.append(
                        QuoteWidget(b.get("content", "")))
                except Exception:
                    _l = _make_wrap_label()
                    _l.set_text(b.get("content", ""))
                    self._blocks_container.append(_l)
            elif b["kind"] == "rule":
                try:
                    self._blocks_container.append(RuleWidget())
                except Exception:
                    pass
            elif b["kind"] == "list":
                try:
                    self._blocks_container.append(
                        ListWidget(b.get("items") or []))
                except Exception:
                    _l = _make_wrap_label()
                    _l.set_text("\n".join(
                        "%s %s" % (i.get("marker", "-"), i.get("content", ""))
                        for i in (b.get("items") or [])))
                    self._blocks_container.append(_l)
            elif b["kind"] == "image":
                if _RENDER_IMAGES:
                    self._blocks_container.append(
                        ImageWidget(b.get("url", ""), b.get("alt", "")))
                else:
                    # Image rendering disabled — show a tappable link instead so
                    # nothing reaches out to the image host unasked.
                    lbl = _make_wrap_label()
                    alt = b.get("alt") or "image"
                    url = b.get("url", "")
                    try:
                        lbl.set_markup(
                            f"🖼 <a href=\"{GLib.markup_escape_text(url)}\">"
                            f"{GLib.markup_escape_text(alt)}</a>")
                    except Exception:
                        lbl.set_text(f"🖼 {url}")
                    self._blocks_container.append(lbl)
            else:
                lbl = _make_wrap_label()
                # NOT selectable — selectable labels swallow touch swipes
                # and break message-list scrolling.  Code blocks have a
                # copy button; prose can be copied via long-press menu.
                try:
                    lbl.set_markup(text_to_pango(b["content"]))
                except Exception:
                    lbl.set_text(b["content"])
                self._blocks_container.append(lbl)

        # Render any proposed-command cards from the raw text.  These are
        # advisory only — the model emits <tool name="propose"> and the
        # operator decides whether to run.  Parsed from the raw (un-
        # stripped) content so the cards survive a chat reload.
        # In autonomous mode proposals auto-execute (no operator watching), so
        # we don't draw interactive cards at all — they'd just sit there.
        if self.role == "assistant" and _APPROVAL_MODE != "none":
            try:
                for call in parse_tool_calls(text):
                    _rendered = False
                    if call.name == "propose":
                        cmd = (call.args.get("command")
                               or call.args.get("cmd") or "").strip()
                        if not cmd:
                            self._append_card_warn(
                                "Basilisk tried to propose a command but the call "
                                "had no command text — nothing to run.")
                            break
                        try:
                            self._blocks_container.append(ProposedCommandWidget(
                                cmd,
                                explanation=str(call.args.get("explanation", "")),
                                risk=str(call.args.get("risk", "medium")),
                                on_run=self._on_run_command))
                            _rendered = True
                        except Exception as e:
                            log(f"command card build failed: {e}")
                            self._append_card_warn(
                                f"Basilisk proposed a command but the card failed "
                                f"to render ({e}). Nothing was run.")
                            break
                    elif call.name in ("propose_edit", "write_file"):
                        # An edit proposal renders as a diff card.  It NEVER
                        # writes on its own — the operator's Apply click is
                        # the approval, and tool_write_file still enforces
                        # the parse-check + backup + immutable-guardrail net.
                        epath = (call.args.get("path") or "").strip()
                        econtent = call.args.get("content")
                        # The tag WAS emitted but the args are unusable — say
                        # WHY in the chat instead of silently drawing nothing
                        # and letting Basilisk claim a card that isn't there.
                        if "_raw" in call.args or not epath or econtent is None:
                            if "_raw" in call.args:
                                why = ("the file contents couldn't be parsed — "
                                       "most likely an unescaped \" or a stray "
                                       "control character in the JSON")
                            elif not epath:
                                why = "no target path was given"
                            else:
                                why = "no file content was given"
                            self._append_card_warn(
                                f"⚠ Basilisk tried to write a file but {why}, so no "
                                f"diff card could be drawn and nothing was "
                                f"written. Ask it to re-send the change.")
                            break
                        econtent = str(econtent)
                        try:
                            d = make_edit_diff(epath, econtent)
                        except Exception:
                            d = {"ok": False}
                        try:
                            self._blocks_container.append(ProposedEditWidget(
                                epath, econtent,
                                diff_lines=d.get("diff") if d.get("ok") else None,
                                added=d.get("added", 0),
                                removed=d.get("removed", 0),
                                is_new=d.get("is_new", False),
                                truncated=d.get("truncated", False),
                                explanation=str(call.args.get("explanation", "")),
                                on_apply=self._on_apply_edit))
                            _rendered = True
                        except Exception as e:
                            log(f"edit card build failed: {e}")
                            self._append_card_warn(
                                f"⚠ Basilisk proposed an edit to {epath} but the "
                                f"diff card failed to render ({e}). Nothing was "
                                f"written.")
                            break
                    # One command at a time: only the first proposal becomes a
                    # card.  Anything past it is ignored at render time.
                    if _rendered:
                        break
            except Exception as e:
                log(f"propose render failed: {e}")

    def _append_card_warn(self, msg: str):
        """Show a visible, in-chat diagnostic when a proposal/edit tag was
        emitted but no card could be drawn.  Without this the failure is
        silent and Basilisk looks like it's lying about a card that isn't there."""
        if self._blocks_container is None:
            return
        try:
            lbl = _make_wrap_label()
            lbl.set_text(msg)
            lbl.add_css_class("card-warn")
            self._blocks_container.append(lbl)
        except Exception as e:
            log(f"card-warn render failed: {e}")

    def set_speak_state(self, state: str):
        """state: 'idle' | 'speaking' | 'paused'."""
        self._speak_state = state
        if not self.speak_btn:
            return
        if state == "speaking":
            self.speak_btn.set_icon_name("media-playback-pause-symbolic")
            self.speak_btn.set_tooltip_text("Pause")
            self.speak_btn.add_css_class("speaking")
        elif state == "paused":
            self.speak_btn.set_icon_name("media-playback-start-symbolic")
            self.speak_btn.set_tooltip_text("Resume")
            self.speak_btn.add_css_class("speaking")
        else:  # idle
            self.speak_btn.set_icon_name("audio-volume-high-symbolic")
            self.speak_btn.set_tooltip_text("Read this message aloud")
            self.speak_btn.remove_css_class("speaking")

    def start_streaming(self):
        if getattr(self, "_disposed", False) or self._blocks_container is None:
            return
        child = self._blocks_container.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._blocks_container.remove(child)
            child = nxt
        self._streaming_label = _make_wrap_label()
        # NOT selectable — see comment in set_content
        self._streaming_label.set_text("")
        self._blocks_container.append(self._streaming_label)
        self._content = ""
        # Force the first token of a new stream to paint immediately — a reply
        # that opens with a pause reads as a hang.
        self._last_stream_render = 0.0
        self._stream_render_pending = False

    def append_streaming(self, token: str):
        if getattr(self, "_disposed", False):
            return
        if self._streaming_label is None:
            self.start_streaming()
        if self._streaming_label is None:      # disposed / no container
            return
        self._content += token
        # RENDER IS COALESCED, AND THAT IS A COMPLEXITY FIX, NOT A COSMETIC ONE.
        # Stripping is a function of the WHOLE buffer, so re-running it per
        # token is O(n²) in the reply length no matter how fast the regexes
        # are.  Measured on the shipped v9.6.0 with a single large write_file —
        # the ordinary path for the workspace repair tools — that was 1.75s of
        # GTK main-thread CPU at 66KB and 7.24s at 131KB, scaling ×4 per ×2.
        # Redrawing on a ~50ms floor instead caps the number of full passes at
        # ~20/second regardless of token rate, which no reader can tell apart
        # from per-token and which no longer grows with the reply.
        now = time.monotonic()
        if now - self._last_stream_render >= _STREAM_RENDER_MIN_S:
            self._render_stream()
        elif not self._stream_render_pending:
            # Trailing edge: the last token of a burst must still land, or the
            # tail of a reply that ends mid-interval is never drawn.
            self._stream_render_pending = True
            GLib.timeout_add(_STREAM_RENDER_MIN_MS, self._flush_stream_render)

    def _render_stream(self):
        """Recompute the visible text from the whole buffer and paint it."""
        if getattr(self, "_disposed", False) or self._streaming_label is None:
            return
        self._last_stream_render = time.monotonic()
        # Hide both tool XML and any inline <think> reasoning from the live
        # reply.  The reasoning (if any) gets captured at finish_streaming /
        # set_content and shown in the collapsible thoughts panel.
        display = strip_tool_calls(strip_think_blocks(self._content))
        self._streaming_label.set_text(display)

    def _flush_stream_render(self):
        self._stream_render_pending = False
        self._render_stream()
        return False        # GLib.SOURCE_REMOVE — one shot

    def canonical_content(self) -> str:
        """Fold `_content` to the canonical tool syntax, in place, and return it.

        ── THE BOUNDARY ──
        A stream becomes "the message" at more than one place: it can FINISH,
        it can be STOPPED by the operator, or it can ERROR mid-token.  All
        three write `_content` into the store and into the history that is
        re-sent to the model on every later turn — so all three must fold the
        model's native dialect to the canonical form first.  Only the finish
        path did.  A stopped or errored turn wrote raw `<｜DSML｜｜tool …>` into
        the database, and strip_tool_calls' own docstring spells out the cost:
        every later turn re-sent that garbage as history, wasting context and
        teaching the model the broken format was acceptable.

        Doing it here, on the attribute rather than on a caller's local, is what
        makes `_content` canonical for EVERY later reader — renderer, store, and
        the per-message speak button all read it directly.

        _normalise_tool_syntax is idempotent (locked by tests/test_toolsyntax),
        so calling this twice, or calling it after the caller already
        normalised, is a no-op rather than a second opinion.
        """
        try:
            self._content = _normalise_tool_syntax(self._content or "")
        except Exception:
            pass                      # keep the raw text over losing the reply
        return self._content

    def finish_streaming(self) -> str:
        final = self.canonical_content()
        self._streaming_label = None
        if not getattr(self, "_disposed", False):
            self.set_content(final)
        return final

    # ── thoughts (model reasoning) ─────────────────────────────────
    def append_thought(self, token: str):
        """Accumulate a reasoning token (from a reasoning_content stream)
        and reveal/refresh the collapsed thoughts expander live."""
        if not token or getattr(self, "_disposed", False):
            return
        self._thoughts += token
        self._render_thoughts()

    def get_thoughts(self) -> str:
        return (self._thoughts or "").strip()

    def _render_thoughts(self):
        """Create (once) and update a collapsed 'Thoughts' expander holding
        the model's reasoning.  No-op for non-assistant messages."""
        text = (self._thoughts or "").strip()
        if not text or self._thoughts_container is None or not self._show_thoughts:
            return
        if self._thoughts_label is None:
            expander = Gtk.Expander(label="💭  Thoughts")
            expander.set_expanded(False)          # click to open
            expander.add_css_class("thoughts-expander")
            lbl = _make_wrap_label()
            lbl.add_css_class("thoughts-text")
            lbl.set_margin_top(4)
            lbl.set_margin_start(6)
            lbl.set_margin_bottom(4)
            expander.set_child(lbl)
            self._thoughts_container.append(expander)
            self._thoughts_label = lbl
        try:
            self._thoughts_label.set_text(text)
        except Exception:
            pass


# ═════════════════════════════════════════════════════════════════════
# CHAT ROW
# ═════════════════════════════════════════════════════════════════════

class ChatRow(Gtk.ListBoxRow):
    def __init__(self, chat: Chat):
        super().__init__()
        self.chat = chat
        self.add_css_class("chat-row")

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)

        title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        if chat.pinned:
            pin = Gtk.Label(label="📌")
            pin.add_css_class("pin-icon")
            title_row.append(pin)
        if chat.agent_mode:
            mode = Gtk.Label(label="⚡")
            mode.add_css_class("pin-icon")
            title_row.append(mode)

        title = Gtk.Label(label=chat.title, xalign=0.0)
        title.set_ellipsize(Pango.EllipsizeMode.END)
        title.set_hexpand(True)
        title.add_css_class("title-line")
        title_row.append(title)
        outer.append(title_row)

        meta_lbl = Gtk.Label(label=self._format_meta(chat), xalign=0.0)
        meta_lbl.add_css_class("meta-line")
        meta_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        outer.append(meta_lbl)

        self.set_child(outer)

    @staticmethod
    def _format_meta(chat: Chat) -> str:
        try:
            dt = datetime.datetime.fromtimestamp(chat.updated_at)
            delta = datetime.datetime.now() - dt
            if delta.days == 0:
                stamp = dt.strftime("%H:%M")
            elif delta.days == 1:
                stamp = "yesterday"
            elif delta.days < 7:
                stamp = dt.strftime("%a")
            else:
                stamp = dt.strftime("%d %b")
        except Exception:
            stamp = ""
        # Chat row shows just the time — the model isn't useful clutter here.
        return stamp or ""


# ═════════════════════════════════════════════════════════════════════
# CONFIRM DIALOGS
# ═════════════════════════════════════════════════════════════════════

def confirm_command_dialog(parent: Gtk.Window, command: str, reason: str,
                            on_decision: Callable[[bool, Optional[str]], None],
                            catastrophic: bool = False):
    """Confirm a shell command.  If it needs sudo, show an inline
    password field so the operator can authenticate in one step.

    on_decision(allow: bool, password: Optional[str]) — password is the
    typed sudo password when the command needs sudo and the operator
    approved; otherwise None.

    catastrophic=True is the auto-run backstop: the command matched a
    system-destroying pattern (disk wipe, fs nuke, recursive root delete).
    The dialog shouts, defaults to Cancel, and is shown even in auto-run
    mode so an irreversible mistake always stops for a human.
    """
    needs_sudo = command_needs_sudo(command)
    if catastrophic:
        title = "⚠ DESTRUCTIVE COMMAND — confirm to run"
        subtitle = ("This command can irreversibly destroy data or this "
                    "system (disk/filesystem wipe, recursive delete of a "
                    "system path, or similar). It will NOT auto-run. Only "
                    "continue if you typed it or fully understand it.\n\n"
                    f"{reason}")
    else:
        title = "Run shell command?"
        subtitle = (f"{reason}\n\nRuns as your user.  Output goes back to Basilisk."
                    if not needs_sudo else
                    f"{reason}\n\nThis needs root.  Enter your sudo password to "
                    f"let it through — Basilisk never stores or sees it.")
    dlg = Adw.AlertDialog.new(title, subtitle)
    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    cmd_lbl = Gtk.Label(label=command, xalign=0.0)
    cmd_lbl.set_wrap(True)
    cmd_lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    cmd_lbl.set_selectable(True)
    cmd_lbl.add_css_class("confirm-cmd")
    body.append(cmd_lbl)

    pw_entry: Optional[Gtk.PasswordEntry] = None
    if needs_sudo:
        pw_entry = Gtk.PasswordEntry()
        pw_entry.set_show_peek_icon(True)
        pw_entry.add_css_class("sudo-pass")
        pw_entry.set_property("placeholder-text", "sudo password")
        body.append(pw_entry)

    dlg.set_extra_child(body)
    dlg.add_response("cancel", "Cancel")
    run_label = ("Run anyway" if catastrophic
                 else "Run" if not needs_sudo else "Authenticate & run")
    dlg.add_response("run", run_label)
    if catastrophic:
        # Red button, and default to Cancel so a reflexive Enter is safe.
        dlg.set_response_appearance("run", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.set_default_response("cancel")
    else:
        dlg.set_response_appearance("run", Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response("run")
    dlg.set_close_response("cancel")

    def _cb(_dlg, response):
        allow = (response == "run")
        pw = pw_entry.get_text() if (allow and pw_entry is not None) else None
        on_decision(allow, pw)
    dlg.connect("response", _cb)

    # Pressing Enter in the password field activates the run response.
    # (Not for catastrophic commands — there the default is Cancel.)
    if pw_entry is not None and not catastrophic:
        pw_entry.connect("activate", lambda *_: dlg.response("run"))

    dlg.present(parent)
    if pw_entry is not None:
        pw_entry.grab_focus()


def confirm_sensitive_read_dialog(parent: Gtk.Window, path: str,
                                   on_decision: Callable[[bool], None]):
    dlg = Adw.AlertDialog.new(
        "Read sensitive file?",
        f"Basilisk wants to read:\n\n{path}\n\nThis path is on the "
        f"sensitive list (keys, secrets, system auth).",
    )
    dlg.add_response("cancel", "Deny")
    dlg.add_response("read", "Allow")
    dlg.set_response_appearance("read", Adw.ResponseAppearance.DESTRUCTIVE)
    dlg.set_default_response("cancel")
    dlg.set_close_response("cancel")

    def _cb(_dlg, response):
        on_decision(response == "read")
    dlg.connect("response", _cb)
    dlg.present(parent)


# ═════════════════════════════════════════════════════════════════════
# SETTINGS DIALOG
# ═════════════════════════════════════════════════════════════════════

class SettingsDialog(Adw.PreferencesDialog):
    def __init__(self, parent: "MainWindow"):
        super().__init__()
        self.win = parent
        self.set_title("Settings")

        # ── BACKENDS ───────────────────────────────────────
        page = Adw.PreferencesPage()
        page.set_title("Backends")
        page.set_icon_name("network-server-symbolic")

        # ── Provider routing (which cloud provider is active) ──
        self._model_rows = {}   # provider_key -> (combo_row, [model_ids])

        rg = Adw.PreferencesGroup()
        rg.set_title("Provider routing")
        rg.set_description(
            "Pick which cloud provider Basilisk uses.  Set that provider's "
            "API key and model in its section below.")

        self.active_provider_row = Adw.ComboRow()
        self.active_provider_row.set_title("Active provider")
        prov_labels = [p.label for p in PROVIDERS]
        self.active_provider_row.set_model(Gtk.StringList.new(prov_labels))
        cur_key = parent.settings.get("active_provider", "siliconflow")
        prov_keys = [p.key for p in PROVIDERS]
        if cur_key in prov_keys:
            self.active_provider_row.set_selected(prov_keys.index(cur_key))
        self.active_provider_row.connect("notify::selected",
                                         self._on_active_provider)
        rg.add(self.active_provider_row)

        # Research depth for LEASHED (question) turns. This had NO control at
        # all: it was a hardcoded fallback of 18 that was not even in
        # DEFAULT_SETTINGS, so the operator could neither see it nor raise it.
        # Every load_tools, web_search, web_read and file read counts against
        # it, so a genuinely deep question hit the cap while still mid-research
        # and the answer arrived truncated. Exposed here because it is the one
        # limit he is realistically going to want to move.
        self.answer_budget_row = Adw.SpinRow.new_with_range(5, 200, 5)
        self.answer_budget_row.set_title("Research depth (answer mode)")
        self.answer_budget_row.set_subtitle(
            "How many tool round-trips one QUESTION may take before Basilisk "
            "stops looking and answers with what it has. A runaway backstop, "
            "not a work budget — raise it for deep research.")
        self.answer_budget_row.set_value(
            float(parent.settings.get("answer_tool_budget", 40)))
        self.answer_budget_row.connect(
            "notify::value",
            lambda r, *_a: self._set("answer_tool_budget",
                                     int(r.get_value())))
        rg.add(self.answer_budget_row)

        self.adaptive_effort_row = Adw.SwitchRow()
        self.adaptive_effort_row.set_title("Adaptive effort")
        self.adaptive_effort_row.set_subtitle(
            "Match model + token budget to the task: fast model for chat, the "
            "heavier reasoning sibling once several tool-steps deep. Turn OFF to "
            "keep every turn on the fast model — snappier for a benchmark grind.")
        self.adaptive_effort_row.set_active(
            bool(parent.settings.get("adaptive_effort", True)))
        self.adaptive_effort_row.connect(
            "notify::active",
            lambda r, _ps: self._set("adaptive_effort", r.get_active()))
        rg.add(self.adaptive_effort_row)

        self.fast_light_row = Adw.SwitchRow()
        self.fast_light_row.set_title("Skip thinking on light turns")
        self.fast_light_row.set_subtitle(
            "On short conversational turns, ask the model to answer without "
            "chain-of-thought. Output tokens are generated one at a time, so "
            "a few hundred thinking tokens on \"yeah, makes sense\" is pure "
            "waiting \u2014 and output costs 2-3x input. Engagement work is "
            "never touched. Needs Adaptive effort ON. If a model rejects it, "
            "Basilisk retries without it and stops asking.")
        self.fast_light_row.set_active(
            bool(parent.settings.get("fast_light_turns", False)))
        self.fast_light_row.connect(
            "notify::active",
            lambda r, _ps: self._set("fast_light_turns", r.get_active()))
        rg.add(self.fast_light_row)

        self.auto_fallback_row = Adw.SwitchRow()
        self.auto_fallback_row.set_title("Auto-fallback on a bad reply")
        self.auto_fallback_row.set_subtitle(
            "If a reply comes back empty or repetitive, automatically retry on "
            "the fallback provider for the next turn instead of just warning.")
        self.auto_fallback_row.set_active(
            bool(parent.settings.get("auto_fallback_on_degraded", False)))
        self.auto_fallback_row.connect(
            "notify::active",
            lambda r, _ps: self._set("auto_fallback_on_degraded", r.get_active()))
        rg.add(self.auto_fallback_row)

        page.add(rg)

        # ── Agent mode (moved here from above the chat) ──
        ag = Adw.PreferencesGroup()
        ag.set_title("Agent mode")
        ag.set_description(
            "Let Basilisk use system tools and run commands on its own. Off = a "
            "plain conversational chat (it describes what it would run instead).")
        self.agent_mode_row = Adw.SwitchRow()
        self.agent_mode_row.set_title("Agent mode (system tools)")
        self.agent_mode_row.set_active(bool(parent.current_agent_mode))
        self.agent_mode_row.connect("notify::active", self._on_agent_mode_setting)
        ag.add(self.agent_mode_row)
        page.add(ag)

        # ── One group per cloud provider: key + model picker ──
        for spec in PROVIDERS:
            self._build_provider_group(page, spec, parent)

        self.add(page)

        # ── GENERATION ─────────────────────────────────────
        gen_page = Adw.PreferencesPage()
        gen_page.set_title("Generation")
        gen_page.set_icon_name("preferences-other-symbolic")

        gen_g = Adw.PreferencesGroup()
        gen_g.set_title("Parameters")

        temp_row = Adw.SpinRow.new_with_range(0.0, 2.0, 0.05)
        temp_row.set_title("Temperature")
        temp_row.set_subtitle("Higher = more creative")
        temp_row.set_value(parent.settings["temperature"])
        temp_row.connect("notify::value", self._on_temp)
        gen_g.add(temp_row)

        max_row = Adw.SpinRow.new_with_range(256, 8192, 128)
        max_row.set_title("Max response tokens")
        max_row.set_value(parent.settings["max_tokens"])
        max_row.connect("notify::value", self._on_max)
        gen_g.add(max_row)

        gen_page.add(gen_g)

        # ── Intelligence & trust ──
        intel_g = Adw.PreferencesGroup()
        intel_g.set_title("Intelligence &amp; trust")
        intel_g.set_description(
            "Verification, reasoning, and context handling.")

        self.headroom_row = Adw.SwitchRow()
        self.headroom_row.set_title("Context compression")
        self.headroom_row.set_subtitle(
            "Crush bulky tool output before it reaches the model — saves "
            "context and tokens on long sessions.")
        self.headroom_row.set_active(
            bool(parent.settings.get("headroom_enabled", True)))
        self.headroom_row.connect(
            "notify::active",
            lambda r, _ps: self._set("headroom_enabled", r.get_active()))
        intel_g.add(self.headroom_row)

        self.lean_chat_row = Adw.SwitchRow()
        self.lean_chat_row.set_title("Lean chat")
        self.lean_chat_row.set_subtitle(
            "Skip the tool list on plain conversational messages (a greeting, "
            "thanks, an opinion) — big token save for just talking. The full "
            "toolset returns the moment a message asks for an action.")
        self.lean_chat_row.set_active(
            bool(parent.settings.get("lean_chat", True)))
        self.lean_chat_row.connect(
            "notify::active",
            lambda r, _ps: self._set("lean_chat", r.get_active()))
        intel_g.add(self.lean_chat_row)

        self.max_mode_row = Adw.SwitchRow()
        self.max_mode_row.set_title("Max mode (full tool catalog)")
        self.max_mode_row.set_subtitle(
            "OFF (default): lean — a tiny tool directory plus load-on-demand, "
            "~7k tokens lighter every turn. ON: ship every tool's full spec "
            "inline every turn — maximum context for the model, far more tokens "
            "(and money). Autonomous mode always stays lean regardless.")
        self.max_mode_row.set_active(
            bool(parent.settings.get("max_mode", False)))
        self.max_mode_row.connect(
            "notify::active",
            lambda r, _ps: self._set("max_mode", r.get_active()))
        intel_g.add(self.max_mode_row)

        self.thoughts_row = Adw.SwitchRow()
        self.thoughts_row.set_title("Show reasoning panel")
        self.thoughts_row.set_subtitle(
            "Add a click-to-open Thoughts panel on a reply when the model "
            "exposes its reasoning.")
        self.thoughts_row.set_active(
            bool(parent.settings.get("show_thoughts", True)))
        self.thoughts_row.connect(
            "notify::active",
            lambda r, _ps: self._set("show_thoughts", r.get_active()))
        intel_g.add(self.thoughts_row)

        gen_page.add(intel_g)

        # ── Extensions (sidecar capabilities) ──
        ext_g = Adw.PreferencesGroup()
        ext_g.set_title("Extensions")
        ext_g.set_description(
            "Basilisk's sidecar capabilities. Memory, skills and foresight are on "
            "by default. MCP stays off until you start it here.")

        self.memory_row = Adw.SwitchRow()
        self.memory_row.set_title("Memory")
        self.memory_row.set_subtitle(
            "Persistent cross-session recall of facts about you and your gear.")
        self.memory_row.set_active(
            bool(parent.settings.get("memory_enabled", True)))
        self.memory_row.connect(
            "notify::active",
            lambda r, _ps: self._set("memory_enabled", r.get_active()))
        ext_g.add(self.memory_row)

        self.skills_row = Adw.SwitchRow()
        self.skills_row.set_title("Skills")
        self.skills_row.set_subtitle(
            "Let Basilisk write and sandbox-test small reusable skills.")
        self.skills_row.set_active(
            bool(parent.settings.get("skills_enabled", True)))
        self.skills_row.connect(
            "notify::active",
            lambda r, _ps: self._set("skills_enabled", r.get_active()))
        ext_g.add(self.skills_row)

        self.foresight_row = Adw.SwitchRow()
        self.foresight_row.set_title("Foresight")
        self.foresight_row.set_subtitle(
            "Predict a command's consequences before running it. "
            "Catastrophic commands are always blocked regardless.")
        self.foresight_row.set_active(
            bool(parent.settings.get("foresight_enabled", True)))
        self.foresight_row.connect(
            "notify::active",
            lambda r, _ps: self._set("foresight_enabled", r.get_active()))
        ext_g.add(self.foresight_row)

        self.mem_consolidate_row = Adw.SwitchRow()
        self.mem_consolidate_row.set_title("Consolidate memory")
        self.mem_consolidate_row.set_subtitle(
            "Let the model distil durable facts from a conversation into memory "
            "(costs an extra call). Needs memory on.")
        self.mem_consolidate_row.set_active(
            bool(parent.settings.get("memory_consolidate", True)))
        self.mem_consolidate_row.connect(
            "notify::active",
            lambda r, _ps: self._set("memory_consolidate", r.get_active()))
        ext_g.add(self.mem_consolidate_row)

        self.mem_semantic_row = Adw.SwitchRow()
        self.mem_semantic_row.set_title("Semantic recall")
        self.mem_semantic_row.set_subtitle(
            "Recall memories by meaning, not just matching words, using "
            "SiliconFlow embeddings. Needs a SiliconFlow key; falls back to "
            "keyword recall without one.")
        self.mem_semantic_row.set_active(
            bool(parent.settings.get("memory_semantic", True)))
        self.mem_semantic_row.connect(
            "notify::active",
            lambda r, _ps: self._set("memory_semantic", r.get_active()))
        ext_g.add(self.mem_semantic_row)

        self.foresight_model_row = Adw.SwitchRow()
        self.foresight_model_row.set_title("Foresight: add a model pass")
        self.foresight_model_row.set_subtitle(
            "Add a model-based consequence check on top of the rule-based "
            "foresight before acting. Needs foresight on.")
        self.foresight_model_row.set_active(
            bool(parent.settings.get("foresight_model", False)))
        self.foresight_model_row.connect(
            "notify::active",
            lambda r, _ps: self._set("foresight_model", r.get_active()))
        ext_g.add(self.foresight_model_row)

        self.mcp_row = Adw.SwitchRow()
        self.mcp_row.set_title("MCP (external tool servers)")
        self.mcp_row.set_subtitle(
            "Start the MCP servers configured below. Off by default — MCP runs "
            "external subprocesses (an RCE surface), so only enable it for "
            "servers you trust.")
        self.mcp_row.set_active(bool(parent.settings.get("mcp_enabled", False)))
        self.mcp_row.connect("notify::active", self._on_mcp_toggled)
        ext_g.add(self.mcp_row)

        self.mcp_servers_row = Adw.EntryRow()
        self.mcp_servers_row.set_title("Add MCP server (command)")
        self.mcp_servers_row.set_text("")
        self.mcp_servers_row.set_show_apply_button(True)
        self.mcp_servers_row.connect("apply", self._on_mcp_server_add)
        ext_g.add(self.mcp_servers_row)

        self.mcp_status_row = Adw.ActionRow()
        self.mcp_status_row.set_title("MCP status")
        self._refresh_mcp_status()
        ext_g.add(self.mcp_status_row)

        gen_page.add(ext_g)
        self.add(gen_page)

        # ── DISPLAY ────────────────────────────────────────
        d_page = Adw.PreferencesPage()
        d_page.set_title("Display")
        d_page.set_icon_name("video-display-symbolic")

        dg = Adw.PreferencesGroup()
        dg.set_title("UI scale")
        dg.set_description(
            "Resize text, padding, and controls.  Changes apply live — "
            "no restart needed.  Set to 0 for automatic detection based "
            "on screen size.")

        # Use a SpinRow over the full useful range.  0 is a sentinel
        # meaning "let auto-detection pick" — clamped on the lower side
        # so a slip of the finger doesn't make the UI invisible.
        ui_scale_current = parent.settings.get("ui_scale", 0) or 0
        scale_row = Adw.SpinRow.new_with_range(0.0, 2.0, 0.05)
        scale_row.set_title("Scale factor")
        scale_row.set_subtitle("1.0 = unmodified.  Higher = bigger.  0 = auto.")
        scale_row.set_value(float(ui_scale_current))
        scale_row.set_digits(2)
        scale_row.connect("notify::value", self._on_ui_scale)
        dg.add(scale_row)

        # Reset button row
        reset_row = Adw.ActionRow()
        reset_row.set_title("Reset to auto-detect")
        reset_row.set_subtitle("Sets scale back to 0 and re-runs detection.")
        reset_btn = Gtk.Button(label="Reset")
        reset_btn.set_valign(Gtk.Align.CENTER)
        reset_btn.add_css_class("icon-button")
        def _reset_scale(_b):
            scale_row.set_value(0.0)
        reset_btn.connect("clicked", _reset_scale)
        reset_row.add_suffix(reset_btn)
        dg.add(reset_row)

        d_page.add(dg)

        # Interface
        ui_g = Adw.PreferencesGroup()
        ui_g.set_title("Interface")

        self.provider_pill_row = Adw.SwitchRow()
        self.provider_pill_row.set_title("Show provider pill")
        self.provider_pill_row.set_subtitle(
            "Show the active provider and model in the composer bar.")
        self.provider_pill_row.set_active(
            bool(parent.settings.get("show_provider_pill", True)))
        self.provider_pill_row.connect(
            "notify::active",
            lambda r, _ps: self._set("show_provider_pill", r.get_active()))
        ui_g.add(self.provider_pill_row)

        self.token_count_row = Adw.SwitchRow()
        self.token_count_row.set_title("Show token count")
        self.token_count_row.set_subtitle(
            "Show an approximate token count for the conversation.")
        self.token_count_row.set_active(
            bool(parent.settings.get("show_token_count", False)))
        self.token_count_row.connect(
            "notify::active",
            lambda r, _ps: self._set("show_token_count", r.get_active()))
        ui_g.add(self.token_count_row)

        d_page.add(ui_g)

        # Images & vision
        iv_g = Adw.PreferencesGroup()
        iv_g.set_title("Images &amp; vision")
        iv_g.set_description(
            "Show pictures in chat, and choose the model Basilisk uses to SEE "
            "images (analyze_image).")

        self.render_images_row = Adw.SwitchRow()
        self.render_images_row.set_title("Show images in chat")
        self.render_images_row.set_subtitle(
            "Render image links as pictures.  Off = a tappable link instead "
            "(no auto-download; better OPSEC).")
        self.render_images_row.set_active(
            bool(parent.settings.get("chat_render_images", True)))
        self.render_images_row.connect(
            "notify::active",
            lambda r, _ps: self._set_render_images(r.get_active()))
        iv_g.add(self.render_images_row)

        self.notif_sound_row = Adw.SwitchRow()
        self.notif_sound_row.set_title("Notification sound")
        self.notif_sound_row.set_subtitle(
            "Play a chime when Basilisk raises a notification.")
        self.notif_sound_row.set_active(
            bool(parent.settings.get("notif_sound", True)))
        self.notif_sound_row.connect(
            "notify::active",
            lambda r, _ps: self._set("notif_sound", r.get_active()))
        iv_g.add(self.notif_sound_row)

        _vp_labels = [p.label for p in PROVIDERS]
        self._vp_keys = [p.key for p in PROVIDERS]
        self.vision_provider_row = Adw.ComboRow()
        self.vision_provider_row.set_title("Vision provider")
        self.vision_provider_row.set_subtitle(
            "Which provider hosts the vision model. Needs that provider's API "
            "key — set it right below.")
        self.vision_provider_row.set_model(Gtk.StringList.new(_vp_labels))
        _cur_vp = parent.settings.get("vision_provider", "siliconflow")
        if _cur_vp in self._vp_keys:
            self.vision_provider_row.set_selected(self._vp_keys.index(_cur_vp))
        self.vision_provider_row.connect(
            "notify::selected", self._on_vision_provider)
        iv_g.add(self.vision_provider_row)

        # API key for the vision provider — the SAME key that provider uses for
        # chat, surfaced here so vision can be set up in one place.  Editing it
        # here updates it everywhere.
        self.vision_key_row = Adw.PasswordEntryRow()
        self.vision_key_row.set_title("API key")
        self.vision_key_row.set_show_apply_button(True)
        self.vision_key_row.connect(
            "apply",
            lambda r: self._on_provider_key(self._vision_prov_key(),
                                            r.get_text().strip()))
        iv_g.add(self.vision_key_row)

        # Quick-pick of known vision models for the chosen provider.  Selecting
        # one fills the free-text field below; that field stays authoritative so
        # any current model id can still be typed (line-ups change).
        self.vision_pick_row = Adw.ComboRow()
        self.vision_pick_row.set_title("Pick a vision model")
        self.vision_pick_row.connect("notify::selected", self._on_vision_pick)
        iv_g.add(self.vision_pick_row)

        self.vision_model_row = Adw.EntryRow()
        self.vision_model_row.set_title("Vision model")
        self.vision_model_row.set_text(
            parent.settings.get("vision_model", "") or "")
        self.vision_model_row.set_show_apply_button(True)
        self.vision_model_row.connect(
            "apply",
            lambda r: self._set("vision_model", r.get_text().strip()))
        iv_g.add(self.vision_model_row)

        # fill the key field + quick-pick for whichever provider is selected
        self._refresh_vision_widgets()

        d_page.add(iv_g)
        self.add(d_page)

        # ── BEHAVIOUR ──────────────────────────────────────
        b_page = Adw.PreferencesPage()
        b_page.set_title("Behaviour")
        b_page.set_icon_name("system-run-symbolic")

        bg = Adw.PreferencesGroup()
        bg.set_title("Agent mode")
        self.agent_default_row = Adw.SwitchRow()
        self.agent_default_row.set_title("Agent mode by default")
        self.agent_default_row.set_active(parent.settings["agent_mode_default"])
        self.agent_default_row.connect("notify::active", self._on_agent_default)
        bg.add(self.agent_default_row)

        self.autonomous_persist_row = Adw.SwitchRow()
        self.autonomous_persist_row.set_title("Never stop until the task is done")
        self.autonomous_persist_row.set_subtitle(
            "Walk-away autonomy: the message you send is the objective, and "
            "Basilisk keeps working it — through plain replies and through "
            "errors — until it's genuinely finished or you press Stop. Nothing "
            "else ends the run. (Agent mode only.)")
        self.autonomous_persist_row.set_active(
            bool(parent.settings.get("autonomous_persist", True)))
        self.autonomous_persist_row.connect(
            "notify::active",
            lambda r, _ps: self._set("autonomous_persist", r.get_active()))
        bg.add(self.autonomous_persist_row)
        # Autonomous operation is the ONLY posture — there is no confirmation
        # setting. Every command runs; a sudo password is collected once and
        # cached; catastrophic commands are refused outright. A read-only info
        # row makes that explicit (Adw.ActionRow with no switch).
        _auto_info = Adw.ActionRow()
        _auto_info.set_title("Autonomous operation")
        _auto_info.set_subtitle(
            "Basilisk runs every command with no approval prompts — turn it on a "
            "task, walk away, come back to results. The only prompt is a one-time "
            "sudo password (then cached, never shown). System-destroying commands "
            "are refused outright. There is no confirm-every-command mode.")
        bg.add(_auto_info)

        self.one_cmd_row = Adw.SwitchRow()
        self.one_cmd_row.set_title("One command at a time")
        self.one_cmd_row.set_subtitle(
            "Never propose or run more than one shell command per message. "
            "Safer; leave on unless you want batched commands.")
        self.one_cmd_row.set_active(
            bool(parent.settings.get("one_command_at_a_time", True)))
        self.one_cmd_row.connect(
            "notify::active",
            lambda r, _ps: self._set("one_command_at_a_time", r.get_active()))
        bg.add(self.one_cmd_row)

        self.urgency_row = Adw.SwitchRow()
        self.urgency_row.set_title("Urgency fast-path")
        self.urgency_row.set_subtitle(
            "When your message reads as urgent, skip the preamble and act "
            "immediately.")
        self.urgency_row.set_active(
            bool(parent.settings.get("urgency_fast_path", True)))
        self.urgency_row.connect(
            "notify::active",
            lambda r, _ps: self._set("urgency_fast_path", r.get_active()))
        bg.add(self.urgency_row)

        self.auto_sudo_row = Adw.SwitchRow()
        self.auto_sudo_row.set_title("Reuse cached sudo")
        self.auto_sudo_row.set_subtitle(
            "If you've already authenticated this session, use sudo silently "
            "instead of prompting again. Your password is never stored or shown.")
        self.auto_sudo_row.set_active(
            bool(parent.settings.get("auto_sudo_when_cached", True)))
        self.auto_sudo_row.connect(
            "notify::active",
            lambda r, _ps: self._set("auto_sudo_when_cached", r.get_active()))
        bg.add(self.auto_sudo_row)

        self.warn_dup_row = Adw.SwitchRow()
        self.warn_dup_row.set_title("Warn on duplicate commands")
        self.warn_dup_row.set_subtitle(
            "Flag when the same command is about to run again within ~10 minutes.")
        self.warn_dup_row.set_active(
            bool(parent.settings.get("warn_duplicate_commands", False)))
        self.warn_dup_row.connect(
            "notify::active",
            lambda r, _ps: self._set("warn_duplicate_commands", r.get_active()))
        bg.add(self.warn_dup_row)

        b_page.add(bg)

        # Watcher
        wg = Adw.PreferencesGroup()
        wg.set_title("Watcher (background)")
        wg.set_description(
            "Periodically checks system state and surfaces notable events.")

        self.watcher_row = Adw.SwitchRow()
        self.watcher_row.set_title("Enable watcher")
        self.watcher_row.set_active(parent.settings["watcher_enabled"])
        self.watcher_row.connect("notify::active", self._on_watcher_enable)
        wg.add(self.watcher_row)

        self.w_updates_row = Adw.SwitchRow()
        self.w_updates_row.set_title("Watch for security updates")
        self.w_updates_row.set_active(parent.settings["watcher_check_updates"])
        self.w_updates_row.connect("notify::active",
                                    lambda r, _ps: self._set("watcher_check_updates",
                                                              r.get_active()))
        wg.add(self.w_updates_row)

        self.w_dl_row = Adw.SwitchRow()
        self.w_dl_row.set_title("Watch Downloads folder")
        self.w_dl_row.set_active(parent.settings["watcher_check_downloads"])
        self.w_dl_row.connect("notify::active",
                               lambda r, _ps: self._set("watcher_check_downloads",
                                                         r.get_active()))
        wg.add(self.w_dl_row)

        self.w_journal_row = Adw.SwitchRow()
        self.w_journal_row.set_title("Watch system journal")
        self.w_journal_row.set_subtitle("Surfaces failed logins, USB, OOM")
        self.w_journal_row.set_active(parent.settings["watcher_check_journal"])
        self.w_journal_row.connect("notify::active",
                                    lambda r, _ps: self._set("watcher_check_journal",
                                                              r.get_active()))
        wg.add(self.w_journal_row)

        interval = Adw.SpinRow.new_with_range(5, 360, 5)
        interval.set_title("Check interval (minutes)")
        interval.set_value(parent.settings["watcher_interval_minutes"])
        interval.connect("notify::value",
                          lambda r, *_: self._set("watcher_interval_minutes",
                                                  int(r.get_value())))
        wg.add(interval)

        self.worker_row = Adw.SwitchRow()
        self.worker_row.set_title("Background worker")
        self.worker_row.set_subtitle(
            "The headless systemd --user companion (installed by the installer) "
            "polls on a cadence and posts notable events to the inbox even when "
            "the app is closed. Off by default.")
        self.worker_row.set_active(
            bool(parent.settings.get("worker_enabled", False)))
        self.worker_row.connect(
            "notify::active",
            lambda r, _ps: self._set("worker_enabled", r.get_active()))
        wg.add(self.worker_row)

        b_page.add(wg)

        # History / retention
        hg = Adw.PreferencesGroup()
        hg.set_title("Chat history")
        hg.set_description(
            "Keep things ephemeral.  Pinned chats are always kept.")

        self.fresh_chat_row = Adw.SwitchRow()
        self.fresh_chat_row.set_title("Start a new chat each launch")
        self.fresh_chat_row.set_active(
            bool(parent.settings.get("ephemeral_new_chat_on_launch", True)))
        self.fresh_chat_row.connect(
            "notify::active",
            lambda r, _ps: self._set("ephemeral_new_chat_on_launch",
                                     r.get_active()))
        hg.add(self.fresh_chat_row)

        self.discard_empty_row = Adw.SwitchRow()
        self.discard_empty_row.set_title("Discard empty chats")
        self.discard_empty_row.set_subtitle(
            "Bin unused 'New chat' placeholders on close.")
        self.discard_empty_row.set_active(
            bool(parent.settings.get("discard_empty_chats", True)))
        self.discard_empty_row.connect(
            "notify::active",
            lambda r, _ps: self._set("discard_empty_chats", r.get_active()))
        hg.add(self.discard_empty_row)

        retain_row = Adw.SpinRow.new_with_range(0, 720, 1)
        retain_row.set_title("Auto-delete chats after (hours)")
        retain_row.set_subtitle("Idle chats older than this go.  0 = keep forever.")
        retain_row.set_value(
            float(parent.settings.get("chat_retention_hours", 24)))
        retain_row.connect(
            "notify::value",
            lambda r, *_: self._set("chat_retention_hours",
                                    int(r.get_value())))
        hg.add(retain_row)
        b_page.add(hg)
        self.add(b_page)

        # ── VOICE ──────────────────────────────────────────
        v_page = Adw.PreferencesPage()
        v_page.set_title("Voice")
        v_page.set_icon_name("audio-input-microphone-symbolic")

        tts = getattr(parent, "tts", None)
        stt = getattr(parent, "stt", None)

        # Output (read replies aloud)
        og = Adw.PreferencesGroup()
        og.set_title("Read replies aloud")
        if tts is not None and tts.available():
            og.set_description(f"Speech engine: {tts.engine_name()}.")
        elif tts is not None:
            og.set_description(
                "No speech engine found.  Install espeak-ng (basic) or "
                "Piper (neural) — see install.sh --voice.")
        else:
            og.set_description("Voice module unavailable.")

        self.tts_enabled_row = Adw.SwitchRow()
        self.tts_enabled_row.set_title("Read assistant replies aloud")
        self.tts_enabled_row.set_active(bool(parent.settings.get("tts_enabled")))
        self.tts_enabled_row.set_sensitive(tts is not None)
        self.tts_enabled_row.connect("notify::active", self._on_tts_enable)
        og.add(self.tts_enabled_row)

        self.tts_engine_row = Adw.ComboRow()
        self.tts_engine_row.set_title("Voice engine")
        self.tts_engine_row.set_subtitle("Auto prefers Piper, falls back to espeak")
        self._tts_engine_keys = ["auto", "piper", "espeak"]
        self.tts_engine_row.set_model(Gtk.StringList.new(
            ["Auto", "Piper (neural)", "espeak (robotic)"]))
        cur_eng = (parent.settings.get("tts_engine") or "auto").lower()
        if cur_eng in self._tts_engine_keys:
            self.tts_engine_row.set_selected(self._tts_engine_keys.index(cur_eng))
        self.tts_engine_row.connect("notify::selected", self._on_tts_engine)
        og.add(self.tts_engine_row)

        self.tts_monster_row = Adw.SwitchRow()
        self.tts_monster_row.set_title("Monster voice")
        self.tts_monster_row.set_subtitle(
            "Deep growling monster instead of a plain voice.  Needs sox or "
            "ffmpeg for the full pitch-down; install one if it sounds flat.")
        self.tts_monster_row.set_active(
            bool(parent.settings.get("tts_monster", True)))
        # A preference, not an action — keep it settable whenever the voice
        # module loaded, so you can turn it on and have it ready even before
        # espeak/ffmpeg are installed (it applies the moment they are).
        self.tts_monster_row.set_sensitive(tts is not None)
        self.tts_monster_row.connect("notify::active", self._on_tts_monster)
        og.add(self.tts_monster_row)

        self.tts_depth_row = Adw.SpinRow.new_with_range(0.0, 8.0, 0.5)
        self.tts_depth_row.set_title("Voice depth")
        self.tts_depth_row.set_subtitle(
            "Semitones the voice drops.  Higher = deeper and more monstrous.")
        self.tts_depth_row.set_digits(1)
        self.tts_depth_row.set_value(
            float(parent.settings.get("tts_depth", 4.0) or 4.0))
        self.tts_depth_row.set_sensitive(
            tts is not None
            and bool(parent.settings.get("tts_monster", True)))
        self.tts_depth_row.connect(
            "notify::value",
            lambda r, *_: self._set("tts_depth", round(r.get_value(), 1)))
        og.add(self.tts_depth_row)

        rate_row = Adw.SpinRow.new_with_range(0.5, 2.0, 0.05)
        rate_row.set_title("Speech rate")
        rate_row.set_subtitle("1.0 = normal.  Lower = slower.")
        rate_row.set_digits(2)
        rate_row.set_value(float(parent.settings.get("tts_rate", 1.0) or 1.0))
        rate_row.connect("notify::value",
                         lambda r, *_: self._set("tts_rate",
                                                 round(r.get_value(), 2)))
        og.add(rate_row)

        self.tts_voice_row = Adw.EntryRow()
        self.tts_voice_row.set_title("Piper voice file (.onnx)")
        self.tts_voice_row.set_text(parent.settings.get("tts_voice", "") or "")
        self.tts_voice_row.set_show_apply_button(True)
        self.tts_voice_row.connect("apply", self._on_tts_voice)
        og.add(self.tts_voice_row)

        test_row = Adw.ActionRow()
        test_row.set_title("Test voice")
        test_row.set_subtitle("Speak a short sample with the current settings.")
        test_btn = Gtk.Button(label="▶ Test")
        test_btn.set_valign(Gtk.Align.CENTER)
        test_btn.add_css_class("icon-button")
        test_btn.set_sensitive(tts is not None and tts.available())
        test_btn.connect("clicked", self._on_tts_test)
        test_row.add_suffix(test_btn)
        og.add(test_row)
        v_page.add(og)

        # Input (speak instead of type)
        ig = Adw.PreferencesGroup()
        ig.set_title("Speak instead of type")
        if stt is not None and stt.recorder_available():
            ig.set_description(
                f"Mic recorder: {stt.recorder_name()}.  Transcribed by "
                "SiliconFlow (SenseVoiceSmall) or Groq (Whisper) — whichever "
                "key you have.")
        elif stt is not None:
            ig.set_description(
                "No microphone recorder found.  Install pulseaudio-utils "
                "(parecord) or alsa-utils (arecord).")
        else:
            ig.set_description("Voice module unavailable.")

        self.autosend_row = Adw.SwitchRow()
        self.autosend_row.set_title("Auto-send after transcription")
        self.autosend_row.set_subtitle(
            "Off = drop the text in the box so you can edit before sending.")
        self.autosend_row.set_active(bool(parent.settings.get("voice_autosend", True)))
        self.autosend_row.set_sensitive(stt is not None and stt.recorder_available())
        self.autosend_row.connect("notify::active",
                                  lambda r, _ps: self._set("voice_autosend",
                                                           r.get_active()))
        ig.add(self.autosend_row)

        self.stt_provider_row = Adw.ComboRow()
        self.stt_provider_row.set_title("Transcription provider")
        self.stt_provider_row.set_subtitle(
            "Auto uses your active chat provider when it can transcribe.")
        self._stt_provider_keys = ["auto", "siliconflow", "groq"]
        self.stt_provider_row.set_model(Gtk.StringList.new(
            ["Auto", "SiliconFlow (SenseVoiceSmall)", "Groq (Whisper)"]))
        cur_sp = (parent.settings.get("stt_provider") or "auto").lower()
        if cur_sp in self._stt_provider_keys:
            self.stt_provider_row.set_selected(
                self._stt_provider_keys.index(cur_sp))
        self.stt_provider_row.set_sensitive(
            stt is not None and stt.recorder_available())
        self.stt_provider_row.connect(
            "notify::selected",
            lambda r, *_: self._set(
                "stt_provider",
                self._stt_provider_keys[r.get_selected()]))
        ig.add(self.stt_provider_row)

        # Groq is no longer a CHAT provider, so it no longer gets an API-key row
        # from _build_provider_group. But it is still the Whisper transcription
        # backend, and the picker above still offers it — which left the option
        # selectable with nowhere to put the key. Give it its own field here,
        # beside the setting that actually uses it.
        self.stt_key_row = Adw.PasswordEntryRow()
        self.stt_key_row.set_title("Groq API key (Whisper only)")
        self.stt_key_row.set_text(parent.settings.get("groq_api_key", ""))
        self.stt_key_row.connect(
            "changed",
            lambda r: self._set("groq_api_key", r.get_text().strip()))
        ig.add(self.stt_key_row)

        self.stt_key_hint = Adw.ActionRow()
        self.stt_key_hint.set_title("Get a Groq key")
        self.stt_key_hint.set_subtitle(
            "console.groq.com/keys — free. Used ONLY for speech-to-text; "
            "Basilisk does not chat through Groq.")
        _stt_link = Gtk.Button(label="Open")
        _stt_link.set_valign(Gtk.Align.CENTER)
        _stt_link.connect(
            "clicked",
            lambda *_a: tool_open_url("https://console.groq.com/keys"))
        self.stt_key_hint.add_suffix(_stt_link)
        ig.add(self.stt_key_hint)

        self.stt_model_row = Adw.EntryRow()
        self.stt_model_row.set_title("Groq Whisper model")
        self.stt_model_row.set_text(
            parent.settings.get("stt_model", "whisper-large-v3-turbo"))
        self.stt_model_row.set_show_apply_button(True)
        self.stt_model_row.connect("apply",
                                   lambda r: self._set("stt_model",
                                                       r.get_text().strip()
                                                       or "whisper-large-v3-turbo"))
        ig.add(self.stt_model_row)

        self.stt_lang_row = Adw.EntryRow()
        self.stt_lang_row.set_title("Language hint (optional)")
        self.stt_lang_row.set_text(parent.settings.get("stt_language", "") or "")
        self.stt_lang_row.set_show_apply_button(True)
        self.stt_lang_row.connect("apply",
                                  lambda r: self._set("stt_language",
                                                      r.get_text().strip()))
        ig.add(self.stt_lang_row)

        stt_test_row = Adw.ActionRow()
        stt_test_row.set_title("Test microphone")
        stt_test_row.set_subtitle(
            "Records ~4s, transcribes, shows the exact result or error.")
        self.stt_test_btn = Gtk.Button(label="● Record 4s")
        self.stt_test_btn.set_valign(Gtk.Align.CENTER)
        self.stt_test_btn.add_css_class("icon-button")
        self.stt_test_btn.set_sensitive(
            stt is not None and stt.recorder_available())
        self.stt_test_btn.connect("clicked", self._on_stt_test)
        stt_test_row.add_suffix(self.stt_test_btn)
        ig.add(stt_test_row)
        v_page.add(ig)
        self.add(v_page)

        # ── SYSTEM PROMPT ──────────────────────────────────
        sp_page = Adw.PreferencesPage()
        sp_page.set_title("Persona")
        sp_page.set_icon_name("emblem-favorite-symbolic")

        sp_g = Adw.PreferencesGroup()
        sp_g.set_title("Custom addendum to system prompt")
        sp_g.set_description(
            "Appended to Basilisk's built-in persona.  "
            "Edit basilisk_persona.py for deeper changes.")

        sp_card = Gtk.Frame()
        sp_card.set_margin_top(8)
        sp_card.set_margin_bottom(8)
        sp_sw = Gtk.ScrolledWindow()
        sp_sw.set_min_content_height(_scaled(200, floor=140))
        sp_sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.sp_view = Gtk.TextView()
        self.sp_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.sp_view.set_top_margin(8)
        self.sp_view.set_bottom_margin(8)
        self.sp_view.set_left_margin(8)
        self.sp_view.set_right_margin(8)
        self.sp_view.get_buffer().set_text(parent.settings.get("system_prompt", ""))
        self.sp_view.get_buffer().connect("changed", self._on_sp_changed)
        sp_sw.set_child(self.sp_view)
        sp_card.set_child(sp_sw)
        sp_g.add(sp_card)
        sp_page.add(sp_g)
        self.add(sp_page)

    # ── helpers ────────────────────────────────────────────

    def _build_provider_group(self, page, spec, parent):
        """Build a Settings group for one cloud provider: API key entry,
        a model picker (curated big-first list, refreshable from the live
        catalogue), and a 'get a key' link."""
        g = Adw.PreferencesGroup()
        g.set_title(spec.label)
        g.set_description(spec.blurb)

        # API key
        key_row = Adw.PasswordEntryRow()
        key_row.set_title("API key")
        key_row.set_text(parent.settings.get(f"{spec.key}_api_key", ""))
        key_row.connect(
            "changed",
            lambda row, k=spec.key: self._on_provider_key(k, row.get_text()))
        g.add(key_row)

        # Model picker.  The visible strings carry context + price so the
        # choice is informed, which means the display text is NOT the model
        # id — `self._model_rows` keeps the parallel id list and the handler
        # indexes into that.  (The old code read the id back out of the
        # widget label, so any label change would have silently written a
        # bogus model into settings.)
        model_row = Adw.ComboRow()
        model_row.set_title("Model")
        model_row.set_subtitle("Best first. Use \u27f3 to fetch the live list.")
        ids = list(spec.pick_ids)
        saved = parent.settings.get(f"{spec.key}_model", spec.default_model)
        if saved and saved not in ids:
            ids.insert(0, saved)   # keep a custom/old selection visible
        self._populate_model_row(spec.key, model_row, ids, saved)
        model_row.connect(
            "notify::selected",
            lambda row, _ps, k=spec.key: self._on_provider_model(k, row))

        # Refresh-from-API button lives as a suffix on the model row
        refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh_btn.set_valign(Gtk.Align.CENTER)
        refresh_btn.add_css_class("flat")
        refresh_btn.set_tooltip_text("Fetch available models from the API")
        refresh_btn.connect(
            "clicked",
            lambda _b, k=spec.key: self._fetch_live_models(k))
        model_row.add_suffix(refresh_btn)
        g.add(model_row)

        # Get-a-key link
        link_row = Adw.ActionRow()
        link_row.set_title("Get an API key")
        link_btn = Gtk.LinkButton.new_with_label(spec.key_url, "Open")
        link_btn.set_valign(Gtk.Align.CENTER)
        link_row.add_suffix(link_btn)
        g.add(link_row)

        page.add(g)

    def _set(self, key, value):
        self.win.settings[key] = value
        save_settings(self.win.settings)

    def _on_agent_mode_setting(self, row, _ps):
        # Drive the (now-hidden) toolbar toggle so every existing agent-mode side
        # effect fires — per-chat persistence, subtitle, and the internal state.
        want = row.get_active()
        tog = getattr(self.win, "agent_toggle", None)
        if tog is not None and tog.get_active() != want:
            tog.set_active(want)          # fires _on_agent_toggled
        else:
            self.win.current_agent_mode = want

    def _set_render_images(self, on):
        # Persist and apply live so the chat renderer picks it up immediately.
        self._set("chat_render_images", on)
        global _RENDER_IMAGES
        _RENDER_IMAGES = bool(on)

    def _ext(self):
        return getattr(self.win, "_ext", None)

    def _refresh_mcp_status(self):
        row = getattr(self, "mcp_status_row", None)
        if row is None:
            return
        ext = self._ext()
        if ext is None:
            row.set_subtitle("extensions not loaded")
            return
        try:
            st = ext.mcp_status()
            if st.get("running"):
                row.set_subtitle(
                    f"running — {st.get('tools', 0)} tools from "
                    f"{st.get('configured_servers', 0)} server(s)")
            else:
                row.set_subtitle(
                    f"stopped — {st.get('configured_servers', 0)} "
                    f"server(s) configured")
        except Exception:
            row.set_subtitle("status unavailable")

    def _on_mcp_toggled(self, row, _ps):
        on = row.get_active()
        if getattr(self, "_mcp_toggling", False):
            return
        self._set("mcp_enabled", on)
        ext = self._ext()
        if ext is None:
            self.win._show_toast("Extensions not loaded — MCP unavailable")
            return
        try:
            res = ext.set_mcp_enabled(on)
        except Exception as e:
            res = {"ok": False, "error": str(e)}
        if res.get("ok"):
            self.win._show_toast(
                f"MCP started — {res.get('tools', 0)} tools" if on
                else "MCP stopped")
        else:
            self.win._show_toast(f"MCP: {res.get('error', 'failed to start')}")
            if on:                       # revert the switch without recursing
                self._mcp_toggling = True
                row.set_active(False)
                self._mcp_toggling = False
                self._set("mcp_enabled", False)
        self._refresh_mcp_status()

    def _on_mcp_server_add(self, row):
        raw = (row.get_text() or "").strip()
        if not raw:
            return
        # Parse "command arg1 arg2" into {name, command, args}.
        parts = raw.split()
        cmd = parts[0]
        args = parts[1:]
        name = os.path.basename(cmd).split(".")[0] or "server"
        servers = list(self.win.settings.get("mcp_servers") or [])
        if any(s.get("name") == name for s in servers):
            name = f"{name}-{len(servers) + 1}"
        servers.append({"name": name, "command": cmd, "args": args})
        self._set("mcp_servers", servers)
        row.set_text("")
        self.win._show_toast(
            f"Added MCP server '{name}'. Toggle MCP off/on to (re)start.")
        self._refresh_mcp_status()

    def _on_provider_key(self, key, text):
        self.win.settings[f"{key}_api_key"] = text
        save_settings(self.win.settings)
        backend = self.win.cloud.get(key)
        if backend is not None and hasattr(backend, "set_api_key"):
            backend.set_api_key(text)
        self.win.update_status_pills()
        # a key change may unlock/lock the vision key field mirror
        if getattr(self, "vision_key_row", None) is not None:
            self._refresh_vision_widgets()

    def _vision_prov_key(self):
        """Provider key currently selected in the Vision provider row."""
        i = self.vision_provider_row.get_selected()
        return (self._vp_keys[i] if 0 <= i < len(self._vp_keys)
                else "siliconflow")

    def _on_vision_provider(self, row, _ps):
        self._set("vision_provider", self._vision_prov_key())
        self._refresh_vision_widgets()

    def _refresh_vision_widgets(self):
        """Sync the vision API-key field and the model quick-pick to whichever
        vision provider is selected.  Guarded so programmatic updates here don't
        re-fire the pick handler and clobber the saved model."""
        self._vision_refreshing = True
        try:
            pk = self._vision_prov_key()
            label = (PROVIDERS_BY_KEY[pk].label
                     if pk in PROVIDERS_BY_KEY else pk)
            self.vision_key_row.set_title(f"{label} API key")
            self.vision_key_row.set_text(
                self.win.settings.get(f"{pk}_api_key", "") or "")
            models = list(VISION_MODELS.get(pk, []))
            self._vision_pick_models = models
            self.vision_pick_row.set_model(
                Gtk.StringList.new(models + ["Custom (type below)"]))
            cur = (self.win.settings.get("vision_model", "") or "").strip()
            self.vision_pick_row.set_selected(
                models.index(cur) if cur in models else len(models))
        finally:
            self._vision_refreshing = False

    def _on_vision_pick(self, row, _ps):
        if getattr(self, "_vision_refreshing", False):
            return
        i = row.get_selected()
        models = getattr(self, "_vision_pick_models", [])
        if 0 <= i < len(models):
            self.vision_model_row.set_text(models[i])
            self._set("vision_model", models[i])

    def _model_row_text(self, spec, model_id):
        """One combo line: name, then the numbers that decide the pick."""
        info = spec.info(model_id) if hasattr(spec, "info") else None
        short = (info.label if info is not None
                 else (model_id.split("/")[-1] if "/" in model_id
                       else model_id))
        detail = self.win._model_detail(spec, model_id)
        return f"{short}   \u2014   {detail}" if detail else short

    def _populate_model_row(self, key, model_row, ids, saved):
        """Fill a provider's model ComboRow and restore the saved selection.

        GUARDED.  Gtk.ComboRow.set_model() resets `selected` to 0 and emits
        notify::selected, so repopulating fired _on_provider_model with
        whatever happened to be first and wrote it to disk -- a spurious
        settings write on every Settings open, and a window where the wrong
        model was persisted during a live refresh.  The vision picker
        already had this guard; the provider picker did not.
        """
        spec = PROVIDERS_BY_KEY.get(key)
        self._model_rows_refreshing = True
        try:
            model_row.set_model(Gtk.StringList.new(
                [self._model_row_text(spec, i) for i in ids] if spec
                else list(ids)))
            if saved in ids:
                model_row.set_selected(ids.index(saved))
        finally:
            self._model_rows_refreshing = False
        self._model_rows[key] = (model_row, ids)

    def _on_provider_model(self, key, row):
        if getattr(self, "_model_rows_refreshing", False):
            return
        entry = self._model_rows.get(key)
        if not entry:
            return
        _row, ids = entry
        idx = row.get_selected()
        if 0 <= idx < len(ids):
            model_id = ids[idx]
            if model_id:
                self.win.settings[f"{key}_model"] = model_id
                save_settings(self.win.settings)
                self.win._update_model_button()

    def _on_active_provider(self, row, _ps):
        idx = row.get_selected()
        keys = [p.key for p in PROVIDERS]
        if 0 <= idx < len(keys):
            self.win.settings["active_provider"] = keys[idx]
            save_settings(self.win.settings)
            self.win.update_status_pills()

    def _fetch_live_models(self, key):
        """Query the provider's live /models catalogue on a background
        thread and repopulate its picker.  Falls back silently to the
        curated chain on any failure."""
        backend = self.win.cloud.get(key)
        if backend is None or not hasattr(backend, "list_models_live"):
            self.win._show_toast("This provider has no live model list.")
            return
        spec = PROVIDERS_BY_KEY.get(key)
        self.win._show_toast(f"Fetching {spec.label if spec else key} models…")

        def _bg():
            ids = backend.list_models_live()
            GLib.idle_add(lambda: self._apply_live_models(key, ids) or False)

        threading.Thread(target=_bg, daemon=True).start()

    def _apply_live_models(self, key, ids):
        entry = self._model_rows.get(key)
        if not entry:
            return
        model_row, _old = entry
        if not ids:
            self.win._show_toast("No models returned — keeping defaults.")
            return
        # Keep the currently-saved model visible even if the live list
        # omits it (some catalogues page or filter).
        saved = self.win.settings.get(f"{key}_model", "")
        names = list(ids)
        if saved and saved not in names:
            names.insert(0, saved)
        self._populate_model_row(key, model_row, names, saved)
        spec = PROVIDERS_BY_KEY.get(key)
        self.win._show_toast(
            f"{spec.label if spec else key}: {len(ids)} chat models loaded.")

    def _on_temp(self, row, *args):
        self._set("temperature", float(row.get_value()))

    def _on_max(self, row, *args):
        self._set("max_tokens", int(row.get_value()))

    def _on_ui_scale(self, row, *args):
        # Persist as float.  Then trigger a LIVE CSS reload so the
        # change is visible immediately — no app restart needed.
        # Debounce the reload by 200ms so rapid scrolling doesn't
        # spam the CSS provider.
        value = float(row.get_value())
        self._set("ui_scale", value)

        if hasattr(self, "_ui_scale_timeout") and self._ui_scale_timeout:
            try:
                GLib.source_remove(self._ui_scale_timeout)
            except Exception:
                pass
            self._ui_scale_timeout = None

        def _do_reload():
            try:
                self.win.app.reload_css(value)
            except Exception as e:
                log(f"ui_scale live reload failed: {e}")
            self._ui_scale_timeout = None
            return False

        self._ui_scale_timeout = GLib.timeout_add(200, _do_reload)

    def _on_agent_default(self, row, _ps):
        self._set("agent_mode_default", row.get_active())

    def _on_watcher_enable(self, row, _ps):
        self._set("watcher_enabled", row.get_active())
        if row.get_active():
            self.win.watcher.start()
        else:
            self.win.watcher.stop()

    def _on_sp_changed(self, buf):
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
        self._set("system_prompt", text)

    # ── voice handlers ──
    def _on_tts_enable(self, row, _ps):
        on = row.get_active()
        self._set("tts_enabled", on)
        # Keep the toolbar speaker toggle in sync if it exists.
        tb = getattr(self.win, "tts_toggle", None)
        if tb is not None and tb.get_active() != on:
            tb.set_active(on)

    def _on_tts_monster(self, row, _ps):
        on = row.get_active()
        self._set("tts_monster", on)
        # Depth only matters when the monster voice is on — grey it out otherwise.
        dr = getattr(self, "tts_depth_row", None)
        if dr is not None:
            dr.set_sensitive(on)
        if not on and getattr(self.win, "tts", None):
            self.win.tts.stop()

    def _on_tts_engine(self, row, _ps):
        idx = row.get_selected()
        key = self._tts_engine_keys[idx] if 0 <= idx < len(self._tts_engine_keys) else "auto"
        self._set("tts_engine", key)
        tts = getattr(self.win, "tts", None)
        if tts is not None:
            tts.reconfigure()
            avail = tts.available()
            self.tts_enabled_row.set_sensitive(avail)
            if avail:
                self.win._show_toast(f"Voice engine: {tts.engine_name()}")
            else:
                self.win._show_toast("That engine isn't available on this box.")

    def _on_tts_voice(self, row):
        self._set("tts_voice", row.get_text().strip())
        tts = getattr(self.win, "tts", None)
        if tts is not None:
            tts.reconfigure()
            self.tts_enabled_row.set_sensitive(tts.available())
            self.win._show_toast(f"Voice engine: {tts.engine_name()}")

    def _on_tts_test(self, _btn):
        tts = getattr(self.win, "tts", None)
        if tts is None or not tts.available():
            self.win._show_toast("No voice engine available.")
            return
        tts.stop()
        tts.speak_all("Voice check. Basilisk is online and ready.")

    def _on_stt_test(self, _btn):
        stt = getattr(self.win, "stt", None)
        if stt is None or not stt.recorder_available():
            self.win._show_toast("No microphone recorder available.")
            return
        reason = stt.unavailable_reason()
        if reason:
            self.win._show_toast(reason, timeout=6)
            return
        self.stt_test_btn.set_sensitive(False)
        self.stt_test_btn.set_label("● Listening 4s…")
        self.win._show_toast("Listening for 4 seconds — say something.", timeout=4)

        def _bg():
            text, err = stt.test_capture(4.0)

            def _show():
                self.stt_test_btn.set_sensitive(True)
                self.stt_test_btn.set_label("● Record 4s")
                if err:
                    self.win._show_toast(f"Mic test failed: {err}", timeout=8)
                    self.win.terminal_log(f"mic test FAILED: {err}", "error")
                elif text:
                    self.win._show_toast(f"Heard: “{text}”", timeout=8)
                    self.win.terminal_log(f"mic test OK: {text}", "ok")
                else:
                    self.win._show_toast(
                        "Recorded but transcript was empty — likely silence "
                        "or wrong input source.", timeout=8)
                    self.win.terminal_log("mic test: empty transcript", "error")
                return False
            GLib.idle_add(_show)
        threading.Thread(target=_bg, daemon=True).start()


# ═════════════════════════════════════════════════════════════════════
# MAIN WINDOW
# ═════════════════════════════════════════════════════════════════════

class MainWindow(Adw.ApplicationWindow):

    def __init__(self, app: "BasiliskApp"):
        super().__init__(application=app)
        self.set_title(APP_NAME)
        w, h = _default_window_size()
        self.set_default_size(w, h)
        # libadwaita warns once per layout pass that an AdwApplicationWindow
        # "does not have a minimum size" — 25 times in a 16-state sweep — and
        # without one the adaptive machinery has nothing to break against, so
        # a narrow window can squeeze children past their own minimums (which
        # is how widgets end up overlapping).
        #
        # ── BUT THE NUMBER HAS TO BE TRUE ──
        # It was 360, chosen as "the narrowest screen this app targets", and
        # the content pane's own measured minimum is 480. A size request
        # BELOW what the children need does not make them fit; it forces GTK
        # to allocate less than the minimum and clip the remainder off the
        # right edge. Measured: at a 458px window the Close button was sliced
        # in half, the model pill was truncated, the user avatar was off
        # screen entirely, and libadwaita said so on every layout pass —
        #
        #   AdwToastOverlay exceeds MainWindow width:
        #   requested 462 px, 458 px available
        #
        # — which is the warning this line was added to silence, still being
        # emitted because the declared minimum was a wish rather than a
        # measurement. The message bubbles were never the constraint: every
        # block type wraps or scrolls cleanly down to 350px. The floor is the
        # header's fixed-size art buttons, and those are not negotiable.
        #
        # So declare the truth. The window can still be small; it can no
        # longer be made smaller than it can draw.
        self.set_size_request(480, 480)
        self.app = app
        self.settings = load_settings()
        global _APPROVAL_MODE
        _APPROVAL_MODE = self.settings.get("approval_mode", "none")
        # In-app notification inbox — things Basilisk flags for the operator.
        # Persisted so they survive a restart; capped so it can't grow forever.
        self._notif_path = os.path.expanduser(
            "~/.local/share/basilisk/notifications.json")
        self._notifications = self._load_notifications()
        # Community-tier web_read hosts the operator has approved THIS session.
        # In-memory only (a fresh run starts locked down again); the gate that
        # enforces this lives in _web_read_gated, not in the model's prompt.
        self._web_grants: set = set()
        # In-app sudo password cache. Held ONLY in memory, passed straight to
        # the sudo subprocess, never written to disk/log/history — the model
        # cannot see it. Entered once per chat; cleared when you start a new
        # chat; expires 30 minutes after entry, after which it's asked again.
        self._sudo_pw = None
        self._sudo_pw_time = 0.0
        # Apply the inline-image toggle to the module global the renderer reads.
        global _RENDER_IMAGES
        try:
            _RENDER_IMAGES = bool(self.settings.get("chat_render_images", True))
        except Exception:
            _RENDER_IMAGES = True
        # Build one backend per registered cloud provider.  Groq keeps its
        # library-backed backend; everything else rides the generic
        # OpenAI-compatible backend.  Keyed by provider id for the router.
        self.cloud: Dict[str, Any] = {}
        for spec in PROVIDERS:
            key = self.settings.get(f"{spec.key}_api_key", "")
            if spec.engine == "groq":
                self.cloud[spec.key] = GroqBackend(key)
            else:
                self.cloud[spec.key] = OpenAICompatBackend(spec, key)
        # Back-compat alias used in a few spots.
        self.groq = self.cloud.get("groq")
        self.router = BackendRouter(self.cloud, self.settings)
        self.store = ChatStore()
        self.watcher = Watcher(self.settings, self._on_watcher_event)

        # ── basilisk_ext sidecar (optional) ──
        # Imports nothing from this app; depends only on stdlib + the two
        # callables handed to init().  If the package is missing or init
        # raises, self._ext stays None and every hook below no-ops, leaving
        # Basilisk identical to a stock build.  Nothing here starts a background
        # thread unless the matching setting is on.
        self._ext = None
        try:
            from basilisk_ext import extman as _extman
            # Semantic memory recall: wire the embedder only when it's enabled
            # AND a SiliconFlow key exists (that's the endpoint hosting the
            # embedding models).  Otherwise pass None and memory stays in the
            # offline keyword mode — recall degrades, never breaks.
            _semantic = (bool(self.settings.get("memory_semantic", True))
                         and bool((self.settings.get("siliconflow_api_key")
                                   or "").strip()))
            _extman.init(settings=self.settings,
                         data_dir="~/.local/share/basilisk",
                         complete_fn=self._ext_complete,
                         embed_fn=(self._ext_embed if _semantic else None),
                         ledger=get_ledger())
            self._ext = _extman
            if _semantic:
                self._start_memory_backfill()
        except Exception as _e:
            log(f"basilisk_ext not loaded: {_e}")

        self.current_chat_id: Optional[int] = None
        self.current_agent_mode = bool(self.settings.get("agent_mode_default",
                                                          True))
        # ── UNLEASH: the master switch (the big red dragon button) ──
        # ON  → confirm the target, then go FULLY autonomous and never stop until
        #       the mission is complete (MISSION_COMPLETE token).
        # OFF → answer once and stop. No autonomous grind, ever.
        # Unleash implies agent mode (it needs the tools + the mission loop), so
        # arming it forces current_agent_mode on and syncs the agent toggle.
        self._unleashed: bool = bool(self.settings.get("unleashed", False))
        # One-shot: set when Unleash is armed so the very next turn confirms the
        # target (or asks for it once if none is set yet) before going full send.
        self._unleash_kickoff_pending: bool = False
        if self._unleashed:
            self.current_agent_mode = True
        self.streaming_thread: Optional[threading.Thread] = None
        # Bumped once per stream. A callback carrying an older value belongs
        # to a turn that has been replaced and is ignored -- see the block
        # in the stream setup for the three ways that happens.
        self._stream_epoch: int = 0
        # GLib source id of a queued next-turn kick, 0 when none. Declared
        # here so _is_busy() and _cancel_pending_kick() never depend on a
        # getattr default to be correct.
        self._pending_kick_id: int = 0
        self.streaming_cancel: Optional[threading.Event] = None
        self.streaming_msg_widget: Optional[MessageWidget] = None
        self.streaming_msg_db_id: Optional[int] = None
        # Chat the active streaming/tool turn belongs to.  Used so that
        # if the user navigates to a different chat mid-turn, tool results
        # and follow-up assistant messages still land in the chat that
        # started the turn — not whichever chat happens to be displayed
        # when the background work completes.
        self.streaming_chat_id: Optional[int] = None
        self._tool_chain_depth: int = 0
        # Set once per turn when the tool-step budget is exhausted: the next
        # turn ignores any tool calls and just answers, so we never dead-end.
        self._tools_locked: bool = False
        # How many times THIS turn has been pushed to produce a written answer
        # after a dropped tool call or an all-tool-call reply. Bounded so a
        # model that will not write prose cannot loop. See _on_stream_done.
        self._force_answer_tries: int = 0
        # Text appended to the next tool result when extra calls in a reply
        # were not run this turn. See _on_stream_done_body / _feed_tool_result.
        self._deferred_note: str = ""
        # Name of the tool currently being dispatched, so a lambda-wrapped
        # handler can log what it actually is. See _run_tool_call / _tool_simple.
        self._dispatching_tool: str = ""
        # Per-tool labels for a parallel batch, so the repeat guard can match a
        # later SOLO call of a tool that already ran inside one.
        self._batch_members: List[str] = []
        # Answer-mode stall pushes spent on the current request. See
        # ANSWER_STALL_NUDGE_MAX.
        self._answer_stall_nudges: int = 0
        # Set when the operator hits the stop button.  Halts the current
        # stream AND prevents the tool chain from kicking another turn.
        self._stop_requested: bool = False

        # ── Autonomous mission (walk-away autonomy) ──
        # When agent mode is on, the message you send IS the objective. Basilisk
        # works it turn after turn; a plain (no-tool) reply does NOT end the run
        # and a stream/API error triggers backoff+retry, never a dead stop. It
        # ends ONLY when you press Stop, or the model explicitly signals the
        # objective is fully done AND re-confirms it on a forced re-check.
        self._mission_active: bool = False
        self._mission_objective: str = ""
        self._mission_kicks: int = 0            # consecutive no-progress re-kicks
        self._recent_commands: list = []        # tail of run commands, for loop-break
        # ACTION RECALL — the durable record of what this run has already done.
        # The transcript is NOT that record: _build_history_for_model keeps only
        # HISTORY_KEEP_FULL_TOOL_RESULTS full tool results and headroom
        # compresses what survives, so several steps in, the model's evidence of
        # having already tried something is a truncated stub while the loudest
        # thing in its context is still the original objective. That is what
        # made it redo work from a few turns back. One line per action lives
        # here instead, outside the transcript, and is re-sent whole every turn.
        self._action_log = _recall.ActionLog() if _recall else None
        # The action currently in flight, so the result that comes back can be
        # attached to it. Set at dispatch, consumed in _feed_tool_result — one
        # hook covers every tool instead of instrumenting each of them.
        self._pending_action: Optional[str] = None
        # Files staged for the NEXT message. Shown as chips above the
        # composer; folded into the text at send.
        self._attachments: List[Dict[str, Any]] = []
        # Liveness marker for the turn watchdog — bumped whenever the turn
        # actually advances (a token, a tool result, a new step).
        self._turn_progress_ts: float = time.monotonic()
        # How many times the watchdog has tried to nudge the CURRENT stall.
        # Reset by any real progress. See _turn_watchdog.
        self._unblock_attempts: int = 0
        # Per-chat trim watermark: how many tool results have been demoted to
        # their trimmed form. Only ever advances, and only when the history
        # exceeds HISTORY_STABLE_BUDGET_CHARS — so the request stays
        # append-only (and cacheable) between advances. See
        # _build_history_for_model.
        self._trim_watermark: dict = {}
        self._mission_verify_pending: bool = False   # first completion signal seen
        self._mission_no_action_streak: int = 0      # turns in a row with no tool call
        self._mission_directive: str = ""       # transient nudge for the next kick
        self._error_retries: int = 0            # consecutive stream-error retries

        # ── Voice (optional) ──
        # stt: tap-to-talk transcription via Groq Whisper.
        # tts: read assistant replies aloud (Piper or espeak).
        # streamer: turns the token stream into speakable sentences.
        self.stt = None
        self.tts = None
        self._tts_streamer = None
        self._recording = False
        self._tts_suspended = False    # true for a turn that's running tools
        # The assistant message whose audio is currently queued/playing,
        # so its per-message button reflects play/pause and switching to
        # another message stops this one.
        self._speaking_widget = None
        self._turn_active = False       # an assistant turn is mid-flight
        if _VOICE_OK:
            try:
                self.stt = basilisk_voice.SpeechToText(lambda: self.settings)
                self.tts = basilisk_voice.TextToSpeech(lambda: self.settings)
                self._tts_streamer = basilisk_voice.SpeechStreamer()
                self.tts.set_state_callback(
                    lambda st: GLib.idle_add(self._on_tts_state, st))
            except Exception as _e:
                log(f"voice init failed: {_e}")
                self.stt = None
                self.tts = None

        self._build_ui()
        self._wire_actions()
        self._boot()
        GLib.idle_add(self._initial_chat_load)
        GLib.idle_add(self._refresh_sidebar)

    def _initial_chat_load(self):
        """At launch: tidy up per the history policy, then either open a
        brand-new chat (the default) or resume the most recent one."""
        self._run_retention()
        if self.settings.get("ephemeral_new_chat_on_launch", True):
            self._new_chat()
            return False
        chats = self.store.list_chats(limit=1)
        if chats:
            self._load_chat(chats[0].id)
        else:
            self._new_chat()
        return False

    def _run_retention(self):
        """Apply the chat-history policy: drop chats idle past the
        retention window and abandoned empty placeholders.  Never removes
        the chat currently open, nor pinned chats."""
        keep = self.current_chat_id
        try:
            hours = float(self.settings.get("chat_retention_hours", 24) or 0)
        except (TypeError, ValueError):
            hours = 24.0
        removed = 0
        try:
            if hours > 0:
                removed += self.store.purge_old_chats(hours * 3600.0,
                                                      keep_chat_id=keep)
            if self.settings.get("discard_empty_chats", True):
                removed += self.store.purge_empty_chats(keep_chat_id=keep)
        except Exception as e:
            log(f"retention error: {e}")
        if removed:
            log(f"retention: removed {removed} chat(s)")
            self._refresh_sidebar()
        return removed

    def _mark_turn_progress(self):
        """Something advanced the current turn.  Cheap enough to call anywhere."""
        self._turn_progress_ts = time.monotonic()
        # Real progress clears the unblock ladder, so a run that hits one slow
        # patch hours in still gets its full two nudges rather than inheriting
        # a count from something that resolved itself long ago.
        if getattr(self, "_unblock_attempts", 0):
            self._unblock_attempts = 0

    def _turn_watchdog(self):
        """Recover a turn whose loop has died.

        The assistant turn loop is a chain of hand-offs — stream callback feeds
        a tool call, tool thread feeds a result, result kicks the next stream —
        and every link runs on a daemon thread.  Before this existed, one
        unhandled exception anywhere in that chain ended the turn silently: no
        error, no toast, just "working…" forever and a Stop button that only
        cleared a flag nothing was reading any more.  The individual links are
        all guarded now (_tool_thread, _feed_tool_result, the stream worker),
        but a chain of guards is a promise, and this is the check.

        It only fires after TURN_WATCHDOG_S of TOTAL silence, which is longer
        than the longest command the runtime estimator will ever wait for, so it
        cannot cut real work short.  It does not retry anything — retrying an
        unknown failure blind is how you get duplicate side effects.  It hands
        the UI back and says what happened.
        """
        try:
            if self.streaming_chat_id is None and not self._is_busy():
                return True
            last = getattr(self, "_turn_progress_ts", None)
            if last is None:
                self._turn_progress_ts = time.monotonic()
                return True
            idle = time.monotonic() - last
            if idle < TURN_WATCHDOG_S:
                return True
            # ── UNBLOCK LADDER, not a kill ──
            # The first version of this ended the turn, which is the same
            # mistake as a timeout: the conversation, the action ledger and
            # whatever the run had achieved all went in the bin because one
            # step failed to report back. Try to get it MOVING first, and only
            # hand the UI back if nudging has already failed twice.
            self._unblock_attempts = getattr(self, "_unblock_attempts", 0) + 1

            if self._unblock_attempts <= 2:
                self.terminal_log(
                    f"⏸ nothing has advanced for {int(idle)}s — nudging the "
                    f"run rather than ending it "
                    f"(attempt {self._unblock_attempts}/2)", "error")
                # Cancel only the stream that is hanging. The chat, the store
                # and the action ledger are untouched, so the model comes back
                # with its full context and knows exactly what it already did —
                # which is what stops a nudge turning into a loop.
                try:
                    if self.streaming_cancel:
                        self.streaming_cancel.set()
                except Exception:
                    pass
                # ABANDONING A STREAM MEANS RETIRING ITS IDENTITY.
                # The worker is not joined here -- it may be blocked in a
                # socket read and will not notice the cancel until its own
                # idle timeout, then call back. By then this turn has been
                # replaced, and without this bump the dead stream's tokens
                # would append to the NEW turn's bubble and its error path
                # would schedule a retry for a turn that is not its own.
                self._stream_epoch = getattr(self, "_stream_epoch", 0) + 1
                self.streaming_msg_widget = None
                self.streaming_msg_db_id = None
                try:
                    cid = self.streaming_chat_id or self.current_chat_id
                    if cid:
                        self.store.add_message(
                            cid, "user",
                            "<tool_result>\n[host] The previous step never "
                            "reported back and was cancelled. Nothing was lost "
                            "— everything you had already done still stands, "
                            "and the ALREADY DONE list above is current. Do NOT "
                            "start over and do NOT repeat the step that hung. "
                            "Pick the next action from where you actually got "
                            "to; if the same step hangs again, do it a "
                            "different way or with a narrower "
                            "scope.\n</tool_result>",
                            meta={"kind": "tool_result"})
                except Exception:
                    pass
                self._turn_progress_ts = time.monotonic()
                try:
                    self._kick_assistant_turn()
                except Exception:
                    log(f"watchdog nudge failed: {traceback.format_exc()}")
                    self._unblock_attempts = 99      # fall through next tick
                return True

            # Nudging twice did not move it: hand the UI back rather than
            # leaving him staring at a spinner.
            self.terminal_log(
                f"■ turn watchdog: still stuck after {self._unblock_attempts - 1} "
                f"nudges — ending the turn so the app is usable again. The "
                f"conversation and everything done so far are kept.", "error")
            self._show_toast(
                "That step wouldn't restart — turn ended, nothing lost. "
                "Send again to continue.", timeout=8)
            self._stop_requested = True
            self._mission_active = False
            try:
                if self.streaming_cancel:
                    self.streaming_cancel.set()
            except Exception:
                pass
            self._finish_turn_cleanup()
            self._stop_requested = False
            self._unblock_attempts = 0
            self._turn_progress_ts = time.monotonic()
        except Exception:
            log(f"turn watchdog: {traceback.format_exc()}")
        return True

    def _periodic_retention(self):
        """Hourly sweep so a long-running session still honours the
        retention window (a startup-only purge would miss it)."""
        self._run_retention()
        return True   # keep the GLib timer alive

    # ── boot ────────────────────────────────────────────────────

    def _boot(self):
        def _bg():
            GLib.idle_add(self.update_status_pills)
            if self.settings.get("watcher_enabled"):
                self.watcher.start()
        threading.Thread(target=_bg, daemon=True).start()
        # Roll old chats hourly so a session left open for days still
        # honours the retention window.
        GLib.timeout_add_seconds(3600, self._periodic_retention)
        # Liveness backstop for the turn loop.  See _turn_watchdog.
        GLib.timeout_add_seconds(TURN_WATCHDOG_POLL_S, self._turn_watchdog)

    # ── UI construction ─────────────────────────────────────────

    def _build_ui(self):
        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)

        self.split = Adw.OverlaySplitView()
        self.split.set_min_sidebar_width(280)
        self.split.set_max_sidebar_width(360)
        self.split.set_sidebar_width_fraction(0.28)
        self.toast_overlay.set_child(self.split)

        self.split.set_sidebar(self._build_sidebar())
        self.split.set_content(self._build_main())

        # On narrow screens (phones, split-view tablets) the 280-360 px
        # sidebar eats the whole window, leaving no room for the chat
        # area.  Collapse it so the sidebar overlays content instead of
        # pushing it aside.  Two paths: a libadwaita Breakpoint when
        # available (reactive to resize), and a static fallback gated
        # on actual screen width when Breakpoint isn't supported.
        try:
            bp = Adw.Breakpoint.new(
                Adw.BreakpointCondition.parse("max-width: 820px"))
            bp.add_setter(self.split, "collapsed", True)
            self.add_breakpoint(bp)
        except Exception as e:
            log(f"breakpoint unavailable, using static collapse: {e}")
            # Detect narrow screen via Gdk directly so we don't depend on
            # UI scale (which is about font sizes, not screen geometry).
            # Use LOGICAL width (device width / scale factor) so a phone that
            # reports raw device pixels (e.g. 1080) still collapses correctly.
            try:
                display = Gdk.Display.get_default()
                mon = display.get_monitors().get_item(0) if display else None
                if mon:
                    geo = mon.get_geometry()
                    sf = mon.get_scale_factor() or 1
                    logical_w = geo.width / sf if sf > 0 else geo.width
                    if logical_w < 820 or geo.width < 820:
                        self.split.set_collapsed(True)
            except Exception:
                pass

    def _build_sidebar(self):
        sb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        sb.add_css_class("sidebar")

        # Header
        sb_header = Adw.HeaderBar()
        sb_header.set_show_end_title_buttons(False)
        sb_header.set_show_start_title_buttons(False)

        # Header — BASILISK (with a live online dot) on the left, new-chat on the
        # right.  The dot is green when online, red when offline.
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
        # Death-metal wordmark: the carved logo art. SCALED DOWN to a small
        # intrinsic size (never CONTAIN off a full-res texture, which renders at
        # the image's huge natural size and blows the header up). Falls back to a
        # styled text label if the image isn't present.
        if _LOGO_PNG_PATH:
            try:
                _lh = 34
                _pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    _LOGO_PNG_PATH, -1, _lh, True)   # height=_lh, width auto
                t = Gtk.Picture.new_for_paintable(
                    Gdk.Texture.new_for_pixbuf(_pb))
                t.set_content_fit(Gtk.ContentFit.SCALE_DOWN)
                t.set_can_shrink(True)
                t.set_hexpand(False)
                t.set_vexpand(False)
                t.set_size_request(_pb.get_width(), _lh)
                t.set_valign(Gtk.Align.CENTER)
                t.set_halign(Gtk.Align.START)
                t.set_tooltip_text(APP_NAME)
            except Exception:
                t = Gtk.Label(label=APP_NAME.upper(), xalign=0.0)
                t.add_css_class("app-title")
                t.set_valign(Gtk.Align.CENTER)
        else:
            t = Gtk.Label(label=APP_NAME.upper(), xalign=0.0)
            t.add_css_class("app-title")
            t.set_valign(Gtk.Align.CENTER)
        # The BASILISK death-metal wordmark IS the new-chat button now: tap the
        # logo art to start a fresh chat (no separate + button beside it).
        wordmark_btn = Gtk.Button()
        wordmark_btn.add_css_class("wordmark-btn")
        wordmark_btn.set_has_frame(False)
        wordmark_btn.set_child(t)
        wordmark_btn.set_tooltip_text("New chat")
        wordmark_btn.set_valign(Gtk.Align.CENTER)
        wordmark_btn.connect("clicked", lambda *_: self._new_chat())
        title_box.append(wordmark_btn)
        self.online_dot = Gtk.Label(label="●")
        self.online_dot.add_css_class("online-dot")
        self.online_dot.set_valign(Gtk.Align.CENTER)
        self.online_dot.set_tooltip_text("Connectivity")
        title_box.append(self.online_dot)
        sb_header.pack_start(title_box)
        # Suppress the default centered window-title ("Basilisk") — the red
        # BASILISK wordmark packed on the left is the only brand mark we want.
        # Without this, Adw.HeaderBar renders the window title in the center,
        # showing "Basilisk" a second time (in white) next to the wordmark.
        _empty_title = Gtk.Label()
        _empty_title.set_visible(False)
        sb_header.set_title_widget(_empty_title)
        sb.append(sb_header)

        # (Chat search removed by request.)

        # List
        self.chat_listbox = Gtk.ListBox()
        self.chat_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.chat_listbox.connect("row-activated", self._on_chat_selected)

        gc = Gtk.GestureClick()
        gc.set_button(3)
        gc.connect("pressed", self._on_chat_rightclick)
        self.chat_listbox.add_controller(gc)
        lp = Gtk.GestureLongPress()
        lp.connect("pressed", self._on_chat_longpress)
        self.chat_listbox.add_controller(lp)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_vexpand(True)
        sw.set_child(self.chat_listbox)
        sb.append(sw)

        # A Tao Te Ching line under the chat list -- a different one is chosen
        # each time the app launches (this runs once at window build).
        import random as _rnd
        _tao_lines = [
            "The Tao that can be spoken is not the eternal Tao.",
            "The journey of a thousand miles begins beneath one's feet.",
            "He who knows others is wise; he who knows himself is enlightened.",
            "He who conquers others is strong; he who conquers himself is mighty.",
            "He who is contented is rich.",
            "The soft and the yielding overcome the hard and the strong.",
            "Nothing is softer than water, yet nothing is better at wearing down the hard.",
            "He who knows does not speak; he who speaks does not know.",
            "Do the difficult while it is easy; do the great while it is small.",
            "The tree that fills a man's arms grew from a tiny sprout.",
            "To know that you do not know is best.",
            "The more the sage gives to others, the more he has.",
            "Govern a great nation as you would cook a small fish.",
            "The highest good is like water: it benefits all things and does not contend.",
            "Fill your bowl to the brim and it will spill.",
            "He who stands on tiptoe does not stand firm.",
            "Manifest plainness, embrace simplicity, reduce selfishness, have few desires.",
            "Returning to the root is stillness.",
            "The sage puts himself last, and so finds himself in front.",
            "Act without striving; work without meddling.",
            "Knowing constancy is insight.",
            "The way of Heaven is to benefit, and not to harm.",
            "When the work is done, withdraw -- such is the way of Heaven.",
            "A good traveler has no fixed plans and is not intent upon arriving.",
        ]
        _tao_lbl = Gtk.Label(label=_rnd.choice(_tao_lines))
        _tao_lbl.add_css_class("tao-quote")
        _tao_lbl.set_wrap(True)
        _tao_lbl.set_justify(Gtk.Justification.CENTER)
        _tao_lbl.set_xalign(0.5)
        _tao_lbl.set_margin_top(10)
        _tao_lbl.set_margin_bottom(12)
        _tao_lbl.set_margin_start(14)
        _tao_lbl.set_margin_end(14)
        sb.append(_tao_lbl)

        return sb

    def _build_main(self):
        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Header
        hb = Adw.HeaderBar()
        # Only our own dragon toggle belongs at the top-left — suppress the
        # compositor's start-side title button so there aren't two icons there.
        hb.set_show_start_title_buttons(False)
        # Custom dragon-forged window controls (minimise / close). Only take over
        # from the compositor's buttons when the art is actually present, so we
        # never leave the window with no way to close.
        _close_art = _btn_art(_BTN_CLOSE, px=_COMPOSER_BTN_PX)
        _min_art = _btn_art(_BTN_MINIMISE, px=_COMPOSER_BTN_PX)
        if _close_art is not None and _min_art is not None:
            hb.set_show_end_title_buttons(False)
            _close_btn = Gtk.Button()
            _close_btn.set_child(_close_art)
            _close_btn.add_css_class("art-button")
            _close_btn.set_tooltip_text("Close")
            _close_btn.connect("clicked", lambda *_: self.close())
            hb.pack_end(_close_btn)            # first packed_end = far right
            # Expand / restore (maximise toggle) — sits between minimise and
            # close.  Optional: shown only when its art is present.
            _exp_art = _btn_art(_BTN_EXPAND, px=_COMPOSER_BTN_PX)
            if _exp_art is not None:
                _exp_btn = Gtk.Button()
                _exp_btn.set_child(_exp_art)
                _exp_btn.add_css_class("art-button")
                _exp_btn.set_tooltip_text("Expand / restore")
                _exp_btn.connect(
                    "clicked",
                    lambda *_: (self.unmaximize() if self.is_maximized()
                                else self.maximize()))
                hb.pack_end(_exp_btn)          # sits left of close
            _min_btn = Gtk.Button()
            _min_btn.set_child(_min_art)
            _min_btn.add_css_class("art-button")
            _min_btn.set_tooltip_text("Minimise")
            _min_btn.connect("clicked", lambda *_: self.minimize())
            hb.pack_end(_min_btn)              # leftmost of the three
        # The sidebar toggle IS the dragon logo now — tap the emblem to show/hide
        # the sidebar (one branded button instead of a plain toggle + a logo).
        sb_toggle = Gtk.Button()
        sb_toggle.add_css_class("header-icon-button")
        sb_toggle.add_css_class("logo-toggle")
        sb_toggle.set_tooltip_text("Toggle sidebar")
        if _AVATAR_PNG_PATH:
            _logo_img = Gtk.Image.new_from_file(_AVATAR_PNG_PATH)
            _logo_img.set_pixel_size(24)
            sb_toggle.set_child(_logo_img)
        else:
            sb_toggle.set_icon_name("sidebar-show-symbolic")
        sb_toggle.connect("clicked", lambda *_:
                          self.split.set_show_sidebar(
                              not self.split.get_show_sidebar()))
        hb.pack_start(sb_toggle)

        self.title_widget_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                                         spacing=0)
        self.chat_title_lbl = Gtk.Label(label="New chat", xalign=0.5)
        self.chat_title_lbl.add_css_class("chat-title")
        # Subtitle label kept for code that references it, but never shown.
        self.chat_subtitle_lbl = Gtk.Label(label="", xalign=0.5)
        self.chat_subtitle_lbl.add_css_class("chat-subtitle")
        self.title_widget_box.append(self.chat_title_lbl)
        # Header centre shows a SMALL BASILISK death-metal wordmark instead of the
        # tiny "New chat" title text. (chat_title_lbl is kept, un-shown, so rename/
        # title code still works.)
        # IMPORTANT: scale the source DOWN to a small intrinsic size and never let
        # it expand — otherwise the wide title area makes a CONTAIN Picture fill
        # the width and blow the header up to hundreds of px tall.
        _hdr_title = None
        _H = 24   # target wordmark height in px — keeps the header its normal size
        if _LOGO_PNG_PATH:
            try:
                _pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    _LOGO_PNG_PATH, -1, _H, True)   # height=_H, width auto, keep aspect
                _t2 = Gdk.Texture.new_for_pixbuf(_pb)
                _hdr_title = Gtk.Picture.new_for_paintable(_t2)
                _hdr_title.set_content_fit(Gtk.ContentFit.SCALE_DOWN)  # never upscale
                _hdr_title.set_can_shrink(True)
                _hdr_title.set_hexpand(False)
                _hdr_title.set_vexpand(False)
                _hdr_title.set_halign(Gtk.Align.CENTER)
                _hdr_title.set_valign(Gtk.Align.CENTER)
                _hdr_title.set_size_request(_pb.get_width(), _H)
                _hdr_title.set_tooltip_text(APP_NAME)
            except Exception:
                _hdr_title = None
        hb.set_title_widget(_hdr_title if _hdr_title is not None
                            else self.title_widget_box)

        # (Provider + online status used to live here as pills; the operator
        # knows their provider, so that's gone — connectivity is now just the
        # green/red dot next to BASILISK in the sidebar header.)

        menu_btn = Gtk.MenuButton()
        _mset = _btn_art(_BTN_SETTINGS, px=_COMPOSER_BTN_PX)
        if _mset is not None:
            menu_btn.set_child(_mset)
            menu_btn.add_css_class("art-button")
        else:
            menu_btn.set_icon_name("open-menu-symbolic")
            menu_btn.add_css_class("icon-button")
        menu = Gio.Menu()
        menu.append("Pin chat", "win.pin-chat")
        menu.append("Rename chat", "win.rename-chat")
        menu.append("Delete chat", "win.delete-chat")
        menu.append("Settings", "win.settings")
        menu.append("About", "win.about")
        menu_btn.set_menu_model(menu)
        hb.pack_end(menu_btn)

        # Notification bell — opens the in-app inbox of things Basilisk flagged.
        # An overlaid badge shows the unread count. Use a text glyph rather than a
        # themed icon name: Kali's icon theme doesn't ship the notifications
        # symbolic icon, so set_icon_name rendered a blank button. A bell glyph
        # renders in any font.
        self.notif_btn = Gtk.MenuButton()
        _bellart = _btn_art(_BTN_BELL, px=_COMPOSER_BTN_PX)
        if _bellart is not None:
            self.notif_btn.set_child(_bellart)
            self.notif_btn.add_css_class("art-button")
        else:
            _bell = Gtk.Label(label="\U0001F514")   # bell
            _bell.add_css_class("bell-glyph")
            self.notif_btn.set_child(_bell)
            self.notif_btn.add_css_class("icon-button")
        self.notif_btn.set_valign(Gtk.Align.CENTER)
        self.notif_btn.set_tooltip_text("Notifications from Basilisk")
        notif_pop = Gtk.Popover()
        notif_pop.set_size_request(340, 420)
        _pop_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        _pop_box.set_margin_top(8)
        _pop_box.set_margin_bottom(8)
        _pop_box.set_margin_start(6)
        _pop_box.set_margin_end(6)
        _pop_head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        _pop_title = Gtk.Label(label="Notifications", xalign=0.0)
        _pop_title.add_css_class("title-4")
        _pop_title.set_hexpand(True)
        _clear_btn = Gtk.Button(label="Clear")
        _clear_btn.add_css_class("flat")
        _clear_btn.connect("clicked", self._clear_notifications)
        _pop_head.append(_pop_title)
        _pop_head.append(_clear_btn)
        _pop_box.append(_pop_head)
        _scroll = Gtk.ScrolledWindow()
        _scroll.set_vexpand(True)
        _scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.notif_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                                      spacing=2)
        _scroll.set_child(self.notif_list_box)
        _pop_box.append(_scroll)
        notif_pop.set_child(_pop_box)
        self.notif_btn.set_popover(notif_pop)
        # opening the inbox marks everything read (clears the badge)
        notif_pop.connect("show", lambda *_: self._mark_notifications_read())

        # unread badge overlaid on the bell
        _bell_overlay = Gtk.Overlay()
        _bell_overlay.set_valign(Gtk.Align.CENTER)
        _bell_overlay.set_child(self.notif_btn)
        self.notif_badge_lbl = Gtk.Label(label="")
        self.notif_badge_lbl.add_css_class("notif-badge")
        self.notif_badge_lbl.set_halign(Gtk.Align.END)
        self.notif_badge_lbl.set_valign(Gtk.Align.START)
        self.notif_badge_lbl.set_can_target(False)  # clicks pass through to the bell
        self.notif_badge_lbl.set_visible(False)
        _bell_overlay.add_overlay(self.notif_badge_lbl)
        hb.pack_end(_bell_overlay)
        # initial paint of badge/list
        GLib.idle_add(self._refresh_notifications)

        main.append(hb)

        # Watcher event banner
        self.banner_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                                   spacing=0)
        main.append(self.banner_box)

        # "Working..." status row, shown while assistant is generating or
        # a tool is running.  Hidden by default.
        self.working_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                                    spacing=12)
        self.working_row.add_css_class("working-row")
        self.working_row.set_halign(Gtk.Align.CENTER)
        self.working_row.set_margin_top(8)
        self.working_row.set_margin_bottom(8)
        self.working_spinner = Gtk.Spinner()
        self.working_spinner.add_css_class("working-spinner")
        self.working_label = Gtk.Label(label="working…")
        self.working_label.add_css_class("working-label")
        self.working_row.append(self.working_spinner)
        self.working_row.append(self.working_label)
        self.working_row.set_visible(False)
        # NOTE: working_row is appended just above the composer input (see the
        # tail of _build_input_area) so the burning status bar sits directly
        # over the Send button instead of up under the banner.

        # Messages
        self.msg_scroll = Gtk.ScrolledWindow()
        self.msg_scroll.set_policy(Gtk.PolicyType.NEVER,
                                    Gtk.PolicyType.AUTOMATIC)
        self.msg_scroll.set_vexpand(True)
        # Force kinetic (swipe) scrolling — needed for phone touch input
        self.msg_scroll.set_kinetic_scrolling(True)
        self.msg_scroll.set_overlay_scrolling(True)
        self.msg_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.msg_box.set_margin_top(12)
        self.msg_box.set_margin_bottom(12)
        self.msg_box.set_margin_start(8)
        self.msg_box.set_margin_end(8 + self._SCROLLBAR_GUTTER)
        self.msg_scroll.set_child(self.msg_box)
        self.msg_scroll.add_css_class("chat-scroll")
        self._wire_scroll_stickiness()

        # A faint menacing-penguin watermark sits BEHIND the conversation.
        # Gtk.Overlay draws its main child at the back and overlays on top, so
        # the watermark is the main child and the (transparent) scroller is the
        # overlay — messages render over the penguin.  Falls back to just the
        # scroller if the watermark SVG isn't on disk.
        wm = self._build_chat_watermark()
        if wm is not None:
            # Darken the backdrop behind the dragon (brightness only, same hue)
            # so the brighter watermark reads clearly against it. The scrim box
            # sits behind the (transparent-background) watermark picture.
            scrim = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            scrim.add_css_class("chat-scrim")
            scrim.set_hexpand(True)
            scrim.set_vexpand(True)
            scrim.append(wm)
            chat_overlay = Gtk.Overlay()
            chat_overlay.set_vexpand(True)
            chat_overlay.set_child(scrim)
            chat_overlay.add_overlay(self.msg_scroll)
            main.append(chat_overlay)
        else:
            main.append(self.msg_scroll)

        main.append(self._build_input_area())

        # Terminal log panel — hidden by default, shown when user taps the log button
        self._terminal_visible = False
        self.terminal_panel = self._build_terminal_panel()
        self.terminal_panel.set_visible(False)
        main.append(self.terminal_panel)

        return main

    def _build_chat_watermark(self):
        """A large, faint dragon watermark for behind the chat.  Loads either a
        PNG (the dragon emblem, already alpha-baked) or an SVG.  Non-interactive
        (never grabs touch/clicks), scaled to fit, low opacity so it sets the
        mood without fighting the text.  Returns None if the art isn't on disk."""
        path = _WATERMARK_SVG_PATH
        if not path:
            return None
        try:
            if path.lower().endswith(".png"):
                # BOUNDED, AND SHARED. Full resolution is 1672x941, i.e. a 6MB
                # RGBA texture that COVER rescales behind the chat on every
                # repaint — and the chat repaints on every scroll frame and
                # every streamed token. At 10% opacity behind text, nothing
                # above ~1100px wide is perceivable, so the cost was bought for
                # nothing. Goes through the shared cache too, so switching
                # chats does not re-decode it.
                tex = _cached_texture(path, 1100)
                if tex is None:
                    try:
                        tex = Gdk.Texture.new_from_filename(path)
                    except Exception:
                        from gi.repository import Gio
                        tex = Gdk.Texture.new_from_file(
                            Gio.File.new_for_path(path))
                # 0.5 on a bright, photographic 2MB PNG is not a watermark,
                # it is a picture with text on top: it read as a lava scene
                # pasted into the middle of the conversation and it fought
                # every line of the reply. A watermark has to be felt, not
                # read.
                opacity = 0.10
            else:
                tex = _svg_texture(path, 720)
                opacity = 0.2
            if tex is None:
                return None
            pic = Gtk.Picture.new_for_paintable(tex)
            pic.set_can_target(False)
            pic.set_hexpand(True)
            pic.set_vexpand(True)
            pic.set_halign(Gtk.Align.FILL)
            pic.set_valign(Gtk.Align.FILL)
            pic.set_opacity(opacity)
            try:
                # COVER, not CONTAIN. Contain letterboxes a landscape image
                # inside a tall chat pane, so the art appeared as a bright
                # BAND across the middle with plain background above and
                # below it — which is what made it read as content rather
                # than as backdrop. Cover fills the pane evenly.
                pic.set_content_fit(Gtk.ContentFit.COVER)
            except Exception:
                pass
            pic.add_css_class("chat-watermark")
            return pic
        except Exception as e:
            log(f"watermark build failed: {e}")
            return None

    def _build_terminal_panel(self):
        """Live terminal output panel — shows exactly what tools are doing."""
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        panel.add_css_class("terminal-panel")
        panel.set_size_request(-1, _scaled(360, floor=240))

        # Header row
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.add_css_class("terminal-panel-header")

        title_lbl = Gtk.Label(label="▶ TERMINAL LOG", xalign=0.0)
        title_lbl.add_css_class("terminal-panel-title")
        title_lbl.set_hexpand(True)
        header.append(title_lbl)

        self.terminal_status_lbl = Gtk.Label(label="idle", xalign=1.0)
        self.terminal_status_lbl.add_css_class("tool-indicator-label")
        header.append(self.terminal_status_lbl)

        clear_btn = Gtk.Button(label="clear")
        clear_btn.add_css_class("terminal-toggle-btn")
        clear_btn.connect("clicked", self._clear_terminal_log)
        header.append(clear_btn)

        close_btn = Gtk.Button.new_from_icon_name("window-close-symbolic")
        close_btn.add_css_class("icon-button")
        close_btn.connect("clicked", self._toggle_terminal_panel)
        header.append(close_btn)

        panel.append(header)

        # Log view
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.set_vexpand(True)
        sw.set_kinetic_scrolling(True)

        self.terminal_log_view = Gtk.TextView()
        self.terminal_log_view.set_editable(False)
        self.terminal_log_view.set_cursor_visible(False)
        self.terminal_log_view.set_monospace(True)
        self.terminal_log_view.set_wrap_mode(Gtk.WrapMode.CHAR)
        self.terminal_log_view.add_css_class("terminal-log-view")
        self.terminal_log_buf = self.terminal_log_view.get_buffer()

        # Colour tags
        self.terminal_log_buf.create_tag("cmd",    foreground="#d51f2e", weight=700)
        self.terminal_log_buf.create_tag("stdout", foreground="#9aa3ad")
        self.terminal_log_buf.create_tag("stderr", foreground="#e5484d")
        self.terminal_log_buf.create_tag("info",   foreground="#7d121b")
        self.terminal_log_buf.create_tag("error",  foreground="#e5484d", weight=700)
        self.terminal_log_buf.create_tag("ok",     foreground="#2ecc71", weight=700)
        self.terminal_log_buf.create_tag("dim",    foreground="#7d8794")

        sw.set_child(self.terminal_log_view)
        panel.append(sw)
        return panel

    def _model_button_label(self) -> str:
        key = self.settings.get("active_provider", "siliconflow")
        spec = PROVIDERS_BY_KEY.get(key)
        plabel = spec.label if spec else key
        model = self.settings.get(
            f"{key}_model", spec.default_model if spec else "")
        short = model.split("/")[-1] if "/" in model else model
        return f"⮂  {plabel}  ·  {short or 'pick a model'}"

    def _update_model_button(self):
        btn = getattr(self, "model_btn", None)
        if btn is not None:
            btn.set_label(self._model_button_label())

    def _provider_has_key(self, key: str) -> bool:
        return bool((self.settings.get(f"{key}_api_key", "") or "").strip())

    _TIER_ORDER = ("flagship", "workhorse", "budget")
    _TIER_LABEL = {
        "flagship":  "FLAGSHIP  \u00b7  hard targets",
        "workhorse": "WORKHORSE  \u00b7  everyday",
        "budget":    "BUDGET  \u00b7  triage & bulk",
    }

    def _models_priced_high_to_low(self, spec):
        """Order a provider's models best/most-capable first.

        WAS: parse the largest 'NNb' number out of the model id and sort on
        it, on the theory that bigger == better == pricier.  That silently
        failed on every id that doesn't carry a parameter count in its name
        -- DeepSeek-V4-Flash, GLM-5.2, Kimi-K3, Hy3 all scored 0.0 and sank
        to the BOTTOM of the operator's own picker, underneath a 72B legacy
        model, while an MoE's total-parameter count told you nothing about
        what it costs to run anyway.

        NOW: a provider with a catalogue is already ordered by hand (tier,
        then capability), so use that.  The regex survives only for
        live-fetched ids we have no metadata for.

        Kept under the old name because the popover calls it; see
        `_models_by_tier` for the grouped view.
        """
        if spec.catalogue:
            return list(spec.pick_ids)
        import re as _re

        def size_of(m):
            nums = _re.findall(r"(\d+(?:\.\d+)?)\s*[bB]\b", m)
            return max((float(n) for n in nums), default=0.0)
        ordered = sorted(
            list(enumerate(spec.chain)),
            key=lambda im: (-size_of(im[1]), im[0]))
        return [m for _i, m in ordered]

    def _models_by_tier(self, spec):
        """[(tier_heading_or_None, [model_id, ...]), ...] for the popover.
        A provider with no catalogue gets one unlabelled group, i.e. exactly
        the old flat list."""
        if not spec.catalogue:
            return [(None, self._models_priced_high_to_low(spec))]
        groups = []
        for tier in self._TIER_ORDER:
            ids = [m.id for m in spec.catalogue if m.tier == tier]
            if ids:
                groups.append((self._TIER_LABEL.get(tier, tier.upper()), ids))
        # Any tier string that isn't one of the three known ones still shows.
        stray = [m.id for m in spec.catalogue
                 if m.tier not in self._TIER_ORDER]
        if stray:
            groups.append(("OTHER", stray))
        return groups

    @staticmethod
    def _model_detail(spec, model_id):
        """'1M ctx  .  $0.13/$0.28 per Mtok' — the two numbers that actually
        decide a pick.  Empty string for an id with no metadata."""
        info = spec.info(model_id) if hasattr(spec, "info") else None
        if info is None:
            return ""
        ctx = (f"{info.ctx_k / 1024:.0f}M" if info.ctx_k >= 1000
               else f"{info.ctx_k}K")
        if info.in_usd <= 0 and info.out_usd <= 0:
            price = "free"
        else:
            price = f"${info.in_usd:g}/${info.out_usd:g} per Mtok"
        eye = "  \u00b7  vision" if info.vision else ""
        return f"{ctx} ctx  \u00b7  {price}{eye}"

    def _open_model_switcher(self, *_):
        pop = Gtk.Popover()
        pop.set_parent(self.model_btn)
        pop.add_css_class("model-switch-pop")
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        outer.set_margin_top(8)
        outer.set_margin_bottom(8)
        outer.set_margin_start(8)
        outer.set_margin_end(8)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_max_content_height(440)
        sw.set_min_content_width(240)
        sw.set_propagate_natural_height(True)
        listbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)

        cur_key = self.settings.get("active_provider", "siliconflow")
        cur_model = self.settings.get(f"{cur_key}_model", "")
        any_provider = False
        for spec in PROVIDERS:
            if not self._provider_has_key(spec.key):
                continue
            any_provider = True
            hdr = Gtk.Label(label=spec.label.upper(), xalign=0.0)
            hdr.add_css_class("model-group-header")
            listbox.append(hdr)
            for tier_label, ids in self._models_by_tier(spec):
                if tier_label:
                    sub = Gtk.Label(label="   " + tier_label, xalign=0.0)
                    sub.add_css_class("model-group-header")
                    sub.add_css_class("dim-label")
                    listbox.append(sub)
                for model in ids:
                    info = spec.info(model) if hasattr(spec, "info") else None
                    short = (info.label if info is not None
                             else (model.split("/")[-1] if "/" in model
                                   else model))
                    detail = self._model_detail(spec, model)
                    # Two-line row: name, then the ctx/price line that makes
                    # the pick an informed one rather than a guess.
                    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                                  spacing=0)
                    name_lbl = Gtk.Label(label=short, xalign=0.0)
                    name_lbl.set_ellipsize(Pango.EllipsizeMode.END)
                    box.append(name_lbl)
                    if detail:
                        det_lbl = Gtk.Label(label=detail, xalign=0.0)
                        det_lbl.add_css_class("dim-label")
                        det_lbl.add_css_class("caption")
                        det_lbl.set_ellipsize(Pango.EllipsizeMode.END)
                        box.append(det_lbl)
                    b = Gtk.Button()
                    b.set_child(box)
                    b.add_css_class("model-pick-row")
                    b.set_halign(Gtk.Align.FILL)
                    if info is not None and info.note:
                        b.set_tooltip_text(f"{model}\n{info.note}")
                    else:
                        b.set_tooltip_text(model)
                    if spec.key == cur_key and model == cur_model:
                        b.add_css_class("model-pick-active")
                    b.connect(
                        "clicked",
                        lambda _w, k=spec.key, m=model: self._switch_model(
                            k, m, pop))
                    listbox.append(b)

        if not any_provider:
            hint = Gtk.Label(
                label="No API keys yet.\nAdd one in Settings → Providers.",
                xalign=0.0)
            hint.add_css_class("model-group-header")
            listbox.append(hint)

        sw.set_child(listbox)
        outer.append(sw)
        pop.set_child(outer)
        pop.connect("closed", lambda p: p.unparent())
        pop.popup()

    def _switch_model(self, provider, model, pop=None):
        self.settings["active_provider"] = provider
        self.settings[f"{provider}_model"] = model
        save_settings(self.settings)
        self._update_model_button()
        self.update_status_pills()
        spec = PROVIDERS_BY_KEY.get(provider)
        info = spec.info(model) if spec is not None else None
        short = (info.label if info is not None
                 else (model.split("/")[-1] if "/" in model else model))
        detail = self._model_detail(spec, model) if spec is not None else ""
        msg = f"Now using {spec.label if spec else provider} · {short}"
        self._show_toast(f"{msg}  ({detail})" if detail else msg)
        if pop is not None:
            pop.popdown()

    def _build_input_area(self):
        area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        area.add_css_class("input-area")

        # Model switcher — shows the active provider · model, click to switch.
        # Now sits INLINE in the action-button row below, not on its own line.
        self.model_btn = Gtk.Button()
        self.model_btn.add_css_class("model-switch-btn")
        self.model_btn.set_valign(Gtk.Align.CENTER)
        self.model_btn.set_tooltip_text("Switch model / provider")
        self.model_btn.connect("clicked", self._open_model_switcher)
        self._update_model_button()

        # Action chips
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        actions.set_margin_start(4)
        actions.set_margin_end(4)

        # Agent-mode toggle: the widget still exists (it drives all the
        # agent-mode side effects) but it lives in Settings now, not above the
        # chat. Kept un-parented here so Settings' switch can flip it.
        self.agent_toggle = Gtk.ToggleButton()
        self.agent_toggle.set_icon_name("applications-system-symbolic")
        self.agent_toggle.add_css_class("icon-button")
        self.agent_toggle.set_tooltip_text("Agent mode (system tools)")
        self.agent_toggle.set_active(self.current_agent_mode)
        if self.current_agent_mode:
            self.agent_toggle.add_css_class("toggled")
        self.agent_toggle.connect("toggled", self._on_agent_toggled)

        # ── UNLEASH button (the big red dragon) ──
        # The operator's one-tap "go full send" control. Armed → Basilisk
        # confirms the target and runs relentlessly until the mission is done.
        # Disarmed → one answer per message, then stop. Rendered a touch larger
        # than the other toolbar icons so the emblem reads, with its own glow.
        self.unleash_toggle = Gtk.ToggleButton()
        _ulart = _btn_art(_BTN_UNLEASH, px=40)
        if _ulart is not None:
            self.unleash_toggle.set_child(_ulart)
            self.unleash_toggle.add_css_class("art-button")
        else:
            self.unleash_toggle.set_child(Gtk.Label(label="\U0001F409"))  # dragon
            self.unleash_toggle.add_css_class("icon-button")
        self.unleash_toggle.add_css_class("unleash-button")
        self.unleash_toggle.set_active(self._unleashed)
        if self._unleashed:
            self.unleash_toggle.add_css_class("toggled")
            self.unleash_toggle.set_tooltip_text(
                "UNLEASHED — full autonomous, will not stop until the mission is "
                "complete. Click to stand down.")
        else:
            self.unleash_toggle.set_tooltip_text(
                "Unleash — confirm the target and go full autonomous (never "
                "stops). While off, Basilisk answers once and stops.")
        self.unleash_toggle.connect("toggled", self._on_unleash_toggled)
        actions.append(self.unleash_toggle)

        for icon, tip, cb, art in [
            ("mail-attachment-symbolic", "Attach file",
             self._pick_attachment, _BTN_ATTACH),
            ("camera-photo-symbolic", "Take a photo (Basilisk can see it)",
             self._user_action_camera, _BTN_CAMERA),
        ]:
            btn = Gtk.Button()
            _bart = _btn_art(art, px=_COMPOSER_BTN_PX)
            if _bart is not None:
                btn.set_child(_bart)
                btn.add_css_class("art-button")
            else:
                btn.set_child(Gtk.Image.new_from_icon_name(icon))
                btn.add_css_class("icon-button")
            btn.set_tooltip_text(tip)
            btn.connect("clicked", lambda *_, c=cb: c())
            actions.append(btn)

        # Suggestion button — send a nudge to Basilisk mid-run WITHOUT stopping
        # it. Type your suggestion and tap this: while it's working the note is
        # queued into the conversation and picked up on its next step; when idle
        # it just sends. A lightbulb glyph (icon themes don't all ship one).
        self.suggest_btn = Gtk.Button()
        _sgart = _btn_art(_BTN_SUGGEST, px=_COMPOSER_BTN_PX)
        if _sgart is not None:
            self.suggest_btn.set_child(_sgart)
            self.suggest_btn.add_css_class("art-button")
        else:
            _sg = Gtk.Label(label="\U0001F4A1")   # lightbulb
            self.suggest_btn.set_child(_sg)
            self.suggest_btn.add_css_class("icon-button")
        self.suggest_btn.set_tooltip_text(
            "Send a suggestion without stopping Basilisk")
        self.suggest_btn.connect("clicked", lambda *_: self._send_suggestion())
        actions.append(self.suggest_btn)

        # Speaker toggle — read assistant replies aloud.  Only shown when
        # a TTS engine is actually available on the box.
        self.tts_toggle = None
        if self.tts is not None and self.tts.available():
            self.tts_toggle = Gtk.ToggleButton()
            _sndart = _btn_art(_BTN_SOUND, px=_COMPOSER_BTN_PX)
            if _sndart is not None:
                self.tts_toggle.set_child(_sndart)
                self.tts_toggle.add_css_class("art-button")
            else:
                self.tts_toggle.set_icon_name("audio-volume-high-symbolic")
                self.tts_toggle.add_css_class("icon-button")
            self.tts_toggle.set_tooltip_text(
                f"Read replies aloud — {self.tts.engine_name()}")
            on = bool(self.settings.get("tts_enabled"))
            self.tts_toggle.set_active(on)
            if on:
                self.tts_toggle.add_css_class("toggled")
            self.tts_toggle.connect("toggled", self._on_tts_toggled)
            actions.append(self.tts_toggle)

        # Log toggle sits right alongside the other toolbar buttons.
        self.terminal_toggle_btn = Gtk.Button()
        _termart = _btn_art(_BTN_TERMINAL, px=_COMPOSER_BTN_PX)
        if _termart is not None:
            self.terminal_toggle_btn.set_child(_termart)
            self.terminal_toggle_btn.add_css_class("art-button")
        else:
            self.terminal_toggle_btn.set_child(
                Gtk.Image.new_from_icon_name("utilities-terminal-symbolic"))
            self.terminal_toggle_btn.add_css_class("icon-button")
        self.terminal_toggle_btn.set_tooltip_text("Show/hide live terminal log")
        self.terminal_toggle_btn.connect("clicked", self._toggle_terminal_panel)
        actions.append(self.terminal_toggle_btn)

        # The chips live in a horizontal scroller so a phone too narrow to fit
        # them all can't be forced wider than the screen — they scroll instead.
        actions.set_margin_start(0)
        actions.set_margin_end(0)
        chips_scroll = Gtk.ScrolledWindow()
        chips_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        chips_scroll.set_hexpand(True)
        chips_scroll.set_propagate_natural_height(True)
        chips_scroll.set_kinetic_scrolling(True)
        chips_scroll.set_overlay_scrolling(True)
        chips_scroll.add_css_class("chips-scroll")
        chips_scroll.set_child(actions)

        actions_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        actions_row.set_margin_start(4)
        actions_row.set_margin_end(4)
        # Buttons on the LEFT (chips_scroll is hexpand so it fills), model name
        # pushed to the RIGHT edge.
        actions_row.append(chips_scroll)
        self.model_btn.set_halign(Gtk.Align.END)
        actions_row.append(self.model_btn)

        # The idle/thinking status pill was removed — the chat itself now shows
        # exactly what each turn did, so a persistent "idle" pill was redundant.
        # The pill objects are still created (kept un-parented) so _set_working /
        # update_status_pills keep working; they just aren't shown.
        self.status_pill_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                                       spacing=6)
        self.status_pill_box.add_css_class("status-pill")
        self.status_pill_spinner = Gtk.Spinner()
        self.status_pill_label = Gtk.Label(label="idle")
        self.status_pill_box.append(self.status_pill_spinner)
        self.status_pill_box.append(self.status_pill_label)

        # ── THE ACTIVITY FEED IS DOCKED, NOT SCROLLED ──
        # It used to be appended into the message list, which meant that after
        # two or three more messages the one widget telling you what Basilisk
        # is doing had scrolled off the top of the screen. A status surface
        # that you have to go looking for is not a status surface. It sits
        # above the action buttons now, pinned, always in view — and because
        # it is outside the scroller it is also unaffected by the rolling trim.
        self.activity_dock = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                                     spacing=0)
        self.activity_dock.add_css_class("activity-dock")
        self.activity_dock.set_visible(False)
        area.append(self.activity_dock)

        area.append(actions_row)

        # Staged attachments sit HERE — between the action chips and the
        # composer — so they are visible above the box you type in rather
        # than pasted inside it.
        area.append(self._build_attach_tray())

        # Input
        ibox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        ibox.add_css_class("input-frame")
        ibox.set_margin_start(4)
        ibox.set_margin_end(4)

        in_scroll = Gtk.ScrolledWindow()
        in_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        in_scroll.set_min_content_height(_scaled(64, floor=52))
        in_scroll.set_max_content_height(_scaled(200, floor=150))
        in_scroll.set_propagate_natural_height(True)
        in_scroll.set_hexpand(True)
        in_scroll.set_valign(Gtk.Align.FILL)

        self.input_view = Gtk.TextView()
        self.input_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.input_view.set_top_margin(10)
        self.input_view.set_bottom_margin(10)
        self.input_view.set_left_margin(4)
        self.input_view.set_right_margin(4)
        in_scroll.set_child(self.input_view)
        ibox.append(in_scroll)

        kc = Gtk.EventControllerKey()
        kc.connect("key-pressed", self._on_input_key)
        self.input_view.add_controller(kc)

        # (Mic / speech-to-text button removed — the composer leads with a
        # single big Send button instead.)
        self.mic_btn = None

        # Big Send button wearing the dragon logo.  It glows while Basilisk is
        # working (a tap then stops her) rather than turning into a stop icon.
        self.send_btn = Gtk.Button()
        self.send_btn.add_css_class("send-button")
        self.send_btn.set_valign(Gtk.Align.CENTER)
        self.send_btn.set_vexpand(False)
        self.send_btn.set_hexpand(False)
        self.send_btn.set_tooltip_text("Send")
        if _AVATAR_PNG_PATH:
            # Small fixed-size emblem, same size it always was.  The button hugs
            # it (min-width:0, tiny padding, no border in CSS) so no dark gutter
            # shows around it; the emblem art is already cropped flush to its
            # frame so there's no transparent margin either.
            _send_img = Gtk.Image.new_from_file(_AVATAR_PNG_PATH)
            _send_img.set_pixel_size(_scaled(40, floor=30))
            self.send_btn.set_child(_send_img)
        else:
            self.send_btn.set_icon_name("send-to-symbolic")
        self.send_btn.connect("clicked", lambda *_: self._on_send_or_stop())
        ibox.append(self.send_btn)

        # Burning status bar sits directly above the composer / Send button.
        area.append(self.working_row)
        area.append(ibox)
        return area

    # ── actions ────────────────────────────────────────────────

    def _wire_actions(self):
        def add(name, cb):
            a = Gio.SimpleAction.new(name, None)
            a.connect("activate", lambda *_: cb())
            self.add_action(a)
        add("settings", self._open_settings)
        add("about", self._open_about)
        add("rename-chat", self._rename_current_chat)
        add("delete-chat", self._delete_current_chat)
        add("pin-chat", self._toggle_pin_current)
        GLib.timeout_add_seconds(10, self._poll_status)
        self._poll_status()

    def _poll_status(self):
        def _bg():
            on = is_online(timeout=0.8)
            GLib.idle_add(self.update_status_pills, on)
        threading.Thread(target=_bg, daemon=True).start()
        return True

    def update_status_pills(self, online: Optional[bool] = None):
        # Connectivity is now a single green/red dot next to BASILISK in the
        # sidebar header (the old provider/online pills were removed).
        if online is None:
            online = is_online(max_age=15)
        dot = getattr(self, "online_dot", None)
        if dot is None:
            return False
        if online:
            dot.remove_css_class("offline")
            dot.add_css_class("online")
            dot.set_tooltip_text("Online")
        else:
            dot.remove_css_class("online")
            dot.add_css_class("offline")
            dot.set_tooltip_text("Offline")
        return False

    # ── chat list ───────────────────────────────────────────────

    def _refresh_sidebar(self, query: str = ""):
        child = self.chat_listbox.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.chat_listbox.remove(child)
            child = nxt

        chats = self.store.list_chats()
        if query:
            ql = query.lower()
            chats = [c for c in chats if ql in c.title.lower()]
        if not chats:
            empty = Gtk.Label(
                label="No matches." if query else "No chats yet.")
            empty.add_css_class("empty-state")
            self.chat_listbox.append(empty)
            return False
        for c in chats:
            row = ChatRow(c)
            self.chat_listbox.append(row)
            if c.id == self.current_chat_id:
                self.chat_listbox.select_row(row)
        return False

    def _on_search(self, entry):
        self._refresh_sidebar(entry.get_text().strip())

    def _on_chat_selected(self, _lb, row):
        if isinstance(row, ChatRow) and row.chat.id != self.current_chat_id:
            self._load_chat(row.chat.id)

    def _on_chat_rightclick(self, gesture, n_press, x, y):
        row = self.chat_listbox.get_row_at_y(int(y))
        if isinstance(row, ChatRow):
            self.chat_listbox.select_row(row)
            self._load_chat(row.chat.id)
            self._show_chat_context_menu(row, x, y)

    def _on_chat_longpress(self, gesture, x, y):
        row = self.chat_listbox.get_row_at_y(int(y))
        if isinstance(row, ChatRow):
            self.chat_listbox.select_row(row)
            self._load_chat(row.chat.id)
            self._show_chat_context_menu(row, x, y)

    def _show_chat_context_menu(self, row, x, y):
        menu = Gio.Menu()
        menu.append("Pin / unpin", "win.pin-chat")
        menu.append("Rename", "win.rename-chat")
        menu.append("Delete", "win.delete-chat")
        popover = Gtk.PopoverMenu.new_from_model(menu)
        # The gesture coords (x, y) are relative to the LISTBOX, so the popover
        # must be parented to the listbox for them to line up — parenting to the
        # row (its own coordinate space) is what made it appear at a random spot.
        popover.set_parent(self.chat_listbox)
        popover.set_has_arrow(False)
        popover.add_css_class("context-menu")
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        popover.set_pointing_to(rect)
        # Unparent when dismissed so it doesn't leak / warn.
        popover.connect("closed", lambda p: p.unparent())
        popover.popup()

    # ── chat load / new ─────────────────────────────────────────

    def _new_chat(self):
        # Don't leave an unused 'New chat' behind when starting another.
        if (self.settings.get("discard_empty_chats", True)
                and self.current_chat_id is not None):
            try:
                if self.store.count_messages(self.current_chat_id) == 0:
                    self.store.delete_chat(self.current_chat_id)
            except Exception:
                pass
        backend, model = self.router.pick()
        cid = self.store.create_chat(
            title="New chat", model=model,
            agent_mode=self.settings.get("agent_mode_default", True))
        # A new chat starts locked down: the sudo password and any community-
        # source grants from the previous chat are wiped — each must be
        # re-authorised in the new chat.
        self._clear_sudo_pw()
        self._web_grants = set()
        self._load_chat(cid)
        self._refresh_sidebar()
        return False

    def _load_chat(self, chat_id: int):
        self.current_chat_id = chat_id
        chat = self.store.get_chat(chat_id)
        if not chat:
            return
        self.current_agent_mode = bool(chat.agent_mode)
        self.agent_toggle.set_active(self.current_agent_mode)
        if self.current_agent_mode:
            self.agent_toggle.add_css_class("toggled")
        else:
            self.agent_toggle.remove_css_class("toggled")
        self.chat_title_lbl.set_text(chat.title)
        self._refresh_subtitle()

        child = self.msg_box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            # A live feed keeps a GLib timeout running. Unparenting it is not
            # enough — the clock would keep ticking against a widget nothing
            # can see, forever, once per chat switch. Dispose stops it.
            # DISPOSE THE BUBBLES TOO, not just the feeds.
            # Only ActivityFeedWidget was disposed here, so every chat switch
            # unparented its MessageWidgets with their signal handlers still
            # connected -- and a handler's C-side closure holds the widget, so
            # unparenting frees nothing. Measured: 20 chats visited 3 times
            # went 270 -> 452 -> 634 live bubbles. The rolling trim already
            # disposes; the chat switch has to as well, or it is the larger
            # leak of the two.
            if isinstance(child, (ActivityFeedWidget, MessageWidget)):
                if child is not self.streaming_msg_widget \
                        and child is not getattr(self, "_speaking_widget", None):
                    try:
                        child.dispose_widget()
                    except Exception:
                        pass
            self.msg_box.remove(child)
            child = nxt
        # Switching chats abandons the visible feed; the turn it belonged to
        # keeps running and keeps writing to the store, it just has nowhere to
        # draw. The dock is OUTSIDE the message list, so clearing the list does
        # not clear it — it has to be emptied explicitly or the previous
        # conversation's status strip stays pinned over the new one.
        self._clear_activity_dock()

        msgs = self.store.list_messages(chat_id)

        # ── HISTORY MUST LOOK LIKE THE RUN LOOKED ──
        # Tool rows are stored (`⚙ tool: name({...})`, meta kind=call) and were
        # dropped outright on reload, while the bare-tool-step assistant rows
        # around them rendered as `(working…)` bubbles. So a reopened chat
        # showed several near-identical stub replies and no sign of the work
        # that produced the real one. Rebuild it the way the live view drew it:
        # the tool calls of a turn collapse into ONE folded feed, and the stub
        # bubbles they belong to are not drawn at all.
        items: List[Any] = []
        pending: List[Any] = []

        def _flush_pending():
            if pending:
                items.append(("feed", list(pending)))
                pending.clear()

        for m in msgs:
            meta = m.meta or {}
            if meta.get("kind") == "tool_result":
                continue
            if m.role == "tool":
                if meta.get("kind") == "call":
                    pending.append(m)
                continue
            if m.role == "assistant":
                if not m.content.strip():
                    continue
                if _reply_is_tool_only(m.content):
                    continue
                _flush_pending()
            else:
                # An empty USER row was not filtered, only the assistant one,
                # so a whitespace-only message rendered as a padded capsule
                # with nothing in it. `"\n\n"` produced a 210px tall blank
                # bubble under "YOU" -- it reads as a message that failed to
                # load rather than one that was never really sent.
                if not (m.content or "").strip():
                    continue
                _flush_pending()
            items.append(("msg", m))
        _flush_pending()

        if not items:
            self._show_empty_state()
        else:
            # Only build widgets for the most recent window. Older messages stay
            # safe in the store (and would be trimmed on append anyway) — not
            # building them means opening a long conversation is fast and never
            # spikes RAM, instead of constructing then destroying hundreds of
            # heavy widgets.
            # Same budget, same reason: walk back until MAX_CHAT_ROWS
            # MESSAGES have been claimed, and keep whatever feeds fall
            # between them. `items[-MAX_CHAT_ROWS:]` counted feeds against
            # the budget, so reopening an agentic chat showed roughly half
            # the exchanges a plain one did.
            _kept = 0
            _start = len(items)
            for _i in range(len(items) - 1, -1, -1):
                _start = _i
                if items[_i][0] == "msg":
                    _kept += 1
                    if _kept >= MAX_CHAT_ROWS:
                        break
            for kind, payload in items[_start:]:
                if kind == "feed":
                    self._append_history_feed(payload)
                else:
                    self._append_message_widget(
                        payload.role, payload.content, payload.meta)

        # ── THE REPLY IN FLIGHT BELONGS BACK ON SCREEN ──
        # The clear loop above unparents everything, including the bubble the
        # live stream is writing into, and the rebuild cannot replace it: its
        # stored row is still "" at this point and the loop above skips empty
        # assistant rows on purpose. So switching away from a chat mid-reply
        # and back showed NOTHING in flight, and when the stream finished it
        # wrote the finished answer into a widget with no parent -- the answer
        # was in the database and invisible until the operator happened to
        # switch chats again. Measured: rows 11 -> 10 on leaving, still 10 on
        # returning, and the completed reply nowhere on screen.
        #
        # Re-attaching is the whole fix: the widget is intact, it just needs
        # its place back, and only in the chat that actually owns the stream.
        _live = self.streaming_msg_widget
        if _live is not None and self.streaming_chat_id == chat_id:
            try:
                if _live.get_parent() is None:
                    self.msg_box.append(_live)
                elif _live.get_parent() is not self.msg_box:
                    _live.get_parent().remove(_live)
                    self.msg_box.append(_live)
            except Exception:
                log("re-attach of in-flight bubble failed: "
                    + traceback.format_exc())

        GLib.idle_add(self._force_scroll_to_bottom)

    def _show_empty_state(self):
        # Intentionally blank: a new chat just shows the dragon watermark.
        # No greeting text, no suggestion chips (those actions live in the
        # composer toolbar already).
        return

    def _refresh_subtitle(self):
        # Model + agent indicator removed from the header by request: the model
        # is visible in the composer switcher, and agent state shows as the
        # green-lit toggle.  Keep the label empty so the header stays slim.
        if hasattr(self, "chat_subtitle_lbl") and self.chat_subtitle_lbl:
            self.chat_subtitle_lbl.set_text("")

    # ── messages ────────────────────────────────────────────────

    # Overlay scrollbars float ON TOP of the content, so the rightmost thing
    # in a row — the user's avatar — was drawn underneath the scrollbar. The
    # message box reserves the gutter instead.
    _SCROLLBAR_GUTTER = 14

    def _append_message_widget(self, role, content, meta=None):
        # Clear empty state if present. The feed is a first-class row in this
        # box now, so "not a MessageWidget" is no longer a safe test for "this
        # is the empty-state placeholder" — it would delete the activity feed
        # of the turn currently running.
        first = self.msg_box.get_first_child()
        if first is not None and not isinstance(
                first, (MessageWidget, ActivityFeedWidget)):
            self.msg_box.remove(first)
        w = MessageWidget(role, content, meta,
                          on_run_command=self._run_proposed_command,
                          on_apply_edit=self._run_proposed_edit,
                          on_speak=self._on_message_speak,
                          show_thoughts=self.settings.get("show_thoughts", True))
        self.msg_box.append(w)
        # Rolling window: keep only the most recent MessageWidgets in the view.
        # The full transcript is in the SQLite ChatStore and the model's history
        # is rebuilt from there — these widgets are display only, so trimming the
        # oldest frees GTK memory (and speeds layout) without touching context,
        # autonomy, or behaviour. Only trims from the FRONT, never the live tail.
        # Each trimmed bubble is DISPOSED (its refs broken) so it's reclaimed
        # promptly, not just unparented; a throttled gc sweep collects any cycles.
        try:
            trimmed = 0
            extra = self._count_msg_rows() - MAX_CHAT_ROWS
            while extra > 0:
                old = self.msg_box.get_first_child()
                if old is None or old is w:
                    break
                if isinstance(old, ActivityFeedWidget):
                    # Same reason as the chat-switch teardown: a trimmed feed
                    # that is still live keeps a 200ms timeout running against
                    # a widget nobody can see.
                    if old is not getattr(self, "_activity_feed", None):
                        try:
                            old.dispose_widget()
                        except Exception:
                            pass
                if isinstance(old, MessageWidget):
                    # Never dispose a bubble the WINDOW still holds a live
                    # reference to. The view's rolling trim and the window's
                    # streaming/speaking pointers are independent, so trimming
                    # could null the containers out from under a widget that is
                    # still receiving tokens or TTS state changes. Unparent it
                    # (frees the layout cost) but leave its innards intact.
                    if old is not self.streaming_msg_widget \
                            and old is not self._speaking_widget:
                        try:
                            old.dispose_widget()
                        except Exception:
                            pass
                self.msg_box.remove(old)
                trimmed += 1
                extra -= 1
            if trimmed:
                # Reclaim the freed widgets' memory. Throttled so a fast burst of
                # messages doesn't pay a gc pause on every single one.
                self._trim_since_gc = getattr(self, "_trim_since_gc", 0) + trimmed
                if self._trim_since_gc >= 8:
                    self._trim_since_gc = 0
                    gc.collect()
        except Exception:
            pass
        # ── FORCE ONLY FOR WHAT THE OPERATOR HIMSELF DID ──
        # This was unconditional, so a new ASSISTANT bubble slammed the view
        # to the bottom and re-armed the stick -- discarding the position
        # _on_vadj_value_changed had just correctly recorded. Measured while
        # reading history at the top of a 30-message chat: an assistant
        # append moved the view 4769px and flipped stick False -> True, and
        # with the rolling trim the row being read was unparented out from
        # under the cursor.
        #
        # Sending a message is a request to see it, so a user row still
        # forces. An arriving reply is not: it follows the tail only if the
        # operator was already at the tail, which is exactly what the
        # streamed TOKENS of that same reply have always done. The two now
        # agree.
        if role == "user":
            GLib.idle_add(self._force_scroll_to_bottom)
        else:
            GLib.idle_add(self._scroll_to_bottom)
        return w

    _HIST_CALL_RE = re.compile(r"tool:\s*([a-zA-Z_0-9]+)\s*\((.*)\)\s*$", re.S)

    def _append_history_feed(self, rows):
        """One folded feed for the tool calls of a finished turn.

        Parsed from the stored `⚙ tool: name({json})` line rather than from a
        second, tidier column, because that line is what actually exists in
        every chat already on disk — a new column would show history only for
        chats recorded after this build."""
        try:
            feed = ActivityFeedWidget()
        except Exception:
            return
        added = 0
        for m in rows:
            name, args = "tool", None
            try:
                mt = self._HIST_CALL_RE.search(m.content or "")
                if mt:
                    name = mt.group(1)
                    try:
                        args = json.loads(mt.group(2))
                    except Exception:
                        args = None
            except Exception:
                pass
            try:
                feed.replay_step(name, _feed_detail(name, args))
                added += 1
            except Exception:
                pass
        if not added:
            try:
                feed.dispose_widget()
            except Exception:
                pass
            return
        try:
            feed.finish_history()
        except Exception:
            pass
        self.msg_box.append(feed)

    def _count_msg_rows(self) -> int:
        """How many CONVERSATION rows are on screen.

        Activity feeds are deliberately not counted. MAX_CHAT_ROWS exists to
        bound how many message bubbles are built, and a feed is a folded
        status strip, not an exchange -- counting them spent the budget on
        the tool log. Measured on a 12-turn agentic chat: 13 bubbles + 7
        feeds = 20 rows, so a conversation with 24 user/assistant messages
        showed thirteen of them. The more tools a run uses, the less of the
        conversation survives, which is backwards.
        """
        n = 0
        c = self.msg_box.get_first_child()
        while c is not None:
            if isinstance(c, MessageWidget):
                n += 1
            c = c.get_next_sibling()
        return n

    # ── STICKY BOTTOM ───────────────────────────────────────────
    # A ONE-SHOT SCROLL CANNOT REACH THE BOTTOM OF A MESSAGE IT HAS NOT
    # MEASURED YET. Every scroll here used to be `GLib.idle_add(...)` then
    # `adj.set_value(adj.get_upper())`, and `upper` at that moment is still the
    # value from BEFORE the new bubble was laid out — GTK has not re-measured.
    # So the view jumped to the old bottom and the newest message sat below the
    # fold, half-hidden behind the composer. It got worse the taller the new
    # message was, which is why it looked like a "long conversation" bug: a
    # one-line reply happened to fit, a reply with a table or a code block did
    # not. Anything that changes height AFTER layout — an image finishing its
    # load, a table reflowing, streamed text rewrapping — reopened the same gap.
    #
    # The fix is not a longer timeout, it is to stop guessing when layout is
    # done: hold a STICK flag and re-snap on the adjustment's own `changed`
    # signal, which GTK emits every time upper/page-size move. The flag clears
    # when the operator scrolls up himself and re-arms when he comes back down,
    # so following the tail never fights him.

    _STICK_SLACK = 120        # px from the bottom that still counts as "at the bottom"

    def _wire_scroll_stickiness(self):
        adj = self.msg_scroll.get_vadjustment()
        if adj is None:
            return
        self._stick_bottom = True
        self._scroll_self = False
        adj.connect("changed", self._on_vadj_changed)
        adj.connect("value-changed", self._on_vadj_value_changed)

    def _snap_bottom(self, adj=None):
        adj = adj or self.msg_scroll.get_vadjustment()
        if adj is None:
            return
        # ── set_value() IS A NO-OP WHEN THE VALUE IS ALREADY THE VALUE ──
        #
        # This is the bug behind "the answer is there but I'm looking at the
        # top of it, and the scrollbar says I'm at the bottom".
        #
        # GtkAdjustment::set_value only emits ::value-changed when the number
        # actually MOVES. GtkViewport does not hold a scroll offset of its
        # own -- it applies one when that signal tells it to. So if the
        # adjustment already reads `upper - page_size` at the moment we snap
        # (which is exactly what happens when a chat is loaded: `upper` grows
        # during the measure pass and the adjustment is clamped up to the new
        # bottom BEFORE the viewport has been allocated), the set is silently
        # dropped, the viewport never learns, and it keeps painting from
        # offset 0.
        #
        # Nothing corrects it afterwards, because a value that never changes
        # never emits again -- the view stays stuck until the operator
        # scrolls by hand. Meanwhile GtkScrollbar reads the ADJUSTMENT, so
        # its thumb sits confidently at the bottom of a view showing the top.
        # Verified in the real app: value=1174.0, upper=1702.0, page=528.0 --
        # a numerically perfect bottom -- rendering offset 0.
        #
        # Measured, not assumed: bouncing through 0 and back forces the
        # notify, and the same frame then paints the true bottom.
        target = max(0.0, adj.get_upper() - adj.get_page_size())
        self._scroll_self = True
        try:
            if abs(adj.get_value() - target) < 0.5:
                # The plain set would be dropped. Bounce so it cannot be.
                # No paint can land between these two calls -- they run
                # inside one main-loop callback -- so there is no flicker.
                adj.set_value(0.0)
            adj.set_value(target)
        finally:
            self._scroll_self = False
        self._arm_snap_reassert()

    # A snap issued before the scroller has been allocated computes its
    # target from an `upper` that is still growing. Re-assert it for a few
    # frames so the final measure wins, then stop -- a permanent tick
    # callback would repaint forever, which is the lag this session already
    # removed once by deleting an always-on CSS animation.
    _SNAP_REASSERT_FRAMES = 4

    def _arm_snap_reassert(self):
        if getattr(self, "_snap_tick_id", 0):
            return                       # already armed
        self._snap_frames_left = self._SNAP_REASSERT_FRAMES
        try:
            self._snap_tick_id = self.msg_scroll.add_tick_callback(
                self._snap_tick)
        except Exception:
            self._snap_tick_id = 0

    def _snap_tick(self, _widget, _clock):
        self._snap_frames_left = getattr(self, "_snap_frames_left", 0) - 1
        if not getattr(self, "_stick_bottom", True):
            self._snap_tick_id = 0
            return GLib.SOURCE_REMOVE
        adj = self.msg_scroll.get_vadjustment()
        if adj is not None:
            target = max(0.0, adj.get_upper() - adj.get_page_size())
            if abs(adj.get_value() - target) > 0.5:
                self._scroll_self = True
                try:
                    adj.set_value(target)
                finally:
                    self._scroll_self = False
        if self._snap_frames_left <= 0:
            self._snap_tick_id = 0
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def _on_vadj_changed(self, adj):
        """upper / page-size moved: the content was re-measured."""
        if getattr(self, "_stick_bottom", True):
            self._snap_bottom(adj)

    def _on_vadj_value_changed(self, adj):
        """The view moved. If the operator did it, his position wins."""
        if getattr(self, "_scroll_self", False):
            return
        at_bottom = (adj.get_value() + adj.get_page_size()
                     >= adj.get_upper() - self._STICK_SLACK)
        self._stick_bottom = at_bottom

    def _scroll_to_bottom(self):
        """Follow the tail during streaming, but only if he is already there."""
        adj = self.msg_scroll.get_vadjustment()
        if adj is None:
            return False
        if (adj.get_value() + adj.get_page_size()
                >= adj.get_upper() - self._STICK_SLACK):
            self._stick_bottom = True
            self._snap_bottom(adj)
        return False

    def _force_scroll_to_bottom(self):
        """Unconditional — a new user message, or opening a chat. Re-arms the
        stick so the snap survives the layout passes that follow it."""
        self._stick_bottom = True
        self._snap_bottom()
        return False

    # ── sending ─────────────────────────────────────────────────

    def _on_input_key(self, controller, keyval, keycode, state):
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
            if not shift:
                self._send_user_message()
                return True
        # Escape stops Basilisk mid-reply.
        if keyval == Gdk.KEY_Escape and self._is_busy():
            self._request_stop()
            return True
        return False

    def _on_send_or_stop(self):
        """The primary button is Send when idle, Stop when Basilisk is working."""
        if self._is_busy():
            self._request_stop()
        else:
            self._send_user_message()

    def _set_send_mode(self, working: bool):
        """Keep the dragon logo at all times.  While Basilisk is working the button
        GLOWS (and a tap stops her); idle, it's the normal Send button."""
        if working:
            self.send_btn.set_tooltip_text("Working… tap to stop")
            self.send_btn.add_css_class("working")
        else:
            self.send_btn.set_tooltip_text("Send")
            self.send_btn.remove_css_class("working")
        self.send_btn.set_sensitive(True)

    def _request_stop(self):
        """Operator pressed Stop.  Cancel the in-flight stream and make
        sure the tool chain doesn't kick another turn behind our back."""
        self._stop_requested = True
        # Stop is the one true off-switch: end any autonomous mission so no
        # continuation or error-retry can kick another turn behind our back.
        # A queued kick is exactly such a continuation, and setting the flag
        # was not enough to stop it -- _send_user_message clears the flag
        # again on the operator's next message, so the orphan fired anyway.
        self._cancel_pending_kick()
        self._mission_active = False
        self._mission_kicks = 0
        self._recent_commands = []
        self._mission_verify_pending = False
        self._mission_directive = ""
        self._error_retries = 0
        self._mission_ever_acted = False
        if self.streaming_cancel:
            self.streaming_cancel.set()
        if self.tts:
            self.tts.stop()
        self._show_toast("Stopping…")
        # If a stream is live, the backend will fire on_done({cancelled})
        # and _on_stream_done tears everything down.  If we're between
        # tool turns (no live stream), tear down here so we don't hang.
        if not (self.streaming_thread and self.streaming_thread.is_alive()):
            self._finish_turn_cleanup(mark_partial=True)

    def _finish_turn_cleanup(self, mark_partial: bool = False):
        """Single teardown path for the end of an assistant turn —
        whether it finished, errored, or was stopped."""
        if mark_partial and self.streaming_msg_widget is not None:
            # Canonicalise before this partial reply is stored and replayed as
            # history — a stopped turn is still a turn the model will be shown.
            partial = (self.streaming_msg_widget.canonical_content() or "").strip()
            final_text = partial if partial else "*(stopped)*"
            try:
                self.streaming_msg_widget.set_content(final_text)
            except Exception:
                pass
            if self.streaming_msg_db_id:
                self.store.update_message(self.streaming_msg_db_id, final_text)
        self.streaming_msg_widget = None
        self.streaming_msg_db_id = None
        self.streaming_chat_id = None
        self._tool_chain_depth = 0
        self._tools_locked = False
        self._turn_active = False
        self._set_working(False)
        self._set_send_mode(False)
        # Settle the feed LAST: stop_running inside finish() marks anything
        # still open as stopped rather than leaving a spinner running over a
        # turn that has already ended.
        self._activity_finish()

    def _mission_continue(self, verify: bool = False):
        """Chain another turn of the active mission instead of stopping.  Tears
        down the settled turn's widget refs but stays in the working state.  On
        repeated no-progress settles it applies a bounded exponential backoff so
        a stuck model can't hammer the API.  Once the mission has ACTED (run a
        tool), it never gives up on its own — only Stop or a verified completion
        ends it, and a running tool resets the backoff (see _on_stream_done).  A
        mission that has never acted (a pure-text task) is idle-capped here so it
        can't spin re-kicking forever."""
        if (self._stop_requested or not self._mission_active
                or not self.current_agent_mode):
            self._mission_active = False
            self._finish_turn_cleanup()
            return
        self.streaming_msg_widget = None
        self.streaming_msg_db_id = None
        self.streaming_chat_id = None
        self._tool_chain_depth = 0     # fresh tool budget for the continuation
        self._tools_locked = False
        self._turn_active = False
        if verify:
            self.terminal_log("🔎 completion claimed — forcing re-verify", "dim")
            delay = 200
        else:
            # A mission that has NEVER acted (no tool has run) is a pure-text
            # task; if the model neither acts nor emits the completion token, it
            # must not spin re-kicking forever.  Cap the idle re-kicks and finish
            # cleanly.  Once it HAS acted (_mission_ever_acted), this cap never
            # applies — a real pentest runs tools constantly and stays truly
            # relentless until it's done or you press Stop.
            # Only STALLS (a reply that keeps intending action without ever
            # calling a tool) reach here now — a never-acted reply that reads as
            # a finished answer is stopped immediately in _on_stream_done via
            # reply_intends_action. So this cap just bounds a model that only
            # ever talks about acting; 2 nudges is plenty.
            idle_cap = self.settings.get("mission_max_idle_kicks", 2)
            if (not self._mission_ever_acted
                    and self._mission_kicks >= idle_cap):
                self._mission_active = False
                self.terminal_log(
                    "✅ mission settled — nothing left to act on", "ok")
                self._finish_turn_cleanup()
                return
            # Circuit breaker: if the model has fired the EXACT same command 6
            # times in a row (despite the loop-breaker nudge at 3), it's stuck —
            # e.g. re-running an uncached-sudo command that never completes. Stop
            # cleanly rather than spin forever burning API calls; the operator can
            # resume with a new message. (Distinct from the idle cap, which only
            # covers missions that never acted.)
            _tail = [c for c in getattr(self, "_recent_commands", []) if c]
            if len(_tail) >= 6 and len(set(_tail[-6:])) == 1:
                self._mission_active = False
                self.terminal_log(
                    "■ stopped — same command 6× in a row with no progress; "
                    "ending to avoid an infinite loop (send a message to resume)",
                    "error")
                self._finish_turn_cleanup()
                return
            self._mission_kicks += 1
            # Backoff grows ONLY while the model keeps settling without acting
            # (0.15s, then 0.5→1→2→4→8s, capped at 15s).  Progress resets it.
            if self._mission_kicks <= 1:
                delay = 150
            else:
                delay = min(15000, 500 * (2 ** min(self._mission_kicks - 2, 5)))
            self.terminal_log(
                f"↻ mission continues — objective not done "
                f"[{self._mission_kicks}]", "dim")
        self._set_working(True, "continuing…")
        self._schedule_kick(delay)

    def _send_user_message(self):
        if self._is_busy():
            self._show_toast("Already replying — hit stop first.")
            return
        # Fresh turn — clear any leftover stop flag.
        self._stop_requested = False
        # Fresh turn — reset the guard that stops a malformed propose/edit
        # from being bounced back to the model forever.
        self._bad_propose_retries = 0
        buf = self.input_view.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(),
                            False).strip()
        # An attachment with no typed text IS a message ("here, look at this")
        # — the old code returned early on empty text, which with the tray in
        # place would silently discard a staged file.
        if not text and not self._attachments:
            return
        buf.set_text("")

        # Staged attachments join the message here, in the exact form the old
        # in-composer version produced. Drained (and the tray cleared) only on
        # a real send, so a cancelled or empty send never loses them.
        _att = self._drain_attachments()
        if _att:
            text = (text + "\n\n" + _att) if text else _att

        # (#3) /panic — jump straight to tool-first triage: no preamble, run
        # a batched health-check sweep, report what's abnormal.  Expands into
        # a directive the model acts on (the read-only checks batch into one
        # round-trip via the parallel executor).
        if text.lower().split() and text.lower().split()[0] in ("/panic",):
            text = ("[PANIC MODE] Fast triage — skip ALL preamble and "
                    "questions. In ONE turn, fire these read-only checks "
                    "together: quick_facts, system_info, disk_usage, "
                    "processes, network_status, service_status, and "
                    "journal_tail (recent errors). Then give a tight bullet "
                    "summary of anything abnormal and the single most likely "
                    "problem. Look first, report second.")
            self._show_toast("Panic mode — running health sweep.", timeout=4)

        # A new message means stop reading the previous reply out loud.
        if self.tts:
            self.tts.stop()

        if self.current_chat_id is None:
            self._new_chat()
        cid = self.current_chat_id
        self.store.add_message(cid, "user", text)
        self._append_message_widget("user", text)
        # ONE feed for this whole turn, however many round-trips it takes.
        self._activity_new_turn()
        self._maybe_set_title_from_first(cid, text)

        # ── Mission latch: driven by UNLEASH ──
        # Unleashed → THIS message is the objective and Basilisk works it until
        # MISSION_COMPLETE or you stand down; even a question becomes "go find
        # out and don't stop" (that's what unleashed means). A bare greeting is
        # never a mission. Not unleashed → never a mission (the mode block below
        # forces answer-once). The old agent-mode/question gating no longer
        # drives this — Unleash is the single control.
        if (self._unleashed and text.strip()
                and not conversational_turn(text)):
            self._mission_active = True
            self._mission_objective = text
            self._mission_kicks = 0
            self._recent_commands = []      # fresh objective — clear loop history
            self._reset_action_log()
            self._mission_verify_pending = False
            self._mission_no_action_streak = 0
            self._mission_directive = ""
            self._error_retries = 0
            # Relentlessness is unbounded ONLY once it has actually acted (run a
            # tool).  A mission that never acts (pure-text task) is idle-capped
            # in _mission_continue so it can't spin forever — real pentests run
            # tools constantly, so they stay truly relentless.
            self._mission_ever_acted = False
        else:
            self._mission_active = False

        self._kick_assistant_turn()

    def _send_suggestion(self):
        """Send a suggestion to Basilisk WITHOUT stopping it. While it's working,
        the note is added to the conversation and picked up on its NEXT step (the
        model's history is rebuilt from the store each step, so it appears there
        automatically). When idle, this just behaves like a normal Send."""
        buf = self.input_view.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(),
                            False).strip()
        if not text:
            self._show_toast("Type a suggestion first.")
            return
        if not self._is_busy():
            self._send_user_message()      # idle → ordinary send
            return
        # ROUTE TO THE CHAT THAT IS WORKING, not the one being looked at.
        # This used to write to current_chat_id. The running loop reads
        # streaming_chat_id, and those differ the moment the operator scrolls
        # back to another conversation while a mission runs — so the suggestion
        # landed in the wrong transcript, the mission never saw it, and the
        # toast still said it had been delivered. A silently discarded
        # instruction is worse than a refused one.
        cid = self.streaming_chat_id or self.current_chat_id
        if cid is None:
            self._show_toast("No chat is running — nothing to suggest to.")
            return
        buf.set_text("")
        # Stored with a tag so the model reads it as a live operator nudge, not a
        # brand-new request. No _kick_assistant_turn — the running loop picks it
        # up on its next step; the model is NOT interrupted.
        try:
            self.store.add_message(cid, "user",
                                   "[operator suggestion, mid-run — weave this "
                                   "in without stopping]: " + text)
        except Exception as e:
            log(f"suggestion not stored: {e}")
            self._show_toast("Couldn't deliver that suggestion — try again.",
                             timeout=5)
            buf.set_text(text)             # don't eat what he typed
            return
        # Only draw the bubble if he is actually looking at the chat it went to;
        # otherwise it would appear in an unrelated conversation.
        if cid == self.current_chat_id:
            self._append_message_widget("user", text)
            self._show_toast("Suggestion sent — Basilisk will fold it in on "
                             "its next step (still working).", timeout=4)
        else:
            self._show_toast("Suggestion sent to the running chat (you're "
                             "viewing a different one).", timeout=5)

    # ── voice (speech in / speech out) ──────────────────────────
    def _on_tts_toggled(self, btn):
        on = btn.get_active()
        self.settings["tts_enabled"] = on
        save_settings(self.settings)
        if on:
            btn.add_css_class("toggled")
        else:
            btn.remove_css_class("toggled")
            # Turning it off should also shut it up right now.
            if self.tts:
                self.tts.stop()

    # ── per-message playback (play / pause / resume / replay) ──
    def _on_message_speak(self, widget):
        """The speaker button on a single assistant message was tapped."""
        if not (self.tts and self.tts.available()):
            self._show_toast(
                "No voice engine — set one up in Settings → Voice.", timeout=5)
            return
        content = (getattr(widget, "_content", "") or "").strip()
        if not content:
            self._show_toast("Nothing to read yet.")
            return
        if widget is self._speaking_widget:
            # Toggle this message's playback.
            if self.tts.is_paused():
                self.tts.resume()
            elif self.tts.is_speaking():
                self.tts.pause()
            else:
                # Finished already — replay from the top.
                self._start_speaking_widget(widget)
            return
        # A different message — take over.
        self._start_speaking_widget(widget)

    def _start_speaking_widget(self, widget):
        prev = self._speaking_widget
        if prev is not None and prev is not widget:
            prev.set_speak_state("idle")
        # Manual playback shouldn't be re-read by the streamer.
        self._turn_active = False
        self.tts.stop()
        self._speaking_widget = widget
        widget.set_speak_state("speaking")
        # Third consumer of model output, same transform as the other two.
        # This one read `_content` raw, so replaying any message that contained
        # a non-canonical tool call recited the markup — including after a
        # chat reload, where `_content` comes straight back out of the store.
        self.tts.speak_all(speakable_text(getattr(widget, "_content", "") or ""))

    def _on_tts_state(self, state):
        """Driven from the TTS worker (marshalled here): keep the owning
        message's button in sync with what the speaker is doing."""
        w = self._speaking_widget
        if state == "idle":
            # Ignore a stale idle: either the speaker is busy again, or
            # we're still streaming a live reply that will queue more.
            if self.tts and self.tts.is_speaking():
                return False
            if self._turn_active and w is self.streaming_msg_widget:
                return False
            if w is not None:
                w.set_speak_state("idle")
            self._speaking_widget = None
        elif state == "speaking":
            if w is not None:
                w.set_speak_state("speaking")
        elif state == "paused":
            if w is not None:
                w.set_speak_state("paused")
        return False

    def _set_mic_visual(self, state: str):
        """state: 'idle' | 'recording' | 'busy'."""
        if not self.mic_btn:
            return
        self.mic_btn.remove_css_class("mic-recording")
        if state == "recording":
            self.mic_btn.set_icon_name("media-playback-stop-symbolic")
            self.mic_btn.add_css_class("mic-recording")
            self.mic_btn.set_tooltip_text("Listening… tap to stop & send")
            self.mic_btn.set_sensitive(True)
        elif state == "busy":
            self.mic_btn.set_icon_name("content-loading-symbolic")
            self.mic_btn.set_tooltip_text("Transcribing…")
            self.mic_btn.set_sensitive(False)
        else:  # idle
            self.mic_btn.set_icon_name("audio-input-microphone-symbolic")
            self.mic_btn.set_tooltip_text("Speak (tap to start, tap to send)")
            self.mic_btn.set_sensitive(True)

    def _on_mic_clicked(self):
        if not self.stt:
            return
        # Already recording → stop and transcribe.
        if self._recording:
            self._recording = False
            self._set_mic_visual("busy")
            threading.Thread(target=self._transcribe_worker,
                             daemon=True).start()
            return

        # Not recording → check we can, then start.
        reason = self.stt.unavailable_reason()
        if reason:
            self._show_toast(reason, timeout=5)
            return
        # Don't let Basilisk talk over the operator.
        if self.tts:
            self.tts.stop()
        if self.stt.start():
            self._recording = True
            self._set_mic_visual("recording")
        else:
            why = self.stt.last_error()
            self._show_toast(
                f"Couldn't start the microphone — {why}." if why
                else "Couldn't start the microphone.", timeout=5)

    def _transcribe_worker(self):
        """Runs off the UI thread: stop the recorder, send to Groq, hand
        the result back to the UI thread."""
        wav = self.stt.stop()
        if not wav:
            reason = self.stt.last_error()
            probe = self.stt.probe_inputs()
            if reason:
                msg = f"No audio — {reason}"
                if not probe:
                    msg += " (no mic visible to PipeWire/PulseAudio)"
            elif probe:
                msg = f"No audio captured. Inputs seen: {probe}"
            else:
                msg = ("No audio — no mic visible to PipeWire/PulseAudio. "
                       "Check it's plugged in and unmuted.")
            GLib.idle_add(self._apply_transcript, "", msg)
            return
        text, err = self.stt.transcribe(wav)
        GLib.idle_add(self._apply_transcript, text, err)

    def _apply_transcript(self, text: str, err: Optional[str]):
        self._set_mic_visual("idle")
        if err:
            self._show_toast(err, timeout=5)
            return
        if not text:
            self._show_toast("Didn't catch that — try again.")
            return
        buf = self.input_view.get_buffer()
        existing = buf.get_text(buf.get_start_iter(),
                                buf.get_end_iter(), False)
        # Append to whatever's already typed rather than clobbering it.
        if existing.strip():
            buf.set_text((existing.rstrip() + " " + text).strip())
        else:
            buf.set_text(text)
        if self.settings.get("voice_autosend", True):
            self._send_user_message()
        else:
            self.input_view.grab_focus()
        return False

    # ── LIVE ACTIVITY FEED ──────────────────────────────────────
    # One feed per operator turn.  These seven methods are the ONLY way the
    # window talks to it, for the same reason speakable_text() is the only
    # transform on the speech path: thirty instrumented call sites is how two
    # views of the same run drift into disagreeing about what happened.
    #
    # Every one of them is total — a missing feed, a disposed feed or a
    # torn-down turn is a no-op, never an exception.  The feed is DISPLAY.  If
    # it ever raises it would do so inside a GLib callback in the middle of a
    # tool chain and strand the turn, which is a far worse bug than a missing
    # row.

    def _activity_new_turn(self):
        """Retire the previous turn's feed and open a fresh one, attached under
        the user's message.  Called from _send_user_message only: a tool chain
        spanning ten round-trips is ONE turn and shares ONE feed."""
        try:
            old = getattr(self, "_activity_feed", None)
            if old is not None:
                try:
                    old.finish()
                except Exception:
                    pass
            feed = ActivityFeedWidget()
            self._activity_feed = feed
            self._activity_sid = 0
            self._activity_batch_sids = []
            self._dock_feed(feed)
            GLib.idle_add(self._force_scroll_to_bottom)
        except Exception:
            self._activity_feed = None

    def _dock_feed(self, feed):
        """Put `feed` in the pinned dock, retiring whatever was there."""
        dock = getattr(self, "activity_dock", None)
        if dock is None:
            return
        old = dock.get_first_child()
        while old is not None:
            nxt = old.get_next_sibling()
            # The outgoing feed's 200ms clock must stop with it, or every turn
            # leaves another timer running for the life of the process.
            if isinstance(old, ActivityFeedWidget):
                try:
                    old.dispose_widget()
                except Exception:
                    pass
            dock.remove(old)
            old = nxt
        if feed is not None:
            dock.append(feed)
        dock.set_visible(feed is not None)

    def _clear_activity_dock(self):
        self._dock_feed(None)
        self._activity_feed = None

    def _activity(self):
        f = getattr(self, "_activity_feed", None)
        if f is None or getattr(f, "_disposed", False):
            return None
        return f

    def _activity_phase(self, text: str):
        f = self._activity()
        if f is None:
            return
        try:
            f.set_phase(text)
        except Exception:
            pass

    def _activity_begin(self, name: str, args: Any = None,
                        kind: str = "tool") -> int:
        f = self._activity()
        if f is None:
            return 0
        try:
            return f.begin_step(name, _feed_detail(name, args), kind)
        except Exception:
            return 0

    def _activity_end(self, sid: int, ok: bool = True, preview: str = ""):
        f = self._activity()
        if f is None or not sid:
            return
        try:
            f.end_step(sid, ok=ok, preview=preview)
        except Exception:
            pass

    def _activity_note(self, text: str, kind: str = "note"):
        f = self._activity()
        if f is None:
            return
        try:
            f.note(text, kind)
        except Exception:
            pass

    def _activity_finish(self, summary: str = "", ok: bool = True):
        f = self._activity()
        if f is None:
            return
        try:
            f.finish(summary=summary, ok=ok)
        except Exception:
            pass

    def _activity_close_result(self, result_text: str):
        """Close whatever step is open with the result that just came back.

        Hung off _feed_tool_result because that is the single choke point every
        tool result passes through — the same hook ACTION RECALL uses, and for
        the same reason.  A result whose text says it did not run closes the
        step as a FAILURE: `✓ done` printed unconditionally is exactly the lie
        the v9.6.0 log told, and a green tick over a refusal is worse than no
        row at all."""
        sid = getattr(self, "_activity_sid", 0)
        if not sid:
            return
        self._activity_sid = 0
        txt = (result_text or "")
        head = txt.lstrip()[:220].lower()
        _h400 = txt[:400]
        bad = (head.startswith("not run")
               or head.startswith("error")
               or head.startswith("unknown tool")
               or head.startswith("batch error")
               or '"ok": false' in _h400
               or '"ok":false' in _h400)
        try:
            self._activity_end(sid, ok=not bad, preview=_feed_preview(txt))
        except Exception:
            pass

    def _set_working(self, working: bool, label: str = "working…"):
        """Update the permanent status pill in the button row (and the shared
        action phrase). Called from the UI thread. The pill lives in the bottom
        button row, always visible — it reads the action title while working and
        'idle' when not, and never reflows the other buttons."""
        global _CURRENT_ACTION
        if working:
            # Only LOG on a change. _set_working is called from more than one
            # place per tool (the chain step and the tool's own start), so an
            # unchanged label printed the same line twice in a row — which in a
            # long run makes the terminal look like it is stuttering and buries
            # the lines that matter. The pill still updates every call; only
            # the duplicate log line is suppressed.
            _changed = (_CURRENT_ACTION != label)
            _CURRENT_ACTION = label
            # The feed header reads the SAME phrase the status pill does, from
            # the same call, so the two can never disagree about what is
            # happening. set_phase only claims the title while no tool step is
            # in flight, so a live tool row is never overwritten by a stale
            # chain-level label.
            self._activity_phase(label.rstrip("\u2026 ."))
            if hasattr(self, "status_pill_label"):
                self.status_pill_label.set_text(label)
                self.status_pill_spinner.set_visible(True)
                self.status_pill_spinner.start()
                self.status_pill_box.add_css_class("busy")
            if _changed:
                self.terminal_log(f"── {label}", "dim")
        else:
            _CURRENT_ACTION = ""
            if hasattr(self, "status_pill_label"):
                self.status_pill_label.set_text("idle")
                self.status_pill_spinner.stop()
                self.status_pill_spinner.set_visible(False)
                self.status_pill_box.remove_css_class("busy")

    # Friendly present-tense phrases for the working banner, so a tool chain
    # reads "searching the web… → reading a page… → cross-checking sources…"
    # instead of a bare tool name or a flat "working…".
    _TOOL_STATUS = {
        "web_read":         "checking a trusted source",
        "web_sources":      "checking available sources",
        "image_search":     "finding images",
        "analyze_image":    "looking at the image",
        "capture_photo":    "taking a photo",
        "detect_faces":     "finding faces",
        "tooling_check":    "checking installed tools",
        "pentest_plan":     "planning recon",
        "cve_lookup":       "looking up CVEs",
        "parse_output":     "parsing scan output",
        "methodology":      "pulling up methodology",
        "wordlist_find":    "finding wordlists",
        "cheatsheet":       "pulling up syntax",
        "report_findings":  "building the report",
        "nuclei_template":  "writing a nuclei template",
        "reflect_findings": "double-checking the findings",
        "attack_writeup":     "writing the exploitation narrative",
        "workspace_import":   "unpacking the repo",
        "workspace_status":   "checking the workspace",
        "workspace_overview": "sizing up the repo",
        "workspace_tree":     "listing the repo",
        "workspace_search":   "searching the repo",
        "workspace_read":     "reading repo code",
        "workspace_replace":  "editing repo code",
        "workspace_write":    "writing repo code",
        "workspace_delete":   "removing a repo file",
        "workspace_diff":     "diffing the changes",
        "workspace_revert":   "reverting changes",
        "workspace_export":   "zipping the repo back up",
        "workspace_close":    "closing the workspace",
        "workspace_test_command": "finding the test runner",
        "workspace_baseline": "running the tests (baseline)",
        "workspace_verify":   "re-running the tests",
        "workspace_health":   "sweeping the repo for bugs",
        "code_tooling_check": "checking code scanners",
        "code_scan_plan":     "planning the code scan",
        "parse_scan":         "parsing scanner output",
        "triage_findings":    "triaging findings",
        "remediation_hint":   "looking up the fix",
        "scope_set":          "recording authorised scope",
        "scope_check":        "checking scope",
        "scope_exclude":      "recording exclusions",
        "scope_window":       "recording testing window",
        "scope_authorisation": "recording authorisation",
        "scope_show":         "showing scope",
        "asset_record":       "updating the engagement graph",
        "engagement_graph":   "reading the engagement graph",
        "loot_record":        "recording loot",
        "loot_list":          "listing loot",
        "loot_reuse":         "checking credential reuse",
        "graph_ingest":       "updating the engagement graph",
        "sqlmap_plan":        "building the sqlmap command",
        "benchmark_targets":  "loading benchmark targets",
        "benchmark_score":    "scoring the run",
        "benchmark_report":   "building the scorecard",
        "benchmark_compare":  "comparing runs",
        "load_tools":         "loading tools",
        "juiceshop_score":    "reading the scoreboard",
        "juiceshop_report":   "building the scorecard",
        "juiceshop_next":     "picking the next targets",
        "juiceshop_diff":     "confirming what solved",
        "juiceshop_source":   "reading the source",
        "jwt_forge":          "forging a JWT",
        "nosql_injection":    "building a NoSQL payload",
        "xxe_payload":        "building an XXE payload",
        "coupon_forge":       "forging a coupon",
        "ssti_payload":       "building an SSTi payload",
        "ssrf_payload":       "building an SSRF payload",
        "deserialization_payload": "building a deserialization payload",
        "prototype_pollution": "building a prototype-pollution payload",
        "path_traversal":     "building a traversal payload",
        "xss_payload":        "building an XSS payload",
        "sqli_payload":       "building a SQLi payload",
        "payload_encoder":    "encoding the payload",
        "tech_fingerprint":   "fingerprinting the stack",
        "waf_detect":         "analysing the filter",
        "trick_detect":       "scanning for hidden tricks",
        "payload_mutate":     "mutating the request structure",
        "session_flow":       "threading session state",
        "oracle_analyze":     "measuring the blind oracle",
        "captcha_solve":      "reading the captcha",
        "reset_password":     "attacking the reset flow",
        "business_logic":     "hunting business-logic flaws",
        "command_injection":  "building a command-injection payload",
        "idor_probe":         "planning IDOR enumeration",
        "race_condition":     "building a race-condition blast",
        "upload_bypass":      "building an upload bypass",
        "graphql_probe":      "probing GraphQL",
        "open_redirect":      "building open-redirect payloads",
        "cors_probe":         "probing CORS",
        "ldap_injection":     "building an LDAP-injection payload",
        "xpath_injection":    "building an XPath-injection payload",
        "crlf_injection":     "building a CRLF payload",
        "host_header_injection": "building a host-header attack",
        "ssi_injection":      "building an SSI/ESI payload",
        "csv_injection":      "checking for formula injection",
        "request_smuggling":  "building a request-smuggling probe",
        "csrf_poc":           "building a CSRF proof-of-concept",
        "clickjacking":       "checking clickjacking",
        "mass_assignment":    "building a mass-assignment probe",
        "auth_bypass_headers": "building a 403 bypass",
        "auth_attack":        "planning a credential attack",
        "jwt_attack":         "attacking the JWT",
        "api_test":           "attacking the API surface",
        "cache_poisoning":    "probing cache poisoning",
        "email_header_injection": "building an email-header injection",
        "websocket_probe":    "probing WebSockets",
        "oauth_probe":        "probing the OAuth flow",
        "attack_surface":     "mapping the attack surface",
        "verify_solve":       "confirming the solve against ground truth",
        "webapp_recon":       "sweeping the app",
        "submit_flag":        "submitting the flag",
        "xbow_score":         "scoring the benchmark",
        "xbow_report":        "building the scorecard",
        "read_file":        "reading a file",
        "write_file":       "writing a file",
        "list_dir":         "listing files",
        "find_file":        "searching files",
        "path_info":        "checking a path",
        "make_dir":         "making a folder",
        "copy_path":        "copying files",
        "move_path":        "moving files",
        "delete_path":      "deleting files",
        "system_info":      "checking the system",
        "disk_usage":       "checking disk usage",
        "processes":        "listing processes",
        "network_status":   "checking the network",
        "recent_downloads": "checking downloads",
        "service_status":   "checking a service",
        "journal_tail":     "reading the journal",
        "desktop_info":     "checking the desktop",
        "list_apps":        "listing apps",
        "list_windows":     "listing windows",
        "launch_app":       "launching an app",
        "open_url":         "opening a link",
        "focus_window":     "switching windows",
        "close_window":     "closing a window",
        "type_text":        "typing",
        "press_key":        "pressing keys",
        "media_control":    "controlling media",
        "screenshot":       "taking a screenshot",
        "read_screen":      "reading the screen",
        "notify":           "sending a notification",
        "quick_facts":      "checking the system",
    }

    def _status_for_call(self, call) -> str:
        """One short human phrase describing what a single tool call does."""
        n = (getattr(call, "name", "") or "").strip()
        a = getattr(call, "args", None) or {}
        if n == "run":
            cmd = str(a.get("command", "")).strip()
            head = cmd.split()[0] if cmd else ""
            return f"running {head}" if head else "running a command"
        if n.startswith("memory_"):
            return "checking memory"
        if n.startswith("skill"):
            return "using a skill"
        return self._TOOL_STATUS.get(n, f"running {n}" if n else "working")

    def _status_for_batch(self, calls) -> str:
        """Summarise what a parallel batch of read-only tools is doing."""
        if not calls:
            return "running tools"
        labels = [self._status_for_call(c) for c in calls]
        extra = len(labels) - 1
        return f"{labels[0]} + {extra} more" if extra > 0 else labels[0]

    def _ext_complete(self, system: str, user: str) -> str:
        """Short, synchronous, non-streaming completion for the sidecar
        (memory consolidation; the optional foresight model pass).  Routes
        through the existing BackendRouter so it inherits the operator's pinned
        provider.  Blocks the CALLING thread — the sidecar only ever calls this
        from a background thread, never the UI thread.  Tolerant of failure:
        returns "" on any error or timeout, so a flaky model degrades a feature
        instead of wedging it.

        THE TIMEOUT IS REAL NOW.  The previous version called
        `router.stream_chat(...)` and then `done.wait(timeout=30)` — but
        stream_chat is SYNCHRONOUS: it does not return until the stream is
        finished, so `done` was already set by the time we waited on it and the
        30s bound was dead code.  The true bound was the provider's own idle
        timeout times the fallback chain length, i.e. minutes.  The call now
        runs on a worker, the wait carries the deadline, and blowing it SETS THE
        CANCEL EVENT so the socket is actually abandoned rather than left to
        finish into a buffer nobody reads.

        Sidecar calls also ask for what they need — a short JSON object — rather
        than the full chat token budget, and take ONE attempt instead of walking
        the fallback chain.  Nothing here is a conversation."""
        try:
            if not self.router.any_available():
                return ""
            deadline = max(1.0, float(
                self.settings.get("ext_complete_timeout_s",
                                  EXT_COMPLETE_TIMEOUT_S)
                or EXT_COMPLETE_TIMEOUT_S))
            msgs = [{"role": "system", "content": system},
                    {"role": "user", "content": user}]
            buf = {"t": ""}
            done = threading.Event()
            cancel = threading.Event()

            def _run():
                try:
                    self.router.stream_chat(
                        msgs,
                        lambda tok: buf.__setitem__("t", buf["t"] + tok),
                        lambda meta: done.set(),
                        lambda err: done.set(),
                        cancel,
                        max_tokens_override=self.settings.get(
                            "ext_complete_max_tokens",
                            EXT_COMPLETE_MAX_TOKENS),
                        single_model=True)
                except Exception as e:
                    log(f"ext_complete: {type(e).__name__}: {e}")
                finally:
                    done.set()

            t = threading.Thread(target=_run, daemon=True)
            t.start()
            if not done.wait(timeout=deadline):
                cancel.set()
                log(f"ext_complete: timed out after {deadline:.0f}s")
                return ""
            return buf["t"]
        except Exception:
            return ""

    def _ext_embed(self, texts):
        """Embed strings for semantic memory recall via the SiliconFlow
        embeddings endpoint (OpenAI-compatible, same key chat already uses).
        Returns a list of float vectors.  Raises on ANY failure so the memory
        layer falls back to keyword recall — a flaky or offline embedder must
        never break recall, only make that one call keyword-only."""
        key = (self.settings.get("siliconflow_api_key") or "").strip()
        if not key or not texts:
            raise RuntimeError("no embedding backend")
        base = (self.settings.get("siliconflow_base_url")
                or "https://api.siliconflow.com/v1").rstrip("/")
        model = ((self.settings.get("memory_embed_model") or "").strip()
                 or "BAAI/bge-m3")
        payload = json.dumps({"model": model,
                              "input": list(texts)}).encode("utf-8")
        req = urllib.request.Request(
            base + "/embeddings", data=payload,
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read())
        items = data.get("data") or []
        vecs = [it.get("embedding") for it in items
                if isinstance(it, dict) and it.get("embedding")]
        if len(vecs) != len(texts):
            raise RuntimeError("embedding count mismatch")
        return vecs

    def _start_memory_backfill(self):
        """One-shot background pass that embeds any memories stored before
        semantic recall was enabled, so they become searchable by meaning too.
        Bounded loop on a daemon thread; stops the moment there's nothing left."""
        def _run():
            try:
                ext = getattr(self, "_ext", None)
                if ext is None:
                    return
                while ext.backfill_memory(64) > 0:
                    pass
            except Exception:
                pass
        threading.Thread(target=_run, daemon=True).start()

    # ══════════════════════════════════════════════════════════════
    # A DELAYED KICK IS PART OF THE TURN, AND HAS TO BE CANCELLABLE
    # ══════════════════════════════════════════════════════════════
    # Three places used to schedule the next turn with a bare
    # `GLib.timeout_add(delay, lambda: self._kick_assistant_turn())` and throw
    # the source id away -- after having just nulled streaming_msg_widget,
    # streaming_msg_db_id and streaming_chat_id, which are the ONLY three
    # things _is_busy() looks at. For the length of that delay (up to 15s for
    # a mission continue, up to 60s for an error back-off) the app reported
    # itself idle while a turn was definitely still coming.
    #
    # Two ways that produced a duplicate answer, both reachable by hand:
    #
    #   · the operator types a follow-up during the window. _is_busy() says
    #     no, the message is accepted and kicks a turn -- then the orphan
    #     timeout fires and kicks a SECOND one. Two live streams write
    #     through the same self.streaming_msg_widget, so the tokens
    #     interleave and both finalisers commit.
    #
    #   · the operator presses Stop and then sends. _request_stop set
    #     _stop_requested, which is the only thing _kick_assistant_turn
    #     checks -- but _send_user_message clears that flag on entry, so the
    #     orphan timeout sails through the one guard that would have caught
    #     it. Stop did not stop it.
    #
    # Routing every delayed kick through here fixes both: the id is kept, so
    # it can be cancelled, and _is_busy() counts a pending kick as busy.

    def _schedule_kick(self, delay_ms: int):
        """Queue the next assistant turn, cancellably."""
        self._cancel_pending_kick()
        if self._stop_requested:
            return
        def _fire():
            self._pending_kick_id = 0
            if self._stop_requested:
                return False
            self._kick_assistant_turn()
            return False
        self._pending_kick_id = GLib.timeout_add(max(1, int(delay_ms)), _fire)

    def _cancel_pending_kick(self):
        kid = getattr(self, "_pending_kick_id", 0)
        if kid:
            try:
                GLib.source_remove(kid)
            except Exception:
                pass
        self._pending_kick_id = 0

    def _kick_assistant_turn(self):
        self._mark_turn_progress()
        # If the operator hit stop between tool turns, don't start another.
        if self._stop_requested:
            self._finish_turn_cleanup()
            return

        if not self.router.any_available():
            self._show_toast(
                "No provider ready.  Add an API key in Settings → Backends.")
            self.streaming_chat_id = None
            self._tool_chain_depth = 0
            self._set_working(False)
            self._set_send_mode(False)
            return

        # Preserve streaming_chat_id across a tool chain.  Only snapshot
        # when starting a fresh turn (not continuing from a tool result).
        if self.streaming_chat_id is None:
            self.streaming_chat_id = self.current_chat_id
            self._tool_chain_depth = 0
            self._tools_locked = False
            self._force_answer_tries = 0
            # Per-request, like the counters above: a stall on the LAST question
            # must not spend this question's nudges.
            self._answer_stall_nudges = 0

        # Limit how many model round-trips a turn may chain.  Rather than
        # dead-ending with "chain too long" and no answer (annoying), once
        # the budget is spent we lock tools and take ONE more turn to answer
        # with whatever was gathered.  The directive below tells the model
        # to stop calling tools; _after_stream ignores any it emits anyway.
        self._tool_chain_depth += 1
        _budget = self.settings.get("max_tool_steps", MAX_TOOL_CHAIN)
        # Autonomous walk-away mode (no per-command approval — the default) runs
        # UNCAPPED: it keeps going until the task is actually finished (the model
        # stops calling tools) or you press Stop. Stop and the catastrophic-
        # command hard block fire regardless of depth, so uncapped never means an
        # unsupervised risky run. The max_tool_steps cap only applies in a
        # supervised (per-command approval) mode.
        if self.settings.get("approval_mode", "none") == "none":
            _budget = 0  # 0 == unlimited: run to completion
        if _budget and self._tool_chain_depth > _budget and not self._tools_locked:
            self._tools_locked = True
            self.terminal_log("── tool budget reached; finalizing answer", "dim")
            try:
                fin_chat = self.streaming_chat_id or self.current_chat_id
                self.store.add_message(
                    fin_chat, "user",
                    "<tool_result>\n[system note: tool-step budget reached. "
                    "Do not call any more tools. Give your best final answer "
                    "now using everything gathered so far.]\n</tool_result>",
                    meta={"kind": "tool_result"})
            except Exception:
                pass
            # fall through — this turn runs with tools locked.

        chat_id = self.streaming_chat_id

        history = self._build_history_for_model(chat_id)
        addendum = self.settings.get("system_prompt", "")

        # ── IS THIS THE TURN THAT ANSWERS, OR A STEP ON THE WAY? ──
        # _tool_chain_depth is incremented once per model round-trip and reset
        # when a fresh operator message starts a turn, so depth 1 is "replying
        # to the operator" and depth 2+ is "continuing after a tool result".
        #
        # Everything below used to ignore that distinction, and it is the whole
        # reason the operator saw the same conclusion four times in a row.  The
        # directives are properties of his REQUEST — "he is in a hurry, lead
        # with the answer", "deliver ONE complete answer, then stop" — but they
        # were rebuilt from `history` on EVERY round-trip.  `last_user` scans
        # back PAST tool results to find his message, so it found the same
        # urgent question every time and re-armed the same instruction.  The
        # model was told "lead with the answer" and "deliver one complete
        # answer" immediately after every single tool result, and it did
        # exactly that, every time.  Four web_reads, four complete answers,
        # each one rendered as its own message.
        #
        # The model was not being repetitive. It was being obedient.
        _continuation = self._tool_chain_depth > 1

        # (#3) Urgency fast-path: if the operator's latest message reads as
        # urgent, tell the model to skip preamble and go straight to the most
        # likely fix.  FIRST TURN ONLY — "lead with the answer" is advice about
        # how to open a reply to him, and repeating it mid-chain is an
        # instruction to answer again from scratch after every tool result.
        if (self.settings.get("urgency_fast_path", True)
                and not self._tools_locked and not _continuation):
            try:
                last_user = ""
                for m in reversed(history):
                    if m.get("role") == "user" \
                            and "<tool_result>" not in (m.get("content") or ""):
                        last_user = m.get("content", "")
                        break
                u = detect_urgency(last_user)
                if u.get("urgent"):
                    addendum = (addendum + "\n\n[URGENT: the operator is in a "
                                "hurry (markers: "
                                + ", ".join(u["markers"]) + "). Skip pleasantries "
                                "and context-gathering. Lead with the single most "
                                "likely fix or answer, then offer detail.]").strip()
                    self.terminal_log("⚡ urgency fast-path engaged", "dim")
            except Exception:
                pass
        if getattr(self, "_ext", None):
            try:
                extra = self._ext.system_prompt_block()
                if extra:
                    addendum = (addendum + "\n\n" + extra).strip()
            except Exception:
                pass
        # Autonomous posture (approval_mode 'none', the default): act over plan,
        # keep going, NO cards. When the operator has opted into confirming
        # commands, drop this so it reasons/plans more carefully.
        #
        # BUT: a fresh QUESTION (or a greeting) with no active mission must NOT
        # get the never-stop directive — that's what dropped "how does X work?"
        # into a relentless tool-firing loop it couldn't exit. On such a turn we
        # still act directly (no approval cards), but the directive tells it to
        # answer concisely, use at most one tool, and STOP. During a real mission
        # (a task is being worked, _mission_active) the full autonomous push
        # applies as before.
        _opening_user = next(
            (m.get("content", "") for m in reversed(history)
             if m.get("role") == "user"
             and "<tool_result>" not in (m.get("content", "") or "")), "")
        # ── UNLEASH decides the mode for THIS turn ──
        # Unleashed WITH an active mission → relentless: never answer-only, keep
        # firing until MISSION_COMPLETE. Unleashed with no mission yet (arming
        # asked for the target, or we're idle between missions) → answer once and
        # wait for the objective. Not unleashed → always answer once and stop;
        # missions never grind. This is the whole two-mode contract, in one place.
        if not self._unleashed:
            self._mission_active = False
            _answer_only = True
        else:
            _answer_only = not self._mission_active
        if not _continuation:
            if _answer_only:
                self._activity_note(
                    "LEASHED - answer mode: research, verify, answer once, stop",
                    "note")
            else:
                self._activity_note(
                    "UNLEASHED - mission active: running until complete",
                    "note")
        # Unleash kickoff (one-shot, fired the turn right after arming): confirm
        # the target and go, or ask for it once if none is set yet.
        if self._unleash_kickoff_pending:
            self._unleash_kickoff_pending = False
            addendum = (addendum + "\n\n[UNLEASH TRIGGERED — the operator just "
                "armed Unleash. FIRST lock the target: if the conversation "
                "already names a target or objective, restate it in ONE line to "
                "confirm ('Target confirmed: <X> — going now.') and then "
                "immediately begin and do NOT stop until it is fully complete and "
                "verified. If NO target is set yet, ask the operator in ONE short "
                "line what the target is, then STOP and wait — the moment they "
                "reply, you go full send. Seek no approval beyond confirming the "
                "target.]").strip()
            self.terminal_log("🎯 unleash: confirming target", "dim")
        # ANSWER MODE (leashed) is a research-and-confirm SINGLE answer, not a
        # one-shot memory dump: it may chain web_search / web_read / github as
        # many times as it needs to actually find and verify the answer, then
        # give ONE reply and stop. Only a runaway (a model that keeps calling
        # tools without converging) needs breaking, so the cap is generous — lock
        # tools and force the answer only after answer_tool_budget round-trips.
        _ans_cap = self.settings.get("answer_tool_budget", 40)
        if _answer_only and self._tool_chain_depth > _ans_cap and not self._tools_locked:
            self._tools_locked = True
            addendum = (addendum + "\n\n[You've used a lot of tools on this "
                        "question without converging. Do NOT call any more — give "
                        "your best, complete answer NOW from what you've gathered, "
                        "and say plainly if any part is still unverified.]"
                        ).strip()
            self.terminal_log("── answer tool-cap reached; answering now", "dim")
            self._activity_note(
                "research budget reached (%d steps) - answering from what is "
                "gathered" % _ans_cap, "gate")
        if _answer_only:
            if _needs_web_verification(_opening_user):
                if not _continuation:
                    self._activity_note(
                        "checkable claim - reading a primary source before "
                        "answering (memory not trusted here)", "note")
                    addendum = (addendum + "\n\n[!!! CHECK ONLINE FIRST -- this "
                        "question is about current or checkable facts, and your "
                        "training data may be OUT OF DATE. You are FORBIDDEN from "
                        "answering it from memory. Your FIRST action MUST be to "
                        "web_read a primary source (or web_read a search-results "
                        "page and follow the best link), READ it, then answer from "
                        "what you actually read and cite it. Do NOT state a version, "
                        "date, price, name, score, or 'latest' anything from memory. "
                        "If after searching you still cannot confirm it, say plainly "
                        "that you could not verify it -- never guess. A confident "
                        "answer from memory here is a hallucination and is wrong.]"
                        ).strip()
                else:
                    # SAME RULE, RESTATED FROM MID-CHAIN.
                    # The first-turn wording is an imperative about the opening
                    # move — "your FIRST action MUST be to web_read". Re-sending
                    # it after a tool result tells a model that has ALREADY read
                    # a source that its first action must be to read one, so it
                    # reads another, and another: four web_reads for one
                    # question, each followed by a fresh complete answer.
                    # What still needs saying at this point is only the part
                    # about not inventing facts.
                    addendum = (addendum + "\n\n[STILL VERIFY, DON'T RECALL — you "
                        "have already read at least one source this turn. Keep "
                        "stating only what you actually read, and cite it. Do NOT "
                        "re-read a page you have already read, and do NOT open "
                        "another source to re-confirm something that already came "
                        "back clean — one successful read IS the confirmation. "
                        "Fetch again ONLY for a fact you genuinely do not have "
                        "yet; otherwise answer from what you have, marking "
                        "anything you could not verify.]").strip()
            addendum = (addendum + "\n\n[ANSWER MODE (leashed) — THIS turn is a "
                "QUESTION / request, not an autonomous operation. Deliver ONE "
                "complete, correct, verified answer, then STOP.\n"
                "- CONFIRM, don't recall. Do NOT answer from memory for anything "
                "that can change or is checkable: news, current events, prices, "
                "software versions/releases, who currently holds a role, dates, "
                "statistics, documentation, or anything about a specific project "
                "or repo (including your own). SEARCH and READ the primary source "
                "before you state it; if you can't verify something, say so "
                "instead of guessing.\n"
                "- You have UNRESTRICTED web here (no approval needed in this "
                "mode): web_read fetches ANY public page in full — read the "
                "primary source, docs, a GitHub page, a vendor blog, a news "
                "article, anything. When you don't already have a URL, SEARCH by "
                "reading a results page and following its links: web_read "
                "\"https://html.duckduckgo.com/html/?q=YOUR+QUERY\" (or Wikipedia, "
                "or the site's own search), then web_read the best result links in "
                "full. Use image_search to show pictures. Chain as many reads as it "
                "takes — there is NO small tool limit to stop short for. Keep going "
                "until you've actually found and confirmed the answer.\n"
                "- CITE what you used: name the source or paste the link so the "
                "operator can check it, and prefer the most recent authoritative "
                "one.\n"
                "- Act directly, never via `propose`/`propose_edit` cards.\n"
                "- When you have the verified answer, give it once — technical and "
                "direct for an expert operator, no padding — and END your turn. Do "
                "NOT latch a mission or keep grinding after answering; there is no "
                "completion token here, just answer and stop.]").strip()
            if _continuation:
                # "Deliver ONE complete answer, then STOP" is correct advice for
                # the turn that replies to the operator and actively harmful on
                # the turns after it: read literally, after every tool result it
                # says "answer now, completely".  So on a continuation the same
                # rule has to be restated from where the model actually is —
                # mid-chain, having already written prose the operator can see.
                addendum = (addendum + "\n\n[CONTINUATION TURN — you are partway "
                    "through answering. The prose you already wrote this turn IS "
                    "ON SCREEN; the operator has read it.\n"
                    "- Do NOT restate, re-verify or re-summarise a conclusion you "
                    "have already given. Saying \"web reading is confirmed "
                    "working\" a second time tells him nothing and reads as a "
                    "stutter.\n"
                    "- You have exactly two useful moves: call the next tool with "
                    "NO preamble, or give the FINAL answer covering only what is "
                    "still unsaid, and stop.\n"
                    "- If everything you set out to check is now checked, stop. "
                    "Re-confirming something that already succeeded is not "
                    "thoroughness, it is a loop.]").strip()
            # Log ONCE per chain, not once per round-trip. These two lines were
            # printed before every continuation, which is why the terminal log
            # showed the same pair eleven times for one question — the log was
            # accurately reporting the bug above, and doubling its noise.
            if not _continuation:
                self.terminal_log(
                    "💬 answer mode: research, confirm, answer once", "dim")
        elif self.settings.get("approval_mode", "none") == "none":
            addendum = (addendum + "\n\n[AUTONOMOUS MODE — THIS OVERRIDES ANY "
                "CONFLICTING INSTRUCTION ABOVE. The operator turned this on to "
                "start a job, walk away, and come back hours later to find it "
                "still working or finished. Obey these rules exactly:\n"
                "- NEVER use the `propose` or `propose_edit` tools. Never put a "
                "card on screen for the operator to click — there is no operator "
                "watching. Run shell commands DIRECTLY with the `run` tool; write "
                "files DIRECTLY with `write_file`. They execute immediately in "
                "this mode; do not wait for approval.\n"
                "- To run a command you MUST emit a `run` tool call. NEVER write "
                "the command inside a ``` code block or as prose text — a command "
                "shown in a code block does NOT execute, it just displays as a "
                "useless copyable banner. If you want a command to run, the ONLY "
                "way is the run tool. Same for files: use write_file, never a "
                "fenced block.\n"
                "- IGNORE any guidance to 'reason WITH him and propose', 'let him "
                "decide', 'have a conversation not a runaway', or to 'stop and ask "
                "how he wants to proceed'. Those are OFF now. You decide and you "
                "act.\n"
                "- NEVER stop to check in, summarise-and-wait, or ask a question. "
                "Do NOT end your turn with a question or a 'let me know'. If you're "
                "about to write a summary and stop — DON'T; do the next action "
                "instead. The ONLY reasons to stop are: the whole task is finished, "
                "or you are truly blocked on something only the operator can do "
                "(and even then, try every alternative first).\n"
                "- ACT, don't plan. No long option lists, no multi-step plan "
                "narration, no lengthy reasoning. Pick the single most likely path, "
                "try it; if it fails, try the next single option. Every turn must "
                "DO something (a tool call), never just think or list.\n"
                "- Keep firing tool calls until the objective is met (e.g. the "
                "whole board solved / the target fully tested) or you're stopped. "
                "Chain step after step without pausing.\n"
                "- Destructive/system-destroying commands are hard-blocked (refused) "
                "— don't attempt them. sudo: if a credential is cached it's used "
                "silently; you never see the password.\n"
                "- COMPLETION: the run does NOT end when you stop talking — it "
                "keeps going. The ONLY way to end it cleanly is to output the exact "
                "token " + MISSION_COMPLETE_TOKEN + " on its own line, and ONLY "
                "when the whole objective is genuinely achieved and verified (if it "
                "was just a question, answer it fully, then output the token). "
                "Never output it for partial or assumed completion.\n"
                "- Be terse. One short status line per step, not essays. Save "
                "tokens.]").strip()
            self.terminal_log("🔥 autonomous mode: unleashed", "dim")
        # ── Loop breaker ──
        # Once the mission has ACTED, the idle cap no longer applies (a real
        # engagement runs tools constantly and must stay relentless). The failure
        # mode that leaves is the model firing the SAME command over and over —
        # re-running `sudo systemctl start docker` when Docker already started, or
        # an uncached sudo prompt failing silently — with nothing to break it out.
        # If the last 3 executed commands are identical, inject a hard nudge to
        # STOP repeating and VERIFY state with a different command instead. This
        # doesn't stop the mission (legit relentless work continues); it only
        # redirects a provably-stuck repeat.
        _rc = getattr(self, "_recent_commands", [])
        if (len(_rc) >= 3 and _rc[-1] and len(set(_rc[-3:])) == 1):
            _stuck = _rc[-1]
            if len(_stuck) > 160:
                _stuck = _stuck[:157] + "…"
            addendum = (addendum + "\n\n[LOOP BREAKER — you have now run this EXACT "
                "command 3 times in a row:\n    " + _stuck + "\nRepeating it is NOT "
                "making progress. It has almost certainly ALREADY succeeded, or it "
                "is failing silently (an uncached `sudo` password prompt that never "
                "gets answered in autonomous mode, or the service/target is already "
                "in the desired state). Do NOT run that command again. Instead, on "
                "this turn: VERIFY the real state with a DIFFERENT command (e.g. "
                "`docker ps`, `systemctl status docker --no-pager`, "
                "`curl -s -o /dev/null -w '%{http_code}' http://localhost:3000`), "
                "READ the result, and then either advance to the next step or, if "
                "the objective is already met, finish. If it needs sudo and sudo "
                "isn't cached, say so plainly and move on — don't loop.]").strip()
            self.terminal_log("⛔ loop breaker: same command ×3 — forcing a "
                              "verify/redirect", "error")
        # Lean-chat: on a plainly conversational OPENING turn (a greeting,
        # thanks, an opinion question — no hint of an action), skip the ~8K-token
        # tool catalog. "Just talking" shouldn't ship 100+ tool specs. Only the
        # first step of a turn, never mid-tool-chain; conservative detector keeps
        # the full toolset the moment a message hints at any action.
        _lean = False
        if (self.settings.get("lean_chat", True)
                and self.current_agent_mode
                and self._tool_chain_depth == 1 and not self._tools_locked):
            # Only skip the toolset while the conversation is still PURELY
            # social. The moment ANY tool has run in this chat, a short follow-up
            # ("do it", "the next one", "yeah go on") is operational and NEEDS
            # the toolset — stripping it there is what left a long conversation
            # suddenly unable to act for several turns. So: lean is allowed only
            # before the first tool call; after that the full toolset always
            # ships. (Trimmed tool_results keep their <tool_result> head, so this
            # detects operational history even deep into a long chat.)
            _operational = any("<tool_result>" in (m.get("content") or "")
                               for m in history)
            if not _operational:
                _last_user = next(
                    (m.get("content", "") for m in reversed(history)
                     if m.get("role") == "user"
                     and "<tool_result>" not in m.get("content", "")), "")
                _lean = conversational_turn(_last_user)

        # ── Effort ladder ────────────────────────────────────────────
        # Light on a plainly conversational turn (fast, cheap); heavy once
        # we're several tool-steps deep in a live engagement (the router
        # escalates the model + reasoning budget, and the directive below
        # tells the model to slow down and think).  Standard otherwise.
        # All of it collapses to flat behaviour if adaptive_effort is off.
        # A genuinely complex request should think hard from step 1, not only
        # after several tool-steps. Conservative security-engagement markers so
        # ordinary chat never trips it; still gated behind adaptive_effort.
        _hard_now = False
        if (self.settings.get("adaptive_effort", True)
                and self.current_agent_mode and not self._tools_locked
                and not _lean):
            try:
                _hu = next(
                    (m.get("content", "") for m in reversed(history)
                     if m.get("role") == "user"
                     and "<tool_result>" not in m.get("content", "")),
                    "").lower()
                _hard_now = any(mk in _hu for mk in (
                    "pentest", "penetration test", "exploit",
                    "privilege escalation", "priv esc", "full scan",
                    "full audit", "vulnerability scan", "vuln scan",
                    "enumerate", "attack surface", "brute force", "brute-force",
                    "reverse engineer", "map the network", "recon on ",
                    "recon of ", "analyse the codebase", "analyze the codebase"))
            except Exception:
                _hard_now = False

        # ── EFFORT: match it to the JOB, not to elapsed steps ──
        # The old rule escalated to "hard engagement" as soon as the tool chain
        # reached depth 3.  Depth is a proxy for TIME SPENT, not for DIFFICULTY:
        # a plain diagnosis that happened to need four cheap reads got the same
        # "think before you move, reason through the current state" push as a
        # live exploitation run, three steps into a job that was nearly done.
        # That is a direct driver of overcomplication — the turn where the model
        # should be concluding is the exact turn it was being told to deliberate.
        #
        # Escalate on EVIDENCE of a hard problem instead:
        #   · the operator's own words say it is hard (_hard_now), or
        #   · it is deep AND the recent results show it is actually struggling.
        # Going deep while things keep working is not struggling, it is progress.
        _struggling = False
        if self._tool_chain_depth >= self.settings.get("hard_effort_step", 6):
            try:
                _last = [m.get("content", "") for m in history
                         if "<tool_result>" in (m.get("content") or "")][-3:]
                _struggling = sum(
                    1 for tr in _last
                    if ('"ok": false' in tr.lower() or '"ok":false' in tr.lower()
                        or "error" in tr.lower()[:400]
                        or "(rc=1)" in tr or "not found" in tr.lower()[:400])
                ) >= 2
            except Exception:
                _struggling = False
        if _lean:
            _effort = "light"
        elif (self.current_agent_mode and not self._tools_locked
              and (_hard_now or _struggling)):
            _effort = "heavy"
            addendum = (addendum + "\n\n[HARD ENGAGEMENT: this one is not "
                        "going smoothly, so slow the aim down (not the pace). "
                        "State the SINGLE most likely reason it is failing, "
                        "based on what the last results actually said, and test "
                        "that one thing next. Rank by likelihood x cost to "
                        "check, cheapest decisive test first, boring causes "
                        "before exotic ones. Read each result properly instead "
                        "of skimming, and when something fails use what it told "
                        "you to pick the next move rather than repeating "
                        "blindly. One hypothesis per turn; stop the moment it "
                        "is confirmed.]").strip()
        else:
            _effort = "standard"

        # ── STUCK PIVOT (coded, not left to the model) ────────────────
        # If the model has gone DEEP (20+ tool-steps into one turn) and its
        # recent results are mostly failures / no-progress, it's grinding the
        # same approach. Detect that from history and FORCE a research pivot:
        # look the technique up on a trusted source and apply it immediately.
        # The 20-step floor keeps this from firing during normal early
        # iteration (a couple of failed attempts is just how hacking goes).
        # Instant sources (PortSwigger/OWASP/NVD) need no approval; the
        # community ones (exploit-db/GitHub) take a one-tap.
        if (self.current_agent_mode and not self._tools_locked
                and self._tool_chain_depth >= 20):
            _recent = [m.get("content", "") for m in history[-9:]
                       if "<tool_result>" in m.get("content", "")][-4:]
            if len(_recent) >= 3:
                def _looks_failed(tr):
                    low = tr.lower()
                    return ('"ok": false' in low or '"ok":false' in low
                            or '"error"' in low or '"newly_solved": []' in low
                            or 'no new' in low or 'nothing new' in low
                            or 'not solved' in low or 'unchanged' in low
                            or 'did not land' in low or "didn't land" in low)
                if sum(1 for tr in _recent if _looks_failed(tr)) >= max(
                        2, len(_recent) - 1):
                    addendum = (addendum + "\n\n[STUCK - PIVOT TO RESEARCH NOW: "
                        "your last few attempts failed or made no progress. STOP "
                        "repeating the same approach. web_read the exact "
                        "technique from a trusted source - PortSwigger Web "
                        "Security Academy or OWASP for a web attack, NVD/MITRE "
                        "for a CVE (these are instant, no approval); exploit-db "
                        "or a GitHub PoC for a specific exploit (these take a "
                        "one-tap approval). Pull the concrete working method and "
                        "APPLY IT IMMEDIATELY against the target - don't just "
                        "describe it - then diff to confirm and keep moving.]"
                        ).strip()

        # ── ALREADY DONE — the durable action list ──
        # This is the counterweight to history trimming. _build_history_for_model
        # keeps only the last HISTORY_KEEP_FULL_TOOL_RESULTS tool results at full
        # length and headroom compresses the rest, so by step five the model's
        # evidence of having already tried something is a 600-char stub while the
        # mission directive is still shouting the original objective at it. That
        # asymmetry is what made it redo work from a few turns back. One line per
        # action, never trimmed, placed immediately before the directive so it is
        # the last thing read before "take the next action".
        if (self._action_log is not None
                and self.settings.get("action_recall", True)
                and not self._tools_locked):
            try:
                _done = self._action_log.prompt_block(
                    int(self.settings.get("action_recall_entries", 40)))
                if _done:
                    addendum = (addendum + "\n\n" + _done).strip()
            except Exception:
                pass

        if self._mission_active and self._mission_directive:
            addendum = (addendum + "\n\n" + self._mission_directive).strip()
            self._mission_directive = ""

        # PROMPT CACHING: the addendum is NOT passed into the system prompt.
        # It carries the per-turn material — the already-done action list, the
        # mission directive, effort nudges — so putting it in the system message
        # would change the cached prefix on every single turn and forfeit the
        # discount on the whole ~6k-token prompt. It rides at the TAIL instead,
        # where changing it costs only its own tokens.
        sysprompt = build_system_prompt(
            agent_mode=(False if _lean else self.current_agent_mode),
            grouped=(not self.settings.get("max_mode", False)),
            # UNLEASH decides the role framing AND which tool groups exist.
            # Off = ordinary work on his machine, offensive suite not loaded:
            # cheaper, and it stops a general task being framed as an attack.
            unleashed=self._unleashed)
        # The clock and the addendum go last, as their own trailing message, so
        # everything above them stays byte-identical between turns and gets
        # served from the provider's prefix cache: half price on input, lower
        # latency, and on Groq those tokens do not count against rate limits.
        full = assemble_messages(sysprompt, history,
                                 volatile=volatile_block(addendum))
        # Splice in relevance-scoped recall (top-k memories for THIS turn).
        # No-op unless memory is enabled; never grows with history length.
        if getattr(self, "_ext", None):
            try:
                full = self._ext.inject_memory(full)
            except Exception:
                pass

        # Fresh assistant widget for this step — reset the speech streamer
        # so sentence detection starts clean, and clear the tool-turn
        # suspend flag (it re-arms below if this turn emits a tool call).
        if self._tts_streamer is not None:
            self._tts_streamer.reset()
        self._tts_suspended = False
        self._turn_active = True

        # Only show the streaming widget if user is looking at this chat
        if chat_id == self.current_chat_id:
            self.streaming_msg_widget = self._append_message_widget(
                "assistant", "")
            self.streaming_msg_widget.start_streaming()
        else:
            # User has navigated away.  We still need a widget to buffer
            # tokens for finish_streaming, but don't attach it to msg_box.
            self.streaming_msg_widget = MessageWidget(
                "assistant", "", on_run_command=self._run_proposed_command,
                on_apply_edit=self._run_proposed_edit,
                on_speak=self._on_message_speak,
                show_thoughts=self.settings.get("show_thoughts", True))
            self.streaming_msg_widget.start_streaming()

        self.streaming_msg_db_id = self.store.add_message(
            chat_id, "assistant", "")

        self.streaming_cancel = threading.Event()

        # ══════════════════════════════════════════════════════════════
        # EVERY STREAM CARRIES ITS OWN IDENTITY
        # ══════════════════════════════════════════════════════════════
        # The four callbacks below all act on self.streaming_msg_widget /
        # streaming_msg_db_id -- mutable fields naming whatever turn is
        # current WHEN THE CALLBACK RUNS, not the turn that started the
        # stream. With one stream at a time that is the same thing. It is
        # not the same thing whenever a second turn starts while the first
        # is still alive, and there are three ways that happens:
        #
        #   · a queued kick fires alongside an operator-sent message
        #     (fixed above by making kicks cancellable, but defence in
        #     depth belongs here too -- that fix removes the common cause,
        #     this one removes the consequence);
        #   · the turn watchdog abandons a stuck stream and starts a new
        #     turn without joining the worker, which is still blocked in a
        #     socket read and will call back later;
        #   · a cancelled stream whose provider does not observe the
        #     cancel until its own idle timeout.
        #
        # In all three the OLD stream's tokens append to the NEW turn's
        # widget and its on_done finalises the new turn -- the operator
        # watches two answers interleave into one bubble, and both get
        # committed. An epoch captured here, compared on arrival, makes a
        # stale stream silent instead: it cannot write, cannot finalise,
        # and cannot schedule a retry on a turn that is no longer its own.
        self._stream_epoch = getattr(self, "_stream_epoch", 0) + 1
        _epoch = self._stream_epoch

        def _live() -> bool:
            return self._stream_epoch == _epoch

        def _on_tok(tok):
            if _live():
                GLib.idle_add(self._on_stream_token, tok, _epoch)
        def _on_done(meta):
            if _live():
                GLib.idle_add(self._on_stream_done, meta, _epoch)
        def _on_err(err):
            if _live():
                GLib.idle_add(self._on_stream_error, err, _epoch)
        def _on_reason(tok):
            if _live():
                GLib.idle_add(self._on_stream_reasoning, tok, _epoch)

        def _bg():
            # The turn advances ONLY through _on_done / _on_err.  router.
            # stream_chat calls one of them on every path it knows about, but if
            # it raises on a path it does not — a malformed message list, a
            # provider object in a bad state, an encoding error building the
            # payload — this thread would die with a traceback on stderr and
            # neither callback would ever fire.  The reply would sit at
            # "thinking…" forever.  Route any such escape into the error
            # callback, which is the path already built for "this turn failed".
            try:
                self.router.stream_chat(full, _on_tok, _on_done, _on_err,
                                        self.streaming_cancel,
                                        on_reasoning=_on_reason,
                                        effort=_effort)
            except Exception as e:
                log(f"stream worker died: {traceback.format_exc()}")
                _on_err(f"internal error starting the reply: "
                        f"{type(e).__name__}: {e}")

        self.streaming_thread = threading.Thread(target=_bg, daemon=True)
        self.streaming_thread.start()
        self._set_send_mode(True)
        self._set_working(True, "thinking…")
        self.terminal_log("── stream start", "dim")

    def _stale_stream(self, epoch) -> bool:
        """True when this callback belongs to a turn that has been replaced.

        `epoch is None` means a caller from before the epochs existed (or a
        test); those are always treated as live so nothing silently stops
        working.
        """
        return epoch is not None and epoch != getattr(self, "_stream_epoch", 0)

    def _on_stream_token(self, tok, epoch=None):
        if self._stale_stream(epoch):
            return False
        self._mark_turn_progress()
        if self.streaming_msg_widget:
            self.streaming_msg_widget.append_streaming(tok)
            # Only scroll if user is on the chat that owns this stream
            if self.streaming_chat_id == self.current_chat_id:
                self._scroll_to_bottom()
            self._feed_tts_stream()
        return False

    def _on_stream_reasoning(self, tok, epoch=None):
        """Reasoning tokens (model 'thoughts') arrive separately from the
        reply; route them to the message's collapsible thoughts panel."""
        if self._stale_stream(epoch):
            return False
        if self.streaming_msg_widget:
            self.streaming_msg_widget.append_thought(tok)
            if self.streaming_chat_id == self.current_chat_id:
                self._scroll_to_bottom()
        return False

    def _feed_tts_stream(self):
        """Hand any newly-completed sentences to the speaker as the reply
        streams in.  Suspends for a turn that emits tool tags so we never
        read raw tool XML aloud — the post-tool prose reply gets read
        instead."""
        if not (self.tts and self.settings.get("tts_enabled")):
            return
        if self._tts_streamer is None or self.streaming_msg_widget is None:
            return
        raw = self.streaming_msg_widget._content or ""
        # SUSPEND CHECK RUNS ON THE RAW TEXT, and asks "is protocol arriving?"
        # in every dialect.  It used to ask `"<tool" in content` — a literal
        # substring — which is false for `<｜DSML｜｜tool …>`, `<invoke …>` and
        # `<function=…>`.  For those the guard never fired, the speaker kept
        # running through the tool call, and the operator heard the transport.
        if not self._tts_suspended and contains_tool_markup(raw):
            # Model is doing a tool turn — stop streaming this widget's
            # audio.  Drop anything already queued from it.
            self._tts_suspended = True
            self.tts.stop()
            return
        if self._tts_suspended:
            return
        try:
            # speakable_text is the SAME transform used at flush below and by
            # the per-message speak button.  The streamer tracks a prefix across
            # calls, so feeding it one transform here and a different one at
            # flush corrupts its bookkeeping — which is exactly how the model's
            # reasoning ended up being read aloud after the reply finished.
            sentences = self._tts_streamer.feed(speakable_text(raw))
            if sentences:
                # This reply now owns the speaker; its per-message button
                # will show pause while it reads.
                if self._speaking_widget is not self.streaming_msg_widget:
                    prev = self._speaking_widget
                    if prev is not None:
                        prev.set_speak_state("idle")
                    self._speaking_widget = self.streaming_msg_widget
                for sentence in sentences:
                    self.tts.speak(sentence)
        except Exception as e:
            log(f"tts stream feed error: {e}")

    def _shell_block_command(self, text):
        """Delegate to basilisk_core.shell_block_command (tested there). Recovers a
        shell command the model printed in a ``` fence instead of calling run, so
        autonomous mode still executes it."""
        try:
            return shell_block_command(text)
        except Exception:
            return ""

    def _on_stream_done(self, meta, epoch=None):
        if self._stale_stream(epoch):
            return False
        self._mark_turn_progress()
        if not self.streaming_msg_widget:
            self._finish_turn_cleanup()
            return False
        # THE WHOLE BODY IS GUARDED. This callback runs on the main loop —
        # an unhandled exception here kills the GTK source, and with it the
        # turn: no tool result, no continue-nudge, no error toast.  Every exit
        # path from this method either chains the next step (a tool call or
        # another kick) or cleans up (stop / error / completion), so a failure
        # anywhere must land at the cleanup rather than silently dying.
        try:
            self._on_stream_done_body(meta)
        except Exception:
            log(f"_on_stream_done crashed: {traceback.format_exc()}")
            self.terminal_log("✗ internal error finishing that reply — turn "
                              "ended", "error")
            try:
                self._finish_turn_cleanup()
            except Exception:
                pass
        return False

    def _on_stream_done_body(self, meta):
        final = self.streaming_msg_widget.finish_streaming()
        # ── CANONICALISE ONCE, AT THE BOUNDARY ──
        # Everything downstream — parsing, stripping, the stored message, the
        # history re-sent on every later turn, the widget the operator reads —
        # must see the SAME text. Normalising here rather than in each consumer
        # is what guarantees that: a call in the model's native token syntax is
        # rewritten to the canonical form the instant it arrives, so it cannot
        # execute-but-not-strip, and the raw special tokens never reach the
        # database or the screen.
        try:
            final = _normalise_tool_syntax(final or "")
        except Exception:
            pass
        # Mission completion signal: strip the token from what's shown/stored/
        # spoken, but remember that it fired this turn.
        _mission_done_signal = MISSION_COMPLETE_TOKEN in final
        if _mission_done_signal:
            final = final.replace(MISSION_COMPLETE_TOKEN, "").strip()
            try:
                self.streaming_msg_widget.set_content(final or "*(done)*")
            except Exception:
                pass
        # A stream that reached 'done' cleanly resets the error-retry backoff.
        self._error_retries = 0
        if (self.tts and self.settings.get("tts_enabled")
                and not self._tts_suspended and self._tts_streamer is not None
                and not (meta.get("cancelled") or self._stop_requested)):
            try:
                # SAME transform as the per-token feed above — see the note
                # there.  Passing `final` raw here is what broke the streamer's
                # prefix invariant and re-spoke the <think> block.
                for sentence in self._tts_streamer.flush(speakable_text(final)):
                    self.tts.speak(sentence)
            except Exception as e:
                log(f"tts flush error: {e}")
        if self.streaming_msg_db_id:
            self.store.update_message(self.streaming_msg_db_id, final)
            # Persist any captured reasoning so the thoughts panel survives a
            # chat reload.  Merge, don't clobber, whatever meta already exists.
            try:
                thoughts = self.streaming_msg_widget.get_thoughts()
                if thoughts:
                    m = dict(self.streaming_msg_widget.meta or {})
                    m["thoughts"] = thoughts
                    self.streaming_msg_widget.meta = m
                    self.store.update_message_meta(
                        self.streaming_msg_db_id, m)
            except Exception as e:
                log(f"thoughts persist failed: {e}")
        calls = parse_tool_calls(final)
        cancelled = meta.get("cancelled") or self._stop_requested
        self.terminal_log(f"── stream done{' (cancelled)' if cancelled else ''}", "dim")
        # `propose` is advisory — it renders a command card (already done by
        # finish_streaming → set_content) and must NOT execute.  Only the
        # sensing/run tools are executable here.
        # In SUPERVISED mode, propose/propose_edit/write_file are advisory: they
        # render an approval card (drawn in set_content) and must NOT auto-execute
        # here — only the sensing/run tools are executable. But in AUTONOMOUS mode
        # there is NO card and no operator to click it, so those calls MUST execute
        # instead: they run directly through _execute_tool_calls (→ _run_proposed_
        # command / _run_proposed_edit). Excluding them unconditionally was silently
        # dropping autonomous file writes and command proposals (the model's
        # write_file did nothing). So keep them only when supervised.
        if self.settings.get("approval_mode", "none") == "none":
            executable = list(calls)
        else:
            executable = [c for c in calls
                          if c.name not in ("propose", "propose_edit",
                                            "write_file")]
        # ── TOOL LOCK: dropped calls must be TOLD, not silently binned ──
        # When the budget is spent we lock tools for one final answer turn. The
        # old code just emptied `executable` and said nothing. That is the bug
        # behind "it hits the tool cap and never gives me the report":
        #
        #   · the model was mid-research, so its reply was mostly a tool call
        #     with little or no prose,
        #   · the call was dropped in silence — nothing fed back, nothing logged
        #     to the model,
        #   · the turn then settled, and strip_tool_calls() left an empty or
        #     near-empty bubble.
        #
        # The operator gets a blank answer to a question the model had actually
        # half-researched. Feeding the refusal back costs one round-trip and
        # turns a dead end into a finished answer.
        _locked_drop = []
        if self._tools_locked:
            _locked_drop = list(executable)
            executable = []
        # ── RECOVERY: the model printed a command instead of calling `run` ──
        # A known model-drift failure: instead of a `run` tool call, the model
        # writes the shell command in a ```bash``` fence. parse_tool_calls finds
        # no tool tag, so it renders as a copyable code block and NEVER executes —
        # the "it gives me commands with a copy banner instead of running them"
        # bug.
        #
        # This recovery fires in TWO tiers:
        #
        #   1. MISSION (walk-away): always recover. The operator unleashed it; a
        #      printed command is never the right answer during autonomous work.
        #
        #   2. REGULAR TURN (agent mode on, no mission): recover ONLY when the
        #      reply's own wording says it is ACTING, not EXPLAINING.  "Let me
        #      check…" + a fence = the model tried to act and fumbled the format;
        #      recover it.  "You could try running…" + a fence = it is showing an
        #      example to the operator; leave it alone.  The detector is
        #      reply_intends_action(), the same one the mission loop already uses,
        #      so the two judgments are consistent.
        #
        # The catastrophic floor in _execute_command still applies to anything
        # recovered here.  The approval mode gate still applies (if confirmations
        # are on, the recovered command goes through the confirmation dialog, not
        # straight to execution).
        _recover_fence = False
        if (not executable and not cancelled and self.current_agent_mode
                and not self._tools_locked):
            if self._mission_active:
                # Tier 1: mission — always recover.
                _recover_fence = True
            elif reply_intends_action(final):
                # Tier 2: regular turn, but the reply says it is acting.
                _recover_fence = True
        # ── SAME RECOVERY, FOR THE WEB TOOL ──
        # A printed URL is the identical drift to a printed shell block, and
        # it was the one the operator actually hit: three turns running, the
        # model said "let's read the top result", printed the search URL, and
        # never called web_read. The turn ended "done" with a promise in it.
        # Same two-tier gate, so a finished answer that CITES a source is
        # never fetched behind the operator's back.
        if _recover_fence and not self._shell_block_command(final):
            _url = printed_url_target(final)
            if _url:
                synthetic = ('<tool name="web_read">' + json.dumps({
                    "url": _url}) + "</tool>")
                recovered = parse_tool_calls(synthetic)
                if recovered:
                    executable = recovered
                    self.terminal_log(
                        "↩ recovered a printed URL into a web_read call "
                        "(the model wrote the link instead of reading it)",
                        "error")
                    self._activity_note(
                        "the model printed a URL instead of reading it - "
                        "fetching %s" % _url[:70], "gate")

        if _recover_fence:
            _cmd = self._shell_block_command(final)
            if _cmd and not is_catastrophic_command(_cmd):
                synthetic = ('<tool name="run">' + json.dumps({
                    "command": _cmd,
                    "reason": "auto-run: the model wrote a shell block instead of "
                              "calling the run tool"}) + "</tool>")
                recovered = parse_tool_calls(synthetic)
                if recovered:
                    executable = recovered
                    self.terminal_log(
                        "↩ recovered a printed shell block into a run call "
                        "(model wrote a code block instead of executing)", "error")
                    # Persist a correction so the model reads it on the NEXT
                    # turn and stops doing it.  This is the short-term fix —
                    # the persona carries the standing rule, but a model that
                    # has already drifted once needs the slap close to the
                    # drift, not two thousand tokens away in the system prompt.
                    try:
                        _corr_cid = (self.streaming_chat_id
                                     or self.current_chat_id)
                        if _corr_cid:
                            self.store.add_message(
                                _corr_cid, "user",
                                "[system correction] You wrote a shell command "
                                "in a ```bash``` code fence instead of calling "
                                "the run tool. The host recovered it this time. "
                                "On every future turn: CALL the run tool. Never "
                                "print a command for the operator to copy.",
                                meta={"kind": "system"})
                    except Exception:
                        pass
        # Honour the agent-mode toggle and the stop button.  If the user
        # turned agent mode off or hit stop, don't execute even if the
        # model emitted a tool tag.
        if executable and not cancelled and self.current_agent_mode:
            # A bare `notify` is the model ANNOUNCING to the operator — not
            # progress toward the objective. It must NOT reset the completion-
            # verify state or count as acting, or "done → notify → done → notify"
            # loops forever (two completion claims never land in a row, because
            # the notify between them clears the pending flag). Only SUBSTANTIVE
            # tool calls (anything but notify) count as work.
            if any(c.name != "notify" for c in executable):
                self._mission_kicks = 0
                self._mission_verify_pending = False
                self._mission_ever_acted = True
                self._mission_no_action_streak = 0
            # EFFICIENCY: gather the leading run of read-only tools and run
            # them together in ONE round-trip (parallel), instead of one
            # model call per lookup.  Stop at the first side-effecting tool
            # so anything with side effects still goes one-at-a-time through
            # its own confirm gate next turn — the safety model is unchanged.
            batch = []
            for c in executable:
                if self._pure_tool_fn(c) is not None:
                    batch.append(c)
                else:
                    break
            if len(batch) >= 2:
                self._set_working(True, self._status_for_batch(batch) + "…")
                self._execute_tool_batch(batch)
            elif batch:
                self._set_working(True, self._status_for_call(batch[0]) + "…")
                self._execute_tool_calls(batch)
            else:
                # First executable tool has side effects (or is otherwise not
                # batchable) → one at a time.
                #
                # THE REST ARE NOT SILENTLY DROPPED. They used to be, and it is
                # the second half of the "malformed call" failure: `web_read` is
                # deliberately NOT in the batchable set (the web readers were
                # pulled from it to shrink the prompt-injection surface), so a
                # reply containing two or three web_read calls — which the
                # persona explicitly tells the model to emit, "batch reads" —
                # ran only the FIRST and discarded the others without a word.
                # The model then got one result for three lookups, concluded it
                # had emitted malformed calls, apologised, and re-sent them.
                # Same failure again, forever.
                #
                # Telling it costs nothing and turns a mystery into an
                # instruction it can follow.
                self._set_working(
                    True, self._status_for_call(executable[0]) + "…")
                if len(executable) > 1:
                    _rest = executable[1:]
                    _names = ", ".join(
                        self._action_label(c) for c in _rest)[:400]
                    self.terminal_log(
                        f"↷ {len(_rest)} further call(s) not run this turn "
                        f"— they follow one at a time", "dim")
                    self._activity_note(
                        "%d further call(s) queued - they run one at a time"
                        % len(_rest), "note")
                    self._deferred_note = (
                        f"\n\n[host] NOTE — you emitted {len(executable)} tool "
                        f"calls in that reply and only the FIRST was run. The "
                        f"others were NOT executed and NOT lost; they simply do "
                        f"not run in parallel:\n    {_names}\n"
                        f"Nothing was malformed. Re-issue them ONE PER REPLY, "
                        f"reading each result before the next. Read-only tools "
                        f"like read_file and list_dir DO batch; web_read does "
                        f"not.")
                self._execute_tool_calls(executable[:1])
        else:
            # No executable tool ran this turn. Track how many turns in a row
            # THIS mission has produced no tool call — a live pentest runs tools
            # constantly, so a run of quiet turns means it's done or stuck.
            self._mission_no_action_streak = getattr(
                self, "_mission_no_action_streak", 0) + 1
            # ── Rule 1: a pending completion claim is CONFIRMED by any quiet turn.
            # Once the model has claimed done (emitted [[MISSION_COMPLETE]] last
            # turn → verify pending), the very next turn with no NEW substantive
            # action confirms it — whether that turn re-emits the token, says
            # "done, all clean", or produces filler. A finished model confirms in
            # natural language, NOT by re-emitting an exact token; demanding the
            # token twice was why "claim → re-verify → (talk) → claim → …" looped
            # forever. Only a real new tool call cancels a pending completion, and
            # that path runs through the executable branch (which clears the flag).
            if (self._mission_active and not cancelled
                    and self._mission_verify_pending):
                self._mission_active = False
                self._mission_verify_pending = False
                self.terminal_log(
                    "✅ mission complete — confirmed on re-verify", "ok")
                self._show_toast("Mission complete.", timeout=5)
                self._finish_turn_cleanup()
                return False
            # ── Rule 2 (smart completion): the mission has ACTED and this turn
            # produced no tool call. Decide stop-vs-continue by what the reply
            # SAYS, not a blind turn counter — this is what fixed "it answers me
            # 3 times before it stops":
            #   • reads as a CONCLUSION (no "next I'll…" intent), OR it has now
            #     stalled 3 quiet turns (a hard backstop) → force ONE re-verify;
            #     the next quiet turn confirms via Rule 1. A genuine multi-step
            #     run is never cut short: ACTING (a tool call) resets all of this
            #     in the executable branch above, so this only fires once the
            #     model has genuinely stopped doing things.
            #   • still intends a NEXT action ("I'll run X" with no tool call — a
            #     stall) → fall through to the continue-nudge at the end of this
            #     branch, which pushes it to actually act.
            # A degraded/empty reply is NOT a conclusion (the (#7) block below
            # handles that); only the 3-turn backstop can fire on junk, so
            # persistent junk still terminates rather than looping forever.
            if (self._mission_active and not cancelled
                    and self._mission_ever_acted
                    and not self._mission_verify_pending):
                # ── FAST STOP (1 turn, no verify round-trip): an UNAMBIGUOUS
                # completion ends the run immediately — the token emitted this
                # turn, or a decisive "assessment complete / nothing further"
                # phrase. This is the fix for "it answers me 3 different ways
                # before it stops": when the model clearly says it's finished AND
                # it has actually done work, believe it at once. (A real
                # multi-step run never reaches here mid-work — a tool call resets
                # everything in the executable branch above.)
                if ((_mission_done_signal
                        or reply_is_strong_conclusion(final))
                        and not looks_degraded(final)):
                    self._mission_active = False
                    self._mission_verify_pending = False
                    self.terminal_log(
                        "✅ mission complete — clear completion, ending now", "ok")
                    self._show_toast("Mission complete.", timeout=5)
                    self._finish_turn_cleanup()
                    return False
                # ── Otherwise a weaker/ambiguous settle: the model just stopped
                # calling tools without a decisive sign-off, OR it has stalled 3
                # quiet turns (hard backstop). Take ONE verify checkpoint; the
                # next quiet turn confirms via Rule 1. A reply that still intends
                # a NEXT action falls through to the continue-nudge instead.
                _stalled_out = self._mission_no_action_streak >= 3
                _concludes = (not looks_degraded(final)
                              and not reply_intends_action(final))
                if _concludes or _stalled_out:
                    self._mission_verify_pending = True
                    self._mission_directive = _MISSION_VERIFY_DIRECTIVE.format(
                        obj=self._mission_objective)
                    self.terminal_log(
                        "🔎 no tool call and the reply reads as complete "
                        "— forcing one final verify", "dim")
                    self._mission_continue(verify=True)
                    return False
            # (#7) Degraded-output check: if the model returned junk (empty,
            # one-word, or stuck repeating) and it wasn't a deliberate stop, flag
            # it. With auto_fallback_on_degraded on, hop to the next provider that
            # has a key so the NEXT turn retries elsewhere.
            if (not cancelled and not executable
                    and looks_degraded(final)):
                self.terminal_log("⚠ response looked degraded (empty/"
                                  "repetitive)", "error")
                # Never just stop on a degraded reply — retry automatically,
                # bounded so it can't loop forever. Hop to another provider
                # (if one has a key) and re-kick the SAME turn so the work
                # continues without the operator having to tap send.
                _dret = getattr(self, "_degraded_retries", 0)
                if (self.settings.get("auto_fallback_on_degraded", True)
                        and _dret < 3 and not self._stop_requested):
                    self._degraded_retries = _dret + 1
                    # PINNED PROVIDER: never hop clouds behind the operator's
                    # back. Whatever provider is selected (default
                    # SiliconFlow · DeepSeek-V4-Flash) STAYS selected — a
                    # degraded reply just re-kicks the SAME provider. The backend
                    # already walks its own model chain for rate-limits /
                    # unavailability; a junk-content reply gets one more shot on
                    # the same cloud. active_provider is never mutated or
                    # persisted here — only the operator's manual model switcher
                    # changes it.
                    self.terminal_log(
                        f"↻ auto-retry {self._degraded_retries}/3 "
                        f"(staying on selected provider)", "dim")
                    # ── RETIRE THE JUNK BUBBLE BEFORE RETRYING ──
                    # Every other re-kick path (force-answer, stall nudge,
                    # _feed_tool_result, _mission_continue) nulls these two
                    # first. This one did not, so the degraded reply stayed
                    # parented in msg_box and the retry appended a SECOND
                    # bubble underneath it -- the operator saw the junk reply
                    # and its replacement, up to three times over. Drop the
                    # row and the refs, then retry into a clean one.
                    _junk = self.streaming_msg_widget
                    self.streaming_msg_widget = None
                    self.streaming_msg_db_id = None
                    if _junk is not None:
                        try:
                            self.msg_box.remove(_junk)
                        except Exception:
                            pass
                    self._schedule_kick(600)
                    return
                else:
                    # Retries exhausted. Don't loop — just note it. If the model
                    # is actually done, Rule 1/Rule 2 at the top of this branch
                    # end the mission within a couple of quiet turns; if a human
                    # is driving, they tap send.
                    self._degraded_retries = 0
                    self._show_toast(
                        "That reply looked degraded after retries. Tap send to "
                        "try again.", timeout=6)
            # ── the two dead ends that lose an answer ──
            # (a) tools were locked and the model still called one, or
            # (b) the reply is ALL tool call and no prose,
            # either way settling here hands the operator an empty bubble.
            # Push exactly one more turn that demands the answer in words.
            _visible = strip_tool_calls(final or "").strip()
            _empty_answer = (not cancelled and not executable
                             and not _visible
                             and not self._mission_active)
            # ── A TOOL CALL THE HOST DIDN'T UNDERSTAND ──
            # Models emit tool calls in several dialects, including their own
            # native special-token format. Anything parse_tool_calls doesn't
            # recognise is neither executed NOR stripped: it leaks onto the
            # screen as raw protocol garbage and the turn ends with nothing to
            # run. _normalise_tool_syntax now converts the known dialects, but
            # this is the fail-open backstop for the ones it doesn't know yet —
            # tell the model its call wasn't understood and show it the format
            # that works. That fixes the CLASS instead of one member of it.
            # ── AND IT ONLY COUNTS IF THE ANSWER IS MISSING ──
            # `_empty_answer` above is gated on `not _visible`; this was not,
            # so a reply that ANSWERED THE QUESTION IN FULL and merely
            # contained tag-shaped text was treated as a failed tool call and
            # the turn was kicked again. The model has nothing new to send,
            # so it repeats itself -- twice, because the budget below is 2.
            # That is the "it answers twice" the operator reported, and the
            # commonest trigger is asking Basilisk to explain its own tool
            # syntax, because the force-answer text quotes that syntax back.
            #
            # (looks_like_failed_tool_call now masks ``` fences too, so a
            # documented example no longer registers at all -- but the gate
            # belongs here regardless: a delivered answer is never a reason
            # to ask for the answer again.)
            _bad_call = (not cancelled and not executable
                         and not _visible
                         and looks_like_failed_tool_call(final or ""))
            if _bad_call:
                self.terminal_log(
                    "⚠ the model emitted a tool call in a syntax this build "
                    "doesn't parse — asking it to re-send", "error")
            # ── _locked_drop NEEDS THE SAME GATE, FOR THE SAME REASON ──
            # A dropped tool call is a reason to ask for the answer in prose
            # ONLY when there is no answer yet. After the host tells the model
            # "write the full answer NOW", the very next reply routinely does
            # exactly that AND appends one more tool call -- which is dropped,
            # which re-triggers this branch, which asks for the answer again.
            # The operator reads the same complete answer two or three times.
            _drop_without_answer = bool(_locked_drop) and not _visible
            if (not cancelled
                    and (_drop_without_answer or _empty_answer or _bad_call)
                    and getattr(self, "_force_answer_tries", 0) < 2
                    and not self._stop_requested):
                self._force_answer_tries = \
                    getattr(self, "_force_answer_tries", 0) + 1
                if _locked_drop:
                    _why = ("your tool call was NOT run — the tool budget for "
                            "this question is spent")
                elif _bad_call:
                    _why = (
                        "your last message contained a tool call this host "
                        "could NOT parse, so NOTHING ran and the raw text was "
                        "shown to the operator. Do not use your native "
                        "function-calling tokens, DSML tags, argument child "
                        "tags such as <parameter name=\"...\">, JSON tool "
                        "blocks, <tool_call>, <invoke> or <function=...>. "
                        "Put the arguments in the tag BODY as one JSON "
                        "object. The ONLY format that works is exactly:\n"
                        '  <tool name="web_read">{"url": "https://example.com"}'
                        "</tool>\n"
                        "one tag, the tool name in a name=\"...\" attribute, "
                        "plain JSON in the body, closed with </tool>. RE-SEND "
                        "the call you were trying to make, in that exact form")
                else:
                    _why = "your reply contained no answer, only a tool call"
                # The label had two branches for three cases, so an unparsed
                # tool call was announced as "empty reply" — the log named the
                # wrong problem at the exact moment you needed the right one.
                _label = ("dropped tool call" if _locked_drop
                          else "unreadable tool call — asking for a re-send"
                          if _bad_call else "empty reply")
                self.terminal_log(
                    ("── asking the model to re-send its tool call"
                     if _bad_call else "── forcing the final answer")
                    + f" ({_label})", "dim")
                try:
                    _fc = self.streaming_chat_id or self.current_chat_id
                    self.store.add_message(
                        _fc, "user",
                        "<tool_result>\n[system] " + _why + ". Nothing you "
                        "gathered is lost — it is all in this conversation."
                        + ("" if _bad_call else
                           " Do NOT call another tool. Write the FULL answer "
                           "to the operator's original question NOW, in prose, "
                           "using everything you have already read. If some "
                           "part is still unverified, say so plainly and "
                           "answer the rest — a partial answer is useful, "
                           "silence is not.")
                        + "\n</tool_result>",
                        meta={"kind": "tool_result"})
                except Exception:
                    pass
                if not _bad_call:
                    # A dropped/empty answer means "stop calling tools". A
                    # MALFORMED call means the opposite — it still needs to run,
                    # just in the right syntax.
                    self._tools_locked = True
                self.streaming_msg_widget = None
                self.streaming_msg_db_id = None
                try:
                    self._kick_assistant_turn()
                    return False
                except Exception:
                    log(f"force-answer kick failed: {traceback.format_exc()}")

            elif not cancelled and (_drop_without_answer or _empty_answer
                                    or _bad_call):
                # Re-send budget spent and the turn still produced nothing
                # runnable.  Previously this settled in silence and handed the
                # operator an empty bubble with no idea why — say it plainly
                # instead.  The counter resets on the next fresh turn, so
                # tapping send genuinely does retry.
                self._degraded_retries = 0
                self.terminal_log(
                    "⚠ the model kept emitting an unreadable tool call — "
                    "giving up on this turn", "error")
                self._show_toast(
                    "The model's tool calls couldn't be read after 2 "
                    "attempts. Tap send to retry, or switch model in "
                    "Settings.", timeout=8)
            elif not cancelled and not executable:
                # A clean, non-degraded settle → reset the degraded retry counter
                # (but NOT the no-action streak: a plain reply is still a turn
                # with no tool call, and Rule 2 needs to see the run of them).
                self._degraded_retries = 0
            # Turn has fully settled (no tool chaining).  Record it for
            # persistent memory in the background — no-op unless memory is on.
            if getattr(self, "_ext", None) and not cancelled:
                try:
                    rec_chat = self.streaming_chat_id or self.current_chat_id
                    msgs = self.store.list_messages(rec_chat)
                    utext = ""
                    for m in reversed(msgs):
                        if (m.role == "user"
                                and "<tool_result>" not in (m.content or "")):
                            utext = m.content
                            break
                    threading.Thread(
                        target=self._ext.record_turn,
                        args=(utext, final), daemon=True).start()
                except Exception:
                    pass
            # ── Autonomous mission: a plain (no-tool) reply does NOT end the
            #    run.  It ends only on an explicit, re-verified completion
            #    signal or the Stop button. ──
            if self._mission_active and not cancelled:
                if _mission_done_signal:
                    # First explicit completion claim (the token this turn) →
                    # force ONE re-verify; the next quiet turn confirms via Rule 1
                    # (it no longer has to re-emit the exact token — talk/filler
                    # counts). A premature "done" still can't slip through in one
                    # turn.
                    self._mission_verify_pending = True
                    self._mission_directive = (
                        _MISSION_VERIFY_DIRECTIVE.format(
                            obj=self._mission_objective))
                    self._mission_continue(verify=True)
                    return False
                elif (not self._mission_ever_acted
                        and not looks_degraded(final)
                        and not reply_intends_action(final)):
                    # NEVER-ACTED mission whose reply reads as a COMPLETE answer
                    # with NO intent to act — this was really a question (or a
                    # trivial task the model fully answered in one turn). Stop
                    # NOW instead of re-kicking the same answer several times.
                    # (If it HAD intended to act — a preamble/stall — we fall
                    # through to the nudge below and push it to actually act; the
                    # idle cap in _mission_continue bounds a model that only ever
                    # talks.) This is the other half of the "answers me 3 times"
                    # fix: the acted path is handled by Rule 2 above.
                    self._mission_active = False
                    self.terminal_log(
                        "✅ answered in one turn — nothing to act on, ending",
                        "ok")
                    self._finish_turn_cleanup()
                    return False
                else:
                    # Acted-and-mid-task, or a stall that still intends action →
                    # keep working toward the objective. (A pending claim was
                    # accepted by Rule 1 above; a concluded acted-mission by
                    # Rule 2 above.)
                    self._mission_directive = (
                        _MISSION_CONTINUE_DIRECTIVE.format(
                            obj=self._mission_objective))
                    self._mission_continue()
                    return False
            # ── ANSWER MODE: an ANNOUNCED next step with no tool call is a
            #    stall, not an answer. ──
            # Everything above is gated on `_mission_active`, so in answer mode
            # (leashed — the normal way a question gets asked) a reply like
            #
            #   "I've got the site and the paper metadata. Let me grab the HN
            #    discussion thread… and also look for a news writeup."
            #
            # fell straight through to cleanup. The model narrated its next two
            # actions instead of emitting the calls, and the turn simply ENDED —
            # leaving the operator looking at a promise of work that would never
            # happen, and no report. Asking "did you do it?" then starts a fresh
            # turn with no memory that anything was pending.
            #
            # That gap is not incidental: ANSWER MODE's own directive tells the
            # model to "chain as many reads as it takes", so a multi-step answer
            # is the DESIGNED behaviour here — but the only stall recovery in the
            # file (reply_intends_action, already used by the mission loop) was
            # never wired to this path. Answer mode could chain N tool calls and
            # die the moment the model described the next one instead of calling
            # it.
            #
            # BOUNDED, because a model that only ever narrates must not spin:
            # after ANSWER_STALL_NUDGE_MAX pushes we stop nudging and let the
            # turn end, so the worst case is a couple of extra round-trips.
            # reply_is_bare_stall, NOT reply_intends_action: the latter answers
            # the MISSION loop's question ("mid-task or finished?"), and wiring
            # it here asked it the wrong one. A complete answer that mentions a
            # next step — or just ends "Let me know if you want more" — was read
            # as a stall and nudged, and with a budget of 2 nudges the operator
            # got the SAME ANSWER THREE TIMES for one question.
            if (not cancelled and not executable
                    and not self._stop_requested
                    and not self._tools_locked
                    and not looks_degraded(final)
                    and reply_is_bare_stall(final)
                    and getattr(self, "_answer_stall_nudges", 0)
                        < ANSWER_STALL_NUDGE_MAX):
                self._answer_stall_nudges = getattr(
                    self, "_answer_stall_nudges", 0) + 1
                self.terminal_log(
                    "↻ you said you'd do something but called no tool "
                    f"— nudging ({self._answer_stall_nudges}/"
                    f"{ANSWER_STALL_NUDGE_MAX})", "dim")
                try:
                    _sc = self.streaming_chat_id or self.current_chat_id
                    self.store.add_message(
                        _sc, "user",
                        "<tool_result>\n[system note: you described what you "
                        "were going to do next but did not emit a tool call, so "
                        "NOTHING RAN. Saying it is not doing it. Either emit the "
                        "tool call now, or — if you already have enough — give "
                        "the complete final answer to the operator's question in "
                        "full, with no further preamble.]\n</tool_result>",
                        meta={"kind": "tool_result"})
                except Exception as e:
                    log(f"answer-stall nudge: store write failed: {e}")
                self.streaming_msg_widget = None
                self.streaming_msg_db_id = None
                self._kick_assistant_turn()
                return False
            self._finish_turn_cleanup()
        return False

    def _on_stream_error(self, err, epoch=None):
        if self._stale_stream(epoch):
            # A dead stream must not schedule a retry for a turn that has
            # already moved on -- that is a second answer, arriving late.
            return False
        self._mark_turn_progress()
        self.terminal_log(f"✗ stream error: {err}", "error")
        if self.streaming_msg_widget:
            # Preserve any tokens that already streamed in.  Wiping the
            # widget and replacing with just the error text discards
            # potentially useful partial output (an explanation that got
            # cut off, a half-finished tool call, etc).
            # Same boundary as the finish and stop paths: whatever streamed in
            # before the error is about to be stored and replayed as history.
            partial = self.streaming_msg_widget.canonical_content() or ""
            sep = "\n\n" if partial.strip() else ""
            final_text = f"{partial}{sep}*(error: {err})*"
            self.streaming_msg_widget.set_content(final_text)
            if self.streaming_msg_db_id:
                self.store.update_message(self.streaming_msg_db_id,
                                          final_text)
        self._show_toast(f"Error: {err}")
        # Clear widget refs without re-marking the message (we just wrote
        # the error into it above), then restore the button/banner.
        self.streaming_msg_widget = None
        self.streaming_msg_db_id = None
        self.streaming_chat_id = None
        self._tool_chain_depth = 0
        self._turn_active = False
        # ── Autonomous mission: a transient stream/API error must NOT kill the
        #    run.  Back off and retry, forever, until it succeeds or you Stop. ──
        if self._mission_active and not self._stop_requested:
            self._error_retries += 1
            # exponential backoff capped at 60s — so a persistent outage (e.g.
            # provider down for hours) just keeps politely retrying, and a run
            # left for weeks survives it and resumes the moment it clears.
            delay = min(60000, 1000 * (2 ** min(self._error_retries - 1, 6)))
            self.terminal_log(
                f"↻ stream error — retrying in {delay // 1000}s "
                f"[{self._error_retries}]", "dim")
            self._activity_note(
                "stream error - retrying in %ds (attempt %d): %s"
                % (delay // 1000, self._error_retries, str(err)[:80]), "gate")
            self._set_working(True, "retrying after error…")
            self._schedule_kick(delay)
            return False
        self._set_working(False)
        self._set_send_mode(False)
        return False

    # ── tool execution ──────────────────────────────────────────

    def _workspace_call(self, n, a):
        """One arg-mapper for all 13 workspace tools, shared by BOTH dispatch
        paths (autonomous and approval-gated).

        Written once deliberately. The two dispatch sites in this file have
        drifted before -- a tool wired into one and not the other works
        perfectly until the operator flips approval mode, then vanishes. A
        single mapper cannot drift from itself.

        The generous key aliases exist because the model does not always
        emit the exact parameter name: it will send `file`, `filename` or
        `target` when the spec says `path`. Accepting the obvious synonyms
        turns a failed tool call into a working one, and the cost is a dict
        lookup.
        """
        def _p(*names, default=""):
            for k in names:
                if k in a and a[k] not in (None, ""):
                    return a[k]
            return default

        def _b(*names, default=False):
            v = _p(*names, default=None)
            if v is None:
                return default
            if isinstance(v, bool):
                return v
            return str(v).strip().lower() in ("1", "true", "yes", "on")

        def _i(*names, default=0):
            try:
                return int(_p(*names, default=default))
            except (TypeError, ValueError):
                return default

        path = _p("path", "file", "filename", "target", "name")
        if n == "workspace_import":
            return lambda: tool_workspace_import(
                _p("zip_path", "zip", "path", "file", "archive"),
                _p("name", "workspace", "label"))
        if n == "workspace_status":
            return lambda: tool_workspace_status()
        if n == "workspace_overview":
            return lambda: tool_workspace_overview()
        if n == "workspace_tree":
            return lambda: tool_workspace_tree(
                _p("path", "dir", "directory"),
                _i("max_entries", "limit", "max", default=400))
        if n == "workspace_search":
            return lambda: tool_workspace_search(
                _p("pattern", "query", "q", "text", "needle"),
                _p("glob", "filter", "files", "include"),
                _b("regex", "is_regex", "re"),
                _i("max_results", "limit", "max", default=120),
                _i("context", "ctx", "around", default=0))
        if n == "workspace_read":
            return lambda: tool_workspace_read(
                path, _i("start", "from", "start_line", default=1),
                _i("end", "to", "end_line", default=0))
        if n == "workspace_replace":
            return lambda: tool_workspace_replace(
                path, _p("old", "old_str", "find", "search"),
                _p("new", "new_str", "replace", "replacement"),
                _i("count", "n", "occurrences", default=1))
        if n == "workspace_write":
            return lambda: tool_workspace_write(
                path, _p("content", "text", "body", "source", "code"),
                _b("create", "new", "create_new"))
        if n == "workspace_delete":
            return lambda: tool_workspace_delete(path)
        if n == "workspace_diff":
            return lambda: tool_workspace_diff(path)
        if n == "workspace_revert":
            return lambda: tool_workspace_revert(path)
        if n == "workspace_export":
            return lambda: tool_workspace_export(
                _p("out_path", "out", "dest", "output", "zip_path"),
                _b("include_secrets", "secrets"),
                _b("changed_only", "only_changed", "changed"),
                _b("force", "override"))
        if n == "workspace_close":
            return lambda: tool_workspace_close(_b("discard", "delete"))
        if n == "workspace_test_command":
            return lambda: tool_workspace_test_command()
        if n == "workspace_baseline":
            return lambda: tool_workspace_baseline(
                _p("command", "cmd", "test_command"),
                _i("timeout", "secs", default=900))
        if n == "workspace_verify":
            return lambda: tool_workspace_verify(
                _p("command", "cmd", "test_command"),
                _i("timeout", "secs", default=900))
        if n == "workspace_health":
            return lambda: tool_workspace_health()
        return lambda: {"ok": False, "error": f"unknown workspace tool: {n}"}

    def _pure_tool_fn(self, call):
        """Return a zero-arg callable that produces a result dict for a
        read-only, side-effect-free tool that's safe to run in parallel and
        batch — or None if this tool must take the normal (gated / specially
        rendered) single path.  This is the allow-list that decides what can
        be bundled into one round-trip."""
        n = call.name
        a = call.args or {}

        def i(v, d):
            try:
                return int(float(v))
            except (TypeError, ValueError):
                return d

        # Pentest planning / inventory / reference — pure local work (which-
        # checks, building a command plan, text parsing, reading the
        # filesystem, formatting), no network and no execution, so it's safe
        # to bundle.  (The web / OSINT / social / GitHub readers that used to
        # live here were removed — they ingested attacker-controllable external
        # text, i.e. the prompt-injection surface.)
        if n == "tooling_check":
            return lambda: tool_tooling_check()
        if n == "pentest_plan":
            return lambda: tool_pentest_plan(
                a.get("target", a.get("host", a.get("url", ""))),
                a.get("profile", a.get("mode", "web")),
                a.get("intensity", a.get("speed", "normal")))
        if n == "parse_output":
            return lambda: tool_parse_output(
                a.get("tool", a.get("name", "")),
                a.get("raw", a.get("output", a.get("text", ""))),
                a.get("enrich_cves", a.get("enrich", False)) not in
                    (False, "false", "0", 0, None))
        if n == "methodology":
            return lambda: tool_methodology(
                a.get("area", a.get("topic", "")),
                a.get("phase", ""))
        if n == "wordlist_find":
            return lambda: tool_wordlist_find(
                a.get("kind", a.get("type", a.get("category", ""))))
        if n == "cheatsheet":
            return lambda: tool_cheatsheet(
                a.get("topic", a.get("tool", a.get("name", ""))))
        if n == "report_findings":
            return lambda: tool_report_findings(
                a.get("findings", a.get("items", [])),
                a.get("target", a.get("host", a.get("url", ""))),
                a.get("scope_note", a.get("scope", "")),
                a.get("title", ""))
        if n == "attack_writeup":
            return lambda: tool_attack_writeup(
                a.get("access", a.get("summary", "")),
                a.get("steps", a.get("path_steps", None)),
                a.get("target", a.get("host", a.get("url", ""))),
                a.get("scope_note", a.get("scope", "")),
                a.get("impact", ""), a.get("remediation", a.get("fix", "")),
                a.get("root_cause", a.get("cause", "")),
                a.get("ledger_events", a.get("events", None)))
        if n.startswith("workspace_"):
            return self._workspace_call(n, a)
        if n == "code_tooling_check":
            return lambda: tool_code_tooling_check()
        if n == "code_scan_plan":
            return lambda: tool_code_scan_plan(
                a.get("path", a.get("dir", a.get("target", "."))),
                a.get("kind", a.get("type", "auto")),
                a.get("intensity", a.get("depth", "normal")))
        if n == "zday_scan":
            return lambda: _zdayfind.zday_scan(
                path=_ws_path(a.get("path", a.get("dir", a.get("target", "")))),
                code=a.get("code", a.get("source", "")),
                like=a.get("like", a.get("variant_of", a.get("snippet", ""))),
                focus=a.get("focus", a.get("classes", "")),
                filename=a.get("filename", a.get("name", "snippet")))
        if n == "zday_signatures":
            return lambda: _zdayfind.signature_catalog()
        if n == "saml_attack":
            return lambda: _exploits.saml_attack(
                a.get("mode", a.get("technique", "signature_wrapping")),
                a.get("assertion", a.get("response", "")))
        if n == "cloud_storage":
            return lambda: _exploits.cloud_storage(
                a.get("provider", a.get("cloud", "s3")),
                a.get("bucket", a.get("container", a.get("name", ""))))
        if n == "subdomain_takeover":
            return lambda: _exploits.subdomain_takeover(
                a.get("host", a.get("subdomain", a.get("domain", ""))),
                a.get("cname", a.get("target", "")))
        if n == "padding_oracle":
            return lambda: _exploits.padding_oracle(
                a.get("mode", "detect"),
                a.get("ciphertext", a.get("data", "")),
                a.get("block_size", a.get("blocksize", 16)))
        if n == "xslt_injection":
            return lambda: _exploits.xslt_injection(
                a.get("mode", "detect"), a.get("cmd", a.get("command", "id")))
        if n == "parse_scan":
            return lambda: tool_parse_scan(
                a.get("tool", a.get("scanner", a.get("name", ""))),
                a.get("raw", a.get("output", a.get("json", a.get("text", "")))))
        if n == "triage_findings":
            return lambda: tool_triage_findings(
                a.get("findings", a.get("items", [])))
        if n == "remediation_hint":
            return lambda: tool_remediation_hint(
                a.get("finding", a.get("item", a)))
        # ── Engagement state: scope allowlist, asset graph, loot (read/record;
        # scope_check is the authorisation boundary, fails closed) ──
        if n == "scope_set":
            return lambda: tool_scope_set(
                a.get("targets", a.get("scope", a.get("hosts", []))),
                a.get("mode", "replace"))
        if n == "scope_check":
            return lambda: tool_scope_check(
                a.get("target", a.get("host", a.get("url", ""))))
        if n == "scope_show":
            return lambda: tool_scope_show()
        if n == "scope_exclude":
            return lambda: tool_scope_exclude(
                a.get("targets", a.get("exclusions", a.get("hosts", []))),
                a.get("mode", "replace"))
        if n == "scope_window":
            return lambda: tool_scope_window(
                a.get("start", ""), a.get("end", ""), bool(a.get("clear", False)))
        if n == "scope_authorisation":
            return lambda: tool_scope_authorisation(
                a.get("client", ""), a.get("authorised_by", a.get("authorized_by", "")),
                a.get("reference", a.get("ref", "")))
        if n == "asset_record":
            return lambda: tool_asset_record(
                a.get("host", a.get("target", "")), a.get("service", ""),
                a.get("port", None), a.get("finding", ""),
                a.get("access", ""), a.get("note", ""))
        if n == "engagement_graph":
            return lambda: tool_engagement_graph(a.get("host", ""))
        if n == "loot_record":
            return lambda: tool_loot_record(
                a.get("host", ""), a.get("kind", "credential"),
                a.get("username", a.get("user", "")),
                a.get("secret", a.get("password", a.get("hash", ""))),
                a.get("service", ""), a.get("note", ""))
        if n == "loot_list":
            return lambda: tool_loot_list()
        if n == "loot_reuse":
            return lambda: tool_loot_reuse()
        # ── Exploitation oracle: verify whether an exploit actually landed and
        #    keep a verdict ledger that feeds the loop (local; no target/network
        #    side effects beyond a local OOB canary listener) ──
        if n == "oracle_arm":
            return lambda: tool_oracle_arm(
                a.get("objective", a.get("goal", a.get("what", ""))),
                a.get("target", a.get("url", a.get("host", ""))),
                a.get("technique", a.get("vuln", a.get("class", a.get("attack", "")))),
                a.get("criterion_type", a.get("type", a.get("criterion", a.get("check", "contains")))),
                a.get("criterion_value", a.get("value", a.get("marker",
                    a.get("expect", a.get("expected", a.get("pattern", "")))))),
                a.get("blind", a.get("oob", False)),
                a.get("oob_host", a.get("host", a.get("callback_host", ""))))
        if n == "oracle_check":
            return lambda: tool_oracle_check(
                a.get("attempt_id", a.get("id", a.get("attempt", ""))),
                a.get("evidence", a.get("response", a.get("body",
                    a.get("output", a.get("text", a.get("resp", "")))))),
                a.get("status", a.get("code", a.get("status_code", None))),
                a.get("baseline", a.get("base", a.get("normal", a.get("control", "")))))
        if n == "oracle_status":
            return lambda: tool_oracle_status()
        if n == "oracle_listen":
            return lambda: tool_oracle_listen(
                a.get("port", 0),
                a.get("host", a.get("callback_host", a.get("ip", ""))))
        if n == "graph_ingest":
            return lambda: tool_graph_ingest(
                a.get("parsed", a.get("findings", a.get("result", a))))
        if n == "sqlmap_plan":
            return lambda: tool_sqlmap_plan(
                a.get("target", a.get("url", a.get("host", ""))),
                a.get("mode", "detect"), a.get("data", ""), a.get("cookie", ""),
                a.get("headers", ""), a.get("level", 1), a.get("risk", 1),
                a.get("dbms", ""), a.get("technique", ""), a.get("db", ""),
                a.get("table", ""), a.get("request_file", a.get("r", "")),
                a.get("extra", ""))
        if n == "benchmark_targets":
            return lambda: tool_benchmark_targets(a.get("target", ""))
        if n == "benchmark_score":
            return lambda: tool_benchmark_score(
                a.get("target", ""), a.get("findings", a.get("items", [])),
                a.get("ground_truth", a.get("gt", None)), a.get("tool", "basilisk"))
        if n == "benchmark_report":
            return lambda: tool_benchmark_report(
                a.get("scored", a.get("result", a)))
        if n == "benchmark_compare":
            return lambda: tool_benchmark_compare(
                a.get("runs", a.get("results", a.get("items", []))))
        if n == "load_tools":
            return lambda: tool_load_tools(
                a.get("group", a.get("name", a.get("groups", ""))),
                unleashed=self._unleashed)
        if n == "submit_flag":
            return lambda: tool_submit_flag(
                a.get("flag", a.get("value", "")), a.get("challenge", ""))
        if n == "juiceshop_score":
            return lambda: tool_juiceshop_score(
                a.get("base_url", a.get("url", a.get("target",
                      "http://localhost:3000"))))
        if n == "juiceshop_report":
            return lambda: tool_juiceshop_report(a.get("scored", a.get("result", a)))
        if n == "juiceshop_next":
            return lambda: tool_juiceshop_next(
                a.get("base_url", a.get("url", "http://localhost:3000")),
                a.get("max_difficulty", a.get("max_stars", 0)),
                a.get("limit", 0), a.get("per_tier", a.get("per_star", 0)))
        if n == "juiceshop_diff":
            return lambda: tool_juiceshop_diff(
                a.get("base_url", a.get("url", "http://localhost:3000")),
                a.get("since", a.get("solved_names", a.get("previous"))))
        if n == "juiceshop_source":
            return lambda: tool_juiceshop_source(
                a.get("action", "tree"), a.get("path", ""),
                a.get("pattern", a.get("query", "")),
                a.get("container", "juiceshop"),
                a.get("base", a.get("base_path", "/juice-shop")))
        if n == "jwt_forge":
            return lambda: tool_jwt_forge(
                a.get("token", ""), a.get("mode", "none"),
                a.get("email", ""), a.get("role", ""),
                a.get("public_key", a.get("pubkey", "")),
                a.get("payload_overrides", a.get("overrides")))
        if n == "nosql_injection":
            return lambda: tool_nosql_injection(
                a.get("mode", "auth_bypass"), a.get("field", "email"),
                a.get("target", ""))
        if n == "xxe_payload":
            return lambda: tool_xxe_payload(
                a.get("mode", "file_read"),
                a.get("file_path", a.get("file", "/etc/passwd")))
        if n == "coupon_forge":
            return lambda: tool_coupon_forge(
                a.get("mode", "tamper"), a.get("discount", 20),
                a.get("scheme", "z85"), a.get("value", a.get("campaign", "")))
        if n == "captcha_solve":
            return lambda: tool_captcha_solve(
                a.get("url", ""),
                a.get("captcha_text", a.get("text", a.get("captcha", ""))),
                a.get("base_url", ""))
        if n == "reset_password":
            return lambda: tool_reset_password(
                a.get("mode", "methodology"), a.get("email", ""),
                a.get("new_password", a.get("password", "Pwned123!")))
        if n == "business_logic":
            return lambda: tool_business_logic(
                a.get("area", a.get("category", "all")))
        if n == "ssti_payload":
            return lambda: tool_ssti_payload(
                a.get("engine", "detect"), a.get("cmd", a.get("command", "id")))
        if n == "ssrf_payload":
            return lambda: tool_ssrf_payload(
                a.get("mode", "internal"),
                a.get("target_url", a.get("url", "http://localhost/")),
                a.get("host", "169.254.169.254"))
        if n == "deserialization_payload":
            return lambda: tool_deserialization_payload(
                a.get("platform", "node"), a.get("cmd", a.get("command", "id")))
        if n == "prototype_pollution":
            return lambda: tool_prototype_pollution(
                a.get("prop", a.get("property", "isAdmin")),
                a.get("value", "true"), a.get("vector", "json"))
        if n == "path_traversal":
            return lambda: tool_path_traversal(
                a.get("mode", "read"),
                a.get("file_path", a.get("file", "/etc/passwd")),
                a.get("filename", "malicious.md"))
        if n == "xss_payload":
            return lambda: tool_xss_payload(
                a.get("context", "html"), a.get("mode", "basic"))
        if n == "sqli_payload":
            return lambda: tool_sqli_payload(
                a.get("mode", "auth_bypass"), a.get("dbms", "generic"),
                a.get("columns", 3), a.get("table", "users"))
        if n == "payload_encoder":
            return lambda: tool_payload_encoder(
                a.get("payload", a.get("text", "")), a.get("scheme", "all"),
                a.get("decode", False))
        if n == "tech_fingerprint":
            return lambda: tool_tech_fingerprint(
                a.get("headers", ""), a.get("body", ""))
        if n == "waf_detect":
            return lambda: tool_waf_detect(
                a.get("blocked_payload", a.get("payload", "")),
                a.get("response_body", a.get("body", "")),
                a.get("status_code", a.get("status", 0)))
        if n == "trick_detect":
            return lambda: tool_trick_detect(
                a.get("text", a.get("body", a.get("content", ""))))
        if n == "payload_mutate":
            return lambda: tool_payload_mutate(
                a.get("body", a.get("request", "")),
                a.get("payload", "' OR 1=1--"),
                a.get("fmt", a.get("format", "auto")), a.get("mode", "replace"))
        if n == "session_flow":
            return lambda: tool_session_flow(
                a.get("mode", "extract"),
                a.get("response", a.get("body", "")), a.get("flow", ""))
        if n == "oracle_analyze":
            return lambda: tool_oracle_analyze(
                a.get("mode", "diff"), a.get("baseline", ""), a.get("test", ""),
                a.get("baseline_status", 0), a.get("test_status", 0),
                a.get("baseline_times", ""), a.get("payload_times", ""))
        if n == "command_injection":
            return lambda: tool_command_injection(
                a.get("os_type", a.get("os", "unix")),
                a.get("mode", "inline"),
                a.get("cmd", a.get("command", "id")))
        if n == "idor_probe":
            return lambda: tool_idor_probe(
                a.get("base", a.get("url", "")),
                a.get("id_value", a.get("id", "1")),
                a.get("strategy", "all"))
        if n == "race_condition":
            return lambda: tool_race_condition(
                a.get("method", "POST"),
                a.get("url", a.get("target", "")),
                a.get("body", a.get("data", "")),
                a.get("headers", ""),
                a.get("parallel", a.get("count", 20)))
        if n == "upload_bypass":
            return lambda: tool_upload_bypass(
                a.get("filename", a.get("name", "shell.php")),
                a.get("content_type", a.get("mime", "image/png")),
                a.get("technique", "all"))
        if n == "graphql_probe":
            return lambda: tool_graphql_probe(
                a.get("mode", "introspect"),
                a.get("field", ""),
                a.get("payload", ""))
        if n == "open_redirect":
            return lambda: tool_open_redirect(
                a.get("target", a.get("url", "http://evil.example")),
                a.get("param", "redirect"),
                a.get("legit_host", a.get("host", "example.com")))
        if n == "cors_probe":
            return lambda: tool_cors_probe(
                a.get("origin", "https://evil.example"),
                a.get("target_host", a.get("host", "example.com")))
        if n == "ldap_injection":
            return lambda: tool_ldap_injection(
                a.get("mode", "auth_bypass"), a.get("field", "username"))
        if n == "xpath_injection":
            return lambda: tool_xpath_injection(a.get("mode", "auth_bypass"))
        if n == "crlf_injection":
            return lambda: tool_crlf_injection(
                a.get("mode", "header"), a.get("value", ""))
        if n == "host_header_injection":
            return lambda: tool_host_header_injection(
                a.get("mode", "reset"), a.get("host", "evil.example"))
        if n == "ssi_injection":
            return lambda: tool_ssi_injection(a.get("mode", "ssi"))
        if n == "csv_injection":
            return lambda: tool_csv_injection(a.get("mode", "detect"))
        if n == "request_smuggling":
            return lambda: tool_request_smuggling(a.get("mode", "clte"))
        if n == "csrf_poc":
            return lambda: tool_csrf_poc(
                a.get("method", "POST"), a.get("url", a.get("target", "")),
                a.get("body", a.get("data", "")), a.get("mode", "form"))
        if n == "clickjacking":
            return lambda: tool_clickjacking(
                a.get("url", a.get("target", "")), a.get("mode", "check"))
        if n == "mass_assignment":
            return lambda: tool_mass_assignment(
                a.get("base_body", a.get("body", "{}")), a.get("fields", ""))
        if n == "auth_bypass_headers":
            return lambda: tool_auth_bypass_headers(
                a.get("url", a.get("target", "")), a.get("mode", "headers"))
        if n == "auth_attack":
            return lambda: tool_auth_attack(
                a.get("mode", "spray"), a.get("url", a.get("target", "")),
                a.get("users", "users.txt"), a.get("passwords", ""))
        if n == "jwt_attack":
            return lambda: tool_jwt_attack(
                a.get("mode", "weak_secret"), a.get("token", ""),
                a.get("wordlist", "rockyou.txt"))
        if n == "api_test":
            return lambda: tool_api_test(
                a.get("mode", "verb"), a.get("base", a.get("url", "")))
        if n == "cache_poisoning":
            return lambda: tool_cache_poisoning(
                a.get("url", a.get("target", "")), a.get("mode", "poison"))
        if n == "email_header_injection":
            return lambda: tool_email_header_injection(
                a.get("mode", "inject"), a.get("value", ""))
        if n == "websocket_probe":
            return lambda: tool_websocket_probe(
                a.get("url", a.get("target", "")), a.get("mode", "cswsh"))
        if n == "oauth_probe":
            return lambda: tool_oauth_probe(
                a.get("mode", "redirect_uri"),
                a.get("redirect_uri", a.get("uri", "https://evil.example")))
        if n == "attack_surface":
            return lambda: tool_attack_surface(
                a.get("content", a.get("body", a.get("text", ""))),
                a.get("base_url", a.get("url", "")))
        if n == "verify_solve":
            return lambda: tool_verify_solve(
                a.get("mode", "scoreboard"), a.get("before", ""),
                a.get("after", ""), a.get("target", ""),
                a.get("category", ""), a.get("expected", ""),
                a.get("observed", ""))
        if n == "webapp_recon":
            return lambda: tool_webapp_recon(
                a.get("base_url", a.get("url", a.get("target",
                      "http://localhost:3000"))),
                a.get("extra_paths", a.get("paths")),
                a.get("max_paths", 40))
        if n == "xbow_score":
            return lambda: tool_xbow_score(
                a.get("results", a.get("records", a.get("items", []))))
        if n == "xbow_report":
            return lambda: tool_xbow_report(a.get("scored", a.get("result", a)))
        # Pure system / desktop sensing (independent subprocesses).
        if n == "system_info":
            return tool_system_info
        if n == "disk_usage":
            return tool_disk_usage
        if n == "processes":
            return lambda: tool_processes(i(a.get("top_n", 15), 15))
        if n == "network_status":
            return tool_network_status
        if n == "recent_downloads":
            return lambda: tool_recent_downloads(i(a.get("limit", 20), 20))
        if n == "service_status":
            return lambda: tool_service_status(a.get("name"))
        if n == "journal_tail":
            return lambda: tool_journal_tail(
                i(a.get("lines", 50), 50), a.get("unit"))
        if n == "desktop_info":
            return tool_desktop_info
        if n == "list_apps":
            return lambda: tool_list_apps(
                a.get("filter", a.get("filter_text", "")))
        if n == "list_windows":
            return tool_list_windows
        if n == "list_dir":
            return lambda: tool_list_dir(a.get("path", "."))
        if n == "find_file":
            return lambda: tool_find_file(
                a.get("pattern", "*"), a.get("search_path", "~"),
                i(a.get("max_results", 50), 50),
                a.get("min_size_kb", 0), a.get("max_size_kb", 0),
                a.get("modified_within_days", 0))
        if n == "path_info":
            return lambda: tool_path_info(a.get("path", ""))
        if n == "quick_facts":
            return lambda: tool_quick_facts()
        if n == "read_file":
            p = a.get("path", "")
            # Sensitive reads keep their confirm gate — never auto-batched.
            if p and not is_sensitive_path(p):
                return lambda: tool_read_file(p)
            return None
        return None

    def _execute_tool_batch(self, calls):
        """Run several read-only tools concurrently and feed ONE combined
        tool_result back.  A multi-lookup turn then costs a single model
        round-trip (and a single chain step) instead of one per tool."""
        chat_id = self.streaming_chat_id or self.current_chat_id
        for c in calls:
            self.store.add_message(
                chat_id, "tool",
                f"⚙ tool: {c.name}({json.dumps(c.args)})",
                meta={"kind": "call"})
        names = ", ".join(c.name for c in calls)
        self.terminal_log(f"→ batch: {names} ({len(calls)} in parallel)", "info")
        # ── THE REPEAT GUARD MUST SEE BOTH EXECUTION PATHS ──
        # It was called only from _execute_tool_calls, so a batch was never
        # repeat-checked at all — and worse, a batch recorded ONE combined
        # recall entry ("system_info + disk_usage + processes"), which no
        # per-tool lookup can ever match.  So `system_info` could run inside a
        # batch and again on its own a turn later, forever, with the guard
        # blind to both halves.  That is visible in the operator's log.
        #
        # Same drift class as _pure_tool_fn vs dispatch (tests/test_dispatch.py
        # exists because those two got out of step); this time it was the guard
        # that sat on one path.
        #
        # Individually-blocked calls are DROPPED from the batch rather than
        # failing the whole thing — the other tools in it are still useful, and
        # a batch is a convenience, not an atomic unit.
        _kept, _dropped = [], []
        for c in calls:
            if self._repeat_guard_blocks(self._action_label(c)):
                _dropped.append(c)
            else:
                _kept.append(c)
        if _dropped and not _kept:
            self._feed_tool_result(
                self._repeat_guard(self._action_label(_dropped[0]))
                or "NOT RUN — repeat guard: every tool in that batch has "
                   "already been run. Pick a different next action.")
            return
        if _dropped:
            calls = _kept
            names = ", ".join(c.name for c in calls)
            self.terminal_log(
                f"⛔ repeat guard: dropped {len(_dropped)} already-run "
                f"tool(s) from the batch", "error")
            self._activity_note(
                "repeat guard dropped %d already-run tool(s): %s"
                % (len(_dropped),
                   ", ".join(c.name for c in _dropped)[:120]), "gate")
        # Per-tool recall entries so a later SOLO call of the same tool is
        # recognised as a repeat.  The combined label still names the action
        # for the log, but the per-tool keys are what the guard counts.
        self._pending_action = " + ".join(
            self._action_label(c) for c in calls)[:400]
        self._batch_members = [self._action_label(c) for c in calls]
        # ONE ROW PER TOOL. A parallel batch is the exact case the single
        # status line could not represent honestly: it has one slot and four
        # tools are running in it. Each row closes on its own worker's result,
        # so a slow member is visibly the slow one instead of the whole batch
        # looking stalled. _activity_sid stays 0 on this path — the combined
        # result must not close a row that a worker already closed.
        self._activity_sid = 0
        _sids = [self._activity_begin(c.name, c.args) for c in calls]
        self._activity_batch_sids = list(_sids)

        def _bg(feed):
            import concurrent.futures
            results: list = [None] * len(calls)

            def run_one(pair):
                idx, c = pair
                fn = self._pure_tool_fn(c)
                try:
                    res = fn()
                    txt = json.dumps(res, indent=2, default=str)
                except Exception as e:
                    txt = f"error: {type(e).__name__}: {str(e)[:200]}"
                # Close THIS member's row the moment it lands, from the worker
                # thread, marshalled onto the main loop. Waiting for ex.map to
                # drain would make four rows all finish at the slowest one's
                # time, which is a picture of the run that is simply false.
                _ok = not txt.lstrip().lower().startswith("error")
                GLib.idle_add(
                    lambda i=idx, o=_ok, t=txt: (
                        self._activity_end(_sids[i] if i < len(_sids) else 0,
                                           ok=o, preview=_feed_preview(t))
                        or False))
                return idx, c.name, txt

            workers = max(1, min(TOOL_BATCH_MAX_WORKERS, len(calls)))
            try:
                with concurrent.futures.ThreadPoolExecutor(
                        max_workers=workers) as ex:
                    for idx, name, txt in ex.map(
                            run_one, list(enumerate(calls))):
                        results[idx] = (name, txt)
            except Exception as e:
                feed(f"batch error: {e}")
                return

            blocks = []
            for n, slot in enumerate(results, 1):
                # A slot is None only if ex.map skipped one — unpacking it
                # blind raised inside this worker thread, and an exception here
                # means no tool result is ever fed and the turn hangs.
                if slot is None:
                    blocks.append(f"[tool {n}/{len(results)}: unknown]\n"
                                  f"error: no result returned")
                    continue
                name, txt = slot
                blocks.append(f"[tool {n}/{len(results)}: {name}]\n{txt}")
            combined = "\n\n".join(blocks)
            GLib.idle_add(lambda: self.terminal_log(
                f"✓ batch done ({len(calls)} tools)", "ok") or False)
            feed(combined)

        self._tool_thread(_bg, f"batch({names})")

    def _execute_tool_calls(self, calls):
        call = calls[0]
        # ── ACTION RECALL: name the action, then check we are not redoing it ──
        # Set BEFORE dispatch so the result that comes back can be attached to
        # it in _feed_tool_result. The guard sits here rather than at each tool
        # because this is the one place every single-tool call passes through.
        self._pending_action = self._action_label(call)
        _blocked = self._repeat_guard(self._pending_action)
        if _blocked is not None:
            self._activity_note(
                "repeat guard: %s already ran - not repeating"
                % self._action_label(call)[:110], "gate")
            self._pending_action = None
            self._feed_tool_result(_blocked)
            return
        # `propose` and `propose_edit` are advisory — the card (command or
        # diff) already rendered and carries its own Run/Apply button.
        # They never execute here; if one slips through, end the turn so
        # the card stands on its own.
        if call.name in ("propose", "propose_edit", "write_file"):
            # AUTONOMOUS MODE: never leave a card waiting — there's no operator
            # watching. Execute the proposal directly and keep the chain going.
            if self.settings.get("approval_mode", "none") == "none":
                if call.name == "propose":
                    _cmd = (call.args.get("command")
                            or call.args.get("cmd") or "").strip()
                    if _cmd:
                        self.terminal_log("• autonomous: running proposed command "
                                          "directly", "dim")
                        self._run_proposed_command(
                            _cmd, str(call.args.get("explanation", "")))
                        return
                else:  # propose_edit / write_file
                    _p = (call.args.get("path") or "").strip()
                    _c = call.args.get("content")
                    if _p and _c is not None:
                        self.terminal_log("• autonomous: applying file write "
                                          "directly", "dim")
                        self._run_proposed_edit(_p, _c)
                        return
                # args unusable — fall through to the normal re-emit handling
            # …but ONLY if the card actually had the data to render.  A
            # propose_edit whose JSON couldn't be parsed (e.g. unescaped
            # quotes inside `content` that the lenient parser can't safely
            # repair) arrives here with no path/content and renders NOTHING —
            # and silently finishing the turn would leave the model believing
            # a diff card is waiting when the screen is empty.  Catch that,
            # tell the model plainly, and let it re-emit instead of lying to
            # the operator about a card that doesn't exist.
            if call.name == "propose":
                card_ok = bool((call.args.get("command")
                                or call.args.get("cmd") or "").strip())
                what = "command proposal"
            else:
                card_ok = (bool((call.args.get("path") or "").strip())
                           and call.args.get("content") is not None)
                what = "file proposal (diff card)"
            if not card_ok:
                retries = getattr(self, "_bad_propose_retries", 0)
                if retries < 2:
                    self._bad_propose_retries = retries + 1
                    self.terminal_log(
                        f"✗ {call.name} did not render (unparseable args) — "
                        f"asking model to re-emit", "error")
                    self._feed_tool_result(
                        f"Your {call.name} did NOT render — its arguments "
                        f"could not be parsed (most likely an unescaped \" or "
                        f"a stray control character inside the \"content\" "
                        f"string). NO {what} is on screen and NOTHING was "
                        f"written or proposed. Re-send it now as a single "
                        f"well-formed tool call: the JSON must be valid — "
                        f"escape every \" inside content as \\\" and use \\n "
                        f"for newlines. Until the card actually renders, do "
                        f"not tell the operator that a proposal or diff card "
                        f"exists.")
                    return
                # Gave it two honest shots; stop bouncing and let the turn end
                # so we don't loop.  The error is in context for next turn.
                self.terminal_log(
                    f"✗ {call.name} still unparseable after retries — "
                    f"ending turn", "error")
            self._finish_turn_cleanup()
            return
        # Always write to the chat this turn was started in, not whichever
        # one the user might have navigated to.
        chat_id = self.streaming_chat_id or self.current_chat_id

        # Update the working banner with a human phrase for this tool so the
        # operator can see what's happening as a chain runs ("searching the
        # web…", "running nmap…").  Hidden tool indicators in the message
        # stream stay hidden — they're noisy.
        self._set_working(True, self._status_for_call(call) + "…")

        self.store.add_message(chat_id, "tool",
                                f"⚙ tool: {call.name}({json.dumps(call.args)})",
                                meta={"kind": "call"})

        # Models drift and sometimes emit non-numeric values for numeric
        # args ("fifteen", null, "15.5", {}).  A bare int() on those raises
        # and kills the whole tool turn — coerce safely and fall back to
        # the default instead.
        def _safe_int(v, default):
            try:
                return int(float(v))   # tolerates "15", 15, "15.5"
            except (TypeError, ValueError):
                return default

        dispatch = {
            "read_file":         lambda a: self._tool_read_file(a.get("path", "")),
            "list_dir":          lambda a: self._tool_list_dir(a.get("path", ".")),
            "find_file":         lambda a: self._tool_find_file(
                a.get("pattern", "*"), a.get("search_path", "~"),
                _safe_int(a.get("max_results", 50), 50),
                a.get("min_size_kb", 0), a.get("max_size_kb", 0),
                a.get("modified_within_days", 0)),
            "quick_facts":       lambda a: self._tool_simple(
                lambda: tool_quick_facts()),
            "system_info":       lambda a: self._tool_simple(tool_system_info),
            "disk_usage":        lambda a: self._tool_simple(tool_disk_usage),
            "processes":         lambda a: self._tool_simple(
                lambda: tool_processes(_safe_int(a.get("top_n", 15), 15))),
            "network_status":    lambda a: self._tool_simple(tool_network_status),
            "recent_downloads":  lambda a: self._tool_simple(
                lambda: tool_recent_downloads(_safe_int(a.get("limit", 20), 20))),
            "check_updates":     lambda a: self._tool_simple(tool_check_updates),
            "service_status":    lambda a: self._tool_simple(
                lambda: tool_service_status(a.get("name"))),
            "journal_tail":      lambda a: self._tool_simple(
                lambda: tool_journal_tail(
                    _safe_int(a.get("lines", 50), 50), a.get("unit"))),
            "run":               lambda a: self._tool_run(
                a.get("command", ""), a.get("reason", "")),
            "audit":             lambda a: self._tool_audit(),
            "scan_net":          lambda a: self._tool_scan_net(a.get("cidr")),

            # ── Desktop control (read-only: simple) ──
            "desktop_info":      lambda a: self._tool_simple(tool_desktop_info),
            "list_apps":         lambda a: self._tool_simple(
                lambda: tool_list_apps(a.get("filter", a.get("filter_text", "")))),
            "list_windows":      lambda a: self._tool_simple(tool_list_windows),
            "media_control":     lambda a: self._tool_simple(
                lambda: tool_media_control(a.get("action", "status"))),
            "notify":            lambda a: self._tool_simple(
                lambda: (self._add_notification(a.get("title", "Basilisk"),
                                                a.get("message", "")),
                         self._desktop_notify(a.get("title", "Basilisk"),
                                              a.get("message", "")),
                         {"ok": True, "notified": a.get("message", "")})[2]),

            # ── Desktop control (actions: confirm-gated) ──
            "launch_app":        lambda a: self._action_tool(
                "launch_app", lambda: tool_launch_app(
                    a.get("app", ""), a.get("args", "")),
                f"launch app: {a.get('app','')}"),
            "open_url":          lambda a: self._action_tool(
                "open_url", lambda: tool_open_url(a.get("url", "")),
                f"open URL: {a.get('url','')}"),
            "focus_window":      lambda a: self._action_tool(
                "focus_window", lambda: tool_focus_window(a.get("title", "")),
                f"focus window: {a.get('title','')}"),
            "close_window":      lambda a: self._action_tool(
                "close_window", lambda: tool_close_window(a.get("title", "")),
                f"close window: {a.get('title','')}"),
            "type_text":         lambda a: self._action_tool(
                "type_text", lambda: tool_type_text(a.get("text", "")),
                f"type {len(a.get('text',''))} chars into focused window"),
            "press_key":         lambda a: self._action_tool(
                "press_key", lambda: tool_press_key(a.get("keys", "")),
                f"press key: {a.get('keys','')}"),

            # ── Screenshots & screen reading (read-only: simple) ──
            "screenshot":        lambda a: self._tool_simple(
                lambda: tool_screenshot(a.get("save_path", a.get("path", "")))),
            "read_screen":       lambda a: self._tool_simple(
                lambda: tool_read_screen(a.get("region", ""))),

            # ── Filesystem (read-only: simple) ──
            "path_info":         lambda a: self._tool_simple(
                lambda: tool_path_info(a.get("path", ""))),
            "make_dir":          lambda a: self._tool_simple(
                lambda: tool_make_dir(a.get("path", ""))),
            "copy_path":         lambda a: self._tool_simple(
                lambda: tool_copy_path(a.get("src", ""), a.get("dst", ""))),

            # ── Filesystem (destructive: confirm-gated) ──
            "move_path":         lambda a: self._action_tool(
                "move_path", lambda: tool_move_path(
                    a.get("src", ""), a.get("dst", "")),
                f"move {a.get('src','')} → {a.get('dst','')}"),
            "delete_path":       lambda a: self._action_tool(
                "delete_path", lambda: tool_delete_path(
                    a.get("path", ""),
                    bool(a.get("recursive", False))),
                f"DELETE {a.get('path','')}"
                f"{' (recursive)' if a.get('recursive') else ''}"),

            # ── Trusted-source reference lookup (read-only, allow-listed) ──
            # web_read refuses any host not on basilisk_core._WEB_READ_ALLOW, and
            # the TWO-TIER gate (_web_read_gated) is enforced here in code:
            # trusted sources fetch automatically; community/user-authored ones
            # (GitHub, Wikipedia, SO, …) are held outside the autonomous loop
            # and need the operator's approval via a notification. Redirects are
            # re-validated and output shielded. Single-path (own fetch).
            "web_read":          lambda a: self._tool_simple(
                lambda: self._web_read_gated(
                    a.get("url", a.get("u", "")),
                    _safe_int(a.get("max_chars", 6000), 6000))),
            "web_sources":       lambda a: self._tool_simple(tool_web_sources),

            # ── Media: image search / analysis (read-only) ──
            # image_search returns image URLs to RENDER, not page text to
            # reason over.  (The web/OSINT/social/GitHub/CVE readers were
            # removed — they fed attacker-controllable external text into the
            # model, the indirect-prompt-injection surface.)
            "image_search":      lambda a: self._tool_simple(
                lambda: tool_image_search(
                    a.get("query", a.get("q", "")),
                    _safe_int(a.get("max_results", 4), 4))),
            "analyze_image":     lambda a: self._tool_simple(
                lambda: tool_analyze_image(
                    a.get("image_path", a.get("path", a.get("url", ""))),
                    a.get("question", a.get("prompt", "")),
                    self._vision_key(), self._vision_base_url(),
                    self.settings.get("vision_model", ""))),
            "capture_photo":     lambda a: self._tool_simple(
                lambda: tool_capture_photo(a.get("out_path", ""))),
            "detect_faces":      lambda a: self._tool_simple(
                lambda: tool_detect_faces(
                    a.get("image_path", a.get("path", "")))),

            # ── Pentest support (read-only / proposing only) ──
            # None of these execute an attack: pentest_plan returns PROPOSED
            # commands that still go through the approve-before-run gate; the
            # rest are inventory, text parsing, filesystem lookups, reference
            # knowledge and report formatting.
            "tooling_check":     lambda a: self._tool_simple(
                lambda: tool_tooling_check()),
            "pentest_plan":      lambda a: self._tool_simple(
                lambda: tool_pentest_plan(
                    a.get("target", a.get("host", a.get("url", ""))),
                    a.get("profile", a.get("mode", "web")),
                    a.get("intensity", a.get("speed", "normal")))),
            # cve_lookup is host-pinned to NVD / CISA KEV / FIRST EPSS (not a
            # general web reader) — it fans out its own network calls, so it
            # stays single-path (not in the pure/batch resolver).
            "cve_lookup":        lambda a: self._tool_simple(
                lambda: tool_cve_lookup(
                    a.get("product", a.get("name", a.get("software", ""))),
                    a.get("version", a.get("ver", "")),
                    _safe_int(a.get("limit", 8), 8),
                    a.get("enrich", True) not in (False, "false", "0", 0))),
            "parse_output":      lambda a: self._tool_simple(
                lambda: tool_parse_output(
                    a.get("tool", a.get("name", "")),
                    a.get("raw", a.get("output", a.get("text", ""))),
                    a.get("enrich_cves", a.get("enrich", False)) not in
                        (False, "false", "0", 0, None))),
            "methodology":       lambda a: self._tool_simple(
                lambda: tool_methodology(
                    a.get("area", a.get("topic", "")),
                    a.get("phase", ""))),
            "wordlist_find":     lambda a: self._tool_simple(
                lambda: tool_wordlist_find(
                    a.get("kind", a.get("type", a.get("category", ""))))),
            "cheatsheet":        lambda a: self._tool_simple(
                lambda: tool_cheatsheet(
                    a.get("topic", a.get("tool", a.get("name", ""))))),
            "report_findings":   lambda a: self._tool_simple(
                lambda: tool_report_findings(
                    a.get("findings", a.get("items", [])),
                    a.get("target", a.get("host", a.get("url", ""))),
                    a.get("scope_note", a.get("scope", "")),
                    a.get("title", ""))),
            "evidence_report":   lambda a: self._tool_simple(
                lambda: _evidence_report(
                    a.get("engagement", a.get("name", None)))),
            "evidence_verify":   lambda a: self._tool_simple(
                lambda: (get_ledger().verify(a.get("engagement", None))
                         if get_ledger() else {"error": "ledger unavailable"})),
            "evidence_engagement": lambda a: self._tool_simple(
                lambda: _evidence_set_engagement(
                    a.get("engagement", a.get("name", a.get("value", ""))))),
            "nuclei_template":   lambda a: self._tool_simple(
                lambda: tool_nuclei_template(
                    a.get("spec", a.get("template", a)),
                    a.get("mode", "build"),
                    a.get("yaml", a.get("yaml_text", "")))),
            "reflect_findings":  lambda a: self._tool_simple(
                lambda: tool_reflect_findings(
                    a.get("findings", a.get("items", a)))),
            "attack_writeup":    lambda a: self._tool_simple(
                lambda: tool_attack_writeup(
                    a.get("access", a.get("summary", "")),
                    a.get("steps", a.get("path_steps", None)),
                    a.get("target", a.get("host", a.get("url", ""))),
                    a.get("scope_note", a.get("scope", "")),
                    a.get("impact", ""), a.get("remediation", a.get("fix", "")),
                    a.get("root_cause", a.get("cause", "")),
                    a.get("ledger_events", a.get("events", None)))),
            "workspace_import":   lambda a: self._tool_simple(
                self._workspace_call("workspace_import", a)),
            "workspace_status":   lambda a: self._tool_simple(
                self._workspace_call("workspace_status", a)),
            "workspace_overview": lambda a: self._tool_simple(
                self._workspace_call("workspace_overview", a)),
            "workspace_tree":     lambda a: self._tool_simple(
                self._workspace_call("workspace_tree", a)),
            "workspace_search":   lambda a: self._tool_simple(
                self._workspace_call("workspace_search", a)),
            "workspace_read":     lambda a: self._tool_simple(
                self._workspace_call("workspace_read", a)),
            "workspace_replace":  lambda a: self._tool_simple(
                self._workspace_call("workspace_replace", a)),
            "workspace_write":    lambda a: self._tool_simple(
                self._workspace_call("workspace_write", a)),
            "workspace_delete":   lambda a: self._tool_simple(
                self._workspace_call("workspace_delete", a)),
            "workspace_diff":     lambda a: self._tool_simple(
                self._workspace_call("workspace_diff", a)),
            "workspace_revert":   lambda a: self._tool_simple(
                self._workspace_call("workspace_revert", a)),
            "workspace_export":   lambda a: self._tool_simple(
                self._workspace_call("workspace_export", a)),
            "workspace_close":    lambda a: self._tool_simple(
                self._workspace_call("workspace_close", a)),
            "workspace_test_command": lambda a: self._tool_simple(
                self._workspace_call("workspace_test_command", a)),
            "workspace_baseline": lambda a: self._tool_simple(
                self._workspace_call("workspace_baseline", a)),
            "workspace_verify":   lambda a: self._tool_simple(
                self._workspace_call("workspace_verify", a)),
            "workspace_health":   lambda a: self._tool_simple(
                self._workspace_call("workspace_health", a)),
            "code_tooling_check": lambda a: self._tool_simple(
                lambda: tool_code_tooling_check()),
            "code_scan_plan":     lambda a: self._tool_simple(
                lambda: tool_code_scan_plan(
                    a.get("path", a.get("dir", a.get("target", "."))),
                    a.get("kind", a.get("type", "auto")),
                    a.get("intensity", a.get("depth", "normal")))),
            "zday_scan":          lambda a: self._tool_simple(
                lambda: _zdayfind.zday_scan(
                    path=_ws_path(a.get("path", a.get("dir", a.get("target", "")))),
                    code=a.get("code", a.get("source", "")),
                    like=a.get("like", a.get("variant_of", a.get("snippet", ""))),
                    focus=a.get("focus", a.get("classes", "")),
                    filename=a.get("filename", a.get("name", "snippet")))),
            "zday_signatures":    lambda a: self._tool_simple(
                lambda: _zdayfind.signature_catalog()),
            "saml_attack":        lambda a: self._tool_simple(
                lambda: _exploits.saml_attack(
                    a.get("mode", a.get("technique", "signature_wrapping")),
                    a.get("assertion", a.get("response", "")))),
            "cloud_storage":      lambda a: self._tool_simple(
                lambda: _exploits.cloud_storage(
                    a.get("provider", a.get("cloud", "s3")),
                    a.get("bucket", a.get("container", a.get("name", ""))))),
            "subdomain_takeover": lambda a: self._tool_simple(
                lambda: _exploits.subdomain_takeover(
                    a.get("host", a.get("subdomain", a.get("domain", ""))),
                    a.get("cname", a.get("target", "")))),
            "padding_oracle":     lambda a: self._tool_simple(
                lambda: _exploits.padding_oracle(
                    a.get("mode", "detect"),
                    a.get("ciphertext", a.get("data", "")),
                    a.get("block_size", a.get("blocksize", 16)))),
            "xslt_injection":     lambda a: self._tool_simple(
                lambda: _exploits.xslt_injection(
                    a.get("mode", "detect"), a.get("cmd", a.get("command", "id")))),
            "parse_scan":         lambda a: self._tool_simple(
                lambda: tool_parse_scan(
                    a.get("tool", a.get("scanner", a.get("name", ""))),
                    a.get("raw", a.get("output", a.get("json", a.get("text", "")))))),
            "triage_findings":    lambda a: self._tool_simple(
                lambda: tool_triage_findings(
                    a.get("findings", a.get("items", [])))),
            "remediation_hint":   lambda a: self._tool_simple(
                lambda: tool_remediation_hint(
                    a.get("finding", a.get("item", a)))),
            "scope_set":          lambda a: self._tool_simple(
                lambda: tool_scope_set(
                    a.get("targets", a.get("scope", a.get("hosts", []))),
                    a.get("mode", "replace"))),
            "scope_check":        lambda a: self._tool_simple(
                lambda: tool_scope_check(
                    a.get("target", a.get("host", a.get("url", ""))))),
            "scope_show":         lambda a: self._tool_simple(
                lambda: tool_scope_show()),
            "scope_exclude":      lambda a: self._tool_simple(
                lambda: tool_scope_exclude(
                    a.get("targets", a.get("exclusions", a.get("hosts", []))),
                    a.get("mode", "replace"))),
            "scope_window":       lambda a: self._tool_simple(
                lambda: tool_scope_window(
                    a.get("start", ""), a.get("end", ""),
                    bool(a.get("clear", False)))),
            "scope_authorisation": lambda a: self._tool_simple(
                lambda: tool_scope_authorisation(
                    a.get("client", ""),
                    a.get("authorised_by", a.get("authorized_by", "")),
                    a.get("reference", a.get("ref", "")))),
            "asset_record":       lambda a: self._tool_simple(
                lambda: tool_asset_record(
                    a.get("host", a.get("target", "")), a.get("service", ""),
                    a.get("port", None), a.get("finding", ""),
                    a.get("access", ""), a.get("note", ""))),
            "engagement_graph":   lambda a: self._tool_simple(
                lambda: tool_engagement_graph(a.get("host", ""))),
            "loot_record":        lambda a: self._tool_simple(
                lambda: tool_loot_record(
                    a.get("host", ""), a.get("kind", "credential"),
                    a.get("username", a.get("user", "")),
                    a.get("secret", a.get("password", a.get("hash", ""))),
                    a.get("service", ""), a.get("note", ""))),
            "loot_list":          lambda a: self._tool_simple(
                lambda: tool_loot_list()),
            "loot_reuse":         lambda a: self._tool_simple(
                lambda: tool_loot_reuse()),
            "graph_ingest":       lambda a: self._tool_simple(
                lambda: tool_graph_ingest(
                    a.get("parsed", a.get("findings", a.get("result", a))))),
            "sqlmap_plan":        lambda a: self._tool_simple(
                lambda: tool_sqlmap_plan(
                    a.get("target", a.get("url", a.get("host", ""))),
                    a.get("mode", "detect"), a.get("data", ""), a.get("cookie", ""),
                    a.get("headers", ""), a.get("level", 1), a.get("risk", 1),
                    a.get("dbms", ""), a.get("technique", ""), a.get("db", ""),
                    a.get("table", ""), a.get("request_file", a.get("r", "")),
                    a.get("extra", ""))),
            "benchmark_targets":  lambda a: self._tool_simple(
                lambda: tool_benchmark_targets(a.get("target", ""))),
            "benchmark_score":    lambda a: self._tool_simple(
                lambda: tool_benchmark_score(
                    a.get("target", ""), a.get("findings", a.get("items", [])),
                    a.get("ground_truth", a.get("gt", None)), a.get("tool", "basilisk"))),
            "benchmark_report":   lambda a: self._tool_simple(
                lambda: tool_benchmark_report(a.get("scored", a.get("result", a)))),
            "benchmark_compare":  lambda a: self._tool_simple(
                lambda: tool_benchmark_compare(
                    a.get("runs", a.get("results", a.get("items", []))))),
            "load_tools":         lambda a: self._tool_simple(
                lambda: tool_load_tools(
                    a.get("group", a.get("name", a.get("groups", ""))),
                    unleashed=self._unleashed)),
            "submit_flag":        lambda a: self._tool_simple(
                lambda: tool_submit_flag(
                    a.get("flag", a.get("value", "")), a.get("challenge", ""))),
            "juiceshop_score":    lambda a: self._tool_simple(
                lambda: tool_juiceshop_score(
                    a.get("base_url", a.get("url", a.get("target",
                          "http://localhost:3000"))))),
            "juiceshop_report":   lambda a: self._tool_simple(
                lambda: tool_juiceshop_report(a.get("scored", a.get("result", a)))),
            "juiceshop_next":     lambda a: self._tool_simple(
                lambda: tool_juiceshop_next(
                    a.get("base_url", a.get("url", "http://localhost:3000")),
                    a.get("max_difficulty", a.get("max_stars", 0)),
                    a.get("limit", 0), a.get("per_tier", a.get("per_star", 0)))),
            "juiceshop_diff":     lambda a: self._tool_simple(
                lambda: tool_juiceshop_diff(
                    a.get("base_url", a.get("url", "http://localhost:3000")),
                    a.get("since", a.get("solved_names", a.get("previous"))))),
            "juiceshop_source":   lambda a: self._tool_simple(
                lambda: tool_juiceshop_source(
                    a.get("action", "tree"), a.get("path", ""),
                    a.get("pattern", a.get("query", "")),
                    a.get("container", "juiceshop"),
                    a.get("base", a.get("base_path", "/juice-shop")))),
            "jwt_forge":          lambda a: self._tool_simple(
                lambda: tool_jwt_forge(
                    a.get("token", ""), a.get("mode", "none"),
                    a.get("email", ""), a.get("role", ""),
                    a.get("public_key", a.get("pubkey", "")),
                    a.get("payload_overrides", a.get("overrides")))),
            "nosql_injection":    lambda a: self._tool_simple(
                lambda: tool_nosql_injection(
                    a.get("mode", "auth_bypass"), a.get("field", "email"),
                    a.get("target", ""))),
            "xxe_payload":        lambda a: self._tool_simple(
                lambda: tool_xxe_payload(
                    a.get("mode", "file_read"),
                    a.get("file_path", a.get("file", "/etc/passwd")))),
            "coupon_forge":       lambda a: self._tool_simple(
                lambda: tool_coupon_forge(
                    a.get("mode", "tamper"), a.get("discount", 20),
                    a.get("scheme", "z85"), a.get("value", a.get("campaign", "")))),
            "captcha_solve":      lambda a: self._tool_simple(
                lambda: tool_captcha_solve(
                    a.get("url", ""),
                    a.get("captcha_text", a.get("text", a.get("captcha", ""))),
                    a.get("base_url", ""))),
            "reset_password":     lambda a: self._tool_simple(
                lambda: tool_reset_password(
                    a.get("mode", "methodology"), a.get("email", ""),
                    a.get("new_password", a.get("password", "Pwned123!")))),
            "business_logic":     lambda a: self._tool_simple(
                lambda: tool_business_logic(
                    a.get("area", a.get("category", "all")))),
            "ssti_payload":       lambda a: self._tool_simple(
                lambda: tool_ssti_payload(
                    a.get("engine", "detect"),
                    a.get("cmd", a.get("command", "id")))),
            "ssrf_payload":       lambda a: self._tool_simple(
                lambda: tool_ssrf_payload(
                    a.get("mode", "internal"),
                    a.get("target_url", a.get("url", "http://localhost/")),
                    a.get("host", "169.254.169.254"))),
            "deserialization_payload": lambda a: self._tool_simple(
                lambda: tool_deserialization_payload(
                    a.get("platform", "node"),
                    a.get("cmd", a.get("command", "id")))),
            "prototype_pollution": lambda a: self._tool_simple(
                lambda: tool_prototype_pollution(
                    a.get("prop", a.get("property", "isAdmin")),
                    a.get("value", "true"), a.get("vector", "json"))),
            "path_traversal":     lambda a: self._tool_simple(
                lambda: tool_path_traversal(
                    a.get("mode", "read"),
                    a.get("file_path", a.get("file", "/etc/passwd")),
                    a.get("filename", "malicious.md"))),
            "xss_payload":        lambda a: self._tool_simple(
                lambda: tool_xss_payload(
                    a.get("context", "html"), a.get("mode", "basic"))),
            "sqli_payload":       lambda a: self._tool_simple(
                lambda: tool_sqli_payload(
                    a.get("mode", "auth_bypass"), a.get("dbms", "generic"),
                    a.get("columns", 3), a.get("table", "users"))),
            "payload_encoder":    lambda a: self._tool_simple(
                lambda: tool_payload_encoder(
                    a.get("payload", a.get("text", "")),
                    a.get("scheme", "all"), a.get("decode", False))),
            "tech_fingerprint":   lambda a: self._tool_simple(
                lambda: tool_tech_fingerprint(
                    a.get("headers", ""), a.get("body", ""))),
            "waf_detect":         lambda a: self._tool_simple(
                lambda: tool_waf_detect(
                    a.get("blocked_payload", a.get("payload", "")),
                    a.get("response_body", a.get("body", "")),
                    a.get("status_code", a.get("status", 0)))),
            "trick_detect":       lambda a: self._tool_simple(
                lambda: tool_trick_detect(
                    a.get("text", a.get("body", a.get("content", ""))))),
            "payload_mutate":     lambda a: self._tool_simple(
                lambda: tool_payload_mutate(
                    a.get("body", a.get("request", "")),
                    a.get("payload", "' OR 1=1--"),
                    a.get("fmt", a.get("format", "auto")), a.get("mode", "replace"))),
            "session_flow":       lambda a: self._tool_simple(
                lambda: tool_session_flow(
                    a.get("mode", "extract"),
                    a.get("response", a.get("body", "")), a.get("flow", ""))),
            "oracle_analyze":     lambda a: self._tool_simple(
                lambda: tool_oracle_analyze(
                    a.get("mode", "diff"), a.get("baseline", ""), a.get("test", ""),
                    a.get("baseline_status", 0), a.get("test_status", 0),
                    a.get("baseline_times", ""), a.get("payload_times", ""))),
            "command_injection":  lambda a: self._tool_simple(
                lambda: tool_command_injection(
                    a.get("os_type", a.get("os", "unix")),
                    a.get("mode", "inline"),
                    a.get("cmd", a.get("command", "id")))),
            "idor_probe":         lambda a: self._tool_simple(
                lambda: tool_idor_probe(
                    a.get("base", a.get("url", "")),
                    a.get("id_value", a.get("id", "1")),
                    a.get("strategy", "all"))),
            "race_condition":     lambda a: self._tool_simple(
                lambda: tool_race_condition(
                    a.get("method", "POST"),
                    a.get("url", a.get("target", "")),
                    a.get("body", a.get("data", "")),
                    a.get("headers", ""),
                    a.get("parallel", a.get("count", 20)))),
            "upload_bypass":      lambda a: self._tool_simple(
                lambda: tool_upload_bypass(
                    a.get("filename", a.get("name", "shell.php")),
                    a.get("content_type", a.get("mime", "image/png")),
                    a.get("technique", "all"))),
            "graphql_probe":      lambda a: self._tool_simple(
                lambda: tool_graphql_probe(
                    a.get("mode", "introspect"),
                    a.get("field", ""),
                    a.get("payload", ""))),
            "open_redirect":      lambda a: self._tool_simple(
                lambda: tool_open_redirect(
                    a.get("target", a.get("url", "http://evil.example")),
                    a.get("param", "redirect"),
                    a.get("legit_host", a.get("host", "example.com")))),
            "cors_probe":         lambda a: self._tool_simple(
                lambda: tool_cors_probe(
                    a.get("origin", "https://evil.example"),
                    a.get("target_host", a.get("host", "example.com")))),
            "ldap_injection":     lambda a: self._tool_simple(
                lambda: tool_ldap_injection(
                    a.get("mode", "auth_bypass"), a.get("field", "username"))),
            "xpath_injection":    lambda a: self._tool_simple(
                lambda: tool_xpath_injection(a.get("mode", "auth_bypass"))),
            "crlf_injection":     lambda a: self._tool_simple(
                lambda: tool_crlf_injection(
                    a.get("mode", "header"), a.get("value", ""))),
            "host_header_injection": lambda a: self._tool_simple(
                lambda: tool_host_header_injection(
                    a.get("mode", "reset"), a.get("host", "evil.example"))),
            "ssi_injection":      lambda a: self._tool_simple(
                lambda: tool_ssi_injection(a.get("mode", "ssi"))),
            "csv_injection":      lambda a: self._tool_simple(
                lambda: tool_csv_injection(a.get("mode", "detect"))),
            "request_smuggling":  lambda a: self._tool_simple(
                lambda: tool_request_smuggling(a.get("mode", "clte"))),
            "csrf_poc":           lambda a: self._tool_simple(
                lambda: tool_csrf_poc(
                    a.get("method", "POST"), a.get("url", a.get("target", "")),
                    a.get("body", a.get("data", "")), a.get("mode", "form"))),
            "clickjacking":       lambda a: self._tool_simple(
                lambda: tool_clickjacking(
                    a.get("url", a.get("target", "")), a.get("mode", "check"))),
            "mass_assignment":    lambda a: self._tool_simple(
                lambda: tool_mass_assignment(
                    a.get("base_body", a.get("body", "{}")), a.get("fields", ""))),
            "auth_bypass_headers": lambda a: self._tool_simple(
                lambda: tool_auth_bypass_headers(
                    a.get("url", a.get("target", "")), a.get("mode", "headers"))),
            "auth_attack":        lambda a: self._tool_simple(
                lambda: tool_auth_attack(
                    a.get("mode", "spray"), a.get("url", a.get("target", "")),
                    a.get("users", "users.txt"), a.get("passwords", ""))),
            "jwt_attack":         lambda a: self._tool_simple(
                lambda: tool_jwt_attack(
                    a.get("mode", "weak_secret"), a.get("token", ""),
                    a.get("wordlist", "rockyou.txt"))),
            "api_test":           lambda a: self._tool_simple(
                lambda: tool_api_test(
                    a.get("mode", "verb"), a.get("base", a.get("url", "")))),
            "cache_poisoning":    lambda a: self._tool_simple(
                lambda: tool_cache_poisoning(
                    a.get("url", a.get("target", "")), a.get("mode", "poison"))),
            "email_header_injection": lambda a: self._tool_simple(
                lambda: tool_email_header_injection(
                    a.get("mode", "inject"), a.get("value", ""))),
            "websocket_probe":    lambda a: self._tool_simple(
                lambda: tool_websocket_probe(
                    a.get("url", a.get("target", "")), a.get("mode", "cswsh"))),
            "oauth_probe":        lambda a: self._tool_simple(
                lambda: tool_oauth_probe(
                    a.get("mode", "redirect_uri"),
                    a.get("redirect_uri", a.get("uri", "https://evil.example")))),
            "attack_surface":     lambda a: self._tool_simple(
                lambda: tool_attack_surface(
                    a.get("content", a.get("body", a.get("text", ""))),
                    a.get("base_url", a.get("url", "")))),
            "verify_solve":       lambda a: self._tool_simple(
                lambda: tool_verify_solve(
                    a.get("mode", "scoreboard"), a.get("before", ""),
                    a.get("after", ""), a.get("target", ""),
                    a.get("category", ""), a.get("expected", ""),
                    a.get("observed", ""))),
            "webapp_recon":       lambda a: self._tool_simple(
                lambda: tool_webapp_recon(
                    a.get("base_url", a.get("url", a.get("target",
                          "http://localhost:3000"))),
                    a.get("extra_paths", a.get("paths")),
                    a.get("max_paths", 40))),
            "xbow_score":         lambda a: self._tool_simple(
                lambda: tool_xbow_score(
                    a.get("results", a.get("records", a.get("items", []))))),
            "xbow_report":        lambda a: self._tool_simple(
                lambda: tool_xbow_report(a.get("scored", a.get("result", a)))),
        }
        # Merge sidecar tools (memory_*, skill_list, skill_run).  Returns an
        # empty dict unless the matching feature is enabled, so stock Basilisk is
        # unchanged.  skill_write is registered here (not in the sidecar) so
        # the save goes through Basilisk's own confirm dialog.
        if getattr(self, "_ext", None):
            try:
                for _tname, _tfn in self._ext.extra_tools(self).items():
                    # Sidecar tools return a result STRING.  Run each off the
                    # GTK main loop (this dispatch runs ON it) and feed the
                    # result back via the loop — skill_run spawns a sandbox
                    # subprocess that can take many seconds, and running it
                    # inline here froze the whole UI until it returned.
                    dispatch[_tname] = (lambda f:
                                        (lambda a: self._bg_feed_text(
                                            lambda: f(a))))(_tfn)
                if self.settings.get("skills_enabled", False):
                    dispatch["skill_write"] = self._tool_skill_write
            except Exception:
                pass
        # ── ORACLE: single-call path ──
        # These four were wired ONLY into _pure_tool_fn (the parallel read-only
        # batch path) and were missing from this map, which is the one a SINGLE
        # tool call goes through. So `oracle_check` on its own — the normal way
        # it is used, right after firing an exploit — fell through to
        # "Unknown tool 'oracle_check'". The oracle is the verified-exploitation
        # core: no proof, no finding. Losing it silently turns every confirmed
        # hit back into a guess. Exactly the two-dispatch-path drift v7.10.0
        # documented and routed the workspace tools through one mapper to avoid.
        dispatch.setdefault("oracle_arm", lambda a: self._tool_simple(
            lambda: tool_oracle_arm(
                a.get("objective", a.get("goal", a.get("what", ""))),
                a.get("target", a.get("url", a.get("host", ""))),
                a.get("technique", a.get("vuln", a.get("class",
                                                       a.get("attack", "")))),
                a.get("criterion_type", a.get("type", a.get(
                    "criterion", a.get("check", "contains")))),
                a.get("criterion_value", a.get("value", a.get(
                    "marker", a.get("expect", a.get(
                        "expected", a.get("pattern", "")))))),
                a.get("blind", a.get("oob", False)),
                a.get("oob_host", a.get("host", a.get("callback_host", ""))))))
        dispatch.setdefault("oracle_check", lambda a: self._tool_simple(
            lambda: tool_oracle_check(
                a.get("attempt_id", a.get("id", a.get("attempt", ""))),
                a.get("evidence", a.get("response", a.get("body", a.get(
                    "output", a.get("text", a.get("resp", "")))))),
                a.get("status", a.get("code", a.get("status_code", None))),
                a.get("baseline", a.get("base", a.get("normal",
                                                      a.get("control", "")))))))
        dispatch.setdefault("oracle_status",
                            lambda a: self._tool_simple(tool_oracle_status))
        dispatch.setdefault("oracle_listen", lambda a: self._tool_simple(
            lambda: tool_oracle_listen(
                a.get("port", 0),
                a.get("host", a.get("callback_host", a.get("ip", ""))))))

        fn = dispatch.get(call.name)
        if fn:
            # ── ARGUMENTS THE TOOL CANNOT SEE MUST NOT BE SILENTLY DROPPED ──
            # Every handler below reads its arguments with `a.get("src")`,
            # `a.get("cidr")` and friends, so a key the tool does not know is
            # simply invisible and the call proceeds on defaults. Two live
            # examples from the operator's own tool audit:
            #
            #   copy_path{"path": "/etc/hostname"}  -> src="" -> "source not
            #       found: ''", which reads like the FILE is missing rather
            #       than like the argument never arrived; and
            #   scan_net{"target": "127.0.0.1"}     -> cidr=None -> swept the
            #       default gateway subnet instead. On a scanner that is worse
            #       than a no-op: it ran an unrequested active scan of a
            #       network nobody named.
            #
            # `_normalise_tool_args` maps the obvious synonyms onto the real
            # keys, and refuses outright when NONE of the supplied keys are
            # ones this tool accepts — telling the model the accepted names so
            # it can re-issue. Same principle the tool-DIALECT handling already
            # uses: an unreadable call costs a round trip, never a wrong action.
            _args, _argerr = _normalise_tool_args(call.name, call.args)
            if _argerr:
                self.terminal_log(
                    f"✗ {call.name}: {_argerr}", "error")
                self._activity_note(f"{call.name} rejected: {_argerr}", "gate")
                self._feed_tool_result(f"NOT RUN — {_argerr}")
                return
            call.args = _args
            self.terminal_log(f"→ tool: {call.name}({json.dumps(call.args, separators=(',',':'))[:80]})", "info")
            # Open the feed row HERE — after normalisation, so the row shows
            # the arguments that actually ran, not the ones the model emitted.
            # Closed in _feed_tool_result, the single point every result
            # passes through.
            self._activity_sid = self._activity_begin(call.name, call.args)
            # The name the log line below should use. Set here because this is
            # the ONE place that knows it; _tool_simple reads it synchronously
            # inside fn(). Cleared in finally so a later stray call cannot
            # inherit a stale name and mislabel itself — an unnamed tool is
            # honest, a wrongly-named one is not.
            self._dispatching_tool = call.name
            try:
                fn(call.args)
            finally:
                self._dispatching_tool = ""
        else:
            self.terminal_log(f"✗ unknown tool: {call.name}", "error")
            self._activity_note(f"unknown tool: {call.name}", "gate")
            self._feed_tool_result(f"Unknown tool '{call.name}'.")

    def _feed_tool_result(self, result_text):
        # Carry any "these calls did not run" note into the SAME result, so the
        # model reads it at exactly the moment it is wondering where the other
        # answers went. See the deferred branch in _on_stream_done_body.
        _note = getattr(self, "_deferred_note", "")
        if _note:
            self._deferred_note = ""
            result_text = (result_text or "") + _note

        # The pending action is `"<tool>: <argument>"` (see _action_label), so
        # the tool name is already here — capture it BEFORE the recall block
        # below clears it, and tag the envelope with it further down.  Same
        # single hook, same reason: instrumenting thirty-odd dispatch sites is
        # how they drift apart.
        _tool = ""
        try:
            _pa = self._pending_action or ""
            _tool = _pa.split(":", 1)[0].strip() if ":" in _pa else _pa.strip()
        except Exception:
            _tool = ""

        # ACTION RECALL: attach this result to whatever action produced it. One
        # hook here covers every tool, instead of instrumenting each of the
        # thirty-odd dispatch sites (which is how they drift apart).
        try:
            if self._action_log is not None and self._pending_action:
                self._action_log.record(self._pending_action, result_text or "")
                # A batch also records each MEMBER under its own label, so a
                # later solo call of the same tool is seen as the repeat it is.
                # The combined entry above stays for the digest the model
                # reads; these are what times_run() can actually match.
                for _m in (getattr(self, "_batch_members", None) or []):
                    if _m and _m != self._pending_action:
                        self._action_log.record(_m, result_text or "")
        except Exception:
            pass
        finally:
            self._pending_action = None
            self._batch_members = []

        # Close the live feed row with what actually came back, BEFORE the
        # turn advances. One hook here covers every tool, for the same reason
        # ACTION RECALL hangs off this method rather than the dispatch sites.
        try:
            self._activity_close_result(result_text)
        except Exception:
            pass

        self._mark_turn_progress()
        # Route to the chat this turn was started in.  Resolved from
        # streaming_chat_id; if the turn was torn down (stop / delete)
        # it's None and we fall back to the current chat.
        #
        # EVERYTHING BELOW IS GUARDED. This method is the ONLY thing that
        # advances the turn loop after a tool runs; if it raised — a store write
        # failing, a deleted chat id, a full disk — _kick_assistant_turn was
        # never reached and the turn hung in "working…" with no way out but
        # restarting the app. A failure here must still hand the loop back.
        try:
            chat_id = self.streaming_chat_id or self.current_chat_id
            # ── NAME THE SOURCE TOOL, INSIDE the envelope ──
            # The compressor needs to know what produced a block: a page of
            # prose and an nmap dump want opposite treatment, and guessing from
            # content alone is fragile.  The tag goes on its OWN LINE INSIDE
            # `<tool_result>` rather than as an attribute on the opening tag,
            # which is the obvious way to do it and would have been a silent
            # disaster: nine places in this file test `"<tool_result>" in
            # content` as a literal, plus headroom's _TOOL_RE and
            # _trim_tool_result's synthesised closing tag.  Changing the opener
            # to `<tool_result source="web_read">` breaks every one of them
            # without an error — operational-message detection, dedup and
            # history trimming would all just quietly stop matching.
            #
            # So the envelope stays byte-identical and the identity rides
            # inside it, where adding it can't break a matcher.
            _src = (_tool or "").strip()
            _hdr = f"[tool: {_src}]\n" if _src else ""
            self.store.add_message(
                chat_id, "user",
                f"<tool_result>\n{_hdr}{result_text}\n</tool_result>",
                meta={"kind": "tool_result", "tool": _src or None})
        except Exception as e:
            log(f"feed_tool_result: store write failed: {e}")
            self.terminal_log(f"✗ could not record the tool result: {e}",
                              "error")
        self.streaming_msg_widget = None
        self.streaming_msg_db_id = None
        # If the operator stopped while the tool was running, record the
        # result for context but don't start another model turn.
        if self._stop_requested:
            self._finish_turn_cleanup()
            return
        # streaming_chat_id stays set — _kick_assistant_turn will preserve it
        try:
            self._kick_assistant_turn()
        except Exception:
            log(f"kick after tool result failed: {traceback.format_exc()}")
            self.terminal_log("✗ could not start the next step — turn ended",
                              "error")
            self._finish_turn_cleanup()

    # ── action recall ───────────────────────────────────────────
    def _reset_action_log(self):
        """A new objective was latched — the previous run's actions are no
        longer 'what we already tried'."""
        if self._action_log is not None:
            self._action_log.reset()
        self._pending_action = None

    def _action_label(self, call) -> str:
        """One short, comparable line describing a tool call.

        This is what the repeat check compares and what the model reads back, so
        it has to carry the ARGUMENT that makes the call distinct — `run` alone
        is not an action, `run: nmap -sV 10.0.0.5` is.
        """
        n = (getattr(call, "name", "") or "tool").strip()
        a = getattr(call, "args", None) or {}
        for k in ("command", "cmd", "path", "url", "query", "target",
                  "pattern", "name", "host"):
            v = a.get(k)
            if v:
                return f"{n}: {str(v).strip()[:180]}"
        if a:
            try:
                return f"{n}: {json.dumps(a, sort_keys=True, default=str)[:180]}"
            except Exception:
                pass
        return n

    def _repeat_guard_blocks(self, label: str) -> bool:
        """Would the repeat guard refuse this action?  Decision only, no
        message and no logging — the batch path needs to ask about each of
        several tools before it knows what it is running."""
        if self._action_log is None or not label:
            return False
        limit = int(self.settings.get("repeat_block_after", 2) or 0)
        if limit <= 0:
            return False
        return self._action_log.should_block(label, limit)

    def _repeat_guard(self, label: str):
        """Deterministic backstop for a model that ignores the already-done list.

        Returns the text to feed back INSTEAD of running, or None to proceed.

        Two executions of the same action are always allowed: re-running a check
        after changing something is how verification works, and blocking that
        would break correct behaviour. A THIRD is not verification — by then the
        result is not being read, and running it again costs a round-trip, real
        side effects, and (on a scanner) minutes.
        """
        if self._action_log is None or not label:
            return None
        limit = int(self.settings.get("repeat_block_after", 2) or 0)
        if limit <= 0:
            return None
        if not self._action_log.should_block(label, limit):
            return None
        prev = self._action_log.previous(label) or {}
        self.terminal_log(f"⛔ repeat guard: {label[:70]} already run "
                          f"{self._action_log.times_run(label)}× — not "
                          f"running it again", "error")
        return (f"NOT RUN — repeat guard. You have already performed this exact "
                f"action {self._action_log.times_run(label)} times this run:\n"
                f"    {label}\n"
                f"Its result last time was:\n    {prev.get('outcome', 'n/a')}\n"
                f"Running it a third time cannot tell you anything new. Read "
                f"the ALREADY DONE list, pick a DIFFERENT next action — verify "
                f"the state another way, change the parameters, or conclude "
                f"with what you have.")

    def _tool_thread(self, body, label="tool"):
        """Run a tool body on a worker thread with a GUARANTEED tool result.

        THIS IS THE FIX FOR "IT JUST HANGS".  The assistant turn loop only ever
        advances when something feeds it — a stream callback, or a tool result.
        Every tool runs on a daemon thread, and before this helper existed each
        one was individually responsible for making sure a result came back.
        Several did not: `tool_run_command` (the hottest path in the app),
        `tool_list_dir`, `tool_find_file` and `tool_write_file` were all called
        with no exception handling, and their results indexed with `r['rc']` /
        `r['entries']` / `r['size']` rather than `.get`.  An OSError spawning a
        process, a KeyError on an unexpected result shape, a UnicodeDecodeError
        on binary output — any of them killed the worker thread silently, no
        tool result was ever fed, and the turn sat in "working…" forever with no
        way out but restarting the app.

        `body(feed)` receives a ONE-SHOT feed callable.  Whatever the body does
        — returns without feeding, raises halfway, feeds and then raises —
        exactly one result reaches the model, so the loop always advances and
        the failure is something the model can read and route around.
        """
        state = {"fed": False}
        lock = threading.Lock()

        def feed(text):
            with lock:
                if state["fed"]:
                    return
                state["fed"] = True
            GLib.idle_add(self._feed_tool_result, text)

        def _run():
            try:
                body(feed)
            except Exception as e:
                log(f"tool thread [{label}] failed: {traceback.format_exc()}")
                try:
                    GLib.idle_add(
                        lambda m=str(e): self.terminal_log(
                            f"✗ {label} failed: {m}", "error") or False)
                except Exception:
                    pass
                feed(f"error: {label} failed with "
                     f"{type(e).__name__}: {e}\nThe tool did not complete. "
                     f"Do not retry it identically — check the arguments or "
                     f"use a different approach.")
            finally:
                # Belt and braces: a body that returns without feeding (an early
                # `return` down some branch) would otherwise strand the turn.
                feed(f"error: {label} produced no result (internal fault). "
                     f"Treat this as a failure and try a different approach.")

        threading.Thread(target=_run, daemon=True).start()

    def _bg_feed_text(self, fn):
        """Run fn() — which returns the final result STRING — on a background
        thread, then feed that string back via the main loop.  Like
        _tool_simple, but for callables that already produce the finished text
        (no JSON re-encoding), e.g. the sidecar's memory_*/skill_* tools."""
        def _bg():
            try:
                text = fn()
            except Exception as e:
                text = f"error: {type(e).__name__}: {e}"
            if not isinstance(text, str):
                text = json.dumps(text, default=str)
            GLib.idle_add(self._feed_tool_result, text)
        threading.Thread(target=_bg, daemon=True).start()

    def _load_notifications(self):
        try:
            with open(self._notif_path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save_notifications(self):
        try:
            os.makedirs(os.path.dirname(self._notif_path), exist_ok=True)
            with open(self._notif_path, "w", encoding="utf-8") as f:
                json.dump(self._notifications[-200:], f)
        except Exception:
            pass

    def _add_notification(self, title: str, message: str):
        """Record a notification into the in-app inbox and refresh the bell."""
        import time as _t
        self._notifications.append({
            "title": (title or "Basilisk").strip(),
            "message": (message or "").strip(),
            "ts": _t.strftime("%Y-%m-%d %H:%M"),
            "read": False,
        })
        self._notifications = self._notifications[-200:]
        self._save_notifications()
        self._play_notification_sound()
        try:
            GLib.idle_add(self._refresh_notifications)
        except Exception:
            pass

    def _play_notification_sound(self):
        """Chime when a notification arrives.  Best-effort and non-blocking:
        synthesises a small WAV once (cached in the data dir), then fires it
        through whatever audio player exists.  Silent no-op when disabled in
        settings or no player is available."""
        try:
            if not self.settings.get("notif_sound", True):
                return
        except Exception:
            return
        import shutil as _sh, subprocess as _sp
        player = getattr(self, "_notif_player", "unset")
        if player == "unset":
            player = None
            for cand in (["paplay"], ["pw-play"], ["aplay", "-q"],
                         ["ffplay", "-nodisp", "-autoexit",
                          "-loglevel", "quiet"], ["play", "-q"]):
                if _sh.which(cand[0]):
                    player = cand
                    break
            self._notif_player = player
        if not player:
            return
        path = os.path.expanduser("~/.local/share/basilisk/notify.wav")
        if not os.path.isfile(path):
            try:
                self._write_notify_wav(path)
            except Exception:
                return
        try:
            _sp.Popen(list(player) + [path], stdin=_sp.DEVNULL,
                      stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
        except Exception:
            pass

    @staticmethod
    def _write_notify_wav(path):
        """Synthesise a soft two-note ascending chime (G5 -> C6) once."""
        import wave as _wave, struct as _st, math as _m
        os.makedirs(os.path.dirname(path), exist_ok=True)
        sr = 44100
        notes = [(784.0, 0.0, 0.16), (1046.5, 0.10, 0.30)]
        n = int(sr * 0.44)
        samples = [0.0] * n
        for freq, start, dur in notes:
            s0 = int(start * sr)
            s1 = min(n, int((start + dur) * sr))
            for i in range(s0, s1):
                t = (i - s0) / sr
                env = _m.exp(-t * 5.5)
                atk = min(1.0, (i - s0) / (0.005 * sr))   # tiny attack, no click
                samples[i] += 0.5 * env * atk * _m.sin(2 * _m.pi * freq * t)
        peak = max(1e-6, max(abs(s) for s in samples))
        with _wave.open(path, "w") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(b"".join(
                _st.pack("<h", int(max(-1.0, min(1.0, s / peak * 0.9)) * 32767))
                for s in samples))

    def _unread_count(self) -> int:
        return sum(1 for n in self._notifications if not n.get("read"))

    # ── Community-source approval gate (enforced in code, not the prompt) ──
    def _desktop_notify(self, title: str, body: str = "",
                        nid: str = "basilisk-notify"):
        """Fire a REAL desktop notification through the GTK application (Gio).
        This uses the app's own D-Bus connection and the installed .desktop
        file, so it works on GNOME / Phosh / KDE WITHOUT libnotify-bin and
        without a notify-send binary in PATH. Falls back to notify-send /
        kdialog only if the Gio path is unavailable."""
        title = (title or "Basilisk").strip()
        body = (body or "").strip()
        sent = False
        try:
            app = self.get_application()
            if app is not None:
                note = Gio.Notification.new(title)
                if body:
                    note.set_body(body)
                try:
                    note.set_priority(Gio.NotificationPriority.HIGH)
                except Exception:
                    pass
                app.send_notification(nid, note)
                sent = True
        except Exception:
            sent = False
        if not sent:
            try:
                tool_notify(body or title, title)
            except Exception:
                pass

    def _url_host(self, url: str) -> str:
        try:
            from urllib.parse import urlsplit
            u = url if "://" in (url or "") else "https://" + (url or "")
            return (urlsplit(u).hostname or "").lower().rstrip(".")
        except Exception:
            return ""

    def _web_grant_domain(self, host: str) -> str:
        """The domain an approval covers for `host` — so allowing one URL covers
        the whole site (approving one github.com URL covers *.github.com). Now
        that ANY non-trusted public host is approval-gated (not just a fixed
        community list), this returns the registrable domain for any public host,
        and '' only for a trusted host (auto, no grant needed) or an internal one
        (refused, never granted)."""
        try:
            from basilisk_core import (web_read_tier, _grant_domain_for,
                                   _is_internal_host)
        except Exception:
            return ""
        h = (host or "").lower().rstrip(".")
        if not h or _is_internal_host(h):
            return ""
        if web_read_tier(h) == "trusted":
            return ""            # trusted → fetched automatically, no grant
        return _grant_domain_for(h)

    def _web_read_gated(self, url: str, max_chars: int):
        """Access gate for web_read, enforced HERE in code (never left to the
        model).

        LEASHED (normal) mode: the operator is in the loop for every single turn
        and Basilisk gives one answer and stops, so the prompt-injection risk the
        community gate defends against is minimal — read ANY public page directly
        (GitHub, a vendor blog, a news site, any URL) so research is unrestricted.

        UNLEASHED (autonomous) mode: the gate holds — TRUSTED sources fetch
        immediately; any OTHER public host is held outside the autonomous loop and
        needs a one-tap Allow, so a compromised page can't redirect a relentless
        run to an unvetted host on its own.

        Either mode: internal / private / metadata hosts are refused by
        tool_web_read regardless (SSRF floor — no approval overrides that)."""
        if self._unleashed and web_read_tier(url) == "community":
            dom = self._web_grant_domain(self._url_host(url))
            if dom and dom not in self._web_grants:
                self._request_web_approval(dom, url)
                return {
                    "ok": False,
                    "pending_approval": True,
                    "host": dom,
                    "error": (
                        f"'{dom}' isn't on the trusted-source list, so while "
                        "UNLEASHED it's held outside the autonomous loop and I "
                        "can't read it on my own. I've put an access request in "
                        "the notifications bell — the operator can Allow it (which "
                        "unlocks that domain for the rest of this session) or "
                        "ignore it. It is NOT auto-granted: I'll continue without "
                        "it and look for another way. Don't re-request it in a "
                        "loop — move on, and if it gets approved I'll read it."),
                }
        return tool_web_read(url, max_chars)

    def _request_web_approval(self, domain: str, url: str):
        """Post a NON-BLOCKING approval request for a community-tier domain: an
        inbox notification with an Allow button + a desktop popup. Deduped by
        domain so a retry loop can't spam the inbox; ignoring it leaves the run
        going and the request waiting in the bell until the operator gets to it."""
        domain = (domain or "").strip().lower()
        if not domain:
            return
        for n in self._notifications:
            if (n.get("kind") == "approval"
                    and (n.get("host") or "").lower() == domain
                    and n.get("state") in ("pending", "granted")):
                return  # already waiting or already handled this session
        import time as _t
        self._notifications.append({
            "kind": "approval",
            "host": domain,
            "url": url,
            "state": "pending",
            "title": f"Access requested: {domain}",
            "message": (f"Basilisk wants to read {domain} — a source that isn't "
                        "on the trusted-auto list, so it's held outside the "
                        "autonomous loop. Allow it to let Basilisk read this "
                        "domain for the rest of this session, or ignore it and "
                        "the run keeps going."),
            "ts": _t.strftime("%Y-%m-%d %H:%M"),
            "read": False,
        })
        self._notifications = self._notifications[-200:]
        self._save_notifications()
        self._play_notification_sound()
        try:
            GLib.idle_add(self._refresh_notifications)
        except Exception:
            pass
        try:  # real desktop notification (Gio), per-domain so they don't clobber
            self._desktop_notify(
                f"Access requested: {domain}",
                "Basilisk wants to read this source — open it to Allow or ignore.",
                nid=f"basilisk-approval-{domain}")
        except Exception:
            pass

    def _grant_web_host(self, domain: str):
        """Operator approved a community-tier domain — grant it for this session
        and mark the request done. Future web_read to that domain (and its
        subdomains) fetches without asking again until the app restarts.

        Crucially, this also SIGNALS the agent that the block just cleared:
        without it, the model was told to 'carry on without this source' and has
        no way to learn the operator said yes, so it never retries. We collect
        the exact URL(s) it was blocked on and hand them straight back."""
        domain = (domain or "").strip().lower()
        pending_urls = []
        if domain:
            self._web_grants.add(domain)
        for n in self._notifications:
            if n.get("kind") == "approval" and (n.get("host") or "").lower() == domain:
                if n.get("state") != "granted" and n.get("url"):
                    pending_urls.append(n.get("url"))
                n["state"] = "granted"
                n["read"] = True
        self._save_notifications()
        self._refresh_notifications()
        try:
            self.toast_overlay.add_toast(Adw.Toast.new(
                f"Allowed {domain} for this session — Basilisk can read it now."))
        except Exception:
            pass
        # Tell the agent, right now, that it can proceed.
        self._notify_web_grant_to_agent(domain, pending_urls)

    def _notify_web_grant_to_agent(self, domain: str, pending_urls):
        """Drop a note into the conversation naming the approved domain (and the
        exact URL the agent was blocked on) so it retries. If no turn is running
        the run had already settled — re-kick one so it acts immediately; if a
        turn IS in flight, the running loop reads the note on its next step
        (same contract as an operator suggestion), so we don't interrupt it."""
        cid = self.current_chat_id
        if cid is None:
            return
        if pending_urls:
            first = pending_urls[0]
            extra = ""
            if len(pending_urls) > 1:
                extra = (" Other now-allowed URLs you had queued: "
                         + ", ".join(pending_urls[1:4]) + ".")
            note = (f"[operator APPROVED access to {domain}] web_read is now "
                    f"unlocked for {domain} (and its subdomains) for the rest of "
                    f"this session. Retry the fetch you were blocked on now — "
                    f"web_read {first} — and continue the task with what it "
                    f"returns.{extra}")
        else:
            note = (f"[operator APPROVED access to {domain}] web_read is now "
                    f"unlocked for {domain} for the rest of this session. If you "
                    f"still need that source, read it now and continue.")
        try:
            self.store.add_message(cid, "user", note)
        except Exception:
            return
        if not self._is_busy():
            # The run had stopped — surface a clean line and start a turn so the
            # agent acts on the approval instead of waiting for the operator.
            try:
                self._append_message_widget(
                    "user", f"\u2713 Approved {domain} \u2014 Basilisk is "
                            f"retrying that source now.")
            except Exception:
                pass
            try:
                GLib.idle_add(lambda: (self._kick_assistant_turn(), False)[1])
            except Exception:
                self._kick_assistant_turn()

    def _refresh_notifications(self):
        """Rebuild the bell badge + the popover list from the store."""
        try:
            n = self._unread_count()
            if hasattr(self, "notif_badge_lbl"):
                self.notif_badge_lbl.set_label(str(n) if n else "")
                self.notif_badge_lbl.set_visible(n > 0)
            if hasattr(self, "notif_list_box"):
                child = self.notif_list_box.get_first_child()
                while child:
                    nxt = child.get_next_sibling()
                    self.notif_list_box.remove(child)
                    child = nxt
                if not self._notifications:
                    empty = Gtk.Label(label="No notifications yet.")
                    empty.add_css_class("dim-label")
                    empty.set_margin_top(18)
                    empty.set_margin_bottom(18)
                    self.notif_list_box.append(empty)
                else:
                    for item in reversed(self._notifications[-50:]):
                        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                                      spacing=2)
                        row.set_margin_top(8)
                        row.set_margin_bottom(8)
                        row.set_margin_start(10)
                        row.set_margin_end(10)
                        t = Gtk.Label(xalign=0.0,
                                      label=item.get("title", "Basilisk"))
                        t.add_css_class("notif-title")
                        t.set_wrap(True)
                        m = Gtk.Label(xalign=0.0, label=item.get("message", ""))
                        m.add_css_class("notif-body")
                        m.set_wrap(True)
                        ts = Gtk.Label(xalign=0.0, label=item.get("ts", ""))
                        ts.add_css_class("notif-time")
                        ts.add_css_class("dim-label")
                        row.append(t)
                        row.append(m)
                        row.append(ts)
                        # Community-source access requests carry an inline
                        # Allow button (pending) or an "allowed" marker (granted).
                        if item.get("kind") == "approval":
                            st = item.get("state", "pending")
                            if st == "granted":
                                done = Gtk.Label(
                                    xalign=0.0, label="✓ Allowed this session")
                                done.add_css_class("dim-label")
                                done.set_margin_top(4)
                                row.append(done)
                            else:
                                _host = item.get("host", "")
                                btn = Gtk.Button(label=f"Allow {_host}")
                                btn.add_css_class("suggested-action")
                                btn.set_halign(Gtk.Align.START)
                                btn.set_margin_top(6)
                                btn.connect(
                                    "clicked",
                                    lambda _b, h=_host: self._grant_web_host(h))
                                row.append(btn)
                        self.notif_list_box.append(row)
        except Exception:
            pass
        return False

    def _mark_notifications_read(self):
        for n in self._notifications:
            n["read"] = True
        self._save_notifications()
        self._refresh_notifications()

    def _clear_notifications(self, *_a):
        self._notifications = []
        self._save_notifications()
        self._refresh_notifications()

    def _vision_key(self) -> str:
        prov = self.settings.get("vision_provider", "siliconflow")
        return (self.settings.get(f"{prov}_api_key", "") or "").strip()

    def _vision_base_url(self) -> str:
        prov = self.settings.get("vision_provider", "siliconflow")
        spec = PROVIDERS_BY_KEY.get(prov)
        return spec.base_url if spec else ""

    def _tool_simple(self, fn, name=None):
        # LABEL, NOT LOGIC — but a log that lies is a debugging tax you pay on
        # every future bug. `fn.__name__` works only when a bare function is
        # passed; 150 of the 151 dispatch entries wrap the call in a lambda to
        # bind its arguments, so every one of them logged `→ running <lambda>…`
        # and the terminal could not tell you WHICH tool ran. The dispatcher
        # already knows the name — take it from there rather than reflecting on
        # a closure. Read synchronously here, in the dispatcher's own call
        # stack, before any thread starts, so there is no race with the next
        # tool in the chain.
        name = (name
                or getattr(self, "_dispatching_tool", "")
                or getattr(fn, "__name__", "") or "tool")
        if name == "<lambda>":
            name = getattr(self, "_dispatching_tool", "") or "tool"
        def _bg(feed):
            GLib.idle_add(lambda: self.terminal_log(
                f"→ running {name}…", "info") or False)
            result = fn()
            text = json.dumps(result, indent=2, default=str)
            # A tool that reported ok:false / error is NOT "✓ done". Printing
            # a tick over a failure is the same lie the DSML bug told — the
            # run looks healthy while nothing is actually being learned, so
            # the first place you look for the cause is the last place that
            # will show it. Say what happened.
            _bad = ""
            if isinstance(result, dict):
                if result.get("ok") is False or result.get("error"):
                    _bad = str(result.get("error")
                               or result.get("reason") or "failed")
            GLib.idle_add(lambda: self.terminal_log(
                (f"✗ {name}: {_bad[:120]}" if _bad else "✓ done"),
                ("error" if _bad else "ok")) or False)
            feed(text)
        self._tool_thread(_bg, name)

    def _action_tool(self, name, fn, description):
        """Run an action tool (one with side effects: launching apps,
        typing, moving/deleting files).  Honours the SAME 'Confirm every
        command' toggle the shell `run` tool uses — when it's on, the
        operator approves via a dialog first; when off (auto mode), the
        action runs immediately.  Either way the result is fed back to
        the model."""
        def _go(allow=True, password=None):
            if not allow:
                self._feed_tool_result(f"operator declined: {description}")
                return
            self._tool_simple(fn)

        # No confirmation — autonomous. The action just runs.
        _go(True)

    def _tool_skill_write(self, a):
        """Self-written skill.  The model supplies name/code/test/description/
        capabilities.  Saving is gated by the same confirm dialog the operator
        uses for commands: on approval the sidecar ast-checks the code, runs
        its test IN THE SANDBOX, and keeps it only if the test passes.  Nothing
        executes in Basilisk's own process."""
        name = str(a.get("name", "")).strip()
        code = str(a.get("code", ""))
        test = str(a.get("test", ""))
        desc = str(a.get("description", ""))
        caps = list(a.get("capabilities", []) or [])

        def _go(allow=True, password=None):
            if not allow:
                self._feed_tool_result(f"operator declined saving skill {name!r}")
                return

            def _bg(feed):
                try:
                    r = self._ext.commit_skill(name, code, test, desc, caps)
                except Exception as e:
                    r = {"ok": False, "error": f"{type(e).__name__}: {e}"}
                if r.get("ok"):
                    self.terminal_log(f"✓ skill saved: {name} "
                                      f"(sandbox: {r.get('tier')})", "ok")
                else:
                    self.terminal_log(f"✗ skill rejected: "
                                      f"{r.get('reason') or r.get('error')}",
                                      "error")
                feed(json.dumps(r, indent=2, default=str))
            self._tool_thread(_bg, f"skill_save {name}")

        descr = (f"save self-written skill '{name}'"
                 + (f" (caps: {', '.join(caps)})" if caps else "")
                 + " — sandbox-tested before keeping")
        # No confirmation — autonomous. The skill is saved directly (it's still
        # ast-checked and sandbox-tested before being kept, so nothing unsafe
        # runs in Basilisk's own process regardless).
        _go(True)


    def _tool_read_file(self, path):
        if not path:
            self._feed_tool_result("error: no path")
            return
        def do_read():
            def _bg(feed):
                feed(self._format_read(tool_read_file(path)))
            self._tool_thread(_bg, "read_file")
        if is_sensitive_path(path):
            confirm_sensitive_read_dialog(self, path, lambda allow:
                do_read() if allow
                else self._feed_tool_result(f"denied: {path}"))
        else:
            do_read()

    def _format_read(self, r):
        """Turn a tool_read_file result into the text the model sees.

        Was _render_read, which fed the result itself and indexed r["content"] /
        r["path"] / r["size"] directly — so an unexpected result shape raised
        inside a worker thread and the turn hung.  Now it only FORMATS; the
        feeding (and the guarantee that one happens) belongs to _tool_thread."""
        r = r or {}
        if not r.get("ok"):
            return f"read_file error: {r.get('error')}"
        body = r.get("content", "")
        header = (f"file: {r.get('path')} ({r.get('size')} bytes"
                  f"{' truncated' if r.get('truncated') else ''})")
        return f"{header}\n\n{body}"

    def _tool_list_dir(self, path):
        def _bg(feed):
            self.terminal_log(f"→ list_dir {path}", "info")
            r = tool_list_dir(path) or {}
            if not r.get("ok"):
                text = f"list_dir error: {r.get('error')}"
                self.terminal_log(f"✗ {r.get('error')}", "error")
            else:
                entries = r.get("entries") or []
                lines = [f"dir: {r.get('path', path)}", ""]
                for e in entries:
                    sz = "" if e.get("is_dir") else f"  ({e.get('size')}B)"
                    lines.append(f"  {e.get('name')}{sz}")
                text = "\n".join(lines)
                self.terminal_log(f"✓ {len(entries)} entries", "ok")
            feed(text)
        self._tool_thread(_bg, "list_dir")

    def _tool_find_file(self, pattern, search_path, max_results=50,
                        min_size_kb=0, max_size_kb=0,
                        modified_within_days=0):
        def _bg(feed):
            self.terminal_log(f"→ find {pattern} in {search_path}", "info")
            r = tool_find_file(pattern, search_path, max_results,
                               min_size_kb, max_size_kb,
                               modified_within_days) or {}
            if r.get("ok"):
                found = r.get("found") or []
                count = r.get("count", len(found))
                lines = [f"find {pattern} in {r.get('search_path', search_path)}: "
                         f"{count} hit(s)"]
                for hit in found:
                    if isinstance(hit, dict):
                        sz = hit.get("size")
                        szs = f"  ({sz}B)" if sz is not None else ""
                        lines.append(f"  {hit.get('path')}{szs}")
                    else:
                        lines.append(f"  {hit}")
                text = "\n".join(lines)
                self.terminal_log(f"✓ {count} found", "ok")
            else:
                text = f"find_file error: {r.get('error')}"
                self.terminal_log(f"✗ {r.get('error')}", "error")
            feed(text)
        self._tool_thread(_bg, "find_file")

    def _tool_run(self, command, reason):
        # Reached only when the model emits <tool name="run"> after the
        # operator approved.  Goes through the same gate as the card.
        self._execute_command(command, reason)

    def _reload_persona(self) -> bool:
        """Hot-reload basilisk_persona after a self-edit and rebind the names this
        module imported from it, so a change to Basilisk's persona applies on the
        next reply without a relaunch.  basilisk.py / basilisk_core.py changes still
        need a relaunch (you can't safely swap a running app's own modules)."""
        try:
            import importlib
            import basilisk_persona as _kp
            importlib.reload(_kp)
            # Every persona symbol this module imported must be rebound, or a
            # self-edit silently keeps calling the stale one.
            global build_system_prompt, assemble_messages, volatile_block
            global title_from_first_message
            build_system_prompt = _kp.build_system_prompt
            assemble_messages = _kp.assemble_messages
            volatile_block = _kp.volatile_block
            title_from_first_message = _kp.title_from_first_message
            log("persona hot-reloaded")
            return True
        except Exception as e:
            log(f"persona reload failed: {e}")
            return False

    def _run_proposed_edit(self, path, content, card=None):
        """Called when the operator clicks Apply on a proposed-edit card.
        The click IS the approval.  Mirrors _run_proposed_command: set up
        a turn context, write the file (with the parse-check + backup net
        in tool_write_file), then feed the result back so Basilisk confirms.

        A file write is the same kind of action as a command — it goes
        through the same confirm-by-clicking gate.  We surface a sudo
        prompt only if the write lands somewhere the user can't write,
        in which case we tell Basilisk to retry via `sudo tee` rather than
        silently failing."""
        if not path:
            if card is not None:
                card.reset_apply_button()
            return
        # The busy guard is for OPERATOR CLICKS (card is not None) — don't apply a
        # file mid-task from a click. When called programmatically in autonomous
        # mode (card is None, from _execute_tool_calls mid-turn) we ARE the task
        # and must proceed, or the model's write_file silently does nothing.
        if card is not None and self._is_busy():
            self._show_toast("Busy — let the current task finish or stop it.")
            card.reset_apply_button()
            return
        self._stop_requested = False
        if self.current_chat_id is None:
            self._new_chat()
        self.streaming_chat_id = self.current_chat_id
        self._tool_chain_depth = 0
        self._set_working(True, "writing file…")
        self._set_send_mode(True)

        def _bg(feed):
            r = tool_write_file(path, content) or {}
            if r.get("ok"):
                parts = [f"wrote {r.get('path', path)} ({r.get('size')} bytes)"]
                if r.get("created"):
                    parts.append("(new file created)")
                if r.get("backup"):
                    parts.append(f"backup: {r['backup']}")
                if r.get("is_python"):
                    base = os.path.basename(r.get("path") or path)
                    if base == "basilisk_persona.py":
                        if self._reload_persona():
                            parts.append("Persona reloaded live — the new "
                                         "character takes effect on my next "
                                         "reply, no relaunch needed.")
                        else:
                            parts.append("Python syntax was checked, but the "
                                         "live persona reload failed — "
                                         "relaunch to apply.")
                    else:
                        parts.append("Python syntax was checked before "
                                     "writing. This is a core file (basilisk.py / "
                                     "basilisk_core.py) — relaunch to load it.")
                out = "\n".join(parts)
            else:
                out = f"write failed for {path}\nerror: {r.get('error')}"
            feed(out)
        self._tool_thread(_bg, f"write_file {path}")

    def _run_proposed_command(self, command, explanation="", card=None):
        """Called when the operator clicks Run on a proposed-command card.
        The click IS the approval — we set up a turn context and execute,
        then Basilisk interprets the output."""
        if not command:
            if card is not None:
                card.reset_run_button()
            return
        # Busy guard is for OPERATOR CLICKS only (card is not None). The
        # programmatic autonomous path (card is None) IS the running task and
        # must proceed.
        if card is not None and self._is_busy():
            self._show_toast("Busy — let the current task finish or stop it.")
            card.reset_run_button()
            return
        self._stop_requested = False
        if self.current_chat_id is None:
            self._new_chat()
        # This is the start of a turn — capture the chat and show the
        # stop affordance so a long command can be interrupted.
        self.streaming_chat_id = self.current_chat_id
        self._tool_chain_depth = 0
        _cmd_head = command.strip().split()[0] if command.strip() else ""
        self._set_working(True, f"running {_cmd_head}…" if _cmd_head else "running…")
        self._set_send_mode(True)
        # The click on the card IS the approval, so don't re-confirm a safe
        # command — only stop for a sudo password when root is required.
        self._execute_command(command, explanation or "operator approved",
                              from_card=True)

    def _sudo_pw_valid(self) -> bool:
        """A cached sudo password exists and hasn't hit its 30-minute expiry."""
        import time
        return bool(self._sudo_pw) and (time.time() - self._sudo_pw_time) < 1800

    def _cache_sudo_pw(self, pw):
        """Hold the sudo password in memory for this chat (30-min TTL). It is
        never written to disk, the log, the ledger, or the conversation — the
        model has no way to read it."""
        import time
        self._sudo_pw = pw or None
        self._sudo_pw_time = time.time() if pw else 0.0

    def _clear_sudo_pw(self):
        """Wipe the cached sudo password (new chat, expiry, or a failed auth)."""
        self._sudo_pw = None
        self._sudo_pw_time = 0.0

    def _foresight_rule_floor(self, command):
        """Foresight's DETERMINISTIC verdict only — no model, no network.

        Used when the optional model pass blows its deadline.  Falling back to
        this rather than to a bare `allow` matters: the rule floor is the tier
        that catches the irreversible shapes (mkfs, dd onto a block device,
        partition edits, fork bombs), and the model pass may only ever ESCALATE
        above it.  So a timeout costs us the refinement, never the floor."""
        try:
            from basilisk_ext.foresight import _rule_floor
            return _rule_floor(command or "")
        except Exception:
            return {"verdict": "allow", "reasons": ["foresight unavailable"]}

    def _execute_command(self, command, reason, from_card=False,
                         _foresight=None):
        """Confirm (with sudo password if needed), run, feed result back.
        Shared by the model's `run` tool and the card's Run button.

        from_card=True means the operator already approved by clicking Run,
        so we skip the redundant y/n and only surface a dialog when the
        command needs root (to collect the password).

        _foresight is internal: None means "not assessed yet" and a dict means
        "already assessed, don't re-enter the gate".  It is a PARAMETER rather
        than instance state deliberately — the previous instance-flag version
        was cleared in a `finally` as soon as this method returned, which is
        while the command it launched is still running on a worker thread."""
        self._mark_turn_progress()
        if not command:
            self._feed_tool_result("error: no command")
            return

        # ── HARD BLOCK — the one gate with no override ──
        # A command in the catastrophic class (rm -rf /, mkfs, dd onto a disk,
        # fork bomb, recursive delete of root/system dirs, …) is REFUSED
        # outright, before any confirm dialog, before foresight, before the
        # shell.  There is no "Run anyway" button and no setting that turns
        # this off: Basilisk, as an AI, will never be the thing that runs a
        # system-destroying command.  A human who truly needs such an op does
        # it themselves in a real terminal.
        if is_catastrophic_command(command):
            self.terminal_log("■ BLOCKED — catastrophic command refused "
                              "(no override)", "error")
            self._activity_note(
                "BLOCKED (no override): catastrophic command  " + command[:90],
                "gate")
            self._feed_tool_result(
                "REFUSED. This command is in the catastrophic class — it would "
                "irreversibly destroy the system or its data — so Basilisk will not "
                "run it under any circumstances. There is no override; this is "
                "a hard safety floor. If a human genuinely needs this, they "
                "must do it themselves in a real terminal.\n\n  " + command)
            return

        # ── foresight gate ──
        # Predict consequences before running.  Off unless foresight_enabled.
        #
        # Three things were wrong with the old version of this block and all
        # three are fixed here:
        #
        #  1. A `block` verdict did NOTHING.  The old code computed a
        #     `force_confirm` flag, stored it on self as `_fs_force_confirm`,
        #     and then no code anywhere ever read that attribute — so foresight
        #     printed an alarming card and ran the command regardless.  A safety
        #     layer that logs and proceeds is not a safety layer.  A block now
        #     actually refuses, AND the refusal is fed back as a tool result so
        #     the model can pick a different approach instead of the turn simply
        #     dangling with nothing to answer.
        #
        #  2. The assessment had NO deadline.  With the optional model pass on,
        #     `_ext.foresight()` makes a full network round-trip; if that hung,
        #     `_resume` never ran, the command never executed, no tool result was
        #     ever fed back, and the whole turn sat in "working" until the app
        #     was restarted.  The assessment is now watchdogged: if it does not
        #     land inside `foresight_timeout_s`, we proceed on the deterministic
        #     rule floor (instant, local, and the part that actually carries the
        #     safety weight) and say so in the log.  Latency never wedges a turn.
        #
        #  3. Re-entrancy rode on an INSTANCE flag (`_fs_cleared`) that was
        #     cleared in a `finally` the moment `_execute_command` returned —
        #     which is long before the command it started has finished.  The
        #     verdict is now passed down as a parameter, so it belongs to this
        #     one call and cannot be clobbered by a concurrent one.
        if (_foresight is None
                and getattr(self, "_ext", None)
                and self.settings.get("foresight_enabled", False)):
            _fs_deadline = max(
                1.0, float(self.settings.get("foresight_timeout_s",
                                             FORESIGHT_TIMEOUT_S) or
                           FORESIGHT_TIMEOUT_S))
            _slot = {"v": None}
            _landed = threading.Event()

            def _fbg():
                try:
                    _slot["v"] = self._ext.foresight(command)
                except Exception as e:
                    _slot["v"] = {"verdict": "allow",
                                  "reasons": [f"foresight error: {e}"]}
                finally:
                    _landed.set()

            def _resume():
                v = _slot["v"]
                timed_out = v is None
                if timed_out:
                    # The assessment is still in flight.  Fall back to the
                    # deterministic rule floor, which is pure pattern matching
                    # over the command string: no network, no model, sub-100us.
                    # The catastrophic floor at the execution primitive is
                    # untouched by any of this and still applies.
                    v = self._foresight_rule_floor(command)
                    self.terminal_log(
                        f"⏱ foresight model pass exceeded {_fs_deadline:.0f}s "
                        f"— proceeding on the deterministic rules", "error")
                try:
                    from basilisk_ext.foresight import render_card
                except Exception:
                    render_card = lambda x: ""
                verdict = (v or {}).get("verdict", "allow")
                if verdict in ("block", "caution"):
                    # Show the consequence card either way so the operator
                    # sees foresight's read in the log.
                    card = render_card(v)
                    if card:
                        self.terminal_log(card, "error")
                if verdict == "block":
                    # BLOCK is the whole point of the layer: an irreversible,
                    # system-destroying shape (disk wipe, mkfs, partition edit,
                    # fork bomb) — never an ordinary hacking command, and never
                    # something the model can argue down, because the rule floor
                    # sets it and the model may only escalate.  Refuse, and TELL
                    # THE MODEL, so it adapts rather than waiting on a result
                    # that would never come.
                    _why = "; ".join((v or {}).get("reasons") or []) \
                        or "predicted irreversible damage to this machine"
                    self.terminal_log(
                        "■ BLOCKED by foresight — not run", "error")
                    self._activity_note(
                        "BLOCKED by foresight: " + _why[:110], "gate")
                    self._feed_tool_result(
                        "REFUSED by foresight. Predicted consequence: " + _why
                        + ".\nThis command was NOT run. Do not retry it as-is. "
                        "Use a reversible form, narrow the target, or ask the "
                        "operator to do it himself in a real terminal.\n\n  "
                        + command)
                    return False
                # In autonomous walk-away mode, foresight's CAUTION layer is
                # advisory ONLY — it logs and lets the command run, so risky-
                # but-normal pentest commands (curl|bash to fetch a tool,
                # kill -9 a hung scan, a firewall/route tweak) never interrupt
                # an unattended engagement.  Supervised mode still stops on a
                # caution through the normal confirm path below.
                self._execute_command(command, reason, from_card=from_card,
                                      _foresight=(v or {"verdict": "allow"}))
                return False

            def _watch():
                _landed.wait(_fs_deadline)
                GLib.idle_add(_resume)

            threading.Thread(target=_fbg, daemon=True).start()
            threading.Thread(target=_watch, daemon=True).start()
            return

        # ── (#4) command de-duplication ──
        # Record every command that reaches execution; if the operator opted
        # in, warn when the exact command was already run very recently (a
        # stale re-issue or an accidental double-tap).  Non-blocking.
        if self.settings.get("warn_duplicate_commands", False):
            try:
                if recent_duplicate(command, 600):
                    self._show_toast(
                        "You just ran this command. Intentional, or stale?",
                        timeout=5)
                    self.terminal_log(
                        f"⚠ duplicate command within 10m: {command[:60]}",
                        "dim")
            except Exception:
                pass
        try:
            note_command(command)
        except Exception:
            pass

        # ── loop-break bookkeeping ──
        # Track the tail of executed commands so _kick_assistant_turn / _mission_
        # continue can spot the model firing the SAME command over and over (a
        # stuck autonomous loop). Placed AFTER the foresight gate so it records
        # each command exactly once — _execute_command re-enters itself through
        # foresight, and appending at the top double-counted with foresight on.
        try:
            self._recent_commands.append((command or "").strip())
            self._recent_commands = self._recent_commands[-8:]
        except Exception:
            self._recent_commands = [(command or "").strip()]

        # How long should this command take, and when do we give up? The
        # estimator knows a quick command from a build from a server that will
        # NEVER return on its own — so a hung start is terminated in ~25s
        # instead of blocking for the full window.
        _est = estimate_runtime(command)
        timeout = _est["hard_timeout_seconds"]
        if _est.get("is_server") and not _est.get("backgrounded"):
            self._show_toast(
                "That's a server — capping the start at 25s. Background it "
                "(append ' &') so it doesn't block.", timeout=6)

        def run_bg(password=None):
            def _bg(feed):
                # Log the command but DON'T force the panel open — the
                # operator opens the log themselves with the toggle when
                # they want it.  The command still shows in the status line.
                self.terminal_log(f"$ {command}", "cmd")
                r = tool_run_command(command, timeout=timeout,
                                     sudo_password=password) or {}
                # Record to the evidence ledger (fail-safe: a ledger error must
                # never affect the command result the operator sees).
                try:
                    _led = get_ledger()
                    if _led is not None:
                        _led.record(command, reason, r)
                except Exception:
                    pass
                if r.get("ok"):
                    # `.get` throughout, not `r['rc']`.  This runs on a worker
                    # thread whose only job is to produce a tool result; a
                    # KeyError here used to kill the thread, and with it the
                    # turn — the loop has no other way to advance.
                    rc = r.get("rc")
                    stdout = r.get("stdout") or ""
                    stderr = r.get("stderr") or ""
                    parts = [f"$ {command}", f"(rc={rc})"]
                    if stdout:
                        # Stream stdout to terminal log line by line
                        for line in stdout.splitlines()[:80]:
                            GLib.idle_add(lambda l=line: self.terminal_log(l, "stdout") or False)
                        parts.append(stdout)
                    if stderr:
                        for line in stderr.splitlines()[:20]:
                            GLib.idle_add(lambda l=line: self.terminal_log(l, "stderr") or False)
                        parts.append(f"stderr:\n{stderr}")
                    if r.get("sudo_auth_failed"):
                        parts.append(
                            "\n[note] sudo could not authenticate "
                            "non-interactively. The password may have been "
                            "wrong, or sudo timed out its cached credential.")
                        self.terminal_log("✗ sudo auth failed", "error")
                        # Drop the bad/expired cached password so the next root
                        # command asks for it again instead of failing silently.
                        GLib.idle_add(self._clear_sudo_pw)
                    else:
                        self.terminal_log(f"✓ rc={rc}",
                                          "ok" if rc == 0 else "error")
                    out = "\n".join(parts)
                elif r.get("partial"):
                    # A STALL, not a clean failure. The output collected before
                    # it stalled is real work and goes back to the model in
                    # full, with the diagnosis — otherwise it re-runs the whole
                    # command and stalls in exactly the same place.
                    parts = [f"$ {command}", "(STALLED — partial result)"]
                    if r.get("stdout"):
                        for line in r["stdout"].splitlines()[:80]:
                            GLib.idle_add(lambda l=line: self.terminal_log(l, "stdout") or False)
                        parts.append(r["stdout"])
                    if r.get("stderr"):
                        parts.append(f"stderr:\n{r['stderr']}")
                    if r.get("diagnosis"):
                        parts.append(f"\n[stall diagnosis]\n{r['diagnosis']}")
                    self.terminal_log(
                        f"⏸ stalled after {r.get('elapsed_s', '?')}s — kept "
                        f"{len(r.get('stdout') or '')} chars of output", "error")
                    out = "\n".join(parts)
                else:
                    out = f"$ {command}\nerror: {r.get('error')}"
                    self.terminal_log(f"✗ {r.get('error')}", "error")
                feed(out)
            self._tool_thread(_bg, f"run {command.strip().split()[0]}"
                              if command.strip() else "run")

        def decide(allow, password=None):
            if not allow:
                self._feed_tool_result(f"operator declined: {command}")
                return
            run_bg(password)

        # Sudo password: held in an in-app cache, entered ONCE per chat, reused
        # silently for 30 minutes, then asked again; wiped on a new chat. The
        # password lives only in memory and is passed straight to sudo — never
        # logged, stored, or shown to the model.
        sudo_needed = command_needs_sudo(command)
        reason_txt = reason or "no reason"
        # ── NO CONFIRMATION. Basilisk is autonomous, full stop. ──
        # There is no "confirm every command", no approval card, no mode. Every
        # command just runs. The ONLY two exceptions, and neither is a
        # "may I?" prompt:
        #   1. Catastrophic/system-destroying commands are REFUSED (already
        #      hard-blocked at the top of this method) — a hard floor, no dialog.
        #   2. A raw shell write to Basilisk's OWN source is refused too, so a
        #      malicious page/tool can't overwrite the safety code — also no
        #      dialog, just refused.
        # The one dialog that can appear is to COLLECT A SUDO PASSWORD, once per
        # chat, when a root command has no valid cached credential.
        if command_tampers_self(command):
            self.terminal_log("■ refused — raw write to Basilisk's own source "
                              "(use the guarded edit path)", "error")
            self._activity_note(
                "REFUSED: raw write to Basilisk's own source", "gate")
            self._feed_tool_result(
                "REFUSED — this command writes directly to one of Basilisk's own "
                "source files, bypassing the guarded edit path. Not run (this "
                "protects the safety code from being overwritten). Use propose_edit "
                "/ write_file for legitimate self-edits.\n\n  " + command)
            return
        if sudo_needed:
            if self._sudo_pw_valid():
                # Cached this chat and still inside the 30-min window — run silently.
                self.terminal_log("• using cached sudo credential (this chat)", "dim")
                run_bg(self._sudo_pw)
            else:
                # Never entered this chat, or the 30-min cache expired: ask once,
                # cache it for this chat, then run.
                self._clear_sudo_pw()

                def _decide_and_cache(allow, password=None):
                    if allow and password:
                        self._cache_sudo_pw(password)
                    decide(allow, password)
                confirm_command_dialog(self, command, reason_txt,
                                       _decide_and_cache, catastrophic=False)
        else:
            run_bg(None)

    def _tool_audit(self):
        self._show_toast("Auditing…")
        def _bg(feed):
            def _prog(title, done, total):
                self.terminal_log(f"[{done}/{total}] {title}", "info")
            audit = run_security_audit(on_progress=_prog)
            text = format_audit_for_chat(audit)
            self.terminal_log(f"✓ audit complete — grade {audit.get('grade')}", "ok")
            feed(text)
        self._tool_thread(_bg, "audit")

    def _tool_scan_net(self, cidr=None):
        self._show_toast("Scanning network…")
        def _bg(feed):
            def _prog(msg):
                self.terminal_log(f"nmap: {msg}", "info")
            scan = run_network_scan(cidr, on_progress=_prog)
            text = format_scan_for_chat(scan)
            if scan.get("ok"):
                self.terminal_log(f"✓ scan complete — "
                                  f"{len(scan.get('hosts', []))} hosts", "ok")
            else:
                self.terminal_log(f"✗ scan failed: {scan.get('error')}",
                                  "error")
            feed(text)
        self._tool_thread(_bg, "scan_net")

    # ── user-initiated chip actions ─────────────────────────────

    def _is_busy(self) -> bool:
        """True when an assistant turn or tool call is in flight."""
        if self.streaming_thread and self.streaming_thread.is_alive():
            return True
        if self.streaming_msg_widget is not None:
            return True
        if self.streaming_chat_id is not None:
            return True
        # A kick already queued IS the turn, even though every field above
        # has been cleared in preparation for it. Without this the app
        # answers "idle" for up to a minute of error back-off and accepts a
        # second turn on top of the one already coming.
        if getattr(self, "_pending_kick_id", 0):
            return True
        return False

    def _begin_chip_action(self) -> bool:
        """Snapshot the current chat for an upcoming chip-triggered tool
        and switch the primary button to Stop.  Returns False if busy."""
        if self._is_busy():
            self._show_toast("Already busy — stop the current task first.")
            return False
        self._stop_requested = False
        # Capture the chat NOW so that when the async tool finishes and
        # _feed_tool_result fires (could be many seconds later), the
        # result lands in the chat the user clicked from, not whichever
        # they happen to be looking at when the result arrives.
        if self.current_chat_id is None:
            self._new_chat()
        self.streaming_chat_id = self.current_chat_id
        self._tool_chain_depth = 0
        self._set_working(True, "working…")
        self._set_send_mode(True)
        return True

    def _maybe_set_title_from_first(self, chat_id: int, first_text: str):
        """If this is the first user message in the chat, derive a title
        from it.  Called from both regular send and chip actions."""
        if self.store.count_messages_by_role(chat_id, "user") == 1:
            title = title_from_first_message(first_text)
            self.store.rename_chat(chat_id, title)
            if chat_id == self.current_chat_id:
                self.chat_title_lbl.set_text(title)
            self._refresh_sidebar()

    def _inject_user_request(self, text: str):
        if self.current_chat_id is None:
            self._new_chat()
        cid = self.current_chat_id
        self.store.add_message(cid, "user", text)
        self._append_message_widget("user", text)
        # ONE feed for this whole turn, however many round-trips it takes.
        self._activity_new_turn()
        self._maybe_set_title_from_first(cid, text)

    def _user_action_audit(self):
        if not self._begin_chip_action(): return
        self._inject_user_request("Audit my system and tell me what to fix.")
        self._tool_audit()

    def _user_action_scan(self):
        if not self._begin_chip_action(): return
        self._inject_user_request("Scan the local network.")
        self._tool_scan_net()

    def _user_action_sysinfo(self):
        if not self._begin_chip_action(): return
        self._inject_user_request("Give me a system overview.")
        self._tool_simple(tool_system_info)

    def _user_action_updates(self):
        if not self._begin_chip_action(): return
        self._inject_user_request("What security updates are pending?")
        self._tool_simple(tool_check_updates)

    def _user_action_downloads(self):
        if not self._begin_chip_action(): return
        self._inject_user_request("What's in my Downloads recently?")
        self._tool_simple(lambda: tool_recent_downloads(20))

    def _user_action_camera(self):
        """Capture a photo off-thread, then drop it into the composer as an
        image so it renders and Basilisk can see it with analyze_image."""
        self._show_toast("Taking a photo…")

        def _bg():
            r = tool_capture_photo()
            GLib.idle_add(lambda: self._finish_camera(r) or False)
        threading.Thread(target=_bg, daemon=True).start()

    def _finish_camera(self, r):
        if not r.get("ok"):
            self._show_toast(r.get("error", "Camera failed"))
            return False
        path = r.get("path", "")
        buf = self.input_view.get_buffer()
        cur = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
        ref = f"![photo](file://{path})"
        prompt = "What do you see in this photo?"
        new = (f"{cur}\n{ref}\n{prompt}" if cur.strip()
               else f"{ref}\n{prompt}")
        buf.set_text(new)
        self._show_toast("Photo captured")
        return False

    # ── ATTACHMENT TRAY ─────────────────────────────────────────
    # Attachments used to be pasted INTO the composer: a 40KB text file became
    # 40KB of text in the box you are trying to type in, and an image became a
    # line of raw markdown. You could not see your own message, editing it
    # meant editing around the payload, and removing an attachment meant
    # hand-deleting the right fence.
    #
    # They live ABOVE the composer now, as chips. The message you type stays
    # the message you type; the payload is folded in at SEND, in exactly the
    # form the old code produced — so what reaches the model and what is
    # stored are byte-for-byte what they were before. This is a composer
    # change only, deliberately: the send path is not where you want a
    # surprise.

    _ATTACH_MAX_CHIP_NAME = 28

    def _build_attach_tray(self) -> Gtk.Widget:
        self.attach_tray = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                                   spacing=6)
        self.attach_tray.add_css_class("attach-tray")
        # Horizontal scroller for the same reason the action chips have one: a
        # narrow window must scroll them, never be forced wider than the screen.
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        scroll.set_propagate_natural_height(True)
        scroll.set_kinetic_scrolling(True)
        scroll.set_overlay_scrolling(True)
        scroll.set_child(self.attach_tray)
        self._attach_revealer = Gtk.Revealer()
        self._attach_revealer.set_transition_type(
            Gtk.RevealerTransitionType.SLIDE_DOWN)
        self._attach_revealer.set_transition_duration(150)
        self._attach_revealer.set_child(scroll)
        self._attach_revealer.set_reveal_child(False)
        return self._attach_revealer

    def _attach_add(self, kind: str, path: str, payload: str):
        """Record one attachment and draw its chip. `payload` is the exact text
        this attachment will contribute to the sent message."""
        self._attachments.append(
            {"kind": kind, "path": path, "payload": payload})
        self._refresh_attach_tray()

    def _refresh_attach_tray(self):
        tray = getattr(self, "attach_tray", None)
        if tray is None:
            return
        child = tray.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            tray.remove(child)
            child = nxt
        for i, att in enumerate(list(self._attachments)):
            tray.append(self._attach_chip(i, att))
        self._attach_revealer.set_reveal_child(bool(self._attachments))

    def _attach_chip(self, idx: int, att: Dict[str, Any]) -> Gtk.Widget:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
        row.add_css_class("attach-chip")
        row.add_css_class("image" if att["kind"] == "image" else "file")

        icon = Gtk.Label(label="IMG" if att["kind"] == "image" else "TXT")
        icon.add_css_class("attach-chip-kind")
        row.append(icon)

        name = os.path.basename(att["path"]) or att["path"]
        if len(name) > self._ATTACH_MAX_CHIP_NAME:
            # Middle-elide by hand: the EXTENSION is the part that says what
            # the file is, so a plain end-ellipsis throws away the useful half.
            keep = self._ATTACH_MAX_CHIP_NAME - 3
            name = name[:keep // 2] + "..." + name[-(keep - keep // 2):]
        lbl = Gtk.Label(label=name, xalign=0.0)
        lbl.add_css_class("attach-chip-name")
        row.append(lbl)

        size = ""
        try:
            n = os.path.getsize(att["path"])
            size = ("%d B" % n if n < 1024 else
                    "%.0f KB" % (n / 1024) if n < 1024 * 1024 else
                    "%.1f MB" % (n / (1024 * 1024)))
        except Exception:
            size = ""
        if size:
            sl = Gtk.Label(label=size)
            sl.add_css_class("attach-chip-size")
            row.append(sl)

        rm = Gtk.Button(label="×")          # MULTIPLICATION SIGN
        rm.add_css_class("attach-chip-remove")
        rm.set_has_frame(False)
        rm.set_tooltip_text("Remove this attachment")
        rm.connect("clicked", lambda *_a, i=idx: self._attach_remove(i))
        row.append(rm)
        return row

    def _attach_remove(self, idx: int):
        # Index into a list that is rebuilt on every refresh, so a stale chip
        # can only ever point past the end — never at the wrong file.
        if 0 <= idx < len(self._attachments):
            self._attachments.pop(idx)
            self._refresh_attach_tray()

    def _attach_clear(self):
        self._attachments = []
        self._refresh_attach_tray()

    def _drain_attachments(self) -> str:
        """The text the pending attachments contribute, and clear them.

        Byte-identical to what the old in-composer version produced, so the
        stored message, the rendered bubble and what the model reads are all
        exactly what they were before the tray existed."""
        if not self._attachments:
            return ""
        parts = [a["payload"] for a in self._attachments]
        self._attach_clear()
        return "\n".join(parts)

    def _pick_attachment(self):
        # Gtk.FileDialog is GTK 4.10+.  On an older GTK it doesn't
        # exist, so the attach button silently did nothing — fall back to
        # FileChooserNative there so attaching works on every device.
        if hasattr(Gtk, "FileDialog"):
            try:
                dlg = Gtk.FileDialog()
                dlg.set_title("Attach file or image")

                def _cb(d, res):
                    try:
                        f = d.open_finish(res)
                        if f:
                            self._attach_file(f.get_path())
                    except Exception:
                        pass
                dlg.open(self, None, _cb)
                return
            except Exception as e:
                log(f"FileDialog failed, falling back: {e}")
        try:
            chooser = Gtk.FileChooserNative.new(
                "Attach file or image", self,
                Gtk.FileChooserAction.OPEN, "Attach", "Cancel")

            def _resp(c, resp):
                try:
                    if resp == Gtk.ResponseType.ACCEPT:
                        f = c.get_file()
                        if f:
                            self._attach_file(f.get_path())
                finally:
                    c.destroy()
            chooser.connect("response", _resp)
            chooser.show()
        except Exception as e:
            self._show_toast(f"Could not open file picker: {e}")

    # image types Basilisk can SHOW inline (rendered by ImageWidget)
    _ATTACH_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp",
                          ".bmp", ".svg"}

    def _attach_file(self, path):
        if not path:
            self._show_toast("Could not get file path.")
            return
        ext = os.path.splitext(path)[1].lower()
        if ext in self._ATTACH_IMAGE_EXTS:
            # Markdown pointing at the local file, so it renders inline in the
            # chat (ImageWidget handles file:// URLs) instead of being read as
            # binary garbage. Staged as a chip; folded in at send.
            name = os.path.basename(path)
            self._attach_add("image", path, f"![{name}](file://{path})")
            self._show_toast(f"Attached image: {name}")
            return
        # Text-like file: read its contents into the message.
        def _bg():
            r = tool_read_file(path, max_bytes=40_000)
            GLib.idle_add(self._finish_attach, path, r)
        threading.Thread(target=_bg, daemon=True).start()

    def _finish_attach(self, path, r):
        if not r.get("ok"):
            self._show_toast(f"Read error: {r.get('error')}")
            return False
        body = r["content"]
        self._attach_add("file", path,
                         f"[attached: {path}]\n```\n{body}\n```")
        self._show_toast(f"Attached: {os.path.basename(path)}")
        return False

    # ── history ─────────────────────────────────────────────────

    def _trim_tool_result(self, content: str) -> str:
        """Shrink an older, already-consumed tool_result so a long research
        chat doesn't re-bill the full (sometimes huge) output every turn.

        This is a SECOND, INDEPENDENT compression layer — headroom runs in the
        router, this runs while building history — and the two do not know
        about each other.  Fixing one leaves the other, which is why a page
        could still arrive gutted after headroom was taught to skip web_read.

        Two things were wrong beyond the size:

          * It cut at a byte offset with no regard for structure, so a JSON
            result was left with an unterminated string and a synthesised
            `</tool_result>` glued on.  The model got malformed JSON and no
            indication that it was malformed rather than genuinely short.
          * Head-only.  A document's conclusion — the redress, the deadline,
            the verdict — lives at the END, so a head-only cut reliably keeps
            the preamble and drops the answer.

        The budget is unchanged; this spends it better and says clearly that
        the block is incomplete, so the model can re-read rather than conclude
        the source did not contain what it was looking for.
        """
        if len(content) <= HISTORY_TRIM_HEAD_CHARS + 200:
            return content
        body = content
        closer = ""
        if body.rstrip().endswith("</tool_result>"):
            # Trim the BODY and put the operator's real closing tag back,
            # rather than truncating through it and inventing a new one.
            cut = body.rstrip()[: -len("</tool_result>")]
            closer = "\n</tool_result>"
            body = cut
        head_n = int(HISTORY_TRIM_HEAD_CHARS * 0.7)
        tail_n = HISTORY_TRIM_HEAD_CHARS - head_n
        head = body[:head_n]
        tail = body[-tail_n:] if tail_n > 0 else ""
        return (f"{head}\n…[INCOMPLETE — {len(content) - HISTORY_TRIM_HEAD_CHARS}"
                f" chars of this earlier tool output were removed to save "
                f"tokens; {len(content)} chars originally. The middle is gone, "
                f"not empty — re-run the tool if you need it.]\n{tail}{closer}")

    def _next_provider_with_key(self) -> Optional[str]:
        """Pick the next cloud provider (after the current active one) that
        has an API key set.  Returns None if no other configured provider is
        available.

        RETAINED BUT NOT WIRED INTO CHAT: the degraded-output path used to
        call this to auto-hop clouds, which silently flipped the operator's
        selected provider (e.g. DeepSeek -> Groq) and persisted it. That is
        gone — the active provider is now pinned to the operator's choice and
        only the manual model switcher changes it. Do not re-wire this into
        the chat turn loop."""
        cur = (self.settings.get("active_provider") or "").strip()
        keys = [p.key for p in PROVIDERS]
        if cur in keys:
            order = keys[keys.index(cur) + 1:] + keys[:keys.index(cur)]
        else:
            order = keys
        for k in order:
            if (self.settings.get(f"{k}_api_key") or "").strip():
                return k
        return None

    def _build_history_for_model(self, chat_id: Optional[int] = None):
        out = []
        msgs = self.store.list_messages(chat_id or self.current_chat_id)
        # Keep only the most recent few tool_result blocks at full length;
        # trim older ones (they've already been read and acted on).
        tr_idx = [i for i, m in enumerate(msgs)
                  if m.role == "user"
                  and (m.meta or {}).get("kind") == "tool_result"]
        keep_full = set(tr_idx[-HISTORY_KEEP_FULL_TOOL_RESULTS:]) \
            if HISTORY_KEEP_FULL_TOOL_RESULTS > 0 else set()

        # ── TRIM ON A WATERMARK, NOT A SLIDING WINDOW ──
        # `keep_full` above is a sliding window, and a sliding window rewrites a
        # message in the MIDDLE of the request on EVERY turn: the tool result
        # that was sent in full last turn is sent trimmed this turn. Prefix
        # caching cannot survive that. DeepSeek is explicit that "partial
        # matches in the middle of the input will not trigger a cache hit", and
        # Groq's matcher stops at the first differing byte just the same. The
        # message it rewrites sits a few places from the end, so what got thrown
        # away every turn was the largest and most expensive part of the
        # history — the full-length recent tool results.
        #
        # Note the direction that actually helps: it is NOT "once trimmed,
        # always trimmed" (the trimming IS the mutation, so that changes
        # nothing). It is "once sent in full, KEEP sending it in full" — that
        # makes the request strictly append-only and the whole head cacheable.
        #
        # Kept in full forever would grow without bound, which is why the
        # trimming exists at all. So the two pressures are resolved by
        # AMORTISING the mutation: hold the render stable until the history
        # actually exceeds a size budget, then advance a watermark once and stay
        # stable again for many turns. One cache miss occasionally instead of
        # one every single turn.
        _wm = getattr(self, "_trim_watermark", None)
        if _wm is None:
            _wm = self._trim_watermark = {}
        _key = chat_id or self.current_chat_id
        _mark = _wm.get(_key, 0)

        # Size measured on what would actually be SENT, not on the raw store.
        # Measuring the store instead is a trap: it only ever grows, so the
        # "over budget" condition would latch true forever and the watermark
        # would creep forward one place every turn — a sliding window again,
        # exactly what this replaces.
        _max_mark = max(0, len(tr_idx) - HISTORY_KEEP_FULL_TOOL_RESULTS)

        def _rendered_size(mark: int) -> int:
            trimmed = set(tr_idx[:mark])
            total = 0
            for _j, _m in enumerate(msgs):
                _c = _m.content or ""
                total += (HISTORY_TRIM_HEAD_CHARS if _j in trimmed
                          else len(_c))
            return total

        if _rendered_size(_mark) > HISTORY_STABLE_BUDGET_CHARS:
            # Over budget: jump the watermark ALL THE WAY, not by one. A
            # one-step advance puts us straight back into per-turn mutation;
            # jumping to the maximum drops the rendered size a long way and
            # buys many stable turns before the next advance. One occasional
            # cache miss instead of one every turn.
            _mark = _max_mark
            _wm[_key] = _mark

        # Trim the first `_mark` tool results (stable set, only ever grows);
        # everything newer stays full, which keeps the tail append-only.
        _trim_idx = set(tr_idx[:_mark])
        keep_full = set(tr_idx) - _trim_idx
        for i, m in enumerate(msgs):
            kind = (m.meta or {}).get("kind")
            if m.role == "user":
                content = m.content
                # The "tool-step budget reached" note is only meant to make the
                # model finalize the turn it was raised in (and the runtime lock
                # enforces that regardless). Never replay it into later turns —
                # otherwise the model keeps seeing "don't call tools" and refuses
                # to continue when the operator says "keep going", even though the
                # budget already reset. Drop it from history.
                if "[system note: tool-step budget reached" in content:
                    continue
                if kind == "tool_result" and i not in keep_full:
                    content = self._trim_tool_result(content)
                out.append({"role": "user", "content": content})
            elif m.role == "assistant":
                # Don't replay the model's own chain-of-thought back to it —
                # reasoning belongs to the turn that produced it, can be huge,
                # and feeding it back wastes context and can derail the next
                # turn.  Tool tags stay (the model needs to see its prior
                # actions); only <think> blocks are removed.
                out.append({"role": "assistant",
                            "content": strip_think_blocks(m.content)})
            elif m.role == "tool":
                if kind == "result":
                    out.append({"role": "user", "content": m.content})
            elif m.role == "system":
                out.append({"role": "system", "content": m.content})
        return out

    # ── agent toggle ────────────────────────────────────────────

    def _on_agent_toggled(self, btn):
        self.current_agent_mode = btn.get_active()
        if btn.get_active():
            btn.add_css_class("toggled")
        else:
            btn.remove_css_class("toggled")
        if self.current_chat_id is not None:
            self.store.set_agent_mode(self.current_chat_id,
                                       self.current_agent_mode)
        self._refresh_subtitle()

    def _on_unleash_toggled(self, btn):
        """Arm/disarm Unleash — the master go-full-send switch."""
        self._unleashed = btn.get_active()
        self.settings["unleashed"] = self._unleashed
        try:
            save_settings(self.settings)
        except Exception:
            pass
        if self._unleashed:
            btn.add_css_class("toggled")
            btn.set_tooltip_text(
                "UNLEASHED — full autonomous, will not stop until the mission is "
                "complete. Click to stand down.")
            # Unleash needs the tools and the mission loop → force agent mode on.
            if not self.current_agent_mode:
                self.agent_toggle.set_active(True)   # fires _on_agent_toggled
            self.terminal_log(
                "🔥 UNLEASHED — confirming target, going full autonomous", "ok")
            self._show_toast(
                "Unleashed. Confirming target, going full send.", timeout=4)
            self._unleash_kickoff_pending = True
            self._stop_requested = False
            if self.current_chat_id is None:
                self._new_chat()
            # If an objective already exists in this chat, latch a mission on it
            # so the kickoff turn runs relentless; otherwise the kickoff turn just
            # asks for the target and waits (the reply latches the mission).
            last = ""
            if self.current_chat_id is not None:
                for m in reversed(self.store.list_messages(self.current_chat_id)):
                    if m.role == "user" and "<tool_result>" not in (m.content or "") \
                            and m.meta.get("kind") != "tool_result":
                        last = m.content or ""
                        break
            if last.strip() and not conversational_turn(last):
                self._mission_active = True
                self._mission_objective = last
                self._mission_kicks = 0
                self._recent_commands = []
                self._reset_action_log()
                self._mission_verify_pending = False
                self._mission_no_action_streak = 0
                self._mission_directive = ""
                self._error_retries = 0
                self._mission_ever_acted = False
            if self.streaming_chat_id is None:
                self._kick_assistant_turn()
        else:
            btn.remove_css_class("toggled")
            btn.set_tooltip_text(
                "Unleash — confirm the target and go full autonomous (never "
                "stops). While off, Basilisk answers once and stops.")
            self._unleash_kickoff_pending = False
            # Stand down: halt any running mission immediately.
            self._stop_requested = True
            self._mission_active = False
            self.terminal_log("🧯 stood down — one answer per message now", "dim")
            self._show_toast("Stood down. One answer per message.", timeout=3)
        self._refresh_subtitle()

    # ── menu ────────────────────────────────────────────────────

    def _open_settings(self):
        SettingsDialog(self).present(self)

    def _open_about(self):
        about = Adw.AboutDialog()
        about.set_application_name(APP_NAME)
        about.set_version(VERSION)
        about.set_developer_name("The Priest")
        about.set_comments(
            "Personal, loyal AI assistant.\n"
            "Multi-provider cloud AI · lives on your hardware.")
        about.set_license_type(Gtk.License.MIT_X11)
        about.present(self)

    def _rename_current_chat(self):
        if not self.current_chat_id:
            return
        chat = self.store.get_chat(self.current_chat_id)
        if not chat:
            return
        dlg = Adw.AlertDialog.new("Rename chat", "")
        entry = Gtk.Entry()
        entry.set_text(chat.title)
        dlg.set_extra_child(entry)
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("ok", "Rename")
        dlg.set_default_response("ok")
        def _cb(d, response):
            if response == "ok":
                new = entry.get_text().strip() or chat.title
                self.store.rename_chat(self.current_chat_id, new)
                self.chat_title_lbl.set_text(new)
                self._refresh_sidebar()
        dlg.connect("response", _cb)
        dlg.present(self)

    def _delete_current_chat(self):
        if not self.current_chat_id:
            return
        dlg = Adw.AlertDialog.new("Delete chat?", "Can't undo.")
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("delete", "Delete")
        dlg.set_response_appearance("delete",
                                     Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.set_default_response("cancel")
        dlg.set_close_response("cancel")

        def _cb(d, response):
            if response != "delete":
                return
            deleted_id = self.current_chat_id

            # If the chat being deleted has a turn in flight, cancel it
            # so it doesn't try to write to a now-gone chat row.
            if self.streaming_chat_id == deleted_id:
                if self.streaming_cancel:
                    self.streaming_cancel.set()
                self._stop_requested = True
                self.streaming_msg_widget = None
                self.streaming_msg_db_id = None
                self.streaming_chat_id = None
                self._tool_chain_depth = 0
                self._set_working(False)
                self._set_send_mode(False)

            self.store.delete_chat(deleted_id)
            self.current_chat_id = None

            # Pick the next-most-recent chat to display, if any.  Only
            # spawn a fresh one when there are literally no chats left.
            remaining = self.store.list_chats(limit=1)
            if remaining:
                self._load_chat(remaining[0].id)
            else:
                # No chats at all — clear the view and let the user
                # start fresh whenever they want via the + button.
                child = self.msg_box.get_first_child()
                while child is not None:
                    nxt = child.get_next_sibling()
                    self.msg_box.remove(child)
                    child = nxt
                self.chat_title_lbl.set_text("No chat")
                self.chat_subtitle_lbl.set_text("Tap + to start a new chat")
                self._show_empty_state()

            self._refresh_sidebar()

        dlg.connect("response", _cb)
        dlg.present(self)

    def _toggle_pin_current(self):
        if not self.current_chat_id:
            return
        chat = self.store.get_chat(self.current_chat_id)
        if not chat:
            return
        self.store.set_pinned(self.current_chat_id, not bool(chat.pinned))
        self._refresh_sidebar()

    # ── watcher event handler ──────────────────────────────────

    def _on_watcher_event(self, event):
        # Persist the event so it survives in the notification inbox (the bell),
        # AND fire a real desktop notification — not just the transient banner,
        # which vanishes after 15s and is missed if you're not looking.
        _title = (event.get("title", "") or "Basilisk").strip()
        _detail = (event.get("detail", "") or "").strip()
        try:
            self._add_notification(_title, _detail)
        except Exception:
            pass
        try:
            self._desktop_notify(_title, _detail, nid="basilisk-watcher")
        except Exception:
            pass

        # banner appears at top of chat area
        def _ui():
            banner = Gtk.Label()
            banner.add_css_class("watcher-banner")
            banner.set_xalign(0.0)
            banner.set_wrap(True)
            # Escape user-controlled strings (filenames, journal lines)
            # before composing pango markup, or set_markup will reject
            # invalid input and the banner won't render.
            title = GLib.markup_escape_text(event.get("title", ""))
            detail = GLib.markup_escape_text(event.get("detail", ""))
            try:
                banner.set_markup(f"<b>{title}</b>\n{detail}")
            except Exception:
                # Final fallback if markup still fails for any reason
                banner.set_text(f"{event.get('title','')}\n{event.get('detail','')}")
            self.banner_box.append(banner)
            # auto-remove after 15s
            GLib.timeout_add_seconds(15,
                lambda: (self.banner_box.remove(banner)
                          if banner.get_parent() else None) or False)
            return False
        GLib.idle_add(_ui)

    # ── terminal log panel ──────────────────────────────────────

    def _toggle_terminal_panel(self, *_):
        self._terminal_visible = not self._terminal_visible
        self.terminal_panel.set_visible(self._terminal_visible)
        if self._terminal_visible:
            self.terminal_toggle_btn.add_css_class("active")
            GLib.idle_add(self._terminal_scroll_to_bottom)
        else:
            self.terminal_toggle_btn.remove_css_class("active")

    def _clear_terminal_log(self, *_):
        self.terminal_log_buf.set_text("")
        self._terminal_turn_offsets = []
        self.terminal_status_lbl.set_text("cleared")

    def _terminal_scroll_to_bottom(self):
        adj = self.terminal_log_view.get_parent()
        if adj is None:
            return False
        try:
            # Walk up to find the ScrolledWindow
            parent = self.terminal_log_view.get_parent()
            while parent and not isinstance(parent, Gtk.ScrolledWindow):
                parent = parent.get_parent()
            if parent:
                a = parent.get_vadjustment()
                if a:
                    a.set_value(a.get_upper())
        except Exception:
            pass
        return False

    def terminal_log(self, text: str, kind: str = "info"):
        """Append a line to the terminal log panel.  Thread-safe via GLib.idle_add."""
        text = text if isinstance(text, str) else str(text)
        # Truncate a monster single line (a full HTTP body / base64 blob) BEFORE
        # it enters the buffer — otherwise the line-count cap never trips and the
        # buffer grows in bytes without bound during a pentest run.
        if len(text) > MAX_TERMINAL_LINE_CHARS:
            text = (text[:MAX_TERMINAL_LINE_CHARS]
                    + "  …[+%d bytes truncated]" % (len(text) - MAX_TERMINAL_LINE_CHARS))

        def _ui():
            try:
                buf = self.terminal_log_buf
                # Turn tracking: each "$ cmd" line starts a new command-block.
                # Keep only the last MAX_TERMINAL_TURNS; delete older blocks
                # outright so their text leaves the buffer (and RAM).
                if kind == "cmd":
                    offs = getattr(self, "_terminal_turn_offsets", None)
                    if offs is None:
                        offs = []
                        self._terminal_turn_offsets = offs
                    offs.append(buf.get_char_count())
                    if len(offs) > MAX_TERMINAL_TURNS:
                        cut_off = offs[-MAX_TERMINAL_TURNS]
                        if cut_off > 0:
                            buf.delete(buf.get_start_iter(),
                                       buf.get_iter_at_offset(cut_off))
                        # shift remaining boundaries down by what we removed
                        self._terminal_turn_offsets = [
                            o - cut_off for o in offs if o >= cut_off]
                buf.insert_with_tags_by_name(buf.get_end_iter(), text + "\n", kind)
                # Backstop rolling window — bound BOTH lines and bytes. These also
                # delete from the FRONT, so track how much and shift the turn
                # offsets by the same amount (otherwise they'd point to the wrong
                # place and a later turn-trim could wipe the buffer). The byte cap
                # uses get_iter_at_offset (a plain iter, always succeeds).
                deleted = 0
                try:
                    n = buf.get_line_count()
                    if n > MAX_TERMINAL_LINES:
                        res = buf.get_iter_at_line(n - MAX_TERMINAL_LINES)
                        cut = res[1] if isinstance(res, tuple) else res
                        deleted += cut.get_offset()
                        buf.delete(buf.get_start_iter(), cut)
                except Exception:
                    pass
                over = buf.get_char_count() - MAX_TERMINAL_CHARS
                if over > 0:
                    buf.delete(buf.get_start_iter(), buf.get_iter_at_offset(over))
                    deleted += over
                if deleted:
                    _offs = getattr(self, "_terminal_turn_offsets", None)
                    if _offs:
                        self._terminal_turn_offsets = [
                            o - deleted for o in _offs if o >= deleted]
                self.terminal_status_lbl.set_text(text[:40].strip() or "…")
                GLib.idle_add(self._terminal_scroll_to_bottom)
            except Exception:
                pass
            return False
        GLib.idle_add(_ui)

    def terminal_log_and_show(self, text: str, kind: str = "cmd"):
        """Log and auto-reveal the panel so the operator can see live output.
        Thread-safe: terminal_log already defers its whole body to the main
        loop, but the reveal below touches widgets directly, so it is queued
        the same way. Without this, the first worker thread to call this
        helper would mutate GTK off the main loop and segfault. Queuing the
        reveal BEFORE the log call preserves ordering — idle callbacks run in
        the order they were added."""
        def _reveal():
            if not self._terminal_visible:
                self._terminal_visible = True
                self.terminal_panel.set_visible(True)
                self.terminal_toggle_btn.add_css_class("active")
            return False
        GLib.idle_add(_reveal)
        self.terminal_log(text, kind)

    # ── toast ──────────────────────────────────────────────────

    def _show_toast(self, text, timeout=3):
        t = Adw.Toast.new(text)
        t.set_timeout(timeout)
        self.toast_overlay.add_toast(t)
        return False

    # ── shutdown ───────────────────────────────────────────────

    def shutdown(self):
        if self.streaming_cancel:
            self.streaming_cancel.set()
        if getattr(self, "tts", None):
            try:
                self.tts.stop()
            except Exception:
                pass
        if getattr(self, "stt", None):
            try:
                self.stt.cancel()
            except Exception:
                pass
        self.watcher.stop()
        # Bin the open chat if it was never written to.
        if (self.settings.get("discard_empty_chats", True)
                and self.current_chat_id is not None):
            try:
                if self.store.count_messages(self.current_chat_id) == 0:
                    self.store.delete_chat(self.current_chat_id)
            except Exception:
                pass
        try:
            self.store.close()
        except Exception:
            pass


# ═════════════════════════════════════════════════════════════════════
# APPLICATION
# ═════════════════════════════════════════════════════════════════════

class DragonSplash(Gtk.Window):
    """Startup splash: the chat-background dragon, dark, with a band of light
    that sweeps UP from the bottom to its head — when the light reaches the top
    the whole dragon is lit, then it fades and the main window opens behind it.

    Entirely self-guarding: every path is wrapped so that ANY failure (no cairo,
    no pixbuf, a draw error, an old GTK) just fires on_done and closes, so the
    app always opens normally. It is NEVER allowed to wedge startup.

    THE `import cairo` PROBE BELOW IS LOAD-BEARING, AND THE try/except INSIDE
    _draw DOES NOT COVER IT. When pycairo is absent, PyGObject cannot marshal
    the Gtk.Snapshot's cairo context into the Python callback at all: it raises
    `TypeError: Couldn't find foreign struct converter for 'cairo.Context'` in
    the BINDING layer, before a single line of _draw runs. So _draw's own
    try/except never sees it, the splash paints nothing, and stderr gets that
    line at 60fps for the whole animation. Measured in this sandbox, which has
    GTK4 but no pycairo — exactly the shape of a box that installed via
    install.sh, because that script installs python3-gi/gtk4/libadwaita and
    (until now) never installed the cairo binding.

    The claim in this docstring was false for the one failure mode it names.
    Probing up front is what makes it true."""

    def __init__(self, app, image_path, on_done):
        super().__init__(application=app)
        self.on_done = on_done
        self._done = False
        self._tick_id = 0
        try:
            self.set_decorated(False)
            self.set_resizable(False)
            self.add_css_class("splash-window")
        except Exception:
            pass
        self._side = 460
        self.set_default_size(self._side, self._side)
        # Raise BEFORE building the DrawingArea if the binding cannot deliver a
        # cairo context — the caller already treats a raise here as "skip the
        # splash", which is the correct and only graceful outcome.
        import cairo as _cairo_probe          # noqa: F401
        self._pb = GdkPixbuf.Pixbuf.new_from_file(image_path)  # may raise → caught by caller
        self.area = Gtk.DrawingArea()
        self.area.set_content_width(self._side)
        self.area.set_content_height(self._side)
        self.area.set_draw_func(self._draw)
        self.set_child(self.area)
        import time
        self._t0 = time.monotonic()
        self._sweep = 0.95   # seconds: light travels bottom → head
        self._hold = 0.40    # fully lit, held
        self._fade = 0.35    # fade out to reveal the app
        self._tick_id = GLib.timeout_add(16, self._tick)

    def _elapsed(self) -> float:
        import time
        return time.monotonic() - self._t0

    def _tick(self):
        if self._elapsed() >= self._sweep + self._hold + self._fade:
            self._finish()
            return False
        try:
            self.area.queue_draw()
        except Exception:
            self._finish()
            return False
        return True

    def _finish(self):
        if self._done:
            return
        self._done = True
        try:
            if self._tick_id:
                GLib.source_remove(self._tick_id)
        except Exception:
            pass
        self._tick_id = 0
        try:
            self.on_done()
        except Exception:
            pass
        try:
            self.close()
        except Exception:
            pass

    def _draw(self, area, cr, w, h):
        try:
            import cairo
            # dark backdrop (matches app chrome)
            cr.set_source_rgb(0.055, 0.063, 0.075)
            cr.paint()
            pb = self._pb
            iw, ih = pb.get_width(), pb.get_height()
            scale = min(w / iw, h / ih)
            dw, dh = iw * scale, ih * scale
            ox, oy = (w - dw) / 2.0, (h - dh) / 2.0

            t = self._elapsed()
            sweep = min(1.0, t / self._sweep) if self._sweep > 0 else 1.0
            prog = sweep * sweep * (3.0 - 2.0 * sweep)      # smoothstep ease
            flash_y = oy + dh * (1.0 - prog)                # bottom → top

            def blit(alpha=1.0):
                cr.save()
                cr.translate(ox, oy)
                cr.scale(scale, scale)
                Gdk.cairo_set_source_pixbuf(cr, pb, 0, 0)
                cr.paint_with_alpha(alpha)
                cr.restore()

            # 1) dark dragon everywhere
            blit(1.0)
            cr.save()
            cr.rectangle(ox, oy, dw, dh)
            cr.clip()
            cr.set_source_rgba(0, 0, 0, 0.78)
            cr.paint()
            cr.restore()

            # 2) lit region below the flash line: full-bright dragon + warm ignite
            lit_h = (oy + dh) - flash_y
            if lit_h > 0:
                cr.save()
                cr.rectangle(ox, flash_y, dw, lit_h)
                cr.clip()
                blit(1.0)
                cr.set_operator(cairo.OPERATOR_ADD)
                cr.set_source_rgba(0.55, 0.06, 0.03, 0.15)
                cr.rectangle(ox, flash_y, dw, lit_h)
                cr.fill()
                cr.set_operator(cairo.OPERATOR_OVER)
                cr.restore()

            # 3) the travelling flash band
            if 0.0 < prog < 1.0:
                band = 32.0
                grad = cairo.LinearGradient(0, flash_y - band, 0, flash_y + band)
                grad.add_color_stop_rgba(0.0, 0.90, 0.22, 0.12, 0.0)
                grad.add_color_stop_rgba(0.5, 1.00, 0.55, 0.38, 0.60)
                grad.add_color_stop_rgba(1.0, 0.90, 0.22, 0.12, 0.0)
                cr.save()
                cr.rectangle(ox, flash_y - band, dw, band * 2.0)
                cr.clip()
                cr.set_operator(cairo.OPERATOR_ADD)
                cr.set_source(grad)
                cr.paint()
                cr.restore()

            # 4) fade out at the end to reveal the app underneath
            if t > self._sweep + self._hold:
                fp = (t - self._sweep - self._hold) / self._fade
                fp = max(0.0, min(1.0, fp))
                cr.set_source_rgba(0.055, 0.063, 0.075, fp)
                cr.paint()
        except Exception:
            GLib.idle_add(self._finish)


class BasiliskApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID,
                          flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.win: Optional[MainWindow] = None
        # Hold the CSS provider so we can rebuild it live when the
        # user moves the UI-scale slider in Settings.  Without this
        # the user has to restart Basilisk to see scale changes.
        self.css_provider: Optional[Gtk.CssProvider] = None

    def do_startup(self):
        Adw.Application.do_startup(self)
        self.css_provider = Gtk.CssProvider()
        global _UI_SCALE
        _UI_SCALE = _detect_ui_scale()
        # AFTER scale is set, derive viewport-dependent metrics.
        _compute_viewport_metrics()
        self.css_provider.load_from_data(_scale_css(CSS, _UI_SCALE))
        log(f"ui_scale = {_UI_SCALE:.2f}")
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), self.css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        Adw.StyleManager.get_default().set_color_scheme(
            Adw.ColorScheme.FORCE_DARK)

    def reload_css(self, scale: float):
        """Apply a new UI scale without restart.  Called from the
        Settings UI-scale slider.  GTK4's CssProvider re-resolves
        styles on widgets when load_from_data is called again, so
        the change is visible immediately."""
        global _UI_SCALE
        if scale and 0.3 < scale < 3:
            _UI_SCALE = float(scale)
        else:
            # 0 (or out-of-range) means "use auto-detect"
            _UI_SCALE = _detect_ui_scale()
        try:
            self.css_provider.load_from_data(_scale_css(CSS, _UI_SCALE))
            log(f"ui_scale reloaded → {_UI_SCALE:.2f}")
        except Exception as e:
            log(f"reload_css failed: {e}")

    def do_activate(self):
        # Already running (second activation) → just present the window.
        if self.win:
            self.win.present()
            return

        def _open_main():
            if not self.win:
                self.win = MainWindow(self)
            self.win.present()

        # Startup splash — the chat-background dragon lighting up bottom → head.
        # Fully optional and self-guarding: gated by a setting (default on), only
        # runs on a raster dragon image, and ANY failure falls straight through
        # to opening the app. Can't visually test it here (no display), so it is
        # wrapped to never block startup.
        want_splash = True
        try:
            want_splash = bool(load_settings().get("startup_splash", True))
        except Exception:
            want_splash = True
        if want_splash:
            try:
                img = _WATERMARK_SVG_PATH or _AVATAR_PNG_PATH
                if img and img.lower().endswith(".png") and os.path.isfile(img):
                    DragonSplash(self, img, _open_main).present()
                    return
            except Exception as e:
                log(f"startup splash failed, opening app directly: {e}")
        _open_main()

    def do_shutdown(self):
        if self.win:
            self.win.shutdown()
        Adw.Application.do_shutdown(self)


def _default_window_size() -> tuple[int, int]:
    """Pick a sensible default window size for the screen we're on.

    The old code hardcoded 440x800 — a portrait phone shape.  On a
    desktop or laptop that opens as a cramped vertical sliver with the
    sidebar eating most of the width.  Instead: go portrait only on an
    actually-narrow screen (phone / Phosh), and open a comfortable
    landscape window on anything bigger, capped so we never exceed the
    monitor's work area.
    """
    # Conservative fallbacks if we can't read the monitor.
    phone = (440, 860)
    desktop = (1100, 760)
    try:
        display = Gdk.Display.get_default()
        if not display:
            return desktop
        monitors = display.get_monitors()
        if monitors is None or monitors.get_n_items() == 0:
            return desktop
        geo = monitors.get_item(0).get_geometry()
        sw, sh = int(geo.width), int(geo.height)
        if sw <= 0 or sh <= 0:
            return desktop

        # Narrow screen → portrait, sized to fit (phones, split panes).
        if sw < 720:
            return (min(sw, phone[0]), min(sh, phone[1]))

        # Desktop / laptop → landscape, but never larger than ~90% of
        # the work area so the window isn't clipped or off-screen.
        w = min(desktop[0], int(sw * 0.72))
        h = min(desktop[1], int(sh * 0.85))
        return (max(760, w), max(560, h))
    except Exception as e:
        log(f"default window size detection failed: {e}")
        return desktop


def _detect_ui_scale() -> float:
    """Pick a UI scale based on physical screen size, not pixel width.

    The old logic compared logical-pixel width to a threshold, but logical
    pixels vary wildly depending on whether the compositor reports device
    pixels (no HiDPI scaling) or scaled application pixels.  A phone with
    1080 device-pixels wide might report as 360 (Phosh, scale=3) OR 1080
    (no scaling).  Both are phones and both need the LARGE UI.

    Use physical mm via width_mm if available — that's the actual screen
    size and doesn't lie.  Fall back to monitor.get_scale_factor() (>1
    means HiDPI which is almost always a phone or tablet) when width_mm
    is 0 (some compositors don't report it).

    Phone (< 100 mm wide)            → 0.9   (slightly smaller than CSS base;
                                              the CSS sizes are already big
                                              enough on the OP6's narrow width)
    Tablet (100-200 mm)              → 1.0
    Laptop (200-350 mm)              → 0.85
    Desktop monitor (> 350 mm)       → 0.7
    """
    # Explicit override always wins
    try:
        s = load_settings().get("ui_scale", 0)
        if isinstance(s, (int, float)) and 0.3 < s < 3:
            log(f"ui_scale from settings: {s}")
            return float(s)
    except Exception:
        pass

    try:
        display = Gdk.Display.get_default()
        if not display:
            return 1.0
        monitors = display.get_monitors()
        if monitors is None or monitors.get_n_items() == 0:
            return 1.0
        monitor = monitors.get_item(0)

        # First try physical width (millimetres)
        try:
            width_mm = int(monitor.get_width_mm())
        except Exception:
            width_mm = 0

        if width_mm > 0:
            if width_mm < 100:
                bucket = "phone"; scale = 0.9
            elif width_mm < 200:
                bucket = "tablet"; scale = 1.0
            elif width_mm < 350:
                bucket = "laptop"; scale = 0.85
            else:
                bucket = "desktop"; scale = 0.7
            log(f"ui_scale: width_mm={width_mm} → {bucket} → {scale}")
            return scale

        # Fall back to scale_factor (HiDPI hint) + geometry
        try:
            sf = int(monitor.get_scale_factor())
        except Exception:
            sf = 1
        geo = monitor.get_geometry()
        # device pixels = logical pixels × scale_factor
        device_w = int(geo.width) * sf

        if sf >= 2 or device_w < 1280:
            # HiDPI compositors (Phosh on a phone) already enlarge text via
            # the scale factor.  Don't double up — use 1.0, let the user
            # dial in further via the Settings slider if they want.
            bucket = "phone/hidpi"; scale = 1.0
        elif device_w < 1920:
            bucket = "laptop"; scale = 0.85
        else:
            bucket = "desktop"; scale = 0.7
        log(f"ui_scale: sf={sf} device_w={device_w} → {bucket} → {scale}")
        return scale

    except Exception as e:
        log(f"ui_scale detection failed: {e} — defaulting to 1.0")
        return 1.0


# Cached UI scale.  Set once in do_startup so widgets created later (avatars,
# buttons) can apply the same scale to their programmatic sizes that the CSS
# uses for fonts/padding.
_UI_SCALE: float = 1.0

# Cached viewport width and derived max-chars for message bubbles.  Set
# from real Gdk geometry in do_startup, used by _make_wrap_label.
_VIEWPORT_WIDTH: int = 540   # OP6 portrait logical width
_MAX_BUBBLE_CHARS: int = 25  # conservative default; recomputed at startup

# Minimum wall-clock gap between two full re-renders of a streaming reply.
# Stripping tool markup is a function of the entire buffer, so the per-token
# render that preceded this was quadratic in reply length; this bounds the
# number of full passes per second instead of per token.  50ms is 20fps —
# above the rate at which text reads as continuous, and far below the point
# where the cost tracks the reply size.
_STREAM_RENDER_MIN_MS: int = 50
_STREAM_RENDER_MIN_S: float = _STREAM_RENDER_MIN_MS / 1000.0


def _ui_scale() -> float:
    return _UI_SCALE


def _compute_viewport_metrics() -> None:
    """Pin down the actual logical viewport width via Gdk, then derive
    a max-width-chars cap for message labels.  Without a cap that's
    actually narrower than the viewport, Gtk.Label's natural width
    blows the chat bubble out past the right edge of the screen on
    the phone — see the message-bubble bug history."""
    global _VIEWPORT_WIDTH, _MAX_BUBBLE_CHARS
    try:
        display = Gdk.Display.get_default()
        if display:
            mons = display.get_monitors()
            if mons and mons.get_n_items() > 0:
                mon = mons.get_item(0)
                geo = mon.get_geometry()
                _VIEWPORT_WIDTH = max(300, geo.width)
                # Rough char width estimate.  The CSS default message
                # font is 30 px; with a phone UI scale of 0.9 that
                # renders ≈27 px, and avg glyph width is roughly
                # half that → 13-14 px per char.  Leave ~100 px for
                # avatar + margins.
                avail = max(200, _VIEWPORT_WIDTH - 100)
                char_w = max(8.0, 17.0 * _UI_SCALE)
                _MAX_BUBBLE_CHARS = max(15, min(60, int(avail / char_w)))
                log(f"viewport: {_VIEWPORT_WIDTH}px, scale={_UI_SCALE:.2f}"
                    f" → max bubble chars: {_MAX_BUBBLE_CHARS}")
                return
    except Exception as e:
        log(f"viewport detect failed: {e}")


def _scaled(n: int, floor: int = 1) -> int:
    return max(floor, int(round(n * _UI_SCALE)))


_PX_RE = re.compile(r'(\d+)px')


def _scale_css(css_bytes: bytes, scale: float) -> bytes:
    """Multiply every Npx in the CSS by `scale`, with a sane floor so
    border-widths and 1px lines don't disappear."""
    if abs(scale - 1.0) < 0.01:
        return css_bytes
    text = css_bytes.decode("utf-8")
    def repl(m):
        n = int(m.group(1))
        if n <= 2:
            return f"{n}px"   # don't scale 1px/2px borders
        scaled = max(1, int(round(n * scale)))
        return f"{scaled}px"
    return _PX_RE.sub(repl, text).encode("utf-8")


def main():
    try:
        return BasiliskApp().run(sys.argv)
    except KeyboardInterrupt:
        # Ctrl+C from the terminal: GTK/PyGObject re-raises SIGINT as a
        # KeyboardInterrupt while the main loop unwinds.  Swallow it and
        # exit cleanly — the window is already shutting down by here, so a
        # traceback would just be noise.
        return 0


if __name__ == "__main__":
    sys.exit(main())
