import os, re, json, shutil, subprocess, tempfile, tkinter as tk, time, threading, random, traceback

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
GRID_COLS = 3
CURRENT_SIZE = 74
AVATAR_SIZE = 78



def avatar_selections_path(root):
    """User-owned avatar selections; safe to remove before packaging a release."""
    return os.path.join(root, "OnePunchMod", "one_punch_avatar_selections.json")


def load_avatar_selections(root):
    """Load saved choices and report whether the file was present and valid."""
    path = avatar_selections_path(root)
    if not os.path.isfile(path):
        return {}, False
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        values = data.get("avatars", data) if isinstance(data, dict) else {}
        if not isinstance(values, dict):
            return {}, False
        return {str(k).lower(): str(v).lower() for k, v in values.items()}, True
    except (OSError, ValueError, TypeError):
        return {}, False


def save_avatar_selections(root, heroes):
    """Atomically persist the currently equipped avatar for every hero."""
    path = avatar_selections_path(root)
    values = {}
    for hero in heroes or []:
        folder = str(hero.get("folder", "")).lower()
        current = str(hero.get("current", "default")).lower()
        if folder:
            values[folder] = current if current in set(hero.get("avatars") or {"default"}) else "default"
    payload = {"version": 1, "avatars": values}
    temporary = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(temporary, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(temporary, path)
        return True
    except OSError:
        try:
            if os.path.isfile(temporary):
                os.remove(temporary)
        except OSError:
            pass
        return False


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


# OnePunchMod.log is a user-facing diagnostic log. Keep lifecycle events,
# repairs, fallbacks, warnings and errors, but suppress the large per-file
# dependency/entity dumps that are useful only during development.
_DIAG_KEEP_PREFIXES = (
    "MOD_OVERLAY_SYNC",
    "PROFILE_FILE",
    "PROFILE_FILES",
    "PRISTINE_ENTITY",
    "REF_REPAIR_DONE",
    "BODY_SHELL_SUPPRESS",
    "ABILITY_OVERLAY_SKIP",
    "ABILITY_OVERLAY_DONE",
    "EXPLICIT_GRAPH_DONE",
    "PREPARED_PUBLISH",
    "PREPARED_INSTALL",
    "FAST_RECIPE_SAVE",
    "FAST_RECIPE_RESTORE",
    "PREPARED_ENTITY_REFS_REPAIRED",
    "APPLY ",
    "ABILITY_RUNTIME_OVERRIDES",
    "REBORN_MODIFIER_COSMETICS",
    "COSMETIC_ENTITY_FALLBACK",
    "AVATAR_VOICE_REFS_REPAIRED",
    "MATERIAL_COMPAT_DONE",
    "PREPARED_VISUAL_REPAIRS",
    "TEXTURE_REF_REPAIR",
    "MORPH_MODEL_REPAIR",
    "ANIMATION_CLIP_UNRESOLVED",
    "ANIMATION_CLIP_REPAIR",
    "ANIMATION_SLOT_REPAIR",
    "SHARED_EFFECT_COMPAT",
    "LAUNCH ",
    "VANITY_APPLY",
    "VOICE_SELECT_CALL",
    "VOICE_SELECT_SKIP",
    "VOICE_SELECT_RESULT",
    "VOICE_SELECT_ERROR",
    "VOICE_PLAY_SKIP",
)


def clear_diagnostic_log(root):
    """Start each tool session with a fresh, bounded diagnostic log."""
    path = diagnostic_log_path(root)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + " | SESSION_START\n")
    except OSError:
        pass


