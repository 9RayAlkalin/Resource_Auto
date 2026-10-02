import base64
from concurrent.futures import ThreadPoolExecutor
from configparser import ConfigParser
import gc
from io import BytesIO
import json
import os
from queue import Queue
import shutil
import sys
import threading
import time
import traceback
from tqdm import tqdm
from UnityPy import Environment
from UnityPy.classes import AudioClip
from UnityPy.enums import ClassIDType
from zipfile import ZipFile
from fsb5 import FSB5

class ByteReader:
    def __init__(self, data):
        self.data = data
        self.position = 0

    def readInt(self):
        self.position += 4
        return int.from_bytes(self.data[self.position-4:self.position], 'little')

queue_out = Queue()
queue_in = Queue()

def getbool(t):
    if t[:6] == "Chart_":
        return config["Chart"]
    else:
        return config[t]

def io():
    while True:
        item = queue_in.get()
        if item is None:
            break
        try:
            if isinstance(item, list):
                env = Environment()
                for i in range(1, len(item)):
                    env.load_file(item[0].read(f"assets/aa/Android/{item[i][1]}"), name=item[i][0])
                queue_out.put(env)
                del env
            else:
                path, resource = item
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                if isinstance(resource, BytesIO):
                    with resource:
                        with open(path, "wb") as f:
                            f.write(resource.getbuffer())
                else:
                    with open(path, "wb") as f:
                        f.write(resource)
        except Exception:
            # 单个文件失败不能让 IO 线程退出，否则主线程会阻塞在 queue_out.get()
            traceback.print_exc()
            if isinstance(item, list):
                queue_out.put(Environment())

def save_image(path, image):
    bytesIO = BytesIO()
    image.save(bytesIO, "png")
    queue_in.put((path, bytesIO))

def save_music(path, music: AudioClip):
    # queue_in.put((path, music.samples["music.wav"]))
    fsb = FSB5(music.m_AudioData)
    rebuilt_sample = fsb.rebuild_sample(fsb.samples[0])
    '''with open(path, 'wb') as fp:
        fp.write(rebuilt_sample)'''
    queue_in.put((path, rebuilt_sample))

classes = ClassIDType.TextAsset, ClassIDType.Sprite, ClassIDType.AudioClip

progress_cb = None
stop_check = None


class ExtractCancelled(Exception):
    """Raised when extraction is aborted via stop_check."""


def _pbar(iterable=None, total=None, desc="", **kwargs):
    """tqdm wrapper: when progress_cb is set, forward n/total/postfix to it."""
    cb = progress_cb
    if cb is None:
        return tqdm(iterable, total=total, desc=desc, **kwargs)

    class _GuiTqdm(tqdm):
        def update(self, n=1):
            result = super().update(n)
            cb(self.n, self.total, self.postfix or "")
            return result

        def set_postfix_str(self, s, **kw):
            result = super().set_postfix_str(s, **kw)
            cb(self.n, self.total, s)
            return result

    return _GuiTqdm(iterable, total=total, desc=desc, **kwargs)

