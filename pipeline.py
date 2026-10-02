"""流程编排层：把 main.py 的模块级流程拆成可单独/顺序执行的步骤。

不依赖 Qt，供 gui.py 调度，也可被命令行复用。

约定：
- 每个步骤签名 step(ctx, progress, stop)：
    ctx     -- Context，跨步骤共享状态
    progress(current, total, message) 回调；total<=0 表示不确定进度
    stop()  返回 True 表示用户请求取消，步骤应尽快抛出 StepCancelled
- 前置条件不满足时抛 StepError（带人类可读的中文提示）
"""
import datetime
import json
import os
import time
from configparser import ConfigParser
from dataclasses import dataclass
from typing import Callable, List, Optional

Progress = Callable[[int, int, str], None]
StopCheck = Callable[[], bool]

APP_ID = 165287
CONFIG_PATH = "config.ini"


class StepError(Exception):
    """步骤无法执行（缺文件、配置错误等）。"""


class StepCancelled(Exception):
    """用户主动取消。"""


def _noop_progress(current: int, total: int, message: str) -> None:
    pass


def _noop_stop() -> bool:
    return False


def load_config(path: str = CONFIG_PATH) -> ConfigParser:
    cfg = ConfigParser()
    if not os.path.exists(path):
        raise StepError(f"配置文件不存在: {os.path.abspath(path)}")
    cfg.read(path, encoding="utf8")
    return cfg


def save_config(cfg: ConfigParser, path: str = CONFIG_PATH) -> None:
    from io import StringIO
    buf = StringIO()
    cfg.write(buf)
    with open(path, "w", encoding="utf8") as f:
        f.write(buf.getvalue().rstrip("\n") + "\n")


@dataclass
class Context:
    """跨步骤共享的状态。"""
    ver_now: str = ""            # 用户输入的当前版本
    ver: str = ""                # 本次流程确定的目标版本
    download_url: str = ""
    manual_apk: str = ""         # 用户手动指定的 apk 路径
    chdir: str = "data"
    cancelled: bool = False

    @property
    def apk_name(self) -> str:
        ver = self.ver or self.ver_now
        return f"Phigros_{ver}.apk"

    @property
    def apk_path(self) -> str:
        return self.manual_apk or self.apk_name

    def stop(self) -> bool:
        return self.cancelled


def _check_stop(stop: StopCheck) -> None:
    if stop():
        raise StepCancelled()


def _require_apk(ctx: Context) -> str:
    path = ctx.apk_path
    if not os.path.exists(path):
        raise StepError(
            f"APK 不存在: {os.path.abspath(path)}\n"
            "请先执行「检查更新 / 下载 APK」，或手动选择 APK 文件。"
        )
    return path


def _require_files(ctx: Context, names: List[str], hint: str) -> None:
    missing = [n for n in names if not os.path.exists(os.path.join(ctx.chdir, n))]
    if missing:
        raise StepError(f"缺少 {', '.join(missing)}，{hint}")