def diag(root,msg=""):
    message = str(msg)
    upper = message.upper()
    relevant = message.startswith(_DIAG_KEEP_PREFIXES) or any(
        marker in upper for marker in ("ERROR", "FAIL", "UNRESOLVED")
    )
    if not relevant:
        return
    try:
        with open(diagnostic_log_path(root),"a",encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S")+" | "+message+"\n")
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

def avatar_display_name(hero,av,names):
    """Resolve an avatar label without trusting stale cross-hero folder maps."""
    if av=="default":
        return "Original"
    folder=str(hero.get("folder") or "").lower()
    identities=[folder]
    for alias in LEGACY_ALIASES.get(folder,()):
        alias=str(alias).lower()
        if alias not in identities:
            identities.append(alias)
    # The old cache can contain a useful physical namespace for a hero whose
    # direct key was not recorded, but only accept it when it is a declared
    # alias. Never use an arbitrary resolved legacy_folder here: that cache
    # previously caused Accursed, Aluna, and others to display Zephyr names.
    for identity in identities:
        known=KNOWN_AVATAR_NAMES.get("hero_"+identity,{})
        if av in known and known[av]:
            return known[av]
        value=(names or {}).get(f"{identity}::{av}".lower())
        if value and value.lower()!=pretty_avatar(av).lower():
            return value
    return pretty_avatar(av)

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
        os.path.join(one_punch_root(root), "tools", "7za.exe"),
        os.path.join(one_punch_root(root), "tools", "7z.exe"),
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

def sync_mod_overlay(root):
    """Build the small final overlay used to keep HoN's profile layer active.

    Runtime remains the editable loose layer containing the prepared models,
    textures, sounds and effects.  Only generated hero base entities are copied
    into the final ``mods`` archive.  HoN then keeps its writable profile under
    Documents\\Juvio\\Heroes of Newerth while still resolving the selected hero
    entities and the prepared assets from OnePunchMod.
    """
    runtime=switcher_root(root)
    mods=os.path.join(root,"mods")
    os.makedirs(mods,exist_ok=True)
    stage=tempfile.mkdtemp(prefix="mods_overlay_",dir=cache_dir(root))
    archive=os.path.join(mods,"resources0.jz")
    temporary=archive+".new"
    copied=0
    try:
        marker=os.path.join(stage,"one_punch_overlay.manifest")
        write_text(marker,"Generated by One Punch Mod. Do not edit.\n")
        source_root=os.path.join(runtime,"heroes")
        if os.path.isdir(source_root):
            for hero_dir in os.scandir(source_root):
                if not hero_dir.is_dir():continue
                source=os.path.join(hero_dir.path,"base","hero.entity")
                if not os.path.isfile(source):continue
                target=os.path.join(stage,"heroes",hero_dir.name,"base","hero.entity")
                os.makedirs(os.path.dirname(target),exist_ok=True)
                shutil.copy2(source,target)
                copied+=1
        z=find_7za(root)
        if not z:
            raise RuntimeError("7za.exe is required to build the HoN mods overlay.")
        if os.path.isfile(temporary):os.remove(temporary)
        cp=_run_hidden([z,"a","-tzip","-mx=0",temporary,"*","-r"],
                       cwd=stage,capture_output=True,text=True,errors="replace",timeout=180)
        if cp.returncode:
            raise RuntimeError(cp.stderr or cp.stdout or "Could not build mods\\resources0.jz")
        os.replace(temporary,archive)
        diag(root,f"MOD_OVERLAY_SYNC files={copied} archive={archive} bytes={os.path.getsize(archive)}")
        return copied
    finally:
        try:shutil.rmtree(stage,ignore_errors=True)
        except OSError:pass
        try:
            if os.path.isfile(temporary):os.remove(temporary)
        except OSError:pass

def ensure_mod_profile_login(root):
    """Expose the user's existing HoN profile state to the final mods profile.

    Juvio resolves ``#/login.cfg`` relative to the final mod profile.  The
    credentials and saved login state are owned by the normal HoN profile, so
    create local hard links at the paths Juvio reads instead of copying them
    into the tool.
    """
    documents=os.path.join(os.path.expanduser("~"),"Documents")
    normal=os.path.join(documents,"Juvio","Heroes of Newerth")
    mod=os.path.join(documents,"Juvio","mods")
    os.makedirs(mod,exist_ok=True)
    shared=(
        "login.cfg",
        "startup.cfg",
        "game_settings_local.cfg",
        "srp.txt",
        "persistentselectiongroups.json",
        "voice_config.cfg",
    )
    linked=0
    for name in shared:
        source=os.path.join(normal,name)
        target=os.path.join(mod,name)
        if not os.path.isfile(source):
            continue
        try:
            if os.path.exists(target):
                if os.path.isfile(target) and os.path.samefile(source,target):
                    linked+=1
                    continue
                if os.path.isdir(target):
                    raise RuntimeError(f"Cannot share HoN profile file because the target is a directory: {target}")
                os.remove(target)
            os.link(source,target)
            linked+=1
        except OSError as ex:
            # A same-volume hard link is the normal path.  Copy only as a
            # local runtime fallback; these files are never packaged.
            try:
                shutil.copy2(source,target)
                linked+=1
                diag(root,f"PROFILE_FILE copied_fallback name={name} reason={ex}")
            except OSError as copy_ex:
                raise RuntimeError(f"Could not share HoN profile file '{name}': {copy_ex}")
    if linked:
        diag(root,f"PROFILE_FILES_SHARED count={linked} target={mod}")
    else:
        diag(root,f"PROFILE_FILES source_missing={normal}")
    return linked>0

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


def _hero_path_parts(p):
    low=p.lower().replace("\\","/").strip("/")
    m=re.search(r"(?:^|/)heroes/([^/]+)/(.*)$",low)
    return (m.group(1),m.group(2)) if m else (None,None)


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
    # Pandamonium's current Reborn folder is pandamonium, while the prepared
    # legacy avatar packages and their generated entity references use panda.
    # Keep both namespaces in every animation/material repair pass.
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




def cache_path(root): return os.path.join(root,"OnePunchMod","Cache","hon_avatar_switcher_cache_v135.json")

def archive_signature(paths):
    out={}
    for p in paths:
        if os.path.isfile(p):
            key=os.path.normcase(os.path.abspath(p).replace("/","\\"))
            st=os.stat(p);out[key]={"size":st.st_size,"mtime_ns":st.st_mtime_ns}
    return out


def is_real_hero_folder(folder):
    f=_simple_name(folder)
    return f not in {"innateabilities","innateability","innates","abilities","shared","tutorial"}



def _prepared_avatar_dirs(root, hero_folder):
    """Return prepared avatar package names without consulting source assets."""
    base=os.path.join(prepared_root(root),"recipes",hero_folder.lower())
    if not os.path.isdir(base):
        return []
    result=[]
    try: entries=os.scandir(base)
    except OSError: return result
    with entries:
        for entry in entries:
            if not entry.is_dir():
                continue
            if os.path.isfile(os.path.join(entry.path,"recipe.json")):
                result.append(entry.name.lower())
    return result

def _prepared_entity_namespace(root, hero_folder):
    """Read the physical hero namespace recorded by prepared entity files.

    A Reborn hero can have a modern folder name while its prepared avatar
    assets live under a historical namespace (for example blacksmith ->
    dwarf_magi).  The generated base entity is the authoritative record. Do
    not infer this relationship from avatar-name overlap or stale cache data.
    """
    modern=str(hero_folder or '').lower()
    base=os.path.join(prepared_root(root),"heroes",modern,"base","hero.entity")
    if not os.path.isfile(base):
        return None
    try:
        text=read_text(base)
    except OSError:
        return None
    counts={}
    for match in re.finditer(r'(?i)/heroes/([^/]+)/([^"\s<>]+)',text):
        namespace=match.group(1).lower()
        tail=match.group(2).strip('/')
        if not os.path.isdir(os.path.join(prepared_root(root),"heroes",namespace)):
            continue
        score=1
        first=tail.split('/',1)[0] if tail else ''
        if first and os.path.isdir(os.path.join(
                prepared_root(root),"heroes",namespace,first)):
            score+=3
        candidate=os.path.join(prepared_root(root),"heroes",namespace,*tail.split('/'))
        if os.path.isfile(candidate):
            score+=2
        stem,ext=os.path.splitext(candidate)
        alternatives=[]
        if ext.lower() in ('.tga','.png'):
            alternatives.append(stem+'.dds')
        elif ext.lower()=='.wav':
            alternatives.append(stem+'.ogg')
        if any(os.path.isfile(p) for p in alternatives):
            score+=1
        counts[namespace]=counts.get(namespace,0)+score
    # Some prepared base entities keep their asset references relative to
    # ``base/``.  In that case the selected-avatar recipes still contain the
    # authoritative absolute namespace (for example Glacius recipes point to
    # ``/heroes/frosty/...``).  Read those recipes before falling back to the
    # modern folder name; this keeps a clean Runtime rebuild self-contained.
    if not counts:
        recipe_root=os.path.join(prepared_root(root),"recipes",modern)
        if os.path.isdir(recipe_root):
            for dp,_,files in os.walk(recipe_root):
                for fn in files:
                    if fn.lower() != "hero.entity":
                        continue
                    path=os.path.join(dp,fn)
                    try: recipe_text=read_text(path)
                    except OSError: continue
                    for match in re.finditer(r'(?i)/heroes/([^/]+)/',recipe_text):
                        namespace=match.group(1).lower()
                        if os.path.isdir(os.path.join(prepared_root(root),"heroes",namespace)):
                            counts[namespace]=counts.get(namespace,0)+1
    return max(counts,key=lambda value:(counts[value],value)) if counts else None

def _load_prepared_avatar_names(root):
    path=os.path.join(cache_dir(root),"avatar_names.json")
    try:
        data=json.load(open(path,"r",encoding="utf-8"))
        return data if isinstance(data,dict) else {}
    except (OSError,ValueError,TypeError):
        return {}

def build_prepared_inventory(root,force=False):
    """Build the public roster from HoN plus PreparedAssets only.

    This is intentionally separate from the developer inventory builder below.
    It never scans, indexes, extracts, or falls back to developer source assets.
    """
    z=find_7za(root);arc=find_archive(root)
    if not arc:
        raise RuntimeError("Reborn resources0.jz was not found under the selected HoN directory.")
    if not z:
        raise RuntimeError("7-Zip command-line tool was not found. Put 7za.exe in <HoN>\\tools\\.")
    cp=cache_path(root)
    cached=None;cache_hit=False
    if not force and os.path.isfile(cp):
        try: cached=json.load(open(cp,"r",encoding="utf-8"))
        except (OSError,ValueError,TypeError): cached=None
    paths=None
    if isinstance(cached,dict):
        old_paths=cached.get("reborn_paths")
        current_signature=archive_signature([arc])
        same_root=(os.path.normcase(os.path.abspath(str(cached.get("reborn_root") or "")))
                   ==os.path.normcase(os.path.abspath(root)))
        if (old_paths and same_root
                and cached.get("signature")==current_signature):
            paths=old_paths;cache_hit=True
    if paths is None:
        paths=list_archive(z,arc)
    ai=archive_index(paths);ki=scan_kongor(root);oi=scan_active_overrides(root)
    loose_named,packed_named=build_named_icons(root,paths)
    resolved=(cached or {}).get("resolved_legacy_map",{}) if isinstance(cached,dict) else {}
    legacy_index_data=(cached or {}).get("legacy_index",{}) if isinstance(cached,dict) else {}
    heroes=[]
    for key in sorted(ai):
        a=ai[key]
        if not is_real_hero_folder(a["folder"]):
            continue
        o=oi.get(key);current=o["current"] if o else "default"
        folder=a["folder"]
        # Prefer a known historical alias when its prepared namespace exists.
        # The persisted resolver cache can contain an old heuristic match from
        # a previous asset set (for example War Beast -> zephyr).  Reusing that
        # stale value sends morphs, portraits, and projectiles to the wrong
        # hero namespace even though the correct package is present.
        aliases=LEGACY_ALIASES.get(folder.lower(),())
        alias_folder=next((a for a in aliases if os.path.isdir(
            os.path.join(prepared_root(root),"heroes",a))),None)
        prepared_namespace=_prepared_entity_namespace(root,folder)
        # PreparedAssets is self-contained: use its recorded namespace, an
        # explicit alias, or the modern package itself. Never revive the old
        # resolver cache here; it can contain unrelated cross-hero matches
        # from earlier inventory scans.
        legacy_folder=alias_folder or prepared_namespace or folder
        if not legacy_folder:
            legacy_folder=folder
        legacy_folder=str(legacy_folder).lower()
        info=legacy_index_data.get(legacy_folder,{})
        stub={"key":key,"folder":folder,"name":pretty_hero(folder),"archive":a,
              "legacy_folder":legacy_folder,"legacy_info":info}
        prepared=[]
        for av in _prepared_avatar_dirs(root,folder):
            if _prepared_avatar_available(root,stub,av):
                prepared.append(av)
        reborn={"default"}|set(a["alts"])
        heroes.append({"key":key,"folder":folder,"legacy_folder":legacy_folder,
          "name":pretty_hero(folder),"archive":a,"kongor":ki.get(key),"override":o,
          "current":current,"avatars":sorted(reborn|set(prepared),key=avatar_sort),
          "reborn":reborn,"legacy":set(prepared),"legacy_info":info})
    names=_load_prepared_avatar_names(root)
    named_by_folder={}
    for raw_key in names:
        if "::" not in str(raw_key):
            continue
        physical,av=str(raw_key).lower().split("::",1)
        named_by_folder.setdefault(physical,set()).add(av)
    # Namespace resolution is complete above from PreparedAssets entity data
    # and explicit aliases. Never infer a physical hero folder from matching
    # avatar names in this cache: unrelated heroes often share alt keys.
    # Keep the cache useful when the source package is absent: display names are
    # data already generated during preprocessing, not a runtime source lookup.
    for h in heroes:
        for av in h["legacy"]:
            key=f"{h['legacy_folder']}::{av}".lower()
            names.setdefault(key,pretty_avatar(av))
    prepared_name_index={
        physical:{av:{} for av in avatars}
        for physical,avatars in named_by_folder.items()
    }
    cached_index=(cached or {}).get("legacy_index",{}) if isinstance(cached,dict) else {}
    if not cached_index:
        cached_index=prepared_name_index
    try:
        current_cache={
            "version":1300,
            "reborn_root":root,
            "signature":archive_signature([arc]),
            "reborn_paths":paths,
            # Preserve developer metadata as inert cache data if it already
            # exists; the launcher never reads it to discover or build assets.
            "resolved_legacy_map":{h["folder"].lower():h.get("legacy_folder",h["folder"]) for h in heroes},
            "legacy_index":cached_index,
            "legacy_members":(cached or {}).get("legacy_members",{}) if isinstance(cached,dict) else {},
            "legacy_folders":(cached or {}).get("legacy_folders",{}) if isinstance(cached,dict) else {},
            "legacy_internal_map":(cached or {}).get("legacy_internal_map",{}) if isinstance(cached,dict) else {},
            "legacy_display_map":(cached or {}).get("legacy_display_map",{}) if isinstance(cached,dict) else {},
        }
        with open(cp,"w",encoding="utf-8") as f:
            json.dump(current_cache,f,ensure_ascii=False)
    except OSError:
        pass
    return heroes,z,arc,paths,loose_named,packed_named,(),{},cache_hit,names

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


def loose_icon(hero,av):
    k=hero.get("kongor")
    if not k:return None
    hd=k["hero_dir"];bd=k["base_dir"];cs=[]
    for ext in ("png","tga","dds"):
        if av=="default":cs += [os.path.join(hd,f"icon.{ext}"),os.path.join(bd,f"icon.{ext}")]
        else:cs += [os.path.join(bd,av,f"icon.{ext}"),os.path.join(hd,av,f"icon.{ext}")]
    return next((p for p in cs if os.path.isfile(p)),None)



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
    # Runtime is the ONLY One Punch layer mounted by Juvio. developer source assets is source-only.
    return os.path.join(one_punch_root(root),"Runtime")


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
    legacy=(hero.get("legacy_folder") or hero["folder"]).lower()
    modern=hero["folder"].lower()
    shell_files=[]
    for asset_root in (switcher_root(root),prepared_root(root)):
        for namespace in {legacy,modern}:
            base=os.path.join(asset_root,"heroes",namespace,av.lower())
            for rel in BODY_SHELL_FILES:
                shell_files.append(os.path.join(base,*rel.split("/")))
    removed=0
    for q in shell_files:
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
    logical=raw.lstrip('/')
    parts=[x for x in logical.split('/') if x and x not in ('.','..')]
    if len(parts)<2 or parts[0].lower()!='heroes':
        return ref
    # Recipe replay runs entirely from the files already published in the
    # Runtime/PreparedAssets layers. Do not consult the removed source index.
    physical=[]
    for base in (switcher_root(root),prepared_root(root)):
        candidate=os.path.join(base,*parts)
        physical.append((logical,candidate))
        stem=os.path.splitext(candidate)[0]
        if ext in ('.tga','.png'):
            physical.append((logical,stem+'.dds'))
        elif ext=='.dds':
            physical.extend(((logical,stem+'.tga'),(logical,stem+'.png')))
    hits=[(name,path,'runtime') for name,path in physical if os.path.isfile(path)]
    if not hits:
        # The entity may use a relative avatar path. The generated package
        # checker already validates the owning hero tree, so test the same
        # path through the runtime hero namespace before giving up.
        hits=[]
        for base in (switcher_root(root),prepared_root(root)):
            candidate=os.path.join(base,'heroes',*parts[2:])
            if os.path.isfile(candidate):hits.append((logical,candidate,'runtime'))
        if not hits:return ref
    # The engine uses normal.tga as the logical name for the paired
    # normal_rxgb.dds/normal_s.dds representation.  Rewriting it to only one
    # DDS component would discard half of the normal map.
    if re.fullmatch(r"normal\d*",os.path.basename(os.path.splitext(raw.split(",",1)[0])[0]).lower()):
        stem_name=os.path.basename(os.path.splitext(raw.split(",",1)[0])[0]).lower()
        if any(os.path.basename(x[0]).lower() in (stem_name+"_rxgb.dds",stem_name+"_s.dds") for x in hits):
            return ref
    physical_ext = os.path.splitext(hits[0][1])[1].lower()
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

    These files are normally stored at ``<avatar>/sounds/voice``. Search the
    prepared and runtime copies. The physical package may differ from the
    logical avatar key (Trophy skins are one example), so both names are used.
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
    roots=[prepared_root(root),switcher_root(root)]
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

    # The recipe is the package manifest. Physical model names can differ from
    # the avatar key, so availability must not guess a model path from source
    # metadata that is intentionally absent in the player release.
    return True


def _prepared_ref_path(root, base_dir, ref):
    """Resolve a model/animation reference inside the packaged asset tree."""
    ref = str(ref or '').replace('\\', '/').strip()
    if not ref:
        return None
    if ref.startswith('/'):
        return os.path.join(prepared_root(root), *ref.lstrip('/').split('/'))
    return os.path.normpath(os.path.join(base_dir, *ref.split('/')))


def _prepared_model_health(root, model_path):
    """Validate the dependency graph that HoN needs to render a prepared model.

    A recipe can exist and still produce HoN's teapot fallback when its MDF
    points at missing renderable geometry.  This check intentionally stays
    conservative: it only reports geometry files explicitly referenced by a
    readable MDF and never treats optional animation clips as a teapot fault.
    """
    try:
        model_text = read_text(model_path)
    except OSError:
        return ""
    if not model_text.lstrip().startswith('<'):
        # Binary model formats cannot be inspected safely here.  The MDF
        # existence check above still protects the common broken-package case.
        return ""

    missing = []
    model_dir = os.path.dirname(model_path)

    # The high-detail geometry is the critical dependency for the teapot
    # fallback.  HoN can use the high model when lower LOD files are absent,
    # so missing med/low files alone are not enough to mark an avatar broken.
    # `file` may name an authoring source such as rig.max, so it is deliberately
    # not validated.
    for attr in ('high',):
        match = re.search(r'\b' + attr + r'\s*=\s*"([^"]+)"', model_text, re.I)
        if not match:
            continue
        ref = match.group(1)
        path = _prepared_ref_path(root, model_dir, ref)
        if path and not os.path.isfile(path):
            missing.append(ref)

    if not missing:
        return ""
    unique = []
    for ref in missing:
        if ref not in unique:
            unique.append(ref)
    shown = ', '.join(unique[:4])
    extra = f" and {len(unique) - 4} more" if len(unique) > 4 else ""
    return (
        "Model dependencies are missing ("
        + shown + extra
        + "); HoN may show a teapot."
    )


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
    model_warning = _prepared_model_health(root, candidate)
    if model_warning:
        return model_warning
    return ""


def find_prepared_teapot_candidates(root, heroes):
    """Return prepared avatars whose model graph is likely to become a teapot.

    The scan is intentionally on demand because parsing every avatar package
    would make the launcher slower.  The avatar warning path calls the same
    validator lazily, so the UI marker and group randomization stay consistent
    with this report.
    """
    candidates = []
    for hero in heroes or []:
        for avatar in sorted(hero.get('legacy') or set(), key=avatar_sort):
            warning = prepared_avatar_warning(root, hero, avatar)
            if warning and 'teapot' in warning.lower():
                candidates.append({
                    'hero': hero.get('folder', ''),
                    'avatar': avatar,
                    'warning': warning,
                })
    return candidates


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
                if not selected_names or not rel_file.lower().startswith(av.lower()+"/"):
                    continue
                try:entity_text=read_text(os.path.join(dp,fn))
                except OSError:continue
                named=re.search(r'<\s*[A-Za-z_][A-Za-z0-9_.:-]*\b[^>]*\bname\s*=\s*"([^"]+)"',entity_text,re.I|re.S)
                if not named or named.group(1).strip().lower() not in selected_names:
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
    """End-user fast path: install already-normalized files; no developer source assets scanning/parsing."""
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
    # Repair older prepared packages as they are mounted. This remains fully
    # PreparedAssets/Runtime based and does not re-enter the developer source
    # pipeline.
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
    ):
        raise RuntimeError(
            f"{hero['name']} / {new} is unavailable: its PreparedAssets package is missing."
        )


    if new in hero["legacy"]:
        # The published tool has one source of historical avatar assets:
        # PreparedAssets. Missing packages are reported instead of being built
        # from a developer-only source tree.
        if not _prepared_avatar_available(root,hero,new):
            raise RuntimeError(
                f"{hero['name']} / {new} is unavailable: its PreparedAssets package is missing."
            )
        if not _install_prepared_avatar(root,hero,new):
            raise RuntimeError(
                f"{hero['name']} / {new} could not be installed from PreparedAssets."
            )
        return 0
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
                for m in LEGACY_REF_RE.finditer(' '+txt):
                    ref=m.group(1); low=ref.replace('\\\\','/').lower()
                    if av.lower() not in low and f'heroes/{lf}/' not in low:continue
                    owner='heroes/'+hero['folder'].lower()+'/'+os.path.relpath(fp,ph).replace('\\\\','/')
                    hits=_resolve_legacy_logical_path(root,ref,owner)
                    if not hits:unresolved.append({"owner":rel,"ref":ref})
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

