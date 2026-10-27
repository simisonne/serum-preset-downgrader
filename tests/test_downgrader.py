"""Tests for the Serum 2 preset downgrader.

Everything here is built from scratch by the tests themselves: they assemble
preset files byte by byte from a dictionary, convert them, and read them back.
No real preset content is included or required.

    python tests/test_downgrader.py
"""

import hashlib
import json
import os
import struct
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import zstandard  # noqa: E402

import serum_preset_downgrader as tool  # noqa: E402


def build_preset(payload, build='2.1.5', schema=11.0):
    """Assemble a .SerumPreset container around a payload dictionary."""
    header = {
        'fileType': 'SerumPreset',
        'hash': '',
        'presetAuthor': 'Test',
        'presetDescription': '',
        'presetName': 'Test Preset',
        'product': 'Serum2',
        'productVersion': build,
        'tags': ['Wavetable'],
        'url': 'https://xferrecords.com/',
        'vendor': 'Xfer Records',
        'version': schema,
    }
    payload = dict(payload)
    payload.setdefault('fileType', 'SerumPreset')
    payload['productVersion'] = build
    payload['version'] = schema
    raw = tool.cbor_dumps(payload)
    frame = zstandard.ZstdCompressor(level=3).compress(raw)
    header['hash'] = hashlib.md5(frame).hexdigest()
    header_raw = json.dumps(header, sort_keys=True, separators=(',', ':')).encode()
    return (tool.MAGIC
            + struct.pack('<Q', len(header_raw))
            + header_raw
            + struct.pack('<II', len(raw), 2)
            + frame)


def sample_payload(**overrides):
    payload = {
        'Env0': {'plainParams': {'kParamAttack': 0.01, 'kParamRelease': 0.25}},
        'LFO0': {'plainParams': {'kParamMode': 'Free', 'kParamRate': 1.0}},
        # 0.1 is not exact in single precision, so this one must stay float64.
        'VoiceFilter0': {'plainParams': {'kParamFreq': 0.1, 'kParamType': 'MgL12'}},
        'Global0': {'plainParams': {'kParamMonoToggle': 1.0,
                                    'kParamLimitSameNotePolyphony': 'Sustain'}},
        'ModSlot0': {'source': [3, 0], 'destModuleTypeString': 'VoiceFilter',
                     'destModuleID': 0, 'destModuleParamName': 'kParamFreq',
                     'destModuleParamID': 3, 'plainParams': {'kParamAmount': 50.0}},
        'presetName': 'Test Preset',
        'tags': ['Wavetable'],
    }
    payload.update(overrides)
    return payload


class WriteTempFile:
    """Context manager giving a path that the test can write to."""

    def __init__(self, data, name='Test Preset.SerumPreset'):
        self.data = data
        self.name = name

    def __enter__(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, self.name)
        with open(self.path, 'wb') as handle:
            handle.write(self.data)
        return self.path

    def __exit__(self, *exc):
        self.dir.cleanup()


class CborTests(unittest.TestCase):
    def test_scalars_round_trip(self):
        for value in (0, 1, -1, 23, 24, 255, 256, 65535, 2 ** 32, -2 ** 32,
                      0.0, 0.5, 0.1, 1e300, -1.5, True, False, None,
                      '', 'hello', '\u00e9\u4e16\u754c', b'\x00\x01\xff'):
            self.assertEqual(tool.cbor_loads(tool.cbor_dumps(value)), value)

    def test_containers_keep_order(self):
        value = {'b': 1, 'a': [1, 2, {'z': 3}], 'c': {'y': 2, 'x': 1}}
        encoded = tool.cbor_dumps(value)
        self.assertEqual(tool.cbor_loads(encoded), value)
        self.assertEqual(tool.cbor_dumps(tool.cbor_loads(encoded)), encoded)

    def test_floats_use_shortest_exact_form(self):
        # 0.5 survives single precision, so it must be written as float32 (0xfa).
        self.assertEqual(tool.cbor_dumps(0.5), b'\xfa?\x00\x00\x00')
        # 0.1 does not, so it must be written as float64 (0xfb).
        self.assertEqual(tool.cbor_dumps(0.1)[0], 0xFB)

    def test_integers_are_not_written_as_floats(self):
        self.assertEqual(tool.cbor_dumps(1), b'\x01')

    def test_rejects_truncated_data(self):
        for junk in (b'', b'\x1b\x00\x00\x00', b'\xff', b'\x82\x01'):
            with self.assertRaises(Exception):
                tool.cbor_loads(junk)

    def test_rejects_trailing_data(self):
        with self.assertRaises(ValueError):
            tool.cbor_loads(tool.cbor_dumps(1) + b'\x00')