def save(chdir, key, entry, pbar, skipExisting: bool = True):
    # 根据资源类型确定输出路径
    output_path = None
    
    if config["avatar"] and key.startswith("avatar."):
        avatar_name = key[7:] if key != "Cipher1" else avatar.get(key[7:], key)
        pbar.set_postfix_str(avatar_name)
        output_path = f"{chdir}/avatar/{avatar_name}.png"
        
    elif config["Chart"] and key[-14:-7] == "/Chart_" and key[-5:] == ".json":
        name = key[:-14]
        file_name = (name[:17] + '...') if len(name) > 20 else name
        pbar.set_postfix_str(file_name)
        output_path = f"{chdir}/Chart_%s/%s.json" % (key[-7:-5], name)
        
    # ... 其他条件类似处理，为每个资源类型设置 output_path
    
    # 检查文件是否存在
    if skipExisting and output_path and os.path.exists(output_path):
        pbar.set_postfix_str(f"{pbar.postfix} (已存在，跳过)")
        return
    obj = next(entry.get_filtered_objects(classes)).read()
    if config["avatar"] and key.startswith("avatar."):
        key = key[7:] if key != "Cipher1" else avatar.get(key[7:], key)
        pbar.set_postfix_str(key)
        bytesIO = BytesIO()
        obj.image.save(bytesIO, "png")
        queue_in.put((f"{chdir}/avatar/{key}.png", bytesIO))
    elif config["Chart"] and key[-14:-7] == "/Chart_" and key[-5:] == ".json":
        name = key[:-14]
        file_name = (name[:17] + '...') if len(name) > 20 else name
        pbar.set_postfix_str(file_name)
        queue_in.put((f"{chdir}/Chart_%s/%s.json" % (key[-7:-5], name), obj.script))
    elif config["Chart"] and key[-18:-11] == "/Chart_" and key[-5:] == ".json":
        name = key[:-18]
        file_name = (name[:17] + '...') if len(name) > 20 else name
        pbar.set_postfix_str(file_name)
        queue_in.put((f"{chdir}/Chart_%s/%s.json" % (key[-11:-5], name), obj.script))
    elif config["IllustrationBlur"] and key.endswith("/IllustrationBlur.jpg"):
        bytesIO = BytesIO()
        obj.image.save(bytesIO, "png")
        name = key[:-21]
        file_name = (name[:17] + '...') if len(name) > 20 else name
        pbar.set_postfix_str(file_name)
        queue_in.put((f"{chdir}/IllustrationBlur/{name}.png", bytesIO))
    elif config["IllustrationLowRes"] and key.endswith("/IllustrationLowRes.jpg"):
        name = key[:-23]
        file_name = (name[:17] + '...') if len(name) > 20 else name
        pbar.set_postfix_str(file_name)
        bytesIO = BytesIO()
        obj.image.save(bytesIO, "png")
        queue_in.put((f"{chdir}/IllustrationLowRes/{name}.png", bytesIO))
        #pool.submit(save_image, f"IllustrationLowRes/{name}.png", obj.image)
    elif config["Illustration"] and key.endswith("/Illustration.jpg"):
        name = key[:-17]
        file_name = (name[:17] + '...') if len(name) > 20 else name
        pbar.set_postfix_str(file_name)
        bytesIO = BytesIO()
        obj.image.save(bytesIO, "png")
        queue_in.put((f"{chdir}/Illustration/{name}.png", bytesIO))
        #pool.submit(save_image, f"Illustration/{name}.png", obj.image)
    elif config["Illustration"] and key[-20:-6] == "/Illustration_" and key[-4:] == ".jpg":
        name = key[:-20]
        level = key[-6:-4]
        file_name = (name[:17] + '...') if len(name) > 20 else name
        pbar.set_postfix_str(file_name)
        bytesIO = BytesIO()
        obj.image.save(bytesIO, "png")
        queue_in.put((f"{chdir}/Illustration/{name}_{level}.png", bytesIO))
    elif config["music"] and key.endswith("/music.wav"):
        name = key[:-10]
        file_name = (name[:17] + '...') if len(name) > 20 else name
        pbar.set_postfix_str(file_name)
        #pool.submit(save_music, f"music/{name}.ogg", obj)
        #queue_in.put((f"music/{name}.wav", obj.samples["music.wav"]))
        save_music(f"{chdir}/music/{name}.ogg", obj)
    elif config["music"] and key[-13:-6] == "/music_" and key[-4:] == ".wav":
        name = key[:-13]
        level = key[-6:-4]
        file_name = (name[:17] + '...') if len(name) > 20 else name
        pbar.set_postfix_str(file_name)
        save_music(f"{chdir}/music/{name}_{level}.ogg", obj)