_RELATIVE_TEXTURE_EXTS={".tga",".dds",".png"}

def _texture_ref_replacement(owner_path, raw_ref, package_root):
    """Find the packaged texture represented by a relative legacy reference.

    Legacy materials frequently say ``color.tga`` or ``../../../color.tga``
    while the normalized package contains ``color.dds``.  HoN resolves this
    through its archive index in the original client, but a loose prepared
    package needs the reference itself to land on a real file.  Normal maps
    are special: ``normal.tga`` is the logical name for a paired
    ``normal_rxgb.dds``/``normal_s.dds`` set.
    """
    raw=str(raw_ref or '').replace('\\','/')
    if not raw or raw.startswith('/') or '%' in raw or ',' in raw:
        return None
    ext=os.path.splitext(raw)[1].lower()
    if ext not in _RELATIVE_TEXTURE_EXTS:
        return None
    owner_dir=os.path.dirname(owner_path)
    exact=os.path.normpath(os.path.join(owner_dir,*raw.split('/')))
    if os.path.isfile(exact):
        return None

    rel_dir=os.path.dirname(raw)
    base_name=os.path.basename(raw)
    stem=os.path.splitext(base_name)[0]
    is_normal=bool(re.fullmatch(r'normal\d*',stem,re.I))

    def logical(path):
        value=os.path.relpath(path,owner_dir).replace('\\','/')
        return value if value != '.' else base_name

    def alternatives(directory):
        # PreparedAssets is mounted as loose files. HoN's archive index can
        # resolve ``normal.tga`` to the paired channels, but that lookup is not
        # available for a loose mod overlay. Point the material at the normal
        # channel explicitly and keep the packed specular channel in the
        # material's separate ``normal_s.dds`` sampler.
        if is_normal and all(os.path.isfile(os.path.join(directory,x))
                             for x in (stem+'_rxgb.dds',stem+'_s.dds')):
            return os.path.join(directory,stem+'_rxgb.dds')

        # Some legacy materials call the packed specular channel
        # ``spec_color.tga`` even though the prepared package stores that
        # channel beside the normal map as ``normal_s.dds``.  Reborn treats a
        # missing specular sampler as a white fallback; with the old
        # full-reflect shaders that makes the complete model, including
        # attached weapons, render white.  Use the physical packed channel
        # only when the requested spec_color file is absent and normal_s.dds
        # is present in the same material directory.
        if stem.lower() == 'spec_color':
            packed_spec = os.path.join(directory, 'normal_s.dds')
            if os.path.isfile(packed_spec):
                return packed_spec

        for candidate_ext in ('.dds','.tga','.png'):
            candidate=os.path.join(directory,stem+candidate_ext)
            if os.path.isfile(candidate):
                return candidate
        return None

    direct=alternatives(os.path.dirname(exact))
    if direct:
        return logical(direct)

    # A few projectile/effect materials are stored one or more directories
    # below the avatar root but intentionally refer to the avatar's shared
    # color/normal maps by a bare name. Search only upward inside this avatar.
    cursor=os.path.dirname(exact)
    package_root=os.path.abspath(package_root)
    while True:
        candidate=alternatives(cursor)
        if candidate:
            return logical(candidate)
        if os.path.normcase(cursor)==os.path.normcase(package_root):
            break
        parent=os.path.dirname(cursor)
        if parent==cursor or not os.path.commonpath((package_root,parent)) == package_root:
            break
        cursor=parent
    # Effects sometimes live below an elemental/model directory but refer to
    # a shared normal map at the avatar root.  If the root stores that map in
    # a named skin directory, resolve the pair there instead of leaving a
    # dangling normal.tga reference.
    if is_normal:
        try: children=sorted(os.scandir(package_root),key=lambda item:item.name.lower())
        except OSError: children=[]
        for child in children:
            if not child.is_dir():
                continue
            candidate=alternatives(child.path)
            if candidate and os.path.basename(candidate).lower().endswith('_rxgb.dds'):
                return logical(candidate)
    return None

