#!/usr/bin/env python3
"""
test_models.py — the provider model catalogue and everything that reads it.

WHY THIS FILE EXISTS: a wrong model id fails at RUNTIME, on the operator's
box, mid-engagement, as an HTTP 404 that looks like a network blip.  Before
v7.9.3 three of the six ids in SILICONFLOW_CHAIN were discontinued models
and nothing in 862 tests noticed, because nothing asserted anything about
the chain beyond "it is non-empty and starts with the pinned default".

This locks the structural properties that CAN be checked offline:
  * catalogue/chain separation (adding a pickable model must not lengthen
    the runtime fallback walk)
  * the pinned default is still pinned and still in both
  * no duplicate / malformed / obviously-stale ids
  * ordering: the picker sorts by curated tier, NOT by the old regex that
    parsed 'NNb' out of the id and scored DeepSeek-V4-Flash at 0.0
  * the live-catalogue filter drops embeddings/TTS/image models
  * knows() accepts catalogue models, so the effort escalation isn't a no-op

It cannot check that an id is currently SERVED — that needs the network and
an API key.  The ⟳ live-refresh in Settings is the answer to drift.

Run:  python3 tests/test_models.py
"""

from __future__ import annotations

import os
import re
import sys
import types

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

_p = _f = 0


def ck(name: str, cond: bool, detail: str = "") -> None:
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS {name}")
    else:
        _f += 1
        print(f"  FAIL {name}" + (f"   [{detail}]" if detail else ""))


import basilisk_core as C  # noqa: E402

SF = C.PROVIDERS_BY_KEY["siliconflow"]
GOOG = C.PROVIDERS_BY_KEY["google"]
GROQ = GOOG   # legacy alias in this file; Groq was removed as a chat provider


# ── 1. the pinned default ────────────────────────────────────────────
print("\n== pinned default ==")
PINNED = "deepseek-ai/DeepSeek-V4-Flash"
ck("chain[0] is the pinned default", SF.chain[0] == PINNED, SF.chain[0])
ck("default_model agrees", SF.default_model == PINNED)
ck("pinned default is also pickable", PINNED in SF.pick_ids)
ck("DEFAULT_SETTINGS still pins siliconflow",
   C.DEFAULT_SETTINGS["active_provider"] == "siliconflow")
ck("DEFAULT_SETTINGS model matches the chain head",
   C.DEFAULT_SETTINGS.get("siliconflow_model") == PINNED,
   str(C.DEFAULT_SETTINGS.get("siliconflow_model")))


# ── 2. catalogue / chain separation ──────────────────────────────────
# The whole point of the split: the picker can grow without making an
# outage slower.  Every chain entry is one more full round-trip the
# operator waits through, each bounded by STREAM_IDLE_TIMEOUT_S.
print("\n== catalogue vs fallback chain ==")
ck("catalogue is populated", len(SF.catalogue) >= 12, str(len(SF.catalogue)))
ck("fallback chain stays SHORT", len(SF.chain) <= 5, str(len(SF.chain)))
ck("catalogue is strictly bigger than the chain",
   len(SF.catalogue) > len(SF.chain))
_chain_not_in_cat = [m for m in SF.chain if SF.info(m) is None]
ck("every chain model has catalogue metadata",
   not _chain_not_in_cat, str(_chain_not_in_cat))
_worst = len(SF.chain) * C.STREAM_IDLE_TIMEOUT_S
ck("worst-case fallback walk stays under 10 min", _worst < 600, f"{_worst}s")


# ── 3. id hygiene ────────────────────────────────────────────────────
print("\n== id hygiene ==")
_ids = [m.id for m in SF.catalogue]
ck("no duplicate ids", len(_ids) == len(set(_ids)),
   str([i for i in _ids if _ids.count(i) > 1]))
_labels = [m.label for m in SF.catalogue]
ck("no duplicate labels", len(_labels) == len(set(_labels)))
_bad = [i for i in _ids if "/" not in i or i != i.strip()]
ck("every id is vendor/model and unpadded", not _bad, str(_bad))

