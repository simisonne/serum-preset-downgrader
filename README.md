<p align="center">
  <img src="docs/logo.svg" alt="Serum 2 Preset Downgrader" width="96" height="96">
</p>

<h1 align="center">Serum 2 Preset Downgrader</h1>

<p align="center"><strong>Open presets made in a newer Serum 2.</strong><br>Drag them onto one file. No install, no account, no internet.</p>

<p align="center">
  <a href="https://github.com/simisonne/serum-preset-downgrader/releases/latest"><strong>Download</strong></a> ·
  <a href="#what-it-fixes">What it fixes</a> ·
  <a href="#use-it">How to use it</a> ·
  <a href="#if-something-goes-wrong">If something goes wrong</a> ·
  <a href="#under-the-hood">Under the hood</a> ·
  <a href="#privacy">Privacy</a>
</p>

<p align="center">
  <a href="serum_preset_downgrader.py"><img src="https://img.shields.io/badge/No_install_needed-Windows-0078D6" alt="No install needed on Windows"></a>
  <a href="serum_preset_downgrader.py"><img src="https://img.shields.io/badge/Dependencies-one-3C873A" alt="One dependency"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-1D9BF0" alt="MIT license"></a>
</p>

Serum 2 will not open a preset that was saved by a newer Serum 2. It tells you the preset
was made with a newer version and stops, even when the newer version only added things and
nothing your copy cares about has actually changed.

This tool rewrites the version stamp inside the preset file so your Serum will open it. It
also repairs one setting whose type changed between versions, which is what makes the older
Serum crash instead of just refusing. The preset itself is untouched: same oscillators, same
filters, same wavetables, same modulation.

**Drop your presets on the file in the download. You get fixed copies. Your originals stay
exactly as they were.**

## What it fixes

| What | What happens |
| --- | --- |
| **The version check** | Serum writes the version number in two places inside every preset, once in the small header the browser reads and once in the sound data itself. Both get rewritten to the version you ask for, and the checksum is recalculated, because otherwise the file looks corrupted. |
| **A crash on load** | Serum 2.1 writes one setting, the limit on stacking the same note, as a word like `Sustain` where 2.0 wrote a number. The older Serum cannot read a word there and the whole DAW goes down with it. The tool turns the word back into the number the older version expects. |
| **Nothing else** | Every oscillator, filter, envelope, LFO, effect, modulation slot and wavetable reference is copied over exactly. On a 95 preset test batch the sound data comes out byte for byte identical to the original apart from the two version values and that one repaired setting. |
| **Your files** | The tool only ever reads your presets and writes new copies into a separate folder. Nothing is overwritten, moved or deleted. |
| **Folders** | Drop one preset, drop fifty, or drop a whole preset folder. It converts what it finds and skips anything that is already fine. |
| **Bad files** | If a file is damaged or is not a Serum preset at all, it says so and carries on with the rest instead of dying halfway through. |

## Use it

### If you just want it to work