def _repair_relative_texture_references(root,hero,av):
    """Repair missing relative texture extensions/locations in one avatar.

    This operates only on Runtime and PreparedAssets. It is used both during
    developer preprocessing and when an older prepared package is installed,
    so old packages receive the same repair as newly generated ones.
    """
    modern=str(hero.get('folder') or '').lower()
    legacy=str(hero.get('legacy_folder') or modern).lower()
    roots=[]
    for asset_root in (switcher_root(root),prepared_root(root)):
        for namespace in dict.fromkeys((modern,legacy)):
            # Some projectile/effect assets are shared at the hero namespace
            # root instead of inside the selected avatar folder.  Include that
            # tree so references such as bullet.material -> color.tga are
            # repaired when only the avatar package is installed.
            shared_root=os.path.join(asset_root,'heroes',namespace)
            if os.path.isdir(shared_root) and os.path.normcase(shared_root) not in {
                os.path.normcase(x) for x in roots
            }:
                roots.append(shared_root)
            package=os.path.join(asset_root,'heroes',namespace,av.lower())
            if os.path.isdir(package) and os.path.normcase(package) not in {
                os.path.normcase(x) for x in roots
            }:
                roots.append(package)
    changed=0
    for package in roots:
        for dp,_,files in os.walk(package):
            for fn in files:
                if os.path.splitext(fn)[1].lower() not in LEGACY_TEXT_EXTS:
                    continue
                path=os.path.join(dp,fn)
                try:text=read_text(path)
                except OSError:continue
                updated=text
                def replace(match):
                    nonlocal changed
                    raw=match.group(1)
                    fixed=_texture_ref_replacement(path,raw,package)
                    if fixed and fixed!=raw:
                        changed+=1
                        return match.group(0).replace(raw,fixed,1)
                    return match.group(0)
                updated=LEGACY_REF_RE.sub(replace,' '+updated)[1:]
                if updated!=text:
                    write_text(path,updated)
    if changed:
        diag(root,f"TEXTURE_REF_REPAIR hero={hero.get('folder')} avatar={av} changed={changed}")
    return changed