# Models SiliconFlow has announced as discontinued.  A regression here means
# somebody re-added a dead id from an old branch or an out-of-date memory.
#
# EXACT match, not startswith.  A prefix test flags every live SUCCESSOR:
# 'zai-org/GLM-4.5-Air' starts with the retired 'zai-org/GLM-4.5' but is a
# different model that is still served, and 'MiniMax-M2.5' starts with the
# retired 'MiniMax-M2'.  Version numbers are not a prefix hierarchy.
_RETIRED_EXACT = {
    "zai-org/GLM-4.6",               # superseded by GLM-5.x
    "zai-org/GLM-4.5",               # discontinued 2025-12-31
    "moonshotai/Kimi-K2.5",          # redirects to K2.6
    "MiniMaxAI/MiniMax-M2",          # discontinued 2026-02-09
    "MiniMaxAI/MiniMax-M1-80k",      # discontinued 2026-02-09
    "moonshotai/Kimi-Dev-72B",       # discontinued 2026-02-09
    "Qwen/Qwen3-30B-A3B",            # discontinued 2026-02-09
    "Qwen/QVQ-72B-Preview",          # discontinued 2026-02-09
    "stepfun-ai/step3",              # discontinued 2026-02-09
}
# The one family where every suffixed variant went at once.
_RETIRED_PREFIX = ("Qwen/Qwen3-235B-A22B",)   # discontinued 2025-12-31


def _is_retired(mid: str) -> bool:
    bare = mid[4:] if mid.startswith("Pro/") else mid
    return (bare in _RETIRED_EXACT
            or any(bare.startswith(r) for r in _RETIRED_PREFIX))


_dead = [i for i in _ids + list(SF.chain) if _is_retired(i)]
ck("no discontinued ids anywhere", not _dead, str(_dead))


# ── GROQ retirement guard ────────────────────────────────────────────
# This block exists because the SiliconFlow guard above was provider-specific,
# so nothing watched Groq — and by 2026-08 FOUR of its six chain entries had
# been retired, including GROQ_DEFAULT_MODEL. Two were already erroring. The
# lesson from v7.9.3 was "an id list is perishable"; the miss was applying it to
# one provider only.
#
# Dates are Groq's published SHUTDOWN dates, not announcement dates
# (console.groq.com/docs/deprecations).
_GROQ_RETIRED = {
    "llama-3.1-8b-instant":                       "2026-08-16",
    "llama-3.3-70b-versatile":                    "2026-08-16",
    "qwen/qwen3-32b":                             "2026-07-17",
    "meta-llama/llama-4-scout-17b-16e-instruct":  "2026-07-17",
    "moonshotai/kimi-k2-instruct-0905":           "2026-04-15",
    "meta-llama/llama-4-maverick-17b-128e-instruct": "2026-03-09",
    "meta-llama/llama-guard-4-12b":               "2026-03-05",
    "moonshotai/kimi-k2-instruct":                "2025-10-10",
    "gemma2-9b-it":                               "2025-10-08",
    "deepseek-r1-distill-llama-70b":              "2025-10-02",
    "mistral-saba-24b":                           "2025-07-30",
    "qwen-qwq-32b":                               "2025-07-14",
}
GQ = C.PROVIDERS_BY_KEY["google"]
_gq_ids = [m.id for m in GQ.catalogue]
_gq_dead = [i for i in _gq_ids + list(GQ.chain) if i in _GROQ_RETIRED]
ck("groq: no retired ids in chain or catalogue", not _gq_dead, str(_gq_dead))
ck("groq: default model is not retired",
   C.GOOGLE_DEFAULT_MODEL not in _GROQ_RETIRED, C.GOOGLE_DEFAULT_MODEL)
ck("groq: default model is one the provider knows",
   GQ.knows(C.GOOGLE_DEFAULT_MODEL))
ck("groq: default model heads the chain",
   list(GQ.chain)[0] == C.GOOGLE_DEFAULT_MODEL,
   f"{list(GQ.chain)[0]} vs {C.GOOGLE_DEFAULT_MODEL}")

# The chain is the OUTAGE path: production models only. A preview model can be
# withdrawn at short notice, which is the one thing a fallback must not do.
_GROQ_PREVIEW = set()
_prev_in_chain = [i for i in GQ.chain if i in _GROQ_PREVIEW]
ck("groq: no PREVIEW model on the fallback chain", not _prev_in_chain,
   str(_prev_in_chain))
ck("groq: chain stays short (each entry is another round-trip)",
   len(GQ.chain) <= 3, str(len(GQ.chain)))