def _read_version_record(chdir: str) -> Optional[dict]:
    """读取 data/version.json；缺失或损坏返回 None。"""
    try:
        with open(os.path.join(chdir, "version.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _allow_skip_game_info(ctx: Context, cfg: ConfigParser) -> bool:
    """skipExisting 仅对同一版本生效：版本变化或记录缺失时强制重新提取。"""
    if not cfg["SETTING"].getboolean("skipExisting", fallback=True):
        return False
    record = _read_version_record(ctx.chdir)
    if record is None:
        return False
    ver = ctx.ver or ctx.ver_now
    if ver:
        return record.get("version") == ver
    # 版本号未知（手动指定 APK）→ 退回按 APK 文件名核对
    recorded_apk = os.path.basename(str(record.get("apk_name") or ""))
    current_apk = os.path.basename(ctx.apk_path)
    return bool(recorded_apk) and recorded_apk == current_apk


def _ensure_version(ctx: Context, cfg: ConfigParser) -> None:
    """确保 ctx.ver / download_url 已就绪（供单步执行时懒加载）。"""
    setting = cfg["SETTING"]
    if not setting.getboolean("autoUpdate"):
        if not ctx.ver_now:
            raise StepError("未提供当前版本号，无法确定 APK 文件名。")
        if not ctx.ver:
            ctx.ver = ctx.ver_now
    if not ctx.download_url or not ctx.ver:
        import taptap
        r = taptap.taptap(APP_ID)
        ctx.download_url = r["data"]["apk"]["download"]
        if not ctx.ver:
            ctx.ver = r["data"]["apk"]["version_name"]


# ---------------------------------------------------------------- 步骤实现

def step_check_version(ctx: Context, progress: Progress, stop: StopCheck) -> None:
    """等待触发时间 + 轮询 TapTap 直到出现新版本。"""
    cfg = load_config()
    setting = cfg["SETTING"]

    target_time = setting.get("triggerTime")
    if target_time:
        deadline = datetime.datetime.strptime(target_time, "%Y-%m-%d %H:%M:%S")
        while datetime.datetime.now() < deadline:
            _check_stop(stop)
            remaining = int((deadline - datetime.datetime.now()).total_seconds())
            print(f"等待触发时间 {target_time}（剩余 {remaining}s）", end="\r")
            progress(0, 0, f"等待触发时间（剩余 {remaining}s）")
            time.sleep(1)
        print()

    if not setting.getboolean("autoUpdate"):
        if not ctx.ver_now:
            raise StepError("autoUpdate 已关闭，但未填写当前版本号。")
        ctx.ver = ctx.ver_now
        print(f"跳过更新检查，使用版本: {ctx.ver}")
        progress(1, 1, ctx.ver)
        return

    import taptap
    times = 0
    while True:
        _check_stop(stop)
        try:
            r = taptap.taptap(APP_ID)
            remote = r["data"]["apk"]["version_name"]
            ctx.download_url = r["data"]["apk"]["download"]
            print(f"TapTap: {remote} ({times})", end="\r")
            progress(0, 0, f"TapTap: {remote} ({times})")
            if remote != ctx.ver_now:
                ctx.ver = remote
                print(f"\n发现新版本: {ctx.ver}")
                break
        except StepCancelled:
            raise
        except Exception as e:
            print(f"TapTap: null ({e})", end="\r")
        times += 1
        time.sleep(1)


def step_download(ctx: Context, progress: Progress, stop: StopCheck) -> None:
    """下载 APK（已存在或手动指定时跳过）。"""
    cfg = load_config()
    setting = cfg["SETTING"]

    if ctx.manual_apk:
        if not os.path.exists(ctx.manual_apk):
            raise StepError(f"手动指定的 APK 不存在: {ctx.manual_apk}")
        print(f"使用手动指定的 APK: {ctx.manual_apk}")
        progress(1, 1, "已就绪")
        return

    if not ctx.ver:
        if setting.getboolean("autoUpdate"):
            _ensure_version(ctx, cfg)
        else:
            if not ctx.ver_now:
                raise StepError("未提供当前版本号，无法确定 APK 文件名。")
            ctx.ver = ctx.ver_now
    apk_name = ctx.apk_name
    if os.path.exists(apk_name):
        print("Apk exists, skip download")
        progress(1, 1, "已存在")
        return

    if not setting.getboolean("autoDownload"):
        raise StepError(
            f"autoDownload 已关闭，且本地不存在 {apk_name}。\n"
            "请手动下载后放到工作目录，或在界面中选择 APK 文件。"
        )

    if not ctx.download_url:
        import taptap
        r = taptap.taptap(APP_ID)
        ctx.download_url = r["data"]["apk"]["download"]
    import taptap

    print(f"开始下载: {apk_name}")
    start_time = time.time()

    def on_progress(pct: int, done: int, total: int) -> None:
        progress(done, total, f"{apk_name} {pct}%")

    try:
        taptap.download_mt(ctx.download_url, apk_name, progress_cb=on_progress, stop_check=stop)
    except taptap.DownloadCancelled:
        raise StepCancelled()
    print(f"elapsed time: {time.time() - start_time} s")


def step_game_info(ctx: Context, progress: Progress, stop: StopCheck) -> None:
    """提取难度/曲目元数据 → data/*.json。"""
    cfg = load_config()
    setting = cfg["SETTING"]
    apk = _require_apk(ctx)
    os.makedirs(ctx.chdir, exist_ok=True)
    _check_stop(stop)

    skip = _allow_skip_game_info(ctx, cfg)
    if setting.getboolean("skipExisting", fallback=True) and not skip:
        print("skipExisting 不适用：版本已变化或版本记录缺失，强制重新提取游戏信息")

    print(f"提取游戏信息: {apk}")
    progress(0, 0, "提取游戏信息…")
    import gameInformation
    gameInformation.run(apk, ctx.chdir, bool(setting.getboolean("outputCsv")),
                        skipExisting=skip)
    progress(1, 1, "完成")


def step_extract(ctx: Context, progress: Progress, stop: StopCheck) -> None:
    """提取资源（谱面/插图/音乐/头像）。"""
    cfg = load_config()
    types = cfg["TYPES"]
    update = cfg["UPDATE"]
    apk = _require_apk(ctx)
    os.makedirs(ctx.chdir, exist_ok=True)

    if types.getboolean("avatar") and not os.path.exists(os.path.join(ctx.chdir, "avatar.json")):
        raise StepError("缺少 data/avatar.json，请先执行「提取游戏信息」。")
    if any(update.getint(k) for k in ("main_story", "side_story", "other_song")) and \
            not os.path.exists(os.path.join(ctx.chdir, "difficulty.json")):
        raise StepError("增量提取需要 data/difficulty.json，请先执行「提取游戏信息」。")

    _check_stop(stop)
    print(f"开始提取资源: {apk}")
    progress(0, 0, "准备提取…")
    import getResource

    def on_progress(current: int, total: int, message: str) -> None:
        progress(current, total, message)

    try:
        getResource.run(apk, ctx.chdir, {
            "avatar": types.getboolean("avatar"),
            "Chart": types.getboolean("Chart"),
            "IllustrationBlur": types.getboolean("illustrationBlur"),
            "IllustrationLowRes": types.getboolean("illustrationLowRes"),
            "Illustration": types.getboolean("illustration"),
            "music": types.getboolean("music"),
            "UPDATE": {
                "main_story": update.getint("main_story"),
                "side_story": update.getint("side_story"),
                "other_song": update.getint("other_song"),
            },
        }, progress_callback=on_progress, stop_checker=stop)
    except getResource.ExtractCancelled:
        raise StepCancelled()


def step_pack(ctx: Context, progress: Progress, stop: StopCheck) -> None:
    """打包 .pez 到 data/phira/。"""
    _require_files(
        ctx, ["info.json", "difficulty.json"],
        "请先执行「提取游戏信息」。"
    )
    _check_stop(stop)
    print("开始打包 .pez")
    progress(0, 0, "准备打包…")
    import phira

    def on_progress(current: int, total: int, message: str) -> None:
        progress(current, total, message)

    try:
        phira.run(ctx.chdir, False, progress_callback=on_progress, stop_checker=stop)
    except phira.PackCancelled:
        raise StepCancelled()
    print("打包完成")


def step_covers(ctx: Context, progress: Progress, stop: StopCheck) -> None:
    """为 data/Illustration 下所有插图生成封面。"""
    input_directory = os.path.join(ctx.chdir, "Illustration")
    if not os.path.isdir(input_directory):
        raise StepError(f"插图目录不存在: {input_directory}，请先执行「提取资源」。")
    _require_files(ctx, ["info.json", "difficulty.json"], "请先执行「提取游戏信息」。")

    files = sorted(f for f in os.listdir(input_directory) if f.endswith(".png"))
    if not files:
        raise StepError(f"{input_directory} 下没有 .png 插图。")
    output_directory = os.path.join(ctx.chdir, "output", "Cover")
    os.makedirs(output_directory, exist_ok=True)

    import autoImage
    for i, name in enumerate(files, 1):
        _check_stop(stop)
        progress(i - 1, len(files), name)
        src = os.path.join(input_directory, name)
        dst = os.path.join(output_directory, name)
        ok = autoImage.run(src, dst)
        if not ok:
            print(f"封面生成失败: {name}")
        progress(i, len(files), name)
    print(f"封面生成完成 → {output_directory}")


def step_render(ctx: Context, progress: Progress, stop: StopCheck) -> None:
    """调用外部 Phi-Recorder 渲染视频。"""
    cfg = load_config()
    setting = cfg["SETTING"]
    phi_render = setting.get("phiRender", "")
    if not phi_render or not os.path.exists(phi_render):
        raise StepError(f"phiRender 路径不存在: {phi_render}")

    difficulties = [d for d in ("AT", "IN", "HD", "EZ") if setting.getboolean(d)]
    if not difficulties:
        raise StepError("未勾选任何渲染难度（AT/IN/HD/EZ）。")

    plan = []
    for diff in difficulties:
        folder = os.path.join(ctx.chdir, "phira", diff)
        if os.path.isdir(folder):
            count = len([f for f in os.listdir(folder) if f.endswith(".pez")])
            if count:
                plan.append((diff, folder, count))
    if not plan:
        raise StepError("data/phira/ 下没有可渲染的 .pez，请先执行「打包 PEZ」。")

    import ttools
    output_root = os.path.join(ctx.chdir, "output")
    total = sum(c for _, _, c in plan)
    done = 0
    for diff, folder, count in plan:
        output_folder = os.path.join(output_root, diff)
        os.makedirs(output_folder, exist_ok=True)

        def on_progress(current: int, item_total: int, message: str,
                        _base=done, _diff=diff) -> None:
            progress(_base + current, total, f"{_diff}/{message}")

        ttools.sfileTask(phi_render, folder, output_folder,
                         progress_cb=on_progress, stop_check=stop)
        done += count
        _check_stop(stop)
    print(f"渲染完成 → {output_root}")


def step_version_json(ctx: Context, progress: Progress, stop: StopCheck) -> None:
    """写入 data/version.json。"""
    ver = ctx.ver or ctx.ver_now
    if not ver:
        raise StepError("版本号未知，请先执行「检查更新」或填写当前版本号。")
    os.makedirs(ctx.chdir, exist_ok=True)
    version_info = {
        "version": ver,
        "extracted_date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "apk_name": os.path.basename(ctx.apk_path),
    }
    with open(os.path.join(ctx.chdir, "version.json"), "w", encoding="utf-8") as f:
        json.dump(version_info, f, indent=2, ensure_ascii=False)
    print(f"版本信息已保存: {ver}")
    progress(1, 1, ver)


# ---------------------------------------------------------------- 步骤注册表

@dataclass(frozen=True)
class Step:
    id: str
    name: str
    func: Callable[[Context, Progress, StopCheck], None]
    desc: str = ""


STEPS: List[Step] = [
    Step("check_version", "检查更新", step_check_version,
         "等待触发时间并轮询 TapTap 获取新版本号"),
    Step("download", "下载 APK", step_download,
         "多线程下载 APK（已存在则跳过）"),
    Step("game_info", "提取游戏信息", step_game_info,
         "解析难度、曲目元数据、tips → data/*.json"),
    Step("extract", "提取资源", step_extract,
         "提取谱面/插图/音乐/头像（最耗时）"),
    Step("pack", "打包 PEZ", step_pack,
         "生成 data/phira/<难度>/*.pez"),
    Step("covers", "生成封面", step_covers,
         "为插图批量生成封面 → data/output/Cover"),
    Step("render", "渲染视频", step_render,
         "调用外部 Phi-Recorder 渲染（较慢）"),
    Step("version_json", "写入版本信息", step_version_json,
         "写入 data/version.json"),
]

STEP_MAP = {s.id: s for s in STEPS}


def run(step_ids: Optional[List[str]] = None,
        ctx: Optional[Context] = None,
        progress: Optional[Progress] = None,
        stop: Optional[StopCheck] = None) -> Context:
    """按顺序执行步骤；step_ids 为 None 时执行全部。

    返回执行结束时的 Context。错误/取消向上抛出。
    """
    ctx = ctx or Context()
    progress = progress or _noop_progress
    stop = stop or ctx.stop
    ids = [s.id for s in STEPS] if step_ids is None else step_ids

    for step_id in ids:
        if step_id not in STEP_MAP:
            raise StepError(f"未知步骤: {step_id}")
        step = STEP_MAP[step_id]
        if stop():
            raise StepCancelled()
        progress(0, 0, f"[{step.name}] 开始")
        step.func(ctx, progress, stop)
        progress(1, 1, f"[{step.name}] 完成")
    return ctx


if __name__ == "__main__":
    ver = input("now version: ")
    run(ctx=Context(ver_now=ver))
    input("Finish")