def _repair_avatar_morph_models(root,hero,av):
    """Bind an avatar's available ability-4 form to the current ult modifier."""
    modern=str(hero.get('folder') or '').lower()
    legacy=str(hero.get('legacy_folder') or modern).lower()
    candidates=[]
    for asset_root in (switcher_root(root),prepared_root(root)):
        for namespace in dict.fromkeys((modern,legacy)):
            avatar_root=os.path.join(asset_root,'heroes',namespace,av.lower())
            for rel in (
                'ability_04/morph/model.mdf',
                'ability_04/effects/ult_form/model.mdf',
                'ability_04/transform/model.mdf',
                'transform/model.mdf',
                'trans/model.mdf',
            ):
                path=os.path.join(avatar_root,*rel.split('/'))
                if os.path.isfile(path):
                    candidates.append((asset_root,namespace,rel))
    if not candidates:
        return 0

    # Prefer the historical namespace because generated hero entities normally
    # reference that namespace for legacy avatar assets.
    _,namespace,rel=min(candidates,key=lambda x:(0 if x[1]==legacy else 1,x[1],x[2]))
    model_ref=f"/heroes/{namespace}/{av.lower()}/{rel}"
    effect_ref=f"/heroes/{namespace}/{av.lower()}/{os.path.dirname(rel)}/effects/body.effect"
    effect_exists=any(os.path.isfile(os.path.join(asset_root,'heroes',namespace,av.lower(),
                                                   os.path.dirname(rel),'effects','body.effect'))
                      for asset_root in (switcher_root(root),prepared_root(root)))
    roots=[]
    for asset_root in (switcher_root(root),prepared_root(root)):
        roots.extend([
            os.path.join(asset_root,'heroes',modern,'base','hero.entity'),
            os.path.join(asset_root,'heroes',modern,'base','ability_04','state.entity'),
        ])
        recipe=os.path.join(asset_root,'recipes',modern,av.lower(),'files','heroes',modern,'base','hero.entity')
        roots.append(recipe)
    # The fast selection cache is copied directly during avatar switching, so
    # repair its saved hero entity as well.
    roots.append(os.path.join(_recipe_dir(root,hero,av),'files','heroes',modern,'base','hero.entity'))
    changed=0
    for path in dict.fromkeys(roots):
        if not os.path.isfile(path):continue
        try:text=read_text(path)
        except OSError:continue
        def replace(match):
            nonlocal changed
            tag=match.group(0)
            key_match=re.search(r'\bkey\s*=\s*"([^"]+)"',tag,re.I)
            model_match=re.search(r'\bmodel\s*=\s*"([^"]+)"',tag,re.I)
            key=(key_match.group(1) if key_match else '').lower()
            model=(model_match.group(1) if model_match else '').lower()
            if not model_match or not (('ult' in key or 'morph' in key) and
                                       ('morph' in model or 'ult_form' in model or
                                        'transform' in model)):
                return tag
            updated=re.sub(r'(\bmodel\s*=\s*")[^"]*(")',
                           lambda m:m.group(1)+model_ref+m.group(2),tag,count=1,flags=re.I)
            if effect_exists:
                if re.search(r'\bpassiveeffect\s*=\s*"[^"]*"',updated,re.I):
                    updated=re.sub(r'(\bpassiveeffect\s*=\s*")[^"]*(")',
                                   lambda m:m.group(1)+effect_ref+m.group(2),updated,count=1,flags=re.I)
                else:
                    updated=re.sub(r'(/?>)$',f' passiveeffect="{effect_ref}"\\1',updated,count=1)
            if updated!=tag:changed+=1
            return updated
        updated=re.sub(r'<modifier\b[^>]*>',replace,text,flags=re.I|re.S)
        if updated!=text:write_text(path,updated)
    if changed:
        diag(root,f"MORPH_MODEL_REPAIR hero={hero.get('folder')} avatar={av} model={model_ref} changed={changed}")
    return changed

def _repair_missing_animation_clips(root,hero,av):
    """Supply missing get-up clips used by networked and replayed animation state."""
    modern=str(hero.get('folder') or '').lower()
    legacy=str(hero.get('legacy_folder') or modern).lower()
    namespaces=tuple(dict.fromkeys((modern,legacy)))
    sources=[]
    for asset_root in (prepared_root(root),switcher_root(root)):
        for namespace in namespaces:
            hero_root=os.path.join(asset_root,'heroes',namespace)
            if not os.path.isdir(hero_root):
                continue
            preferred=(
                os.path.join(hero_root,'set_ascension','clips','getup_1.clip'),
                os.path.join(hero_root,'clips','getup_1.clip'),
            )
            sources.extend(path for path in preferred if os.path.isfile(path))
            if not sources:
                for dp,_,files in os.walk(hero_root):
                    if 'getup_1.clip' in files:
                        sources.append(os.path.join(dp,'getup_1.clip'))
    source=next((path for path in sources if os.path.isfile(path)),None)

    packages=[]
    for asset_root in (prepared_root(root),switcher_root(root)):
        for namespace in namespaces:
            package=os.path.join(asset_root,'heroes',namespace,av.lower())
            if os.path.isdir(package):
                packages.append((package,asset_root))
    changed=0
    for package,asset_root in dict.fromkeys(packages):
        for dp,_,files in os.walk(package):
            for fn in files:
                if not fn.lower().endswith('.mdf'):
                    continue
                model_path=os.path.join(dp,fn)
                try:text=read_text(model_path)
                except OSError:continue
                refs=re.findall(r'\bclip\s*=\s*["\']([^"\']*getup_1\.clip)["\']',text,re.I)
                for ref in refs:
                    ref=ref.replace('\\','/')
                    if ref.startswith('/'):
                        destination=os.path.join(asset_root,*ref.lstrip('/').split('/'))
                    else:
                        destination=os.path.normpath(os.path.join(dp,*ref.split('/')))
                    if os.path.isfile(destination):
                        continue
                    copy_source=source
                    source_kind='getup' if copy_source else 'fallback_walk'
                    if not copy_source:
                        walk_refs=re.findall(r'\bname\s*=\s*["\']walk_1["\'][^>]*\bclip\s*=\s*["\']([^"\']+)["\']',text,re.I)
                        if walk_refs:
                            walk_ref=walk_refs[0].replace('\\','/')
                            if walk_ref.startswith('/'):
                                walk_path=os.path.join(asset_root,*walk_ref.lstrip('/').split('/'))
                            else:
                                walk_path=os.path.normpath(os.path.join(dp,*walk_ref.split('/')))
                            if os.path.isfile(walk_path):
                                copy_source=walk_path
                    if not copy_source:
                        for candidate in (
                            os.path.join(dp,'clips','walk_1.clip'),
                            os.path.join(os.path.dirname(dp),'clips','walk_1.clip'),
                        ):
                            if os.path.isfile(candidate):
                                copy_source=candidate
                                break
                    if not copy_source:
                        diag(root,f"ANIMATION_CLIP_UNRESOLVED hero={hero.get('folder')} avatar={av} model={model_path} ref={ref}")
                        continue
                    os.makedirs(os.path.dirname(destination),exist_ok=True)
                    try:shutil.copy2(copy_source,destination)
                    except OSError:continue
                    changed+=1
                    diag(root,f"ANIMATION_CLIP_REPAIR hero={hero.get('folder')} avatar={av} model={model_path} ref={ref} source={copy_source} kind={source_kind}")
    return changed