def run(path: str, chdir: str, c, progress_callback=None, stop_checker=None):
    global config, progress_cb, stop_check
    config = c
    progress_cb = progress_callback
    stop_check = stop_checker
    # 上次异常退出可能在队列里残留脏数据，清掉避免下次运行读到旧 env
    while not queue_out.empty():
        queue_out.get_nowait()
    while not queue_in.empty():
        queue_in.get_nowait()
    with ZipFile(path) as apk:
        with apk.open("assets/aa/catalog.json") as f:
            data = json.load(f)

    type_list = ["avatar", "IllustrationBlur", "IllustrationLowRes", "Illustration", "music"]
    for directory in filter(lambda x: getbool(x), type_list):
        shutil.rmtree(os.path.join(chdir, directory), True)
        os.mkdir(os.path.join(chdir, directory))

    key = base64.b64decode(data["m_KeyDataString"])
    bucket = base64.b64decode(data["m_BucketDataString"])
    entry = base64.b64decode(data["m_EntryDataString"])

    table = []
    reader = ByteReader(bucket)
    for _ in range(reader.readInt()):
        key_position = reader.readInt()
        key_type = key[key_position]
        key_position += 1
        if key_type == 0:
            length = key[key_position]
            key_position += 4
            key_value = key[key_position:key_position + length].decode()
        elif key_type == 1:
            length = key[key_position]
            key_position += 4
            key_value = key[key_position:key_position + length].decode("utf16")
        elif key_type == 4:
            key_value = key[key_position]
        else:
            raise ValueError(f"Unknown key type: {key_type}")
        for _ in range(reader.readInt()):
            entry_position = reader.readInt()
            entry_value = entry[4 + 28 * entry_position:4 + 28 * entry_position + 28]
            entry_value = int.from_bytes(entry_value[8:10], 'little')
        table.append([key_value, entry_value])
    for i in range(len(table)):
        if table[i][1] != 65535:
            table[i][1] = table[table[i][1]][0]
        if isinstance(table[i][1], str) and table[i][1].endswith(".bundle"):
            table[i][1] = table[i][1].split("_")[-1]
    for i in range(len(table) - 1, -1, -1):
        if type(table[i][0]) == int or table[i][0][:15] == "Assets/Tracks/#" or table[i][0][:14] != "Assets/Tracks/" and table[i][0][:7] != "avatar.":
            del table[i]
        elif table[i][0][:14] == "Assets/Tracks/":
            table[i][0] = table[i][0][14:]

    # 谱面目录从 catalog 表动态推导（4.0.1 起新增 Chart_SP 等难度），并清理表中已不存在的目录
    if config["Chart"]:
        chart_dirs = set()
        for k, _ in table:
            if k[-14:-7] == "/Chart_" and k[-5:] == ".json":
                chart_dirs.add("Chart_" + k[-7:-5])
            elif k[-18:-11] == "/Chart_" and k[-5:] == ".json":
                chart_dirs.add("Chart_" + k[-11:-5])
        for name in os.listdir(chdir):
            if name.startswith("Chart_") and name not in chart_dirs:
                shutil.rmtree(os.path.join(chdir, name), True)
        for d in sorted(chart_dirs):
            shutil.rmtree(os.path.join(chdir, d), True)
            os.mkdir(os.path.join(chdir, d))

    global avatar
    if config["avatar"]:
        with open(os.path.join(chdir, "avatar.json"), encoding="utf8") as f:
            avatar = json.load(f)

    thread = threading.Thread(target=io)
    thread.start()

    global pool
    try:
        with ThreadPoolExecutor() as pool:
            if all(v == 0 for v in config["UPDATE"].values()):
                with ZipFile(path) as apk:
                    size = 0
                    batch = [apk]
                    pbar = _pbar(table, desc="Extract")
                    for key, entry in pbar:
                        if stop_check is not None and stop_check():
                            raise ExtractCancelled()
                        batch.append((key, entry, pbar))
                        size += apk.getinfo(f"assets/aa/Android/{entry}").file_size
                        if size > 32 * 1024 * 1024:
                            queue_in.put(batch)
                            env = queue_out.get()
                            for ikey, ientry in env.files.items():
                                save(chdir, ikey, ientry, pbar)
                            size = 0
                            batch = [apk]
                    queue_in.put(batch)
                    env = queue_out.get()
                    for ikey, ientry in env.files.items():
                        save(chdir, ikey, ientry, pbar)
            else:
                l = []
                with open(os.path.join(chdir, "difficulty.json"), encoding="utf8") as f:
                    l = json.load(f)
                lName = [item[0] for item in l]
                index1 = lName.index("Doppelganger.LeaF")
                index2 = lName.index("Poseidon.1112vsStar")
                # index1 = l.index("ENERGYSYNERGYMATRIX.Tanchiky") + 1 # 指定导出
                del lName[index2:len(l) - config["UPDATE"]["side_story"]] 
                del lName[index1:index2 - config["UPDATE"]["other_song"]] 
                del lName[:index1 - config["UPDATE"]["main_story"]]

                env = Environment()
                with ZipFile(path) as apk:
                    # pbar = _pbar(table, desc="Extract")
                    with _pbar(table, desc="FindChart") as pbar:
                        for key, entry in pbar:
                            if stop_check is not None and stop_check():
                                raise ExtractCancelled()
                            if key.startswith("avatar."):
                                env.load_file(apk.read(f"assets/aa/Android/{entry}"), name=key)
                            if any(key.startswith(f"{id}") for id in lName):
                                env.load_file(apk.read(f"assets/aa/Android/{entry}"), name=key)
                    with _pbar(env.files.items(), desc="Extract") as pbar:
                        for ikey, ientry in pbar:
                            if stop_check is not None and stop_check():
                                raise ExtractCancelled()
                            save(chdir, ikey, ientry, pbar)
    finally:
        queue_in.put(None)
        thread.join()
        progress_cb = None
        stop_check = None

if __name__ == "__main__":
    c = ConfigParser()
    c.read("config.ini", encoding="utf8")
    types = c["TYPES"]
    run(sys.argv[1], os.getcwd(), {
        "avatar": types.getboolean("avatar"),
        "Chart": types.getboolean("Chart"),
        "IllustrationBlur": types.getboolean("illustrationBlur"),
        "IllustrationLowRes": types.getboolean("illustrationLowRes"),
        "Illustration": types.getboolean("illustration"),
        "music": types.getboolean("music"),
        "UPDATE": {
            "main_story": c["UPDATE"].getint("main_story"),
            "side_story": c["UPDATE"].getint("side_story"),
            "other_song": c["UPDATE"].getint("other_song")
        }
    })
