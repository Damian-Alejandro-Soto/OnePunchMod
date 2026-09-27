"""Local Tk interaction smoke test and native WAV routing checks; no avatars are applied."""
import array
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import wave

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
import one_punch_mod as mod
import one_punch_ui_audio as audio


class ArenaTests(unittest.TestCase):
    def test_portrait_roster_gallery_search_and_equipping(self):
        errors=[]
        with patch.object(mod.App,'full_load',lambda *a:None):
            app=mod.App()
            self.addCleanup(app.destroy)
            app.report_callback_exception=lambda *args:errors.append(args)
            app._ui_sound=lambda *args:None
            data=json.loads((PROJECT/'Cache/hon_avatar_switcher_cache_v135.json').read_text())
            app.arc=str(PROJECT.parent/'heroes of newerth/resources0.jz')
            app.z=str(PROJECT.parent/'tools/7za.exe')
            app.lmembers=data['legacy_members'];app.larcs=[];app.heroes=[]
            for key,record in sorted(mod.archive_index(data['reborn_paths']).items()):
                if not mod.is_real_hero_folder(record['folder']):continue
                legacy_folder=data['resolved_legacy_map'].get(record['folder'].lower())
                reborn={'default'}|set(record['alts'])
                legacy=set(data['legacy_index'].get(legacy_folder or '',{}))-reborn
                app.heroes.append(dict(key=key,folder=record['folder'],legacy_folder=legacy_folder,
                    name=mod.pretty_hero(record['folder']),archive=record,legacy=legacy,reborn=reborn,
                    avatars=sorted(reborn|legacy,key=mod.avatar_sort),current='default'))
            app._names=json.loads((PROJECT/'Cache/avatar_names.json').read_text())
            def pump(seconds=.25):
                end=time.monotonic()+seconds
                while time.monotonic()<end:app.update();time.sleep(.005)
            app.render_all();pump(2)
            self.assertEqual(len(app._roster_tiles),len(app.heroes))
            hero=next(h for h in app.heroes if h['folder']=='pebbles')
            app._select_hero(hero);pump()
            self.assertEqual(len(app._avatar_tiles),len(hero['avatars']))
            self.assertEqual(app.avatar_label(hero,'alt2'),'Jade Giant Pebbles')
            with patch.object(app,'change') as apply:
                app.cards[hero['key']]['buttons']['alt2'].invoke()
                apply.assert_called_once_with(hero,'alt2')
                apply.reset_mock()
                app._show_avatar(hero,'alt3')
                apply.assert_not_called()
                app.equip_btn.invoke()
                apply.assert_called_once_with(hero,'alt3')
            hero['current']='alt2';app.refresh_card(hero)
            self.assertEqual(app.cards[hero['key']]['badges']['alt2'].cget('text'),'EQUIPPED')
            self.assertEqual(app.equip_btn.cget('state'),'disabled')
            for geometry in ('1120x740','1480x920','1920x1080'):
                app.geometry(geometry);pump()
                for tile in app._avatar_tiles:
                    self.assertLessEqual(tile.winfo_x()+tile.winfo_width(),app.avatar_canvas.winfo_width())
                self.assertGreater(app.avatar_canvas.winfo_height(),170)
            app.search_var.set('pebbles');pump()
            self.assertEqual(len(app._visible_heroes),1)
            app.search_var.set('unmatched hero search');pump()
            self.assertFalse(app._visible_heroes)
            app.search_var.set('');pump(1)
            self.assertEqual(len(app._roster_tiles),len(app.heroes))
            app.show_extras();pump()
            self.assertTrue(app._settings_window.winfo_exists())
            app._settings_window.destroy()
            self.assertFalse(errors,errors)

    def test_audio_volume_mute_and_wav_route(self):
        with tempfile.TemporaryDirectory(dir=PROJECT/'Cache') as tmp:
            base=Path(tmp)/'OnePunchMod';base.mkdir()
            sound=base/'click.wav'
            with wave.open(str(sound),'wb') as stream:
                stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(22050)
                stream.writeframes(array.array('h',[1000,-1000,2000,-2000]).tobytes())
            settings=base/'one_punch_settings.ini'
            settings.write_text('[audio]\nenabled=true\nui_click=click.wav\n[ui]\nsound_volume=0.5\n')
            with patch('winsound.PlaySound') as play,patch.object(audio.subprocess,'Popen') as spawn:
                audio.play(tmp,'ui_click')
                play.assert_called_once();spawn.assert_not_called()
                with wave.open(play.call_args.args[0],'rb') as stream:
                    self.assertEqual(list(array.array('h',stream.readframes(4))),[500,-500,1000,-1000])
                play.reset_mock()
                settings.write_text('[audio]\nenabled=false\nui_click=click.wav\n[ui]\nsound_volume=0.5\n')
                audio.play(tmp,'ui_click');play.assert_not_called()


if __name__=='__main__':unittest.main()