def _load_animation_slot_reference(root,hero):
    """Load the base hero animation order generated by the offline preprocessor."""
    path=os.path.join(prepared_root(root),'animation_slots.json')
    try:
        data=json.load(open(path,'r',encoding='utf-8'))
    except (OSError,ValueError,TypeError):
        return []
    for key in (str(hero.get('folder') or '').lower(),
                str(hero.get('legacy_folder') or '').lower()):
        value=data.get(key) if isinstance(data,dict) else None
        if isinstance(value,list):
            return [str(name) for name in value if str(name)]
    return []

def _repair_network_animation_slots(root,hero,av,reference_names=None):
    """Keep avatar animation slots aligned with the base hero for network/replay playback."""
    reference_names=list(reference_names or _load_animation_slot_reference(root,hero))
    if not reference_names:
        return 0
    modern=str(hero.get('folder') or '').lower()
    legacy=str(hero.get('legacy_folder') or modern).lower()
    namespaces=tuple(dict.fromkeys((modern,legacy)))
    packages=[]
    for asset_root in (prepared_root(root),switcher_root(root)):
        for namespace in namespaces:
            package=os.path.join(asset_root,'heroes',namespace,av.lower())
            if os.path.isdir(package):
                packages.append(package)

    name_pattern=re.compile(r'\bname\s*=\s*["\']([^"\']+)["\']',re.I)

    def animation_blocks(text):
        """Read top-level animation elements without confusing self-closing tags."""
        blocks=[]
        for match in re.finditer(r'<anim\b',text,re.I):
            header_end=text.find('>',match.start())
            if header_end<0:
                continue
            if text[header_end-1:header_end]=='/':
                end=header_end+1
            else:
                close=text.find('</anim>',header_end+1)
                if close<0:
                    continue
                end=close+len('</anim>')
            blocks.append((match.start(),end,text[match.start():end]))
        return blocks

    changed=0
    for package in dict.fromkeys(packages):
        # The cached reference describes the hero's network animation table.
        # Nested models, especially Maliken's temporary ability-4 model, have
        # their own native table and must keep that order.
        model_path=os.path.join(package,'model.mdf')
        if not os.path.isfile(model_path):
            continue
        try:text=read_text(model_path)
        except OSError:continue
        matches=animation_blocks(text)
        if not matches:
            continue
        blocks=[item[2] for item in matches]
        names=[(name_pattern.search(block).group(1).lower()
                if name_pattern.search(block) else '') for block in blocks]
        reference_keys={name.lower() for name in reference_names}
        by_name={}
        extras=[]
        for block,name in zip(blocks,names):
            if name in reference_keys:
                by_name.setdefault(name,block)
            else:
                extras.append(block)

        def make_placeholder(name):
            candidates=[
                f'clips/{name}.clip',
                f'clips/{name.replace("_1","")}.clip',
            ]
            if name=='portrait':
                candidates[0:0]=['clips/portrait_1.clip','clips/portrait.clip']
            elif name=='getup_1':
                candidates[0:0]=['clips/getup_1.clip','clips/getup.clip']
            clip=next((ref for ref in candidates
                       if os.path.isfile(os.path.join(package,*ref.split('/')))),None)
            if clip is None:
                clip='clips/default_1.clip'
            return f'<anim name="{name}" clip="{clip}" loop="true"/>'

        ordered=[]
        for name in reference_names:
            key=name.lower()
            ordered.append(by_name.get(key) or make_placeholder(name))
        ordered.extend(extras)

        old_sequence=names
        new_sequence=[(name_pattern.search(block).group(1).lower()
                       if name_pattern.search(block) else '') for block in ordered]
        if old_sequence==new_sequence:
            continue
        start=matches[0][0]; end=matches[-1][1]
        updated=text[:start]+'\n'.join(ordered)+text[end:]
        write_text(model_path,updated)
        changed+=1
        diag(root,f"ANIMATION_SLOT_REPAIR hero={hero.get('folder')} avatar={av} model={model_path} old_walk={old_sequence.index('walk_1') if 'walk_1' in old_sequence else -1} new_walk={new_sequence.index('walk_1') if 'walk_1' in new_sequence else -1}")
    return changed

def _normalize_legacy_materials_for_reborn(root, hero, av):
    """Normalize legacy K2 material shaders known to render incorrectly in Reborn.

    Some historical avatars use old environment/reflection shaders:

        mesh_color_enviro_unit
        mesh_color_enviro_unit_spec_reflectmask_glow
        mesh_color_enviro_unit_team_spec_reflectmask4

    In current Reborn this can render the entire model with an incorrect
    blue/environment tint. Preserve the avatar's own material and textures,
    but replace that shader pair with the simpler compatible shader used by
    working legacy materials.
    """
    legacy = (hero.get("legacy_folder") or hero["folder"]).lower()
    modern = hero["folder"].lower()
    avatar_dirs = set()
    for asset_root in (switcher_root(root), prepared_root(root)):
        avatar_dirs.update({
            os.path.join(asset_root, "heroes", legacy, av.lower()),
            os.path.join(asset_root, "heroes", modern, av.lower()),
        })
    changed = _normalize_reborn_shared_effect_materials(root)

    def repair_shader_names(text):
        """Remove the obsolete environment variant from ordinary unit shaders.

        Cubespec and refractmask shaders are deliberately left alone: they are
        used by crystal/opal and refraction effects where the environment map
        is part of the effect.  The ordinary unit shader family is the one that
        produces the full-model blue shell under Reborn.
        """
        pattern = re.compile(
            r'(\b(?:vs|ps)\s*=\s*["\'])(mesh_color_enviro_unit[^"\']*)(["\'])',
            re.I,
        )

        def replace(match):
            shader = match.group(2)
            low = shader.lower()
            if "cubespec" in low or "refractmask" in low:
                return match.group(0)
            exact = {
                "mesh_color_enviro_unit": "mesh_color_unit",
                "mesh_color_enviro_unit_lightmap_spec_reflectmask4": "mesh_color_unit_spec",
                "mesh_color_enviro_unit_spec_reflectmask_glow": "mesh_color_unit_spec",
                "mesh_color_enviro_unit_team_spec_reflectmask4": "mesh_color_unit_team_spec_reflectmask4",
                "mesh_color_enviro_unit_team_spec_reflectmask4_glow": "mesh_color_unit_team_spec_reflectmask4",
                "mesh_color_enviro_unit_team_spec_reflectmask4_burn": "mesh_color_unit_team_spec_reflectmask4_burn",
                "mesh_color_enviro_unit_team_spec_reflectmask": "mesh_color_unit_team_spec_reflectmask",
                "mesh_color_enviro_unit_team_spec_reflectmask3": "mesh_color_unit_team_spec_reflectmask3",
            }
            replacement = exact.get(low)
            if replacement is None:
                replacement = re.sub(r'(?i)mesh_color_enviro_', 'mesh_color_', shader)
            return match.group(1) + replacement + match.group(3)

        return pattern.sub(replace, text)

    # Some historical avatar models reuse a sibling avatar's material tree
    # (for example Sir Benzington Alt13 uses Alt12's model). Scan the mounted
    # historical hero namespace so those explicit cross-avatar dependencies get
    # the same compatibility treatment.
    scan_dirs=set(avatar_dirs)
    for asset_root in (switcher_root(root), prepared_root(root)):
        scan_dirs.add(os.path.join(asset_root,"heroes",legacy))
        scan_dirs.add(os.path.join(asset_root,"heroes",modern))
    for avatar_dir in scan_dirs:
        if not os.path.isdir(avatar_dir):
            continue
        for dp, _, files in os.walk(avatar_dir):
            for fn in files:
                if not fn.lower().endswith(".material"):
                    continue

                path = os.path.join(dp, fn)

                try:
                    with open(path, "r", encoding="utf-8") as f:
                        text = f.read()
                except (UnicodeDecodeError, OSError):
                    continue

                newtext = repair_shader_names(text)

                if newtext == text:
                    continue

                with open(path, "w", encoding="utf-8", newline="") as f:
                    f.write(newtext)

                changed += 1
                diag(
                    root,
                    f"MATERIAL_REBORN_COMPAT hero={hero['folder']} "
                    f"avatar={av} file={os.path.relpath(path, one_punch_root(root))}"
                )

    return changed + _suppress_legacy_body_shell(root, hero, av)


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