class PresetTests(unittest.TestCase):
    def test_reads_back_what_it_built(self):
        with WriteTempFile(build_preset(sample_payload())) as path:
            preset = tool.Preset(path)
            self.assertEqual(preset.build, '2.1.5')
            self.assertEqual(preset.schema, 11.0)
            self.assertTrue(preset.hash_ok())
            self.assertEqual(preset.payload['Env0']['plainParams']['kParamAttack'], 0.01)

    def test_hash_is_the_md5_of_the_compressed_frame(self):
        with WriteTempFile(build_preset(sample_payload())) as path:
            preset = tool.Preset(path)
            self.assertEqual(preset.header['hash'],
                             hashlib.md5(preset.frame).hexdigest())
            # And it is not the hash of the payload.
            raw = zstandard.ZstdDecompressor().decompress(
                preset.frame, max_output_size=preset.payload_size)
            self.assertNotEqual(preset.header['hash'], hashlib.md5(raw).hexdigest())

    def test_edited_bytes_are_refused(self):
        blob = bytearray(build_preset(sample_payload()))
        blob[-1] ^= 0xFF
        with WriteTempFile(bytes(blob)) as path:
            with self.assertRaises(ValueError) as caught:
                tool.Preset(path)
            self.assertIn('damaged', str(caught.exception))

    def test_rejects_a_file_that_is_not_a_preset(self):
        with WriteTempFile(b'not a preset at all') as path:
            with self.assertRaises(ValueError):
                tool.Preset(path)


class DowngradeTests(unittest.TestCase):
    def convert(self, payload=None, **kwargs):
        blob = build_preset(payload or sample_payload())
        with WriteTempFile(blob) as path:
            with tempfile.TemporaryDirectory() as out:
                final, was = tool.convert_one(path, out, '2.0.23', 9.0,
                                             quiet=True, **kwargs)
                with open(final, 'rb') as handle:
                    return tool.Preset(final), was, handle.read()

    def test_stamps_both_copies_of_the_version(self):
        preset, was, _ = self.convert()
        self.assertEqual(was, '2.1.5')
        self.assertEqual(preset.build, '2.0.23')
        self.assertEqual(preset.schema, 9.0)
        self.assertEqual(preset.header['version'], 9.0)
        self.assertEqual(preset.payload['version'], 9.0)
        self.assertEqual(preset.payload['productVersion'], '2.0.23')

    def test_result_is_valid_and_self_consistent(self):
        preset, _, blob = self.convert()
        self.assertTrue(preset.hash_ok())
        # Length fields must add up to the file size exactly.
        header_len = struct.unpack('<Q', blob[9:17])[0]
        self.assertEqual(17 + header_len + 8 + len(preset.frame), len(blob))

    def test_string_parameter_is_repaired_to_a_number(self):
        preset, _, _ = self.convert()
        params = preset.payload['Global0']['plainParams']
        self.assertIsInstance(params[tool.LIMIT_POLY_PARAM], float)
        self.assertEqual(params[tool.LIMIT_POLY_PARAM], 1.0)

    def test_repair_can_be_switched_off(self):
        preset, _, _ = self.convert(repair=False)
        params = preset.payload['Global0']['plainParams']
        self.assertEqual(params[tool.LIMIT_POLY_PARAM], 'Sustain')

    def test_repair_leaves_a_numeric_parameter_alone(self):
        payload = sample_payload()
        payload['Global0'] = {'plainParams': {'kParamLimitSameNotePolyphony': 1.0}}
        preset, _, _ = self.convert(payload)
        self.assertEqual(preset.payload['Global0']['plainParams'][tool.LIMIT_POLY_PARAM],
                         1.0)

    def test_repair_tolerates_a_missing_global_section(self):
        payload = sample_payload()
        del payload['Global0']
        preset, _, _ = self.convert(payload)
        self.assertNotIn('Global0', preset.payload)

    def test_everything_else_is_left_untouched(self):
        """Apart from the stamps and the one repaired param, the payload is identical."""
        preset, _, _ = self.convert()
        after = dict(preset.payload)
        after.pop('version')
        after.pop('productVersion')
        expected = sample_payload()
        expected['fileType'] = 'SerumPreset'  # build_preset always writes this
        expected['Global0']['plainParams'][tool.LIMIT_POLY_PARAM] = 1.0
        self.assertEqual(after, expected)

    def test_float_precision_survives_the_rewrite(self):
        preset, _, _ = self.convert()
        self.assertEqual(preset.payload['VoiceFilter0']['plainParams']['kParamFreq'], 0.1)
        self.assertEqual(preset.payload['Env0']['plainParams']['kParamAttack'], 0.01)

    def test_modulation_routing_survives(self):
        preset, _, _ = self.convert()
        route = preset.payload['ModSlot0']
        self.assertEqual(route['source'], [3, 0])
        self.assertEqual(route['destModuleParamName'], 'kParamFreq')
        self.assertEqual(route['plainParams']['kParamAmount'], 50.0)

    def test_damaged_input_is_refused(self):
        blob = bytearray(build_preset(sample_payload()))
        blob[-1] ^= 0xFF
        with WriteTempFile(bytes(blob)) as path:
            with tempfile.TemporaryDirectory() as out:
                with self.assertRaises(ValueError):
                    tool.convert_one(path, out, '2.0.23', 9.0, quiet=True)

    def test_nothing_is_left_behind_when_writing_fails(self):
        blob = bytearray(build_preset(sample_payload()))
        blob[-1] ^= 0xFF
        with WriteTempFile(bytes(blob)) as path:
            with tempfile.TemporaryDirectory() as out:
                try:
                    tool.convert_one(path, out, '2.0.23', 9.0, quiet=True)
                except ValueError:
                    pass
                self.assertEqual(os.listdir(out), [])


