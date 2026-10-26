#!/usr/bin/env python3
"""Serum 2 preset downgrader.

Rewrites a .SerumPreset file saved by a newer Serum 2 so an older Serum 2 will
open it. Original files are never modified.

    python serum_preset_downgrader.py "My Preset.SerumPreset"
    python serum_preset_downgrader.py "C:/Presets/Some Pack"
    python serum_preset_downgrader.py --target 2.0.23 --out-dir fixed *.SerumPreset

MIT licensed. No network access, nothing leaves the machine.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys

__version__ = '1.0'

try:
    import zstandard
except ImportError:  # pragma: no cover - friendly message for a missing dep
    sys.exit('This tool needs the "zstandard" package.\n'
             'Install it with:  pip install zstandard')

MAGIC = b'XferJson\x00'
ENCODING_ZSTD = 2

# Serum stores a schema number inside the preset next to the build string. Both
# are written twice, once in the small JSON header and once in the payload.
KNOWN_VERSIONS = {
    '2.0.19': 7.0,
    '2.0.20': 7.0,
    '2.0.23': 9.0,
    '2.0.24': 9.0,
    '2.1.5': 11.0,
}
DEFAULT_TARGET = '2.0.23'

USAGE = '''\
Drag preset files or a folder onto this tool, or run it from a terminal:

    python serum_preset_downgrader.py "My Preset.SerumPreset"
    python serum_preset_downgrader.py "C:/Presets/Some Pack"

It writes fixed copies into a folder called "Serum 2.0.23 versions" next to
your presets, and leaves the originals alone.'''

# Serum 2.1 writes this one as a named string ("On", "Sustain") while 2.0.x
# stores a plain number. Handing a string to the older loader crashes the host
# instead of showing an error, so it gets rewritten to 1.0 (enabled).
LIMIT_POLY_PARAM = 'kParamLimitSameNotePolyphony'


# --------------------------------------------------------------------------
# CBOR, the binary format inside the preset
# --------------------------------------------------------------------------

def _head(major: int, value: int) -> bytes:
    if value < 24:
        return bytes([major << 5 | value])
    if value < 0x100:
        return bytes([major << 5 | 24, value])
    if value < 0x10000:
        return bytes([major << 5 | 25]) + struct.pack('>H', value)
    if value < 0x100000000:
        return bytes([major << 5 | 26]) + struct.pack('>I', value)
    return bytes([major << 5 | 27]) + struct.pack('>Q', value)


def cbor_dumps(obj, out=None) -> bytes:
    """Encode to CBOR the way Serum does.

    The important detail is floats: Serum writes the shortest exact form, so a
    value that survives single precision goes out as float32 and everything else
    as float64. Python's cbor2 always writes float64, which changes the encoded
    length and does not reproduce Serum's own files.
    """
    top = out is None
    if top:
        out = bytearray()
    if obj is True:
        out.append(0xF5)
    elif obj is False:
        out.append(0xF4)
    elif obj is None:
        out.append(0xF6)
    elif isinstance(obj, int):
        out += _head(0, obj) if obj >= 0 else _head(1, -1 - obj)
    elif isinstance(obj, float):
        try:
            packed = struct.pack('>f', obj)
        except OverflowError:  # too big for single precision
            packed = None
        if packed is not None and struct.unpack('>f', packed)[0] == obj:
            out.append(0xFA)
            out += packed
        else:
            out.append(0xFB)
            out += struct.pack('>d', obj)
    elif isinstance(obj, str):
        raw = obj.encode('utf-8')
        out += _head(3, len(raw))
        out += raw
    elif isinstance(obj, (bytes, bytearray)):
        out += _head(2, len(obj))
        out += obj
    elif isinstance(obj, (list, tuple)):
        out += _head(4, len(obj))
        for item in obj:
            cbor_dumps(item, out)
    elif isinstance(obj, dict):
        out += _head(5, len(obj))
        for key, value in obj.items():  # insertion order is what Serum writes
            cbor_dumps(key, out)
            cbor_dumps(value, out)
    else:
        raise TypeError(f'cannot store {type(obj).__name__} in CBOR')
    return bytes(out) if top else out


def cbor_loads(data) -> object:
    """Decode CBOR into dict, list, str, bytes, int, float, bool or None."""
    value, offset = _decode(data, 0)
    if offset != len(data):
        raise ValueError(f'unexpected trailing data at byte {offset}')
    return value


def _decode(data, i):
    if i >= len(data):
        raise ValueError('unexpected end of CBOR data')
    initial = data[i]
    i += 1
    major = initial >> 5
    info = initial & 0x1F

    if info < 24:
        argument = info
    elif info == 24:
        argument = data[i]
        i += 1
    elif info == 25:
        argument = struct.unpack_from('>H', data, i)[0]
        i += 2
    elif info == 26:
        argument = struct.unpack_from('>I', data, i)[0]
        i += 4
    elif info == 27:
        argument = struct.unpack_from('>Q', data, i)[0]
        i += 8
    elif info == 31:
        argument = None  # indefinite length
    else:
        raise ValueError(f'bad CBOR marker 0x{initial:02x}')

    if major == 0:
        return argument, i
    if major == 1:
        return -1 - argument, i
    if major == 2:
        if argument is None:
            parts = []
            while data[i] != 0xFF:
                chunk, i = _decode(data, i)
                parts.append(chunk)
            return b''.join(parts), i + 1
        return bytes(data[i:i + argument]), i + argument
    if major == 3:
        if argument is None:
            parts = []
            while data[i] != 0xFF:
                chunk, i = _decode(data, i)
                parts.append(chunk)
            return ''.join(parts), i + 1
        return data[i:i + argument].decode('utf-8'), i + argument
    if major == 4:
        items = []
        if argument is None:
            while data[i] != 0xFF:
                item, i = _decode(data, i)
                items.append(item)
            return items, i + 1
        for _ in range(argument):
            item, i = _decode(data, i)
            items.append(item)
        return items, i
    if major == 5:
        result = {}
        if argument is None:
            while data[i] != 0xFF:
                key, i = _decode(data, i)
                result[key], i = _decode(data, i)
            return result, i + 1
        for _ in range(argument):
            key, i = _decode(data, i)
            result[key], i = _decode(data, i)
        return result, i
    if major == 6:  # tag: skip the tag number, decode what it wraps
        return _decode(data, i)
    if major == 7:
        if info == 20:
            return False, i
        if info == 21:
            return True, i
        if info == 22:
            return None, i
        if info == 25:
            return struct.unpack('>e', struct.pack('>H', argument))[0], i
        if info == 26:
            return struct.unpack('>f', struct.pack('>I', argument))[0], i
        if info == 27:
            return struct.unpack('>d', struct.pack('>Q', argument))[0], i
        raise ValueError(f'unsupported CBOR simple value {info}')
    raise ValueError(f'unsupported CBOR major type {major}')


# --------------------------------------------------------------------------
# The preset file
# --------------------------------------------------------------------------

class Preset:
    """A parsed .SerumPreset.

    Layout:
        b"XferJson\\x00"   magic
        uint64 LE          length of the JSON header
        <n> bytes          JSON header: name, author, build, schema, hash
        uint32 LE          payload size once decompressed
        uint32 LE          how the payload is packed, always 2 (zstd)
        <rest>             one zstd frame holding CBOR
    """

    def __init__(self, path):
        self.path = path
        with open(path, 'rb') as handle:
            blob = handle.read()
        if blob[:9] != MAGIC:
            raise ValueError('not a Serum 2 preset')
        header_len = struct.unpack('<Q', blob[9:17])[0]
        self.header_raw = blob[17:17 + header_len]
        self.header = json.loads(self.header_raw)
        offset = 17 + header_len
        self.payload_size, self.encoding = struct.unpack('<II', blob[offset:offset + 8])
        if self.encoding != ENCODING_ZSTD:
            raise ValueError(f'unknown packing type {self.encoding}')
        self.frame = blob[offset + 8:]
        if offset + 8 + len(self.frame) != len(blob):
            raise ValueError('file length does not match its header')
        # Check the checksum before unpacking: a damaged file should say so
        # plainly instead of failing deep inside the decompressor.
        if not self.hash_ok():
            raise ValueError('file is damaged: its checksum does not match its contents')
        raw = zstandard.ZstdDecompressor().decompress(
            self.frame, max_output_size=self.payload_size)
        if len(raw) != self.payload_size:
            raise ValueError('payload size does not match its header')
        self.payload = cbor_loads(raw)

    @property
    def build(self):
        return str(self.header.get('productVersion', '?'))

    @property
    def schema(self):
        return float(self.header.get('version', 0))

    def hash_ok(self):
        """The header hash is the MD5 of the compressed frame, not the payload."""
        return hashlib.md5(self.frame).hexdigest() == self.header.get('hash')

    def rebuild(self, build, schema, repair=True):
        """Return the bytes of this preset restamped for another Serum build."""
        header = dict(self.header)
        header['productVersion'] = build
        header['version'] = schema

        payload = dict(self.payload)
        payload['productVersion'] = build
        payload['version'] = schema
        if repair:
            payload = _repair_global(payload)

        raw = cbor_dumps(payload)
        frame = zstandard.ZstdCompressor(level=3).compress(raw)
        header['hash'] = hashlib.md5(frame).hexdigest()
        header_raw = json.dumps(header, sort_keys=True, separators=(',', ':'),
                                ensure_ascii=False).encode('utf-8')
        return (MAGIC
                + struct.pack('<Q', len(header_raw))
                + header_raw
                + struct.pack('<II', len(raw), ENCODING_ZSTD)
                + frame)


def _repair_global(payload):
    """Fix Global0 values that an older Serum cannot read."""
    global0 = payload.get('Global0')
    if not isinstance(global0, dict):
        return payload
    params = global0.get('plainParams')
    if not isinstance(params, dict):
        return payload
    value = params.get(LIMIT_POLY_PARAM)
    if not isinstance(value, str):
        return payload
    params = dict(params)
    params[LIMIT_POLY_PARAM] = 1.0
    global0 = dict(global0)
    global0['plainParams'] = params
    payload = dict(payload)
    payload['Global0'] = global0
    return payload


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------

def _collect(paths):
    """Expand files and folders into a list of .SerumPreset paths."""
    found, skipped = [], []
    for path in paths:
        if os.path.isdir(path):
            for name in sorted(os.listdir(path)):
                full = os.path.join(path, name)
                if name.lower().endswith('.serumpreset') and os.path.isfile(full):
                    found.append(full)
        elif os.path.isfile(path):
            found.append(path)
        else:
            skipped.append((path, 'no such file or folder'))
    return found, skipped


def _output_dir(files, requested):
    if requested:
        return requested
    folder = os.path.dirname(os.path.abspath(files[0]))
    return os.path.join(folder, 'Serum 2.0.23 versions')


def convert_one(path, out_dir, target, schema, repair=True, quiet=False):
    preset = Preset(path)
    blob = preset.rebuild(target, schema, repair=repair)
    # Read the result back and check it before writing anything.
    check = os.path.join(out_dir, '.check.tmp')
    os.makedirs(out_dir, exist_ok=True)
    with open(check, 'wb') as handle:
        handle.write(blob)
    try:
        verify = Preset(check)
        if not verify.hash_ok():
            raise ValueError('rebuilt checksum is wrong')
        if verify.schema != schema or verify.build != target:
            raise ValueError('rebuilt file has the wrong version')
        if verify.payload.get('version') != schema:
            raise ValueError('rebuilt payload has the wrong version')
    except Exception:
        os.remove(check)
        raise
    final = os.path.join(out_dir, os.path.basename(path))
    os.replace(check, final)
    if not quiet:
        print(f'   {os.path.basename(path)}')
    return final, preset.build


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='serum_preset_downgrader',
        description='Make Serum 2 presets saved in a newer Serum 2 open in an older one.')
    parser.add_argument('paths', nargs='*',
                        help='preset files or folders to convert')
    parser.add_argument('--target', default=DEFAULT_TARGET,
                        choices=sorted(KNOWN_VERSIONS),
                        help=f'Serum version to convert down to (default {DEFAULT_TARGET})')
    parser.add_argument('--out-dir', help='where to put the converted copies')
    parser.add_argument('--no-repair', action='store_true',
                        help='skip the parameter fix (advanced)')
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    args = parser.parse_args(argv)

    if not args.paths:
        print(USAGE)
        return 1

    files, problems = _collect(args.paths)
    files = [f for f in files if f.lower().endswith('.serumpreset')]
    if not files:
        print('No .SerumPreset files found.')
        return 1

    target, schema = args.target, KNOWN_VERSIONS[args.target]
    out_dir = _output_dir(files, args.out_dir)

    print(f'Converting {len(files)} preset(s) to Serum {target}')
    done, up_to_date, failed = 0, 0, []
    for path in files:
        try:
            preset = Preset(path)
            if preset.schema <= schema and preset.build <= target:
                up_to_date += 1
                continue
            convert_one(path, out_dir, target, schema,
                        repair=not args.no_repair)
            done += 1
        except Exception as error:
            failed.append((os.path.basename(path), str(error)))

    print()
    print(f'Converted:       {done}')
    if up_to_date:
        print(f'Already fine:    {up_to_date}')
    if failed:
        print(f'Could not do:    {len(failed)}')
        for name, reason in failed:
            print(f'   {name}: {reason}')
    for path, reason in problems:
        print(f'   skipped {path}: {reason}')
    if done:
        print()
        print(f'Your fixed presets are in:\n   {out_dir}')
        print()
        print('Copy that folder into your Serum 2 preset folder, then use')
        print('Menu > Rescan Folders on Disk inside Serum 2.')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
