"""Offline generation checks. No Runtime, prepared recipes, or historical assets are modified."""
from contextlib import ExitStack
from pathlib import Path
import importlib.util
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
import one_punch_mod as mod


def generate(hero,av,destination,module=mod):
    """Exercise the real hero generator, isolating asset/ability publishing side effects."""
    mod=module
    hero=dict(hero,_root=str(PROJECT.parent),legacy=[av],reborn=['default'])
    source=PROJECT/'Cache'/'entities'/hero['folder']/'hero.entity'
    with ExitStack() as stack:
        for name in ('_normalize_explicit_cosmetic_refs','_apply_legacy_ability_overrides',
                     '_suppress_legacy_body_shell','_save_selection_recipe','_publish_prepared_avatar','diag'):
            stack.enter_context(patch.object(mod,name,return_value=0))
        stack.enter_context(patch.object(mod,'source_entity',return_value=str(source)))
        stack.enter_context(patch.object(mod,'override_path',return_value=str(destination)))
        stack.enter_context(patch.object(mod,'_avatar_assets_already_installed',return_value=True))
        stack.enter_context(patch.object(mod,'extract_member',side_effect=AssertionError('archive access')))
        mod.apply_avatar(str(PROJECT.parent),hero,av,None,None,str(destination.parent),[],{},force_rebuild=True)
    return destination.read_text(encoding='utf-8')


def gameplay_tree(text):
    root=ET.fromstring(text)
    for node in root.iter():
        for key in list(node.attrib):
            if mod.is_avatar_cosmetic_attr(key) or key in mod.HERO_MODIFIER_COSMETIC_ATTRS:
                del node.attrib[key]
    def structure(node):
        return (node.tag,dict(node.attrib),(node.text or '').strip(),[structure(n) for n in node])
    return structure(root)


class ModifierCosmeticsTests(unittest.TestCase):
    def test_growth_and_gameplay_preservation(self):
        hero={'folder':'pebbles','legacy_folder':'rocky'}
        pristine=(PROJECT/'Cache/entities/pebbles/hero.entity').read_text(encoding='utf-8-sig')
        with tempfile.TemporaryDirectory(dir=PROJECT/'Cache') as tmp:
            expected_scales={
                'alt2':['1.15','1.45','1.65'],
                'alt3':['1','1','1'],
                'alt6':['1.25','1.55','1.7'],
                'alt12':['0.85','0.95','1.3'],
                'alt13':['1.4','1.6','1.8'],
            }
            for av in ['alt']+['alt'+str(i) for i in range(2,14)]:
                expected=expected_scales.get(av,['1.485','1.775','2.07'])
                with self.subTest(avatar=av):
                    text=generate(hero,av,Path(tmp)/'hero.entity')
                    self.assertEqual(gameplay_tree(text),gameplay_tree(pristine))
                    root=ET.fromstring(text)
                    modifiers=[root.find(f"modifier[@key='Rocky_Grow{i}']") for i in range(1,4)]
                    self.assertEqual([n.get('preglobalscale') for n in modifiers],expected)
                    for level,node in enumerate(modifiers,1):
                        self.assertEqual(node.get('walkanim'),f'ability_4_walk_{level}')
                        model=node.get('model',root.get('model'))
                        if av in ('alt11','alt12','alt13'):
                            self.assertIn(f'/Rocky_Grow{level}/model.mdf',model)
                        if av=='alt3':
                            self.assertEqual(node.get('modelscale'),['.9','.92','1.1'][level-1])
                            if level==3:self.assertIn('/ability_04/transformed/model.mdf',model)
                        for directory in ('Runtime','PreparedAssets'):
                            path=PROJECT/directory/model.lstrip('/')
                            self.assertTrue(path.is_file(),str(path))
                            animation=ET.parse(path).getroot().find(f"anim[@name='{node.get('walkanim')}']")
                            self.assertIsNotNone(animation)
                            self.assertTrue((path.parent/animation.get('clip')).is_file())
                            if node.get('passiveeffect'):
                                self.assertTrue((PROJECT/directory/node.get('passiveeffect').lstrip('/')).is_file())
                    if av=='alt2':
                        self.assertTrue(all(n.get('passiveeffect')=='/heroes/rocky/alt2/effects/body_grow1.effect'
                                            for n in modifiers))

    def test_only_existing_direct_modifiers_and_cosmetic_fields(self):
        text='<hero><modifier key="live" damage="9"><modifier key="live" modelscale="8"/></modifier></hero>'
        result=mod._overlay_hero_modifier_cosmetics(text,{'live':{'modelscale':'2','damage':'1'},
                                                       'absent':{'modelscale':'4'}})
        root=ET.fromstring(result)
        self.assertEqual(root[0].get('damage'),'9')
        self.assertEqual(root[0].get('modelscale'),'2')
        self.assertEqual(root[0][0].get('modelscale'),'8')
        self.assertEqual(len(root),1)

    def test_root_patch_leaves_modifier_values_and_actions_untouched(self):
        text='<hero preglobalscale="1"><modifier key="grow" preglobalscale="2"><onframe/></modifier></hero>'
        actual=mod._transform_hero_root(text,lambda tag:tag.replace('"1"','"0.95"'))
        self.assertEqual(actual,'<hero preglobalscale="0.95"><modifier key="grow" preglobalscale="2"><onframe/></modifier></hero>')

    def test_known_good_hero_root_cosmetics_and_gameplay(self):
        spec=importlib.util.spec_from_file_location('before_growth',PROJECT/'Cache/one_punch_mod_v149_before_growth_fix.py')
        baseline=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(baseline)
        cases=[('amun_ra','ra',['alt3','alt5','alt10']),
               ('accursed','accursed',['alt']+['alt'+str(i) for i in range(2,9)]+['pog_skin'])]
        with tempfile.TemporaryDirectory(dir=PROJECT/'Cache') as tmp:
            for folder,legacy,avatars in cases:
                pristine=(PROJECT/'Cache/entities'/folder/'hero.entity').read_text(encoding='utf-8-sig')
                for av in avatars:
                    with self.subTest(hero=folder,avatar=av):
                        oldtext=generate({'folder':folder,'legacy_folder':legacy},av,Path(tmp)/'before.entity',baseline)
                        oldroot=ET.fromstring(oldtext)
                        text=generate({'folder':folder,'legacy_folder':legacy},av,Path(tmp)/'hero.entity')
                        newroot=ET.fromstring(text)
                        self.assertEqual(newroot.attrib,oldroot.attrib)
                        self.assertEqual(gameplay_tree(text),gameplay_tree(pristine))


if __name__=='__main__':
    unittest.main()