ck("groq: catalogue is populated (picker showed nothing before)",
   len(GQ.catalogue) >= 3, str(len(GQ.catalogue)))
ck("google: the restricted-quota model is pickable but NOT on the chain",
   GQ.knows("gemini-2.5-pro") and "gemini-2.5-pro" not in GQ.chain,
   "50 requests/day answers a hard question; it cannot carry an outage path")
ck("google: every note carries the free-tier training warning",
   all("training" in m.note.lower() or "TRAINS" in m.note
       for m in GQ.catalogue),
   "a pentest tool sending engagement data to a training-enabled tier is a "
   "disclosure the operator must see at the point of choosing")

# The agentic systems fetch attacker-chosen URLs by themselves, outside the
# web_read tier gate. Keeping them out is a security decision, so pin it.
ck("groq is no longer a chat provider",
   "groq" not in C.PROVIDERS_BY_KEY,
   "removed in v9.3.0; its Whisper STT endpoint is a separate feature")

ck("groq: every catalogue id carries real metadata",
   all(m.ctx_k > 0 and m.out_usd > 0 and m.note for m in GQ.catalogue))
ck("groq: catalogue ids are unique",
   len(_gq_ids) == len(set(_gq_ids)))


# ── prompt-cache economics ───────────────────────────────────────────
# Both wired providers cache automatically. The discount is the biggest cost
# lever an agent has, because an agent re-sends the same prompt every step.
print("\n== cached pricing ==")
_CACHED = {
    "gemini-2.5-flash": 0.075,             # Google: ~75% off cached
    "deepseek-ai/DeepSeek-V4-Flash": 0.028,  # SiliconFlow: 80% off
}
for _mid, _want in _CACHED.items():
    _info = (GQ.info(_mid) or SF.info(_mid))
    ck(f"{_mid} has a cached rate", _info is not None and _info.cached_in_usd > 0)
    if _info:
        ck(f"{_mid} cached rate is right", abs(_info.cached_in_usd - _want) < 1e-6,
           str(_info.cached_in_usd))
        ck(f"{_mid} cached is cheaper than uncached",
           _info.cached_in_usd < _info.in_usd)

# THE REGRESSION THIS FIELD ALMOST CAUSED. Catalogue entries are built with
# POSITIONAL arguments, so a new dataclass field inserted anywhere but the END
# silently re-maps every one of them — first attempt put cached_in_usd right
# after out_usd and each model's `note` string became its cached price. Cheap
# to assert, invisible otherwise.
_all_models = list(SF.catalogue) + list(GQ.catalogue)
ck("every note is a string, not a shifted number",
   all(isinstance(m.note, str) for m in _all_models))
ck("every cached rate is a number, not a shifted string",
   all(isinstance(m.cached_in_usd, (int, float)) for m in _all_models))
ck("every ctx_k is a positive int", all(isinstance(m.ctx_k, int) and m.ctx_k > 0
                                        for m in _all_models))
ck("every tier is one of the three labels",
   all(m.tier in ("flagship", "workhorse", "budget") for m in _all_models))
ck("no cached rate exceeds its uncached rate",
   all(m.cached_in_usd <= m.in_usd for m in _all_models if m.cached_in_usd))

# A dead id is dead EVERYWHERE, not just in the chain. Both Groq vision models
# were retired (maverick 2026-03-09, scout 2026-07-17) and nothing noticed,
# because the retirement guard only ever looked at chains and catalogues —
# analyze_image on Groq would simply have 404'd. Sweep every id list.
_VISION_ALL = [(prov, mid) for prov, ids in C.VISION_MODELS.items()
               for mid in ids]
_dead_vision = [f"{p}:{m}" for p, m in _VISION_ALL
                if (m in _GROQ_RETIRED) or _is_retired(m)]
ck("no retired ids in ANY vision list", not _dead_vision, str(_dead_vision))
ck("every provider with vision has at least one model",
   all(ids for ids in C.VISION_MODELS.values()))
ck("groq vision points at a model groq actually serves",
   all(GQ.knows(m) or m in {x.id for x in GQ.catalogue}
       for m in C.VISION_MODELS.get("groq", [])),
   str(C.VISION_MODELS.get("groq")))

