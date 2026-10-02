import os
import shutil
from zipfile import ZipFile, ZIP_STORED, ZIP_DEFLATED
import json
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm

progress_cb = None
stop_check = None


class PackCancelled(Exception):
    """Raised when packing is aborted via stop_check."""


def _pbar(*args, **kwargs):
    """tqdm wrapper: when progress_cb is set, forward n/total/postfix to it."""
    cb = progress_cb
    if cb is None:
        return tqdm(*args, **kwargs)

    class _GuiTqdm(tqdm):
        def update(self, n=1):
            result = super().update(n)
            cb(self.n, self.total, self.postfix or "")
            return result

        def set_postfix_str(self, s, **kw):
            result = super().set_postfix_str(s, **kw)
            cb(self.n, self.total, s)
            return result

    return _GuiTqdm(*args, **kwargs)

def yaml_str(value):
    """Safely format a string for YAML output."""
    return json.dumps(value, ensure_ascii=False)

def build_info_yml(info, id, level_name, level_idx):
    difficulty = info["difficulty"][level_idx]
    lines = [
        f"name: {yaml_str(info['Name'])}",
        f"difficulty: {difficulty}",
        f"level: {yaml_str(f'{level_name}  Lv.{difficulty}')}",
        f"charter: {yaml_str(info['Chater'][level_idx])}",
        f"composer: {yaml_str(info['Composer'])}",
        f"illustrator: {yaml_str(info['Illustrator'])}",
        f"chart: {yaml_str(f'{id}.json')}",
        f"music: {yaml_str(f'{id}.ogg')}",
        f"illustration: {yaml_str(f'{id}.png')}",
        "previewStart: 0.0",
        "aspectRatio: 1.7777777777777777",
        "backgroundDim: 0.6",
        "lineLength: 6.0",
        "offset: 0.0",
        "tags: []",
        "intro: \"\"",
        "holdPartialCover: false",
        "noteUniformScale: false",
        "forceAspectRatio: false",
        "foldAnimation: true",
        "scoreTotal: 1000000",
        "negativeLengthHold: true",
    ]
    return "\n".join(lines) + "\n"

def _resolve_asset(chdir, folder, id, num, level_name, ext):
    """优先 {id}{num}{ext}；不存在时回退到按难度分文件 {id}{num}_{level}{ext}。"""
    plain = f"{chdir}/{folder}/{id}{num}{ext}"
    if os.path.exists(plain):
        return plain
    variant = f"{chdir}/{folder}/{id}{num}_{level_name}{ext}"
    if os.path.exists(variant):
        return variant
    return None

def create_zip_file(chdir, id, info, levels, level, pbar, skipExisting: bool = True):
    file_name = (id[:17] + '...') if len(id) > 20 else id
    pbar.set_postfix_str(file_name)
    pez_filename = f"{chdir}/phira/{levels[level]}/{id}-{levels[level]}.pez"

    if stop_check is not None and stop_check():
        pbar.update(1)
        return
    if skipExisting and os.path.exists(pez_filename):
        pbar.set_postfix_str(f"{file_name} (已存在，跳过)")
        pbar.update(1)
        return
    num = ".0"
    if os.path.exists(f"{chdir}/Chart_{levels[level]}/{id}{num}.json"):
        try:
            with ZipFile(pez_filename, "w", compression=ZIP_DEFLATED) as pez:
                pez.writestr("info.yml", build_info_yml(info, id, levels[level], level))

                pez.write(f"{chdir}/Chart_{levels[level]}/{id}{num}.json", f"{id}.json")

                illus = _resolve_asset(chdir, "Illustration", id, num, levels[level], ".png")
                if illus is None:
                    print(f"  警告: 缺少插图，跳过 {id}-{levels[level]}")
                    raise FileNotFoundError(f"Illustration/{id}{num}.png 或按难度变体均不存在")
                pez.write(illus, f"{id}.png")

                music = _resolve_asset(chdir, "music", id, num, levels[level], ".ogg")
                if music is None:
                    print(f"  警告: 缺少音乐，跳过 {id}-{levels[level]}")
                    raise FileNotFoundError(f"music/{id}{num}.ogg 或按难度变体均不存在")
                pez.write(music, f"{id}.ogg")

                if os.path.exists(f"{chdir}/music/{id}{num}_EZ.ogg"):
                    pez.write(f"{chdir}/music/{id}{num}_EZ.ogg", f"{id}_EZ.ogg")
                if os.path.exists(f"{chdir}/music/{id}{num}_HD.ogg"):
                    pez.write(f"{chdir}/music/{id}{num}_HD.ogg", f"{id}_HD.ogg")
                if os.path.exists(f"{chdir}/music/{id}{num}_IN.ogg"):
                    pez.write(f"{chdir}/music/{id}{num}_IN.ogg", f"{id}_IN.ogg")
                if os.path.exists(f"{chdir}/music/{id}{num}_AT.ogg"):
                    pez.write(f"{chdir}/music/{id}{num}_AT.ogg", f"{id}_AT.ogg")
        except Exception as e:
            # 单曲失败不中断整体，但必须让异常可见（此前被线程池静默吞掉）
            print(f"  打包失败 {id}-{levels[level]}: {e}")
            if os.path.exists(pez_filename):
                os.remove(pez_filename)
    pbar.update(1)

