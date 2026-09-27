"""Developer-only PreparedAssets builder.

This command-line utility is intentionally separate from the player launcher.
It may read the old extracted source tree and publish normalized packages into
PreparedAssets; the GUI launcher never imports or runs this file.
"""
import os, re, json, shutil, subprocess, tempfile, tkinter as tk, time, threading, random, traceback, configparser, sys
from pathlib import Path

_voice_state_lock=threading.Lock()
_active_voice_stop=None
_active_voice_process=None

def _run_hidden(args, **kwargs):
    """Run command-line helpers without flashing console windows on Windows."""
    if os.name == "nt":
        kwargs.setdefault("creationflags", getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        kwargs.setdefault("startupinfo", si)
    return subprocess.run(args, **kwargs)
from tkinter import ttk, messagebox, filedialog

# Ask Windows to let the application render at native DPI instead of bitmap-scaling it.
# Equivalent to Compatibility > High DPI scaling override > Application.
if os.name == "nt":
    try:
        import ctypes
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception:
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

try:
    from PIL import Image, ImageOps
except Exception:
    Image = ImageOps = None

APP = "One Punch Mod | Hero Arena"
DEFAULT_ROOT = r"D:\HoN"
#DEFAULT_LEGACY = r"D:\HoN\Heroes of Newerth x64"
DEFAULT_LEGACY = r"D:\HoN\OnePunchMod\LegacyAssets"
GRID_COLS = 3
CURRENT_SIZE = 74
AVATAR_SIZE = 78


SOUND_DEFAULTS = {
    "ui_hover": "",
    "ui_click": "",
    "hero_select": "",
    "avatar_hover": "",
    "avatar_select": "",
    "apply_success": "",
    "apply_error": "",
    "launch_game": "",
}

def settings_path(root):
    return os.path.join(root,"OnePunchMod","one_punch_settings.ini")

def avatar_selections_path(root):
    """User-owned avatar selections; safe to remove before packaging a release."""
    return os.path.join(root,"OnePunchMod","one_punch_avatar_selections.json")

def load_avatar_selections(root):
    """Load saved choices and report whether the file was present and valid."""
    path=avatar_selections_path(root)
    if not os.path.isfile(path):
        return {},False
    try:
        data=json.load(open(path,"r",encoding="utf-8"))
        values=data.get("avatars",data) if isinstance(data,dict) else {}
        if not isinstance(values,dict):
            return {},False
        return {str(k).lower():str(v).lower() for k,v in values.items()},True
    except (OSError,ValueError,TypeError):
        return {},False

def save_avatar_selections(root,heroes):
    """Atomically persist the currently equipped avatar for every hero."""
    path=avatar_selections_path(root)
    values={}
    for hero in heroes or []:
        folder=str(hero.get("folder","")).lower()
        current=str(hero.get("current","default")).lower()
        if folder:
            values[folder]=current if current in set(hero.get("avatars") or {"default"}) else "default"
    payload={"version":1,"avatars":values}
    temporary=path+".tmp"
    try:
        os.makedirs(os.path.dirname(path),exist_ok=True)
        with open(temporary,"w",encoding="utf-8") as f:
            json.dump(payload,f,ensure_ascii=False,indent=2,sort_keys=True)
        os.replace(temporary,path)
        return True
    except OSError:
        try:
            if os.path.isfile(temporary):os.remove(temporary)
        except OSError:pass
        return False

def ensure_settings(root):
    p=settings_path(root); os.makedirs(os.path.dirname(p),exist_ok=True)
    if not os.path.isfile(p):
        c=configparser.ConfigParser();c["audio"]=SOUND_DEFAULTS;c["ui"]={"animations":"true","animation_speed":"1.0","sound_volume":"0.8"}
        with open(p,"w",encoding="utf-8") as f:c.write(f)
    return p

def tool_fonts_dir(root):
    return os.path.join(one_punch_root(root),"fonts")

FONT_ROLE_DEFINITIONS = (
    ("game", "Legacy game text", (".ttf", ".otf")),
    ("system", "Legacy system text", (".ttf", ".otf")),
    ("hon_regular", "HoN interface regular", (".ttf", ".otf")),
    ("hon_bold", "HoN interface bold", (".ttf", ".otf")),
    ("hon_condensed", "HoN interface condensed", (".ttf", ".otf")),
    ("inter_regular", "Web UI Inter regular", (".woff2",)),
    ("inter_semibold", "Web UI Inter semibold", (".woff2",)),
    ("inter_bold", "Web UI Inter bold", (".woff2",)),
    ("barlow", "Web UI Barlow", (".woff2",)),
    ("barlow_condensed", "Web UI Barlow condensed", (".woff2",)),
)


def font_role_definitions():
    return FONT_ROLE_DEFINITIONS


def available_tool_fonts(root, extensions=None):
    """Return selectable Windows and bundled font files."""
    allowed=tuple(x.lower() for x in (extensions or (".ttf", ".otf", ".woff2")))
    locations=[("Windows",os.path.join(os.environ.get("WINDIR",r"C:\\Windows"),"Fonts")),
               ("Tool fonts",tool_fonts_dir(root))]
    found=[];seen=set()
    for label,folder in locations:
        if not os.path.isdir(folder):continue
        try:names=sorted(os.listdir(folder),key=str.lower)
        except OSError:continue
        for name in names:
            if not name.lower().endswith(allowed):continue
            path=os.path.abspath(os.path.join(folder,name))
            if not os.path.isfile(path):continue
            key=os.path.normcase(path)
            if key in seen:continue
            seen.add(key);found.append((f"{label}: {name}",path))
    return found

def saved_font_paths(root):
    path=settings_path(root)
    values={role:"" for role,_,_ in FONT_ROLE_DEFINITIONS}
    if not os.path.isfile(path):return values
    try:
        cfg=configparser.ConfigParser();cfg.read(path,encoding="utf-8")
        legacy=cfg.get("font","selected",fallback="").strip()
        for role,_,extensions in FONT_ROLE_DEFINITIONS:
            fallback=legacy if role in ("game","system","hon_regular","hon_bold","hon_condensed") else ""
            value=cfg.get("font",role,fallback=fallback).strip()
            if os.path.isfile(value) and value.lower().endswith(extensions):values[role]=value
        return values
    except (OSError,configparser.Error):
        return values


def saved_font_path(root):
    return saved_font_paths(root).get("hon_regular", "")

def save_font_paths(root,values):
    p=settings_path(root);os.makedirs(os.path.dirname(p),exist_ok=True)
    cfg=configparser.ConfigParser()
    if os.path.isfile(p):
        try:cfg.read(p,encoding="utf-8")
        except configparser.Error:cfg=configparser.ConfigParser()
    if not cfg.has_section("font"):cfg.add_section("font")
    regular=values.get("hon_regular", "")
    cfg.set("font","selected",os.path.abspath(regular) if regular else "")
    for role,_,_ in FONT_ROLE_DEFINITIONS:
        value=values.get(role, "")
        cfg.set("font",role,os.path.abspath(value) if value else "")
    with open(p,"w",encoding="utf-8") as f:cfg.write(f)

def save_font_path(root,path):
    values=saved_font_paths(root)
    for role in ("game","system","hon_regular","hon_bold","hon_condensed"):
        values[role]=path or ""
    save_font_paths(root,values)


def font_role_targets(root,role):
    """Return every mounted file used by one selectable font role."""
    runtime=switcher_root(root)
    rel={
        "game":["core/fonts/game.ttf"],
        "system":["core/fonts/system.ttf"],
        "hon_regular":["preact/public/assets/fonts/hon_intl.ttf","preact/dist/assets/fonts/hon_intl.ttf"],
        "hon_bold":["preact/public/assets/fonts/hon_bold_intl.ttf","preact/dist/assets/fonts/hon_bold_intl.ttf"],
        "hon_condensed":["preact/public/assets/fonts/hon_cond_intl.ttf","preact/dist/assets/fonts/hon_cond_intl.ttf"],
        "inter_regular":["preact/public/assets/fonts/inter-regular.woff2","preact/dist/assets/fonts/inter-regular.woff2"],
        "inter_semibold":["preact/public/assets/fonts/inter-semibold.woff2","preact/dist/assets/fonts/inter-semibold.woff2"],
        "inter_bold":["preact/public/assets/fonts/inter-bold.woff2","preact/dist/assets/fonts/inter-bold.woff2"],
        "barlow":[
            "preact/public/assets/fonts/barlow/barlow-400-latin.woff2","preact/public/assets/fonts/barlow/barlow-400-latin-ext.woff2","preact/public/assets/fonts/barlow/barlow-500-latin.woff2","preact/public/assets/fonts/barlow/barlow-500-latin-ext.woff2","preact/public/assets/fonts/barlow/barlow-600-latin.woff2","preact/public/assets/fonts/barlow/barlow-600-latin-ext.woff2","preact/public/assets/fonts/barlow/barlow-700-latin.woff2","preact/public/assets/fonts/barlow/barlow-700-latin-ext.woff2",
            "preact/dist/assets/fonts/barlow/barlow-400-latin.woff2","preact/dist/assets/fonts/barlow/barlow-400-latin-ext.woff2","preact/dist/assets/fonts/barlow/barlow-500-latin.woff2","preact/dist/assets/fonts/barlow/barlow-500-latin-ext.woff2","preact/dist/assets/fonts/barlow/barlow-600-latin.woff2","preact/dist/assets/fonts/barlow/barlow-600-latin-ext.woff2","preact/dist/assets/fonts/barlow/barlow-700-latin.woff2","preact/dist/assets/fonts/barlow/barlow-700-latin-ext.woff2",
        ],
        "barlow_condensed":[
            "preact/public/assets/fonts/barlow/barlow-condensed-500-latin.woff2","preact/public/assets/fonts/barlow/barlow-condensed-500-latin-ext.woff2","preact/public/assets/fonts/barlow/barlow-condensed-600-latin.woff2","preact/public/assets/fonts/barlow/barlow-condensed-600-latin-ext.woff2","preact/public/assets/fonts/barlow/barlow-condensed-700-latin.woff2","preact/public/assets/fonts/barlow/barlow-condensed-700-latin-ext.woff2",
            "preact/dist/assets/fonts/barlow/barlow-condensed-500-latin.woff2","preact/dist/assets/fonts/barlow/barlow-condensed-500-latin-ext.woff2","preact/dist/assets/fonts/barlow/barlow-condensed-600-latin.woff2","preact/dist/assets/fonts/barlow/barlow-condensed-600-latin-ext.woff2","preact/dist/assets/fonts/barlow/barlow-condensed-700-latin.woff2","preact/dist/assets/fonts/barlow/barlow-condensed-700-latin-ext.woff2",
        ],
    }
    return [os.path.join(runtime,*x.split("/")) for x in rel.get(role,())]


def font_override_targets(root):
    return [target for role,_,_ in FONT_ROLE_DEFINITIONS for target in font_role_targets(root,role)]


def apply_font_roles(root,values):
    """Apply independent font selections while preserving untouched roles."""
    saved=dict(values);applied=False
    for role,_,extensions in FONT_ROLE_DEFINITIONS:
        source=str(values.get(role,"") or "")
        valid=bool(source and os.path.isfile(source) and source.lower().endswith(extensions))
        for target in font_role_targets(root,role):
            marker=target+".onepunch_font_override"
            if valid:
                os.makedirs(os.path.dirname(target),exist_ok=True)
                temporary=target+".new";shutil.copy2(source,temporary);os.replace(temporary,target)
                write_text(marker,os.path.abspath(source)+"\n");applied=True
            elif os.path.isfile(marker):
                for item in (target,marker):
                    try:
                        if os.path.isfile(item):os.remove(item)
                    except OSError:pass
        saved[role]=source if valid else ""
    save_font_paths(root,saved)
    return applied


def apply_font_override(root,path):
    """Compatibility wrapper applying one TTF/OTF to legacy/HoN roles."""
    values=saved_font_paths(root)
    for role in ("game","system","hon_regular","hon_bold","hon_condensed"):
        values[role]=path or ""
    return font_role_targets(root,"hon_regular")[0] if apply_font_roles(root,values) and path else ""

def ui_sound(root,event):
    from one_punch_ui_audio import play
    play(root,event)

AVATAR_RE = re.compile(r"(?i)^(alt\d*|classic|pog_skin|community\d*|ultimate\d*|trophy_skin\d*|main_reskin|set_[a-z0-9_]+|naughty|angel|[a-z0-9_]+)$")


# Verified historical Hero_*.Alt* -> display names.  This is only a fallback;
# v1.14 primarily resolves names from the English stringtables in the user's own
# old HoN installation, so it can cover far more avatars without hardcoding them.
KNOWN_AVATAR_NAMES = {
    "hero_slither": {"alt":"MSIvy Slither","alt2":"Infected Slither","alt3":"Rift Slither","alt4":"Sally Slither","alt5":"Scorpio","alt6":"Red Scorpio Slither","alt7":"Deep Poison Slither","alt8":"Cake Snake","classic":"Throwback Slither","pog_skin":"POG Slither"},
    "hero_ebulus": {"alt":"MSIvy Slither","alt2":"Infected Slither","alt3":"Rift Slither","alt4":"Sally Slither","alt5":"Scorpio","alt6":"Red Scorpio Slither","alt7":"Deep Poison Slither","alt8":"Cake Snake","classic":"Throwback Slither","pog_skin":"POG Slither"},
    "hero_moon_queen": {"alt2":"Moon Prince","alt3":"Eclipse","alt4":"Lady Liberty","alt5":"Gisele","alt7":"Nian Guardian Moon Queen","alt8":"Lunari","alt9":"Moon","main_reskin":"Blood Moon Queen","pog_skin":"POG Moon Queen","sexy":"Sexy Moon Queen","classic":"Throwback Moon Queen"},
    "hero_krixi": {"alt2":"Moon Prince","alt3":"Eclipse","alt4":"Lady Liberty","alt5":"Gisele","alt7":"Nian Guardian Moon Queen","alt8":"Lunari","alt9":"Moon","main_reskin":"Blood Moon Queen","pog_skin":"POG Moon Queen","sexy":"Sexy Moon Queen","classic":"Throwback Moon Queen"},
    "hero_legionnaire": {"alt":"Logger Legionnaire","alt2":"Golden Centurion","alt3":"Executioner Legionnaire","alt4":"Quintan","alt5":"Chip Legionnaire","alt6":"The Kurgan","alt7":"Boudica","alt8":"Savior Legionnaire","alt10":"Mercenary Legionnaire","alt11":"Siam Warrior Legionnaire","alt12":"Argentus","alt13":"Royal Guardsman","alt15":"Maritime Legionnaire","alt16":"F.L.E.X Legionnaire","classic":"Throwback Legionnaire","pog_skin":"POG Legionnaire","trophy_skin":"Trophy Legionnaire"},
    "hero_scar": {"alt2":"Hook Madman","alt3":"Chupacabra","alt4":"Raving Madman","alt5":"MadCat Madman","alt8":"The Playmaker","classic":"Throwback Madman","pog_skin":"POG Madman","scary":"Nightmare Madman"},
    "hero_hantumon": {"alt":"Teen Hound","alt2":"Night Hunter","alt3":"Night Hoodlum","alt4":"Cowardly Night Hound","alt5":"Rabid Night Bunny","alt6":"Leo","alt7":"Fright Hound","alt9":"Ferocious Leo","alt10":"Catnip Night Hound","alt11":"Plushie Night Hound","alt12":"Misfit Night Hound","alt13":"Wildcat","classic":"Throwback Night Hound","pog_skin":"POG Night Hound"},
    "hero_accursed": {"alt":"Sub Zero Accursed","alt2":"Diseased Accursed","alt3":"Green Knight","alt4":"Abaddon","alt5":"Lord of Locusts","alt6":"Rahwana","alt7":"Laboratory Accursed","alt8":"General Noroi","classic":"Throwback Accursed","pog_skin":"POG Accursed"},
    "hero_aluna": {"alt":"Stardust Aluna","alt2":"Conquistador Aluna","alt3":"Steampunk Aluna","alt4":"Santa Baby Aluna","alt5":"Spirit Warrior","alt7":"The Emerald Princess","alt8":"Aluna Red Riding Hood"},
    "hero_andromeda": {"alt":"Mandromeda","alt2":"Alien Andromeda","alt3":"Gundromeda","alt4":"Christmas Lights Andromeda","alt5":"Eos","alt6":"Nebula","classic":"Throwback Andromeda","pog_skin":"POG Andromeda","soccer_skin":"Soccer Andromeda"},
    "hero_arachna": {"alt":"Queen Arachna","alt2":"Brass Arachna","alt3":"Rift Arachna","alt4":"Arachnae","alt5":"Black Widow","alt7":"Yokai Arachna","main_reskin":"Arachnabot","pog_skin":"POG Arachna"},
    "hero_armadon": {"alt":"Winston Charmadon","alt2":"Sloth","alt3":"Vagabonadon","alt4":"Robodon","alt5":"Horny Lizardon","alt6":"Scarlord","alt8":"Dreadmace","alt9":"God of Fortune","alt10":"Arma Donna","pog_skin":"POG Armadon","set_ascension":"Ascension Armadon"},
    "hero_artesia": {"alt":"Arcannis","alt3":"Artesia le Fay","alt4":"Corsair","alt5":"Mechartesia","alt6":"Yuanri"},
    "hero_artillery": {"alt":"Heavy Artillery","alt2":"Gunnar the Artillerist","alt3":"Gorilla Warfare Artillery","alt4":"Apollo","alt5":"Rock God Apollo","alt6":"Boggus","alt7":"Srikandi","alt8":"Ravus","alt10":"Huang Zhong","alt11":"Cyber Artillery"},
    "hero_vanya": {"alt":"Dark Zealot","alt_reskin":"Glorious Dark Lady","alt_reskin2":"Glorious Dark Lady 2","alt2":"Hachina","alt3":"Set","alt4":"The Dark Consort","alt5":"Cyber Vanya","alt6":"Vice","alt7":"White Tiger","classic":"Throwback Dark Lady","pog_skin":"POG The Dark Lady","set_ascension":"Ascension Dark Lady"},
    "hero_vindicator": {"alt":"Vigilante Vindicator","alt2":"Judge Vindicator","alt3":"Merlin","alt4":"Vindi the Gray","alt5":"Sexy Librarian","alt6":"Space Wizard Merlin","alt7":"Necronomicon Vindicator","alt9":"Si Ma Yi (EN)","alt10":"Si Ma Yi","alt11":"HoNWorld Vindicator"},
    "hero_voodoo": {"alt":"Voodoo Raptor","alt2":"Voodoo Doctor","alt3":"Hel","alt4":"Ragnarok Hel","alt5":"Siam Warrior Voodoo Jester","alt6":"Hunter Voodoo Jester","alt8":"Painkiller","pog_skin":"POG Voodoo"},
    "hero_witchslayer": {"alt2":"Witch Hunter","alt3":"Hope","alt4":"Hunter Witch Slayer","alt5":"Partisan Slayer","alt6":"Sacrilege","alt7":"Bangkok Slayer","alt8":"Lapis Lazuli Paragon Witch Slayer","alt9":"Songkran Slayer (EN)","alt10":"Songkran Slayer","alt11":"Sin Slayer","pimp":"Pimp Slayer","pog_skin":"POG Witch Slayer","trophy_skin":"Trophy Witch Slayer"},
    "hero_wolfman": {"alt":"Horseman War","alt2":"Den Mother","alt3":"Shock Troop War"},
}

def _parse_stringtable(text):
    """Parse K2 .str files permissively (tab/space/= separated, quoted or plain)."""
    out={}
    for raw in text.splitlines():
        line=raw.strip().lstrip('\ufeff')
        if not line or line.startswith(('#','//',';')): continue
        m=re.match(r'^([^\s=]+)\s*(?:=|\t|\s)\s*"?(.+?)"?\s*$',line)
        if not m: continue
        k=m.group(1).strip().lower(); v=m.group(2).strip()
        if len(v)>=2 and v[0]=='"' and v[-1]=='"': v=v[1:-1]
        v=v.replace(r'\\n',' ').replace(r'\n',' ').strip()
        if k and v: out[k]=v
    return out

def _legacy_name_source(root,member,z,lmembers,tmp):
    """Read name metadata from extracted assets, then an indexed archive."""
    path=os.path.join(legacy_assets_root(root),*member.split('/'))
    if os.path.isfile(path):
        try:return read_text(path)
        except OSError:pass
    want=member.lower()
    for arc,paths in lmembers.items():
        for mem in paths:
            if mem.replace('\\','/').lower().strip('/')!=want:continue
            ep=extract_member(z,arc,mem,tmp)
            if ep:
                try:return read_text(ep)
                except OSError:pass
    return ''


def _legacy_localization(root,z,larcs,lmembers,tmp,force=False):
    cache=os.path.join(cache_dir(root),'legacy_localization_en.json')
    metadata=cache+'.sources.json'
    wanted=('stringtables/interface_en.str','stringtables/entities_en.str',
            'content/store_avatars.package','content/store_avatars_sea.package')
    def stamp(path):
        try:
            s=os.stat(path);return [os.path.abspath(path),s.st_size,s.st_mtime_ns]
        except OSError:return [os.path.abspath(path),None,None]
    signature={'version':2,'files':[stamp(os.path.join(legacy_assets_root(root),*p.split('/'))) for p in wanted],
               'archives':[stamp(p) for p in lmembers]}
    if not force and os.path.isfile(cache) and os.path.isfile(metadata):
        try:
            with open(metadata,'r',encoding='utf-8') as f:cached_signature=json.load(f)
            if cached_signature==signature:
                with open(cache,'r',encoding='utf-8') as f:return json.load(f)
        except Exception:pass
    loc={}
    for want in wanted[:2]:
        loc.update(_parse_stringtable(_legacy_name_source(root,want,z,lmembers,tmp)))
    # Store packages join Hero_Foo.AltN identities to numbered localized products.
    # Keep the primary package's mapping when the regional package repeats it.
    for want in wanted[2:]:
        text=_legacy_name_source(root,want,z,lmembers,tmp)
        text=re.sub(r'<!--.*?-->','',text,flags=re.S)
        for tag in re.finditer(r'<instance\b[^>]*>',text,re.I|re.S):
            attrs=_parse_attrs(tag.group(0))
            product=attrs.get('product','').lower()
            value=loc.get('mstore_product'+attrs.get('id','')+'_name','')
            if product and value:loc.setdefault(product+'_name',value)
    try:
        with open(cache,'w',encoding='utf-8') as f:json.dump(loc,f,ensure_ascii=False)
        with open(metadata,'w',encoding='utf-8') as f:json.dump(signature,f)
    except Exception:pass
    return loc

def _resolve_localized(raw,loc):
    if not raw:return ''
    val=raw.strip()
    # K2 values are often keys such as Hero_Foo_alt7_name. Follow a few aliases.
    seen=set()
    for _ in range(4):
        k=val.strip().strip('$').lower()
        if k in seen:break
        seen.add(k)
        nv=loc.get(k)
        if not nv:break
        val=nv.strip()
    return val

def _name_from_legacy_localization(loc,h,av):
    """Find an avatar display name from old English stringtables using hero+avatar identity."""
    avl=av.lower(); lf=(h.get('legacy_folder') or h['folder']).lower()
    intern=(h.get('internal_name') or '').lower()
    stems={lf, lf.replace('_',''), intern, intern.removeprefix('hero_')}
    stems={x for x in stems if x}
    for identity in (intern,'hero_'+lf,'hero_'+lf.replace('_','')):
        value=loc.get(identity+'.'+avl+'_name')
        if value:return _resolve_localized(value,loc)
    best=[]
    for k,v in loc.items():
        kl=k.lower().strip('$')
        if not re.search(r'(?<![a-z0-9])'+re.escape(avl)+r'(?![a-z0-9])', kl): continue
        if not any(st in kl for st in stems): continue
        val=_resolve_localized(v,loc).strip()
        if not val or val.lower()==avl or val.lower().startswith(('hero_','modifier_','altavatar_','store_')):continue
        # Prefer explicit name/display/store-label keys over descriptions/tooltips.
        score=0
        # Exact Hero_Foo.AltN identity is much stronger than a loose substring.
        if any(kl.endswith(x) or (x+'_' in kl) or (x+'.' in kl) for x in ('.'+avl, '_'+avl)): score+=30
        if any(x in kl for x in ('name','display','label','proper')):score+=20
        if 'description' in kl or 'desc' in kl or 'tooltip' in kl:score-=20
        if len(val)>80:score-=10
        best.append((score,val))
    return max(best,key=lambda x:x[0])[1] if best else ''

def build_legacy_name_cache(root,heroes,z,larcs,lmembers,tmp,force=False):
    """Resolve every physical legacy avatar in one pass per hero, not one 7z call per avatar."""
    fn=os.path.join(cache_dir(root),'avatar_names.json')
    if os.path.isfile(fn) and not force:
        try:
            with open(fn,'r',encoding='utf-8') as f:names=json.load(f)
        except Exception:names={}
    else:names={}
    loc=_legacy_localization(root,z,larcs,lmembers,tmp,force=force)
    for h in heroes:
        legacy=list(h.get('legacy',[]))
        if not legacy:continue
        tags={}
        lf=(h.get('legacy_folder') or h['folder']).lower()
        text=_legacy_name_source(root,f'heroes/{lf}/hero.entity',z,lmembers,tmp)
        for mt in re.finditer(r'<[^>]+>',re.sub(r'<!--.*?-->','',text,flags=re.S),re.S):
            a=_parse_attrs(mt.group(0)); mk=(a.get('key') or a.get('modifier') or a.get('skin') or '').lower()
            if mk:tags[mk]=a
        hero_internal=(h.get('internal_name') or '').lower()
        # inventory versions that do not retain internal_name can still use legacy folder aliases
        candidates=[hero_internal, 'hero_'+(h.get('legacy_folder') or h['folder']).replace('_','').lower(), 'hero_'+(h.get('legacy_folder') or h['folder']).lower()]
        known={}
        for c in candidates:
            if c in KNOWN_AVATAR_NAMES: known.update(KNOWN_AVATAR_NAMES[c])
        for av in legacy:
            key=f"{h.get('legacy_folder') or h['folder']}::{av}".lower()
            avl=av.lower()
            a=tags.get(avl,{})
            if not a:
                # Normal old-HoN form: key="Hero_Foo.Alt7".  Earlier builds
                # indexed that full key but then incorrectly looked it up as only "alt7".
                # Match the exact final modifier component so Alt1 never matches Alt10.
                for tk,ta in tags.items():
                    if tk == avl or tk.endswith('.'+avl):
                        a=ta; break
            raws=[a.get(x,'') for x in ('displayname','display_name','modifiername','label','propername','name')]
            val=''
            for raw in raws:
                r=_resolve_localized(raw,loc)
                if r and not r.lower().startswith(('hero_','modifier_','altavatar_','store_')) and r.lower()!=av.lower():
                    val=r;break
            if not val: val=_name_from_legacy_localization(loc,h,av)
            if not val: val=known.get(av.lower(),'')
            if val:names[key]=val
            elif key not in names:names[key]=pretty_avatar(av)
    try:
        with open(fn,'w',encoding='utf-8') as f:json.dump(names,f,ensure_ascii=False,indent=2)
    except Exception:pass
    return names

AVATAR_ATTRS = [
    "icon","icon2","portrait","animatedportrait","model","storemodel","skin",
    "passiveeffect","spawneffect","respawneffect","deathsound","respawnsound",
    "selectedsound","selectedflavorsound","confirmmovesound","confirmattacksound",
    "nomanasound","cooldownsound","tauntedsound","tauntkillsound","announcersound",
    "attackstarteffect","attackactioneffect","attackimpacteffect","attackprojectile",
    "attackanim","attacknumanims",
    "preglobalscale","modelscale","effectscale","portraitcampos",
    "previewmodel","previewpos","previewangles","previewscale",
    "storepos","storeangles","storescale","infoheight"
]

def is_avatar_cosmetic_attr(attr):
    """Historical AltAvatar attributes that are safe presentation/cosmetic semantics."""
    a = (attr or "").lower()

    if a in AVATAR_ATTRS:
        return True

    # Additional presentation effects omitted by the old fixed whitelist.
    if a in (
        "previewpassiveeffect",
        "storepassiveeffect",
    ):
        return True

    # K2 item/tool-driven cosmetic attachments.
    # Examples: weapons, helmets, boots, backpacks, SOTM effects, etc.
    if re.fullmatch(r"tooleffect(?:keyname|path|group)\d*", a):
        return True

    return False



def cache_dir(root):
    p=os.path.join(root,"OnePunchMod","Cache")
    os.makedirs(p,exist_ok=True)
    return p

def log_path(root):
    return os.path.join(cache_dir(root),"timing.log")

def diagnostic_log_path(root):
    return os.path.join(root,"OnePunchMod","Logs","OnePunchMod.log")

def diag(root,msg=""):
    try:
        with open(diagnostic_log_path(root),"a",encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S")+" | "+str(msg)+"\n")
    except Exception:
        pass

def _voice_inventory(base):
    out=[]
    if os.path.isdir(base):
        for dp,_,fs in os.walk(base):
            for fn in fs:
                if fn.lower().endswith((".ogg",".wav")):
                    out.append(os.path.relpath(os.path.join(dp,fn),base).replace("\\","/"))
    return sorted(out)

def log_event(root,name,start=None,detail=""):
    try:
        now=time.time()
        elapsed="" if start is None else f" elapsed={now-start:.3f}s"
        with open(log_path(root),"a",encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S")+f" | {name}{elapsed} {detail}\n")
    except Exception:
        pass
    return time.time()

def read_text(path):
    with open(path,"r",encoding="utf-8",errors="replace") as f: return f.read()

def write_text(path,text):
    os.makedirs(os.path.dirname(path),exist_ok=True)
    with open(path,"w",encoding="utf-8",newline="\n") as f: f.write(text)

def norm(s): return re.sub(r"[^a-z0-9]","",s.lower())
def pretty_hero(s): return s.replace("_"," ").title()

def pretty_avatar(a):
    if a=="default": return "Default"
    m=re.fullmatch(r"alt(\d*)",a,re.I)
    if m: return "Alt"+(m.group(1) or "")
    return a.replace("_"," ").title()

def avatar_sort(a):
    if a=="default": return (0,0,a)
    m=re.fullmatch(r"alt(\d*)",a,re.I)
    if m: return (1,int(m.group(1) or 1),a)
    return (2,999,a)

def model_avatar_from_text(text):
    m=re.search(r'\bmodel\s*=\s*"([^"]+)"',text,re.I)
    if not m:return "default"
    p=m.group(1).replace("\\","/").strip("/")
    # v1.5 accepts ../alt8/model.mdf as well as alt8/model.mdf
    parts=[x.lower() for x in p.split("/") if x not in ("",".","..")]
    for x in parts[:-1]:
        if AVATAR_RE.fullmatch(x): return x
    return "default"

def find_7za(root):
    # One Punch Mod: prefer the helper bundled/placed with the HoN install.
    # Damian's development layout is D:\HoN\tools\7za.exe.
    candidates = [
        os.path.join(root, "tools", "7za.exe"),
        os.path.join(root, "tools", "7z.exe"),
        os.path.join(root, "7za.exe"),
        os.path.join(root, "7z.exe"),
        os.path.join(root, "bin", "7za.exe"),
        os.path.join(root, "bin", "7z.exe"),
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
        r"C:\Program Files\Newerth Forge\resources\app.asar.unpacked\7za.exe",
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    for exe in ("7za.exe", "7z.exe"):
        p = shutil.which(exe)
        if p:
            return p
    return None

def find_archive(root):
    for p in [os.path.join(root,"heroes of newerth","resources0.jz"),
              os.path.join(root,"resources0.jz")]:
        if os.path.isfile(p):return p
    return None

def list_archive(z,arc):
    cp=_run_hidden([z,"l","-slt",arc],capture_output=True,text=True,errors="replace",timeout=180)
    if cp.returncode:raise RuntimeError(cp.stderr or "Could not list archive")
    return [x[7:].strip().replace("\\","/") for x in cp.stdout.splitlines() if x.startswith("Path = ")]

def archive_index(paths):
    d={}; rx=re.compile(r"(?i)(?:^|/)heroes/([^/]+)/")
    for p in paths:
        q=p.replace("\\","/");m=rx.search("/"+q)
        if not m:continue
        folder=m.group(1);key=folder.lower()
        r=d.setdefault(key,{"folder":folder,"paths":[],"alts":set()});r["paths"].append(p)
    for r in d.values():
        folder=r["folder"].lower();prefix="heroes/"+folder+"/"
        for p in r["paths"]:
            low=p.lower().replace("\\","/")
            if not low.endswith("/hero.entity"):continue
            pos=low.find(prefix)
            if pos<0:continue
            rel=low[pos+len(prefix):];parts=rel.split("/")
            if len(parts)==2 and parts[1]=="hero.entity" and parts[0]!="base":
                r["alts"].add(parts[0])
    return d

def scan_kongor(root):
    base=os.path.join(root,"KONGOR","heroes");d={}
    if not os.path.isdir(base):return d
    for folder in os.listdir(base):
        hd=os.path.join(base,folder)
        if not os.path.isdir(hd):continue
        d[folder.lower()]={"folder":folder,"hero_dir":hd,"base_dir":os.path.join(hd,"base")}
    return d

def scan_active_overrides(root):
    out={}
    # Read our dedicated layer first; fall back to ~mods only for legacy versions.
    for layer in ("OnePunchMod/Runtime",):
        hr=os.path.join(root,layer,"heroes")
        if not os.path.isdir(hr):continue
        for hero in os.listdir(hr):
            p=os.path.join(hr,hero,"base","hero.entity")
            if not os.path.isfile(p):continue
            txt=read_text(p)
            mm=re.search(r'\bskin\s*=\s*"([^"]*)"',txt,re.I)
            current=(mm.group(1).lower() if mm and mm.group(1) else "default")
            key=norm(hero)
            if key not in out or layer=="OnePunchMod/Runtime":
                out[key]={"path":p,"current":current}
    return out

def build_named_icons(root,paths):
    loose={};ir=os.path.join(root,"KONGOR","icons")
    if os.path.isdir(ir):
        for dp,_,fs in os.walk(ir):
            for fn in fs:
                if os.path.splitext(fn)[1].lower() in (".png",".tga",".dds"):
                    loose[norm(os.path.splitext(fn)[0])]=os.path.join(dp,fn)
    packed={}
    for p in paths:
        if os.path.splitext(p)[1].lower() in (".png",".tga",".dds") and "/icons/" in ("/"+p.lower().replace("\\","/")):
            packed[norm(os.path.splitext(os.path.basename(p))[0])]=p
    return loose,packed

def legacy_archives(legacy_root):
    game=os.path.join(legacy_root,"game")
    names=["resources0.s2z","resources1.s2z","resources2.s2z","resources3.s2z",
           "resources4.s2z","resourcesHDSound.s2z","textures.s2z"]
    return [os.path.join(game,n) for n in names if os.path.isfile(os.path.join(game,n))]

def _hero_path_parts(p):
    low=p.lower().replace("\\","/").strip("/")
    m=re.search(r"(?:^|/)heroes/([^/]+)/(.*)$",low)
    return (m.group(1),m.group(2)) if m else (None,None)

def legacy_index(z,legacy_root):
    arcs=legacy_archives(legacy_root)
    if not arcs:return {},[],{},{}
    idx={};members={};hero_folders=set()
    excluded={"base","ability_01","ability_02","ability_03","ability_04","ability_05",
              "effects","sounds","projectile","store","pets","shared","textures","materials",
              "preview","clips"}
    for arc in arcs:
        ps=list_archive(z,arc);members[arc]=ps
        for p in ps:
            hero,rest=_hero_path_parts(p)
            if not hero: continue
            hero_folders.add(hero)
            parts=rest.split("/")
            # Some late HoN avatars don't put model.mdf directly at <avatar>/model.mdf.
            # Treat the first directory as the avatar if any model.mdf exists below it.
            if len(parts)>=2 and parts[-1].lower() in ("model.mdf","high.model","med.model","low.model"):
                av=parts[0].lower()
                if av in excluded or av.startswith("ability_"):continue
                # Late/legacy cosmetics are not always packaged with a model.mdf; some
                # only contain the compiled .model hierarchy.  Accept cosmetic-looking
                # top-level directories while still excluding ability/support trees.
                if not (re.match(r"^alt\d*$",av) or av in ("classic","pog_skin","trophy_skin","scary") or av.endswith("_skin")):
                    continue
                idx.setdefault(hero,{}).setdefault(av,{"archive":arc,"model_member":p})
    return idx,arcs,members,{x:x for x in hero_folders}

def parse_entity_name(text):
    m=re.search(r'\bname\s*=\s*"(Hero_[^"]+)"',text,re.I)
    return m.group(1) if m else None

def _simple_name(v):
    return re.sub(r"[^a-z0-9]","",v.lower())

LEGACY_ALIASES={
    "nighthound":["hantumon"],
    "night_hound":["hantumon"],
    # Reborn uses pollywog_priest, while historical resources and prepared
    # avatar references use pollywogpriest.
    "pollywogpriest":["pollywogpriest"],
    "pollywog_priest":["pollywogpriest"],
    "madman":["scar"],
    "themadman":["scar"],
    "the_madman":["scar"],
    "scar":["scar"],
    "succubus":["succubis"],
    "pebbles":["rocky"],
    # Modern Wretched Hag is Hero_WretchedHag, while the historical entity
    # and asset folder are Hero_BabaYaga / heroes/babayaga.
    "wretchedhag":["babayaga"],
    "wretched_hag":["babayaga"],
    "warbeast":["wolfman"],
    "war_beast":["wolfman"],
    "swift_blade":["swiftblade"],
    "soul_reaper":["soulreaper"],
    "rift_walker":["riftwalker"],
    "plague_rider":["plaguerider","diseasedrider"],
        "plaguerider":["diseasedrider"],
    # Pandamonium's Reborn namespace is pandamonium; legacy avatar packages
    # and generated entity paths use panda.
    "pandamonium":["panda"],
    "amunra":["ra"],
    "amun_ra":["ra"],
    "ra":["ra"],
    "myrmidon":["hydromancer"],
    "keeperoftheforest":["treant"],
    "keeper_of_the_forest":["treant"],
    "kinesis":["kenisis"],
    "fayde":["fade"],
    "swiftblade":["hiro"],
    "riftwalker":["riftmage"],
    "rift_walker":["riftmage"],
    "slither":["ebulus"],
    "moon_queen":["krixi"],
    "moonqueen":["krixi"],
}

def build_legacy_internal_map(z,lmembers):
    """Map old entity name=Hero_X to its physical heroes/<folder> directory."""
    out={}
    stage=tempfile.mkdtemp(prefix="hon_old_hero_map_")
    try:
        for arc,paths in lmembers.items():
            wanted=[]
            for p in paths:
                low=p.lower().replace("\\","/").strip("/")
                m=re.search(r"(?:^|/)heroes/([^/]+)/hero\.entity$",low)
                if m:wanted.append(p)
            for i in range(0,len(wanted),100):
                batch=wanted[i:i+100]
                _run_hidden([z,"x","-y",f"-o{stage}",arc]+batch,
                               capture_output=True,text=True,errors="replace",timeout=240)
                for mem in batch:
                    suffix=mem.lower().replace("\\","/")
                    fp=None
                    candidate=os.path.join(stage,*mem.replace("\\","/").split("/"))
                    if os.path.isfile(candidate):fp=candidate
                    else:
                        for dp,_,fs in os.walk(stage):
                            for fn in fs:
                                q=os.path.join(dp,fn)
                                if q.lower().replace("\\","/").endswith(suffix):
                                    fp=q;break
                            if fp:break
                    if fp:
                        name=parse_entity_name(read_text(fp))
                        mm=re.search(r"(?:^|/)heroes/([^/]+)/hero\.entity$",suffix)
                        if name and mm:out[name.lower()]=mm.group(1).lower()
                # clear staging between batches
                for x in os.listdir(stage):
                    q=os.path.join(stage,x)
                    if os.path.isdir(q):shutil.rmtree(q,ignore_errors=True)
                    else:
                        try:os.remove(q)
                        except OSError:pass
    finally:shutil.rmtree(stage,ignore_errors=True)
    return out

def build_legacy_display_map(root,z,larcs,lmembers,tmp,legacy_internal_map):
    """Resolve visible hero names (Magebane) to old physical folders (javaras).
    Uses the legacy English stringtables and heroes.xml, so renamed internal IDs
    do not require one-off aliases.
    """
    loc=_legacy_localization(root,z,larcs,lmembers,tmp)
    out={}
    # Typical keys are Hero_Javaras_name, Hero_Scar_name, etc.  Accept common
    # title/display variants while requiring that the Hero_* prefix maps to a
    # physical root hero.entity discovered from the old archives.
    for k,v in loc.items():
        kl=k.lower().strip().strip('$')
        m=re.match(r'^(hero_[a-z0-9_]+?)(?:_(?:name|displayname|display_name|title))?$',kl)
        if not m: continue
        internal=m.group(1)
        folder=legacy_internal_map.get(internal)
        if not folder: continue
        val=_resolve_localized(v,loc)
        if val:
            out.setdefault(_simple_name(val),folder)

    # The old hero roster is a more complete rename map than the stringtables.
    # Its displayName is the name shown to players, while path points at the
    # physical historical folder.  Prefer the extracted source when present;
    # it is available in developer builds and avoids scanning old archives.
    heroes_xml=os.path.join(legacy_assets_root(root),"heroes.xml")
    if os.path.isfile(heroes_xml):
        try:
            import xml.etree.ElementTree as ET
            document=ET.parse(heroes_xml).getroot()
            for node in document.iter():
                if node.tag.lower().split('}')[-1] != 'hero':
                    continue
                display=(node.get('displayName') or '').strip()
                path=(node.get('path') or '').replace('\\','/').strip('/')
                m=re.search(r'(?:^|/)heroes/([^/]+)$',path,re.I)
                if not display or not m:
                    continue
                folder=m.group(1).lower()
                if not os.path.isdir(os.path.join(legacy_assets_root(root),'heroes',folder)):
                    continue
                key=_simple_name(display)
                if key:
                    out.setdefault(key,folder)
                    # Historical roster labels sometimes include a leading
                    # article ("The Dark Lady") while the current roster
                    # calls the same hero "Dark Lady".
                    if key.startswith('the') and len(key)>3:
                        out.setdefault(key[3:],folder)
        except (OSError, ET.ParseError):
            pass

    # Also make internal suffixes searchable, but only as a lower-priority aid.
    for internal,folder in legacy_internal_map.items():
        if internal.startswith('hero_'):
            out.setdefault(_simple_name(internal[5:]),folder)
    return out

def legacy_folder_for_hero(hero,z,arc,tmp,legacy_folders,legacy_internal_map=None,legacy_display_map=None):
    folders=list(legacy_folders.keys()) if isinstance(legacy_folders,dict) else list(legacy_folders)
    candidates=[hero["folder"].lower(),hero["key"].lower()]
    try:
        mem=original_entity_member(hero)
        p=extract_member(z,arc,mem,tmp) if mem else None
        if p:
            n=parse_entity_name(read_text(p))
            if n and legacy_internal_map and n.lower() in legacy_internal_map:
                return legacy_internal_map[n.lower()]
            if n and n.lower().startswith("hero_"):
                candidates.insert(0,n[5:].lower())
    except Exception: pass

    # Generic renamed-hero resolver: compare the current visible/folder name to
    # the old English localization (e.g. Magebane -> Hero_Javaras -> heroes/javaras).
    if legacy_display_map:
        for probe in (hero.get("name",""), hero.get("folder",""), hero.get("key","")):
            hit=legacy_display_map.get(_simple_name(probe))
            if hit in legacy_folders:return hit

    for c in list(candidates):
        candidates.extend(LEGACY_ALIASES.get(c,[]))
        candidates.extend(LEGACY_ALIASES.get(_simple_name(c),[]))

    # Exact first.
    for c in candidates:
        if c in legacy_folders:return c

    # Then punctuation/underscore-insensitive match.
    wanted={_simple_name(c) for c in candidates}
    for f in folders:
        if _simple_name(f) in wanted:return f
    return None

def cache_path(root): return os.path.join(root,"OnePunchMod","Cache","hon_avatar_switcher_cache_v135.json")

def archive_signature(paths):
    out={}
    for p in paths:
        if os.path.isfile(p):
            st=os.stat(p);out[p]={"size":st.st_size,"mtime_ns":st.st_mtime_ns}
    return out


def is_real_hero_folder(folder):
    f=_simple_name(folder)
    return f not in {"innateabilities","innateability","innates","abilities","shared","tutorial"}

def augment_legacy_index_from_extracted(legacy_root, li, lfolders):
    """Add avatars declared by extracted historical hero.entity files.

    The <altavatar> declarations are authoritative.  When an extracted old
    tree is missing a hero.entity, the store-avatar product declarations are
    the equivalent identity source, and a direct model.mdf check is required
    before accepting the package.  Do not infer avatars from arbitrary
    directory names: non-avatar directories may also contain model.mdf.
    """
    import xml.etree.ElementTree as ET

    heroes_root = os.path.join(legacy_root or "", "heroes")
    if not os.path.isdir(heroes_root):
        return li, lfolders

    for entry in os.scandir(heroes_root):
        if not entry.is_dir():
            continue

        hero_file = os.path.join(entry.path, "hero.entity")
        if not os.path.isfile(hero_file):
            continue

        folder = entry.name.lower()

        try:
            rootxml = ET.parse(hero_file).getroot()
        except Exception:
            continue

        info = li.setdefault(folder, {})

        # Normalize archive-derived avatar keys such as
        # "Hero_Rocky.Alt2" -> "alt2".
        normalized_info = {}

        for old_key, old_value in info.items():
            normalized_key = old_key.rsplit(".", 1)[-1].lower()

            if normalized_key in {"classic", "default"}:
                continue

            normalized_info.setdefault(normalized_key, old_value)

        info.clear()
        info.update(normalized_info)

        for node in rootxml.iter():
            if node.tag.lower().split("}")[-1] != "altavatar":
                continue

            key = (node.attrib.get("key") or "").strip()
            if not key:
                continue

            av = key.rsplit(".", 1)[-1].lower()


            # Classic/base definitions are the Default avatar, not a
            # separate legacy package.
            model = (node.attrib.get("model") or "").replace("\\", "/").strip()
            if av in {"classic", "default"} and "/" not in model:
                continue

            info.setdefault(av, dict(node.attrib))

        if info:
            lfolders[folder] = folder

    # Some historical hero.entity files were not included in the extracted
    # source tree, even though their avatar packages and store declarations
    # are present.  Recover those identities from heroes.xml plus the store
    # package product keys, then require the avatar's own model.mdf.  This is
    # deliberately declaration-driven and does not turn arbitrary folders
    # into selectable avatars.
    heroes_xml=os.path.join(legacy_root or "","heroes.xml")
    if os.path.isfile(heroes_xml):
        try:
            document=ET.parse(heroes_xml).getroot()
            internal_to_folder={}
            for node in document.iter():
                if node.tag.lower().split('}')[-1] != 'hero':
                    continue
                internal=(node.get('name') or '').strip().lower()
                path=(node.get('path') or '').replace('\\','/').strip('/')
                m=re.search(r'(?:^|/)heroes/([^/]+)$',path,re.I)
                if internal.startswith('hero_') and m:
                    folder=m.group(1).lower()
                    if os.path.isdir(os.path.join(heroes_root,folder)):
                        internal_to_folder[internal]=folder

            package_files=[]
            content_root=os.path.join(legacy_root or "","content")
            if os.path.isdir(content_root):
                package_files=[os.path.join(content_root,n) for n in os.listdir(content_root)
                               if n.lower() in {'store_avatars.package','store_avatars_sea.package'}]
            for package in package_files:
                try:
                    package_text=read_text(package)
                except OSError:
                    continue
                for match in re.finditer(r'\bproduct\s*=\s*"(Hero_[A-Za-z0-9_]+)\.([A-Za-z0-9_]+)"',package_text,re.I):
                    internal=match.group(1).lower()
                    av=match.group(2).lower()
                    folder=internal_to_folder.get(internal)
                    if not folder or av in {'classic','default'}:
                        continue
                    model=os.path.join(heroes_root,folder,av,'model.mdf')
                    if not os.path.isfile(model):
                        continue
                    info=li.setdefault(folder,{})
                    info.setdefault(av,{
                        'key': f'{match.group(1)}.{match.group(2)}',
                        'model': f'/heroes/{folder}/{av}/model.mdf',
                    })
                    lfolders[folder]=folder
        except (OSError,ET.ParseError):
            pass

    return li, lfolders

def build_inventory(root,legacy_root,force=False):
    z=find_7za(root);arc=find_archive(root)
    if not arc:
        raise RuntimeError("Reborn resources0.jz was not found under the selected HoN directory.")
    if not z:
        raise RuntimeError("7-Zip command-line tool was not found. Put 7za.exe in <HoN>\\tools\\ (for example D:\\HoN\\tools\\7za.exe).")
    larcs=legacy_archives(legacy_root) if legacy_root and os.path.isdir(legacy_root) else []
    sig=archive_signature([arc]+larcs)
    cp=cache_path(root)
    if not force and os.path.isfile(cp):
        try:
            c=json.load(open(cp,"r",encoding="utf-8"))
            if c.get("signature")==sig and c.get("reborn_root")==root and c.get("legacy_root")==legacy_root:
                paths=c["reborn_paths"];ai=archive_index(paths);ki=scan_kongor(root);oi=scan_active_overrides(root)
                loose_named,packed_named=build_named_icons(root,paths)
                lmembers=c.get("legacy_members",{})
                li=c.get("legacy_index",{})
                lfolders=c.get("legacy_folders",{})
                li,lfolders=augment_legacy_index_from_extracted(legacy_root,li,lfolders)
                resolved=c.get("resolved_legacy_map",{})
                legacy_internal_map=c.get("legacy_internal_map",{})
                legacy_display_map=c.get("legacy_display_map",{})
                heroes=[]
                tmp=tempfile.mkdtemp(prefix="hon_map_")
                try:
                    # Older caches predate the heroes.xml fallback.  Rebuild
                    # that small display map on cache hits so inventory fixes
                    # take effect without forcing a full archive re-index.
                    repaired_display_map=build_legacy_display_map(root,z,larcs,lmembers,tmp,legacy_internal_map)
                    repaired_display_map.update(legacy_display_map)
                    legacy_display_map=repaired_display_map
                    for key in sorted(ai):
                        a=ai[key]
                        if not is_real_hero_folder(a["folder"]):continue
                        o=oi.get(key);current=o["current"] if o else "default"
                        stub={"key":key,"folder":a["folder"],"name":pretty_hero(a["folder"]),"archive":a}
                        aliases=LEGACY_ALIASES.get(a["folder"].lower(),())
                        prepared_alias=next((x for x in aliases if os.path.isdir(os.path.join(prepared_root(root),"heroes",x))),None)
                        lf=prepared_alias or resolved.get(a["folder"].lower())
                        if lf is None:
                            lf=legacy_folder_for_hero(stub,z,arc,tmp,lfolders,legacy_internal_map,legacy_display_map)
                            resolved[a["folder"].lower()]=lf
                        reborn={"default"}|set(a["alts"]);legacy=set(li.get(lf or "",{}))-reborn
                        heroes.append({"key":key,"folder":a["folder"],"legacy_folder":lf,"name":pretty_hero(a["folder"]),
                          "archive":a,"kongor":ki.get(key),"override":o,"current":current,
                          "avatars":sorted(reborn|legacy,key=avatar_sort),"reborn":reborn,"legacy":legacy,
                          "legacy_info":li.get(lf or "",{})})
                finally: shutil.rmtree(tmp,ignore_errors=True)
                _filter_legacy_inventory(root,heroes)
                # Persist repaired mappings and extracted declarations so the
                # next launch can use the normal cache path immediately.
                try:
                    c.update({"legacy_index":li,"legacy_folders":lfolders,
                              "resolved_legacy_map":resolved,
                              "legacy_display_map":legacy_display_map})
                    with open(cp,"w",encoding="utf-8") as f:
                        json.dump(c,f,ensure_ascii=False)
                except Exception: pass
                return heroes,z,arc,paths,loose_named,packed_named,larcs,lmembers,True
        except Exception: pass

    paths=list_archive(z,arc);ai=archive_index(paths);ki=scan_kongor(root);oi=scan_active_overrides(root)
    loose_named,packed_named=build_named_icons(root,paths)
    li,larcs,lmembers,lfolders=legacy_index(z,legacy_root) if larcs else ({},[],{}, {})
    li,lfolders=augment_legacy_index_from_extracted(legacy_root,li,lfolders)
    legacy_internal_map=build_legacy_internal_map(z,lmembers) if lmembers else {}
    tmp=tempfile.mkdtemp(prefix="hon_map_")
    legacy_display_map=build_legacy_display_map(root,z,larcs,lmembers,tmp,legacy_internal_map) if lmembers else {}
    heroes=[];resolved_legacy_map={}
    try:
        for key in sorted(ai):
            a=ai[key]
            if not is_real_hero_folder(a["folder"]):continue
            o=oi.get(key);current=o["current"] if o else "default"
            stub={"key":key,"folder":a["folder"],"name":pretty_hero(a["folder"]),"archive":a}
            aliases=LEGACY_ALIASES.get(a["folder"].lower(),())
            prepared_alias=next((x for x in aliases if os.path.isdir(os.path.join(prepared_root(root),"heroes",x))),None)
            lf=prepared_alias or legacy_folder_for_hero(stub,z,arc,tmp,lfolders,legacy_internal_map,legacy_display_map)
            resolved_legacy_map[a["folder"].lower()]=lf
            reborn={"default"}|set(a["alts"]);legacy=set(li.get(lf or "",{}))-reborn
            heroes.append({"key":key,"folder":a["folder"],"legacy_folder":lf,"name":pretty_hero(a["folder"]),
              "archive":a,"kongor":ki.get(key),"override":o,"current":current,
              "avatars":sorted(reborn|legacy,key=avatar_sort),"reborn":reborn,"legacy":legacy,
              "legacy_info":li.get(lf or "",{})})
    finally: shutil.rmtree(tmp,ignore_errors=True)

    _filter_legacy_inventory(root,heroes)

    try:
        json.dump({"version":1200,"reborn_root":root,"legacy_root":legacy_root,"signature":sig,
                   "reborn_paths":paths,"legacy_members":lmembers,"legacy_index":li,
                    "legacy_folders":lfolders,"resolved_legacy_map":resolved_legacy_map,
                   "legacy_internal_map":legacy_internal_map,"legacy_display_map":legacy_display_map},open(cp,"w",encoding="utf-8"),ensure_ascii=False)
    except Exception: pass
    return heroes,z,arc,paths,loose_named,packed_named,larcs,lmembers,False

def extract_member(z,arc,member,dest):
    # Reborn .jz is a ZIP archive that can contain Zstandard method 93
    # ("zstd-wz" in old 7-Zip). Python 3.14 supports it natively.
    if arc.lower().endswith(".jz"):
        try:
            import zipfile

            wanted = member.replace("\\", "/")
            with zipfile.ZipFile(arc, "r") as za:
                try:
                    info = za.getinfo(wanted)
                except KeyError:
                    # Archive names may use the opposite slash convention.
                    info = next(
                        (
                            i for i in za.infolist()
                            if i.filename.replace("\\", "/").lower() == wanted.lower()
                        ),
                        None
                    )

                if info is None:
                    return None

                data = za.read(info)

            p = os.path.join(dest, *wanted.split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)

            with open(p, "wb") as f:
                f.write(data)

            return p

        except Exception:
            # Keep the existing extractor as a fallback for unusual entries.
            pass

    _run_hidden(
        [z, "x", "-y", f"-o{dest}", arc, member],
        capture_output=True,
        text=True,
        errors="replace",
        timeout=120
    )

    p = os.path.join(dest, *member.replace("\\", "/").split("/"))
    if os.path.isfile(p):
        return p

    suffix = member.lower().replace("\\", "/")
    for dp, _, fs in os.walk(dest):
        for fn in fs:
            fp = os.path.join(dp, fn)
            if fp.lower().replace("\\", "/").endswith(suffix):
                return fp

    return None



def direct_archive_icon(hero,av):
    a=hero.get("archive")
    if not a:return None
    folder=hero["folder"].lower();c=[]
    for p in a["paths"]:
        low=p.lower().replace("\\","/")
        if os.path.basename(low) not in ("icon.png","icon.tga","icon.dds"):continue
        marker="/heroes/"+folder+"/";full="/"+low;pos=full.find(marker)
        if pos<0:continue
        parts=[x for x in full[pos+len(marker):].split("/") if x]
        ext=os.path.splitext(p)[1].lower();es={".png":0,".tga":1,".dds":2}.get(ext,9)
        if av=="default":
            if len(parts)==1:c.append((es,p))
            elif len(parts)==2 and parts[0]=="base":c.append((5+es,p))
        elif av in parts[:-1]:
            score=0 if len(parts)>=2 and parts[0]==av else 10
            if any(x.startswith("ability_") for x in parts):score+=50
            c.append((score+es,p))
    return min(c,key=lambda x:x[0])[1] if c else None

def _current_default_icon_member(hero):
    """Prefer the current Reborn base portrait, never a legacy avatar icon."""
    folder=hero["folder"].lower()
    candidates=[]
    for member in hero.get("archive",{}).get("paths",[]):
        low=member.lower().replace("\\","/").strip("/")
        if low.endswith(f"heroes/{folder}/base/icon.dds"):
            candidates.append((0,member))
        elif low.endswith(f"heroes/{folder}/icon.dds"):
            candidates.append((1,member))
        elif low.endswith(f"heroes/{folder}/base/icon.tga"):
            candidates.append((2,member))
        elif low.endswith(f"heroes/{folder}/icon.tga"):
            candidates.append((3,member))
        elif low.endswith(f"heroes/{folder}/base/icon.png"):
            candidates.append((4,member))
        elif low.endswith(f"heroes/{folder}/icon.png"):
            candidates.append((5,member))
    return min(candidates,key=lambda item:item[0])[1] if candidates else None

def _prepared_default_icon(root,hero):
    """Return the generated current-default portrait before archive fallback."""
    base=os.path.join(prepared_root(root),"heroes",hero["folder"].lower())
    for ext in ("dds","tga","png"):
        path=os.path.join(base,f"icon.{ext}")
        if os.path.isfile(path):
            return path
    return None

def _prepared_avatar_icon(root,hero,av):
    """Return a prepared portrait for a non-default avatar when available."""
    base=os.path.join(prepared_root(root),"heroes",hero["folder"].lower())
    attrs=(hero.get("legacy_info") or {}).get(av,{})
    folders=[]

    def add_folder(value):
        value=str(value or "").replace("\\","/").strip("/")
        if not value or value.startswith("../") or "/../" in f"/{value}/":
            return
        folder=os.path.dirname(value) if os.path.splitext(value)[1] else value
        folder=folder.strip("/")
        if folder and folder not in folders:
            folders.append(folder)

    # The entity metadata is authoritative when an avatar's physical package
    # differs from its display name (for example trophy or reskin folders).
    add_folder(av)
    add_folder(attrs.get("icon2"))
    add_folder(attrs.get("portrait"))
    model_ref=str(attrs.get("model") or "").replace("\\","/").strip("/")
    add_folder(model_ref)

    for folder in folders:
        for ext in ("dds","tga","png"):
            path=os.path.join(base,*folder.split("/"),f"icon.{ext}")
            if os.path.isfile(path):
                return path
    return None

def invalidate_portrait_thumbnails(root,hero=None,av=None):
    """Remove UI thumbnails for a source that has just been regenerated."""
    thumbs=os.path.join(cache_dir(root),"thumbs")
    if not os.path.isdir(thumbs):return 0
    prefix=None
    if hero is not None:
        prefix=f"{norm(hero['folder'])}_{norm(av or 'default')}_".lower()
    removed=0
    try: names=os.listdir(thumbs)
    except OSError:return 0
    for name in names:
        low=name.lower()
        if not low.endswith(".png"):continue
        if prefix is not None and not low.startswith(prefix):continue
        try:
            os.remove(os.path.join(thumbs,name));removed+=1
        except OSError:pass
    return removed

def regenerate_prepared_default_icons(root,heroes,z,arc,tmp):
    """Rebuild PreparedAssets default ``heroes/<hero>/icon.dds`` from Reborn.

    Only the root default portrait is replaced.  Avatar subdirectories and all
    other prepared files remain untouched.
    """
    updated=0;skipped=[]
    for hero in heroes:
        member=_current_default_icon_member(hero)
        if not member:
            skipped.append(hero["folder"]);continue
        stage=os.path.join(tmp,"default_icons",hero["folder"].lower())
        os.makedirs(stage,exist_ok=True)
        source=extract_member(z,arc,member,stage)
        if not source or not os.path.isfile(source):
            skipped.append(hero["folder"]);continue
        target=os.path.join(prepared_root(root),"heroes",hero["folder"].lower(),"icon.dds")
        os.makedirs(os.path.dirname(target),exist_ok=True)
        extension=os.path.splitext(source)[1].lower()
        if extension==".dds":
            shutil.copy2(source,target);invalidate_portrait_thumbnails(root,hero,"default");updated+=1;continue
        if Image is None:
            skipped.append(hero["folder"]);continue
        try:
            with Image.open(source) as image:
                image.convert("RGBA").save(target,format="DDS")
            invalidate_portrait_thumbnails(root,hero,"default")
            updated+=1
        except Exception:
            skipped.append(hero["folder"])
    diag(root,f"DEFAULT_ICONS_REGENERATED updated={updated} skipped={len(skipped)}")
    if skipped:diag(root,f"DEFAULT_ICONS_SKIPPED heroes={','.join(skipped)}")
    return {"updated":updated,"skipped":skipped}

def loose_icon(hero,av):
    k=hero.get("kongor")
    if not k:return None
    hd=k["hero_dir"];bd=k["base_dir"];cs=[]
    for ext in ("png","tga","dds"):
        if av=="default":cs += [os.path.join(hd,f"icon.{ext}"),os.path.join(bd,f"icon.{ext}")]
        else:cs += [os.path.join(bd,av,f"icon.{ext}"),os.path.join(hd,av,f"icon.{ext}")]
    return next((p for p in cs if os.path.isfile(p)),None)

def legacy_fs_icon(root,hero,av):
    """Find a legacy avatar icon in the extracted LegacyAssets tree."""
    lf=(hero.get("legacy_folder") or hero["folder"]).lower()
    avl=av.lower()
    base=legacy_assets_root(root)

    # Highest-quality texture namespace first.
    for ns in ("00000000","00000003","00000005"):
        for ext in ("png","tga","dds"):
            p=os.path.join(base,ns,"heroes",lf,avl,f"icon.{ext}")
            if os.path.isfile(p):
                return p

    # Some extracted clients may contain an un-namespaced icon.
    for ext in ("png","tga","dds"):
        p=os.path.join(base,"heroes",lf,avl,f"icon.{ext}")
        if os.path.isfile(p):
            return p

    return None

def legacy_icon_member(hero,av,lmembers):
    # Icons/textures may live in another old archive, so search all layers.
    f=(hero.get("legacy_folder") or hero["folder"]).lower()
    suffixes=[f"heroes/{f}/{av}/icon.png",f"heroes/{f}/{av}/icon.tga",f"heroes/{f}/{av}/icon.dds"]
    best=None
    for arc,paths in lmembers.items():
        for p in paths:
            low=p.lower().replace("\\","/")
            for rank,s in enumerate(suffixes):
                if low.endswith(s):best=(rank,arc,p)
    return (best[1],best[2]) if best else (None,None)

def to_png(src,cache):
    if not src or not os.path.isfile(src):return None
    ext=os.path.splitext(src)[1].lower()
    if ext==".png":return src
    if Image is None:return None
    dest=os.path.join(cache,norm(src)+".png")
    if os.path.isfile(dest):return dest
    try:
        with Image.open(src) as im:
            im=im.convert("RGBA")
            if ext==".dds":im=ImageOps.flip(im)
            im.save(dest,"PNG")
        return dest
    except Exception:return None

def photo(path,size):
    if not path:return None
    if Image is not None:
        try:
            from PIL import ImageTk
            with Image.open(path) as source:
                fitted=ImageOps.fit(source.convert('RGBA'),(size,size),method=Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(fitted)
        except Exception:pass
    try:
        im=tk.PhotoImage(file=path);fac=max(1,(max(im.width(),im.height())+size-1)//size)
        return im.subsample(fac,fac) if fac>1 else im
    except Exception:return None

def original_entity_member(hero):
    f=hero["folder"].lower()
    for p in hero["archive"]["paths"]:
        low=p.lower().replace("\\","/")
        if low.endswith(f"heroes/{f}/base/hero.entity"):return p
    for p in hero["archive"]["paths"]:
        if p.lower().replace("\\","/").endswith(f"heroes/{f}/hero.entity"):return p
    return None

def source_entity(hero,z,arc,tmp):
    """Return a known-good CURRENT Reborn entity document.

    Prefer previously validated Reborn cache.  The .jz extractor can return compiled/
    non-text entity payloads on some Reborn builds, so never publish those as overrides.
    """
    root=os.path.dirname(os.path.dirname(arc)) if os.path.basename(os.path.dirname(arc)).lower()=="heroes of newerth" else os.path.dirname(arc)
    f=hero["folder"].lower()
    candidates=[
        os.path.join(cache_dir(root),"entities",f,"hero.entity"),
        os.path.join(cache_dir(root),"pristine_entities",f,"hero.entity"),
        os.path.join(root,"avatar_switcher_cache","entities",f,"hero.entity"),
    ]
    def valid(path):
        if not path or not os.path.isfile(path):return False
        try:
            t=read_text(path)
            return bool(t.strip() and re.search(r'<\s*[A-Za-z_][A-Za-z0-9_.:-]*\b',t))
        except Exception:return False
    for c in candidates:
        if valid(c):
            diag(root,f"PRISTINE_ENTITY hero={hero['folder']} source=cache path={c}")
            return c
    mem=original_entity_member(hero)
    if not mem:raise RuntimeError("Original Reborn base hero.entity not found.")
    stage=os.path.join(tmp,"pristine_entity",f,str(time.time_ns()));os.makedirs(stage,exist_ok=True)
    extracted=extract_member(z,arc,mem,stage)
    if valid(extracted):
        ec=os.path.join(cache_dir(root),"entities",f,"hero.entity");os.makedirs(os.path.dirname(ec),exist_ok=True);shutil.copy2(extracted,ec)
        diag(root,f"PRISTINE_ENTITY hero={hero['folder']} source=archive member={mem} bytes={os.path.getsize(extracted)}")
        return ec
    size=os.path.getsize(extracted) if extracted and os.path.isfile(extracted) else -1
    raise RuntimeError(f"Reborn {hero['folder']} hero.entity could not be decoded as text (member={mem}, bytes={size}). Refreshing/replacing it would be unsafe.")

def one_punch_root(root):
    return os.path.join(root,"OnePunchMod")

def switcher_root(root):
    # Runtime is the ONLY One Punch layer mounted by Juvio. LegacyAssets is source-only.
    return os.path.join(one_punch_root(root),"Runtime")

def legacy_assets_root(root):
    return os.path.join(one_punch_root(root),"LegacyAssets")

def override_path(root,hero):return os.path.join(switcher_root(root),"heroes",hero["folder"],"base","hero.entity")
def legacy_dest(root,hero,av):
    # Prepared/runtime avatar assets live beside `base`, not below it.
    # The generated base/hero.entity may reference them with an absolute
    # `/heroes/<folder>/<avatar>/...` path. Keeping this helper aligned with
    # that layout also makes existence checks and voice previews inspect the
    # files that the game actually loads.
    return os.path.join(switcher_root(root),"heroes",hero["folder"],av)

def legacy_mirror_dest(root,hero,av):
    lf=(hero.get("legacy_folder") or hero["folder"])
    return os.path.join(switcher_root(root),"heroes",lf,av)

def _legacy_runtime_ref(hero,av,rel):
    """Return the mounted absolute path for a historical avatar asset."""
    lf=(hero.get("legacy_folder") or hero["folder"]).lower()
    return f"/heroes/{lf}/{av.lower()}/{str(rel).replace('\\\\','/').lstrip('./')}"

def _copy_tree_contents(src,dst):
    if not os.path.isdir(src): return 0
    count=0
    for dp,dirs,files in os.walk(src):
        rel=os.path.relpath(dp,src)
        out=dst if rel=="." else os.path.join(dst,rel)
        os.makedirs(out,exist_ok=True)
        for fn in files:
            shutil.copy2(os.path.join(dp,fn),os.path.join(out,fn));count+=1
    return count

SAFE_VISUAL_EXTS={".model",".mdf",".clip",".material",".effect",".tga",".dds",".png",".ogg",".wav"}

def _extract_legacy_support_tree(root,hero,z,larcs,lmembers):
    """
    Mirror non-gameplay legacy hero assets so avatar MDF/material/clip references that
    leave the avatar folder can still resolve. Entity files are deliberately excluded.
    """
    lf=(hero.get("legacy_folder") or hero["folder"]).lower()
    mirrorhero=os.path.join(switcher_root(root),"heroes",lf)
    stage=tempfile.mkdtemp(prefix="hon_support_v19_")
    try:
        for arc in larcs:
            wanted=[]
            marker=f"heroes/{lf}/"
            for p in lmembers.get(arc,[]):
                low=p.lower().replace("\\","/").strip("/")
                if marker not in low: continue
                ext=os.path.splitext(low)[1]
                if ext not in SAFE_VISUAL_EXTS: continue
                # Avatar itself is handled separately; this imports shared/base visual deps.
                wanted.append(p)
            for i in range(0,len(wanted),100):
                _run_hidden([z,"x","-y",f"-o{stage}",arc]+wanted[i:i+100],
                               capture_output=True,text=True,errors="replace",timeout=240)
            roots=[]
            for dp,dirs,files in os.walk(stage):
                if dp.replace("\\","/").lower().endswith(f"/heroes/{lf}"):
                    roots.append(dp)
            for r in roots:_copy_tree_contents(r,mirrorhero)
            for x in os.listdir(stage):
                p=os.path.join(stage,x)
                if os.path.isdir(p):shutil.rmtree(p,ignore_errors=True)
                else:
                    try:os.remove(p)
                    except OSError:pass
    finally:shutil.rmtree(stage,ignore_errors=True)

LEGACY_TEXT_EXTS={".mdf",".material",".mtrl",".effect",".entity",".xml",".interface",".cfg"}
# Dependency references can be absolute/path-qualified OR avatar-local bare names
# such as model="model.model" / material="body.material". v1.38 only matched
# refs containing a slash, which left many MDF/material dependency chains incomplete
# and made K2 fall back to its teapot/error model.
LEGACY_REF_RE=re.compile(r"""(?ix)
    (?:
        ["'=(\s]
    )
    (
        (?:\.\.[\\/])*
        [\\/]?
        (?:[a-z0-9_.~@#$%()+\-]+[\\/])*
        [a-z0-9_.~@#$%()+\-]+
        \.(?:entity|effect|material|mtrl|mdf|model|clip|anim|tga|dds|png|ogg|wav)
    )
""")
_LEGACY_FS_INDEX={}
_LEGACY_HERO_KEYS={}
_LEGACY_SORTED_KEYS={}

def _logical_norm(p):
    p=str(p or "").replace("\\","/").strip().strip("\"'").lstrip("/")
    parts=[]
    for x in p.split("/"):
        if not x or x==".": continue
        if x=="..":
            if parts: parts.pop()
        else: parts.append(x)
    return "/".join(parts).lower()

def _legacy_fs_index(root,force=False):
    src=legacy_assets_root(root); key=os.path.abspath(src).lower()
    if not force and key in _LEGACY_FS_INDEX:return _LEGACY_FS_INDEX[key]
    exact={}; numbered={}; namespaces=[]
    if not os.path.isdir(src):
        _LEGACY_FS_INDEX[key]=(exact,numbered,namespaces);return _LEGACY_FS_INDEX[key]
    try:namespaces=sorted([x for x in os.listdir(src) if re.fullmatch(r"\d{8}",x) and os.path.isdir(os.path.join(src,x))])
    except OSError:namespaces=[]
    nsset=set(namespaces)
    for dp,_,fs in os.walk(src):
        relbase=os.path.relpath(dp,src).replace("\\","/"); parts=[] if relbase=="." else relbase.split("/")
        ns=parts[0] if parts and parts[0] in nsset else None
        for fn in fs:
            physical=os.path.join(dp,fn)
            if ns:
                logical=_logical_norm("/".join(parts[1:]+[fn])); numbered.setdefault(logical,[]).append((ns,physical))
            else:
                logical=_logical_norm("/".join(parts+[fn])); exact[logical]=physical
    for k in numbered:numbered[k].sort(key=lambda x:x[0])
    _LEGACY_FS_INDEX[key]=(exact,numbered,namespaces)
    _LEGACY_SORTED_KEYS[key]=sorted(set(exact)|set(numbered))
    # Build once: applying one avatar should inspect only that hero's files, not all
    # ~225k LegacyAssets entries on every click.
    hero_keys={}
    for logical in set(exact)|set(numbered):
        m=re.match(r"heroes/([^/]+)/",logical)
        if m:hero_keys.setdefault(m.group(1),[]).append(logical)
    _LEGACY_HERO_KEYS[key]=hero_keys
    diag(root,f"LEGACY_FS_INDEX exact={len(exact)} numbered={sum(len(v) for v in numbered.values())} namespaces={namespaces} heroes={len(hero_keys)}")
    return _LEGACY_FS_INDEX[key]

def _collapse_repeated_path_segments(value):
    """Collapse accidental repeated directory names in a resource reference."""
    raw=str(value or '').replace('\\','/')
    leading=raw.startswith('/')
    parts=[]
    for part in raw.split('/'):
        if not part or part=='.':
            continue
        if part=='..':
            parts.append(part)
            continue
        if parts and parts[-1]!='..' and parts[-1].lower()==part.lower():
            continue
        parts.append(part)
    out='/'.join(parts)
    return ('/' if leading else '')+out

def _repair_legacy_reference(root,ref,owner_logical=None):
    """Return a corrected logical ref when a duplicated directory is provable."""
    repaired=_collapse_repeated_path_segments(ref)
    if repaired==str(ref or '').replace('\\','/'):
        return ref
    if _resolve_legacy_logical_path(root,repaired,owner_logical):
        diag(root,f"REF_REPAIR original={ref} repaired={repaired}")
        return repaired
    return ref

def _trophy_normal_fallbacks(logical,owner_logical=None):
    """Return likely shared normal-map locations for a broken Trophy ref.

    Trophy materials sometimes retain a path from the ordinary hero ability
    tree, or point at a Trophy subdirectory that was never shipped.  The old
    client can still use the corresponding normal pair from the ordinary
    ability/pet directory.  Keep this inference limited to normal maps and to
    files owned by a Trophy asset so ordinary legacy references remain exact.
    """
    logical=_logical_norm(logical)
    owner=_logical_norm(owner_logical or "")
    stem,ext=os.path.splitext(logical)
    if not re.fullmatch(r"normal\d*",os.path.basename(stem).lower()):
        return []
    if "trophy_skin" not in logical and "trophy_skin" not in owner:
        return []

    out=[]
    def add(value):
        value=_logical_norm(value)
        if value and value not in out:out.append(value)

    # A direct Trophy path commonly has an ordinary counterpart after the
    # trophy_skin segment is removed.
    parts=logical.split('/')
    add('/'.join(x for x in parts if x.lower()!='trophy_skin'))

    if "trophy_skin" in owner:
        owner_parts=owner.split('/')
        owner_without_trophy='/'.join(
            x for x in owner_parts if x.lower()!='trophy_skin'
        )
        owner_dir=os.path.dirname(owner_without_trophy)
        raw_dir=os.path.dirname(logical)
        basename=os.path.basename(logical)

        # The reference can be one or more directories above the material's
        # actual effect folder.  Preserve that folder when it is the ordinary
        # counterpart of the Trophy owner (e.g. .../effects/wolves).
        if owner_without_trophy.lower().startswith(
            (raw_dir.rstrip('/') + '/').lower()
        ):
            add(owner_without_trophy+'/'+basename)
        add(owner_dir+'/'+basename)

    return out

def _resolve_legacy_logical_path(root,logical_ref,owner_logical=None,
                                 _allow_trophy_normal_fallback=True):
    exact,numbered,_=_legacy_fs_index(root)
    raw=str(logical_ref or "").replace("\\","/").strip().strip("\"'")
    candidates=[]
    if raw.startswith("/"):candidates.append(_logical_norm(raw))
    else:
        if owner_logical:candidates.append(_logical_norm(os.path.dirname(owner_logical).replace("\\","/")+"/"+raw))
        candidates.append(_logical_norm(raw))
    out=[]
    for q in candidates:
        logical_candidates=[q]
        collapsed=_collapse_repeated_path_segments(q)
        if collapsed!=q:
            logical_candidates.append(collapsed)
        variants=[]
        # Historical entity/material files frequently place an ability's
        # directory before ``effects`` while the copied legacy reference uses
        # ``effects/ability_XX``. Treat that layout difference as a valid
        # compatibility alias, alongside a few known legacy spelling aliases.
        compatible=[]
        for logical in list(logical_candidates):
            parts=logical.split('/')
            if (
                len(parts) >= 5 and parts[0] == 'heroes'
                and parts[2] == 'effects'
                and re.fullmatch(r'ability_\d+', parts[3], re.I)
            ):
                compatible.append('/'.join(
                    [parts[0],parts[1],parts[3],'effects']+parts[4:]
                ))
            # The inverse spelling is also common in old model/effect files:
            # ``ability_01/file`` while the extracted archive stores the file
            # below ``ability_01/effects/file``.
            if (
                len(parts) >= 4 and parts[0] == 'heroes'
                and re.fullmatch(r'ability_\d+', parts[2], re.I)
                and parts[3].lower() != 'effects'
            ):
                compatible.append('/'.join(
                    [parts[0],parts[1],parts[2],'effects']+parts[3:]
                ))
            if len(parts) >= 2 and parts[0] == 'heroes':
                if parts[1] == 'kenisis':
                    compatible.append('/'.join([parts[0],'kinesis']+parts[2:]))
                if parts[1] == 'bephelgor':
                    compatible.append('/'.join([parts[0],'behemoth']+parts[2:]))
                if parts[1] == 'set_ascent':
                    compatible.append('/'.join([parts[0],'set_ascension']+parts[2:]))
                if parts[1] == 'alt' and owner_logical:
                    owner_parts=_logical_norm(owner_logical).split('/')
                    if len(owner_parts) >= 2 and owner_parts[0] == 'heroes':
                        compatible.append('/'.join(
                            [parts[0],owner_parts[1]]+parts[2:]
                        ))
                # Some generated references retain a legacy folder name while
                # the mounted Reborn namespace uses the current hero name.
                for current, aliases in LEGACY_ALIASES.items():
                    if parts[1] == current:
                        compatible.extend('/'.join([parts[0],alias]+parts[2:]) for alias in aliases)
                    elif parts[1] in aliases:
                        compatible.append('/'.join([parts[0],current]+parts[2:]))
            if 'abilsity_01' in logical:
                compatible.append(logical.replace('abilsity_01','ability_01'))
        for logical in compatible:
            if logical not in logical_candidates:
                logical_candidates.append(logical)

        for logical in logical_candidates:
            if logical not in variants: variants.append(logical)
            stem,ext=os.path.splitext(logical)
            ext=ext.lower()

            # Legacy sound resources may reference WAV while the physical asset is OGG.
            if ext==".wav":
                variants.append(stem+".ogg")
            elif ext==".ogg":
                variants.append(stem+".wav")

            # K2 resources commonly reference TGA/PNG while textures.s2z stores
            # the compiled physical texture as DDS.
            if ext in (".tga",".png"):
                variants.append(stem+".dds")
                # Normal maps are stored as a compiled two-file bundle rather than
                # as one normal.dds file. Keep the logical normal.tga reference,
                # but resolve/copy both physical components.
                if re.fullmatch(r"normal\d*",os.path.basename(stem).lower()):
                    variants.extend([stem+"_rxgb.dds",stem+"_s.dds"])
            elif ext==".dds":
                variants.extend([stem+".tga",stem+".png"])

        for v in variants:
            if "%" in v:
                import fnmatch
                # Avoid walking the complete LegacyAssets index for every sound
                # wildcard. The fixed prefix narrows the sorted key list to the
                # relevant path range before fnmatch handles the suffix.
                all_keys=_LEGACY_SORTED_KEYS.get(
                    os.path.abspath(legacy_assets_root(root)).lower(), []
                )
                pattern=v.replace("%","*")
                prefix=pattern.split("*",1)[0]
                if prefix:
                    import bisect
                    lo=bisect.bisect_left(all_keys,prefix)
                    hi=bisect.bisect_right(all_keys,prefix+"\uffff")
                    candidate_keys=all_keys[lo:hi]
                else:
                    candidate_keys=all_keys
                for hit in (k for k in candidate_keys if fnmatch.fnmatchcase(k,pattern)):
                    if hit in exact:out.append((hit,exact[hit],"exact"))
                    elif numbered.get(hit):
                        pick=numbered[hit][0]
                        out.append((hit,pick[1],pick[0]))
            elif v in exact:out.append((v,exact[v],"exact"))
            elif numbered.get(v):
                # textures.s2z namespaces are resolution tiers, verified from DDS headers:
                # 00000000=512x512, 00000003=256x256, 00000005=128x128 for Ra Alt10.
                # Prefer the lowest namespace number (highest available resolution).
                pick=numbered[v][0]
                if len(numbered[v])>1:
                    diag(root,f"NAMESPACE_PICK logical={v} chosen={pick[0]} alternatives={[x[0] for x in numbered[v]]}")
                out.append((v,pick[1],pick[0]))
    ded=[];seen=set()
    for x in out:
        if x[0] not in seen:seen.add(x[0]);ded.append(x)
    if not ded and _allow_trophy_normal_fallback:
        # Resolve the fallback source normally, then publish the physical
        # normal pair under the original requested logical path.  Materials
        # continue to reference normal.tga while Runtime contains the paired
        # normal_rxgb.dds/normal_s.dds files at that path.
        for q in candidates:
            stem,ext=os.path.splitext(q)
            if not re.fullmatch(r"normal\d*",os.path.basename(stem).lower()):
                continue
            for fallback in _trophy_normal_fallbacks(q,owner_logical):
                hits=_resolve_legacy_logical_path(
                    root,fallback,None,_allow_trophy_normal_fallback=False
                )
                mapped=[]
                for logical,src,origin in hits:
                    name=os.path.basename(logical).lower()
                    if name=="normal_rxgb.dds":
                        mapped.append((stem+"_rxgb.dds",src,
                                       f"trophy-fallback:{origin}"))
                    elif name=="normal_s.dds":
                        mapped.append((stem+"_s.dds",src,
                                       f"trophy-fallback:{origin}"))
                if mapped:
                    diag(root,
                         f"TROPHY_NORMAL_FALLBACK requested={q} "
                         f"source={fallback} owner={owner_logical}")
                    return mapped
    return ded

def _repair_legacy_text_references(root,hero,av):
    """Repair duplicated path segments in copied text assets when provable."""
    lf=(hero.get('legacy_folder') or hero['folder']).lower()
    bases=[]
    for base in (legacy_dest(root,hero,av),legacy_mirror_dest(root,hero,av)):
        if os.path.isdir(base) and base not in bases: bases.append(base)
    repaired_count=0
    for base in bases:
        for dp,_,files in os.walk(base):
            for fn in files:
                if os.path.splitext(fn)[1].lower() not in LEGACY_TEXT_EXTS:
                    continue
                path=os.path.join(dp,fn)
                try: text=read_text(path)
                except OSError: continue
                rel=os.path.relpath(path,base).replace('\\','/')
                owner=f"heroes/{lf}/{av.lower()}/{rel}"
                changed=False
                def replace(match):
                    nonlocal changed,repaired_count
                    raw=match.group(1)
                    fixed=_repair_legacy_reference(root,raw,owner)
                    if fixed!=raw:
                        changed=True
                        repaired_count+=1
                        return match.group(0).replace(raw,fixed,1)
                    return match.group(0)
                updated=LEGACY_REF_RE.sub(replace,text)
                if changed: write_text(path,updated)
    if repaired_count:
        diag(root,f"REF_REPAIR_DONE hero={hero['folder']} avatar={av} count={repaired_count}")
    return repaired_count

def _copy_legacy_logical_asset(root,logical_ref,owner_logical=None,queue=None,seen=None):
    copied=0
    for logical,src,origin in _resolve_legacy_logical_path(root,logical_ref,owner_logical):
        dst=os.path.join(switcher_root(root),*logical.split("/"));os.makedirs(os.path.dirname(dst),exist_ok=True)
        if not os.path.isfile(dst) or os.path.getsize(dst)!=os.path.getsize(src):shutil.copy2(src,dst);copied+=1
        diag(root,f"NORMALIZE {logical} <- {origin}:{src}")
        if queue is not None and logical not in seen:queue.append(logical)
    return copied


def _legacy_avatar_physical_root(av, oldattrs=None):
    """Return the historical physical package directory for an avatar.

    Usually AltN -> AltN, but some avatars use a logical key whose assets
    live elsewhere, e.g. trophy_skin01 -> trophy_skin/model_01.
    """
    avl = av.lower()
    model_ref = ((oldattrs or {}).get("model") or "").replace("\\", "/").strip()

    if model_ref and not model_ref.startswith("/"):
        model_dir = os.path.dirname(model_ref).strip("/")
        if model_dir:
            return model_dir.lower()

    return avl

def _normalize_legacy_avatar_assets(root,hero,av,oldattrs=None):
    """Fast avatar-package seed: copy only files physically belonging to this AltN.

    LegacyAssets is already extracted.  Do not recursively crawl the whole hero tree.
    The old S2Z layout is authoritative: heroes/<legacyhero>/<alt>/ plus explicitly
    AltN-named hero files. Numbered texture namespaces are normalized by the resolver.
    """
    if not os.path.isdir(legacy_assets_root(root)):return 0
    exact,numbered,_=_legacy_fs_index(root)
    lf=(hero.get("legacy_folder") or hero["folder"]).lower(); modern=hero["folder"].lower(); avl=av.lower()


    # The logical avatar key is not always its physical directory.
    # Example:
    #   trophy_skin01 -> model="trophy_skin/model_01/model.mdf"
    # Prefer the directory containing the historical model as the package root.
    physical_root = _legacy_avatar_physical_root(av, oldattrs)


    idxkey=os.path.abspath(legacy_assets_root(root)).lower()
    hero_candidates=_LEGACY_HERO_KEYS.get(idxkey,{}).get(lf,[])

    prefix=f"heroes/{lf}/{physical_root}/"
    baseprefix=f"heroes/{lf}/base/{physical_root}/"


    logicals=set()
    for k in hero_candidates:
        tail=k[len(f"heroes/{lf}/"):] if k.startswith(f"heroes/{lf}/") else k
        if k.startswith(prefix) or k.startswith(baseprefix):
            logicals.add(k)
        elif re.search(r'(^|[/_.-])'+re.escape(avl)+r'([/_.-]|$)',tail):
            # Old HoN also stores e.g. ability_04/effects/cast_alt7.effect outside alt7/.
            logicals.add(k)
    copied=0
    for logical in sorted(logicals):
        copied += _copy_legacy_logical_asset(root,logical)
        if lf!=modern and logical.startswith(f"heroes/{lf}/"):
            hits=_resolve_legacy_logical_path(root,logical)
            if hits:
                mapped=f"heroes/{modern}/"+logical[len(f"heroes/{lf}/"):]
                dst=os.path.join(switcher_root(root),*mapped.split('/'));os.makedirs(os.path.dirname(dst),exist_ok=True)
                shutil.copy2(hits[0][1],dst);copied+=1
    diag(root,f"AVATAR_SUBTREE_DONE hero={hero['folder']} legacy={lf} avatar={av} copied={copied} logicals={len(logicals)}")
    return copied

def _legacy_avatar_text_ref_items(root,hero,av,oldattrs=None):
    """Collect references from the selected avatar's copied text assets."""
    lf=(hero.get("legacy_folder") or hero["folder"]).lower()
    refs=[]
    physical=_legacy_avatar_physical_root(av,oldattrs)
    bases=[legacy_dest(root,hero,av),legacy_mirror_dest(root,hero,av)]
    # Trophy keys such as trophy_skin02 share the physical trophy_skin
    # directory.  Scan that directory too, otherwise material dependencies
    # inside the shared package never enter the bounded dependency graph.
    if physical.lower()!=av.lower():
        bases.extend([
            legacy_dest(root,hero,physical),
            legacy_mirror_dest(root,hero,physical),
        ])
    seen_bases=set()
    for base in bases:
        key=os.path.abspath(base).lower()
        if key in seen_bases:continue
        seen_bases.add(key)
        if not os.path.isdir(base):continue
        for dp,_,files in os.walk(base):
            for fn in files:
                if os.path.splitext(fn)[1].lower() not in LEGACY_TEXT_EXTS:
                    continue
                path=os.path.join(dp,fn)
                try:text=read_text(path)
                except Exception:continue
                rel=os.path.relpath(path,base).replace("\\","/")
                owner=os.path.relpath(path,switcher_root(root)).replace("\\","/")
                refs.extend((owner,m.group(1)) for m in LEGACY_REF_RE.finditer(' '+text))
    return refs

def _legacy_named_entity_exists(root,hero,av,name):
    """Check whether a selected avatar ships a named entity dependency.

    Historical hero modifiers can point at a separate projectile entity by
    name. If that definition is absent, keeping the old name makes the game
    silently lose the attack projectile; the caller can retain Reborn's
    current default object instead.
    """
    wanted=str(name or '').strip().lower()
    if not wanted or '/' in wanted or '\\' in wanted:
        return False
    for base in (legacy_dest(root,hero,av),legacy_mirror_dest(root,hero,av)):
        if not os.path.isdir(base):
            continue
        for dp,_,files in os.walk(base):
            for fn in files:
                if not fn.lower().endswith('.entity'):
                    continue
                path=os.path.join(dp,fn)
                try:text=read_text(path)
                except OSError:continue
                m=re.search(r'<\s*[A-Za-z_][A-Za-z0-9_.:-]*\b[^>]*\bname\s*=\s*"([^"]+)"',text,re.I|re.S)
                if m and m.group(1).strip().lower()==wanted:
                    return True
    return False


def _normalize_explicit_cosmetic_refs(root,hero,av,ref_items):
    """Resolve explicit cosmetic roots and a bounded dependency closure.

    Unlike v1.45 this never scans/copies an entire hero. Dependencies are followed only
    from files reached from explicit avatar metadata, and each edge is logged.
    """
    lf=(hero.get("legacy_folder") or hero["folder"]).lower(); avl=av.lower()
    queue=[]; seen=set(); copied=0; provenance={}
    def add(ref,owner,why):
        nonlocal copied
        if not ref:return
        for logical,src,origin in _resolve_legacy_logical_path(root,ref,owner):
            if logical in seen or logical in provenance:continue
            provenance[logical]={"owner":owner or "<avatar>","ref":str(ref),"why":why,"origin":origin}
            dst=os.path.join(switcher_root(root),*logical.split('/'));os.makedirs(os.path.dirname(dst),exist_ok=True)
            if not os.path.isfile(dst) or os.path.getsize(dst)!=os.path.getsize(src):shutil.copy2(src,dst);copied+=1
            queue.append(logical)
            diag(root,f"DEP {logical} <- {owner or '<avatar>'} ref={ref} origin={origin}")
    for owner,ref in ref_items:
        if re.search(r'(?i)\.(?:entity|effect|material|mtrl|mdf|model|clip|anim|tga|dds|png|ogg|wav)$',str(ref or '').strip()):
            add(ref,owner,"explicit-avatar-metadata")
    rounds=0
    while queue and rounds<5000:
        owner=queue.pop(0); rounds+=1
        if owner in seen:continue
        seen.add(owner)
        fp=os.path.join(switcher_root(root),*owner.split('/'))
        if os.path.splitext(owner)[1].lower() not in LEGACY_TEXT_EXTS or not os.path.isfile(fp):continue
        try:txt=read_text(fp)
        except Exception:continue
        for m in LEGACY_REF_RE.finditer(' '+txt):
            ref=m.group(1)
            # Follow real resource dependencies of reached model/material/effect files,
            # but never enumerate neighboring files or the whole hero directory.
            add(ref,owner,"text-reference")
    diag(root,f"EXPLICIT_GRAPH_DONE hero={hero['folder']} avatar={av} copied={copied} nodes={len(provenance)} rounds={rounds}")
    return copied


# Old persistent body-shell effects known to render as a translucent blue overlay.
# NOTE v1.40 also fixes texture namespace precedence; Gauntlet Alt10's wrong palette
# (including Q glow) indicates stale texture/material generation can be the real cause.
# under Reborn. This is deliberately narrow; ability/projectile FX remain untouched.
BODY_SHELL_COMPAT = {
    ("valkyrie","alt7"),
    ("flint_beastwood","alt12"),
    ("flintbeastwood","alt12"),
    ("gauntlet","alt10"),
}
BODY_SHELL_FILES = (
    "effects/body.effect","effects/body_lvl4.effect","effects/body_lvl8.effect",
    "effects/body_lvl12.effect","effects/body_lvl16.effect",
    "effects/charged/body.effect","effects/charged/body_4.effect","effects/charged/body_16.effect",
)

def _suppress_legacy_body_shell(root,hero,av):
    key=(hero["folder"].lower(),av.lower())
    if key not in BODY_SHELL_COMPAT:return 0
    removed=0
    for base in (legacy_dest(root,hero,av),legacy_mirror_dest(root,hero,av)):
        for rel in BODY_SHELL_FILES:
            q=os.path.join(base,*rel.split("/"))
            try:
                if os.path.isfile(q):os.remove(q);removed+=1
            except OSError:pass
    # Normalization also writes the logical legacy path directly under Runtime.
    lf=(hero.get("legacy_folder") or hero["folder"]).lower()
    for rel in BODY_SHELL_FILES:
        q=os.path.join(switcher_root(root),"heroes",lf,av,*rel.split("/"))
        try:
            if os.path.isfile(q):os.remove(q);removed+=1
        except OSError:pass
    diag(root,f"BODY_SHELL_SUPPRESS hero={hero['folder']} avatar={av} removed={removed}")
    return removed

def cleanup_old_switcher_files(root):
    """Remove only overrides explicitly marked as created by older switcher versions."""
    oldroot=os.path.join(root,"~mods","heroes")
    if not os.path.isdir(oldroot):return 0
    n=0
    for dp,dirs,files in os.walk(oldroot):
        if "hero.entity.hon_avatar_switcher_created" in files:
            ent=os.path.join(dp,"hero.entity")
            mark=ent+".hon_avatar_switcher_created"
            for p in (ent,mark):
                try:
                    if os.path.isfile(p):os.remove(p)
                except OSError:pass
            n+=1
    return n

def _package_stamp(root,hero,av):
    return os.path.join(legacy_dest(root,hero,av),".hon_avatar_package_v140")

def legacy_package_ready(root,hero,av):
    d=legacy_dest(root,hero,av)
    return os.path.isfile(os.path.join(d,"model.mdf")) and os.path.isfile(_package_stamp(root,hero,av))

def extract_legacy_avatar(root,hero,av,z,larcs,lmembers):
    """
    Build both:
      avatar_switcher/heroes/<modern>/base/<avatar>/   (skin overlay)
      avatar_switcher/heroes/<legacy>/<avatar>/        (old absolute refs / voices)
    from every matching resource, HD-sound and texture archive member.
    """
    lf=(hero.get("legacy_folder") or hero["folder"]).lower()
    dst=legacy_dest(root,hero,av)
    # v1.9.1 package cache: extraction is expensive, so reuse a verified package.
    if legacy_package_ready(root,hero,av):
        return 0
    # Extract shared visual dependencies only once per legacy hero.
    support_stamp=os.path.join(switcher_root(root),"heroes",lf,".hon_support_v120")
    if not os.path.isfile(support_stamp):
        _extract_legacy_support_tree(root,hero,z,larcs,lmembers)
        os.makedirs(os.path.dirname(support_stamp),exist_ok=True)
        write_text(support_stamp,"ok\n")
    mirror=legacy_mirror_dest(root,hero,av)
    for d in (dst,mirror):
        if os.path.isdir(d): shutil.rmtree(d,ignore_errors=True)
        os.makedirs(d,exist_ok=True)

    stage=tempfile.mkdtemp(prefix="hon_legacy_v18_")
    copied=0
    try:
        for arc in larcs:
            wanted=[]
            markers=(f"heroes/{lf}/{av.lower()}/", f"heroes/{lf}/base/{av.lower()}/")
            for p in lmembers.get(arc,[]):
                low=p.lower().replace("\\","/").strip("/")
                if any(marker in low for marker in markers):
                    wanted.append(p)
            if not wanted: continue

            for i in range(0,len(wanted),100):
                _run_hidden([z,"x","-y",f"-o{stage}",arc]+wanted[i:i+100],
                               capture_output=True,text=True,errors="replace",timeout=240)

            roots=[]
            for dp,dirs,files in os.walk(stage):
                normdp=dp.replace("\\","/").lower()
                if (normdp.endswith(f"/heroes/{lf}/{av.lower()}") or
                    normdp.endswith(f"/heroes/{lf}/base/{av.lower()}")):
                    roots.append(dp)
            for r in roots:
                copied += _copy_tree_contents(r,dst)
                _copy_tree_contents(r,mirror)

            for x in os.listdir(stage):
                p=os.path.join(stage,x)
                if os.path.isdir(p): shutil.rmtree(p,ignore_errors=True)
                else:
                    try: os.remove(p)
                    except OSError: pass
    finally:
        shutil.rmtree(stage,ignore_errors=True)

    # Valkyrie Alt7 compatibility: old package includes persistent body/charge
    # overlays that can render as an unwanted translucent blue shell in Reborn.
    if hero["folder"].lower()=="valkyrie" and av.lower()=="alt7":
        for rel in [
            "effects/body.effect","effects/body_lvl4.effect","effects/body_lvl8.effect",
            "effects/body_lvl12.effect","effects/body_lvl16.effect",
            "effects/charged/body.effect","effects/charged/body_4.effect",
            "effects/charged/body_16.effect"
        ]:
            for d in (dst,mirror):
                p=os.path.join(d,*rel.split("/"))
                if os.path.isfile(p):
                    try: os.remove(p)
                    except OSError: pass

    if not os.path.isfile(os.path.join(dst,"model.mdf")):
        raise RuntimeError(f"Legacy {av} import did not produce model.mdf.")
    # Compatibility: these old skins carry a body shell effect that renders as a
    # translucent blue overlay in Reborn. Keep ability/projectile effects intact.
    if (hero["folder"].lower(),av.lower()) in {("valkyrie","alt7"),("flint_beastwood","alt12"),("flintbeastwood","alt12")}:
        for base in (dst,legacy_mirror_dest(root,hero,av)):
            for rel in ("effects/body.effect","effects/body_lvl4.effect","effects/body_lvl8.effect",
                        "effects/body_lvl12.effect","effects/body_lvl16.effect",
                        "effects/charged/body.effect","effects/charged/body_4.effect","effects/charged/body_16.effect"):
                q=os.path.join(base,*rel.split("/"))
                try:
                    if os.path.isfile(q):os.remove(q)
                except OSError:pass
    write_text(_package_stamp(root,hero,av),"ok\n")
    return copied

def _legacy_root_entity_member(hero,lmembers):
    lf=(hero.get("legacy_folder") or hero["folder"]).lower()
    suffix=f"heroes/{lf}/hero.entity"
    for arc,paths in lmembers.items():
        for p in paths:
            low=p.lower().replace("\\","/").strip("/")
            if low.endswith(suffix):
                return arc,p
    return None,None

def _parse_attrs(tag):
    return {m.group(1).lower():m.group(2) for m in re.finditer(r'([A-Za-z0-9_]+)\s*=\s*"([^"]*)"',tag)}

def legacy_modifier_attrs(hero,av,z,lmembers,tmp):
    """Read the old avatar modifier. Match by key OR by asset paths containing the avatar.
    Old HoN generations used several modifier naming conventions, so key-only matching loses
    names, voice refs and modelscale for otherwise valid avatars.
    """
    
    arc,mem=_legacy_root_entity_member(hero,lmembers)

    # Prefer the fully extracted historical hero.entity when available.
    # Some avatar metadata exists here even when the archive-member index
    # does not contain the corresponding entity.
    root=hero.get("_root","")
    lf=(hero.get("legacy_folder") or hero["folder"]).lower()
    fs_entity=os.path.join(legacy_assets_root(root),"heroes",lf,"hero.entity")

    if os.path.isfile(fs_entity):
        p=fs_entity
    elif arc:
        p=extract_member(z,arc,mem,tmp)
    else:
        return {}

    if not p or not os.path.isfile(p):
        return {}

    txt=read_text(p); avl=av.lower(); best=None; bestscore=-1


    for m in re.finditer(r'<[^>]+>',txt,re.S):
        attrs=_parse_attrs(m.group(0))
        keys=[attrs.get(x,'').lower() for x in ('key','modifier','skin')]
        score=0
        if avl in keys: score+=100
        # Historical keys are normally Hero_Foo.Alt7, not simply Alt7.
        if any(k.endswith('.'+avl) for k in keys if k): score+=1000
        # Asset-reference match is the important generic fallback.
        for v in attrs.values():
            vv=v.replace('\\','/').lower()
            if re.search(r'(?:^|/)'+re.escape(avl)+r'(?:/|$)',vv): score+=15
            if vv.startswith(avl+'/'): score+=20
        if score>bestscore and score>0: best,bestscore=attrs,score
    return best or {}

def legacy_avatar_display_name(hero,av,z,lmembers,tmp):
    root=hero.get("_root","")
    key=f"{hero.get('legacy_folder') or hero['folder']}::{av}".lower()
    namesfile=os.path.join(cache_dir(root),"avatar_names.json") if root else None
    names={}
    if namesfile and os.path.isfile(namesfile):
        try:names=json.load(open(namesfile,"r",encoding="utf-8"))
        except Exception:names={}
    if key in names:return names[key]
    attrs=legacy_modifier_attrs(hero,av,z,lmembers,tmp)
    raw=(attrs.get("displayname") or attrs.get("display_name") or attrs.get("modifiername") or
         attrs.get("label") or attrs.get("propername") or "")
    val=raw.strip()
    # Some old entities contain localization keys rather than the resolved store name.
    # Keep only genuinely human-readable values; otherwise retain AltN until a name is known.
    if not val or val.lower().startswith(("hero_","modifier_","altavatar_","store_")):
        val=pretty_avatar(av)
    names[key]=val
    if namesfile:
        try:
            os.makedirs(os.path.dirname(namesfile),exist_ok=True)
            json.dump(names,open(namesfile,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
        except Exception:pass
    return val

def _legacy_package_has_voice(root,hero,av):
    """Return True when either prepared avatar location contains voice audio.

    Historical assets may live under the legacy hero namespace
    (for example heroes/ra/alt5) while generated Reborn overrides live under
    the modern namespace (for example heroes/amun_ra/...).
    """
    oldattrs=(hero.get("legacy_info") or {}).get(av,{})
    physical=_legacy_avatar_physical_root(av,oldattrs)
    bases=[legacy_dest(root,hero,av),legacy_mirror_dest(root,hero,av)]
    if physical.lower()!=av.lower():
        bases.extend([
            legacy_dest(root,hero,physical),
            legacy_mirror_dest(root,hero,physical),
        ])
    seen=set()
    for d in bases:
        key=os.path.abspath(d).lower()
        if key in seen:continue
        seen.add(key)
        if not os.path.isdir(d):
            continue

        for dp,_,fs in os.walk(d):
            low=dp.replace("\\","/").lower()

            if "/sounds/" in low or low.endswith("/sounds"):
                if any(
                    fn.lower().endswith((".ogg",".wav"))
                    for fn in fs
                ):
                    return True

    return False

def _legacy_ref_exists(root,hero,av,ref):
    """Best-effort existence check for a legacy modifier reference after full-package import."""
    raw=(ref or '').replace('\\','/').lstrip('./')
    lf=(hero.get('legacy_folder') or hero['folder']).lower()
    oldattrs=(hero.get("legacy_info") or {}).get(av,{})
    physical=_legacy_avatar_physical_root(av,oldattrs)
    tokens={av.lower(),physical.lower()}
    prefixes=[]
    for token in tokens:
        prefixes.extend((
            f'heroes/{lf}/{token}/',
            f'heroes/{lf}/base/{token}/',
            token+'/',
        ))
    for prefix in prefixes:
        if raw.lower().startswith(prefix):raw=raw[len(prefix):];break
    bases=[legacy_dest(root,hero,av),legacy_mirror_dest(root,hero,av)]
    if physical.lower()!=av.lower():
        bases.extend([
            legacy_dest(root,hero,physical),
            legacy_mirror_dest(root,hero,physical),
        ])
    seen_bases=set()
    for base in bases:
        key=os.path.abspath(base).lower()
        if key in seen_bases:continue
        seen_bases.add(key)
        q=os.path.join(base,*raw.split('/'))
        if os.path.isfile(q):return True
        # K2 uses % as a numbered sound wildcard (select_%.wav -> select_1, select_2, ...).
        # Historical metadata also commonly says .wav while the shipped payload is .ogg.
        # Validate the logical K2 reference against either physical encoding.


        candidates=[q]
        stem,ext=os.path.splitext(q)
        ext=ext.lower()

        if ext=='.wav':
            candidates.append(stem+'.ogg')
        elif ext=='.ogg':
            candidates.append(stem+'.wav')
        elif ext in ('.tga','.png'):
            candidates.append(stem+'.dds')
        elif ext=='.dds':
            candidates.extend([stem+'.tga',stem+'.png'])

        for cq in candidates:
            if '%' in cq:
                import glob
                pattern=glob.escape(cq).replace('%','*')
                if any(os.path.isfile(hit) for hit in glob.glob(pattern)):
                    return True
            elif os.path.isfile(cq):
                return True
    # Some old references changed directory roots between resource archives. Match tail/basename.
    bn=os.path.basename(raw).lower()
    if bn:
        import fnmatch

        patterns=[bn]
        stem,ext=os.path.splitext(bn)
        ext=ext.lower()

        if ext=='.wav':
            patterns.append(stem+'.ogg')
        elif ext=='.ogg':
            patterns.append(stem+'.wav')
        elif ext in ('.tga','.png'):
            patterns.append(stem+'.dds')
        elif ext=='.dds':
            patterns.extend([stem+'.tga',stem+'.png'])

        patterns=[x.replace('%','*') for x in patterns]
        for base in bases:
            for _,_,fs in os.walk(base):
                for x in fs:
                    if any(fnmatch.fnmatch(x.lower(),pat) for pat in patterns): return True
    return False

def _rewrite_available_texture_extension(root, ref, owner_logical=None):
    """Use the physical texture extension that the prepared package contains.

    Historical entity metadata commonly names DDS textures as ``.tga``. The
    character selector can resolve that convention through its source index,
    but the in-game command bar expects the generated entity path to match the
    published file (for example ``icon.dds``).
    """
    if not root or not ref:
        return ref
    raw = str(ref).replace("\\", "/")
    ext = os.path.splitext(raw.split(",", 1)[0])[1].lower()
    if ext not in (".tga", ".png", ".dds") or "," in raw:
        return ref
    hits = _resolve_legacy_logical_path(root, raw, owner_logical)
    if not hits:
        return ref
    # PreparedAssets is mounted as loose files. The archive index can resolve
    # normal.tga to its paired channels, but a loose overlay needs an explicit
    # normal channel; normal_s.dds remains the separate specular sampler.
    if re.fullmatch(r"normal\d*",os.path.basename(os.path.splitext(raw.split(",",1)[0])[0]).lower()):
        stem_name=os.path.basename(os.path.splitext(raw.split(",",1)[0])[0]).lower()
        if any(os.path.basename(x[0]).lower() == stem_name+"_rxgb.dds" for x in hits):
            extpart=os.path.splitext(raw.split(",",1)[0])[1]
            return raw[:-len(extpart)] + "_rxgb.dds"
    physical_ext = os.path.splitext(hits[0][0])[1].lower()
    if physical_ext not in (".tga", ".png", ".dds") or physical_ext == ext:
        return ref
    return raw[:-len(ext)] + physical_ext


def _rewrite_old_asset_path(v,hero,av,root=None):
    """Turn old relative avatar refs into stable absolute refs to the legacy mirror."""
    if not v:return v
    vv=v.replace("\\","/")
    owner=f"heroes/{(hero.get('legacy_folder') or hero['folder']).lower()}/hero.entity"
    if vv.startswith("/"):
        return _rewrite_available_texture_extension(root, vv)
    lf=(hero.get("legacy_folder") or hero["folder"])
    low=vv.lower().lstrip("./")
    oldattrs=(hero.get("legacy_info") or {}).get(av,{})
    physical=_legacy_avatar_physical_root(av,oldattrs)
    mounted=physical if physical.lower()!=av.lower() else av
    if physical.lower()!=av.lower() and low.startswith(physical.lower()+"/"):
        # Shared Trophy packages are mounted under their physical directory.
        out=f"/heroes/{lf}/{vv.lstrip('./')}"
    elif low.startswith(av.lower()+"/"):
        tail=vv.lstrip("./")[len(av)+1:]
        out=f"/heroes/{lf}/{mounted}/{tail}"
    elif low.startswith("base/"):
        out=f"/heroes/{lf}/{vv.lstrip('./')}"
    # Old modifier sound refs are often already avatar-local.
    elif "sound" in low or low.endswith((".ogg",".wav")):
        out=f"/heroes/{lf}/{mounted}/{vv.lstrip('./')}"
    elif root:
        # A historical avatar may explicitly reuse a sibling avatar package,
        # such as Sir Benzington Alt13 reusing Alt12's portrait/store model.
        # Resolve that mounted sibling instead of leaving the ref relative to
        # the generated base/ directory.
        sibling_candidates=[os.path.join(switcher_root(root),"heroes",lf,*low.split("/"))]
        sibling_ext=os.path.splitext(low)[1]
        if sibling_ext in (".tga",".png"):
            sibling_candidates.append(os.path.splitext(sibling_candidates[0])[0]+".dds")
        if any(os.path.isfile(item) for item in sibling_candidates):
            out=f"/heroes/{lf}/{vv.lstrip('./')}"
        elif _legacy_ref_exists(root,hero,av,vv):
            out=f"/heroes/{lf}/{mounted}/{vv.lstrip('./')}"
        else:
            out=vv
    else:
        out=vv
    return _rewrite_available_texture_extension(root, out, owner)

# Empirical Reborn compatibility corrections from in-game regression tests.
# Values are intentionally narrow: do not guess for untested avatars.
SCALE_CORRECTIONS={}

ABILITY_COSMETIC_ATTRS={
    "icon","icon2","targetscheme","casteffect","caststarteffect","castactioneffect",
    "impacteffect","stateeffect","passiveeffect","projectile","projectilemodel",
    "projectileeffect","model","deatheffect","trailEffect".lower(),"selectedsound",
    "activatesound","impactsound","castsound","loopsound","dynamicprecache"
}


def _legacy_entity_blocks(hero,av,z,lmembers,tmp):
    """Return cosmetic altavatar attrs from legacy hero ability/item entity files."""
    lf=(hero.get("legacy_folder") or hero["folder"]).lower()
    out=[]
    avl=av.lower()

    # Prefer the canonical extracted LegacyAssets tree.
    root=hero.get("_root","")
    hero_dir=os.path.join(legacy_assets_root(root),"heroes",lf)

    if os.path.isdir(hero_dir):
        for dp,_,files in os.walk(hero_dir):
            for fn in files:
                if not fn.lower().endswith(".entity"):
                    continue

                ep=os.path.join(dp,fn)
                mem=os.path.relpath(
                    ep,
                    legacy_assets_root(root)
                ).replace("\\","/")

                low=mem.lower().strip("/")

                if low.endswith("/hero.entity"):
                    continue

                try:
                    txt=read_text(ep)
                except Exception:
                    continue

                for m in re.finditer(r'<altavatar\b([^>]*)>',txt,re.I|re.S):
                    a=_parse_attrs(m.group(0))
                    key=a.get("key","").lower()

                    if key.endswith("."+avl):
                        out.append((
                            mem,
                            {k:v for k,v in a.items() if k in ABILITY_COSMETIC_ATTRS}
                        ))

        return out

    # Fallback for archive-only historical sources.
    for arc,paths in lmembers.items():
        for mem in paths:
            low=mem.lower().replace("\\","/").strip("/")

            if (not low.startswith(f"heroes/{lf}/")
                or not low.endswith(".entity")
                or low.endswith("/hero.entity")):
                continue

            ep=extract_member(z,arc,mem,tmp)
            if not ep:
                continue

            txt=read_text(ep)

            for m in re.finditer(r'<altavatar\b([^>]*)>',txt,re.I|re.S):
                a=_parse_attrs(m.group(0))
                key=a.get("key","").lower()

                if key.endswith("."+avl):
                    out.append((
                        mem,
                        {k:v for k,v in a.items() if k in ABILITY_COSMETIC_ATTRS}
                    ))

    return out


def _legacy_ability_modifier_blocks(hero, av, z, lmembers, tmp):
    """Read cosmetic fields from modifiers nested inside an avatar block.

    Some historical abilities keep the visual for a state transition in a
    nested modifier instead of on the altavatar tag itself.  Keep the
    modifier key as metadata so the overlay can patch the matching current
    Reborn modifier without importing historical gameplay actions.
    """
    out = []
    seen = set()
    for member, _ in _legacy_entity_blocks(hero, av, z, lmembers, tmp):
        if member in seen:
            continue
        seen.add(member)
        text = _legacy_name_source(hero.get("_root", ""), member, z, lmembers, tmp)
        for block in re.finditer(r'<altavatar\b([^>]*)>(.*?)</altavatar\s*>', text, re.I | re.S):
            head = _parse_attrs(block.group(1))
            if head.get("key", "").rsplit(".", 1)[-1].lower() != av.lower():
                continue
            for modifier in re.finditer(r'<modifier\b([^>]*)/?>', block.group(2), re.I | re.S):
                attrs = _parse_attrs(modifier.group(0))
                key = attrs.get("key", "").strip()
                if not key:
                    continue
                visual = {k: v for k, v in attrs.items() if k in ABILITY_COSMETIC_ATTRS}
                if visual:
                    visual["__modifier_key"] = key
                    out.append((member, visual))
    return out



def _legacy_hasavatarkey_actions(root, hero, av):
    """Discover cosmetic actions inside matching legacy hasavatarkey nodes.

    Read from the canonical extracted LegacyAssets tree. Only explicitly
    cosmetic actions are returned; historical gameplay actions are ignored.
    """
    import xml.etree.ElementTree as ET

    legacy_root = legacy_assets_root(root)
    heroes_root = os.path.join(legacy_root, "heroes")

    lf = (hero.get("legacy_folder") or "").lower()

    if not lf or not os.path.isdir(os.path.join(heroes_root, lf)):
        probes = [
            hero.get("folder", "").lower(),
            hero.get("key", "").lower(),
        ]

        candidates = []
        for probe in probes:
            if not probe:
                continue
            candidates.append(probe)
            candidates.extend(LEGACY_ALIASES.get(probe, []))
            candidates.extend(LEGACY_ALIASES.get(_simple_name(probe), []))

        for candidate in candidates:
            if os.path.isdir(os.path.join(heroes_root, candidate)):
                lf = candidate
                break

    hero_dir = os.path.join(heroes_root, lf)


    out = []

    if not os.path.isdir(hero_dir):
        return out

    for dp, _, files in os.walk(hero_dir):
        for fn in files:
            if not fn.lower().endswith(".entity"):
                continue

            path = os.path.join(dp, fn)
            rel = os.path.relpath(
                path,
                legacy_assets_root(root)
            ).replace("\\", "/")

            low = rel.lower()

            if low.endswith("/hero.entity"):
                continue

            if not any(x in low for x in ("/ability_", "/abilities/", "/ability")):
                continue

            try:
                rootxml = ET.parse(path).getroot()
            except Exception:
                continue

            for node in rootxml.iter():
                tag = node.tag.lower().split("}")[-1]

                if tag != "hasavatarkey":
                    continue

                name = node.attrib.get("name", "").lower()

                if not name.endswith("." + av.lower()):
                    continue

                actions = []

                for child in node.iter():
                    if child is node:
                        continue

                    ctag = child.tag.lower().split("}")[-1]

                    if ctag == "play2dsound":
                        attrs = {
                            k.lower(): v
                            for k, v in child.attrib.items()
                        }

                        if attrs.get("sample"):
                            actions.append(("play2dsound", attrs))

                    elif ctag == "playeffect":
                        attrs = {
                            k.lower(): v
                            for k, v in child.attrib.items()
                        }

                        if attrs.get("effect"):
                            actions.append(("playeffect", attrs))

                if actions:
                    out.append((rel, actions))

    return out



def _current_ability_member(hero,legacy_mem):
    """Map a historical hero ability entity path to the CURRENT Reborn member."""
    low=legacy_mem.replace("\\","/").strip("/")
    m=re.search(r"(?:^|/)heroes/[^/]+/(.*)$",low,re.I)
    if not m:return None
    tail=m.group(1).lower()
    # Current archives can put support entities directly under the hero or under base/.
    candidates=[]
    for mem in hero.get("archive",{}).get("paths",[]):
        ml=mem.replace("\\","/").strip("/").lower()
        if ml.endswith("/"+tail) or ml.endswith("/base/"+tail):
            candidates.append(mem)
    if not candidates:return None
    return min(candidates,key=lambda x:(len(x),x.lower()))

def _rewrite_ability_cosmetic_ref(v, hero, av, legacy_mem=None, root=None):
    """Resolve cosmetic refs using the ORIGINAL legacy entity location."""
    if not v:
        return v

    import posixpath

    vv = v.replace("\\", "/")
    lf = (hero.get("legacy_folder") or hero["folder"]).lower()

    # Absolute references already have an unambiguous logical location.
    if vv.startswith("/"):
        return _rewrite_available_texture_extension(root, vv)

    # Resolve relative refs from the OLD entity, not from the generated
    # current-Reborn entity.
    #
    # Example:
    #   legacy entity:
    #       heroes/ra/ability_01/ability.entity
    #
    #   ref:
    #       ../alt5/ability_01/icon.tga
    #
    #   result:
    #       /heroes/ra/alt5/ability_01/icon.tga
    if legacy_mem:
        owner = legacy_mem.replace("\\", "/").strip("/")
        base = posixpath.dirname(owner)
        resolved = posixpath.normpath(posixpath.join(base, vv))

        if resolved.lower().startswith("heroes/"):
            return _rewrite_available_texture_extension(root, "/" + resolved)

    # Avatar-local fallback.
    low = vv.lower().lstrip("./")
    if low.startswith(av.lower() + "/"):
        return _rewrite_available_texture_extension(
            root, f"/heroes/{lf}/{vv.lstrip('./')}"
        )

    return _rewrite_available_texture_extension(root, vv)

def _clear_managed_ability_overrides(root,hero):
    base=os.path.join(switcher_root(root),"heroes",hero["folder"])
    removed=0
    if not os.path.isdir(base):return removed
    for dp,_,fs in os.walk(base):
        for fn in fs:
            if fn.endswith('.onepunch_ability_managed'):
                marker=os.path.join(dp,fn); target=marker[:-len('.onepunch_ability_managed')]
                try:
                    if os.path.isfile(target):os.remove(target);removed+=1
                    os.remove(marker)
                except OSError:pass
    return removed

def _apply_legacy_ability_overrides(root,hero,av,z,arc,lmembers,tmp):
    """Overlay ONLY historical cosmetic AltN fields onto pristine CURRENT ability entities.

    This fixes charged/state visuals reverting to the default Reborn hero while preserving
    every current gameplay/balance field (damage, mana, cooldown, targeting, etc.).
    """
    _clear_managed_ability_overrides(root,hero)
    blocks=_legacy_entity_blocks(hero,av,z,lmembers,tmp)
    blocks += _legacy_ability_modifier_blocks(hero,av,z,lmembers,tmp)
    written=0
    for legacy_mem,attrs in blocks:
        target_modifier=attrs.get('__modifier_key')
        attrs={k:v for k,v in attrs.items() if k in ABILITY_COSMETIC_ATTRS and v}
        if not attrs:continue
        curmem=_current_ability_member(hero,legacy_mem)
        if not curmem:
            diag(root,f"ABILITY_OVERLAY_SKIP no_current legacy={legacy_mem}");continue
        stage=os.path.join(tmp,"ability_current",hero["folder"],str(abs(hash(curmem))))
        os.makedirs(stage,exist_ok=True)
        src=extract_member(z,arc,curmem,stage)
        if not src or not os.path.isfile(src):
            diag(root,f"ABILITY_OVERLAY_SKIP extract_failed current={curmem}");continue
        try:text=read_text(src)
        except Exception:
            diag(root,f"ABILITY_OVERLAY_SKIP unreadable current={curmem}");continue
        if not re.search(r'<\s*[A-Za-z_][A-Za-z0-9_.:-]*\b',text):
            diag(root,f"ABILITY_OVERLAY_SKIP nontext current={curmem}");continue
        changed=0
        # Runtime path mirrors the CURRENT archive member beneath heroes/<modern>/.
        cm=curmem.replace("\\","/").strip("/")
        mm=re.search(r'(?:^|/)heroes/[^/]+/(.*)$',cm,re.I)
        if not mm:continue
        tail=mm.group(1)
        out=os.path.join(switcher_root(root),"heroes",hero["folder"],*tail.split('/'))
        # Several historical cosmetic blocks can target the same current
        # ability entity. Continue from the file written by an earlier block
        # in this pass so a nested state overlay does not erase a root overlay.
        managed_out=out+'.onepunch_ability_managed'
        if os.path.isfile(managed_out) and os.path.isfile(out):
            try:text=read_text(out)
            except OSError:pass
        # Direct altavatar fields patch the current ability root. Nested
        # modifier fields patch the matching current modifier while leaving
        # all historical gameplay actions untouched.
        if target_modifier:
            tagm=re.search(
                r'<\s*modifier\b(?=[^>]*\bkey\s*=\s*"'
                + re.escape(target_modifier) + r'"\s)[^>]*>',
                text, re.I | re.S)
        else:
            tagm=re.search(r'<\s*([A-Za-z_][A-Za-z0-9_.:-]*)\b[^>]*>',text,re.S)
        if not tagm:continue
        tag=tagm.group(0)
        for k,v in attrs.items():
            nv=_rewrite_ability_cosmetic_ref(v,hero,av,legacy_mem,root)
                        # Include the physical asset referenced by this historical
            # ability cosmetic override. The resolver handles:
            #   relative legacy paths
            #   TGA/PNG -> DDS
            #   WAV <-> OGG
            #   numbered texture namespaces
            _copy_legacy_logical_asset(
                root,
                nv,
                owner_logical=legacy_mem
            )
            pat=re.compile(r'(\b'+re.escape(k)+r'\s*=\s*")[^"]*(")',re.I)
            if pat.search(tag):tag=pat.sub(lambda m:m.group(1)+nv+m.group(2),tag,count=1)
            else:tag=tag[:-1]+f' {k}="{nv}">'
            changed+=1
        text=text[:tagm.start()]+tag+text[tagm.end():]
        os.makedirs(os.path.dirname(out),exist_ok=True)
        write_text(out,text);write_text(out+'.onepunch_ability_managed','managed by One Punch Mod v1.41 Arena\n')
        written+=1
        diag(root,f"ABILITY_OVERLAY current={curmem} legacy={legacy_mem} out={out} attrs={attrs}")
    diag(root,f"ABILITY_OVERLAY_DONE hero={hero['folder']} avatar={av} files={written}")
    return written

def _extract_avatar_named_dependencies(root,hero,av,z,larcs,lmembers):
    """Copy hero-scoped files whose basename/path explicitly names this AltN.
    Old HoN often keeps avatar ability effects/icons outside heroes/<hero>/<alt>/.
    """
    lf=(hero.get("legacy_folder") or hero["folder"]).lower(); modern=hero["folder"].lower()
    stage=tempfile.mkdtemp(prefix="hon_altdeps_v127_"); copied=0
    try:
        for arc in larcs:
            wanted=[]
            for mem in lmembers.get(arc,[]):
                low=mem.lower().replace("\\","/").strip("/")
                if not low.startswith(f"heroes/{lf}/"): continue
                ext=os.path.splitext(low)[1]
                if ext not in SAFE_VISUAL_EXTS: continue
                tail=low[len(f"heroes/{lf}/"):]
                # e.g. ability_04/effects/cast_alt7.effect, icon_alt7.tga
                if re.search(r'(^|[/_.-])'+re.escape(av.lower())+r'([/_.-]|$)',tail): wanted.append(mem)
            if not wanted: continue
            for i in range(0,len(wanted),100):
                _run_hidden([z,"x","-y",f"-o{stage}",arc]+wanted[i:i+100],capture_output=True,text=True,errors="replace",timeout=240)
            for dp,_,fs in os.walk(stage):
                norm=dp.replace("\\","/").lower(); marker=f"/heroes/{lf}"
                pos=norm.rfind(marker)
                if pos<0: continue
                rel=dp.replace("\\","/")[pos+len(marker):].lstrip("/")
                for fn in fs:
                    src=os.path.join(dp,fn)
                    for hero_folder in {lf,modern}:
                        dst=os.path.join(switcher_root(root),"heroes",hero_folder,*rel.split("/"),fn)
                        os.makedirs(os.path.dirname(dst),exist_ok=True);shutil.copy2(src,dst)
                    copied+=1
            shutil.rmtree(stage,ignore_errors=True);os.makedirs(stage,exist_ok=True)
    finally: shutil.rmtree(stage,ignore_errors=True)
    return copied

def _find_preview_voice(root,hero,av,oldattrs):
    """Resolve the avatar's own selection/flavour line to one physical audio file."""
    if av not in hero.get("legacy",[]): return None
    import glob
    for key in ("selectedflavorsound","selectedsound","confirmmovesound"):
        ref=oldattrs.get(key)
        if not ref: continue
        raw=ref.replace("\\","/").lstrip("./")
        if raw.lower().startswith(av.lower()+"/"): raw=raw[len(av)+1:]
        for base in (legacy_dest(root,hero,av),legacy_mirror_dest(root,hero,av)):
            q=os.path.join(base,*raw.split("/")); stem,ext=os.path.splitext(q)
            variants=[q]
            if ext.lower()==".wav":variants.append(stem+".ogg")
            elif ext.lower()==".ogg":variants.append(stem+".wav")
            for v in variants:
                hits=glob.glob(glob.escape(v).replace("%","*")) if "%" in v else ([v] if os.path.isfile(v) else [])
                hits=[x for x in hits if os.path.isfile(x)]
                if hits:return sorted(hits)[0]
    return None

def _select_flavour_debug(root,message):
    """Append voice diagnostics to the log the user can inspect directly."""
    try:
        path=os.path.join(one_punch_root(root),"Logs","select_flavour_debug.log")
        os.makedirs(os.path.dirname(path),exist_ok=True)
        with open(path,"a",encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S")+" | "+str(message)+"\n")
    except Exception:
        pass

def _find_select_flavour_voice(root,hero,av,oldattrs=None):
    """Find the random flavour line belonging to a historical avatar.

    These files are normally stored at ``<avatar>/sounds/voice``.  Search the
    extracted source first, then the prepared and runtime copies so this also
    works in the public runtime where LegacyAssets is absent.  The physical
    package may differ from the logical avatar key (Trophy skins are one
    example), so both names are considered.
    """
    if av not in hero.get("legacy",[]):
        diag(root,f"VOICE_SELECT_SCAN_SKIP hero={hero.get('folder')} avatar={av} reason=not_legacy")
        _select_flavour_debug(root,f"VOICE_SELECT_SCAN_SKIP hero={hero.get('folder')} avatar={av} reason=not_legacy")
        return None
    oldattrs = oldattrs or (hero.get("legacy_info") or {}).get(av,{})
    physical = _legacy_avatar_physical_root(av,oldattrs).replace("\\","/").strip("/")
    logical = av.lower()
    physical = physical.lower()
    hero_names=[]
    for value in ((hero.get("legacy_folder") or hero["folder"]), hero["folder"]):
        value=str(value).lower()
        if value not in hero_names: hero_names.append(value)
    avatar_names=[]
    for value in (logical,physical):
        if value and value not in avatar_names: avatar_names.append(value)
    roots=[legacy_assets_root(root),prepared_root(root),switcher_root(root)]
    voice_dirs=[]
    for asset_root in roots:
        for namespace in (None,"00000000","00000003","00000005"):
            namespace_root=asset_root if namespace is None else os.path.join(asset_root,namespace)
            for hero_name in hero_names:
                for avatar_name in avatar_names:
                    base=os.path.join(namespace_root,"heroes",hero_name,*avatar_name.split("/"))
                    for voice_name in (os.path.join("sounds","voice"),"voice"):
                        voice_dirs.append(os.path.join(base,voice_name))
    candidates=[];seen=set();existing_dirs=0
    for voice_dir in voice_dirs:
        if not os.path.isdir(voice_dir): continue
        existing_dirs += 1
        try: entries=os.listdir(voice_dir)
        except OSError: continue
        for name in entries:
            low=name.lower()
            if not low.startswith("select_flavour") or not low.endswith((".ogg",".wav")):
                continue
            path=os.path.join(voice_dir,name)
            if not os.path.isfile(path): continue
            key=os.path.normcase(os.path.abspath(path))
            if key not in seen:
                seen.add(key);candidates.append(path)
    selected=random.choice(candidates) if candidates else None
    diag(root,
         f"VOICE_SELECT_SCAN hero={hero.get('folder')} avatar={av} physical={physical or '<none>'} "
         f"dirs={existing_dirs} candidates={len(candidates)} selected={selected or '<none>'}")
    _select_flavour_debug(root,
         f"VOICE_SELECT_SCAN hero={hero.get('folder')} avatar={av} physical={physical or '<none>'} "
         f"dirs={existing_dirs} candidates={len(candidates)} selected={selected or '<none>'}")
    return selected

def _stop_current_avatar_voice():
    global _active_voice_stop,_active_voice_process
    with _voice_state_lock:
        if _active_voice_stop is not None:
            _active_voice_stop.set()
        process=_active_voice_process
        _active_voice_process=None
    if process is not None:
        try:
            if process.poll() is None:process.terminate()
        except Exception:pass

def _play_avatar_voice_wpf(path,debug_root,stop_event=None):
    """Fallback player retained for systems where the HoN FMOD DLL is unavailable."""
    script=os.path.join(os.path.dirname(__file__),"tools","play_avatar_voice.ps1")
    log_file=os.path.join(one_punch_root(debug_root),"Logs","select_flavour_debug.log")
    if not os.path.isfile(script):
        _select_flavour_debug(debug_root,f"VOICE_WPF_SKIP path={path} reason=player_script_missing")
        return
    if stop_event is not None and stop_event.is_set():
        _select_flavour_debug(debug_root,f"VOICE_WPF_SKIP path={path} reason=stopped_before_spawn")
        return
    args=["powershell.exe","-NoProfile","-WindowStyle","Hidden","-ExecutionPolicy","Bypass",
          "-File",script,"-Path",os.path.abspath(path),"-LogPath",log_file]
    try:
        process=subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        global _active_voice_process
        with _voice_state_lock:_active_voice_process=process
        _select_flavour_debug(debug_root,f"VOICE_WPF_SPAWNED path={path}")
    except Exception as ex:
        _select_flavour_debug(debug_root,f"VOICE_WPF_ERROR path={path} error={ex}")

def _fmod_voice_worker(path,debug_root,stop_event):
    """Play OGG with the FMOD runtime shipped alongside HoN."""
    try:
        import ctypes
        dll_path=os.path.join(debug_root,"bin","fmod.dll")
        if not os.path.isfile(dll_path):
            _select_flavour_debug(debug_root,f"VOICE_FMOD_SKIP path={path} reason=dll_missing dll={dll_path}")
            _play_avatar_voice_wpf(path,debug_root,stop_event)
            return
        dll=ctypes.WinDLL(dll_path)
        pointer=ctypes.c_void_p
        system=pointer()
        dll.FMOD_System_Create.argtypes=[ctypes.POINTER(pointer),ctypes.c_uint]
        dll.FMOD_System_Create.restype=ctypes.c_int
        result=dll.FMOD_System_Create(ctypes.byref(system),0x00020214)
        _select_flavour_debug(debug_root,f"VOICE_FMOD_CREATE result={result}")
        if result != 0 or not system.value:
            _play_avatar_voice_wpf(path,debug_root,stop_event)
            return
        sound=pointer();channel=pointer()
        dll.FMOD_System_Init.argtypes=[pointer,ctypes.c_int,ctypes.c_uint,pointer]
        dll.FMOD_System_Init.restype=ctypes.c_int
        result=dll.FMOD_System_Init(system,32,0,None)
        _select_flavour_debug(debug_root,f"VOICE_FMOD_INIT result={result}")
        if result != 0: return
        if stop_event.is_set(): return
        dll.FMOD_System_CreateSound.argtypes=[pointer,ctypes.c_char_p,ctypes.c_uint,pointer,ctypes.POINTER(pointer)]
        dll.FMOD_System_CreateSound.restype=ctypes.c_int
        result=dll.FMOD_System_CreateSound(system,os.fsencode(path),0,None,ctypes.byref(sound))
        _select_flavour_debug(debug_root,f"VOICE_FMOD_CREATE_SOUND result={result} path={path}")
        if result != 0 or not sound.value: return
        if stop_event.is_set(): return
        dll.FMOD_System_PlaySound.argtypes=[pointer,pointer,pointer,ctypes.c_int,ctypes.POINTER(pointer)]
        dll.FMOD_System_PlaySound.restype=ctypes.c_int
        result=dll.FMOD_System_PlaySound(system,sound,None,0,ctypes.byref(channel))
        _select_flavour_debug(debug_root,f"VOICE_FMOD_PLAY result={result}")
        if result != 0 or not channel.value: return
        dll.FMOD_Channel_Stop.argtypes=[pointer];dll.FMOD_Channel_Stop.restype=ctypes.c_int
        dll.FMOD_System_Update.argtypes=[pointer];dll.FMOD_System_Update.restype=ctypes.c_int
        dll.FMOD_Channel_IsPlaying.argtypes=[pointer,ctypes.POINTER(ctypes.c_int)]
        dll.FMOD_Channel_IsPlaying.restype=ctypes.c_int
        playing=ctypes.c_int(1)
        elapsed=0
        while playing.value and elapsed < 15000 and not stop_event.is_set():
            dll.FMOD_System_Update(system)
            dll.FMOD_Channel_IsPlaying(channel,ctypes.byref(playing))
            time.sleep(.05);elapsed += 50
        if stop_event.is_set():
            dll.FMOD_Channel_Stop(channel)
            _select_flavour_debug(debug_root,f"VOICE_FMOD_STOPPED elapsed_ms={elapsed}")
        else:
            _select_flavour_debug(debug_root,
                                  f"VOICE_FMOD_END playing={playing.value} elapsed_ms={elapsed}")
    except Exception as ex:
        _select_flavour_debug(debug_root,f"VOICE_FMOD_ERROR path={path} error={ex}")
        _play_avatar_voice_wpf(path,debug_root,stop_event)
    finally:
        try:
            if 'sound' in locals() and sound.value: dll.FMOD_Sound_Release(sound)
            if 'system' in locals() and system.value:
                dll.FMOD_System_Close(system);dll.FMOD_System_Release(system)
        except Exception as ex:
            _select_flavour_debug(debug_root,f"VOICE_FMOD_CLEANUP_ERROR error={ex}")
        with _voice_state_lock:
            global _active_voice_stop
            if _active_voice_stop is stop_event:_active_voice_stop=None

def play_avatar_voice(path,debug_root=None):
    """Launch asynchronous FMOD playback for one selected avatar voice line."""
    if not path:
        if debug_root: diag(debug_root,"VOICE_PLAY_SKIP reason=no_path")
        return
    if not os.path.isfile(path):
        if debug_root: diag(debug_root,f"VOICE_PLAY_SKIP path={path} reason=file_missing")
        return
    _stop_current_avatar_voice()
    if debug_root:
        _select_flavour_debug(debug_root,f"VOICE_PLAY_CALL path={path} backend=fmod dll={os.path.join(debug_root,'bin','fmod.dll')}")
    if not debug_root:
        return
    stop_event=threading.Event()
    global _active_voice_stop
    with _voice_state_lock:_active_voice_stop=stop_event
    threading.Thread(target=_fmod_voice_worker,args=(path,debug_root,stop_event),daemon=True,
                     name="one-punch-select-flavour").start()

def prepared_root(root):
    return os.path.join(one_punch_root(root),"PreparedAssets")

def _prepared_hero_dir(root,hero):
    return os.path.join(prepared_root(root),"heroes",hero["folder"].lower())

def _prepared_recipe_dir(root,hero,av):
    return os.path.join(prepared_root(root),"recipes",hero["folder"].lower(),av.lower())

def _prepared_avatar_available(root,hero,av):
    """Return True only when the packaged legacy avatar can be installed safely."""
    src_hero=_prepared_hero_dir(root,hero)
    src_recipe=_prepared_recipe_dir(root,hero,av)
    recipe_path=os.path.join(src_recipe,"recipe.json")
    if not os.path.isdir(src_hero) or not os.path.isfile(recipe_path):
        return False
    try:
        data=json.load(open(recipe_path,"r",encoding="utf-8"))
        files=data.get("files") or []
    except (OSError,ValueError,TypeError):
        return False
    if not files:
        return False
    for rel in files:
        rel=str(rel).replace("\\","/").lstrip("/")
        if not os.path.isfile(os.path.join(src_recipe,"files",*rel.split("/"))):
            return False

    # A declared historical avatar is usable only when its prepared package
    # contains the model that makes the avatar physically real.
    oldattrs=(hero.get("legacy_info") or {}).get(av,{})
    physical=_legacy_avatar_physical_root(av,oldattrs)
    model_candidates=[
        os.path.join(src_hero,*physical.split("/"),"model.mdf"),
        os.path.join(src_hero,av.lower(),"model.mdf"),
    ]
    model_ref=str(oldattrs.get("model") or "").replace("\\","/").strip().lstrip("/")
    if model_ref:
        model_candidates.extend([
            os.path.join(src_hero,*model_ref.split("/")),
            os.path.join(src_hero,*physical.split("/"),os.path.basename(model_ref)),
            os.path.join(src_hero,os.path.basename(model_ref)),
        ])
    return any(os.path.isfile(p) for p in model_candidates)


def prepared_avatar_warning(root, hero, av):
    """Return a user-facing warning when a prepared avatar may fall back."""
    if av == "default" or av not in hero.get("legacy", set()):
        return ""
    if not _prepared_avatar_available(root, hero, av):
        return "Prepared package is incomplete; this avatar may fall back."

    recipe_dir = _prepared_recipe_dir(root, hero, av)
    manifest_path = _prepared_manifest_path(root, hero, av)
    if os.path.isfile(manifest_path):
        try:
            manifest = json.load(open(manifest_path, "r", encoding="utf-8"))
            unresolved = len(manifest.get("unresolved") or [])
            if manifest.get("status") != "clean" and unresolved:
                return f"{unresolved} asset reference(s) need review; test before playing."
        except (OSError, ValueError, TypeError):
            return "Prepared validation report is unreadable."

    files_root = os.path.join(recipe_dir, "files")
    entity_path = os.path.join(
        files_root, "heroes", hero["folder"].lower(), "base", "hero.entity"
    )
    if not os.path.isfile(entity_path):
        return "Generated hero definition is missing."
    try:
        entity = read_text(entity_path)
    except OSError:
        return "Generated hero definition cannot be read."

    model_match = re.search(r"\bmodel\s*=\s*\"([^\"]+)\"", entity, re.I)
    if not model_match:
        return "Generated hero definition has no model."
    ref = model_match.group(1).replace("\\", "/")
    if ref.startswith("/"):
        candidate = os.path.join(prepared_root(root), *ref.lstrip("/").split("/"))
    else:
        candidate = os.path.normpath(os.path.join(os.path.dirname(entity_path), ref))
    if not os.path.isfile(candidate):
        return f"Model file is missing: {ref}"
    return ""

def _legacy_source_avatar_available(root,hero,av):
    """Check the developer-only extracted source for a real avatar model."""
    if not os.path.isdir(legacy_assets_root(root)):
        return False
    lf=(hero.get("legacy_folder") or hero["folder"]).lower()
    oldattrs=(hero.get("legacy_info") or {}).get(av,{})
    model_ref=str(oldattrs.get("model") or "").replace("\\","/").strip()
    refs=[]
    if model_ref:
        refs.append((model_ref,f"heroes/{lf}/hero.entity"))
    physical=_legacy_avatar_physical_root(av,oldattrs)
    refs.extend([
        (f"heroes/{lf}/{physical}/model.mdf",None),
        (f"heroes/{lf}/base/{physical}/model.mdf",None),
    ])
    return any(_resolve_legacy_logical_path(root,ref,owner) for ref,owner in refs)

def _filter_legacy_inventory(root,heroes):
    """Keep declarations only when a prepared package or developer source exists."""
    for hero in heroes:
        declared=set(hero.get("legacy") or set())
        available={
            av for av in declared
            if _prepared_avatar_available(root,hero,av)
            or _legacy_source_avatar_available(root,hero,av)
        }
        hero["unavailable_legacy"]=sorted(declared-available,key=avatar_sort)
        hero["legacy"]=available
        hero["avatars"]=sorted(set(hero.get("reborn") or {"default"})|available,key=avatar_sort)
    return heroes

def _prepared_external_dependencies(root,source_roots,modern,legacy):
    """Find copied assets under other hero namespaces referenced by this package."""
    deps=set()
    skip={modern.lower(),legacy.lower()}
    for source_root in source_roots:
        if os.path.isfile(source_root):
            entries=[(os.path.dirname(source_root),[],[os.path.basename(source_root)])]
        elif os.path.isdir(source_root):
            entries=os.walk(source_root)
        else:
            continue
        for dp,_,files in entries:
            for fn in files:
                if os.path.splitext(fn)[1].lower() not in LEGACY_TEXT_EXTS:
                    continue
                path=os.path.join(dp,fn)
                try:text=read_text(path)
                except Exception:continue
                for match in LEGACY_REF_RE.finditer(' '+text):
                    logical=_logical_norm(match.group(1))
                    parts=logical.split('/')
                    if len(parts)<3 or parts[0] != 'heroes' or parts[1] in skip:
                        continue
                    candidates=[logical]
                    stem,ext=os.path.splitext(logical)
                    if ext.lower() in ('.tga','.png') and os.path.basename(stem).lower()=='normal':
                        candidates.extend([stem+'_rxgb.dds',stem+'_s.dds'])
                    for candidate in candidates:
                        source=os.path.join(switcher_root(root),*candidate.split('/'))
                        if os.path.isfile(source):
                            deps.add(candidate)
    return sorted(deps)


def _publish_prepared_avatar(root,hero,av):
    """Build-time/export step.

    Publish both:
      1. the modern Reborn hero Runtime tree (generated entities/overrides)
      2. the legacy hero asset tree referenced by those generated entities

    Runtime references may intentionally point at the historical hero folder
    (for example /heroes/ra/alt5/...), so that tree must be shipped too.
    """
    runtime_heroes = os.path.join(switcher_root(root), "heroes")
    modern = hero["folder"].lower()
    legacy = (hero.get("legacy_folder") or hero["folder"]).lower()

    src_modern = os.path.join(runtime_heroes, modern)
    src_recipe = _recipe_dir(root, hero, av)

    if not os.path.isdir(src_modern) or not os.path.isfile(
        os.path.join(src_recipe, "recipe.json")
    ):
        return False

    # Modern Reborn-compatible tree.
    #
    # IMPORTANT:
    # Runtime may also contain historical monolithic .entity files copied
    # while resolving cosmetic dependencies. Those are SOURCE material only.
    # Publishing them can shadow/conflict with the generated Reborn base/*
    # entities (Accursed Alt7 exposed this).
    #
    # Publish all physical assets, but for .entity files keep only the
    # generated Reborn-compatible base/* tree.
    dst_modern = os.path.join(prepared_root(root), "heroes", modern)
    if os.path.isdir(dst_modern):
        shutil.rmtree(dst_modern, ignore_errors=True)

    selected_names=set()
    selected_attrs=(hero.get('legacy_info') or {}).get(av,{})
    for key,value in selected_attrs.items():
        if key.lower() in {'attackprojectile','projectile','projectilemodel'}:
            value=str(value).strip().lower()
            if value and '/' not in value and '\\' not in value:
                selected_names.add(value)

    # Some historical hero metadata does not expose attackprojectile in the
    # cached legacy modifier attributes even though the generated recipe does.
    # Read the recipe itself so avatar-local named projectile definitions are
    # retained in PreparedAssets (Flint Spellslinger is one example).
    recipe_files_root=os.path.join(src_recipe,"files")
    if os.path.isdir(recipe_files_root):
        for recipe_dp,_,recipe_files in os.walk(recipe_files_root):
            for recipe_fn in recipe_files:
                if os.path.splitext(recipe_fn)[1].lower() not in LEGACY_TEXT_EXTS:
                    continue
                try: recipe_text=read_text(os.path.join(recipe_dp,recipe_fn))
                except OSError: continue
                for pattern in (
                    r'(?i)\b(?:attackprojectile|projectile|projectilemodel)\s*=\s*"([^"/]+)"',
                    r'(?i)\b(?:setattackprojectile|spawnprojectile)\s+name\s*=\s*"([^"/]+)"',
                ):
                    for match in re.finditer(pattern,recipe_text):
                        selected_names.add(match.group(1).strip().lower())

    # Named projectile definitions are gameplay dependencies even though they
    # are not visual files. The bounded legacy copier skips .entity files, so
    # recover only the named entities selected by the generated hero recipe.
    # Deconstructor/Tempest is the important case: its attackprojectile is
    # Projectile_TempestAttack_Alt2 and the definition lives below the avatar.
    if selected_names:
        legacy_root = os.path.join(
            legacy_assets_root(root), "heroes", legacy, av.lower()
        )
        selected_attrs = (hero.get("legacy_info") or {}).get(av, {})
        physical = _legacy_avatar_physical_root(av, selected_attrs)
        source_roots = [legacy_root]
        if physical and physical.lower() != av.lower():
            source_roots.append(
                os.path.join(
                    legacy_assets_root(root), "heroes", legacy,
                    physical.replace("/", os.sep),
                )
            )
        for source_root in source_roots:
            if not os.path.isdir(source_root):
                continue
            for dp, _, files in os.walk(source_root):
                for fn in files:
                    if not fn.lower().endswith(".entity"):
                        continue
                    source = os.path.join(dp, fn)
                    try:
                        entity_text = read_text(source)
                    except OSError:
                        continue
                    named = re.search(
                        r'<\s*[A-Za-z_][A-Za-z0-9_.:-]*\b[^>]*\bname\s*=\s*"([^"]+)"',
                        entity_text, re.I | re.S,
                    )
                    if not named or named.group(1).strip().lower() not in selected_names:
                        continue
                    rel = os.path.relpath(source, source_root)
                    destination = os.path.join(src_modern, av.lower(), rel)
                    os.makedirs(os.path.dirname(destination), exist_ok=True)
                    shutil.copy2(source, destination)
                    diag(
                        root,
                        f"NAMED_ENTITY_RESTORED hero={modern} avatar={av} "
                        f"name={named.group(1).strip()} path={rel.replace(os.sep, '/')}",
                    )

    for dp, dirs, files in os.walk(src_modern):
        rel_dir = os.path.relpath(dp, src_modern)
        rel_norm = "" if rel_dir == "." else rel_dir.replace("\\", "/")
        out_dir = os.path.join(dst_modern, rel_dir) if rel_dir != "." else dst_modern

        for fn in files:
            rel_file = (rel_norm + "/" + fn).lstrip("/")
            low = rel_file.lower()

            if low.endswith(".entity") and not low.startswith("base/"):
                # Keep only a selected avatar-local named dependency, such as
                # Forsaken Archer's Clockwork Archer projectile definition.
                # Other historical entity files remain source-only.
                is_projectile_entity = "/projectile/" in ("/" + low)
                if not selected_names or (
                    not rel_file.lower().startswith(av.lower()+"/")
                    and not is_projectile_entity
                ):
                    continue
                try:entity_text=read_text(os.path.join(dp,fn))
                except OSError:continue
                named=re.search(r'<\s*[A-Za-z_][A-Za-z0-9_.:-]*\b[^>]*\bname\s*=\s*"([^"]+)"',entity_text,re.I|re.S)
                named_key = named.group(1).strip().lower() if named else ""
                # PreparedAssets/heroes/<hero> is a shared union of all
                # avatars. Keep every avatar-local projectile definition so a
                # later avatar publish cannot delete an earlier alt's attack.
                if not named or (named_key not in selected_names and not is_projectile_entity):
                    continue

            src = os.path.join(dp, fn)
            dst = os.path.join(out_dir, fn)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)

    # Historical cosmetic asset tree, when the old and modern hero folder
    # names differ (e.g. ra -> amun_ra).
    if legacy != modern:
        src_legacy = os.path.join(runtime_heroes, legacy)

        if os.path.isdir(src_legacy):
            dst_legacy = os.path.join(prepared_root(root), "heroes", legacy)
            os.makedirs(os.path.dirname(dst_legacy), exist_ok=True)
            shutil.copytree(src_legacy, dst_legacy, dirs_exist_ok=True)

    # Preserve a small set of copied assets referenced from another hero
    # namespace, such as a legacy sword effect reusing Hiro's normal map.
    try:
        recipe_data=json.load(open(os.path.join(src_recipe,"recipe.json"),"r",encoding="utf-8"))
    except (OSError,ValueError,TypeError):
        recipe_data={}
    dependency_roots=[
        os.path.join(src_modern,av.lower()),
        os.path.join(runtime_heroes,legacy,av.lower()),
    ]
    for rel in recipe_data.get("files") or []:
        q=os.path.join(switcher_root(root),*str(rel).replace("\\","/").split("/"))
        if os.path.isfile(q):dependency_roots.append(q)
    dependencies=_prepared_external_dependencies(root,dependency_roots,modern,legacy)
    for rel in dependencies:
        src=os.path.join(switcher_root(root),*rel.split('/'))
        dst=os.path.join(prepared_root(root),*rel.split('/'))
        if os.path.isfile(src):
            os.makedirs(os.path.dirname(dst),exist_ok=True)
            shutil.copy2(src,dst)

    # Tiny activation recipe.
    dst_recipe = _prepared_recipe_dir(root, hero, av)
    if os.path.isdir(dst_recipe):
        shutil.rmtree(dst_recipe, ignore_errors=True)

    shutil.copytree(src_recipe, dst_recipe)
    recipe_path=os.path.join(dst_recipe,"recipe.json")
    try:
        recipe=json.load(open(recipe_path,"r",encoding="utf-8"))
        recipe["dependencies"]=dependencies
        with open(recipe_path,"w",encoding="utf-8") as f:
            json.dump(recipe,f,indent=2)
    except (OSError,ValueError,TypeError):
        pass

    diag(
        root,
        f"PREPARED_PUBLISH hero={hero['folder']} legacy={legacy} avatar={av}"
    )
    return True

def _install_prepared_avatar(root,hero,av):
    """End-user fast path: install already-normalized files; no LegacyAssets scanning/parsing."""
    src_hero=_prepared_hero_dir(root,hero)
    src_recipe=_prepared_recipe_dir(root,hero,av)
    if not os.path.isdir(src_hero) or not os.path.isfile(os.path.join(src_recipe,"recipe.json")):
        return False
    t=time.time()
    dst_hero=os.path.join(switcher_root(root),"heroes",hero["folder"])
    os.makedirs(os.path.dirname(dst_hero),exist_ok=True)
    shutil.copytree(src_hero,dst_hero,dirs_exist_ok=True)
    legacy=(hero.get("legacy_folder") or hero["folder"]).lower()
    if legacy != hero["folder"].lower():
        src_legacy=os.path.join(prepared_root(root),"heroes",legacy)
        if os.path.isdir(src_legacy):
            shutil.copytree(
                src_legacy,
                os.path.join(switcher_root(root),"heroes",legacy),
                dirs_exist_ok=True,
            )
    try:
        recipe=json.load(open(os.path.join(src_recipe,"recipe.json"),"r",encoding="utf-8"))
    except (OSError,ValueError,TypeError):
        recipe={}
    for rel in recipe.get("dependencies") or []:
        rel=str(rel).replace("\\","/").lstrip("/")
        src=os.path.join(prepared_root(root),*rel.split('/'))
        dst=os.path.join(switcher_root(root),*rel.split('/'))
        if not os.path.isfile(src):
            return False
        os.makedirs(os.path.dirname(dst),exist_ok=True)
        shutil.copy2(src,dst)
    _repair_relative_texture_references(root,hero,av)
    _repair_avatar_morph_models(root,hero,av)
    _repair_missing_animation_clips(root,hero,av)
    _repair_network_animation_slots(root,hero,av)
    dst_recipe=_recipe_dir(root,hero,av)
    if os.path.isdir(dst_recipe):shutil.rmtree(dst_recipe,ignore_errors=True)
    shutil.copytree(src_recipe,dst_recipe)
    diag(root,f"PREPARED_INSTALL hero={hero['folder']} avatar={av} seconds={time.time()-t:.3f}")
    return _restore_selection_recipe(root,hero,av)

def _recipe_dir(root,hero,av):
    return os.path.join(cache_dir(root),"SelectionRecipes",hero["folder"].lower(),av.lower())

def _recipe_manifest(root,hero,av):
    return os.path.join(_recipe_dir(root,hero,av),"recipe.json")

def _save_selection_recipe(root,hero,av,target):
    """Cache only tiny generated entity overrides. Avatar assets stay installed in Runtime."""
    rd=_recipe_dir(root,hero,av)
    if os.path.isdir(rd):shutil.rmtree(rd,ignore_errors=True)
    os.makedirs(rd,exist_ok=True)
    files=[]
    if os.path.isfile(target):
        rel=os.path.relpath(target,switcher_root(root)); dst=os.path.join(rd,"files",rel)
        os.makedirs(os.path.dirname(dst),exist_ok=True);shutil.copy2(target,dst);files.append(rel)
        marker=target+".hon_avatar_switcher_created"
        if os.path.isfile(marker):
            mrel=os.path.relpath(marker,switcher_root(root));md=os.path.join(rd,"files",mrel)
            os.makedirs(os.path.dirname(md),exist_ok=True);shutil.copy2(marker,md);files.append(mrel)
    base=os.path.join(switcher_root(root),"heroes",hero["folder"])
    if os.path.isdir(base):
        for dp,_,fs in os.walk(base):
            for fn in fs:
                if not fn.endswith('.onepunch_ability_managed'):continue
                marker=os.path.join(dp,fn);entity=marker[:-len('.onepunch_ability_managed')]
                for q in (entity,marker):
                    if not os.path.isfile(q):continue
                    rel=os.path.relpath(q,switcher_root(root));dst=os.path.join(rd,"files",rel)
                    os.makedirs(os.path.dirname(dst),exist_ok=True);shutil.copy2(q,dst);files.append(rel)
    with open(_recipe_manifest(root,hero,av),'w',encoding='utf-8') as f:
        json.dump({"version":1,"hero":hero["folder"],"avatar":av,"files":files},f,indent=2)
    diag(root,f"FAST_RECIPE_SAVE hero={hero['folder']} avatar={av} files={len(files)}")

def _restore_selection_recipe(root,hero,av):
    mf=_recipe_manifest(root,hero,av)
    if not os.path.isfile(mf):return False
    try:data=json.load(open(mf,'r',encoding='utf-8'))
    except Exception:return False
    files=data.get('files') or []
    if not files:return False
    # Assets are intentionally NOT removed. All installed avatars can coexist; only entity
    # overrides determine which avatar/state cosmetics are active.
    _clear_managed_ability_overrides(root,hero)
    rd=_recipe_dir(root,hero,av)
    for rel in files:
        src=os.path.join(rd,"files",rel);dst=os.path.join(switcher_root(root),rel)
        if not os.path.isfile(src):return False
        os.makedirs(os.path.dirname(dst),exist_ok=True);shutil.copy2(src,dst)
    _repair_generated_hero_entity_refs(root,hero,av)
    diag(root,f"FAST_RECIPE_RESTORE hero={hero['folder']} avatar={av} files={len(files)}")
    return True

AVATAR_VOICE_ATTRS=(
    "selectedsound","selectedflavorsound","confirmmovesound",
    "confirmattacksound","nomanasound","cooldownsound",
    "announcersound","tauntedsound","tauntkillsound",
)

def _avatar_voice_asset_bases(root,hero,av):
    """Return prepared/runtime roots where one avatar's voice package may live."""
    oldattrs=(hero.get("legacy_info") or {}).get(av,{})
    physical=_legacy_avatar_physical_root(av,oldattrs).replace("\\","/").strip("/") or av
    namespaces=[]
    for value in (hero.get("legacy_folder") or hero["folder"],hero["folder"]):
        value=str(value).lower()
        if value and value not in namespaces:namespaces.append(value)
    bases=[]
    seen=set()
    for layer in (switcher_root(root),prepared_root(root)):
        for namespace in namespaces:
            for folder in (physical.lower(),av.lower()):
                base=os.path.join(layer,"heroes",namespace,folder)
                key=os.path.abspath(base).lower()
                if os.path.isdir(base) and key not in seen:
                    seen.add(key);bases.append(base)
    return bases,physical.lower(),namespaces[0] if namespaces else hero["folder"].lower()

def _avatar_voice_tail(raw):
    value=str(raw or "").replace("\\","/")
    marker="sounds/voice/"
    pos=value.lower().rfind(marker)
    return value[pos+len(marker):].lstrip("/") if pos>=0 else ""

def _avatar_voice_file_exists(root,hero,av,tail):
    """Check a logical voice ref, including HoN's WAV-to-OGG packaging convention."""
    if not tail:return False
    import glob
    bases,_,_= _avatar_voice_asset_bases(root,hero,av)
    for base in bases:
        q=os.path.join(base,"sounds","voice",*tail.split("/"))
        stem,ext=os.path.splitext(q)
        variants=[q]
        if ext.lower()==".wav":variants.append(stem+".ogg")
        elif ext.lower()==".ogg":variants.append(stem+".wav")
        for candidate in variants:
            if "%" in candidate:
                if glob.glob(glob.escape(candidate).replace("%","*")):return True
            elif os.path.isfile(candidate):
                return True
    return False

def _rewrite_avatar_voice_refs(root,hero,av,text):
    """Point generated hero voice refs at the selected avatar's voice package."""
    if av not in hero.get("legacy",[]):return text,0
    bases,physical,namespace=_avatar_voice_asset_bases(root,hero,av)
    if not bases:return text,0
    changed=0
    def replace_tag(tag):
        nonlocal changed
        for attr in AVATAR_VOICE_ATTRS:
            pat=re.compile(r'(\b'+re.escape(attr)+r'\s*=\s*")([^"]*)(")',re.I)
            hit=pat.search(tag)
            if not hit:continue
            raw=hit.group(2);tail=_avatar_voice_tail(raw)
            if not tail or not _avatar_voice_file_exists(root,hero,av,tail):continue
            value=f"/heroes/{namespace}/{physical}/sounds/voice/{tail}"
            if value==raw:continue
            tag=tag[:hit.start(2)]+value+tag[hit.end(2):]
            changed+=1
        return tag
    return _transform_hero_root(text,replace_tag),changed

def _repair_generated_hero_entity_refs(root,hero,av):
    """Repair old prepared recipes that left avatar model refs relative to base/."""
    if av not in hero.get("legacy",[]):return 0
    target=override_path(root,hero)
    if not os.path.isfile(target):return 0
    try:text=read_text(target)
    except OSError:return 0
    changed=0
    attrs={"model","storemodel","icon","icon2","portrait","previewmodel"}
    def replace(match):
        nonlocal changed
        name,value,tail=match.group(1),match.group(2),match.group(3)
        if name.lower() not in attrs or not value or value.startswith("/"):
            return match.group(0)
        rewritten=_rewrite_old_asset_path(value,hero,av,root)
        if rewritten!=value:
            changed+=1
            return f'{name}="{rewritten}"{tail}'
        return match.group(0)
    text=re.sub(r'\b(model|storemodel|icon|icon2|portrait|previewmodel)\s*=\s*"([^"]*)"(\s*)',replace,text,flags=re.I)
    text,voice_changed=_rewrite_avatar_voice_refs(root,hero,av,text)
    changed+=voice_changed
    if not changed:return 0
    temporary=target+".new"
    write_text(temporary,text);os.replace(temporary,target)
    diag(root,f"PREPARED_ENTITY_REFS_REPAIRED hero={hero['folder']} avatar={av} changed={changed}")
    return changed

def _avatar_assets_already_installed(root,hero,av):
    """Cheap test: Runtime keeps avatar packages permanently after first installation."""
    d=legacy_dest(root,hero,av)
    return os.path.isfile(os.path.join(d,"model.mdf"))

def _transform_hero_root(text,transform):
    """Root avatar cosmetics must never overwrite state/level modifier fields."""
    match=re.search(r'<hero\b[^>]*>',text,re.I|re.S)
    if not match:raise ValueError('Missing hero root tag')
    return text[:match.start()]+transform(match.group(0))+text[match.end():]


HERO_MODIFIER_COSMETIC_ATTRS={
    'model','modelscale','preglobalscale','effectscale','passiveeffect','walkanim','infoheight',
    # Historical state modifiers can carry the active form's attack animation
    # and projectile presentation.  These are visual fields only; gameplay
    # attributes remain excluded from the overlay.
    'idleanim','attackanim','attacknumanims','attackprojectile','attackimpacteffect',
    'attackstarteffect','attackactioneffect'
}


def _modifier_cosmetic_aliases(hero,key):
    """Return current-style names for a historical avatar modifier key.

    Old entities commonly create keys such as ``malikenult_Alt9`` or
    ``prisoner_alt9_unbound`` while Reborn keeps the shared visual modifier as
    ``malikenult`` or ``unbound``.  Strip only an explicit avatar token so
    unrelated historical modifiers are never guessed together.
    """
    raw=str(key or '').strip()
    if not raw:return []
    low=raw.lower()
    aliases=[]
    def add(value):
        value=value.strip('_')
        if value and value not in aliases:aliases.append(value)
    add(low)
    # malikenult_Alt9, Unarmored_Alt5
    add(re.sub(r'_alt\d+(?=_|$)','',low))
    # prisoner_alt9_unbound and equivalent hero-prefixed keys
    lf=(hero.get('legacy_folder') or hero.get('folder') or '').lower()
    folder=(hero.get('folder') or '').lower()
    for prefix in {lf,folder}:
        if not prefix:continue
        add(re.sub(r'^'+re.escape(prefix)+r'_alt\d+_','',low))
        add(re.sub(r'^hero_'+re.escape(prefix)+r'_alt\d+_','',low))
    return aliases


def _legacy_hero_modifier_cosmetics(root,hero,av,z,lmembers,tmp,ability_blocks):
    """Discover direct avatar modifier cosmetics; never import historical actions/stats.

    Ability modifierkey lists may bind avatar-specific modifier names to the same
    level slots as the base modifierkey list. Use that explicit correspondence,
    not guessed hero names or suffixes. No ability modifier keys are changed.
    """
    import xml.etree.ElementTree as ET
    lf=(hero.get('legacy_folder') or hero['folder']).lower()
    owner=f'heroes/{lf}/hero.entity'
    try:entity=ET.fromstring(_legacy_name_source(root,owner,z,lmembers,tmp))
    except ET.ParseError:return {}
    selected=next((n for n in entity.findall('altavatar')
                   if n.get('key','').rsplit('.',1)[-1].lower()==av.lower()),None)
    if selected is None:return {}
    nested={n.get('key','').lower():n for n in selected.findall('modifier') if n.get('key')}
    bindings={key:key for key in nested}
    current_keys=set()
    current_entity=os.path.join(cache_dir(root),'entities',hero['folder'],'hero.entity')
    if os.path.isfile(current_entity):
        try:
            current_root=ET.parse(current_entity).getroot()
            current_keys={n.get('key','').lower() for n in current_root.findall('modifier') if n.get('key')}
        except (OSError,ET.ParseError):
            pass
    for member in dict.fromkeys(mem for mem,_ in ability_blocks):
        try:ability=ET.fromstring(_legacy_name_source(root,member,z,lmembers,tmp))
        except ET.ParseError:continue
        if ability.tag.lower()!='ability':continue
        basekeys=[k.strip().lower() for k in ability.get('modifierkey','').split(',') if k.strip()]
        if not basekeys:continue
        for alt in ability.findall('altavatar'):
            if alt.get('key','').rsplit('.',1)[-1].lower()!=av.lower():continue
            for attr,value in alt.attrib.items():
                if not re.fullmatch(r'modifierkey\d*',attr,re.I):continue
                keys=[k.strip().lower() for k in value.split(',')]
                if len(keys)!=len(basekeys):continue
                for base,key in zip(basekeys,keys):
                    if key in nested:bindings[base]=key
    out={}
    for key,source in bindings.items():
        attrs={k:v for k,v in nested[source].attrib.items() if k in HERO_MODIFIER_COSMETIC_ATTRS}
        for attr in ('model','passiveeffect','attackimpacteffect','attackstarteffect','attackactioneffect'):
            if attrs.get(attr):attrs[attr]=_rewrite_ability_cosmetic_ref(attrs[attr],hero,av,owner,root)
        if attrs:
            historical_key=nested[source].get('key') or key
            # Keep the historical key when it is useful for a current entity,
            # and also expose a narrowly derived shared-key alias.  The latter
            # is what makes temporary ability forms retain their avatar model.
            aliases=_modifier_cosmetic_aliases(hero,historical_key)
            matched=False
            for alias in aliases:
                if not current_keys or alias in current_keys:
                    out.setdefault(alias,dict(attrs));matched=True
            if not matched:
                # Preserve the previous exact-key behavior for current
                # entities that do not have a cached base document yet.
                out.setdefault(str(historical_key).lower(),dict(attrs))
        # Some historical skins create private push/pull modifier keys and
        # switch them from an onframe block. Reborn already has the shared
        # Flux-style state modifiers, so copy only the verified visual fields
        # onto the matching skin state. This preserves current gameplay and
        # prevents a state transition from resolving model.mdf from base.
        skin=(nested[source].get('skin') or '').lower()
        raw_nested_key=(nested[source].get('key') or '').lower()
        if attrs and raw_nested_key.startswith('flux_') and skin in ('push','pull'):
            shared='Fluxpush' if skin=='push' else 'Fluxpull'
            out.setdefault(shared,dict(attrs))
    return out

def _reborn_hero_modifier_cosmetics(hero,av,z,arc,tmp):
    """Read visual modifier fields from a current Reborn avatar sibling."""
    import xml.etree.ElementTree as ET
    folder=hero['folder'].lower()
    wanted=f"heroes/{folder}/{av.lower()}/hero.entity"
    member=next((p for p in hero.get('archive',{}).get('paths',[])
                 if p.replace('\\','/').lower().strip('/')==wanted),None)
    if not member:return {}
    path=extract_member(z,arc,member,tmp)
    if not path or not os.path.isfile(path):return {}
    try:entity=ET.parse(path).getroot()
    except (OSError,ET.ParseError):return {}
    out={}
    for node in entity.findall('modifier'):
        raw_key=(node.get('key') or '').strip()
        key=raw_key.lower()
        if not raw_key:continue
        attrs={k.lower():v for k,v in node.attrib.items()
               if k.lower() in HERO_MODIFIER_COSMETIC_ATTRS}
        for attr in ('model','passiveeffect'):
            value=attrs.get(attr)
            if not value:continue
            value=value.replace('\\','/').lstrip('./')
            if not value.startswith('/'):
                value=f"../{av.lower()}/{value}"
            attrs[attr]=value
        if attrs:out[raw_key]=attrs
    return out


def _overlay_hero_modifier_cosmetics(text,cosmetics,av=None):
    """Edit existing direct modifiers, including the current shared morph modifier."""
    from xml.sax.saxutils import escape
    depth=0
    normalized_cosmetics={str(key).lower():value for key,value in cosmetics.items()}
    avatar_model_fragment=(
        f"/{str(av or '').lower()}/ability_04/effects/ult_form/model.mdf"
        if av else ""
    )
    def replace(match):
        nonlocal depth
        tag=match.group(0)
        if tag.startswith(('<!--','<?','<!')):return tag
        if tag.startswith('</'):
            depth-=1
            return tag
        direct=depth==1
        if not tag.rstrip().endswith('/>'):depth+=1
        if not direct or not re.match(r'<modifier\b',tag,re.I):return tag
        current_attrs=_parse_attrs(tag)
        attrs=normalized_cosmetics.get(current_attrs.get('key','').lower(),{})
        if not attrs and avatar_model_fragment and re.search(r'\b(?:model|morphmodel)\s*=',tag,re.I):
            # Historical avatars often put the selected morph model in a
            # modifier named <base>_altN, while current Reborn keeps one shared
            # modifier such as hydromancer_rawrmode. Use only the selected
            # avatar's verified ult_form model as the cosmetic fallback.
            for candidate in cosmetics.values():
                model=str(candidate.get('model','')).lower()
                if avatar_model_fragment in model:
                    attrs=candidate
                    break
        for key,value in attrs.items():
            if key not in HERO_MODIFIER_COSMETIC_ATTRS:continue
            value=escape(value,{'"':'&quot;'})
            pattern=re.compile(r'(\b'+re.escape(key)+r'\s*=\s*")[^"]*(")',re.I)
            if pattern.search(tag):tag=pattern.sub(lambda m:m.group(1)+value+m.group(2),tag,count=1)
            else:tag=re.sub(r'(/?>)$',lambda m:f' {key}="{value}"'+m.group(1),tag)
        return tag
    text=re.sub(r'<!--.*?-->|<[^>]+>',replace,text,flags=re.S)
    # Current base entities may omit optional avatar form modifiers such as
    # Level_6/Level_11. Add only the selected avatar's visual fields.
    existing={m.group(1).lower() for m in re.finditer(
        r'<modifier\b[^>]*\bkey\s*=\s*"([^"]+)"',text,re.I|re.S)}
    missing=[]
    for key,attrs in cosmetics.items():
        if key.lower() in existing:continue
        visual={k:v for k,v in attrs.items() if k in HERO_MODIFIER_COSMETIC_ATTRS}
        if not visual:continue
        rendered=[f'\n\t<modifier key="{escape(key,{"\"":"&quot;"})}"']
        for attr,value in visual.items():
            rendered.append(f' {attr}="{escape(value,{"\"":"&quot;"})}"')
        rendered.append(' />')
        missing.append(''.join(rendered))
    if missing:
        text=re.sub(r'</hero>\s*$', ''.join(missing)+'\n</hero>', text,
                    count=1,flags=re.I|re.S)
    return text


def apply_avatar(root,hero,new,z,arc,tmp,larcs,lmembers,force_rebuild=False):
    target=override_path(root,hero)
    os.makedirs(os.path.dirname(target),exist_ok=True)

    if new=="default":
        _clear_managed_ability_overrides(root,hero)
        if os.path.isfile(target): os.remove(target)
        marker=target+".hon_avatar_switcher_created"
        if os.path.isfile(marker): os.remove(marker)
        return 1

    # FAST PATH: once an avatar has been built, switching is only a few tiny entity copies.
    # Models/textures/voices remain installed side-by-side in Runtime and are never recopied.
    if (
        not force_rebuild
        and new in hero["legacy"]
        and _avatar_assets_already_installed(root,hero,new)
        and _restore_selection_recipe(root,hero,new)
    ):
        return 0

    if (
        not force_rebuild
        and new in hero["legacy"]
        and not _prepared_avatar_available(root,hero,new)
        and not _legacy_source_avatar_available(root,hero,new)
    ):
        raise RuntimeError(
            f"{hero['name']} / {new} is unavailable: its PreparedAssets package is missing."
        )


    if new in hero["legacy"]:
        # PUBLIC/RELEASE FAST PATH: PreparedAssets contains the normalized build output.
        # No recursive dependency discovery is performed on the user's click.
        if not force_rebuild and _install_prepared_avatar(root,hero,new):            
            return 0


        # Developer fallback: prepare from source once when a prebuilt package is absent.
        # LegacyAssets is already an extracted source repository. Do NOT invoke 7-Zip or the
        # old archive extraction path. Install/normalize assets only when this avatar has not
        # already been installed into Runtime.
        if not _avatar_assets_already_installed(root,hero,new):
            t_install=time.time()
            install_attrs=legacy_modifier_attrs(hero,new,z,lmembers,tmp)
            normcount=_normalize_legacy_avatar_assets(root,hero,new,install_attrs)
            diag(root,f"INSTALL_LEGACY avatar={new} copied={normcount} seconds={time.time()-t_install:.3f}")
        else:
            diag(root,f"INSTALL_LEGACY_SKIP avatar={new} reason=runtime_assets_present")
        _suppress_legacy_body_shell(root,hero,new)
    elif new not in hero["reborn"]:
        raise RuntimeError("Avatar is neither installed Reborn content nor a verified legacy model.")

    # NEVER mutate the previous avatar entity. Always start from pristine Reborn.
    src=source_entity(hero,z,arc,tmp)
    # Build in memory first.  Do not overwrite a working hero until validation passes.
    text=read_text(src)
    if not re.search(r'<\s*[A-Za-z_][A-Za-z0-9_.:-]*\b',text):
        raise RuntimeError("Refusing to override hero: pristine Reborn entity is invalid.")


    attrs = list(AVATAR_ATTRS) + [
    "previewpassiveeffect",
    "storepassiveeffect",
]

    attr_pattern = (
        r"(?:"
        + "|".join(map(re.escape, attrs))
        + r"|tooleffect(?:keyname|path|group)\d*"
        + r")"
    )

    pat = re.compile(
        r'(\b' + attr_pattern + r'\s*=\s*")([^"]*)(")',
        re.I
    )

    changed=0
    modifier_cosmetics={}
    oldattrs=legacy_modifier_attrs(hero,new,z,lmembers,tmp) if new in hero["legacy"] else {}
    diag(root,"="*72)
    diag(root,f"APPLY hero={hero['folder']} avatar={new} legacy_folder={hero.get('legacy_folder') or hero['folder']}")
    diag(root,f"target={target}")
    diag(root,f"legacy_modifier_found={bool(oldattrs)} attributes={len(oldattrs)}")
    if new in hero["legacy"]:
        ablocks=_legacy_entity_blocks(hero,new,z,lmembers,tmp)
        nested_ability_blocks=_legacy_ability_modifier_blocks(hero,new,z,lmembers,tmp)
        modifier_cosmetics=_legacy_hero_modifier_cosmetics(root,hero,new,z,lmembers,tmp,ablocks)
        diag(root,f"ABILITY_ALT_BLOCKS count={len(ablocks)}")
        for mem,a in ablocks:
            diag(root,f"ABILITY_ALT {mem} attrs={a}")
        # Seed dependencies from BOTH hero modifier attributes and ability AltAvatar blocks.
        # This is deliberately done before generating the recipe so PreparedAssets contains
        # icons, attachments/weapons, projectiles, state FX and other cosmetic resources.
        explicit=[]
        hero_owner=f"heroes/{(hero.get('legacy_folder') or hero['folder']).lower()}/hero.entity"
        for k,v in oldattrs.items():
            if is_avatar_cosmetic_attr(k):
                explicit.append((hero_owner,v))
        for mem,a in ablocks + nested_ability_blocks:
            for k,v in a.items():
                if not k.startswith('__'):
                    explicit.append((mem.replace('\\','/'),v))
        for attrs in modifier_cosmetics.values():
            for key in ('model','passiveeffect'):
                if attrs.get(key):explicit.append((hero_owner,attrs[key]))
        # Materials/effects inside the avatar package can reference assets from
        # another hero namespace.  Include those edges in the same bounded
        # dependency closure so prepared installs carry the complete package.
        # Some old MDF/effect files contain recoverable duplicated path
        # segments such as sounds/sounds. Repair the copied text before
        # dependency discovery so both the package and the game use the fix.
        _repair_legacy_text_references(root,hero,new)
        explicit.extend(_legacy_avatar_text_ref_items(root,hero,new,oldattrs))
        _normalize_explicit_cosmetic_refs(root,hero,new,explicit)
        ability_written=_apply_legacy_ability_overrides(root,hero,new,z,arc,lmembers,tmp)
        diag(root,f"ABILITY_RUNTIME_OVERRIDES files={ability_written}")
    elif new in hero.get('reborn',set()) and new != 'default':
        # Current Reborn avatars can carry their own morph/level-form models in
        # a sibling hero.entity. Overlay those visual fields onto the pristine
        # current base entity while preserving its gameplay fields.
        modifier_cosmetics=_reborn_hero_modifier_cosmetics(hero,new,z,arc,tmp)
        diag(root,f"REBORN_MODIFIER_COSMETICS avatar={new} count={len(modifier_cosmetics)}")
    if oldattrs:
        for k in sorted(oldattrs): diag(root,f"OLDATTR {k}={oldattrs[k]}")
    if new in hero["legacy"]:
        for base_label,base in (("modern_base_avatar",legacy_dest(root,hero,new)),("legacy_mirror",legacy_mirror_dest(root,hero,new))):
            diag(root,f"VOICE_DIR {base_label}={base} exists={os.path.isdir(base)}")
            voices=_voice_inventory(base)
            diag(root,f"VOICE_FILES {base_label} count={len(voices)}")
            for x in voices[:100]: diag(root,f"  {x}")
        for k in ("selectedsound","selectedflavorsound","confirmmovesound","confirmattacksound","nomanasound","cooldownsound","tauntedsound","tauntkillsound","announcersound"):
            if k in oldattrs:
                diag(root,f"VOICE_REF {k} raw={oldattrs[k]} rewritten={_rewrite_old_asset_path(oldattrs[k],hero,new,root)} exists={_legacy_ref_exists(root,hero,new,oldattrs[k])}")

    def rep(m):
        nonlocal changed
        attr=re.match(r'([A-Za-z0-9_]+)',m.group(1)).group(1).lower()
        v=m.group(2); nv=v
        if new in hero["legacy"] and attr in oldattrs:
            # A historical attackprojectile name is useful only when its
            # named entity was imported with the avatar. Fall back to the
            # pristine Reborn value when the old definition is genuinely
            # absent, keeping a working default projectile.
            if attr in ("attackprojectile","projectile") and not _legacy_named_entity_exists(root,hero,new,oldattrs[attr]):
                diag(root,f"COSMETIC_ENTITY_FALLBACK hero={hero['folder']} avatar={new} attr={attr} value={oldattrs[attr]}")
                nv=v
                return m.group(1)+nv+m.group(3)
            # Preserve Reborn's base passive effect for avatars whose historical
            # avatar-level shell is incompatible. Ability-level passive effects are separate.
            if attr=="passiveeffect" and (hero["folder"].lower(),new.lower()) in BODY_SHELL_COMPAT:
                candidate=v
            else:
                candidate=_rewrite_old_asset_path(oldattrs[attr],hero,new,root)
            if attr.endswith("sound"):
                if _legacy_package_has_voice(root,hero,new) and _legacy_ref_exists(root,hero,new,oldattrs[attr]):
                    nv=candidate
            else:
                nv=candidate
        elif attr in ("model","storemodel"):
            if new in hero["legacy"]:
                rel="model.mdf"
                if attr=="storemodel":
                    candidate=os.path.join(legacy_dest(root,hero,new),"preview.mdf")
                    if os.path.isfile(candidate): rel="preview.mdf"
                nv=_legacy_runtime_ref(hero,new,rel)
            else:
                nv=f"../{new}/model.mdf"
        elif attr in ("icon","icon2","portrait"):
            if new in hero["legacy"]:
                # Component fallback: only point at a legacy portrait/icon when the file
                # really exists. Otherwise retain the pristine Reborn/default reference.
                d=legacy_dest(root,hero,new)
                found=None
                for cand in ("icon.tga","icon.dds","icon.png"):
                    if os.path.isfile(os.path.join(d,cand)):
                        found=cand;break
                if found:nv=_legacy_runtime_ref(hero,new,found)
            else:
                nv=f"../{new}/icon.tga"
        elif new in hero["legacy"] and attr.endswith("sound"):
            # No legacy sound metadata: leave pristine/default hero sound untouched.
            nv=v
        elif new not in hero["legacy"]:
            # Reborn named sibling directories are siblings of base.
            if attr in ("model","storemodel"): nv=f"../{new}/model.mdf"
            elif attr in ("icon","icon2","portrait"): nv=f"../{new}/icon.tga"
        if nv!=v: changed+=1
        return m.group(1)+nv+m.group(3)

    # Historical avatars often define icon2/portrait but no plain icon.
    # Reborn uses the root hero icon in UI contexts, so promote the best
    # historical avatar icon to root "icon" when the selected legacy avatar
    # did not explicitly provide one.
    if new in hero["legacy"] and "icon" not in oldattrs:
        avatar_icon = oldattrs.get("icon2") or oldattrs.get("portrait")

        if avatar_icon and _legacy_ref_exists(root,hero,new,avatar_icon):
            oldattrs["icon"] = avatar_icon


    text=_transform_hero_root(text,lambda tag:pat.sub(rep,tag))
    text,voice_changed=_rewrite_avatar_voice_refs(root,hero,new,text)
    if voice_changed:
        diag(root,f"AVATAR_VOICE_REFS_REPAIRED hero={hero['folder']} avatar={new} changed={voice_changed}")

    # A few historical models expose attack_1/attack_2 clips but their old
    # avatar block omitted attackanim.  Reborn's entity can then select the
    # idle clip for every attack.  Explicitly bind the conventional attack
    # family only when the selected package actually contains those clips.
    if new in hero.get("legacy",[]) and "attackanim" not in oldattrs:
        avatar_dir=legacy_dest(root,hero,new)
        has_attack_clip=any(
            os.path.isfile(os.path.join(avatar_dir,"clips",name))
            for name in ("attack_1.clip","attack_2.clip")
        )
        if has_attack_clip:
            root_tag=re.search(r'<hero\b[^>]*>',text,re.I|re.S)
            if root_tag and not re.search(r'\battackanim\s*=',root_tag.group(0),re.I):
                text=text[:root_tag.end()-1]+' attackanim="attack_%"'+text[root_tag.end()-1:]
                changed+=1

    # Historical avatar metadata is authoritative for PRESENTATION only.  If S2
    # explicitly supplied a cosmetic attribute that Reborn does not have, add it to the
    # current hero root.  Gameplay/stat attributes are intentionally excluded above.

    if new in hero["legacy"]:
        cosmetic_attrs = [
            k for k in oldattrs
            if is_avatar_cosmetic_attr(k)
        ]

        for k in cosmetic_attrs:
            if k in ("skin",):
                continue
            if k=="passiveeffect" and (hero["folder"].lower(),new.lower()) in BODY_SHELL_COMPAT:
                continue
            root_tag=re.search(r'<hero\b[^>]*>',text,re.I|re.S).group(0)
            if re.search(r'\b'+re.escape(k)+r'\s*=',root_tag,re.I):
                continue
            val=_rewrite_old_asset_path(oldattrs[k],hero,new,root)
            if k.endswith("sound") and not (_legacy_package_has_voice(root,hero,new) and _legacy_ref_exists(root,hero,new,oldattrs[k])):
                continue
            text=re.sub(r'(<hero\b[^>]*?)(>)',lambda m:m.group(1)+f'\n        {k}="{val}"'+m.group(2),text,count=1,flags=re.I|re.S)
            changed+=1

    text=_overlay_hero_modifier_cosmetics(text,modifier_cosmetics,new)

    corr=SCALE_CORRECTIONS.get((hero["folder"].lower(),new.lower()))
    if corr is not None:
        val=("%g"%corr)
        if re.search(r'\bmodelscale\s*=',text,re.I):
            text=re.sub(r'(\bmodelscale\s*=\s*")[^"]*(")',r'\g<1>'+val+r'\2',text,count=1,flags=re.I)
        else:
            text=re.sub(r'(<[^>]+?)(\s*/?>)',lambda m:m.group(1)+f' modelscale="{val}"'+m.group(2),text,count=1)
        changed+=1

    # Safety gate: preserve the complete Reborn hero document and only publish a
    # syntactically recognizable hero override after all cosmetic edits are complete.
    if not re.search(r'<\s*[A-Za-z_][A-Za-z0-9_.:-]*\b',text):
        raise RuntimeError("Generated override failed validation; existing Runtime hero was left untouched.")
    tmp_target=target+".new"
    write_text(tmp_target,text)
    os.replace(tmp_target,target)
    write_text(target+".hon_avatar_switcher_created","created/managed by One Punch Mod v1.48 Avatar Packages\n")
    diag(root,f"changed_fields={changed}")
    for k in ("selectedsound","selectedflavorsound","confirmmovesound","confirmattacksound","nomanasound","cooldownsound","tauntedsound","tauntkillsound","announcersound","preglobalscale","modelscale","passiveeffect","model","portrait"):
        mm=re.search(r"\b"+re.escape(k)+r"\s*=\s*\"([^\"]*)\"",text,re.I)
        diag(root,f"GENERATED {k}={mm.group(1) if mm else '<missing>'}")
    diag(root,f"generated_entity={target}")
    if new in hero.get("legacy",[]):
        # Apply the same Reborn material compatibility pass for on-demand builds
        # as for explicit preprocessing.  This must happen before the selection
        # recipe and PreparedAssets package are published, otherwise a cache miss
        # can permanently publish old legacy shader names.
        material_fixes=_normalize_legacy_materials_for_reborn(root,hero,new)
        diag(root,f"MATERIAL_COMPAT_DONE hero={hero['folder']} avatar={new} fixes={material_fixes}")
        texture_fixes=_repair_relative_texture_references(root,hero,new)
        morph_fixes=_repair_avatar_morph_models(root,hero,new)
        animation_fixes=_repair_missing_animation_clips(root,hero,new)
        slot_fixes=_repair_network_animation_slots(root,hero,new)
        diag(root,f"PREPARED_VISUAL_REPAIRS hero={hero['folder']} avatar={new} textures={texture_fixes} morphs={morph_fixes} animations={animation_fixes} slots={slot_fixes}")
        _save_selection_recipe(root,hero,new,target)
        _publish_prepared_avatar(root,hero,new)
    return changed


def _prepared_manifest_path(root,hero,av):
    return os.path.join(_prepared_recipe_dir(root,hero,av),'manifest.json')

_VISUAL_REFERENCE_EXTS = {".effect", ".mdf", ".model", ".clip", ".material", ".mtrl", ".tga", ".dds", ".png"}


def _visual_reference_logical(raw, owner):
    raw = str(raw or "").replace("\\", "/")
    if raw.startswith("/"):
        return _logical_norm(raw)
    return _logical_norm(os.path.dirname(owner).replace("\\", "/") + "/" + raw)


def _missing_visual_source(root, hero, avatar, logical):
    """Find a same-avatar visual for a stale legacy path when its layout moved.

    The legacy tree contains several generations of paths. This resolver only
    selects a source when the avatar folder and meaningful path components make
    the match unambiguous; it never substitutes an arbitrary model just because
    both files are named ``model.mdf``.
    """
    parts = logical.split("/")
    if len(parts) < 3 or parts[0] != "heroes":
        return None
    refhero = parts[1].lower()
    tail = parts[2:]
    legacy = str(hero.get("legacy_folder") or hero.get("folder") or refhero).lower()
    modern = str(hero.get("folder") or refhero).lower()
    aliases = list(LEGACY_ALIASES.get(modern, ()))
    namespaces = list(dict.fromkeys([refhero, legacy, modern] + [str(x).lower() for x in aliases]))
    attrs = (hero.get("legacy_info") or {}).get(avatar, {})
    physical = _legacy_avatar_physical_root(avatar, attrs)

    # Known legacy namespace/layout repairs where the old reference is
    # authoritative but the extracted source uses a different folder.
    explicit = {
        "heroes/bomb/ability_01/effects/explode.mdf": "heroes/artillery/alt5/ability_01/effects/lasers/model.mdf",
        "heroes/doctor_repulsor/alt200/ability_01/ball/model.mdf": "heroes/doctor_repulsor/set_ascension/ability_01/ball/model.mdf",
        "heroes/deadwood/alt5/ability_01/hand/effects/color.tga": "heroes/deadwood/alt5/ability_01/effects/hand/color.dds",
        "heroes/frosty/effects/ice.mdf": "heroes/frosty/ability_02/effects/ice.mdf",
        "heroes/gemini/alt5/frostpet/clips/frozen_run.clip": "heroes/gemini/frostpet/clips/walk_1.clip",
        "heroes/gemini/alt5/frostpet/clips/attack_3.clip": "heroes/gemini/frostpet/clips/attack_1.clip",
        "heroes/gemini/alt5/frostpet/clips/ability_3_walk.clip": "heroes/gemini/frostpet/clips/walk_1.clip",
        "heroes/gemini/alt6/frostpet/clips/frozen_run.clip": "heroes/gemini/frostpet/clips/walk_1.clip",
        "heroes/hammerstorm/ability_02/effects/trail.effect": "heroes/hammerstorm/ability_03/effects/trail.effect",
        "heroes/scout/ability_01/effects/backstab.effect": "heroes/hantumon/alt5/effects/backstab.effect",
        "heroes/sir_benzington/alt8/effects/bored.effect": "heroes/sir_benzington/alt6/effects/bored.effect",
        "heroes/torturer/projectile/model.mdf": "heroes/xalynx/projectile/effects/model.mdf",
        "heroes/xalynx/projectile/model.mdf": "heroes/xalynx/projectile/effects/model.mdf",
        "heroes/war_beast/hd_warbeast/ability_04/effects/body_1.effect": "heroes/wolfman/alt5/ability_04/effects/body.effect",
        "heroes/witch_slayer/effects/taunt.effect": "heroes/witch_slayer/alt3/effects/taunt.effect",
        "heroes/zephyr/effects/rainbowtrail.material": "shared/effects/materials/rainbowtrail.material",
    }
    mapped=explicit.get(logical)
    if mapped:
        hits=_resolve_legacy_logical_path(root,mapped,None)
        if hits:
            return Path(hits[0][1])

    source_roots = []
    for namespace in namespaces:
        hero_root = Path(legacy_assets_root(root)) / "heroes" / namespace
        for package in (physical, str(avatar).lower()):
            if hero_root.joinpath(package).is_dir():
                source_roots.append(hero_root / package)
        if hero_root.is_dir():
            source_roots.append(hero_root)
    # A few effect definitions are shared by several heroes but are referenced
    # through a hero-local path in old entities. Allow the shared tree only for
    # a basename/parent-token match; it cannot replace an avatar model.
    shared_root = Path(legacy_assets_root(root)) / "shared"
    if shared_root.is_dir():
        source_roots.append(shared_root)
    source_roots = list(dict.fromkeys(source_roots))

    tails = [tail]
    if tail and tail[0].lower() in {str(avatar).lower(), str(physical).lower()}:
        tails.append(tail[1:])
    if tail and tail[0].lower().startswith("alt"):
        tails.append(tail[1:])
    if tail and tail[0].lower() == "base":
        tails.append(tail[1:])
    # Effects copied from old archives sometimes contain both
    # ``ability_N/sub/effects/file`` and ``ability_N/effects/sub/file``.
    for value in list(tails):
        if len(value) >= 4 and re.fullmatch(r"ability_\d+", value[0], re.I):
            if "effects" in [x.lower() for x in value[1:-1]]:
                ei=next(i for i,x in enumerate(value[1:-1],1) if x.lower()=="effects")
                if ei != 1:
                    tails.append([value[0],"effects"]+value[1:ei]+value[ei+1:])
    # Known old names for the Gemini frost projectile and the Kinesis folder.
    for value in list(tails):
        joined="/".join(value)
        if "frostpet_projectile" in joined:
            tails.append(joined.replace("frostpet_projectile", "frost_projectile").split("/"))
        if "kenisis" in joined:
            tails.append(joined.replace("kenisis", "kinesis").split("/"))
    tail_keys=[tuple(x.lower() for x in value) for value in tails]

    candidates=[]
    for source_root in source_roots:
        for value,key in zip(tails,tail_keys):
            if not value:
                continue
            direct=source_root.joinpath(*value)
            if direct.is_file():
                candidates.append((1000, direct))
            # The source may store effects/ability_N as ability_N/effects.
            if len(value) >= 3 and value[0].lower() == "effects" and re.fullmatch(r"ability_\\d+", value[1], re.I):
                moved=source_root.joinpath(value[1], "effects", *value[2:])
                if moved.is_file():
                    candidates.append((950, moved))
        wanted = Path(tail[-1]).name.lower() if tail else ""
        stems=[wanted]
        suffix=Path(wanted).suffix.lower()
        if suffix in {".tga", ".png", ".dds"}:
            stem=Path(wanted).stem
            stems += [stem+ext for ext in (".tga", ".png", ".dds")]
            if stem.startswith("normal"):
                stems += [stem+"_rxgb.dds", stem+"_s.dds"]
        # Only use a basename match when a meaningful parent directory also
        # survives in the candidate path. This prevents an unrelated model
        # from replacing a missing effect model.
        ignored_tokens={"effects", "projectile", "base", "alt", "trophy_skin"}
        target_tokens={x.lower() for x in tail[:-1] if x.lower() not in ignored_tokens}
        ability_tokens={x.lower() for x in tail if re.fullmatch(r"ability_\d+", x, re.I)}
        for dp,_,files in os.walk(source_root):
            for fn in files:
                if fn.lower() not in stems:
                    continue
                rel=Path(dp,fn).relative_to(source_root).as_posix().lower()
                rel_tokens=set(rel.split("/"))
                overlap=len(target_tokens & rel_tokens)
                ability_overlap=len(ability_tokens & rel_tokens)
                # Same hero + same ability is a reliable fallback for an old
                # misplaced effect/clip. Shared effects require an additional
                # semantic parent token, so a generic model cannot be selected.
                score=100 + overlap*20 + ability_overlap*70
                if source_root == shared_root and not overlap:
                    continue
                if score >= 120:
                    candidates.append((score, Path(dp,fn)))
    if not candidates:
        return None
    candidates.sort(key=lambda item:(-item[0], str(item[1]).lower()))
    best_score,best=candidates[0]
    if best_score < 120:
        return None
    return best


def _repair_missing_visual_references(root, hero, avatar):
    """Materialize verified visual dependencies at the paths old entities use.

    The legacy client accepted several equivalent layouts. Reborn is stricter,
    so this pass repairs those layouts during preprocessing and removes only
    optional material samplers whose source texture truly does not exist.
    """
    modern=str(hero.get("folder") or "").lower()
    legacy=str(hero.get("legacy_folder") or modern).lower()
    hero_names=tuple(dict.fromkeys((modern,legacy)))
    packages=[]
    for namespace in hero_names:
        hero_root=Path(switcher_root(root))/"heroes"/namespace
        if not hero_root.is_dir():
            continue
        # Include only generated base entities and the selected avatar. Do
        # not rescan every sibling avatar for each package in a full batch.
        roots=[]
        base_root=hero_root/"base"
        avatar_root=hero_root/str(avatar).lower()
        attrs=(hero.get("legacy_info") or {}).get(avatar,{})
        physical_root=hero_root / _legacy_avatar_physical_root(avatar,attrs)
        if base_root.is_dir():
            roots.append(base_root)
        for candidate in (avatar_root,physical_root):
            if candidate.is_dir() and candidate not in roots:
                roots.append(candidate)
        packages.extend((x,namespace,hero_root) for x in roots)

    repaired=0; removed_optional=0
    for package,namespace,hero_root in packages:
        for dp,_,files in os.walk(package):
            for fn in files:
                if Path(fn).suffix.lower() not in LEGACY_TEXT_EXTS:
                    continue
                path=Path(dp)/fn
                try:text=read_text(str(path))
                except OSError:
                    continue
                owner=f"heroes/{namespace}/{path.relative_to(hero_root).as_posix()}"
                changed=False
                missing_optional=[]
                missing_actions=[]
                for match in LEGACY_REF_RE.finditer(" "+text):
                    raw=match.group(1)
                    ext=Path(raw.split("#",1)[0]).suffix.lower()
                    if ext not in _VISUAL_REFERENCE_EXTS:
                        continue
                    logical=_visual_reference_logical(raw,owner)
                    if not logical:
                        continue
                    # A legacy source hit is not enough: the requested logical
                    # path must also exist in the generated Runtime/Prepared
                    # tree. This lets us materialize alias paths such as
                    # ability_N/sub/effects/file.
                    if _mounted_reference_exists(root,raw,owner):
                        continue
                    source=_missing_visual_source(root,hero,avatar,logical)
                    if source:
                        destination=Path(switcher_root(root),*logical.split("/"))
                        destination.parent.mkdir(parents=True,exist_ok=True)
                        # TGA/PNG references can be satisfied by the compiled
                        # DDS generated from the same source texture.
                        if Path(raw).suffix.lower() in {".tga",".png"} and source.suffix.lower()==".dds":
                            destination=destination.with_suffix(".dds")
                        if not destination.is_file() or destination.stat().st_size != source.stat().st_size:
                            shutil.copy2(source,destination)
                        repaired+=1;changed=True
                        diag(root,f"VISUAL_REF_REPAIR hero={modern} avatar={avatar} ref={raw} source={source}")
                    elif (
                        Path(fn).suffix.lower() in {".material",".mtrl"}
                        and (
                            "normal" in Path(raw.split("#",1)[0]).name.lower()
                            or Path(raw.split("#",1)[0]).name.lower().startswith(("spec_color", "team", "glow"))
                        )
                    ):
                        # HoN materials do not require a normal/spec/team map.
                        # Dropping only the sampler prevents a missing optional
                        # map from poisoning the complete material/model.
                        missing_optional.append(raw)
                    elif Path(fn).suffix.lower() in {".mdf",".model",".effect"} and Path(raw.split("#",1)[0]).suffix.lower()==".effect":
                        # An absent cosmetic trigger must not make the model
                        # invalid. Remove only the event that calls it; the
                        # rest of the animation/effect remains intact.
                        missing_actions.append(raw)

                if missing_actions:
                    wanted={x.lower() for x in missing_actions}
                    kept=[]
                    for line in text.splitlines(True):
                        low=line.lower()
                        if any(x in low for x in wanted) and re.search(r"starteffect|spawnevent",line,re.I):
                            changed=True
                            diag(root,f"MISSING_EFFECT_EVENT_REMOVED hero={modern} avatar={avatar} file={path}")
                            continue
                        kept.append(line)
                    text="".join(kept)

                if missing_optional:
                    wanted={x.lower() for x in missing_optional}
                    def clean_sampler(m):
                        nonlocal removed_optional,changed
                        tag=m.group(0)
                        tm=re.search(r'\btexture\s*=\s*"([^"]+)"',tag,re.I)
                        nm=re.search(r'\bname\s*=\s*"([^"]+)"',tag,re.I)
                        if tm and nm and tm.group(1).lower() in wanted and nm.group(1).lower() in {"normalmap","specular","team","lightmap"}:
                            removed_optional+=1;changed=True
                            diag(root,f"OPTIONAL_MAP_REMOVED hero={modern} avatar={avatar} file={path} ref={tm.group(1)}")
                            return ""
                        return tag
                    text=re.sub(r"<sampler\b[^>]*?/>",clean_sampler,text,flags=re.I|re.S)

                if changed:
                    write_text(str(path),text)

    if repaired or removed_optional:
        diag(root,
             f"VISUAL_REF_REPAIR_DONE hero={modern} avatar={avatar} "
             f"copied={repaired} optional_removed={removed_optional}")
    return repaired+removed_optional

def _repair_missing_avatar_ui_refs(root, hero, avatar):
    """Give missing legacy icon/portrait fields a valid generated fallback."""
    entity=Path(switcher_root(root))/"heroes"/str(hero.get("folder") or "").lower()/"base"/"hero.entity"
    if not entity.is_file(): return 0
    try:text=read_text(str(entity))
    except OSError:return 0
    hero_name=str(hero.get("folder") or "").lower()
    hero_root=Path(switcher_root(root))/"heroes"/hero_name
    attrs=(hero.get("legacy_info") or {}).get(avatar,{})
    physical=_legacy_avatar_physical_root(avatar,attrs)
    icon_sources=[]
    for base in (hero_root/physical,hero_root/str(avatar).lower()):
        for ext in (".dds",".tga",".png"):
            q=base/("icon"+ext)
            if q.is_file(): icon_sources.append(q)
    if not icon_sources:
        icon_sources=sorted(
            (q for q in hero_root.rglob("icon.dds") if "/base/" not in q.as_posix().lower()),
            key=lambda q:q.as_posix().lower()
        )
    if not icon_sources: return 0
    fallback=icon_sources[0]
    changed=0
    for key in ("icon","portrait","icon2"):
        pattern=r'(\b'+re.escape(key)+r'\s*=\s*")([^"]+)(")'
        def replace_missing(match):
            nonlocal changed
            ref=match.group(2).replace("\\","/")
            target=(Path(switcher_root(root))/ref.lstrip("/") if ref.startswith("/") else (entity.parent/ref).resolve())
            alternatives=[target]
            if target.suffix.lower() in {".tga",".png"}:
                alternatives.append(target.with_suffix(".dds"))
            if any(x.is_file() for x in alternatives):
                return match.group(0)
            # Reuse the selected avatar's physical icon when available; otherwise
            # use another valid icon from the hero package. This avoids a dangling
            # UI resource while preserving the avatar portrait whenever it exists.
            rel=fallback.relative_to(hero_root).as_posix()
            newref=f"/heroes/{hero_name}/{rel}"
            changed+=1
            return match.group(1)+newref+match.group(3)
        text=re.sub(pattern,replace_missing,text,flags=re.I)
    if changed:
        write_text(str(entity),text)
        write_text(str(entity)+".hon_avatar_switcher_created","created/managed by One Punch Mod v1.48 Avatar Packages\n")
        diag(root,f"UI_REF_FALLBACK hero={hero_name} avatar={avatar} fields={changed}")
    return changed

def _mounted_reference_exists(root, ref, owner):
    logical=_visual_reference_logical(ref,owner)
    if not logical:
        return False
    candidates=[logical]
    stem,ext=os.path.splitext(logical)
    if ext.lower() in ('.tga','.png'):
        candidates.extend([stem+'.dds',stem+'_rxgb.dds',stem+'_s.dds'])
    elif ext.lower()=='.dds':
        candidates.extend([stem+'.tga',stem+'.png'])
    for asset_root in (switcher_root(root),prepared_root(root)):
        for candidate in candidates:
            if os.path.isfile(os.path.join(asset_root,*candidate.split('/'))):
                return True
    return False


def _build_prepared_manifest(root,hero,av,oldattrs=None):
    """Audit the prepared package. This is a build/developer report, not runtime work."""
    ph=_prepared_hero_dir(root,hero); lf=(hero.get('legacy_folder') or hero['folder']).lower()
    counts={"files":0,"models":0,"materials":0,"textures":0,"effects":0,"sounds":0,"icons":0,"entities":0}
    unresolved=[]
    # Count only this avatar's physical subtree / AltN-named files. The prepared hero
    # directory is a deduplicated union across avatars and must not be attributed wholesale.
    if os.path.isdir(ph):
        for dp,_,fs in os.walk(ph):
            for fn in fs:
                fp=os.path.join(dp,fn); relhero=os.path.relpath(fp,ph).replace('\\','/').lower()

                avl=av.lower()
                physical_root=_legacy_avatar_physical_root(av,oldattrs)

                if not (
                    relhero.startswith(physical_root+'/')
                    or relhero == physical_root
                    or re.search(r'(^|[/_.-])'+re.escape(avl)+r'([/_.-]|$)',relhero)
                ):
                    continue


                ext=os.path.splitext(fn)[1].lower(); counts['files']+=1
                if ext in ('.model','.mdf','.clip','.anim'):counts['models']+=1
                if ext in ('.material','.mtrl'):counts['materials']+=1
                if ext in ('.dds','.tga','.png'):counts['textures']+=1
                if ext=='.effect':counts['effects']+=1
                if ext in ('.ogg','.wav'):counts['sounds']+=1
                if ext=='.entity':counts['entities']+=1
                if 'icon' in fn.lower() and ext in ('.dds','.tga','.png'):counts['icons']+=1
                if ext not in LEGACY_TEXT_EXTS:continue
                try:txt=read_text(fp)
                except Exception:continue
                rel=os.path.relpath(fp,prepared_root(root)).replace('\\\\','/')
                # Only flag references that clearly belong to this legacy hero/avatar.
                audit_txt=re.sub(r"<!--.*?-->","",txt,flags=re.S)
                for m in LEGACY_REF_RE.finditer(' '+audit_txt):
                    ref=m.group(1); low=ref.replace('\\\\','/').lower()
                    # Terrain-qualified effect names are intentional runtime expressions resolved by HoN.
                    if '#getterraintype()#' in low: continue
                    if av.lower() not in low and f'heroes/{lf}/' not in low:continue
                    owner='heroes/'+hero['folder'].lower()+'/'+os.path.relpath(fp,ph).replace('\\\\','/')
                    hits=_resolve_legacy_logical_path(root,ref,owner)
                    if not hits and not _mounted_reference_exists(root,ref,owner):
                        unresolved.append({"owner":rel,"ref":ref})
    # de-duplicate while preserving useful owner/ref evidence
    seen=set(); unresolved2=[]
    for x in unresolved:
        k=(x['owner'].lower(),x['ref'].lower())
        if k not in seen:seen.add(k);unresolved2.append(x)
    data={"schema":1,"app":APP,"hero":hero['folder'],"legacy_folder":lf,"avatar":av,
          "counts":counts,"unresolved":unresolved2,"status":"clean" if not unresolved2 else "needs_review"}
    mp=_prepared_manifest_path(root,hero,av);os.makedirs(os.path.dirname(mp),exist_ok=True)
    with open(mp,'w',encoding='utf-8') as f:json.dump(data,f,indent=2)
    return data

def _repair_relative_texture_references(root,hero,av):
    """Use the shared PreparedAssets texture-reference repair pass."""
    from one_punch_mod import _repair_relative_texture_references as repair
    return repair(root,hero,av)

def _repair_avatar_morph_models(root,hero,av):
    """Use the shared prepared ability-4 morph repair pass."""
    from one_punch_mod import _repair_avatar_morph_models as repair
    return repair(root,hero,av)

def _repair_missing_animation_clips(root,hero,av):
    """Use the shared network/replay animation clip repair pass."""
    from one_punch_mod import _repair_missing_animation_clips as repair
    return repair(root,hero,av)

def _repair_network_animation_slots(root,hero,av):
    """Use the shared network/replay animation slot repair pass."""
    from one_punch_mod import _repair_network_animation_slots as repair
    return repair(root,hero,av)

def _normalize_legacy_materials_for_reborn(root, hero, av):
    """Use the launcher/preprocessor shared blue-overlay compatibility pass."""
    from one_punch_mod import _normalize_legacy_materials_for_reborn as normalize
    return normalize(root, hero, av)

def _normalize_reborn_shared_effect_materials(root):
    """Repair verified shared-effect references in the Runtime overlay.

    Reborn's current resources0.jz contains ``quadmap4.dds``.  The shared
    shell2 material still names the old ``quadmap4.jpg`` logical filename.
    Most current effects resolve that convention, but legacy avatar effects
    that use shell2 can otherwise render their model particle as an opaque
    black card.  Keep this correction in the generated Runtime compatibility
    layer so all prepared avatars using the shared material receive it.
    """
    material_dir = os.path.join(
        switcher_root(root), "shared", "effects", "materials"
    )
    if not os.path.isdir(material_dir):
        return 0

    changed = 0
    for name in ("shell2.material",):
        path = os.path.join(material_dir, name)
        if not os.path.isfile(path):
            continue
        try:
            text = read_text(path)
        except OSError:
            continue
        newtext = text.replace(
            "/shared/effects/textures/quadmap4.jpg",
            "/shared/effects/textures/quadmap4.dds",
        )
        if newtext == text:
            continue
        write_text(path, newtext)
        changed += 1
        diag(root, f"SHARED_EFFECT_COMPAT file={os.path.relpath(path, switcher_root(root))}")
    return changed



def _restore_flint_shared_projectile_support(root, arc=None):
    """Publish Flint's shared special-attack projectile support.

    Flint's legacy ability 2 references the shared projectile namespace from
    every avatar package. The avatar packages contain their own trail files,
    but the named invisible/hollowpoint projectile entities and the Reborn
    attack effect were previously left out of PreparedAssets. Keep this
    developer-only recovery here; the launcher consumes only PreparedAssets.
    """
    import zipfile

    source = os.path.join(
        one_punch_root(root), "LegacyAssets", "heroes", "flint_beastwood", "projectile"
    )
    if not os.path.isdir(source):
        return 0

    destinations = [
        os.path.join(prepared_root(root), "heroes", "flint_beastwood", "base", "projectile"),
        os.path.join(switcher_root(root), "heroes", "flint_beastwood", "base", "projectile"),
    ]
    copied = 0
    for destination in destinations:
        os.makedirs(destination, exist_ok=True)
        for dp, _, files in os.walk(source):
            rel = os.path.relpath(dp, source)
            out = destination if rel == "." else os.path.join(destination, rel)
            os.makedirs(out, exist_ok=True)
            for name in files:
                src = os.path.join(dp, name)
                dst = os.path.join(out, name)
                shutil.copy2(src, dst)
                copied += 1

    # Two legacy Flint skins keep absolute attack-impact references in their
    # generated hero entity. The effect itself lives in the shared legacy
    # projectile folder, so publish the expected per-avatar aliases as well.
    # Without these aliases the normal attack impact silently resolves to a
    # missing file for Alt3 and Alt5.
    shared_impact = os.path.join(source, "impact.effect")
    if os.path.isfile(shared_impact):
        for avatar in ("alt3", "alt5"):
            for destination in destinations:
                target = os.path.join(
                    destination, "..", "..", avatar, "projectile", "impact.effect"
                )
                target = os.path.normpath(target)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copy2(shared_impact, target)
                copied += 1

    # These two effects belong to the current Reborn Flint package rather than
    # the legacy source tree. Recover them from resources0.jz when available.
    if arc and os.path.isfile(arc):
        members = (
            "heroes/flint_beastwood/base/projectile/effects/attack_hollowpoint.effect",
            "heroes/flint_beastwood/base/projectile/effects/trail_hollowpoint.effect",
        )
        try:
            with zipfile.ZipFile(arc, "r") as archive:
                names = {name.replace("\\", "/").lower(): name for name in archive.namelist()}
                for logical in members:
                    member = names.get(logical.lower())
                    if not member:
                        continue
                    payload = archive.read(member)
                    rel = logical.split("heroes/flint_beastwood/base/projectile/", 1)[1]
                    for destination in destinations:
                        out = os.path.join(destination, *rel.split("/"))
                        os.makedirs(os.path.dirname(out), exist_ok=True)
                        with open(out, "wb") as handle:
                            handle.write(payload)
                        copied += 1
        except (OSError, KeyError, RuntimeError, zipfile.BadZipFile):
            pass

    # The source bullet material names color.tga while the normalized package
    # carries color.dds. Reuse the already prepared texture in both trees.
    for destination in destinations:
        bullet = os.path.join(destination, "effects", "bullet")
        source_color = os.path.join(
            prepared_root(root), "heroes", "flint_beastwood", "projectile",
            "effects", "bullet", "color.dds"
        )
        target_color = os.path.join(bullet, "color.dds")
        if os.path.isfile(source_color) and not os.path.isfile(target_color):
            os.makedirs(bullet, exist_ok=True)
            shutil.copy2(source_color, target_color)
            copied += 1
        material = os.path.join(bullet, "bullet.material")
        if os.path.isfile(material):
            material_text = read_text(material)
            updated = material_text.replace('texture="color.tga"', 'texture="color.dds"')
            if updated != material_text:
                write_text(material, updated)
                copied += 1

    diag(root, f"FLINT_PROJECTILE_SUPPORT restored={copied}")
    return copied

def _publish_flint_special_attack_projectile(root, avatar):
    """Make Flint's chance-based double attack reuse the selected avatar shot.

    The legacy ability selects the shared invisible projectile, whose historical
    ``<altavatar>`` branches depend on HoN's native avatar-key system. The
    launcher replaces the hero definition in-place, so those branches are not
    reliable for a selected prepared avatar. Publish a per-avatar override of
    the same invisible projectile that spawns the selected avatar's normal shot
    twice. The ability and its damage logic remain unchanged.
    """
    avatar = str(avatar or "").lower()
    if not avatar:
        return 0

    prep = prepared_root(root)
    recipe_root = os.path.join(
        prep, "recipes", "flint_beastwood", avatar, "files",
        "heroes", "flint_beastwood", "base"
    )
    hero_entity = os.path.join(recipe_root, "hero.entity")
    if not os.path.isfile(hero_entity):
        return 0
    try:
        text = read_text(hero_entity)
    except OSError:
        return 0
    match = re.search(r'\battackprojectile\s*=\s*"([^"]+)"', text, re.I)
    if not match:
        return 0
    normal_projectile = match.group(1).strip()
    if not re.match(r'^[A-Za-z_][A-Za-z0-9_.-]*$', normal_projectile):
        return 0

    projectile = f"""<?xml version="1.0" encoding="UTF-8"?>
<projectile
    name="Projectile_FlintBeastwoodAttack_Invis"
    speed="3000"
    gravity="0"
    modelscale=".4"
    model="/shared/models/invis.mdf"
    impacteffect=""
    traileffect=""
>
    <onspawn>
        <spawnprojectile name="{normal_projectile}" source="source_entity" target="target_entity" offset="30 150 100" noresponse="true" />
        <spawnprojectile name="{normal_projectile}" source="source_entity" target="target_entity" offset="-30 150 100" noresponse="true" />
    </onspawn>
</projectile>
"""

    rel = os.path.join(
        "heroes", "flint_beastwood", "base", "projectile",
        "attack_projectile_invis.entity"
    )
    recipe_target = os.path.join(recipe_root, "projectile", "attack_projectile_invis.entity")
    runtime_target = os.path.join(
        switcher_root(root), "heroes", "flint_beastwood", "base",
        "projectile", "attack_projectile_invis.entity"
    )
    for target in (recipe_target, runtime_target):
        os.makedirs(os.path.dirname(target), exist_ok=True)
        write_text(target, projectile)

    manifest = os.path.join(prep, "recipes", "flint_beastwood", avatar, "recipe.json")
    try:
        data = json.load(open(manifest, "r", encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        data = {"version": 1, "hero": "flint_beastwood", "avatar": avatar, "files": []}
    files = data.setdefault("files", [])
    rel = rel.replace("\\", "/")
    if rel not in files:
        files.append(rel)
    with open(manifest, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)

    diag(
        root,
        f"FLINT_SPECIAL_PROJECTILE avatar={avatar} normal={normal_projectile}"
    )
    return 1

_KNOWN_WRONG_WALK_CLIPS = {
    # These legacy skins contain a walk clip that does not behave correctly
    # with their Reborn model in online/replay playback. Use the current
    # Reborn base movement clip for the same rig.
    ("maliken", "alt5"): "heroes/maliken/base/clips/walk_1.clip",
    ("keeper_of_the_forest", "alt7"): "heroes/keeper_of_the_forest/base/clips/walk_1.clip",
}


def _repair_known_wrong_walk_clip(root, hero, avatar, arc=None):
    """Replace verified broken legacy walk clips in the prepared package."""
    key = (str(hero.get("folder") or "").lower(), str(avatar or "").lower())
    member = _KNOWN_WRONG_WALK_CLIPS.get(key)
    if not member or not arc or not os.path.isfile(arc):
        return 0
    try:
        import zipfile
        with zipfile.ZipFile(arc, "r") as archive:
            names = {name.replace("\\", "/").lower(): name for name in archive.namelist()}
            actual = names.get(member.lower())
            if not actual:
                return 0
            payload = archive.read(actual)
    except (OSError, KeyError, RuntimeError, zipfile.BadZipFile):
        return 0

    targets = (
        os.path.join(prepared_root(root), "heroes", key[0], key[1], "clips", "walk_1.clip"),
        os.path.join(switcher_root(root), "heroes", key[0], key[1], "clips", "walk_1.clip"),
    )
    changed = 0
    for target in targets:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as handle:
            handle.write(payload)
        changed += 1
    diag(root, f"KNOWN_WALK_CLIP_REPAIR hero={key[0]} avatar={key[1]} source={member}")
    return changed


def _repair_maliken_walk_clips(root, hero, avatar):
    """Use Maliken's known-good movement clips for every avatar form.

    Maliken has two animation models: the selected avatar model and the
    temporary ability-4 model. Older avatar walk clips can be interpreted as
    stand/death state data during online and replay playback even when they
    look correct in the local Learn map. Both forms use the Maliken rig, so the
    current default walk clips are the safe network-compatible source.
    """
    if str(hero.get("folder") or "").lower() != "maliken":
        return 0
    legacy = legacy_assets_root(root)
    normal_source = os.path.join(legacy, "heroes", "maliken", "clips", "walk_1.clip")
    morph_source = os.path.join(
        legacy, "heroes", "maliken", "ability_04", "clips", "walk_1.clip"
    )
    if not os.path.isfile(normal_source) or not os.path.isfile(morph_source):
        return 0

    changed = 0
    for asset_root in (prepared_root(root), switcher_root(root)):
        package = os.path.join(asset_root, "heroes", "maliken", str(avatar).lower())
        if not os.path.isdir(package):
            continue
        for dp, _, files in os.walk(package):
            for fn in files:
                if not fn.lower().endswith(".mdf"):
                    continue
                model_path = os.path.join(dp, fn)
                try:
                    model_text = read_text(model_path)
                except OSError:
                    continue
                matches = list(re.finditer(
                    r'<anim\b[^>]*\bname\s*=\s*["\']walk_1["\'][^>]*\bclip\s*=\s*["\']([^"\']+)',
                    model_text, re.I | re.S,
                ))
                if not matches:
                    continue
                source = morph_source if "ability_04" in os.path.relpath(
                    model_path, package
                ).replace("\\", "/").lower() else normal_source
                for match in matches:
                    ref = match.group(1).replace("\\", "/")
                    if ref.startswith("/"):
                        destination = os.path.join(asset_root, *ref.lstrip("/").split("/"))
                    else:
                        destination = os.path.normpath(os.path.join(dp, *ref.split("/")))
                    os.makedirs(os.path.dirname(destination), exist_ok=True)
                    try:
                        shutil.copy2(source, destination)
                    except OSError:
                        continue
                    changed += 1
    if changed:
        diag(root, f"MALIKEN_WALK_REPAIR avatar={avatar} copies={changed}")
    return changed


def preprocess_avatar(root,hero,av,z,arc,tmp,larcs,lmembers):
    """Build-time path: deliberately perform expensive discovery once and publish the result.
    Runtime selection remains recipe-only and fast.
    """
    t=time.time()
    oldattrs=legacy_modifier_attrs(hero,av,z,lmembers,tmp)
    norm=_normalize_legacy_avatar_assets(root,hero,av,oldattrs)
    ablocks=_legacy_entity_blocks(hero,av,z,lmembers,tmp)
    owner=f"heroes/{(hero.get('legacy_folder') or hero['folder']).lower()}/hero.entity"
    refs=[(owner,v) for k,v in oldattrs.items() if is_avatar_cosmetic_attr(k)]
    refs += [(mem.replace('\\\\','/'),v) for mem,a in ablocks for v in a.values()]
    extra=_normalize_explicit_cosmetic_refs(root,hero,av,refs)
    # Force regeneration of the tiny activation recipe from the now-complete Runtime tree.
    rd=_recipe_dir(root,hero,av)
    if os.path.isdir(rd):shutil.rmtree(rd,ignore_errors=True)
    apply_avatar(root,hero,av,z,arc,tmp,larcs,lmembers,force_rebuild=True)
    if hero.get("folder", "").lower() == "flint_beastwood":
        _restore_flint_shared_projectile_support(root, arc)
        _publish_flint_special_attack_projectile(root, av)
    _repair_maliken_walk_clips(root, hero, av)
    _repair_known_wrong_walk_clip(root, hero, av, arc)
    _repair_missing_visual_references(root, hero, av)
    ui_fixes=_repair_missing_avatar_ui_refs(root, hero, av)
    if ui_fixes:
        _save_selection_recipe(
            root,hero,av,
            os.path.join(switcher_root(root),"heroes",hero["folder"],"base","hero.entity")
        )
    # Visual repairs happen after apply_avatar publishes the normal package;
    # publish once more so PreparedAssets carries exactly the repaired Runtime
    # files distributed to users.
    _publish_prepared_avatar(root,hero,av)
    man=_build_prepared_manifest(root,hero,av,oldattrs)
    diag(root,f"PREPROCESS_DONE hero={hero['folder']} avatar={av} normalize={norm} explicit={extra} material_fixes=handled_by_apply status={man['status']} seconds={time.time()-t:.3f}")
    return man

def _write_animation_slot_cache(root,heroes,z,arc,tmp):
    """Persist base-model animation order for the fast launcher repair pass."""
    data={}
    for hero in heroes:
        for folder in dict.fromkeys((hero.get('folder'),hero.get('legacy_folder'))):
            if not folder:
                continue
            member=f"heroes/{str(folder).lower()}/base/model.mdf"
            extracted=extract_member(z,arc,member,tmp)
            if not extracted:
                continue
            try:text=read_text(extracted)
            except OSError:continue
            names=re.findall(r'<anim\s+name="([^"]+)"',text,re.I)
            if names:
                data[str(folder).lower()]=names
                break
    path=os.path.join(prepared_root(root),'animation_slots.json')
    os.makedirs(os.path.dirname(path),exist_ok=True)
    with open(path,'w',encoding='utf-8') as f:
        json.dump(data,f,indent=2)
    return len(data)

def preprocess_all(root=DEFAULT_ROOT,legacy=DEFAULT_LEGACY,force_inventory=False):
    print(f"{APP} - PreparedAssets batch builder")
    print(f"Reborn: {root}")
    print(f"Old HoN: {legacy}")
    heroes,z,arc,paths,loose,packed,larcs,lmembers,cache_hit=build_inventory(root,legacy,force_inventory)
    for h in heroes:h['_root']=root
    jobs=[(h,av) for h in heroes for av in sorted(h.get('legacy',[]),key=avatar_sort)]
    total=len(jobs); clean=review=failed=0; report=[]
    tmp=tempfile.mkdtemp(prefix='onepunch_preprocess_')
    try:
        slot_cache_count=_write_animation_slot_cache(root,heroes,z,arc,tmp)
        print(f"Animation slot cache: {slot_cache_count} heroes",flush=True)
        for i,(h,av) in enumerate(jobs,1):
            t=time.time();print(f"[{i}/{total}] {h['name']} / {av} ...",flush=True)
            try:
                man=preprocess_avatar(root,h,av,z,arc,tmp,larcs,lmembers)
                st=man['status']; clean += st=='clean'; review += st!='clean'
                report.append({"hero":h['folder'],"avatar":av,"status":st,"seconds":round(time.time()-t,3),"unresolved":len(man['unresolved'])})
                print(f"    {st.upper()}  files={man['counts']['files']} unresolved={len(man['unresolved'])}  {time.time()-t:.1f}s",flush=True)
            except Exception as ex:
                failed+=1;report.append({"hero":h['folder'],"avatar":av,"status":"failed","error":str(ex)})
                print(f"    FAILED: {ex}",flush=True)
        out=os.path.join(prepared_root(root),'preprocess_report.json');os.makedirs(os.path.dirname(out),exist_ok=True)
        with open(out,'w',encoding='utf-8') as f:json.dump({"app":APP,"total":total,"clean":clean,"needs_review":review,"failed":failed,"avatars":report},f,indent=2)
        print(f"\
DONE: total={total} clean={clean} needs_review={review} failed={failed}")
        print(f"Report: {out}")
    finally:shutil.rmtree(tmp,ignore_errors=True)

def decorate_hero_selection_metadata_old(root,legacy_root,heroes,z,arc,tmp):
    """Attach the original HoN hero-list grouping/order used by the selector."""
    import xml.etree.ElementTree as ET
    legacy_order={}; legacy_attrs={}
    heroes_xml=os.path.join(legacy_root,"heroes.xml")
    if os.path.isfile(heroes_xml):
        try:
            document=ET.parse(heroes_xml).getroot()
            for index,node in enumerate(document.findall('hero')):
                path=(node.get('path') or '').replace('\\','/').strip('/').lower()
                folder=path.rsplit('/',1)[-1] if path else ''
                if folder:
                    legacy_order.setdefault(folder,index)
                    legacy_attrs.setdefault(folder,{})['attribute']=(node.get('primaryattribute') or '').lower()
        except (OSError,ET.ParseError):
            pass

    def read_entity(folder,legacy_folder):
        candidates=[]
        if legacy_folder:
            candidates.append(os.path.join(legacy_root,'heroes',legacy_folder,'hero.entity'))
        for path in candidates:
            if os.path.isfile(path):
                try:return read_text(path)
                except OSError:pass
        return ''

    for h in heroes:
        folder=h['folder'].lower()
        legacy_folder=(h.get('legacy_folder') or '').lower()
        text=read_entity(folder,legacy_folder)
        # Heroes without a historical counterpart still get their current
        # faction/attribute from the Reborn base entity.
        if not text:
            member=next((p for p in h.get('archive',{}).get('paths',[])
                         if p.replace('\\','/').lower().endswith(
                             f'heroes/{folder}/base/hero.entity')),None)
            if member:
                path=extract_member(z,arc,member,tmp)
                if path and os.path.isfile(path):
                    try:text=read_text(path)
                    except OSError:pass
        root_tag=re.search(r'<hero\b[^>]*>',text,re.I|re.S)
        attrs=_parse_attrs(root_tag.group(0)) if root_tag else {}
        attribute=(attrs.get('primaryattribute') or
                   legacy_attrs.get(legacy_folder,{}).get('attribute') or
                   'intelligence').lower()
        if attribute.startswith('agi'):attribute='agility'
        elif attribute.startswith('str'):attribute='strength'
        else:attribute='intelligence'
        team=(attrs.get('team') or '').lower()
        if team.startswith('hell'):team='Hellbourne'
        elif team.startswith('leg'):team='Legion'
        else:team='Legion'
        h['ui_attribute']=attribute
        h['ui_team']=team
        h['ui_order']=legacy_order.get(legacy_folder,10000)
    # Preserve the original roster order for known heroes and append newer
    # Reborn-only heroes consistently afterwards.
    for index,h in enumerate(sorted(heroes,key=lambda x:(x.get('ui_order',10000),x['folder'].lower()))):
        h['ui_order']=index


def decorate_hero_selection_metadata(root,legacy_root,heroes,z,arc,tmp):
    """Attach cached/lightweight selector metadata without archive extraction.

    The old implementation is retained above for comparison. Startup only
    needs the small heroes.xml grouping/order table; extracting one entity per
    hero here made an already-cached launch spend roughly twenty seconds in
    archive I/O.
    """
    import xml.etree.ElementTree as ET
    legacy_order={};legacy_attrs={}
    heroes_xml=os.path.join(legacy_root,"heroes.xml")
    if os.path.isfile(heroes_xml):
        try:
            document=ET.parse(heroes_xml).getroot()
            for index,node in enumerate(document.findall('hero')):
                path=(node.get('path') or '').replace('\\','/').strip('/').lower()
                folder=path.rsplit('/',1)[-1] if path else ''
                if folder:
                    legacy_order.setdefault(folder,index)
                    legacy_attrs.setdefault(folder,{})['attribute']=(node.get('primaryattribute') or '').lower()
        except (OSError,ET.ParseError):
            pass

    for h in heroes:
        legacy_folder=(h.get('legacy_folder') or '').lower()
        attribute=legacy_attrs.get(legacy_folder,{}).get('attribute','intelligence')
        if attribute.startswith('agi'):attribute='agility'
        elif attribute.startswith('str'):attribute='strength'
        else:attribute='intelligence'
        h['ui_attribute']=attribute
        h['ui_team']=h.get('ui_team') or 'Legion'
        h['ui_order']=legacy_order.get(legacy_folder,10000)

    for index,h in enumerate(sorted(heroes,key=lambda x:(x.get('ui_order',10000),x['folder'].lower()))):
        h['ui_order']=index


def launch_hon(root):
    exe=os.path.join(root,"bin","juvio.exe")
    if not os.path.isfile(exe):raise RuntimeError(r"bin\juvio.exe was not found.")
    # Keep K2 file caches. Deleting them on every launch forces an expensive rebuild.
    # The switcher's generated files have stable paths and are rewritten before launch.
    # Keep the user's normal HoN profile last so login.cfg and saved settings
    # are read from Documents\Juvio\Heroes of Newerth instead of the mod
    # runtime. The mod assets remain available in the earlier Runtime layer.
    mod_layers="heroes of newerth;settings;OnePunchMod/Runtime;Heroes of Newerth"
    diag(root,f'LAUNCH exe={exe} cwd={os.path.dirname(exe)} mod={mod_layers}')
    subprocess.Popen([exe,"-mod",mod_layers],
                     cwd=os.path.dirname(exe))


def discover_legacy_announcers(lmembers,root=None):
    packs=set()
    for paths in lmembers.values():
        for p in paths:
            low=p.replace("\\","/").lower().strip("/")
            m=re.search(r"(?:^|/)shared/sounds/announcer/([^/]+)/[^/]+\.(?:ogg|wav)$",low)
            if m:packs.add(m.group(1))
    if root:
        for source_root in (
            os.path.join(one_punch_root(root),"PreparedAssets","announcers"),
            os.path.join(legacy_assets_root(root),"shared","sounds","announcer"),
        ):
            if not os.path.isdir(source_root):continue
            try:entries=os.scandir(source_root)
            except OSError:continue
            with entries:
                for entry in entries:
                    if not entry.is_dir():continue
                    try:
                        if any(os.path.splitext(name)[1].lower() in (".ogg",".wav")
                               for dp,_,files in os.walk(entry.path) for name in files):
                            packs.add(entry.name.lower())
                    except OSError:pass
    return sorted(packs)

ANNOUNCER_LABELS={
    "8-bit":"8-Bit", "2018worldcup":"2018 World Cup", "ballsofsteel":"Balls of Steel",
    "bamf":"Samuel L. Jackson", "bamf_censored":"Samuel L. Jackson (Censored)",
    "breakycpk":"BreakyCPK", "dark_master":"Dark Master", "esan":"E-San", "female":"Female",
    "flamboyant":"Flamboyant", "haunted_house":"Haunted House", "merrick":"Merrick", "miku":"Miku",
    "mspudding":"MsPudding", "na_khom":"Na Khom", "ninja":"Ninja", "paragon":"Paragon",
    "pimp":"Superfly Pimp", "pirate":"Pirate", "seductive":"Seductive", "siam":"Siam Warrior",
    "soccer":"Soccer", "surfer":"Surfer", "thai":"Thai", "thai_english":"Thai English", "ursa":"URSA Corps",
    "ascension":"Ascension", "devo_wars":"Devo Wars", "graffiti":"Graffiti", "sea":"Southeast Asia"
}

def announcer_manifest(root): return os.path.join(cache_dir(root),"announcer_override_manifest.json")
def announcer_selection_file(root): return os.path.join(cache_dir(root),"announcer_selection.json")

def clear_announcer_override(root):
    mf=announcer_manifest(root)
    try:data=json.load(open(mf,"r",encoding="utf-8")) if os.path.isfile(mf) else []
    except Exception:data=[]
    for rel in data:
        p=os.path.join(switcher_root(root),*rel.split("/"))
        try:
            if os.path.isfile(p):os.remove(p)
        except OSError:pass
    try:
        if os.path.isfile(mf):os.remove(mf)
    except OSError:pass

def apply_legacy_announcer(root,pack,z=None,larcs=(),lmembers=None):
    clear_announcer_override(root)
    if not pack or pack=="default":
        json.dump({"pack":"default"},open(announcer_selection_file(root),"w",encoding="utf-8"),indent=2);return 0
    lmembers=lmembers or {}
    stage=tempfile.mkdtemp(prefix="hon_announcer_");copied=[]
    try:
        # The extracted LegacyAssets tree is the preferred source.  This keeps
        # the settings window independent from the main inventory/archive index.
        source_roots=(
            os.path.join(one_punch_root(root),"PreparedAssets","announcers",pack.lower()),
            os.path.join(legacy_assets_root(root),"shared","sounds","announcer",pack.lower()),
        )
        source_root=next((p for p in source_roots if os.path.isdir(p)),None)
        if source_root:
            destroot=os.path.join(switcher_root(root),"shared","sounds","announcer")
            for dp,_,fs in os.walk(source_root):
                relbase=os.path.relpath(dp,source_root)
                for fn in fs:
                    if os.path.splitext(fn)[1].lower() not in (".ogg",".wav"):continue
                    rel=fn if relbase=="." else os.path.join(relbase,fn)
                    src=os.path.join(dp,fn);dst=os.path.join(destroot,rel)
                    os.makedirs(os.path.dirname(dst),exist_ok=True);shutil.copy2(src,dst)
                    copied.append("shared/sounds/announcer/"+rel.replace("\\","/"))
            json.dump(copied,open(announcer_manifest(root),"w",encoding="utf-8"),indent=2)
            json.dump({"pack":pack},open(announcer_selection_file(root),"w",encoding="utf-8"),indent=2)
            return len(copied)
        if not z or not larcs:
            raise RuntimeError(f"Announcer assets for '{pack}' were not found.")
        for arc in larcs:
            wanted=[]
            needle=f"shared/sounds/announcer/{pack.lower()}/"
            for p in lmembers.get(arc,[]):
                low=p.replace("\\","/").lower().strip("/")
                if needle in low and os.path.splitext(low)[1] in (".ogg",".wav"):wanted.append(p)
            if not wanted:continue
            for i in range(0,len(wanted),100):
                _run_hidden([z,"x","-y",f"-o{stage}",arc]+wanted[i:i+100],capture_output=True,text=True,errors="replace",timeout=240)
        # Flatten pack files onto the default announcer path. This lets the existing game
        # announcer references resolve to the selected legacy voice without editing game entities.
        needle=f"/shared/sounds/announcer/{pack.lower()}/"
        destroot=os.path.join(switcher_root(root),"shared","sounds","announcer")
        os.makedirs(destroot,exist_ok=True)
        for dp,_,fs in os.walk(stage):
            normdp=dp.replace("\\","/").lower()
            pos=normdp.find(needle)
            if pos<0:continue
            relbase=dp.replace("\\","/")[pos+len(needle):]
            for fn in fs:
                src=os.path.join(dp,fn);rel=(relbase+"/"+fn).strip("/")
                dst=os.path.join(destroot,*rel.split("/"));os.makedirs(os.path.dirname(dst),exist_ok=True);shutil.copy2(src,dst)
                copied.append("shared/sounds/announcer/"+rel)
        json.dump(copied,open(announcer_manifest(root),"w",encoding="utf-8"),indent=2)
        json.dump({"pack":pack},open(announcer_selection_file(root),"w",encoding="utf-8"),indent=2)
        return len(copied)
    finally:shutil.rmtree(stage,ignore_errors=True)


from one_punch_arena_ui import ArenaUI


class App(ArenaUI,tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("One-Punch mod 1.0")
        try:
            icon=os.path.join(os.path.dirname(__file__),"HoN_Mod_Launcher.ico")
            if os.path.isfile(icon):self.iconbitmap(icon)
        except tk.TclError:
            pass
        self.rv=tk.StringVar(value=DEFAULT_ROOT);self.lv=tk.StringVar(value=DEFAULT_LEGACY)
        self.search_var=tk.StringVar();self.filter_var=tk.StringVar(value="All")
        self.status=tk.StringVar(value="Preparing your hero roster...")
        self._restore_saved_font_override()
        self.tmp=tempfile.mkdtemp(prefix="hon_avatar_v149_")
        self.cache={};self.photos=[];self.cards={};self.busy=False
        self._loading=False;self._load_generation=0
        self.protocol("WM_DELETE_WINDOW",self.destroy)
        self._build_arena()
        self._show_loading()
        self.launch_btn.configure(state="disabled")
        self.random_btn.configure(state="disabled")
        self.after(100,lambda:self.full_load(False))

    def _play_sound(self,event):
        return None

    def _get_avatar_warning(self, hero, avatar):
        return prepared_avatar_warning(self.rv.get(), hero, avatar)

    def _restore_saved_font_override(self):
        selections=saved_font_paths(self.rv.get())
        try:apply_font_roles(self.rv.get(),selections)
        except OSError:pass

    def _font_settings(self):
        entries=available_tool_fonts(self.rv.get())
        by_label={label:path for label,path in entries}
        selected=saved_font_path(self.rv.get())
        current=next((label for label,path in entries if os.path.normcase(path)==os.path.normcase(selected)),"Default HoN font")
        return entries,by_label,current

    def open_settings(self):
        script=os.path.join(os.path.dirname(__file__),"one_punch_font_settings.py")
        try:
            subprocess.Popen(
                [sys.executable,script,self.rv.get()],
                cwd=os.path.dirname(script),
                close_fds=True,
            )
            self.status.set("Font settings opened in a separate window.")
        except OSError as ex:
            messagebox.showerror(APP,f"Could not open font settings.\n\n{ex}")

    def _play_avatar_select_voice(self,hero,avatar):
        """Play one optional select_flavour line for a clicked legacy avatar."""
        root=self.rv.get()
        diag(root,f"VOICE_SELECT_CALL hero={hero.get('folder')} avatar={avatar} legacy={avatar in hero.get('legacy',[])}")
        _select_flavour_debug(root,f"VOICE_SELECT_CALL hero={hero.get('folder')} avatar={avatar} legacy={avatar in hero.get('legacy',[])}")
        if avatar not in hero.get("legacy",[]):
            diag(root,f"VOICE_SELECT_SKIP hero={hero.get('folder')} avatar={avatar} reason=not_legacy")
            _select_flavour_debug(root,f"VOICE_SELECT_SKIP hero={hero.get('folder')} avatar={avatar} reason=not_legacy")
            return
        try:
            attrs=(hero.get("legacy_info") or {}).get(avatar,{})
            diag(root,f"VOICE_SELECT_ATTRS hero={hero.get('folder')} avatar={avatar} attrs={sorted(attrs.keys())}")
            _select_flavour_debug(root,f"VOICE_SELECT_ATTRS hero={hero.get('folder')} avatar={avatar} attrs={sorted(attrs.keys())}")
            voice=_find_select_flavour_voice(root,hero,avatar,attrs)
            diag(root,f"VOICE_SELECT_RESULT hero={hero.get('folder')} avatar={avatar} file={voice or '<none>'}")
            _select_flavour_debug(root,f"VOICE_SELECT_RESULT hero={hero.get('folder')} avatar={avatar} file={voice or '<none>'}")
            if voice: play_avatar_voice(voice,root)
        except Exception as ex:
            diag(root,f"VOICE_SELECT_ERROR hero={hero.get('folder')} avatar={avatar} error={ex}")
            _select_flavour_debug(root,f"VOICE_SELECT_ERROR hero={hero.get('folder')} avatar={avatar} error={ex}")

    def browse_reborn(self):
        p=filedialog.askdirectory(initialdir=self.rv.get() or "C:\\")
        if p:self.rv.set(p);self.full_load(True)
    def browse_legacy(self):
        p=filedialog.askdirectory(initialdir=self.lv.get() or "C:\\")
        if p:self.lv.set(p);self.full_load(True)

    def get_photo(self,h,av,size):
        key=(h["key"],av,size)
        if key in self.cache:return self.cache[key]
        td=os.path.join(cache_dir(self.rv.get()),"thumbs")
        os.makedirs(td,exist_ok=True)
        disk=os.path.join(td,f"{norm(h['folder'])}_{norm(av)}_{size}.png")
        if os.path.isfile(disk):
            ph=photo(disk,size);self.cache[key]=ph;return ph
        # Reuse existing portrait sources at other display sizes before opening archives.
        for previous_size in (260,200,112,104,78,74,68,42):
            existing=os.path.join(td,f"{norm(h['folder'])}_{norm(av)}_{previous_size}.png")
            if os.path.isfile(existing):
                ph=photo(existing,size);self.cache[key]=ph;return ph
        src=None
        if av in h["legacy"]:
            src=_prepared_avatar_icon(self.rv.get(),h,av)
            if not src:src=legacy_fs_icon(self.rv.get(),h,av)
            if not src:
                a,m=legacy_icon_member(h,av,self.lmembers)
                if m:
                    src=extract_member(self.z,a,m,self.tmp)
        else:
            src=_prepared_default_icon(self.rv.get(),h) if av=="default" else None
            if not src:src=loose_icon(h,av)
            if not src:
                mem=direct_archive_icon(h,av)
                if mem:src=extract_member(self.z,self.arc,mem,self.tmp)
        png=to_png(src,self.tmp)
        if png and os.path.isfile(png):
            try:shutil.copy2(png,disk);png=disk
            except Exception:pass
        ph=photo(png,size);self.cache[key]=ph;return ph

    def _load_status(self,generation,text):
        """Publish worker progress on Tk's UI thread."""
        if generation!=self._load_generation:return
        try:self.after(0,lambda:self.status.set(text) if generation==self._load_generation else None)
        except tk.TclError:pass

    def full_load(self,force=False):
        if self._loading:
            self.status.set("The hero roster is still loading...")
            return

        self._loading=True;self.busy=True;self._load_generation+=1
        self._show_loading()
        generation=self._load_generation
        root=self.rv.get();legacy_root=self.lv.get();previous=self.focus_hero.get("key") if self.focus_hero else None
        total_start=time.time()
        self.status.set("Loading your hero roster...")
        self.progress["value"]=0
        self.launch_btn.configure(state="disabled")
        self.random_btn.configure(state="disabled")

        def worker():
            try:
                log_event(root,"STARTUP_BEGIN",detail=f"force={force}")
                self._load_status(generation,"Loading your hero roster...")
                t=time.time()
                data=build_inventory(root,legacy_root,force)
                (heroes,z,arc,paths,loose_named,packed_named,larcs,lmembers,cache_hit)=data
                log_event(root,"inventory",t,detail=f"cache_hit={cache_hit}")
                selections,selections_present=load_avatar_selections(root)
                for h in heroes:
                    h["_root"]=root
                    selected=selections.get(h["folder"].lower(),"default") if selections_present else "default"
                    h["current"]=selected if selected in h.get("avatars",{"default"}) else "default"
                log_event(root,"avatar_selections_loaded",detail=f"present={selections_present} count={len(selections)}")
                decorate_hero_selection_metadata(root,legacy_root,heroes,z,arc,self.tmp)

                announcer_packs=discover_legacy_announcers(lmembers,root)
                announcer_display={"Default":"default"}
                for pk in announcer_packs:
                    announcer_display[ANNOUNCER_LABELS.get(pk,pretty_avatar(pk))]=pk
                try:
                    sf=announcer_selection_file(root)
                    sel=json.load(open(sf,"r",encoding="utf-8")).get("pack","default") if os.path.isfile(sf) else "default"
                except Exception:sel="default"
                shown=next((k for k,v in announcer_display.items() if v==sel),"Default")

                # Resolve friendly names for ALL physically installed legacy avatars up front.
                self._load_status(generation,"Loading historical avatar names...")
                t=time.time();names=build_legacy_name_cache(root,heroes,z,larcs,lmembers,self.tmp,force=force);log_event(root,"legacy_avatar_names",t)

                # Clean only stale overrides created by old switcher builds, never third-party mods.
                t=time.time();cleanup_old_switcher_files(root);log_event(root,"cleanup_old_overrides",t)

                # Rebuild every currently selected avatar from pristine Reborn data at startup.
                # This repairs stale/incomplete output left by an older switcher version.
                self._load_status(generation,"Preparing your equipped avatars...")
                repaired=0;t=time.time()
                for h in heroes:
                    av=h.get("current","default")
                    needs_default_reset=av=="default" and os.path.isfile(override_path(root,h))
                    if (av!="default" and (av in h["legacy"] or av in h["reborn"])) or needs_default_reset:
                        try:
                            apply_avatar(root,h,av,z,arc,self.tmp,larcs,lmembers)
                            repaired+=1
                        except Exception as ex:
                            log_event(root,"startup_reapply_error",detail=f"{h['folder']} {av}: {ex}")
                log_event(root,"startup_reapply_selected",t,detail=f"count={repaired}")
                result=(heroes,z,arc,paths,loose_named,packed_named,larcs,lmembers,names,announcer_packs,announcer_display,shown,total_start)
                try:self.after(0,lambda:self._finish_full_load(result,generation,previous))
                except tk.TclError:pass
            except Exception as ex:
                try:self.after(0,lambda err=str(ex):self._finish_full_load_error(err,generation))
                except tk.TclError:pass

        threading.Thread(target=worker,daemon=True,name="one-punch-startup").start()

    def _finish_full_load(self,result,generation,previous):
        if generation!=self._load_generation:return
        try:
            (self.heroes,self.z,self.arc,self.paths,self.loose_named,self.packed_named,
             self.larcs,self.lmembers,self._names,self.announcer_packs,
             self.announcer_display,shown,total_start)=result
            self.announcer_var.set(shown)
            self.cache={};self.photos=[];self.cards={}
            self._loading=False;self.busy=False
            self.focus_hero=None
            t=time.time();self.render_all();log_event(self.rv.get(),"render_grid",t)
            selected=next((h for h in self.heroes if h["key"]==previous),None)
            if selected:self._show_hero(selected, open_picker=False)
            total=sum(len(h["avatars"]) for h in self.heroes)
            log_event(self.rv.get(),"STARTUP_END",total_start,detail=f"heroes={len(self.heroes)} choices={total}")
            self.progress["value"]=100
            self.status.set(f"Ready  /  {len(self.heroes)} heroes  /  {total} avatars  /  Choose a hero to begin.")
            self._hide_loading()
        except Exception as ex:
            self._finish_full_load_error(str(ex),generation)
            return
        self.launch_btn.configure(state="normal")
        self.random_btn.configure(state="normal")

    def _finish_full_load_error(self,error,generation):
        if generation!=self._load_generation:return
        self._loading=False;self.busy=False
        self._hide_loading()
        self.launch_btn.configure(state="normal")
        self.random_btn.configure(state="normal")
        messagebox.showerror(APP,error)
        self.status.set("Loading failed. Check the HoN installation layout.")










    def change(self,h,av):
        if self.busy:
            self.status.set("One Punch is still finishing the previous operation.");return
        # Serialize all archive/runtime writes. Multiple background 7-Zip jobs used to
        # collide on shared temp/runtime files and could raise WinError 32.
        self.busy=True
        self._show_loading()
        self.launch_btn.configure(state="disabled")
        self.random_btn.configure(state="disabled")
        self._play_sound("avatar_select")
        # Update the selector immediately while the prepared files are being
        # written.  The completion callback still marks the avatar equipped
        # only after the runtime operation succeeds.
        self.focus_hero=h;self.focus_avatar=av
        self._show_avatar(h,av)
        self.status.set(f"Applying {h['name']} -> {self.avatar_label(h,av)} in background...")
        def worker():
            t=time.time()
            try:
                n=apply_avatar(self.rv.get(),h,av,self.z,self.arc,self.tmp,self.larcs,self.lmembers)
                if av in h["legacy"]:
                    try:legacy_avatar_display_name(h,av,self.z,self.lmembers,self.tmp)
                    except Exception:pass
                log_event(self.rv.get(),"apply_avatar",t,detail=f"{h['folder']} {av} fields={n}")
                self.after(0,lambda:self._change_done(h,av,n))
            except Exception as e:
                log_event(self.rv.get(),"apply_avatar_error",t,detail=f"{h['folder']} {av}: {e}")
                self.after(0,lambda err=str(e):self._change_error(err))
        threading.Thread(target=worker,daemon=True).start()

    def _finish_single_operation(self):
        self.busy=False
        self._hide_loading()
        try:self.launch_btn.configure(state="normal")
        except Exception:pass
        try:self.random_btn.configure(state="normal")
        except Exception:pass

    def _change_error(self,err):
        self._finish_single_operation()
        self._play_sound("apply_error")
        messagebox.showerror(APP,err)

    def _change_done(self,h,av,n):
        h["current"]=av;self.refresh_card(h)
        save_avatar_selections(self.rv.get(),self.heroes)
        self._finish_single_operation();self._play_sound("apply_success")
        self.status.set(f"{self.avatar_label(h,av)} equipped for {h['name']}. Ready to play.")

    def _run_group_avatar_action(self, action):
        if self.busy:return
        if action == "random":
            targets=list(self.heroes)
            label="Applying random avatars"
        else:
            targets=list(self.heroes)
            label="Applying default avatars"
        if not targets:
            self.status.set("No heroes with alternate avatars found.");return
        self.busy=True;self._show_loading();self.launch_btn.configure(state="disabled");self.random_btn.configure(state="disabled")
        self.progress["value"]=0
        self.status.set("Checking prepared avatars..." if action == "random" else f"{label} 0/{len(targets)} heroes...")
        def worker():
            done=0;t=time.time();skipped_bad=0
            if action == "random":
                eligible=[]
                for h in targets:
                    choices=[]
                    for av in h["avatars"]:
                        if av == "default":
                            continue
                        if self._get_avatar_warning(h,av):
                            skipped_bad += 1
                            continue
                        choices.append(av)
                    if choices:
                        eligible.append((h,choices))
                work=eligible
            else:
                work=[(h,["default"]) for h in targets]
            total=len(work)
            if not total:
                log_event(self.rv.get(),"group_avatar_action",t,
                          detail=f"action={action} done=0 total=0 skipped_bad={skipped_bad}")
                self.after(0,lambda:self._random_done(0,0,"No safe alternate avatars found"))
                return
            self.after(0,lambda:self.status.set(f"{label} 0/{total} heroes..."))
            for i,(h,choices) in enumerate(work,1):
                av=random.choice(choices) if action == "random" else "default"
                try:
                    apply_avatar(self.rv.get(),h,av,self.z,self.arc,self.tmp,self.larcs,self.lmembers)
                    h["current"]=av;done+=1
                    self.after(0,lambda H=h:self.refresh_card(H))
                except Exception as ex:
                    log_event(self.rv.get(),"group_action_error",detail=f"action={action} hero={h['folder']} avatar={av}: {ex}")
                pct=i*100/total
                self.after(0,lambda I=i,P=pct:self._random_progress(I,total,P))
            log_event(self.rv.get(),"group_avatar_action",t,
                      detail=f"action={action} done={done} total={total} skipped_bad={skipped_bad}")
            self.after(0,lambda:self._random_done(done,total,label))
        threading.Thread(target=worker,daemon=True).start()

    def apply_random_avatars_to_all(self):
        self._run_group_avatar_action("random")

    def apply_default_avatars_to_all(self):
        self._run_group_avatar_action("default")

    def randomize_defaults(self):
        # Compatibility entry point for older callers.
        self.apply_random_avatars_to_all()

    def _random_progress(self,i,total,pct):
        self.progress["value"]=pct
        self.status.set(f"Randomizing {i}/{total} Default heroes... {pct:.0f}%")

    def _random_done(self,done,total,label="Group action complete"):
        save_avatar_selections(self.rv.get(),self.heroes)
        self.progress["value"]=100;self.busy=False;self._hide_loading()
        self.launch_btn.configure(state="normal");self.random_btn.configure(state="normal")
        self.status.set(f"{label}: {done}/{total} heroes changed.")




    def change_announcer(self):
        if self.busy:
            self.status.set("One Punch is still finishing the previous operation.");return
        self.busy=True
        self._show_loading()
        self.launch_btn.configure(state="disabled")
        self.random_btn.configure(state="disabled")
        label=self.announcer_var.get();pack=getattr(self,"announcer_display",{}).get(label,"default")
        self.status.set(f"Applying announcer: {label}...")
        def worker():
            try:
                n=apply_legacy_announcer(self.rv.get(),pack,self.z,self.larcs,self.lmembers)
                self.after(0,lambda:self._announcer_done(label,n))
            except Exception as ex:self.after(0,lambda err=str(ex):self._change_error(err))
        threading.Thread(target=worker,daemon=True).start()

    def _announcer_done(self,label,n):
        self._finish_single_operation()
        self.status.set(f"Announcer: {label} ({n} legacy sound files overlaid).")





    def launch_game(self):
        if self.busy:
            self.status.set("Wait for the current batch operation to finish before launching HoN.");return
        try:
            self.busy=True
            self.launch_btn.configure(state="disabled")
            self.random_btn.configure(state="disabled")
            self._show_loading()
            self._play_sound("launch_game")
            launch_hon(self.rv.get())
            self.status.set('Launched: bin\\juvio.exe -mod "heroes of newerth;settings;OnePunchMod/Runtime;Heroes of Newerth"')
            # juvio remains alive for the whole game session, so process exit
            # cannot identify the end of startup. Keep the modal layer over the
            # tool during the normal HoN launch window, then return control.
            self.after(6000, self._launch_done)
        except Exception as e:
            self.busy=False
            self._hide_loading()
            self.launch_btn.configure(state="normal")
            self.random_btn.configure(state="normal")
            messagebox.showerror(APP,str(e))

    def _launch_done(self):
        self.busy=False
        self._hide_loading()
        self.launch_btn.configure(state="normal")
        self.random_btn.configure(state="normal")
    def destroy(self):
        try:
            if hasattr(self,"heroes"):
                save_avatar_selections(self.rv.get(),self.heroes)
        except Exception:
            pass
        from one_punch_ui_audio import close
        close()
        shutil.rmtree(self.tmp,ignore_errors=True);super().destroy()

if __name__=="__main__":
    import sys

    if "--regenerate-default-icons" in sys.argv:
        root = DEFAULT_ROOT
        legacy = DEFAULT_LEGACY
        print(f"{APP} - default portrait rebuild")
        heroes,z,arc,paths,loose,packed,larcs,lmembers,cache_hit = build_inventory(
            root, legacy, False
        )
        tmp = tempfile.mkdtemp(prefix="onepunch_default_icons_")
        try:
            print(regenerate_prepared_default_icons(root, heroes, z, arc, tmp))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    elif "--preprocess-one" in sys.argv:
        try:
            hero_name = sys.argv[sys.argv.index("--preprocess-one") + 1]
            avatar_name = sys.argv[sys.argv.index("--preprocess-one") + 2]
        except (ValueError, IndexError):
            print("Usage: --preprocess-one HERO AVATAR")
            sys.exit(2)

        root = DEFAULT_ROOT
        legacy = DEFAULT_LEGACY

        print(f"{APP} - single avatar builder")
        print(f"Hero: {hero_name}")
        print(f"Avatar: {avatar_name}")

        heroes,z,arc,paths,loose,packed,larcs,lmembers,cache_hit = build_inventory(
            root, legacy, False
        )

        for h in heroes:
            h["_root"] = root

        wanted = hero_name.lower().replace(" ", "").replace("_", "")
        hero = next(
            (
                h for h in heroes
                if h["name"].lower().replace(" ", "").replace("_", "") == wanted
                or h["folder"].lower().replace(" ", "").replace("_", "") == wanted
            ),
            None
        )

        if hero is None:
            raise RuntimeError(f"Hero not found: {hero_name}")

        if avatar_name not in hero.get("legacy", []):
            raise RuntimeError(
                f"Legacy avatar not found: {hero['name']} / {avatar_name}"
            )

        tmp = tempfile.mkdtemp(prefix="onepunch_preprocess_one_")
        try:
            man = preprocess_avatar(
                root, hero, avatar_name,
                z, arc, tmp, larcs, lmembers
            )

            print()
            print("DONE")
            print(f"Status: {man['status']}")
            print(f"Files: {man['counts']['files']}")
            print(f"Unresolved: {len(man['unresolved'])}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    elif "--preprocess-all" in sys.argv:
        preprocess_all()

    else:
        print(f"{APP} - PreparedAssets command-line builder")
        print("Usage:")
        print("  python one_punch_preprocess.py --preprocess-all")
        print("  python one_punch_preprocess.py --preprocess-one HERO AVATAR")
        print("  python one_punch_preprocess.py --regenerate-default-icons")