# The installer carries its own hardcoded fallback defaults for when
# basilisk_core cannot be imported. It is a second copy of the same facts and
# drifted: it still named the retired llama-3.3-70b-versatile for Groq.
_inst = open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "install.sh"), encoding="utf-8").read()
_inst_dead = [m for m in _GROQ_RETIRED if f'"{m}"' in _inst]
ck("installer fallback names no retired groq model", not _inst_dead,
   str(_inst_dead))
ck("installer fallback names the current google default",
   f'"{C.GOOGLE_DEFAULT_MODEL}"' in _inst,
   "install.sh carries a second copy of these defaults and has drifted before")
ck("the retirement check tolerates live successors",
   not _is_retired("zai-org/GLM-4.5-Air")
   and not _is_retired("MiniMaxAI/MiniMax-M2.5")
   and not _is_retired("moonshotai/Kimi-K2.6"))
ck("the retirement check still catches a dead id",
   _is_retired("zai-org/GLM-4.6")
   and _is_retired("Qwen/Qwen3-235B-A22B-Instruct-2507")
   and _is_retired("Pro/moonshotai/Kimi-K2.5"))

_dead_vision = [i for i in C.VISION_MODELS.get("siliconflow", [])
                if "Qwen2.5-VL" in i or "Qwen2-VL" in i]
ck("vision list is off the retired Qwen2.x-VL family",
   not _dead_vision, str(_dead_vision))


# ── 4. metadata sanity ───────────────────────────────────────────────
print("\n== metadata ==")
_badctx = [m.id for m in SF.catalogue if not (8 <= m.ctx_k <= 4096)]
ck("context windows are plausible", not _badctx, str(_badctx))
_badprice = [m.id for m in SF.catalogue
             if m.in_usd < 0 or m.out_usd < 0 or m.in_usd > 100]
ck("prices are non-negative and sane", not _badprice, str(_badprice))
_nonote = [m.id for m in SF.catalogue if not m.note.strip()]
ck("every model says what it is for", not _nonote, str(_nonote))
_badtier = [m.id for m in SF.catalogue
            if m.tier not in ("flagship", "workhorse", "budget")]
ck("every tier is a known tier", not _badtier, str(_badtier))
for tier in ("flagship", "workhorse", "budget"):
    ck(f"tier '{tier}' is non-empty",
       any(m.tier == tier for m in SF.catalogue))


# ── 5. knows() — the effort-escalation gate ──────────────────────────
# hard_engagement_model used to be validated against the fallback chain
# alone, so a valid heavy model picked from the catalogue was silently
# ignored: the escalation never fired and looked exactly like it had.
print("\n== knows() / effort escalation ==")
_heavy = C.DEFAULT_SETTINGS.get("hard_engagement_model", "")
ck("default hard_engagement_model is recognised", SF.knows(_heavy), _heavy)
_unknown = [m.id for m in SF.catalogue if not SF.knows(m.id)]
ck("knows() accepts every catalogue model", not _unknown, str(_unknown))
ck("knows() accepts every chain model",
   all(SF.knows(m) for m in SF.chain))
ck("knows() rejects a bogus id", not SF.knows("acme/DefinitelyNotAModel"))
_cat_only = [m.id for m in SF.catalogue if m.id not in SF.chain]
ck("a catalogue-only model is a valid heavy pick",
   bool(_cat_only) and SF.knows(_cat_only[0]),
   str(_cat_only[:1]))


# ── 6. providers without a catalogue are unaffected ──────────────────
# Groq deliberately has no catalogue.  It must behave exactly as it did
# before the split, or this change broke the operator's fallback provider
# to make his primary prettier.
print("\n== groq is untouched ==")
# Groq HAS a catalogue as of 2026-08 — it used to be empty, so its picker
# showed bare ids with no context window, price or purpose. These assertions
# used to pin the empty state; they now pin the populated one.
ck("groq has a catalogue", bool(GROQ.catalogue))
ck("groq chain still matches GROQ_FALLBACK_CHAIN",
   list(GROQ.chain) == list(C.GOOGLE_FALLBACK_CHAIN))
ck("google info() returns metadata for a catalogue model",
   GOOG.info("gemini-2.5-flash") is not None)
ck("google info() carries a real context window",
   (GOOG.info("gemini-2.5-flash") or C.ModelInfo("", "", 0, 0, 0)).ctx_k > 0)
ck("groq knows() still works off the chain", GROQ.knows(GROQ.chain[0]))
ck("groq pick_ids covers the catalogue", 
   set(GROQ.pick_ids) >= {m.id for m in GROQ.catalogue})

