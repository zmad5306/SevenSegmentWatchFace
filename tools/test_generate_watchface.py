"""Regression guards for the Pixel Watch clock offload requirements."""
import struct
import unittest
import xml.etree.ElementTree as ET
import zlib

import generate_watchface as face


class AmbientClockTests(unittest.TestCase):
    def test_clock_structure_and_opacity(self):
        root = ET.fromstring(face.build_xml())
        clocks = root.findall('.//DigitalClock')
        self.assertEqual(len(clocks), 2)
        self.assertEqual([c.find('TimeText').get('format') for c in clocks], ['hh', 'mm'])
        parents = {child: parent for parent in root.iter() for child in parent}
        for clock in clocks:
            text = clock.find('TimeText')
            self.assertEqual(text.get('hourFormat'), 'SYNC_TO_DEVICE')
            node = text
            while node is not None:
                self.assertNotEqual(node.tag, 'Condition')
                self.assertEqual(node.get('alpha', '255'), '255')
                self.assertFalse(node.findall("./Variant[@target='alpha']"))
                node = parents.get(node)
        expressions = '\n'.join(e.text or '' for e in root.findall('.//Expression'))
        self.assertNotIn('[HOUR', expressions)
        self.assertNotIn('[MINUTE', expressions)

    def test_glyphs_match_font_and_preserve_spacing(self):
        root = ET.fromstring(face.build_xml())
        chars = root.findall('./BitmapFonts/BitmapFont/Character')
        self.assertEqual({c.get('name') for c in chars}, set('0123456789'))
        keep = (face.RES / 'raw/keep.xml').read_text()
        self.assertIn('@drawable/seg_time_*', keep)
        # Independent segment masks, clockwise from top with middle last.
        masks = ['1111110', '0110000', '1101101', '1111001', '0110011',
                 '1011011', '1011111', '1110000', '1111111', '1111011']
        centers = [(40, 6), (67, 31), (67, 93), (40, 118),
                   (13, 93), (13, 31), (40, 62)]
        for char in chars:
            value = int(char.get('name'))
            png = face.build_time_glyph(value)
            width, height = struct.unpack('>II', png[16:24])
            self.assertEqual((width, height), (80, 124))
            self.assertEqual((width, height), (int(char.get('width')), int(char.get('height'))))
            self.assertEqual(png, (face.RES / 'drawable-nodpi' / (char.get('resource') + '.png')).read_bytes())
            offset, compressed = 8, bytearray()
            while offset < len(png):
                length = struct.unpack('>I', png[offset:offset + 4])[0]
                if png[offset + 4:offset + 8] == b'IDAT':
                    compressed.extend(png[offset + 8:offset + 8 + length])
                offset += length + 12
            pixels = zlib.decompress(compressed)
            stride = width * 4 + 1
            for (x, y), lit in zip(centers, masks[value]):
                self.assertEqual(pixels[y * stride + 1 + x * 4 + 3], 255 if lit == '1' else 0)
            for y in range(height):
                self.assertEqual(pixels[y * stride], 0)
                self.assertEqual(pixels[y * stride + 4], 0)
                self.assertEqual(pixels[y * stride + width * 4], 0)

    def test_generated_xml_is_current(self):
        self.assertEqual(face.build_xml(), (face.RES / 'raw/watchface.xml').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
