<h1 align="center">Serum 2 Preset Downgrader</h1>

<p align="center"><strong>Open presets made in a newer Serum 2.</strong><br>Just drag and drop, no account or install necessary.</p>

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

Serum 2 refuses to open presets made in newer versions, although they are actually still compatible. This tool rewrites the version stamp inside the preset file so your older Serum version can open it. The preset itself is untouched and nothing about the sound changes. 

**Drop your presets on the file in the download. You get fixed copies. Your originals stay
exactly as they were.**

A whole bank counts as a preset too. Drop a `.SerumPack` and all 96 presets inside it come
out fixed, with the wavetables and samples the bank needs carried over.

## What it fixes

| What | What happens |
| --- | --- |
| **The version check** | Serum writes the version number in two places inside every preset, once in the small header the browser reads and once in the sound data itself. Both get rewritten to the version you ask for, and the checksum is recalculated, because otherwise the file looks corrupted. |
| **A crash on load** | Serum 2.1 writes one setting, the limit on stacking the same note, as a word like `Sustain` where 2.0 wrote a number. The older Serum cannot read a word there and the whole DAW goes down with it. The tool turns the word back into the number the older version expects. |
| **Nothing else** | Every oscillator, filter, envelope, LFO, effect, modulation slot and wavetable reference is copied over exactly. On a 95 preset test batch the sound data comes out byte for byte identical to the original apart from the two version values and that one repaired setting. |
| **Banks** | A `.SerumPack` is a zip of presets plus wavetables, samples and multisamples. The tool unpacks it, converts every preset inside, restamps the small manifest the browser reads, and writes the bank back out under the same name with everything else byte for byte unchanged. |
| **Your files** | The tool only ever reads your presets and writes new copies into a separate folder. Nothing is overwritten, moved or deleted. |
| **Folders** | Drop one preset, drop fifty, or drop a whole preset folder. It converts what it finds and skips anything that is already fine. |
| **Bad files** | If a file is damaged or is not a Serum preset at all, it says so and carries on with the rest instead of dying halfway through. A damaged preset inside a bank stops that bank and leaves no half written copy behind. |

## Use it

### If you just want it to work

1. Go to [Releases](https://github.com/simisonne/serum-preset-downgrader/releases/latest) and
   download `SerumPresetDowngrader-1.1-Windows.zip`.
2. Unzip it anywhere, but keep all contents inside one folder.
3. Drag the presets you want onto **Downgrade presets.bat**. You can drag a single file,
   several files, the whole preset folder, or a `.SerumPack` bank.
4. A console window opens and works on the conversion, it ends by telling you where the fixed
   copies are, in a folder called **Serum 2.0.23 versions**.
5. Copy the new files into your preset folder and they will work inside Serum!

That zip carries its own copy of Python, so there is nothing to install. If Windows shows
a blue "Windows protected your PC" box, click **More info** and then **Run anyway**. There is no virus, the code is open source and you can ask ChatGPT to check it. 

### If you have Python

The tool is one file and needs one package.

| Step | Command |
| --- | --- |
| Install the dependency | `pip install zstandard` |
| Convert one preset | `python serum_preset_downgrader.py "My Preset.SerumPreset"` |
| Convert a whole bank | `python serum_preset_downgrader.py "My Bank.SerumPack"` |
| Convert a folder | `python serum_preset_downgrader.py "C:/Presets/Some Pack"` |
| Choose where copies go | `python serum_preset_downgrader.py *.SerumPreset --out-dir fixed` |
| Ask for a different Serum version | `python serum_preset_downgrader.py *.SerumPreset --target 2.0.19` |
| Run the tests | `python tests/test_downgrader.py` |

There is no build step or installer. Python 3.9 or newer.

## Which versions it knows

Serum keeps a schema number inside each preset, next to the version text. These are the
values it has been seen to use:

| Serum 2 version | schema number |
| --- | --- |
| 2.0.19, 2.0.20 | 7 |
| 2.0.23, 2.0.24 | 9 |
| 2.1.4 | 10 |
| 2.1.5 | 11 |

**Confirmed working: files saved by 2.1.5 opened in 2.0.23, and a whole bank of 96 presets
saved by 2.1.4 converted to 2.0.23 with every single preset loading and playing.** That is the
pair this was built and tested for, and likely the one you need. The same mechanism should hold
for other nearby versions, and the `--target` flag offers the ones above, but I haven't really
tested them. If you are on a build that is not in this table, open an issue with your version
and it can be added.

## If something goes wrong

| What you see | What it means |
| --- | --- |
| "file is damaged: its checksum does not match its contents" | The preset was already broken, or it was edited by something else. Delete and download it again. |
| "not a Serum 2 preset" | That file is a Serum 1 `.fxp`, or it is not a preset and not a `.SerumPack` either. Only `.SerumPreset` files and `.SerumPack` banks can be converted. |
| "the pack contains no presets" | That file ends in `.SerumPack` but has no presets inside, so there is nothing to convert. |
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

A `.SerumPack` is a plain zip around a whole bank. Its entries look like this:

```
Presets/Packs/@author/Bank Name/.SerumPack.json   small manifest: name, author, version
Presets/Packs/@author/Bank Name/Preset.SerumPreset
Tables/Packs/@author/Bank Name/table.wav         wavetables
Samples/, Multisamples/                          the rest of the audio
```

The manifest carries the same two version values, so it is restamped as well, otherwise the
browser hides the bank before it ever reads a preset. Everything that is not a preset or the
manifest is copied through untouched, entry for entry and in the same order, and the rebuilt
bank is read back and compared against the original before it replaces the temporary file.
A bank is only written if there is something in it to change.

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

## Privacy

Everything happens on your PC. The tool has no network code at all and cannot send any data anywhere. The Windows zip contains only a Python interpreter and the tool.

## Known limits

- Only the 2.1.4 and 2.1.5 to 2.0.23 routes have been confirmed in the real plugin. The 2.1.4
  one was checked on a whole 96 preset bank, every preset loads and plays.
- A preset that leans on a 2.1 feature the older Serum does not have will sound close but not
  identical, because the missing control falls back to a default.
- A converted bank keeps its original name, so importing it replaces the newer bank rather
  than sitting next to it. That is deliberate, it is the same bank.
- Files created by something other than Serum, or edited by other tools, may not have the
  checksum the loader expects, and are refused rather than guessed at.
- Windows is the only platform with a ready made download. On macOS and Linux, run the Python
  file directly, it is the same code.

## License

MIT, see [LICENSE](LICENSE). Not affiliated with Xfer Records. Serum is a trademark of Xfer
Records.