class CommandLineTests(unittest.TestCase):
    def test_skips_presets_that_are_already_old_enough(self):
        blob = build_preset(sample_payload(), build='2.0.23', schema=9.0)
        with WriteTempFile(blob) as path:
            with tempfile.TemporaryDirectory() as out:
                tool.main([path, '--out-dir', out])
                self.assertEqual(os.listdir(out), [])

    def test_converts_a_whole_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in ('One.SerumPreset', 'Two.SerumPreset'):
                with open(os.path.join(folder, name), 'wb') as handle:
                    handle.write(build_preset(sample_payload()))
            with open(os.path.join(folder, 'notes.txt'), 'w') as handle:
                handle.write('ignore me')
            out = os.path.join(folder, 'out')
            self.assertEqual(tool.main([folder, '--out-dir', out]), 0)
            self.assertEqual(sorted(os.listdir(out)),
                             ['One.SerumPreset', 'Two.SerumPreset'])

    def test_originals_are_not_modified(self):
        blob = build_preset(sample_payload())
        with WriteTempFile(blob) as path:
            with tempfile.TemporaryDirectory() as out:
                tool.main([path, '--out-dir', out])
            with open(path, 'rb') as handle:
                self.assertEqual(handle.read(), blob)

    def test_bad_file_is_reported_without_stopping_the_batch(self):
        with tempfile.TemporaryDirectory() as folder:
            with open(os.path.join(folder, 'Good.SerumPreset'), 'wb') as handle:
                handle.write(build_preset(sample_payload()))
            with open(os.path.join(folder, 'Broken.SerumPreset'), 'wb') as handle:
                handle.write(b'this is not a preset')
            exit_code = tool.main([folder, '--out-dir', os.path.join(folder, 'out')])
            self.assertEqual(exit_code, 1)
            self.assertEqual(os.listdir(os.path.join(folder, 'out')),
                             ['Good.SerumPreset'])