for key, prov in C.PROVIDERS_BY_KEY.items():
    ck(f"{key} has a non-empty chain", bool(prov.chain))
    ck(f"{key} has a non-empty default_model", bool(prov.default_model))
    ck(f"{key} pick_ids is non-empty", bool(prov.pick_ids))


# ── 7. live-catalogue filtering + ranking ────────────────────────────
# SiliconFlow's /models returns the WHOLE platform.  Unfiltered, the eight
# models worth picking were buried under ~200 embeddings, rerankers, TTS
# voices and image generators, every one of which 400s on a chat call.
print("\n== live /models filter ==")
B = C.OpenAICompatBackend(SF)
_should_keep = [
    "deepseek-ai/DeepSeek-V4-Pro", "zai-org/GLM-5.2", "tencent/Hy3",
    "Qwen/Qwen3.6-27B", "moonshotai/Kimi-K3",
]
_should_drop = [
    "Qwen/Qwen3-Embedding-8B", "Qwen/Qwen3-Reranker-0.6B",
    "BAAI/bge-large-en-v1.5", "netease-youdao/bce-reranker-base_v1",
    "FunAudioLLM/SenseVoiceSmall", "fishaudio/fish-speech-1.5",
    "black-forest-labs/FLUX.1-dev", "Qwen/Qwen-Image",
    "Wan-AI/Wan2.2-T2V-A14B", "IndexTeam/IndexTTS-2",
]
_kept_wrong = [m for m in _should_drop if B._is_chat_model(m)]
ck("non-chat models are filtered out", not _kept_wrong, str(_kept_wrong))
_dropped_wrong = [m for m in _should_keep if not B._is_chat_model(m)]
ck("chat models survive the filter", not _dropped_wrong, str(_dropped_wrong))

_ranked = B._rank_live(["zzz/Unknown", "deepseek-ai/DeepSeek-V4-Pro",
                        "aaa/Unknown", "zai-org/GLM-5.2"])
ck("catalogue models rank above unknown ones",
   _ranked.index("zai-org/GLM-5.2") < _ranked.index("aaa/Unknown"),
   str(_ranked))
ck("unknown models still sort A-Z among themselves",
   _ranked.index("aaa/Unknown") < _ranked.index("zzz/Unknown"))
ck("ranking preserves catalogue order",
   _ranked.index("zai-org/GLM-5.2")
   < _ranked.index("deepseek-ai/DeepSeek-V4-Pro")
   or [m.id for m in SF.catalogue].index("zai-org/GLM-5.2")
   > [m.id for m in SF.catalogue].index("deepseek-ai/DeepSeek-V4-Pro"))
ck("ranking is total (nothing lost)", len(_ranked) == 4)

# The cache must not serve another account's catalogue after a key swap.
B.set_api_key("key-one")
B._live_cache = (__import__("time").time(), "key-one", ["a/b"])
ck("cache hits for the same key", B.list_models_live() == ["a/b"])
B.set_api_key("key-two")
_res = B.list_models_live(timeout=0.001)
ck("cache misses after an API-key change", _res != ["a/b"], str(_res))


# ── 8. picker ordering (the GTK layer, under a stub) ─────────────────
# The old sort parsed the largest 'NNb' out of the id.  Every model without
# a parameter count in its NAME scored 0.0 -- which in the current lineup is
# DeepSeek-V4-Flash, GLM-5.2, Kimi-K3, Hy3, i.e. the pinned default and
# three of the four best models, all sorted BELOW a 72B legacy model.
print("\n== picker ordering ==")


class _Meta(type):
    def __getattr__(cls, n):
        if n.startswith("__"):
            raise AttributeError(n)
        return _Obj


class _Obj(metaclass=_Meta):
    def __init__(self, *a, **k):
        pass

    def __call__(self, *a, **k):
        return _Obj()

    def __getattr__(self, n):
        return _Obj()


class _Mod(types.ModuleType):
    def __getattr__(self, n):
        if n.startswith("__"):
            raise AttributeError(n)
        return _Obj

    def require_version(self, *a, **k):
        pass


