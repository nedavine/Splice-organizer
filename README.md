# Reorganize Samples by Type

This Python script reorganizes your **Splice** sample packs (or any sample library) into a clean, type-based folder structure. Instead of browsing by pack names, it groups files into folders like:

- `Drums/Kicks`
- `Drums/Snares`
- `Drums/Hats`
- `Loops/Drums`
- `Bass`
- `Synth/Pads`
- `Vocals`
- `FX`
- …and more

## Why?

Splice (and many other sample sources) store files by **pack**, which makes it hard to find all your kicks, snares, or loops across packs. This script solves that by scanning filenames and moving, copying, or symlinking them into new organized folders.

---

## Usage

### 1. Save the script
Save `reorganize_samples.py` into your `Splice/Sounds` folder (or anywhere you like).

### 2. Open Terminal and navigate
```bash
cd /Users/<YourName>/Splice/Sounds
```
### 4. Run a dry run (no changes, just preview)
```bash
python3 ./reorganize_samples.py \
  --source . \
  --dest ../Samples_By_Type \
  --mode symlink \
  --dry-run
```

	•	--source . → use the current folder (Splice/Sounds)
	•	--dest → where to put the reorganized files (here, one folder up: Samples_By_Type)
	•	--mode symlink → create symbolic links instead of moving or copying
	•	--dry-run → show what would happen without making changes