def create_file(chdir, id, info, levels, level, pbar, skipExisting: bool = True):
    file_name = (id[:17] + '...') if len(id) > 20 else id
    pbar.set_postfix_str(file_name)
    dir_path = f"{chdir}/phira/{levels[level]}/{id}-{levels[level]}"

    if stop_check is not None and stop_check():
        pbar.update(1)
        return
    if skipExisting and os.path.exists(dir_path):
        pbar.set_postfix_str(f"{file_name} (已存在，跳过)")
        pbar.update(1)
        return
    num = ".0"
    os.makedirs(dir_path, exist_ok=True)

    try:
        with open(f"{dir_path}/info.yml", "w", encoding="utf-8") as f:
            f.write(build_info_yml(info, id, levels[level], level))

        shutil.copy(f"{chdir}/Chart_{levels[level]}/{id}{num}.json", f"{dir_path}/{id}.json")

        illus = _resolve_asset(chdir, "Illustration", id, num, levels[level], ".png")
        if illus is None:
            raise FileNotFoundError(f"Illustration/{id}{num}.png 或按难度变体均不存在")
        shutil.copy(illus, f"{dir_path}/{id}.png")

        music = _resolve_asset(chdir, "music", id, num, levels[level], ".ogg")
        if music is None:
            raise FileNotFoundError(f"music/{id}{num}.ogg 或按难度变体均不存在")
        shutil.copy(music, f"{dir_path}/{id}.ogg")
    except Exception as e:
        print(f"  打包失败 {id}-{levels[level]}: {e}")
        shutil.rmtree(dir_path, ignore_errors=True)

    pbar.update(1)

def run(chdir: str, nozip: bool, skipExisting: bool = True, progress_callback=None, stop_checker=None):
    global progress_cb, stop_check
    progress_cb = progress_callback
    stop_check = stop_checker
    levels = ["EZ", "HD", "IN", "AT"]

    shutil.rmtree(os.path.join(chdir, "phira"), True)
    os.mkdir(os.path.join(chdir, "phira"))
    for level in levels:
        os.mkdir(f"{chdir}/phira/{level}")

    raw_infos = {}
    with open(os.path.join(chdir, "info.json"), encoding="utf8") as f:
        raw_infos = json.load(f)
    infos = {}
    for item in raw_infos:
        song_id = item[0]
        infos[song_id] = {
            "Name": item[1],
            "Composer": item[2],
            "Illustrator": item[3],
            "Chater": item[4:]
        }

    with open(os.path.join(chdir, "difficulty.json"), encoding="utf8") as f:
        difficulty_data = json.load(f)

    for item in difficulty_data:
        song_id = item[0]
        if song_id in infos:
            infos[song_id]["difficulty"] = item[1:]

    tasks = [(id, info, levels, level) for id, info in infos.items() for level in range(len(info["difficulty"]))]
    try:
        if nozip:
            with _pbar(total=len(tasks), desc="CreatePEZ") as pbar:
                with ThreadPoolExecutor() as executor:
                    for id, info, levels, level in tasks:
                        executor.submit(create_file, chdir, id, info, levels, level, pbar, skipExisting)
        else:
            with _pbar(total=len(tasks), desc="CreatePEZ") as pbar:
                with ThreadPoolExecutor() as executor:
                    for id, info, levels, level in tasks:
                        executor.submit(create_zip_file, chdir, id, info, levels, level, pbar, skipExisting)
    finally:
        progress_cb = None
        stop_check = None

if __name__ == "__main__":
    run(os.getcwd(), False, skipExisting=True)