"""Run with python tools/test_legacy_names.py; never writes Runtime or source assets."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
import one_punch_mod as mod


class LegacyNamesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=PROJECT / 'Cache')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.cache = self.base / 'cache'
        self.cache.mkdir()
        p = patch.object(mod, 'cache_dir', return_value=str(self.cache))
        p.start()
        self.addCleanup(p.stop)

    def test_installed_pebbles_and_regression_names_without_archives(self):
        heroes = [
            {'folder': 'pebbles', 'legacy_folder': 'rocky',
             'legacy': ['alt'] + ['alt' + str(i) for i in range(2, 14)]},
            {'folder': 'amunra', 'legacy_folder': 'ra', 'legacy': ['alt3', 'alt5', 'alt10']},
            {'folder': 'accursed', 'legacy': ['alt'] + ['alt' + str(i) for i in range(2, 9)] + ['pog_skin']},
        ]
        # Old caches must not hide newly available extracted metadata.
        (self.cache / 'legacy_localization_en.json').write_text('{}')
        (self.cache / 'avatar_names.json').write_text('{"rocky::alt2":"Alt2"}')
        with patch.object(mod, 'extract_member', side_effect=AssertionError('archive access')):
            names = mod.build_legacy_name_cache(str(PROJECT.parent), heroes, None, [], {}, str(self.base))
        expected = ['Golden Pebbles', 'Jade Giant Pebbles', 'Frankie Pebbles',
                    'Earthroc Pebbles', 'Savior Pebbles', 'Rocky', 'Boulderdash',
                    'Siege Golem Pebbles', 'Easter Island Pebbles', 'Chuck Pebbles',
                    'Stonewall Pebbles', 'P-800', 'Diamante']
        self.assertEqual([names['rocky::' + a] for a in heroes[0]['legacy']], expected)
        for h in heroes[1:]:
            for av in h['legacy']:
                value = names[(h.get('legacy_folder') or h['folder']) + '::' + av]
                self.assertNotEqual(value, mod.pretty_avatar(av))
        self.assertIn('00000000', mod.legacy_fs_icon(str(PROJECT.parent), heroes[0], 'alt2'))

    def test_filesystem_entity_precedence_and_archive_fallback(self):
        assets = self.base / 'assets'
        entity = assets / 'heroes' / 'alias' / 'hero.entity'
        entity.parent.mkdir(parents=True)
        entity.write_text('<altavatar key="Hero_Alias.Alt2" displayname="Extracted Name"/>')
        archived = self.base / 'archive.entity'
        archived.write_text('<altavatar key="Hero_Alias.Alt2" displayname="Archive Name"/>')
        hero = {'folder': 'modern', 'legacy_folder': 'alias', 'legacy': ['alt2']}
        members = {'archive.s2z': ['heroes/alias/hero.entity']}
        with patch.object(mod, 'legacy_assets_root', return_value=str(assets)), \
             patch.object(mod, 'extract_member', return_value=str(archived)) as extract:
            result = mod.build_legacy_name_cache('', [hero], None, [], members, str(self.base))
            self.assertEqual(result['alias::alt2'], 'Extracted Name')
            extract.assert_not_called()
            entity.unlink()
            result = mod.build_legacy_name_cache('', [hero], None, [], members, str(self.base))
            self.assertEqual(result['alias::alt2'], 'Archive Name')
            extract.assert_called_once()

    def test_archive_store_mapping_and_cache_refresh(self):
        assets = self.base / 'assets'
        assets.mkdir()
        table = self.base / 'interface.str'
        table.write_text('mstore_product42_name Archive Avatar\n')
        package = self.base / 'store.package'
        package.write_text('<instance product="Hero_Alias.Alt10" id="42"/>')
        files = {'stringtables/interface_en.str': str(table),
                 'content/store_avatars.package': str(package)}
        members = {'archive.s2z': list(files)}
        with patch.object(mod, 'legacy_assets_root', return_value=str(assets)), \
             patch.object(mod, 'extract_member', side_effect=lambda z, a, p, t: files[p]) as extract:
            loc = mod._legacy_localization('', None, [], members, str(self.base))
            hero = {'folder': 'modern', 'legacy_folder': 'alias'}
            self.assertEqual(mod._name_from_legacy_localization(loc, hero, 'alt10'), 'Archive Avatar')
            self.assertEqual(mod._name_from_legacy_localization(loc, hero, 'alt'), '')
            extract.reset_mock()
            self.assertEqual(mod._legacy_localization('', None, [], members, str(self.base)), loc)
            extract.assert_not_called()
            local = assets / 'stringtables' / 'interface_en.str'
            local.parent.mkdir()
            local.write_text('mstore_product42_name Extracted Avatar\n')
            loc = mod._legacy_localization('', None, [], members, str(self.base))
            self.assertEqual(loc['hero_alias.alt10_name'], 'Extracted Avatar')
            table.write_text('mstore_product42_name Changed Archive\n')
            local.unlink()
            loc = mod._legacy_localization('', None, [], members, str(self.base), force=True)
            self.assertEqual(loc['hero_alias.alt10_name'], 'Changed Archive')


if __name__ == '__main__':
    unittest.main()
