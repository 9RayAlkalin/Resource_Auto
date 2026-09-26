import os
import shutil
from zipfile import ZipFile, ZIP_STORED, ZIP_DEFLATED
import json
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm

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

def create_zip_file(chdir, id, info, levels, level, pbar, skipExisting: bool = True):
    file_name = (id[:17] + '...') if len(id) > 20 else id
    pbar.set_postfix_str(file_name)
    pez_filename = f"{chdir}/phira/{levels[level]}/{id}-{levels[level]}.pez"

    if skipExisting and os.path.exists(pez_filename):
        pbar.set_postfix_str(f"{file_name} (已存在，跳过)")
        pbar.update(1)
        return
    num = ".0"
    if os.path.exists(f"{chdir}/Chart_{levels[level]}/{id}{num}.json"):
        with ZipFile(pez_filename, "w", compression=ZIP_DEFLATED) as pez:
            pez.writestr("info.yml", build_info_yml(info, id, levels[level], level))

            pez.write(f"{chdir}/Chart_{levels[level]}/{id}{num}.json", f"{id}.json")
            pez.write(f"{chdir}/Illustration/{id}{num}.png", f"{id}.png")
            pez.write(f"{chdir}/music/{id}{num}.ogg", f"{id}.ogg")
            if os.path.exists(f"{chdir}/music/{id}{num}_EZ.ogg"):
                pez.write(f"{chdir}/music/{id}{num}_EZ.ogg", f"{id}_EZ.ogg")
            if os.path.exists(f"{chdir}/music/{id}{num}_HD.ogg"):
                pez.write(f"{chdir}/music/{id}{num}_HD.ogg", f"{id}_HD.ogg")
            if os.path.exists(f"{chdir}/music/{id}{num}_IN.ogg"):
                pez.write(f"{chdir}/music/{id}{num}_IN.ogg", f"{id}_IN.ogg")
            if os.path.exists(f"{chdir}/music/{id}{num}_AT.ogg"):
                pez.write(f"{chdir}/music/{id}{num}_AT.ogg", f"{id}_AT.ogg")
    pbar.update(1)

def create_file(chdir, id, info, levels, level, pbar, skipExisting: bool = True):
    file_name = (id[:17] + '...') if len(id) > 20 else id
    pbar.set_postfix_str(file_name)
    dir_path = f"{chdir}/phira/{levels[level]}/{id}-{levels[level]}"

    if skipExisting and os.path.exists(dir_path):
        pbar.set_postfix_str(f"{file_name} (已存在，跳过)")
        pbar.update(1)
        return
    num = ".0"
    os.makedirs(dir_path, exist_ok=True)

    with open(f"{dir_path}/info.yml", "w", encoding="utf-8") as f:
        f.write(build_info_yml(info, id, levels[level], level))

    shutil.copy(f"{chdir}/Chart_{levels[level]}/{id}{num}.json", f"{dir_path}/{id}.json")
    shutil.copy(f"{chdir}/Illustration/{id}{num}.png", f"{dir_path}/{id}.png")
    shutil.copy(f"{chdir}/music/{id}{num}.ogg", f"{dir_path}/{id}.ogg")

    pbar.update(1)

def run(chdir: str, nozip: bool, skipExisting: bool = True):
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
    if nozip:
        with tqdm(total=len(tasks), desc="CreatePEZ") as pbar:
            with ThreadPoolExecutor() as executor:
                for id, info, levels, level in tasks:
                    executor.submit(create_file, chdir, id, info, levels, level, pbar, skipExisting)
    else:
        with tqdm(total=len(tasks), desc="CreatePEZ") as pbar:
            with ThreadPoolExecutor() as executor:
                for id, info, levels, level in tasks:
                    executor.submit(create_zip_file, chdir, id, info, levels, level, pbar, skipExisting)

if __name__ == "__main__":
    run(os.getcwd(), False, skipExisting=True)