def decorate_hero_selection_metadata(root,heroes):
    """Attach selector metadata from the prepared base hero entities.

    The GUI reads only files shipped with the mod.  These tiny entities preserve
    the hero's team and primary attribute, so grouping remains correct without
    opening the old source tree or extracting one entity per hero at startup.
    """
    for h in heroes:
        path=os.path.join(prepared_root(root),"heroes",h["folder"].lower(),"base","hero.entity")
        attrs={}
        if os.path.isfile(path):
            try:
                match=re.search(r'<hero\b[^>]*>',read_text(path),re.I|re.S)
                attrs=_parse_attrs(match.group(0)) if match else {}
            except OSError:
                pass
        attribute=(attrs.get("primaryattribute") or attrs.get("attribute") or "intelligence").lower()
        if attribute.startswith("agi"): attribute="agility"
        elif attribute.startswith("str"): attribute="strength"
        else: attribute="intelligence"
        team=(attrs.get("team") or "Legion").lower()
        h["ui_attribute"]=attribute
        h["ui_team"]="Hellbourne" if team.startswith("hell") else "Legion"
        h["ui_order"]=10000
    # PreparedAssets has no dependency on source ordering. Use a stable order
    # until the optional order metadata is supplied by the CLI preprocessor.
    for index,h in enumerate(sorted(heroes,key=lambda x:x["folder"].lower())):
        h["ui_order"]=index


def launch_hon(root):
    exe=os.path.join(root,"bin","juvio.exe")
    if not os.path.isfile(exe):raise RuntimeError(r"bin\juvio.exe was not found.")
    # Keep K2 file caches. Deleting them on every launch forces an expensive rebuild.
    # The switcher's generated files have stable paths and are rewritten before launch.
    # Keep Runtime as a loose editable asset layer.  The final archive is a
    # small overlay so HoN keeps its writable profile and login.cfg in the
    # normal Heroes of Newerth profile directory.
    ensure_mod_profile_login(root)
    sync_mod_overlay(root)
    mod_layers="heroes of newerth;OnePunchMod/Runtime;mods"
    diag(root,f'LAUNCH exe={exe} cwd={root} mod={mod_layers}')
    subprocess.Popen([exe,"-mod",mod_layers],
                     cwd=root)


def discover_announcers(root):
    packs=set()
    source_root=os.path.join(one_punch_root(root),"PreparedAssets","announcers")
    if not os.path.isdir(source_root):
        return []
    try: entries=os.scandir(source_root)
    except OSError: return []
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

def apply_announcer(root,pack):
    clear_announcer_override(root)
    if not pack or pack=="default":
        json.dump({"pack":"default"},open(announcer_selection_file(root),"w",encoding="utf-8"),indent=2);return 0
    stage=tempfile.mkdtemp(prefix="hon_announcer_");copied=[]
    try:
        source_root=os.path.join(one_punch_root(root),"PreparedAssets","announcers",pack.lower())
        if os.path.isdir(source_root):
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
        raise RuntimeError(f"Announcer assets for '{pack}' were not found in PreparedAssets.")
        json.dump(copied,open(announcer_manifest(root),"w",encoding="utf-8"),indent=2)
        json.dump({"pack":pack},open(announcer_selection_file(root),"w",encoding="utf-8"),indent=2)
        return len(copied)
    finally:shutil.rmtree(stage,ignore_errors=True)


def vanity_catalog_path(root):
    return os.path.join(one_punch_root(root),"PreparedAssets","vanity_catalog.json")

def vanity_selection_file(root):
    return os.path.join(cache_dir(root),"vanity_selections.json")

def vanity_overlay_manifest(root):
    return os.path.join(cache_dir(root),"vanity_overlay_manifest.json")

def load_vanity_catalog(root):
    try:
        data=json.load(open(vanity_catalog_path(root),"r",encoding="utf-8"))
        return data if isinstance(data,dict) else {}
    except (OSError,ValueError,TypeError):
        return {}

def load_vanity_selections(root):
    values={key:"default" for key in ("ward","raven","teleport","courier","announcer")}
    try:
        data=json.load(open(vanity_selection_file(root),"r",encoding="utf-8"))
        if isinstance(data,dict):
            values.update({str(k).lower():str(v) for k,v in data.items()})
    except (OSError,ValueError,TypeError):
        pass
    # Keep the older announcer selector and the new unified selector aligned.
    try:
        data=json.load(open(announcer_selection_file(root),"r",encoding="utf-8"))
        if isinstance(data,dict) and data.get("pack"):
            values["announcer"]=str(data["pack"])
    except (OSError,ValueError,TypeError):
        pass
    return values

def _save_vanity_selections(root,values):
    path=vanity_selection_file(root); temporary=path+".tmp"
    try:
        os.makedirs(os.path.dirname(path),exist_ok=True)
        with open(temporary,"w",encoding="utf-8") as f:
            json.dump(values,f,ensure_ascii=False,indent=2,sort_keys=True)
        os.replace(temporary,path)
    except OSError:
        try:
            if os.path.isfile(temporary):os.remove(temporary)
        except OSError:pass

def _load_vanity_overlay_manifest(root):
    try:
        data=json.load(open(vanity_overlay_manifest(root),"r",encoding="utf-8"))
        return data if isinstance(data,dict) else {}
    except (OSError,ValueError,TypeError):
        return {}

def _save_vanity_overlay_manifest(root,data):
    path=vanity_overlay_manifest(root); temporary=path+".tmp"
    try:
        os.makedirs(os.path.dirname(path),exist_ok=True)
        with open(temporary,"w",encoding="utf-8") as f:
            json.dump(data,f,ensure_ascii=False,indent=2,sort_keys=True)
        os.replace(temporary,path)
    except OSError:pass

def clear_vanity_overlay(root,category):
    manifest=_load_vanity_overlay_manifest(root)
    for rel in manifest.pop(str(category).lower(),[]) or []:
        path=os.path.join(switcher_root(root),*str(rel).replace("\\","/").split("/"))
        try:
            if os.path.isfile(path):os.remove(path)
        except OSError:pass
    # Remove empty directories below Runtime without touching non-empty game
    # layers or directories owned by another selector.
    runtime=switcher_root(root)
    for base,dirs,files in os.walk(runtime,topdown=False):
        if base==runtime:continue
        try:
            if not dirs and not files:os.rmdir(base)
        except OSError:pass
    _save_vanity_overlay_manifest(root,manifest)
    return manifest

