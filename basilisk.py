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

import sys
import os
import gc
import re
import json
import threading
import urllib.request
import datetime
import base64
try:
    from basilisk_btn_art import BTN_ART_B64
except Exception:
    BTN_ART_B64 = {}   # missing module -> art buttons just fall back to symbolic
from typing import List, Dict, Any, Optional, Callable

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
    run_security_audit, format_audit_for_chat,
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
    tool_parse_scan, tool_triage_findings, tool_remediation_hint,
    tool_scope_set, tool_scope_check, tool_scope_show, tool_asset_record,
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
    sudo_cached, detect_urgency, looks_degraded,
    note_command, recent_duplicate,
    parse_tool_calls, strip_tool_calls, shell_block_command,
    extract_think_blocks, strip_think_blocks,
    is_online, is_sensitive_path, command_needs_sudo, is_catastrophic_command,
    command_tampers_self, Watcher,
    PROVIDERS, PROVIDERS_BY_KEY,
    VISION_MODELS,
    get_ledger,
)
from basilisk_persona import (
    build_system_prompt, assemble_messages, title_from_first_message,
    conversational_turn, direct_answer_turn,
)

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
VERSION = "7.5.2"

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
    "the objective RIGHT NOW with a tool call.\n"
    "If this is an exploitation run: consult oracle_status to see what's already "
    "CONFIRMED (never redo a proven exploit) and what's still open, and "
    "oracle_check every hit against its success marker before you count it — a "
    "200 or a plausible-looking response is NOT a solve.\n"
    "Only when the objective is genuinely 100% achieved and verified (or it was "
    "purely a question you have now fully answered) output the exact token "
    + MISSION_COMPLETE_TOKEN + " on its own line to end. NEVER output that token "
    "for partial, assumed, or unverified completion. Otherwise: act.]")
_MISSION_VERIFY_DIRECTIVE = (
    "[MISSION COMPLETION CLAIMED — VERIFY BEFORE ENDING.\n"
    "You signalled this objective is done: {obj}\n"
    "Re-check it point by point against concrete evidence you actually produced "
    "this run. If ANY part is incomplete, unverified, untested, or assumed, "
    "continue working NOW — take the next action. Only if you have concretely "
    "confirmed EVERY part is complete, output " + MISSION_COMPLETE_TOKEN
    + " again on its own line.]")
# Keep this many most-recent tool_result blocks at full length in the
# history resent to the model; older ones get trimmed to a stub (they've
# already been consumed) so a long research chat doesn't re-bill huge
# outputs every turn.
HISTORY_KEEP_FULL_TOOL_RESULTS = 2
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
    box-shadow: inset 0 0 0 1px rgba(200, 210, 222, 0.10);
    animation: metalglow 3s ease-in-out infinite;
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
.chat-scrim { background-color: rgba(0, 0, 0, 0.45); }

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
    padding: 4px 13px;
    color: #9aa3ad;
    background-color: #0e1013;
    border: 1px solid #20262d;
    border-radius: 11px;
    font-size: 12px;
    font-weight: 500;
}
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
    animation: sendglow 1.3s ease-in-out infinite;
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
    background: transparent;
    background-image: none;
    border: none;
    box-shadow: none;
    padding: 2px;
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
/* A Gtk.MenuButton (settings, notifications) wraps its child in an inner
   > button that keeps GTK's default flat-grey styling -- that's the grey box
   around those two.  .art-button only clears the OUTER menubutton, so clear the
   inner button too: fully transparent, no border/shadow, ember glow on hover to
   match the plain art buttons. */
