#!/usr/bin/env python3
import argparse
import os
import re
import shutil
import sys
from pathlib import Path

import hashlib

MAX_REL_PATH_CHARS = 128
FILLER_WORDS = {
    "the","and","with","from","for","of","loop","sample","one-shot","oneshot","onesht","shot",
    "stereo","mono","wet","dry","mix","ver","take","take1","take2","v1","v2","pack","splice"
}
SEPARATORS_RE = re.compile(r"[\s\-\._]+")
NON_ALNUM_RE = re.compile(r"[^A-Za-z0-9\+\#]")
VOWELS_RE = re.compile(r"(?i)(?<=.)([aeiouy])(?=.)")
MULTI_UNDERSCORE_RE = re.compile(r"_+")

def _sha7(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:7]

def _collapse(name: str) -> str:
    name = SEPARATORS_RE.sub("_", name.strip())
    return MULTI_UNDERSCORE_RE.sub("_", name).strip("_")

def _drop_filler(name: str) -> str:
    toks = [t for t in name.split("_") if t.lower() not in FILLER_WORDS]
    return "_".join(toks) or name

def _mid_vowel_strip(name: str) -> str:
    out = []
    for t in name.split("_"):
        out.append(VOWELS_RE.sub("", t))
    s = "_".join(out)
    return MULTI_UNDERSCORE_RE.sub("_", s).strip("_")

def _unique(suggested: str, existing: set[str], max_len: int, orig: str) -> str:
    cand = suggested[:max_len]
    if cand not in existing:
        return cand
    suffix = "~" + _sha7(orig)
    room = max_len - len(suffix)
    if room < 1:
        return suffix[-max_len:]
    base = cand[:room]
    final = base + suffix
    if final in existing:
        final = (orig[:max(1, room-1)] + suffix)[:max_len]
    return final

def _shorten_folder(name: str, max_len: int = 18) -> str:
    n = _mid_vowel_strip(_drop_filler(_collapse(name)))
    return (n or "x")[:max_len]

def _shorten_stem(stem: str, pack_hint: str | None) -> str:
    s = _collapse(stem)
    if pack_hint:
        ph = _collapse(pack_hint)
        low = s.lower()
        if low.startswith(ph.lower() + "_"):
            s = s[len(ph) + 1:]
        elif low.startswith(ph.lower()):
            s = s[len(ph):]
    s = _mid_vowel_strip(_drop_filler(s))
    s = NON_ALNUM_RE.sub("_", s)
    s = MULTI_UNDERSCORE_RE.sub("_", s).strip("_")
    return s or "x"

def enforce_m8_limit(dst_root: Path, out_path: Path, pack_hint: str | None = None) -> Path:
    """Return a possibly adjusted out_path so that its relative path length <= 128."""
    rel = out_path.relative_to(dst_root)
    if len(str(rel)) <= MAX_REL_PATH_CHARS:
        return out_path

    parent = out_path.parent
    parent_rel_len = len(str(parent.relative_to(dst_root)))
    max_name_len = MAX_REL_PATH_CHARS - parent_rel_len - 1

    stem = _shorten_stem(out_path.stem, pack_hint)
    ext = out_path.suffix
    max_stem_len = max(1, max_name_len - len(ext))
    if len(stem) > max_stem_len:
        stem = stem[:max_stem_len]

    siblings = {p.name for p in parent.iterdir() if p.is_file()}
    new_name = _unique(stem + ext, siblings - {out_path.name}, max_name_len, out_path.name)
    return parent / new_name

# File types to include
AUDIO_EXTS = {".wav", ".aif", ".aiff", ".flac", ".mp3", ".ogg", ".m4a"}

# Keyword rules for categorization. Order matters. First match wins.
CATEGORY_RULES = [
    # Drums - one shots
    (("kick", "bd", "subkick"), "Drums/Kicks"),
    (("snare", "rimshot", "rim"), "Drums/Snares"),
    (("clap",), "Drums/Claps"),
    (("hi hat", "hi-hat", "hihat", "hat"), "Drums/Hats"),
    (("tom",), "Drums/Toms"),
    (("ride", "crash", "splash", "china", "cymbal"), "Drums/Cymbals"),
    (("shaker", "tamb", "tambo", "tambourine", "bongo", "conga", "timbale", "cowbell", "clave", "guiro", "agogo", "block"), "Drums/Percussion"),

    # Drum loops and breaks
    (("break", "breakbeat", "amen", "funky drummer"), "Loops/Drums/Breaks"),
    (("top loop", "tops"), "Loops/Drums/Tops"),
    (("drum loop", "beat loop", "beat", "loop drums"), "Loops/Drums"),

    # Bass
    (("808",), "Bass/808"),
    (("bass", "sub"), "Bass"),

    # Synths and keys
    (("pad",), "Synth/Pads"),
    (("lead",), "Synth/Leads"),
    (("pluck",), "Synth/Plucks"),
    (("arpeggio", "arp"), "Synth/Arps"),
    (("synth",), "Synth"),
    (("piano", "keys", "rhodes", "wurlitzer", "organ", "epiano"), "Keys"),

    # Guitars and strings
    (("guitar", "gtr"), "Guitar"),
    (("violin", "viola", "cello", "strings", "pizzicato"), "Strings"),

    # Brass and winds
    (("sax", "saxophone", "trumpet", "trombone", "horn", "brass"), "Brass"),
    (("flute", "clarinet", "oboe", "bassoon", "woodwind"), "Winds"),

    # Vocals
    (("vocal", "vox", "choir", "chant", "adlib", "ad-lib", "adlib"), "Vocals"),

    # FX and others
    (("fx", "sfx", "sweep", "riser", "rise", "downlifter", "downer", "impact", "boom", "whoosh", "glitch", "stutter"), "FX"),
    (("noise", "texture", "atmo", "ambience", "ambient", "drone", "foley", "field"), "Textures Foley"),

    # Generic loops and one shots if nothing else matched
    (("loop",), "Loops/Misc"),
    (("one shot", "oneshot", "shot"), "One Shots/Misc"),
]