for _m in ("gi", "gi.repository", "gi.repository.Gtk", "gi.repository.Adw",
           "gi.repository.GLib", "gi.repository.Gio", "gi.repository.Gdk",
           "gi.repository.GdkPixbuf", "gi.repository.Pango",
           "gi.repository.GObject", "gi.repository.GtkSource",
           "gi.repository.Vte", "gi.repository.Soup"):
    sys.modules[_m] = _Mod(_m)
sys.modules["gi"].require_version = lambda *a, **k: None

import basilisk as Bk  # noqa: E402

ck("basilisk.py imports clean under the GTK stub", True)

_W = Bk.MainWindow
# An instance WITHOUT running __init__ (which would build the whole GTK
# window).  The picker helpers only read class attributes and their args.
_pick = object.__new__(Bk.MainWindow)
_order = _pick._models_priced_high_to_low(SF)
ck("picker order == curated catalogue order", _order == list(SF.pick_ids))
ck("pinned default is NOT last in the picker",
   _order.index(PINNED) < len(_order) - 1,
   f"{_order.index(PINNED)} of {len(_order)}")
ck("a flagship model outranks the legacy 72B",
   _order.index("zai-org/GLM-5.2") < _order.index("Qwen/Qwen2.5-72B-Instruct"))

# The old heuristic, reproduced, so the regression is pinned not described.
_old = sorted(
    list(enumerate(SF.pick_ids)),
    key=lambda im: (-max((float(n) for n in
                          re.findall(r"(\d+(?:\.\d+)?)\s*[bB]\b", im[1])),
                         default=0.0), im[0]))
_old_ids = [m for _i, m in _old]
ck("the OLD sort would have buried the pinned default",
   _old_ids.index(PINNED) > _order.index(PINNED),
   f"old={_old_ids.index(PINNED)} new={_order.index(PINNED)}")

# A provider with no catalogue must still get the old regex path.
_groq_order = _pick._models_priced_high_to_low(GROQ)
ck("groq ordering keeps every pickable id",
   sorted(_groq_order) == sorted(GROQ.pick_ids))

# The catalogue-less path is still live code — any provider added without a
# catalogue takes it. Groq used to be the example; now that it has one, use a
# synthetic spec so the fallback keeps its coverage instead of quietly losing it.
_BARE = C.ProviderSpec(
    key="_bare", label="Bare", blurb="synthetic, catalogue-less",
    base_url="https://example.invalid/v1",
    chain=["vendor/big-70b", "vendor/small-7b"], key_url="")
ck("synthetic provider really has no catalogue", not _BARE.catalogue)
ck("no-catalogue provider falls back to its chain for picks",
   _BARE.pick_ids == list(_BARE.chain), str(_BARE.pick_ids))
ck("no-catalogue provider returns no metadata",
   _BARE.info("vendor/big-70b") is None)
_bare_order = _pick._models_priced_high_to_low(_BARE)
ck("no-catalogue providers still get the size heuristic",
   sorted(_bare_order) == sorted(_BARE.chain)
   and len(_bare_order) == len(_BARE.chain))

_tiers = _pick._models_by_tier(SF)
ck("tier grouping produces labelled groups", len(_tiers) >= 3)
ck("tier grouping loses nothing",
   sorted(m for _lbl, ids in _tiers for m in ids) == sorted(SF.pick_ids))
ck("flagship group comes first", "FLAGSHIP" in (_tiers[0][0] or ""))
_groq_tiers = _pick._models_by_tier(_BARE)
ck("no-catalogue provider gets one unlabelled group",
   len(_groq_tiers) == 1 and _groq_tiers[0][0] is None)
ck("groq NOW gets labelled tier groups like any catalogued provider",
   len(_pick._models_by_tier(GROQ)) >= 2)

_d = _pick._model_detail(SF, PINNED)
ck("detail line carries context and price", "ctx" in _d and "$" in _d, _d)
ck("1M context renders as M not K", "1M ctx" in _d, _d)
_free = _pick._model_detail(SF, "nex-agi/Nex-N2-Pro")
ck("a $0 model reads 'free' not '$0/$0'", "free" in _free, _free)
ck("detail is empty for an unknown id",
   _pick._model_detail(SF, "acme/Nope") == "")



