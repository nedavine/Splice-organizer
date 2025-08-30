#!/usr/bin/env python3
import argparse
import os
import re
import shutil
import sys
from pathlib import Path

# File types to include
AUDIO_EXTS = {".wav", ".aif", ".aiff", ".flac", ".mp3", ".ogg", ".m4a"}

# Keyword rules for categorization. Order matters. First match wins.
CATEGORY_RULES = [
    # Drums - one shots
    (("kick", "bd", "subkick"), "Drums/Kicks"),
    (("snare", "rimshot", "rim", "shot"), "Drums/Snares"),
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

def safe_write(src: Path, dest: Path, mode: str) -> Path:
    """
    Place file at dest using mode: move, copy, symlink.
    If name collision occurs, append a counter.
    Symlink fallback strategy: try symlink, then hardlink, then copy.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    final = dest
    stem, ext = dest.stem, dest.suffix
    i = 1
    while final.exists():
        final = dest.with_name(f"{stem} ({i}){ext}")
        i += 1

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
            base = m_key.group(1).upper().replace("B", "b").replace("#", "#")
            qual = m_key.group(2) or ""
            # Normalize minor markers
            if qual.lower() in {"m", "min", "minor"}:
                key = f"{base}m"
            elif qual.lower() in {"maj", "major"}:
                key = f"{base}"
            else:
                key = base

        tags = []
        if bpm:
            tags.append(f"{bpm}bpm")
        if key:
            tags.append(key)
        tag_str = f" [{' '.join(tags)}]" if tags else ""

        rel_name = f"{name}{tag_str}{suffix}"
        out_path = dst_root / cat / rel_name

        if args.dry_run:
            if not args.quiet:
                print(f"{f}  ->  {out_path}  [{args.mode}]")
        else:
            final_path = safe_write(f, out_path, args.mode)
            if not args.quiet:
                print(f"Placed: {final_path}")
        moved += 1

    if not args.quiet:
        action = "Would process" if args.dry_run else "Processed"
        print(f"{action} {moved} files")

if __name__ == "__main__":
    main()