1. Go to [Releases](https://github.com/simisonne/serum-preset-downgrader/releases/latest) and
   download `SerumPresetDowngrader-1.0-Windows.zip`.
2. Unzip it anywhere, for example your Desktop. Keep the folder contents together.
3. Drag the presets you want onto **Downgrade presets.bat**. You can drag a single file,
   several files, or the whole preset folder.
4. A black window opens and lists what it is doing. It ends by telling you where the fixed
   copies are, in a folder called **Serum 2.0.23 versions**.
5. In Serum 2, use **Menu > Open Serum 2 Presets Folder**. Copy the contents of
   **Serum 2.0.23 versions** into it.
6. Back in Serum 2, use **Menu > Rescan Folders on Disk**. The presets appear.

That zip carries its own copy of Python, so there is nothing to install. If Windows shows
a blue "Windows protected your PC" box, click **More info** and then **Run anyway**. That
box appears for any downloaded file that is not signed with a paid certificate.

### If you have Python

The tool is one file and needs one package.

| Step | Command |
| --- | --- |
| Install the dependency | `pip install zstandard` |
| Convert one preset | `python serum_preset_downgrader.py "My Preset.SerumPreset"` |
| Convert a folder | `python serum_preset_downgrader.py "C:/Presets/Some Pack"` |
| Choose where copies go | `python serum_preset_downgrader.py *.SerumPreset --out-dir fixed` |
| Ask for a different Serum version | `python serum_preset_downgrader.py *.SerumPreset --target 2.0.19` |
| Run the tests | `python tests/test_downgrader.py` |

There is no build step and no installer. Python 3.9 or newer.

## Which versions it knows

Serum keeps a schema number inside each preset, next to the version text. These are the
values it has been seen to use:

| Serum 2 version | schema number |
| --- | --- |
| 2.0.19, 2.0.20 | 7 |
| 2.0.23, 2.0.24 | 9 |
| 2.1.5 | 11 |

**Confirmed working: files saved by 2.1.5 opened in 2.0.23.** That is the pair this was
built and tested for. The same mechanism should hold for other nearby versions, and the
`--target` flag offers the ones above, but nothing else has been watched opening in the real
plugin. If you are on a build that is not in this table, open an issue with your version and
it can be added.

Converting up is never needed. Serum upgrades old presets by itself.

## If something goes wrong

| What you see | What it means |
| --- | --- |
| "file is damaged: its checksum does not match its contents" | The preset was already broken, or it was edited by something else. Delete and download it again. |
| "not a Serum 2 preset" | That file is a Serum 1 `.fxp`, or it is a `.SerumPack`, or it is not a preset. Only `.SerumPreset` files can be converted, and only one at a time. |
| Serum still says the preset is too new | You converted to 2.0.23 but your Serum is older than that. Pass your own version with `--target`, or update Serum. |
| Your DAW still crashes | The preset is using something that changed type in a way this tool does not know about yet. Open an issue with the Serum version that saved the preset and the one you are opening it in. |
| The window flashes and closes | You ran the `.py` file on its own. Drag the presets onto `Downgrade presets.bat` instead, and keep it in the same folder as `runtime`. |
| Nothing happens when you drop a file | Check the file really ends in `.SerumPreset`. The tool also refuses folders that contain no presets, and says so. |
| The preset loads but sounds different | Some 2.1 additions have no setting in 2.0 at all, so your Serum falls back to its own default for that control. The tool cannot invent parameters that your version does not have. |

## Under the hood

A `.SerumPreset` is a small container:

```
b"XferJson\x00"    magic
uint64 LE          length of the JSON header
<n> bytes          JSON header: name, author, build, schema, hash
uint32 LE          size of the sound data once unpacked
uint32 LE          how it is packed, always 2 (zstd)
<rest>             one zstd frame holding CBOR
```

Three details matter and all three were worked out by comparing files, since Xfer publishes
no specification:

- **The version is stored twice.** Once in the JSON header, which the preset browser reads
  so it does not have to unpack every preset, and once in the CBOR payload, which the loader
  reads. Editing one and not the other gives you a file that appears in the browser and then
  fails to load.
- **The `hash` field is the MD5 of the compressed audio data**, not of the unpacked payload.
  Any edit invalidates it, so it is recalculated on the way out.
- **Serum writes floats in their shortest exact form.** A value that survives single
  precision goes in as a 32 bit float, everything else as 64 bit. Python's `cbor2` always
  writes 64 bit, which changes the encoded length and reproduces none of the original files.
  This tool carries its own small CBOR reader and writer so that reading a preset and writing
  it back with no changes gives back the identical bytes, which is what makes editing it safe.

The Windows zip is built by `tools/make_windows_release.sh`. It fetches the official
embeddable Python for Windows and the `zstandard` wheel, lays them out next to the tool, and
zips the result. Nothing is compiled and nothing is unsigned except the wrapper itself.

## How it was checked

- 101 real presets were read and written back unchanged, and all 101 came out byte for byte
  identical. That proves the reader and writer do not quietly alter anything.
- 95 of them were converted and structurally verified: checksum correct, both version stamps
  correct, length fields consistent, and no difference from the original other than the two
  version values and the one repaired setting.
- All 95 were then opened in Serum 2.0.23 by hand, in a DAW, and all 95 loaded and played.
- The 25 tests in `tests/` build their own preset files from scratch, so no real preset
  content is included in this repository.

## Privacy

Everything happens on your machine. The tool has no network code at all, no telemetry, no
accounts and no update check. The Windows zip contains a Python interpreter, the tool, and
nothing else.

## Known limits

- Only the 2.1.5 to 2.0.23 route has been confirmed in the real plugin.
- A preset that leans on a 2.1 feature the older Serum does not have will sound close but not
  identical, because the missing control falls back to a default.
- Files created by something other than Serum, or edited by other tools, may not have the
  checksum the loader expects, and are refused rather than guessed at.
- Windows is the only platform with a ready made download. On macOS and Linux, run the Python
  file directly, it is the same code.

## License

MIT, see [LICENSE](LICENSE). Not affiliated with Xfer Records. Serum is a trademark of Xfer
Records.