menubutton.art-button > button {
    background: transparent;
    background-image: none;
    border: none;
    box-shadow: none;
    padding: 2px;
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
.msg-user {
    background-color: rgba(30,12,8,0.55);
    background-image: linear-gradient(0deg, rgba(150,50,16,0.12), rgba(60,18,8,0.05) 40%, rgba(0,0,0,0.0) 72%);
    color: #f3e7de;
    border: 1px solid rgba(190,72,28,0.50);
    box-shadow: 0 0 13px rgba(205,70,22,0.34), inset 0 -7px 18px rgba(170,52,16,0.18);
}
.msg-assistant {
    background-color: rgba(22,9,7,0.55);
    background-image: linear-gradient(0deg, rgba(170,55,16,0.11), rgba(70,20,8,0.05) 40%, rgba(0,0,0,0.0) 72%);
    color: #f1e6de;
    border: 1px solid rgba(175,56,22,0.48);
    box-shadow: 0 0 13px rgba(198,64,20,0.32), inset 0 -7px 18px rgba(160,48,15,0.17);
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
"""


# ═════════════════════════════════════════════════════════════════════
# MARKDOWN-LITE RENDERING
# ═════════════════════════════════════════════════════════════════════

CODE_FENCE_RE  = re.compile(r"```([a-zA-Z0-9_+-]*)\n?(.*?)```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
BOLD_RE        = re.compile(r"\*\*([^*\n]+)\*\*")
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


def text_to_pango(text: str) -> str:
    safe = (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))
    safe = BOLD_RE.sub(r"<b>\1</b>", safe)
    safe = ITALIC_RE.sub(r"<i>\1</i>", safe)
    safe = INLINE_CODE_RE.sub(
        r'<span font_family="JetBrains Mono" '
        r'background="#0a0c0f" foreground="#d6ffdf"> \1 </span>',
        safe)
    return safe


def split_message_into_blocks(text: str) -> List[Dict[str, str]]:
    blocks: List[Dict[str, str]] = []
    last = 0
    for m in CODE_FENCE_RE.finditer(text):
        if m.start() > last:
            pre = text[last:m.start()].strip("\n")
            if pre:
                blocks.extend(_split_text_and_images(pre))
        lang = m.group(1) or "text"
        code = m.group(2).rstrip("\n")
        blocks.append({"kind": "code", "lang": lang, "content": code})
        last = m.end()
    tail = text[last:].strip("\n")
    if tail:
        blocks.extend(_split_text_and_images(tail))
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
        copy_btn.connect("clicked", self._on_copy)
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
            parts.append("_" + p + "_")
    more = len(phrases) - 3
    text = "  ".join(parts)
    if more > 0:
        text += "  _(+%d more)_" % more
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
        self.run_btn.connect("clicked", self._on_run_clicked)
        btn_row.append(self.run_btn)

        copy_btn = Gtk.Button(label="Copy")
        copy_btn.add_css_class("cmd-copy-btn")
        copy_btn.connect("clicked", self._on_copy_clicked)
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
        self.apply_btn.connect("clicked", self._on_apply_clicked)
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


def _find_dragon_svg() -> Optional[str]:
    """Locate the dragon emblem SVG at runtime.  Checks the install dir,
    the icon theme dir, and the directory this script lives in (dev/run
    in place).  Returns None if not found so the avatar falls back to a
    letter."""
    candidates = [
        os.path.expanduser("~/.local/share/basilisk/basilisk-dragon.svg"),
        os.path.expanduser(
            "~/.local/share/icons/hicolor/scalable/apps/basilisk-dragon.svg"),
        os.path.expanduser(
            "~/.local/share/icons/hicolor/scalable/apps/"
            "org.thepriest.basilisk.svg"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "basilisk-dragon.svg"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


# Resolved once at import; None if the emblem isn't on disk.
_DRAGON_SVG_PATH = _find_dragon_svg()


def _find_btn_png(name: str) -> Optional[str]:
    """Locate a custom dragon-forged button icon (basilisk-btn-<name>.png), in the
    install dir or next to this module. None if it isn't on disk."""
    fn = "basilisk-btn-%s.png" % name
    for p in (os.path.expanduser("~/.local/share/basilisk/" + fn),
              os.path.join(os.path.dirname(os.path.abspath(__file__)), fn)):
        if os.path.isfile(p):
            return p
    return None


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
    candidates = [
        os.path.expanduser("~/.local/share/basilisk/basilisk-avatar.png"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "basilisk-avatar.png"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


_AVATAR_PNG_PATH = _find_avatar_png()


def _find_logo_png() -> Optional[str]:
    """Locate the BASILISK wordmark logo (death-metal art) for the header."""
    candidates = [
        os.path.expanduser("~/.local/share/basilisk/basilisk-logo.png"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "basilisk-logo.png"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


_LOGO_PNG_PATH = _find_logo_png()


def _find_watermark_svg() -> Optional[str]:
    """Locate the dragon watermark for the chat background (PNG preferred,
    then SVG).  Falls back to the emblem SVG, then None (no watermark)."""
    candidates = [
        os.path.expanduser("~/.local/share/basilisk/basilisk-watermark.png"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "basilisk-watermark.png"),
        os.path.expanduser("~/.local/share/basilisk/basilisk-watermark.svg"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "basilisk-watermark.svg"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return _DRAGON_SVG_PATH


_WATERMARK_SVG_PATH = _find_watermark_svg()


def _find_cross_svg() -> Optional[str]:
    """Locate the operator's cross emblem (shown as the user avatar)."""
    candidates = [
        os.path.expanduser("~/.local/share/basilisk/basilisk-cross.svg"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "basilisk-cross.svg"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


_CROSS_SVG_PATH = _find_cross_svg()


def _find_priest_png() -> Optional[str]:
    """Locate the operator's portrait (shown as the user avatar)."""
    candidates = [
        os.path.expanduser("~/.local/share/basilisk/basilisk-priest.png"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "basilisk-priest.png"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


_PRIEST_PNG_PATH = _find_priest_png()


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
    try:
        pb = GdkPixbuf.Pixbuf.new_from_file_at_size(path, px, px)
        if pb is None:
            return None
        return Gdk.Texture.new_for_pixbuf(pb)
    except Exception as e:
        log(f"emblem rasterise failed: {e}")
        return None


def Avatar(kind: str = "user") -> Gtk.Widget:
    """Square avatar.  Basilisk shows the dragon emblem; the user shows an
    initial.  Falls back to a letter if the emblem SVG can't be loaded so
    the UI never breaks on a missing file.  Returns a plain Gtk.Image or
    Gtk.Label (both are valid box children) rather than a custom widget
    subclass — simpler and impossible to crash on vfunc mismatch."""
    size = _scaled(52, floor=28)
    if kind == "basilisk" and _AVATAR_PNG_PATH:
        # Preferred: the clean dragon PNG (no ring) as the chat avatar.
        try:
            img = Gtk.Image.new_from_file(_AVATAR_PNG_PATH)
            img.set_pixel_size(size)
            img.set_valign(Gtk.Align.START)
            img.add_css_class("avatar")
            img.add_css_class("avatar-dragon")
            img.set_size_request(size, size)
            return img
        except Exception as e:
            log(f"dragon PNG avatar load failed: {e}")
    if kind == "basilisk" and _DRAGON_SVG_PATH:
        try:
            # Rasterise to a bounded bitmap instead of a live SVG paintable —
            # see _svg_texture: a filtered, many-path emblem rendered live can
            # overflow the GL surface limit and crash the process.  2x the
            # display size keeps it crisp on HiDPI; capped so it stays bounded.
            px = min(max(size * 2, 96), 256)
            tex = _svg_texture(_DRAGON_SVG_PATH, px)
            if tex is not None:
                img = Gtk.Image.new_from_paintable(tex)
            else:
                img = Gtk.Image.new_from_file(_DRAGON_SVG_PATH)
            img.set_pixel_size(size)
            img.set_valign(Gtk.Align.START)
            img.add_css_class("avatar")
            img.add_css_class("avatar-dragon")
            img.set_size_request(size, size)
            return img
        except Exception as e:
            log(f"dragon avatar load failed: {e}")

    if kind == "user" and _PRIEST_PNG_PATH:
        try:
            img = Gtk.Image.new_from_file(_PRIEST_PNG_PATH)
            img.set_pixel_size(size)
            img.set_valign(Gtk.Align.START)
            img.add_css_class("avatar")
            img.add_css_class("avatar-priest")
            img.set_size_request(size, size)
            return img
        except Exception as e:
            log(f"priest avatar load failed: {e}")

    if kind == "user" and _CROSS_SVG_PATH:
        try:
            px = min(max(size * 2, 96), 256)
            tex = _svg_texture(_CROSS_SVG_PATH, px)
            if tex is not None:
                img = Gtk.Image.new_from_paintable(tex)
            else:
                img = Gtk.Image.new_from_file(_CROSS_SVG_PATH)
            img.set_pixel_size(size)
            img.set_valign(Gtk.Align.START)
            img.add_css_class("avatar")
            img.add_css_class("avatar-cross")
            img.set_size_request(size, size)
            return img
        except Exception as e:
            log(f"cross avatar load failed: {e}")

    lbl = Gtk.Label(label="L" if kind == "user" else "K")
    lbl.add_css_class("avatar")
    lbl.add_css_class("avatar-user" if kind == "user" else "avatar-basilisk")
    lbl.set_valign(Gtk.Align.START)
    lbl.set_size_request(size, size)
    return lbl


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
        # Captured model reasoning ("thoughts"): from a reasoning_content
        # stream field and/or inline <think> blocks.  Shown in a collapsed
        # expander the operator can click open.
        self._thoughts: str = (self.meta or {}).get("thoughts", "") or ""
        self._thoughts_container: Optional[Gtk.Box] = None
        self._thoughts_label: Optional[Gtk.Label] = None
        self._show_thoughts: bool = show_thoughts
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
        letting it linger in RAM. Display-only — the message stays in the store."""
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
            content_box.append(inner)
            # Read-aloud control sits UNDERNEATH the message (left-aligned),
            # where it's easy to reach, rather than off on the far right.
            if self._on_speak is not None:
                footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                                 spacing=6)
                footer.add_css_class("msg-footer")
                self.speak_btn = Gtk.Button(label=" Listen")
                self.speak_btn.set_icon_name("audio-volume-high-symbolic")
                self.speak_btn.add_css_class("msg-speak-btn")
                self.speak_btn.set_halign(Gtk.Align.START)
                self.speak_btn.set_tooltip_text("Read this message aloud")
                self.speak_btn.connect(
                    "clicked", lambda *_: self._on_speak(self))
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
            display_text = strip_tool_calls(visible)
        else:
            display_text = text
        # If the assistant message carries only tool calls, don't show a
        # placeholder when at least one is a proposal — the card speaks for
        # itself.  Only fall back to the placeholder for a bare execution
        # tag with no prose and no card.
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
                # This turn DID something — show the real command it ran / what it
                # did (e.g. "$ nmap -sV …", "wrote report.md"), not a generic
                # "thinking". Falls back to the live action title, then working.
                summary = _action_summary(calls)
                if summary:
                    display_text = summary
                else:
                    _act = (_CURRENT_ACTION or "").strip()
                    display_text = "_(%s)_" % _act if _act else "_(working…)_"
            else:
                # No tool calls and no prose in this turn — it really was just
                # reasoning. Only here is "thinking" the honest label.
                display_text = "_(thinking…)_"

        blocks = split_message_into_blocks(display_text) if display_text else []
        for b in blocks:
            if b["kind"] == "code":
                self._blocks_container.append(
                    CodeBlockWidget(b["content"], b["lang"]))
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

    def append_streaming(self, token: str):
        if self._streaming_label is None:
            self.start_streaming()
        self._content += token
        # Hide both tool XML and any inline <think> reasoning from the live
        # reply.  The reasoning (if any) gets captured at finish_streaming /
        # set_content and shown in the collapsible thoughts panel.
        display = strip_tool_calls(strip_think_blocks(self._content))
        self._streaming_label.set_text(display)

    def finish_streaming(self) -> str:
        final = self._content
        self._streaming_label = None
        self.set_content(final)
        return final

    # ── thoughts (model reasoning) ─────────────────────────────────
    def append_thought(self, token: str):
        """Accumulate a reasoning token (from a reasoning_content stream)
        and reveal/refresh the collapsed thoughts expander live."""
        if not token:
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
        self._model_rows = {}   # provider_key -> (combo_row, [names])

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

        # Model picker
        model_row = Adw.ComboRow()
        model_row.set_title("Model")
        model_row.set_subtitle("Biggest first. Use ⟳ to fetch live list.")
        names = list(spec.chain)
        saved = parent.settings.get(f"{spec.key}_model", spec.default_model)
        if saved and saved not in names:
            names.insert(0, saved)   # keep a custom/old selection visible
        model_row.set_model(Gtk.StringList.new(names))
        if saved in names:
            model_row.set_selected(names.index(saved))
        model_row.connect(
            "notify::selected",
            lambda row, _ps, k=spec.key: self._on_provider_model(k, row))
        self._model_rows[spec.key] = (model_row, names)

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

    def _on_provider_model(self, key, row):
        m = row.get_model()
        idx = row.get_selected()
        if m and 0 <= idx < m.get_n_items():
            name = m.get_string(idx)
            if name and not name.startswith("("):
                self.win.settings[f"{key}_model"] = name
                save_settings(self.win.settings)

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
        model_row.set_model(Gtk.StringList.new(names))
        if saved in names:
            model_row.set_selected(names.index(saved))
        self._model_rows[key] = (model_row, names)
        spec = PROVIDERS_BY_KEY.get(key)
        self.win._show_toast(
            f"{spec.label if spec else key}: {len(ids)} models loaded.")

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
        self.streaming_thread: Optional[threading.Thread] = None
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
        self._mission_verify_pending: bool = False   # first completion signal seen
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
        self.msg_box.set_margin_end(8)
        self.msg_scroll.set_child(self.msg_box)
        self.msg_scroll.add_css_class("chat-scroll")

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
                tex = None
                try:
                    tex = Gdk.Texture.new_from_filename(path)
                except Exception:
                    from gi.repository import Gio
                    tex = Gdk.Texture.new_from_file(Gio.File.new_for_path(path))
                opacity = 0.9          # brighter — the dragon should read clearly
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
                pic.set_content_fit(Gtk.ContentFit.CONTAIN)
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

    def _models_priced_high_to_low(self, spec):
        """Order a provider's models most-expensive (biggest) -> cheapest.
        Bigger parameter counts cost more, so sort by the largest 'NNb' / 'NNB'
        number in the model id, descending; ties keep the curated chain order."""
        import re as _re
        def size_of(m):
            nums = _re.findall(r"(\d+(?:\.\d+)?)\s*[bB]\b", m)
            return max((float(n) for n in nums), default=0.0)
        ordered = sorted(
            list(enumerate(spec.chain)),
            key=lambda im: (-size_of(im[1]), im[0]))
        return [m for _i, m in ordered]

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
            for model in self._models_priced_high_to_low(spec):
                short = model.split("/")[-1] if "/" in model else model
                b = Gtk.Button(label=short)
                b.add_css_class("model-pick-row")
                b.set_halign(Gtk.Align.FILL)
                if spec.key == cur_key and model == cur_model:
                    b.add_css_class("model-pick-active")
                b.connect("clicked",
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
        short = model.split("/")[-1] if "/" in model else model
        self._show_toast(f"Now using {spec.label if spec else provider} · {short}")
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

        area.append(actions_row)

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
            self.msg_box.remove(child)
            child = nxt

        msgs = self.store.list_messages(chat_id)

        def _renderable(m):
            # Same rules the append path uses: hide stored tool-result rows,
            # tool 'call' rows, and empty in-flight assistant placeholders.
            if (m.meta or {}).get("kind") == "tool_result":
                return False
            if m.role == "tool":
                return False
            if m.role == "assistant" and not m.content.strip():
                return False
            return True

        renderable = [m for m in msgs if _renderable(m)]
        if not renderable:
            self._show_empty_state()
        else:
            # Only build widgets for the most recent window. Older messages stay
            # safe in the store (and would be trimmed on append anyway) — not
            # building them means opening a long conversation is fast and never
            # spikes RAM, instead of constructing then destroying hundreds of
            # heavy widgets.
            for m in renderable[-MAX_CHAT_ROWS:]:
                self._append_message_widget(m.role, m.content, m.meta)

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

    def _append_message_widget(self, role, content, meta=None):
        # Clear empty state if present
        first = self.msg_box.get_first_child()
        if first is not None and not isinstance(first, MessageWidget):
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
                if isinstance(old, MessageWidget):
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
        # New message → force scroll.  This is when the user sent something
        # or a new assistant turn started; they want to see it.  Mid-stream
        # token updates use the smart _scroll_to_bottom that respects
        # the user reading history above.
        GLib.idle_add(self._force_scroll_to_bottom)
        return w

    def _count_msg_rows(self) -> int:
        n = 0
        c = self.msg_box.get_first_child()
        while c is not None:
            n += 1
            c = c.get_next_sibling()
        return n

    def _scroll_to_bottom(self):
        adj = self.msg_scroll.get_vadjustment()
        if adj is None:
            return False
        # If the user has scrolled UP to read earlier messages, don't
        # yank them back to the bottom on every token.  Only follow if
        # they're already within ~120 px of the bottom.
        at_bottom = (adj.get_value() + adj.get_page_size()
                     >= adj.get_upper() - 120)
        if at_bottom:
            adj.set_value(adj.get_upper())
        return False

    def _force_scroll_to_bottom(self):
        """Unconditional scroll — used when sending a NEW user message
        or loading a chat, where the user expects to see the latest."""
        adj = self.msg_scroll.get_vadjustment()
        if adj is not None:
            adj.set_value(adj.get_upper())
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
            partial = (self.streaming_msg_widget._content or "").strip()
            final_text = partial if partial else "_(stopped)_"
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
            idle_cap = self.settings.get("mission_max_idle_kicks", 3)
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
        GLib.timeout_add(max(1, delay),
                         lambda: self._kick_assistant_turn() or False)

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
        if not text:
            return
        buf.set_text("")

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
        self._maybe_set_title_from_first(cid, text)

        # ── Autonomous mission: THIS message is the objective ──
        # In agent mode, Basilisk works it until it's done or you press Stop —
        # a plain reply never ends it, an error never kills it.  BUT a purely
        # conversational opener (greeting/thanks/opinion) OR a genuine QUESTION
        # ("how does X work?", "should I spray or brute?") is NOT a mission:
        # answering a question should not drop into the relentless loop.  Any
        # message that hints at a real action / names a target still starts one.
        if (self.settings.get("autonomous_persist", True)
                and self.current_agent_mode
                and not conversational_turn(text)
                and not direct_answer_turn(text)):
            self._mission_active = True
            self._mission_objective = text
            self._mission_kicks = 0
            self._recent_commands = []      # fresh objective — clear loop history
            self._mission_verify_pending = False
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
        if self.current_chat_id is None:
            return
        buf.set_text("")
        cid = self.current_chat_id
        # Stored with a tag so the model reads it as a live operator nudge, not a
        # brand-new request. No _kick_assistant_turn — the running loop picks it
        # up on its next step; the model is NOT interrupted.
        self.store.add_message(cid, "user",
                               "[operator suggestion, mid-run — weave this in "
                               "without stopping]: " + text)
        self._append_message_widget("user", text)
        self._show_toast("Suggestion sent — Basilisk will fold it in on its "
                         "next step (still working).", timeout=4)

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
        self.tts.speak_all(getattr(widget, "_content", "") or "")

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

    def _set_working(self, working: bool, label: str = "working…"):
        """Update the permanent status pill in the button row (and the shared
        action phrase). Called from the UI thread. The pill lives in the bottom
        button row, always visible — it reads the action title while working and
        'idle' when not, and never reflows the other buttons."""
        global _CURRENT_ACTION
        if working:
            _CURRENT_ACTION = label
            if hasattr(self, "status_pill_label"):
                self.status_pill_label.set_text(label)
                self.status_pill_spinner.set_visible(True)
                self.status_pill_spinner.start()
                self.status_pill_box.add_css_class("busy")
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
        "code_tooling_check": "checking code scanners",
        "code_scan_plan":     "planning the code scan",
        "parse_scan":         "parsing scanner output",
        "triage_findings":    "triaging findings",
        "remediation_hint":   "looking up the fix",
        "scope_set":          "recording authorised scope",
        "scope_check":        "checking scope",
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
        through the existing BackendRouter so it inherits the fallback chain.
        Blocks the CALLING thread — the sidecar only ever calls this from a
        background thread, never the UI thread.  Tolerant of failure: returns
        "" on any error or timeout so a flaky model never wedges a feature."""
        try:
            if not self.router.any_available():
                return ""
            msgs = [{"role": "system", "content": system},
                    {"role": "user", "content": user}]
            buf = {"t": ""}
            done = threading.Event()
            self.router.stream_chat(
                msgs,
                lambda tok: buf.__setitem__("t", buf["t"] + tok),
                lambda meta: done.set(),
                lambda err: done.set(),
                threading.Event())
            done.wait(timeout=30)
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

    def _kick_assistant_turn(self):
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
        # (#3) Urgency fast-path: if the operator's latest message reads as
        # urgent, tell the model (for THIS turn only) to skip preamble and
        # go straight to the most likely fix.
        if self.settings.get("urgency_fast_path", True) and not self._tools_locked:
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
        _answer_only = (not self._mission_active
                        and (direct_answer_turn(_opening_user)
                             or conversational_turn(_opening_user)))
        # A question must never grind into a tool chain. Autonomous mode is
        # uncapped for MISSIONS (relentless by design), but a question has no
        # mission machinery to stop a runaway chain — and _feed_tool_result keeps
        # re-kicking as long as the model calls tools. So cap it: after a few tool
        # round-trips on a question, lock tools and force the answer THIS turn.
        if _answer_only and self._tool_chain_depth > 4 and not self._tools_locked:
            self._tools_locked = True
            addendum = (addendum + "\n\n[You've already used several tools on "
                        "this question. Do NOT call any more tools — give your "
                        "best, complete answer NOW from what you already have.]"
                        ).strip()
            self.terminal_log("── question tool-cap reached; answering now", "dim")
        if self.settings.get("approval_mode", "none") == "none" and _answer_only:
            addendum = (addendum + "\n\n[AUTONOMOUS MODE — but THIS turn is a "
                "QUESTION, not a task. The operator asked something; give them "
                "the answer, don't launch an operation.\n"
                "- Act directly if you do act: never use `propose`/`propose_edit` "
                "cards; if you genuinely need one tool to answer (e.g. read a "
                "file, look up one fact, run a single check), call it directly.\n"
                "- Use AT MOST ONE tool — and only if you truly can't answer from "
                "what you already know. If you can just answer, just answer.\n"
                "- Then STOP. Do NOT chain tool calls, do NOT keep firing, do NOT "
                "treat this as a mission to grind on. Ending your turn after a "
                "complete answer is correct and expected here — there is no "
                "completion token to emit, just answer and stop.\n"
                "- Answer fully and concretely (this is an expert operator — be "
                "technical and direct), but don't pad it into an essay.]").strip()
            self.terminal_log("💬 direct-answer: question, not a mission", "dim")
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

        if _lean:
            _effort = "light"
        elif (self.current_agent_mode and not self._tools_locked
              and (_hard_now or self._tool_chain_depth
                   >= self.settings.get("hard_effort_step", 3))):
            _effort = "heavy"
            addendum = (addendum + "\n\n[HARD ENGAGEMENT: this is a complex "
                        "operation - think before you move. Reason through the "
                        "current state, form a SPECIFIC hypothesis about what "
                        "to try and why, then act on it. Read each tool result "
                        "carefully instead of skimming, and when something "
                        "fails use what it told you to choose the next move "
                        "rather than repeating blindly. Balance it: enough "
                        "thought to aim, enough action to keep the loop "
                        "moving.]").strip()
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

        if self._mission_active and self._mission_directive:
            addendum = (addendum + "\n\n" + self._mission_directive).strip()
            self._mission_directive = ""

        sysprompt = build_system_prompt(
            agent_mode=(False if _lean else self.current_agent_mode),
            custom_addendum=addendum,
            grouped=(not self.settings.get("max_mode", False)))
        full = assemble_messages(sysprompt, history)
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

        def _on_tok(tok):
            GLib.idle_add(self._on_stream_token, tok)
        def _on_done(meta):
            GLib.idle_add(self._on_stream_done, meta)
        def _on_err(err):
            GLib.idle_add(self._on_stream_error, err)
        def _on_reason(tok):
            GLib.idle_add(self._on_stream_reasoning, tok)

        def _bg():
            self.router.stream_chat(full, _on_tok, _on_done, _on_err,
                                    self.streaming_cancel,
                                    on_reasoning=_on_reason, effort=_effort)

        self.streaming_thread = threading.Thread(target=_bg, daemon=True)
        self.streaming_thread.start()
        self._set_send_mode(True)
        self._set_working(True, "thinking…")
        self.terminal_log("── stream start", "dim")

    def _on_stream_token(self, tok):
        if self.streaming_msg_widget:
            self.streaming_msg_widget.append_streaming(tok)
            # Only scroll if user is on the chat that owns this stream
            if self.streaming_chat_id == self.current_chat_id:
                self._scroll_to_bottom()
            self._feed_tts_stream()
        return False

    def _on_stream_reasoning(self, tok):
        """Reasoning tokens (model 'thoughts') arrive separately from the
        reply; route them to the message's collapsible thoughts panel."""
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
        # Strip the model's <think> reasoning before speaking — only the
        # actual reply should be read aloud, never the chain-of-thought.
        content = strip_think_blocks(self.streaming_msg_widget._content or "")
        if not self._tts_suspended and ("<tool" in content):
            # Model is doing a tool turn — stop streaming this widget's
            # audio.  Drop anything already queued from it.
            self._tts_suspended = True
            self.tts.stop()
            return
        if self._tts_suspended:
            return
        try:
            sentences = self._tts_streamer.feed(content)
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

    def _on_stream_done(self, meta):
        if not self.streaming_msg_widget:
            self._finish_turn_cleanup()
            return False
        final = self.streaming_msg_widget.finish_streaming()
        # Mission completion signal: strip the token from what's shown/stored/
        # spoken, but remember that it fired this turn.
        _mission_done_signal = MISSION_COMPLETE_TOKEN in final
        if _mission_done_signal:
            final = final.replace(MISSION_COMPLETE_TOKEN, "").strip()
            try:
                self.streaming_msg_widget.set_content(final or "_(done)_")
            except Exception:
                pass
        # A stream that reached 'done' cleanly resets the error-retry backoff.
        self._error_retries = 0
        if (self.tts and self.settings.get("tts_enabled")
                and not self._tts_suspended and self._tts_streamer is not None
                and not (meta.get("cancelled") or self._stop_requested)):
            try:
                for sentence in self._tts_streamer.flush(final):
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
        # When the tool budget is spent we lock tools for the final answer
        # turn — ignore anything the model still tried to call.
        if self._tools_locked:
            executable = []
        # ── RECOVERY: the model printed a command instead of calling `run` ──
        # A known model-drift failure: instead of a `run` tool call, the model
        # writes the shell command in a ```bash``` fence. parse_tool_calls finds
        # no tool tag, so it renders as a copyable code block and NEVER executes —
        # the "it gives me commands with a copy banner instead of running them"
        # bug. In autonomous walk-away mode (the operator opted into acting), if
        # NOTHING executable was emitted but the output carries a shell block,
        # recover the first command and run it through the SAME gate (the
        # catastrophic floor in _execute_command still applies). This is
        # deterministic — it doesn't depend on the model getting the format right.
        # ...and only during an ACTIVE MISSION (a task being worked). On a
        # question turn (_mission_active is False, the direct-answer path) the
        # model may legitimately SHOW an example command in a fence — recovering
        # that would auto-run something the operator only ASKED about. So the
        # recovery is scoped to tasks, where acting is the whole point.
        if (not executable and not cancelled and self.current_agent_mode
                and not self._tools_locked and self._mission_active
                and self.settings.get("approval_mode", "none") == "none"):
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
        # Honour the agent-mode toggle and the stop button.  If the user
        # turned agent mode off or hit stop, don't execute even if the
        # model emitted a tool tag.
        if executable and not cancelled and self.current_agent_mode:
            # Progress this turn (a tool is running) → reset the no-progress
            # backoff and clear any pending completion claim (work resumed, so
            # the objective isn't done).
            self._mission_kicks = 0
            self._mission_verify_pending = False
            # It has now ACTED — from here the mission is truly relentless (no
            # idle cap); only Stop or a verified completion ends it.
            self._mission_ever_acted = True
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
                # First executable tool has side effects → one at a time.
                self._set_working(
                    True, self._status_for_call(executable[0]) + "…")
                self._execute_tool_calls(executable[:1])
        else:
            # (#7) Degraded-output check: if the model returned junk (empty,
            # one-word, or stuck repeating) and it wasn't a deliberate stop,
            # flag it.  With auto_fallback_on_degraded on, hop to the next
            # provider that has a key so the NEXT turn retries elsewhere.
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
                    nxt = self._next_provider_with_key()
                    if nxt:
                        self.settings["active_provider"] = nxt
                        save_settings(self.settings)
                        self._refresh_subtitle()
                        self.terminal_log(
                            f"↻ auto-retry {self._degraded_retries}/3 on "
                            f"{nxt}", "dim")
                    else:
                        self.terminal_log(
                            f"↻ auto-retry {self._degraded_retries}/3", "dim")
                    GLib.timeout_add(
                        600, lambda: self._kick_assistant_turn() or False)
                    return
                else:
                    self._degraded_retries = 0
                    self._show_toast(
                        "That reply looked degraded after retries. Tap send to "
                        "try again.", timeout=6)
            elif not cancelled and not executable:
                # A clean, non-degraded settle → reset the retry counter.
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
                    if self._mission_verify_pending:
                        # second confirmation on the forced re-check → accept.
                        self._mission_active = False
                        self._mission_verify_pending = False
                        self.terminal_log("✅ mission complete", "ok")
                        self._show_toast("Mission complete.", timeout=5)
                    else:
                        # first claim → force ONE hard re-verify before ending,
                        # so a premature "done" can't slip through.
                        self._mission_verify_pending = True
                        self._mission_directive = (
                            _MISSION_VERIFY_DIRECTIVE.format(
                                obj=self._mission_objective))
                        self._mission_continue(verify=True)
                        return
                else:
                    # no completion token → keep working toward the objective.
                    self._mission_verify_pending = False
                    self._mission_directive = (
                        _MISSION_CONTINUE_DIRECTIVE.format(
                            obj=self._mission_objective))
                    self._mission_continue()
                    return
            self._finish_turn_cleanup()
        return False

    def _on_stream_error(self, err):
        self.terminal_log(f"✗ stream error: {err}", "error")
        if self.streaming_msg_widget:
            # Preserve any tokens that already streamed in.  Wiping the
            # widget and replacing with just the error text discards
            # potentially useful partial output (an explanation that got
            # cut off, a half-finished tool call, etc).
            partial = self.streaming_msg_widget._content or ""
            sep = "\n\n" if partial.strip() else ""
            final_text = f"{partial}{sep}_(error: {err})_"
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
            self._set_working(True, "retrying after error…")
            GLib.timeout_add(max(1, delay),
                             lambda: self._kick_assistant_turn() or False)
            return False
        self._set_working(False)
        self._set_send_mode(False)
        return False

    # ── tool execution ──────────────────────────────────────────

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
        if n == "code_tooling_check":
            return lambda: tool_code_tooling_check()
        if n == "code_scan_plan":
            return lambda: tool_code_scan_plan(
                a.get("path", a.get("dir", a.get("target", "."))),
                a.get("kind", a.get("type", "auto")),
                a.get("intensity", a.get("depth", "normal")))
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
                a.get("group", a.get("name", a.get("groups", ""))))
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

        def _bg():
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
                return idx, c.name, txt

            workers = max(1, min(TOOL_BATCH_MAX_WORKERS, len(calls)))
            try:
                with concurrent.futures.ThreadPoolExecutor(
                        max_workers=workers) as ex:
                    for idx, name, txt in ex.map(
                            run_one, list(enumerate(calls))):
                        results[idx] = (name, txt)
            except Exception as e:
                GLib.idle_add(self._feed_tool_result,
                              f"batch error: {e}")
                return

            blocks = []
            for n, (name, txt) in enumerate(results, 1):
                blocks.append(f"[tool {n}/{len(results)}: {name}]\n{txt}")
            combined = "\n\n".join(blocks)
            GLib.idle_add(lambda: self.terminal_log(
                f"✓ batch done ({len(calls)} tools)", "ok") or False)
            GLib.idle_add(self._feed_tool_result, combined)

        threading.Thread(target=_bg, daemon=True).start()

    def _execute_tool_calls(self, calls):
        call = calls[0]
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
            "code_tooling_check": lambda a: self._tool_simple(
                lambda: tool_code_tooling_check()),
            "code_scan_plan":     lambda a: self._tool_simple(
                lambda: tool_code_scan_plan(
                    a.get("path", a.get("dir", a.get("target", "."))),
                    a.get("kind", a.get("type", "auto")),
                    a.get("intensity", a.get("depth", "normal")))),
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
                    a.get("group", a.get("name", a.get("groups", ""))))),
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
        fn = dispatch.get(call.name)
        if fn:
            self.terminal_log(f"→ tool: {call.name}({json.dumps(call.args, separators=(',',':'))[:80]})", "info")
            fn(call.args)
        else:
            self.terminal_log(f"✗ unknown tool: {call.name}", "error")
            self._feed_tool_result(f"Unknown tool '{call.name}'.")

    def _feed_tool_result(self, result_text):
        # Route to the chat this turn was started in.  Resolved from
        # streaming_chat_id; if the turn was torn down (stop / delete)
        # it's None and we fall back to the current chat.
        chat_id = self.streaming_chat_id or self.current_chat_id
        self.store.add_message(chat_id, "user",
                                f"<tool_result>\n{result_text}\n</tool_result>",
                                meta={"kind": "tool_result"})
        self.streaming_msg_widget = None
        self.streaming_msg_db_id = None
        # If the operator stopped while the tool was running, record the
        # result for context but don't start another model turn.
        if self._stop_requested:
            self._finish_turn_cleanup()
            return
        # streaming_chat_id stays set — _kick_assistant_turn will preserve it
        self._kick_assistant_turn()

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
        model): TRUSTED sources fetch immediately; ANY OTHER public host (GitHub,
        Wikipedia, a vendor blog, a random site) is held OUTSIDE the autonomous
        loop — it fetches only if the operator granted the domain this session,
        otherwise it raises a non-blocking approval request (notification + Allow
        button) and the agent is told to carry on without it. Internal / private
        / metadata hosts are refused by tool_web_read regardless (SSRF floor)."""
        if web_read_tier(url) == "community":
            dom = self._web_grant_domain(self._url_host(url))
            if dom and dom not in self._web_grants:
                self._request_web_approval(dom, url)
                return {
                    "ok": False,
                    "pending_approval": True,
                    "host": dom,
                    "error": (
                        f"'{dom}' isn't on the trusted-source list, so it's held "
                        "outside the autonomous loop and I can't read it on my "
                        "own. I've put an access request in the notifications "
                        "bell — the operator can Allow it (which unlocks that "
                        "domain for the rest of this session) or ignore it. It is "
                        "NOT auto-granted: I'll continue without it and look for "
                        "another way. Don't re-request it in a loop — move on, "
                        "and if it gets approved I'll be able to read it."),
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
        subdomains) fetches without asking again until the app restarts."""
        domain = (domain or "").strip().lower()
        if domain:
            self._web_grants.add(domain)
        for n in self._notifications:
            if n.get("kind") == "approval" and (n.get("host") or "").lower() == domain:
                n["state"] = "granted"
                n["read"] = True
        self._save_notifications()
        self._refresh_notifications()
        try:
            self.toast_overlay.add_toast(Adw.Toast.new(
                f"Allowed {domain} for this session — Basilisk can read it now."))
        except Exception:
            pass

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

    def _tool_simple(self, fn):
        def _bg():
            try:
                GLib.idle_add(lambda: self.terminal_log(f"→ running {fn.__name__ if hasattr(fn, '__name__') else 'tool'}…", "info") or False)
                result = fn()
                text = json.dumps(result, indent=2, default=str)
                GLib.idle_add(lambda: self.terminal_log("✓ done", "ok") or False)
            except Exception as e:
                # Capture the message NOW — `e` is deleted when this except
                # block exits, but the idle_add lambda runs later in the main
                # loop, so referencing `e` inside it raises NameError.
                msg = str(e)
                text = f"error: {msg}"
                GLib.idle_add(lambda m=msg: self.terminal_log(f"✗ {m}", "error") or False)
            GLib.idle_add(self._feed_tool_result, text)
        threading.Thread(target=_bg, daemon=True).start()

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

            def _bg():
                try:
                    r = self._ext.commit_skill(name, code, test, desc, caps)
                except Exception as e:
                    r = {"ok": False, "error": f"{type(e).__name__}: {e}"}
                if r.get("ok"):
                    self.terminal_log(f"✓ skill saved: {name} "
                                      f"(sandbox: {r.get('tier')})", "ok")
                else:
                    self.terminal_log(f"✗ skill rejected: "
                                      f"{r.get('reason') or r.get('error')}", "error")
                GLib.idle_add(self._feed_tool_result,
                              json.dumps(r, indent=2, default=str))
            threading.Thread(target=_bg, daemon=True).start()

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
            def _bg():
                r = tool_read_file(path)
                GLib.idle_add(self._render_read, r)
            threading.Thread(target=_bg, daemon=True).start()
        if is_sensitive_path(path):
            confirm_sensitive_read_dialog(self, path, lambda allow:
                do_read() if allow
                else self._feed_tool_result(f"denied: {path}"))
        else:
            do_read()

    def _render_read(self, r):
        if not r.get("ok"):
            self._feed_tool_result(f"read_file error: {r.get('error')}")
            return
        body = r["content"]
        header = (f"file: {r['path']} ({r['size']} bytes"
                  f"{' truncated' if r['truncated'] else ''})")
        self._feed_tool_result(f"{header}\n\n{body}")

    def _tool_list_dir(self, path):
        def _bg():
            self.terminal_log(f"→ list_dir {path}", "info")
            r = tool_list_dir(path)
            if not r.get("ok"):
                text = f"list_dir error: {r.get('error')}"
                self.terminal_log(f"✗ {r.get('error')}", "error")
            else:
                lines = [f"dir: {r['path']}", ""]
                for e in r["entries"]:
                    sz = "" if e["is_dir"] else f"  ({e['size']}B)"
                    lines.append(f"  {e['name']}{sz}")
                text = "\n".join(lines)
                self.terminal_log(f"✓ {len(r['entries'])} entries", "ok")
            GLib.idle_add(self._feed_tool_result, text)
        threading.Thread(target=_bg, daemon=True).start()

    def _tool_find_file(self, pattern, search_path, max_results=50,
                        min_size_kb=0, max_size_kb=0,
                        modified_within_days=0):
        def _bg():
            self.terminal_log(f"→ find {pattern} in {search_path}", "info")
            r = tool_find_file(pattern, search_path, max_results,
                               min_size_kb, max_size_kb, modified_within_days)
            if r.get("ok"):
                lines = [f"find {pattern} in {r['search_path']}: "
                         f"{r['count']} hit(s)"]
                for hit in r["found"]:
                    if isinstance(hit, dict):
                        sz = hit.get("size")
                        szs = f"  ({sz}B)" if sz is not None else ""
                        lines.append(f"  {hit.get('path')}{szs}")
                    else:
                        lines.append(f"  {hit}")
                text = "\n".join(lines)
                self.terminal_log(f"✓ {r['count']} found", "ok")
            else:
                text = f"find_file error: {r.get('error')}"
                self.terminal_log(f"✗ {r.get('error')}", "error")
            GLib.idle_add(self._feed_tool_result, text)
        threading.Thread(target=_bg, daemon=True).start()

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
            global build_system_prompt, assemble_messages, title_from_first_message
            build_system_prompt = _kp.build_system_prompt
            assemble_messages = _kp.assemble_messages
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

        def _bg():
            r = tool_write_file(path, content)
            if r.get("ok"):
                parts = [f"wrote {r['path']} ({r['size']} bytes)"]
                if r.get("created"):
                    parts.append("(new file created)")
                if r.get("backup"):
                    parts.append(f"backup: {r['backup']}")
                if r.get("is_python"):
                    base = os.path.basename(r["path"])
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
            GLib.idle_add(self._feed_tool_result, out)
        threading.Thread(target=_bg, daemon=True).start()

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

    def _execute_command(self, command, reason, from_card=False):
        """Confirm (with sudo password if needed), run, feed result back.
        Shared by the model's `run` tool and the card's Run button.

        from_card=True means the operator already approved by clicking Run,
        so we skip the redundant y/n and only surface a dialog when the
        command needs root (to collect the password)."""
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
            self._feed_tool_result(
                "REFUSED. This command is in the catastrophic class — it would "
                "irreversibly destroy the system or its data — so Basilisk will not "
                "run it under any circumstances. There is no override; this is "
                "a hard safety floor. If a human genuinely needs this, they "
                "must do it themselves in a real terminal.\n\n  " + command)
            return

        # ── foresight gate ──
        # Predict consequences before running.  Off unless foresight_enabled.
        # Runs in a background thread so the optional model pass can't freeze
        # the UI, then resumes here.  A `block` (catastrophic / irreversible)
        # refuses outright; a `caution` is surfaced and then proceeds through
        # the normal confirm path.  The _fs_cleared flag stops re-entry.
        if (not getattr(self, "_fs_cleared", False)
                and getattr(self, "_ext", None)
                and self.settings.get("foresight_enabled", False)):
            def _fbg():
                try:
                    v = self._ext.foresight(command)
                except Exception:
                    v = {"verdict": "allow"}
                def _resume():
                    try:
                        from basilisk_ext.foresight import render_card
                    except Exception:
                        render_card = lambda x: ""
                    verdict = v.get("verdict")
                    force_confirm = False
                    if verdict in ("block", "caution"):
                        # Show the consequence card either way so the operator
                        # sees foresight's read in the log.
                        card = render_card(v)
                        if card:
                            self.terminal_log(card, "error")
                        # In autonomous walk-away mode, foresight's CAUTION layer
                        # is advisory ONLY — it logs and lets the command run, so
                        # risky-but-normal pentest commands (curl|bash to fetch a
                        # tool, kill -9 a hung scan, a firewall/route tweak) never
                        # interrupt an unattended engagement. A BLOCK verdict
                        # (disk wipe, mkfs, partition edit, fork bomb — never a
                        # hacking command) still stops for an explicit OK, on top
                        # of the no-override catastrophic floor already enforced
                        # at the execution primitive. Supervised mode stops on
                        # both, as before.
                        force_confirm = (verdict == "block"
                                         or _APPROVAL_MODE != "none")
                    self._fs_cleared = True
                    self._fs_force_confirm = force_confirm
                    try:
                        self._execute_command(command, reason,
                                              from_card=from_card)
                    finally:
                        self._fs_cleared = False
                        self._fs_force_confirm = False
                    return False
                GLib.idle_add(_resume)
            threading.Thread(target=_fbg, daemon=True).start()
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
            def _bg():
                # Log the command but DON'T force the panel open — the
                # operator opens the log themselves with the toggle when
                # they want it.  The command still shows in the status line.
                self.terminal_log(f"$ {command}", "cmd")
                r = tool_run_command(command, timeout=timeout,
                                     sudo_password=password)
                # Record to the evidence ledger (fail-safe: a ledger error must
                # never affect the command result the operator sees).
                try:
                    _led = get_ledger()
                    if _led is not None:
                        _led.record(command, reason, r)
                except Exception:
                    pass
                if r.get("ok"):
                    parts = [f"$ {command}", f"(rc={r['rc']})"]
                    if r["stdout"]:
                        # Stream stdout to terminal log line by line
                        for line in r["stdout"].splitlines()[:80]:
                            GLib.idle_add(lambda l=line: self.terminal_log(l, "stdout") or False)
                        parts.append(r["stdout"])
                    if r["stderr"]:
                        for line in r["stderr"].splitlines()[:20]:
                            GLib.idle_add(lambda l=line: self.terminal_log(l, "stderr") or False)
                        parts.append(f"stderr:\n{r['stderr']}")
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
                        self.terminal_log(f"✓ rc={r['rc']}", "ok" if r['rc'] == 0 else "error")
                    out = "\n".join(parts)
                else:
                    out = f"$ {command}\nerror: {r.get('error')}"
                    self.terminal_log(f"✗ {r.get('error')}", "error")
                GLib.idle_add(self._feed_tool_result, out)
            threading.Thread(target=_bg, daemon=True).start()

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
        def _bg():
            try:
                def _prog(title, done, total):
                    self.terminal_log(f"[{done}/{total}] {title}", "info")
                audit = run_security_audit(on_progress=_prog)
                text = format_audit_for_chat(audit)
                self.terminal_log(f"✓ audit complete — grade {audit['grade']}", "ok")
            except Exception as e:
                text = f"audit failed: {type(e).__name__}: {e}"
                self.terminal_log(f"✗ audit failed: {e}", "error")
            GLib.idle_add(self._feed_tool_result, text)
        threading.Thread(target=_bg, daemon=True).start()

    def _tool_scan_net(self, cidr=None):
        self._show_toast("Scanning network…")
        def _bg():
            try:
                def _prog(msg):
                    self.terminal_log(f"nmap: {msg}", "info")
                scan = run_network_scan(cidr, on_progress=_prog)
                text = format_scan_for_chat(scan)
                if scan.get("ok"):
                    self.terminal_log(f"✓ scan complete — {len(scan.get('hosts', []))} hosts", "ok")
                else:
                    self.terminal_log(f"✗ scan failed: {scan.get('error')}", "error")
            except Exception as e:
                text = f"scan failed: {type(e).__name__}: {e}"
                self.terminal_log(f"✗ {e}", "error")
            GLib.idle_add(self._feed_tool_result, text)
        threading.Thread(target=_bg, daemon=True).start()

    # ── user-initiated chip actions ─────────────────────────────

    def _is_busy(self) -> bool:
        """True when an assistant turn or tool call is in flight."""
        if self.streaming_thread and self.streaming_thread.is_alive():
            return True
        if self.streaming_msg_widget is not None:
            return True
        if self.streaming_chat_id is not None:
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

    def _pick_attachment(self):
        # Gtk.FileDialog is GTK 4.10+.  On older Phosh/NetHunter GTK it doesn't
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
            # Embed an image as markdown pointing at the local file, so it
            # renders inline in the chat (ImageWidget handles file:// URLs)
            # instead of being read as binary garbage.
            buf = self.input_view.get_buffer()
            cur = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
            name = os.path.basename(path)
            ref = f"![{name}](file://{path})"
            buf.set_text(f"{cur}\n{ref}\n" if cur.strip() else f"{ref}\n")
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
        buf = self.input_view.get_buffer()
        cur = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
        body = r["content"]
        new = (f"{cur}\n\n[attached: {path}]\n```\n{body}\n```\n"
               if cur else f"[attached: {path}]\n```\n{body}\n```\n")
        buf.set_text(new)
        return False

    # ── history ─────────────────────────────────────────────────

    def _trim_tool_result(self, content: str) -> str:
        """Shrink an older, already-consumed tool_result so a long research
        chat doesn't re-bill the full (sometimes huge) output every turn."""
        if len(content) <= HISTORY_TRIM_HEAD_CHARS + 200:
            return content
        head = content[:HISTORY_TRIM_HEAD_CHARS]
        return (head + f"\n…[earlier tool output trimmed to save tokens — "
                f"{len(content)} chars originally]\n</tool_result>")

    def _next_provider_with_key(self) -> Optional[str]:
        """Pick the next cloud provider (after the current active one) that
        has an API key set — for degraded-output fallback.  Returns None if
        no other configured provider is available."""
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
        """Log and auto-reveal the panel so the operator can see live output."""
        if not self._terminal_visible:
            self._terminal_visible = True
            self.terminal_panel.set_visible(True)
            self.terminal_toggle_btn.add_css_class("active")
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
    app always opens normally. It is NEVER allowed to wedge startup."""

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