class PackTests(unittest.TestCase):
    """A .SerumPack is a zip of presets plus the wavetables they use."""

    def make_pack(self, folder, presets=2, manifest=None, extra=True,
                  name='Test Bank.SerumPack'):
        path = os.path.join(folder, name)
        with zipfile.ZipFile(path, 'w') as pack:
            pack.writestr('Presets/Packs/@test/Test Bank/.SerumPack.json',
                          json.dumps(manifest if manifest is not None else {
                              'author': '@test', 'description': '',
                              'name': 'Test Bank', 'presetVersion': 11.0,
                              'productVersion': '2.1.5', 'url': ''},
                              sort_keys=True, separators=(',', ':')))
            if extra:
                pack.writestr('Tables/Packs/@test/Test Bank/table.wav',
                              b'RIFF' + bytes(range(256)), zipfile.ZIP_DEFLATED)
            for index in range(presets):
                pack.writestr(f'Presets/Packs/@test/Test Bank/Preset {index}.SerumPreset',
                              build_preset(sample_payload()))
            pack.writestr('Samples/Packs/@test/Test Bank/last.wav', b'RIFFlast')
        return path

    def test_converts_every_preset_and_keeps_everything_else(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.make_pack(folder, presets=3)
            with zipfile.ZipFile(path) as original:
                before = original.namelist()
            final, done, skipped = tool.convert_pack(
                path, os.path.join(folder, 'out'), '2.0.23', 9.0, quiet=True)
            self.assertEqual((done, skipped), (3, 0))
            with zipfile.ZipFile(final) as rebuilt:
                self.assertEqual(rebuilt.namelist(), before)
                manifest = json.loads(rebuilt.read(
                    'Presets/Packs/@test/Test Bank/.SerumPack.json'))
                self.assertEqual(manifest['productVersion'], '2.0.23')
                self.assertEqual(manifest['presetVersion'], 9.0)
                self.assertEqual(manifest['author'], '@test')
                self.assertEqual(rebuilt.read('Tables/Packs/@test/Test Bank/table.wav'),
                                 b'RIFF' + bytes(range(256)))
                preset = tool.Preset.from_bytes(rebuilt.read(
                    'Presets/Packs/@test/Test Bank/Preset 2.SerumPreset'))
                self.assertEqual(preset.build, '2.0.23')
                self.assertEqual(preset.schema, 9.0)
                self.assertTrue(preset.hash_ok())

    def test_originals_are_never_touched(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.make_pack(folder, presets=1)
            with open(path, 'rb') as handle:
                before = handle.read()
            tool.convert_pack(path, os.path.join(folder, 'out'),
                              '2.0.23', 9.0, quiet=True)
            with open(path, 'rb') as handle:
                self.assertEqual(handle.read(), before)

    def test_a_pack_with_nothing_to_do_writes_no_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.make_pack(folder, presets=1, manifest={
                'author': '@test', 'presetVersion': 9.0,
                'productVersion': '2.0.23'})
            # Rebuild the preset inside at the target version.
            with zipfile.ZipFile(path) as pack:
                names = pack.namelist()
                blobs = {n: pack.read(n) for n in names}
            target = build_preset(sample_payload(), build='2.0.23', schema=9.0)
            blobs['Presets/Packs/@test/Test Bank/Preset 0.SerumPreset'] = target
            with zipfile.ZipFile(path, 'w') as pack:
                for name in names:
                    pack.writestr(name, blobs[name])
            out = os.path.join(folder, 'out')
            final, done, skipped = tool.convert_pack(path, out, '2.0.23', 9.0,
                                                     quiet=True)
            self.assertIsNone(final)
            self.assertEqual((done, skipped), (0, 1))
            self.assertFalse(os.path.exists(out))

    def test_a_stale_manifest_alone_is_restamped(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.make_pack(folder, presets=0, manifest={
                'author': '@test', 'presetVersion': 11.0,
                'productVersion': '2.1.5'})
            # One preset that is already old enough lives in the pack.
            with zipfile.ZipFile(path, 'a') as pack:
                pack.writestr('Presets/Packs/@test/Test Bank/Old.SerumPreset',
                              build_preset(sample_payload(), build='2.0.23',
                                           schema=9.0))
            final, done, skipped = tool.convert_pack(
                path, os.path.join(folder, 'out'), '2.0.23', 9.0, quiet=True)
            self.assertEqual((done, skipped), (0, 1))
            with zipfile.ZipFile(final) as rebuilt:
                manifest = json.loads(rebuilt.read(
                    'Presets/Packs/@test/Test Bank/.SerumPack.json'))
                self.assertEqual(manifest['productVersion'], '2.0.23')

    def test_a_damaged_preset_fails_the_pack_and_leaves_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.make_pack(folder, presets=1)
            with zipfile.ZipFile(path, 'a') as pack:
                pack.writestr('Presets/Packs/@test/Test Bank/Broken.SerumPreset',
                              b'this is not a preset')
            out = os.path.join(folder, 'out')
            with self.assertRaises(ValueError):
                tool.convert_pack(path, out, '2.0.23', 9.0, quiet=True)
            self.assertFalse(os.path.exists(out))

    def test_a_pack_without_presets_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.make_pack(folder, presets=0)
            with self.assertRaises(ValueError):
                tool.convert_pack(path, os.path.join(folder, 'out'),
                                  '2.0.23', 9.0, quiet=True)

    def test_conversion_into_the_source_folder_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.make_pack(folder, presets=1)
            with open(path, 'rb') as handle:
                before = handle.read()
            final, _, _ = tool.convert_pack(path, folder, '2.0.23', 9.0,
                                            quiet=True)
            self.assertNotEqual(os.path.abspath(final), os.path.abspath(path))
            self.assertIn('2.0.23', os.path.basename(final))
            with open(path, 'rb') as handle:
                self.assertEqual(handle.read(), before)

    def test_the_command_line_accepts_a_pack(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.make_pack(folder, presets=2)
            out = os.path.join(folder, 'out')
            self.assertEqual(tool.main([path, '--out-dir', out]), 0)
            self.assertEqual(os.listdir(out), ['Test Bank.SerumPack'])

    def test_a_folder_with_a_pack_and_loose_presets_does_both(self):
        with tempfile.TemporaryDirectory() as folder:
            self.make_pack(folder, presets=1)
            with open(os.path.join(folder, 'Loose.SerumPreset'), 'wb') as handle:
                handle.write(build_preset(sample_payload()))
            out = os.path.join(folder, 'out')
            tool.main([folder, '--out-dir', out])
            self.assertEqual(sorted(os.listdir(out)),
                             ['Loose.SerumPreset', 'Test Bank.SerumPack'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
