"""Repair prepared avatar ability cosmetics from the current HoN archive.

This is a developer-side maintenance command. It reads only the current
Reborn resources archive plus PreparedAssets and writes tiny entity overrides
into PreparedAssets/recipes; the player launcher never needs LegacyAssets.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import zipfile

import one_punch_mod as mod


TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_./])"
    r"((?:effects|sounds)/[A-Za-z0-9_.%+\-/]+|icon\.(?:tga|dds|png))",
    re.IGNORECASE,
)
ABILITY_MEMBER_RE = re.compile(
    r"^heroes/([^/]+)/base/(ability_0[1-4])/(.+\.entity)$", re.IGNORECASE
)


def _ability_dir(package, current_dir):
    choices = (current_dir, current_dir.replace("_0", "_"))
    for choice in choices:
        path = os.path.join(package, *choice.split("/"))
        if os.path.isdir(path):
            return choice, path
    return None, None


def _asset_ref(package, ability_dir, raw):
    raw = raw.replace("\\", "/")
    if raw.lower() == "icon.tga":
        candidates = ("icon.dds", "icon.tga", "icon.png")
    else:
        candidates = [raw]
        stem, ext = os.path.splitext(raw)
        ext = ext.lower()
        if ext in (".tga", ".png"):
            candidates.append(stem + ".dds")
        elif ext == ".wav":
            candidates.append(stem + ".ogg")

    for candidate in candidates:
        path = os.path.join(package, ability_dir, *candidate.split("/"))
        if os.path.isfile(path):
            rel = os.path.relpath(path, package).replace("\\", "/")
            return rel
    return None


def _patch_entity(text, package, current_dir, hero, avatar):
    ability_dir, directory = _ability_dir(package, current_dir)
    if not directory:
        return text, 0
    changed = 0

    def replace(match):
        nonlocal changed
        raw = match.group(1)
        if raw.startswith("/") or raw.startswith("../"):
            return match.group(0)
        rel = _asset_ref(package, ability_dir, raw)
        if not rel:
            return match.group(0)
        value = f"/heroes/{hero}/{avatar}/{rel}"
        changed += 1
        return match.group(0).replace(raw, value, 1)

    return TOKEN_RE.sub(replace, text), changed


def repair(root):
    heroes, _, archive, _, _, _, _, _, _, _ = mod.build_prepared_inventory(root, True)
    prepared = mod.prepared_root(root)
    archive_paths = {}
    for hero in heroes:
        for member in hero.get("archive", {}).get("paths", []):
            archive_paths[member.replace("\\", "/").lower()] = member

    changed_packages = 0
    changed_files = 0
    changed_refs = 0

    with zipfile.ZipFile(archive, "r") as resources:
        names = {
            item.filename.replace("\\", "/").lower(): item.filename
            for item in resources.infolist()
        }
        for hero in heroes:
            modern = hero["folder"].lower()
            if not os.path.isdir(os.path.join(prepared, "heroes", modern)):
                continue
            for avatar in sorted(hero.get("legacy") or set(), key=mod.avatar_sort):
                package = os.path.join(prepared, "heroes", modern, avatar.lower())
                if not os.path.isdir(package):
                    continue
                ability_dirs = [
                    name for name in os.listdir(package)
                    if os.path.isdir(os.path.join(package, name))
                    and re.fullmatch(r"ability_0?[1-4]", name, re.IGNORECASE)
                ]
                if not ability_dirs:
                    continue

                recipe_dir = os.path.join(prepared, "recipes", modern, avatar.lower())
                recipe_path = os.path.join(recipe_dir, "recipe.json")
                if not os.path.isfile(recipe_path):
                    continue
                try:
                    recipe = json.load(open(recipe_path, "r", encoding="utf-8"))
                except (OSError, ValueError, TypeError):
                    continue
                recipe_files = set(recipe.get("files") or [])
                # Ability overrides are removed when the user switches back
                # to the default avatar. Use the same managed marker as the
                # launcher; the generic hero marker is not enough for that
                # cleanup pass.
                for old_marker in list(recipe_files):
                    if (
                        "/base/ability_" in old_marker.lower()
                        and old_marker.lower().endswith(
                            ".hon_avatar_switcher_created"
                        )
                    ):
                        recipe_files.discard(old_marker)
                        old_path = os.path.join(
                            recipe_dir, "files", *old_marker.replace("\\", "/").split("/")
                        )
                        try:
                            os.remove(old_path)
                        except OSError:
                            pass
                package_files = 0
                for lower, member in archive_paths.items():
                    match = ABILITY_MEMBER_RE.match(lower)
                    if not match or match.group(1).lower() != modern:
                        continue
                    ability_dir, tail = match.group(2), match.group(3)
                    if lower.endswith(".metadata"):
                        continue
                    archive_name = names.get(member.replace("\\", "/").lower(), member)
                    try:
                        text = resources.read(archive_name).decode("utf-8")
                    except (KeyError, UnicodeDecodeError, OSError):
                        continue
                    updated, refs = _patch_entity(
                        text, package, ability_dir, modern, avatar.lower()
                    )
                    if not refs or updated == text:
                        continue
                    rel = f"heroes/{modern}/base/{ability_dir}/{tail}"
                    destination = os.path.join(recipe_dir, "files", *rel.split("/"))
                    os.makedirs(os.path.dirname(destination), exist_ok=True)
                    with open(destination, "w", encoding="utf-8", newline="") as handle:
                        handle.write(updated)
                    marker = destination + ".onepunch_ability_managed"
                    with open(marker, "w", encoding="utf-8") as handle:
                        handle.write("managed by One Punch Mod prepared ability override\n")
                    recipe_files.update((rel, rel + ".onepunch_ability_managed"))
                    package_files += 1
                    changed_files += 1
                    changed_refs += refs

                if package_files:
                    recipe["files"] = sorted(recipe_files)
                    with open(recipe_path, "w", encoding="utf-8") as handle:
                        json.dump(recipe, handle, indent=2)
                    changed_packages += 1
                    print(f"{modern}/{avatar}: {package_files} entity overrides, {changed_refs} refs total")

    print(
        f"completed: packages={changed_packages} files={changed_files} "
        f"references={changed_refs}"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hon-root",
        default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        help="HoN installation root containing heroes of newerth/resources0.jz",
    )
    args = parser.parse_args()
    repair(os.path.abspath(args.hon_root))


if __name__ == "__main__":
    main()