def apply_vanity_selection(root,category,option):
    """Overlay one prepared non-hero cosmetic package onto HoN's base path."""
    category=str(category).lower(); option=str(option or "default")
    values=load_vanity_selections(root)
    if category=="announcer":
        pack="default" if option=="default" else option
        count=apply_announcer(root,pack)
        values[category]=pack
        _save_vanity_selections(root,values)
        return count

    catalog=load_vanity_catalog(root)
    entry=next((x for x in catalog.get(category,[]) if str(x.get("id"))==option),None)
    manifest=clear_vanity_overlay(root,category)
    if entry is None:
        values[category]="default"
        _save_vanity_selections(root,values)
        return 0
    source=os.path.join(one_punch_root(root),"PreparedAssets",*str(entry["source"]).replace("\\","/").split("/"))
    target=os.path.join(switcher_root(root),*str(entry["target"]).replace("\\","/").split("/"))
    if not os.path.isdir(source):
        raise RuntimeError(f"Prepared cosmetic package is missing: {source}")
    copied=[]
    for base,_,files in os.walk(source):
        relbase=os.path.relpath(base,source)
        for name in files:
            rel=name if relbase=="." else os.path.join(relbase,name)
            src=os.path.join(base,name); dst=os.path.join(target,rel)
            os.makedirs(os.path.dirname(dst),exist_ok=True)
            shutil.copy2(src,dst)
            copied.append(os.path.relpath(dst,switcher_root(root)).replace("\\","/"))
    manifest[category]=copied
    _save_vanity_overlay_manifest(root,manifest)
    values[category]=option
    _save_vanity_selections(root,values)
    diag(root,f"VANITY_APPLY category={category} option={option} files={len(copied)}")
    return len(copied)


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
        self.rv=tk.StringVar(value=DEFAULT_ROOT)
        clear_diagnostic_log(self.rv.get())
        self.search_var=tk.StringVar();self.filter_var=tk.StringVar(value="All")
        self.status=tk.StringVar(value="Preparing your hero roster...")
        self.vanity_catalog=load_vanity_catalog(self.rv.get())
        self.vanity_selections=load_vanity_selections(self.rv.get())
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

    def avatar_label(self, hero, avatar):
        return avatar_display_name(hero, avatar, getattr(self, "_names", {}))

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
        root=self.rv.get();previous=self.focus_hero.get("key") if self.focus_hero else None
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
                data=build_prepared_inventory(root,force)
                (heroes,z,arc,paths,loose_named,packed_named,larcs,lmembers,cache_hit,names)=data
                log_event(root,"inventory",t,detail=f"cache_hit={cache_hit}")
                selections,selections_present=load_avatar_selections(root)
                for h in heroes:
                    h["_root"]=root
                    selected=selections.get(h["folder"].lower(),"default") if selections_present else "default"
                    h["current"]=selected if selected in h.get("avatars",{"default"}) else "default"
                log_event(root,"avatar_selections_loaded",detail=f"present={selections_present} count={len(selections)}")
                decorate_hero_selection_metadata(root,heroes)

                announcer_packs=discover_announcers(root)
                announcer_display={"Default":"default"}
                for pk in announcer_packs:
                    announcer_display[ANNOUNCER_LABELS.get(pk,pretty_avatar(pk))]=pk
                try:
                    sf=announcer_selection_file(root)
                    sel=json.load(open(sf,"r",encoding="utf-8")).get("pack","default") if os.path.isfile(sf) else "default"
                except Exception:sel="default"
                shown=next((k for k,v in announcer_display.items() if v==sel),"Default")

                self._load_status(generation,"Loading prepared avatar names...")
                log_event(root,"prepared_avatar_names",detail=f"count={len(names)}")

                # Clean only stale overrides created by old switcher builds, never third-party mods.
                t=time.time();cleanup_old_switcher_files(root);log_event(root,"cleanup_old_overrides",t)

                # PreparedAssets and the existing Runtime recipes are already the
                # normalized selection state. Do not rebuild all selected avatars at
                # startup; the explicit Group Actions > Reload all avatars command
                # performs that recovery pass when the user requests it.
                overlay_t=time.time()
                sync_mod_overlay(root)
                log_event(root,"sync_mod_overlay",overlay_t)
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
                sync_mod_overlay(self.rv.get())
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
        targets=list(self.heroes)
        if action == "random":
            label="Applying random avatars"
        elif action == "default":
            label="Applying default avatars"
        else:
            action="reload"
            label="Reloading selected avatars"
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
            elif action == "default":
                work=[(h,["default"]) for h in targets]
            else:
                work=[(h,[h.get("current","default")]) for h in targets]
            total=len(work)
            if not total:
                log_event(self.rv.get(),"group_avatar_action",t,
                          detail=f"action={action} done=0 total=0 skipped_bad={skipped_bad}")
                self.after(0,lambda:self._random_done(0,0,"No safe alternate avatars found"))
                return
            self.after(0,lambda:self.status.set(f"{label} 0/{total} heroes..."))
            for i,(h,choices) in enumerate(work,1):
                av=random.choice(choices) if action == "random" else choices[0]
                try:
                    apply_avatar(self.rv.get(),h,av,self.z,self.arc,self.tmp,self.larcs,self.lmembers)
                    h["current"]=av;done+=1
                    self.after(0,lambda H=h:self.refresh_card(H))
                except Exception as ex:
                    log_event(self.rv.get(),"group_action_error",detail=f"action={action} hero={h['folder']} avatar={av}: {ex}")
                pct=i*100/total
                self.after(0,lambda I=i,P=pct,L=label:self._random_progress(I,total,P,L))
            try:
                sync_mod_overlay(self.rv.get())
            except Exception as ex:
                log_event(self.rv.get(),"group_action_error",detail=f"action={action} overlay: {ex}")
                self.after(0,lambda err=str(ex):self._change_error(err))
                return
            log_event(self.rv.get(),"group_avatar_action",t,
                      detail=f"action={action} done={done} total={total} skipped_bad={skipped_bad}")
            self.after(0,lambda:self._random_done(done,total,label))
        threading.Thread(target=worker,daemon=True).start()

    def apply_random_avatars_to_all(self):
        self._run_group_avatar_action("random")

    def apply_default_avatars_to_all(self):
        self._run_group_avatar_action("default")

    def reload_all_selected_avatars(self):
        self._run_group_avatar_action("reload")

    def randomize_defaults(self):
        # Compatibility entry point for older callers.
        self.apply_random_avatars_to_all()

    def _random_progress(self,i,total,pct,label="Processing avatars"):
        self.progress["value"]=pct
        self.status.set(f"{label} {i}/{total} heroes... {pct:.0f}%")

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
                n=apply_announcer(self.rv.get(),pack)
                self.after(0,lambda:self._announcer_done(label,n))
            except Exception as ex:self.after(0,lambda err=str(ex):self._change_error(err))
        threading.Thread(target=worker,daemon=True).start()

    def _announcer_done(self,label,n):
        self._finish_single_operation()
        self.status.set(f"Announcer: {label} ({n} sound files overlaid).")

    def choose_vanity(self,category,option):
        if self.busy:
            self.status.set("One Punch is still finishing the previous operation.")
            return
        category=str(category).lower(); option=str(option or "default")
        entry=next((x for x in self.vanity_catalog.get(category,[])
                    if str(x.get("id"))==option),None)
        label="Default" if option=="default" else str((entry or {}).get("label",option))
        self.busy=True
        self._show_loading()
        self.launch_btn.configure(state="disabled")
        self.random_btn.configure(state="disabled")
        self.status.set(f"Applying {category}: {label}...")
        def worker():
            try:
                count=apply_vanity_selection(self.rv.get(),category,option)
                self.after(0,lambda:self._vanity_done(category,label,count))
            except Exception as ex:
                self.after(0,lambda err=str(ex):self._change_error(err))
        threading.Thread(target=worker,daemon=True).start()

    def _vanity_done(self,category,label,count):
        self.vanity_selections=load_vanity_selections(self.rv.get())
        self._refresh_vanity_buttons()
        self._finish_single_operation()
        self.status.set(f"{category.title()} selected: {label} ({count} files overlaid).")





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
            self.status.set('Launched: bin\\juvio.exe -mod "heroes of newerth;OnePunchMod/Runtime;mods"')
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
        try:
            self._save_window_geometry()
        except Exception:
            pass
        from one_punch_ui_audio import close
        close()
        shutil.rmtree(self.tmp,ignore_errors=True);super().destroy()

if __name__=="__main__":
    App().mainloop()