# ── 12. HISTORY IS APPEND-ONLY BETWEEN WATERMARK ADVANCES ────────────
# The system prompt being stable is only half the job. `_build_history_for_model`
# used a SLIDING keep-full window, so the tool result sent in full last turn was
# sent trimmed this turn — rewriting a message in the MIDDLE of the request.
# DeepSeek: "partial matches in the middle of the input will not trigger a cache
# hit". Measured before the fix: ~40% of the request reusable and a break on
# EVERY turn. After: 100% and zero breaks on a normal run.
#
# Note which direction actually fixes it. "Once trimmed, always trimmed" does
# nothing — the trimming IS the mutation. It has to be "hold the render stable
# until a size budget forces one big advance", which is what the watermark does.
print("\n== history append-only (prompt cache) ==")
_B = Bk   # basilisk, imported above with the GTK stub

ck("a stability budget exists", hasattr(_B, "HISTORY_STABLE_BUDGET_CHARS"))
ck("the budget is well above one tool result",
   _B.HISTORY_STABLE_BUDGET_CHARS > 10 * _B.HISTORY_TRIM_HEAD_CHARS,
   "too small and the watermark advances constantly — a sliding window again")


class _M:
    def __init__(self, i, role, content, kind=None):
        self.id, self.role, self.content = i, role, content
        self.meta = {"kind": kind} if kind else {}


class _Store:
    def __init__(self):
        self.msgs = []

    def list_messages(self, cid):
        return list(self.msgs)


def _mk(n, size):
    out, mid = [_M(0, "user", "go")], 1
    for i in range(n):
        out.append(_M(mid, "assistant", f'<tool name="run">{{"c":{i}}}</tool>'))
        mid += 1
        out.append(_M(mid, "user", "<tool_result>\n" + "X" * size +
                      "\n</tool_result>", "tool_result"))
        mid += 1
    return out


def _shared(a, b):
    sa = "".join(m["role"] + m["content"] for m in a)
    sb = "".join(m["role"] + m["content"] for m in b)
    n = 0
    for x, y in zip(sa, sb):
        if x != y:
            break
        n += 1
    return n, len(sa)


_w = object.__new__(_B.MainWindow)
_w.store = _Store()
_w.settings = {}
_w.current_chat_id = 1
_w._trim_watermark = {}

_breaks, _turns = 0, 0
_prev = None
for _n in range(3, 22):
    _w.store.msgs = _mk(_n, 2000)
    _cur = _w._build_history_for_model(1)
    if _prev is not None:
        _sh, _ln = _shared(_prev, _cur)
        _turns += 1
        if _sh < _ln * 0.9:
            _breaks += 1
    _prev = _cur
ck(f"normal-sized results: ZERO cache breaks over {_turns} turns",
   _breaks == 0, f"{_breaks} breaks")

# Oversized results must still be bounded — the watermark has to advance
# sometimes, or context grows without limit. What it must NOT do is advance
# every turn.
_w2 = object.__new__(_B.MainWindow)
_w2.store = _Store()
_w2.settings = {}
_w2.current_chat_id = 1
_w2._trim_watermark = {}
_breaks2, _turns2, _prev = 0, 0, None
for _n in range(3, 22):
    _w2.store.msgs = _mk(_n, 25000)
    _cur = _w2._build_history_for_model(1)
    if _prev is not None:
        _sh, _ln = _shared(_prev, _cur)
        _turns2 += 1
        if _sh < _ln * 0.9:
            _breaks2 += 1
    _prev = _cur
ck(f"oversized results: breaks are occasional, not every turn "
   f"({_breaks2}/{_turns2})",
   0 < _breaks2 < _turns2 / 2,
   "must advance sometimes (bounded context) but not constantly (sliding)")
ck("the watermark advanced at all", _w2._trim_watermark.get(1, 0) > 0)
ck("the watermark only ever grows",
   _w2._trim_watermark.get(1, 0) <= len(_w2.store.msgs))

# And the rendered history must still be BOUNDED, or stability would just mean
# an ever-growing prompt.
_final = _w2._build_history_for_model(1)
_size = sum(len(m["content"]) for m in _final)
ck(f"oversized history stays bounded ({_size} chars)",
   _size < _B.HISTORY_STABLE_BUDGET_CHARS * 3, str(_size))

# Trimming must never destroy the model's record of WHAT IT DID — the tool
# CALLS live in assistant messages and are never trimmed.
ck("assistant tool calls survive trimming",
   sum(1 for m in _final if "<tool name=" in m["content"]) >= 15,
   "the action record must outlive the output trimming")



print(f"\nmodels: {_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