# Simple helpers
BPM_PAT = re.compile(r"\b(\d{2,3})\s?bpm\b", re.I)
KEY_PAT = re.compile(r"\b([A-G](?:#|b)?)(?:\s|-|_)?(maj|min|m|minor|major)?\b", re.I)

def norm(s: str) -> str:
    return s.lower()

def categorize(path: Path) -> str:
    """
    Decide a category path for a sample based on filename and its parent folders.
    """
    hay = " ".join([
        path.name,
        *[p.name for p in path.parents if p.name]  # includes pack and subfolders
    ])
    hay_n = norm(hay)

    # Try explicit rules
    for keywords, target in CATEGORY_RULES:
        for kw in keywords:
            if kw in hay_n:
                return target

    # Fallback heuristics
    if "loop" in hay_n:
        return "Loops/Misc"
    return "Unsorted"

def safe_write(src: Path, dest: Path, mode: str, dst_root: Path, enforce_limit: bool = True, pack_hint: str | None = None) -> Path:
    """
    Place file at dest using mode: move, copy, symlink.
    Enforce M8 128-char relative path limit and ensure uniqueness without exceeding it.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Optionally enforce the 128-char limit for the target filename before checking collisions
    if enforce_limit:
        dest = enforce_m8_limit(dst_root, dest, pack_hint)

    # Ensure uniqueness among siblings without creating names that would exceed the limit
    siblings = {p.name for p in dest.parent.iterdir() if p.is_file()}
    # Compute the max filename length allowed given the parent relative path length
    parent_rel_len = len(str(dest.parent.relative_to(dst_root)))
    max_name_len = MAX_REL_PATH_CHARS - parent_rel_len - 1

    stem, ext = dest.stem, dest.suffix
    # Use the _unique helper to avoid collisions while respecting max_name_len
    final_name = _unique(stem + ext, siblings, max_name_len, dest.name)
    final = dest.parent / final_name

    if mode == "move":
        shutil.move(str(src), str(final))
    elif mode == "copy":
        shutil.copy2(str(src), str(final))
    elif mode == "symlink":
        try:
            final.symlink_to(src.resolve())
        except Exception:
            # Try hardlink
            try:
                os.link(src, final)
            except Exception:
                shutil.copy2(str(src), str(final))
    else:
        raise ValueError("Unknown mode")
    return final

def scan_files(root: Path):
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in AUDIO_EXTS:
            yield p

def main():
    ap = argparse.ArgumentParser(description="Reorganize Splice packs into type-based folders.")
    ap.add_argument("--source", required=True, type=Path, help="Splice packs root folder. Example: ~/Splice/Sounds")
    ap.add_argument("--dest", required=True, type=Path, help="Destination root for type-based library")
    ap.add_argument("--mode", choices=["symlink", "copy", "move"], default="symlink", help="How to place files at destination")
    ap.add_argument("--dry-run", action="store_true", help="Show what would happen without making changes")
    ap.add_argument("--include-non-audio", action="store_true", help="Also include preset or MIDI files")
    ap.add_argument("--quiet", action="store_true", help="Reduce logging")
    args = ap.parse_args()

    src_root = args.source.expanduser().resolve()
    dst_root = args.dest.expanduser().resolve()

    if not src_root.exists():
        print(f"Source not found: {src_root}", file=sys.stderr)
        sys.exit(1)

    extra_exts = {".mid", ".midi", ".als", ".adg", ".fxp", ".nki"} if args.include_non_audio else set()
    exts = AUDIO_EXTS | extra_exts

    moved = 0
    for f in src_root.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix.lower() not in exts:
            continue

        cat = categorize(f)

        # Build filename with optional bpm and key tags for readability
        name = f.stem
        suffix = f.suffix

        bpm = None
        key = None
        m_bpm = BPM_PAT.search(f.name)
        if m_bpm:
            bpm = m_bpm.group(1)

        m_key = KEY_PAT.search(f.name)
        if m_key:
            # Keep letter uppercase, preserve sharps, and render flats with lowercase 'b' suffix
            raw = m_key.group(1)
            letter = raw[0].upper()
            accidental = raw[1:] if len(raw) > 1 else ""
            if accidental in {"#", "b"}:
                base = f"{letter}{accidental}"
            else:
                base = letter
            qual = (m_key.group(2) or "").lower()
            if qual in {"m", "min", "minor"}:
                key = f"{base}m"
            else:
                key = base

        tags = []
        if bpm:
            tags.append(f"{bpm}bpm")
        if key:
            tags.append(key)
        tag_str = f" [{' '.join(tags)}]" if tags else ""

        # Derive pack/vendor from the source path under src_root for better filename shortening
        try:
            rel_from_src = f.relative_to(src_root)
            pack_hint = rel_from_src.parts[0] if len(rel_from_src.parts) > 1 else None
        except Exception:
            pack_hint = None

        rel_name = f"{name}{tag_str}{suffix}"
        out_path = dst_root / cat / rel_name

        if args.dry_run:
            if not args.quiet:
                print(f"{f}  ->  {out_path}  [{args.mode}]")
        else:
            final_path = safe_write(f, out_path, args.mode, dst_root, True, pack_hint)
            if not args.quiet:
                print(f"Placed: {final_path}")
        moved += 1

    if not args.quiet:
        action = "Would process" if args.dry_run else "Processed"
        print(f"{action} {moved} files")

if __name__ == "__main__":
    main()
