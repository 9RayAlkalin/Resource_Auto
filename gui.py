"""PyQt5 图形界面入口：python gui.py

三个标签页：
  流程 -- 步骤列表（状态 + 单步运行）、进度条、开始/停止控制
  配置 -- config.ini 可视化编辑与保存
  日志 -- print/tqdm 输出（stdout/stderr 重定向，行内刷新不刷屏）
主流程按固定顺序执行，配置里 autoCover/autoRender 决定可选步骤是否跳过。
"""
import os
import sys
import threading
import time
import traceback
from configparser import ConfigParser

from PyQt5.QtCore import QObject, Qt, QThread, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices, QFont, QFontDatabase, QTextCursor
from PyQt5.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QPlainTextEdit, QProgressBar, QPushButton,
    QScrollArea, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

import pipeline

os.chdir(os.path.dirname(os.path.abspath(__file__)))

TYPES_KEYS = ["avatar", "Chart", "IllustrationBlur", "IllustrationLowRes",
              "Illustration", "music"]
UPDATE_KEYS = ["main_story", "other_song", "side_story"]
SETTING_KEYS = ["outputCsv", "skipExisting", "autoUpdate", "autoDownload",
                "autoCover", "autoRender", "phiRender", "triggerTime",
                "pause", "AT", "IN", "HD", "EZ"]
SETTING_BOOL_KEYS = [k for k in SETTING_KEYS
                     if k not in ("phiRender", "triggerTime")]

STEP_COLORS = {
    "pending": "#888888",
    "running": "#2d7ff9",
    "ok": "#1a9f3f",
    "failed": "#d93025",
    "stopped": "#b06000",
}
STEP_STATUS_TEXT = {
    "pending": "待执行",
    "running": "运行中",
    "ok": "成功",
    "failed": "失败",
    "stopped": "已停止",
}


def _as_bool(value, default=True):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


class StreamEmitter(QObject):
    """替换 sys.stdout/stderr；回车触发行内刷新，换行提交整行。"""

    line = pyqtSignal(str)
    partial = pyqtSignal(str)

    def __init__(self, real):
        super().__init__()
        self._real = real
        self._lock = threading.Lock()
        self._cur = ""
        self._last_partial = None

    def write(self, s):
        if not s:
            return 0
        if not isinstance(s, str):
            s = str(s)
        try:
            self._real.write(s)
        except Exception:
            pass
        with self._lock:
            for ch in s:
                if ch == "\n":
                    text, self._cur = self._cur, ""
                    self._last_partial = None
                    self.line.emit(text)
                elif ch == "\r":
                    self._cur = ""
                else:
                    self._cur += ch
            if self._cur and self._cur != self._last_partial:
                self._last_partial = self._cur
                self.partial.emit(self._cur)
        return len(s)

    def flush(self):
        try:
            self._real.flush()
        except Exception:
            pass

    def isatty(self):
        return True

    def fileno(self):
        return self._real.fileno()

    @property
    def encoding(self):
        return "utf-8"

    def writable(self):
        return True


class LogWidget(QPlainTextEdit):
    """日志区：支持行内刷新（行尾刷新不追加新行）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(5000)
        self.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self._partial = False

    def append_line(self, text):
        if self._partial:
            if text:
                self._replace_last(text)
            self._partial = False
            return
        self.appendPlainText(text if text else " ")

    def append_partial(self, text):
        if self._partial:
            self._replace_last(text)
        else:
            self.appendPlainText(text)
            self._partial = True

    def _replace_last(self, text):
        cursor = QTextCursor(self.document().lastBlock())
        cursor.select(QTextCursor.BlockUnderCursor)
        cursor.insertText(text if text else " ")

    def clear_log(self):
        self.clear()
        self._partial = False


class PipelineWorker(QThread):
    """在后台线程中顺序执行步骤。"""

    progress = pyqtSignal(float, float, str)      # current, total, message（float 避免字节数>INT_MAX 时溢出）
    step_status = pyqtSignal(str, str)            # step_id, status
    run_finished = pyqtSignal(bool, str)          # success, message

    def __init__(self, step_ids, ctx, parent=None):
        super().__init__(parent)
        # macOS 上 QThread 默认栈仅 ~512KB，UnityPy 等深层 import 链会
        # 触发 RecursionError: Stack overflow，显式放大到与 Python 线程一致
        self.setStackSize(16 * 1024 * 1024)
        self.step_ids = step_ids
        self.ctx = ctx

    def run(self):
        success = True
        message = "全部完成"
        current = None
        try:
            for step_id in self.step_ids:
                if self.ctx.cancelled:
                    raise pipeline.StepCancelled()
                current = step_id
                self.step_status.emit(step_id, "running")
                step = pipeline.STEP_MAP[step_id]
                print(f"===== [{step.name}] =====")

                def on_progress(cur, total, msg, _name=step.name):
                    self.progress.emit(float(cur or 0), float(total or 0),
                                       f"{_name}: {msg}" if msg else _name)

                step.func(self.ctx, on_progress, self.ctx.stop)
                self.step_status.emit(step_id, "ok")
            if self.ctx.cancelled:
                raise pipeline.StepCancelled()
        except pipeline.StepCancelled:
            success = False
            message = "已停止"
            if current:
                self.step_status.emit(current, "stopped")
            print("已停止")
        except pipeline.StepError as e:
            success = False
            message = str(e)
            if current:
                self.step_status.emit(current, "failed")
            print(f"步骤失败: {e}", file=sys.stderr)
        except Exception as e:
            success = False
            message = f"{type(e).__name__}: {e}"
            if current:
                self.step_status.emit(current, "failed")
            traceback.print_exc()
        self.run_finished.emit(success, message)


class StepRow(QWidget):
    """流程页单个步骤行：步骤名 + 状态 + 单步运行按钮。"""

    run_one = pyqtSignal(str)

    def __init__(self, step, parent=None):
        super().__init__(parent)
        self.step_id = step.id
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        name = QLabel(step.name)
        name.setToolTip(step.desc)
        self.status = QLabel("待执行")
        self.status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.status.setMinimumWidth(52)
        self.btn = QPushButton("运行")
        self.btn.setToolTip(f"单独执行「{step.name}」")
        self.btn.setFixedWidth(48)
        self.btn.clicked.connect(lambda: self.run_one.emit(self.step_id))
        layout.addWidget(name, 1)
        layout.addWidget(self.status)
        layout.addWidget(self.btn)
        self.set_status("pending")

    def set_status(self, status):
        text = STEP_STATUS_TEXT.get(status, status)
        self.status.setText(text)
        self.status.setStyleSheet(
            f"color: {STEP_COLORS.get(status, '#888888')}; font-weight: bold;")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Phigros Resource Auto")
        self.setMinimumSize(640, 540)
        self.worker = None
        self.ctx = None
        self._stage_base = "就绪"
        self._rate_state = None
        self._rate_text = ""
        self._stdout = sys.stdout
        self._stderr = sys.stderr

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(4, 4, 4, 4)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self.tabs.addTab(self._build_flow_tab(), "流程")
        self.tabs.addTab(self._build_config_panel(), "配置")
        self.tabs.addTab(self._build_log_tab(), "日志")

        self._install_stream_redirect()
        self.load_config_to_form()

        # 依据内容自适应窗口大小，限制在屏幕可用区域内，避免固定 1100x760 过大
        hint = self.sizeHint()
        geo = QApplication.primaryScreen().availableGeometry()
        w = min(hint.width() + 120, geo.width() - 40)
        h = min(hint.height() + 90, geo.height() - 80)
        self.resize(max(720, w), max(540, h))

    # ------------------------------------------------------------ UI 构建

    def _build_flow_tab(self):
        page = QWidget()
        lay = QVBoxLayout(page)

        self.step_panel = QGroupBox("流程步骤（固定顺序执行，可单步重跑）")
        steps_lay = QVBoxLayout(self.step_panel)
        self.step_rows = {}
        for step in pipeline.STEPS:
            row = StepRow(step)
            row.run_one.connect(self.run_single)
            self.step_rows[step.id] = row
            steps_lay.addWidget(row)
        steps_lay.addStretch(1)
        lay.addWidget(self.step_panel, 1)

        self.stage_label = QLabel("就绪")
        lay.addWidget(self.stage_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        lay.addWidget(self.progress_bar)

        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("开始流程")
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setEnabled(False)
        self.open_btn = QPushButton("打开输出目录")
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.stop_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.open_btn)
        lay.addLayout(btn_row)

        self.start_btn.clicked.connect(lambda: self.start(self.flow_step_ids()))
        self.stop_btn.clicked.connect(self.stop_run)
        self.open_btn.clicked.connect(self.open_output_dir)
        return page

    def _build_log_tab(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        self.log = LogWidget()
        lay.addWidget(self.log, 1)
        btn_row = QHBoxLayout()
        self.clear_btn = QPushButton("清空日志")
        self.clear_btn.clicked.connect(self.log.clear_log)
        btn_row.addStretch(1)
        btn_row.addWidget(self.clear_btn)
        lay.addLayout(btn_row)
        return page

    def _build_config_panel(self):
        outer = QWidget()
        outer_lay = QVBoxLayout(outer)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        form_host = QWidget()
        form = QVBoxLayout(form_host)
        form.setContentsMargins(0, 0, 0, 0)

        basic = QGroupBox("基本")
        basic_lay = QVBoxLayout(basic)
        row = QHBoxLayout()
        row.addWidget(QLabel("当前版本号:"))
        self.ver_edit = QLineEdit()
        self.ver_edit.setPlaceholderText("如 3.10.2（autoUpdate 开启时用于比对）")
        row.addWidget(self.ver_edit)
        basic_lay.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("手动 APK:"))
        self.apk_edit = QLineEdit()
        self.apk_edit.setPlaceholderText("留空则自动下载/使用 Phigros_<版本>.apk")
        row.addWidget(self.apk_edit)
        apk_browse = QPushButton("浏览…")
        apk_browse.clicked.connect(self.browse_apk)
        row.addWidget(apk_browse)
        basic_lay.addLayout(row)
        form.addWidget(basic)

        types_box = QGroupBox("资源类型 [TYPES]")
        types_lay = QVBoxLayout(types_box)
        self.type_checks = {}
        for key in TYPES_KEYS:
            check = QCheckBox(key)
            self.type_checks[key] = check
            types_lay.addWidget(check)
        form.addWidget(types_box)

        update_box = QGroupBox("增量提取 [UPDATE]（0 = 全量）")
        update_lay = QVBoxLayout(update_box)
        self.update_spins = {}
        for key in UPDATE_KEYS:
            row = QHBoxLayout()
            row.addWidget(QLabel(key))
            spin = QSpinBox()
            spin.setRange(0, 9999)
            self.update_spins[key] = spin
            row.addWidget(spin)
            row.addStretch(1)
            update_lay.addLayout(row)
        form.addWidget(update_box)

        setting_box = QGroupBox("行为开关 [SETTING]")
        setting_lay = QVBoxLayout(setting_box)
        self.setting_checks = {}
        for key in SETTING_BOOL_KEYS:
            check = QCheckBox(key)
            self.setting_checks[key] = check
            setting_lay.addWidget(check)
        row = QHBoxLayout()
        row.addWidget(QLabel("phiRender"))
        self.phirender_edit = QLineEdit()
        row.addWidget(self.phirender_edit)
        pr_browse = QPushButton("浏览…")
        pr_browse.clicked.connect(self.browse_phi_render)
        row.addWidget(pr_browse)
        setting_lay.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("triggerTime"))
        self.triggertime_edit = QLineEdit()
        self.triggertime_edit.setPlaceholderText("YYYY-MM-DD HH:MM:SS，留空不等待")
        row.addWidget(self.triggertime_edit)
        setting_lay.addLayout(row)
        form.addWidget(setting_box)

        save_btn = QPushButton("保存配置到 config.ini")
        save_btn.clicked.connect(self.save_form_to_config)
        form.addWidget(save_btn)
        form.addStretch(1)

        scroll.setWidget(form_host)
        outer_lay.addWidget(scroll)
        return outer

    # ------------------------------------------------------------ 配置读写

    def load_config_to_form(self):
        cfg = ConfigParser()
        if not cfg.read("config.ini", encoding="utf8"):
            print("警告: 未找到 config.ini，使用控件默认值", file=sys.stderr)
            return
        for key in TYPES_KEYS:
            if cfg.has_option("TYPES", key):
                self.type_checks[key].setChecked(
                    _as_bool(cfg.get("TYPES", key)))
        for key in UPDATE_KEYS:
            if cfg.has_option("UPDATE", key):
                self.update_spins[key].setValue(cfg.getint("UPDATE", key))
        for key in SETTING_BOOL_KEYS:
            if cfg.has_option("SETTING", key):
                self.setting_checks[key].setChecked(
                    _as_bool(cfg.get("SETTING", key)))
        if cfg.has_option("SETTING", "phiRender"):
            self.phirender_edit.setText(cfg.get("SETTING", "phiRender"))
        if cfg.has_option("SETTING", "triggerTime"):
            self.triggertime_edit.setText(cfg.get("SETTING", "triggerTime"))

    def save_form_to_config(self):
        cfg = ConfigParser()
        cfg.optionxform = str  # 保留 config.ini 原始键名大小写
        cfg.read("config.ini", encoding="utf8")
        for section in ("TYPES", "UPDATE", "SETTING"):
            if not cfg.has_section(section):
                cfg.add_section(section)
        for key, check in self.type_checks.items():
            cfg.set("TYPES", key, str(check.isChecked()))
        for key, spin in self.update_spins.items():
            cfg.set("UPDATE", key, str(spin.value()))
        for key, check in self.setting_checks.items():
            cfg.set("SETTING", key, str(check.isChecked()))
        cfg.set("SETTING", "phiRender", self.phirender_edit.text().strip())
        cfg.set("SETTING", "triggerTime", self.triggertime_edit.text().strip())
        pipeline.save_config(cfg)
        print("配置已保存: config.ini")

    # ------------------------------------------------------------ 文件浏览

    def browse_apk(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 APK 文件", os.getcwd(), "APK (*.apk);;所有文件 (*)")
        if path:
            self.apk_edit.setText(path)

    def browse_phi_render(self):
        start = self.phirender_edit.text().strip() or os.getcwd()
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 Phi-Recorder", start, "所有文件 (*)")
        if path:
            self.phirender_edit.setText(path)

    # ------------------------------------------------------------ 流程控制

    def flow_step_ids(self):
        """整体流程：固定顺序，可选步骤按配置跳过。"""
        ids = [s.id for s in pipeline.STEPS]
        if not self.setting_checks["autoCover"].isChecked():
            ids.remove("covers")
        if not self.setting_checks["autoRender"].isChecked():
            ids.remove("render")
        return ids

    def make_context(self):
        ctx = pipeline.Context()
        ctx.ver_now = self.ver_edit.text().strip()
        ctx.manual_apk = self.apk_edit.text().strip()
        return ctx

    def start(self, step_ids):
        if self.worker and self.worker.isRunning():
            return
        if not step_ids:
            print("未勾选任何步骤", file=sys.stderr)
            return
        self.save_form_to_config()
        self.ctx = self.make_context()
        self._reset_statuses(step_ids)
        self.worker = PipelineWorker(step_ids, self.ctx)
        self._connect_worker(self.worker)
        self._set_running(True)
        self.worker.start()

    def run_single(self, step_id):
        if self.worker and self.worker.isRunning():
            print("流程运行中，请先停止", file=sys.stderr)
            return
        self.save_form_to_config()
        self.ctx = self.make_context()
        self._reset_statuses([step_id])
        self.worker = PipelineWorker([step_id], self.ctx)
        self._connect_worker(self.worker)
        self._set_running(True)
        self.worker.start()

    def stop_run(self):
        if self.ctx:
            self.ctx.cancelled = True
            self.stage_label.setText("正在停止…")
            self.stop_btn.setEnabled(False)

    def _connect_worker(self, worker):
        worker.progress.connect(self.on_progress)
        worker.step_status.connect(self.on_step_status)
        worker.run_finished.connect(self.on_run_finished)

    def _set_running(self, running):
        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        for row in self.step_rows.values():
            row.btn.setEnabled(not running)

    def _reset_statuses(self, active_ids):
        for row in self.step_rows.values():
            row.set_status("pending")

    def on_step_status(self, step_id, status):
        row = self.step_rows.get(step_id)
        if row:
            row.set_status(status)

    def on_progress(self, current, total, message):
        if message:
            self._stage_base = message
        # 速率/百分比用原始值计算（下载为字节数）
        self._update_rate(float(current or 0), float(total or 0))
        # 进度条可能收到超过 int32 的值（如 APK 3.5GB 字节数），
        # 统一缩放避免 QProgressBar.setRange OverflowError
        INT_MAX = 2147483647
        current = float(current or 0)
        total = float(total or 0)
        if total > 0:
            if total > INT_MAX:
                current = current * INT_MAX / total
                total = float(INT_MAX)
            if self.progress_bar.maximum() != int(total):
                self.progress_bar.setRange(0, int(total))
            self.progress_bar.setValue(min(int(current), int(total)))
        else:
            self.progress_bar.setRange(0, 0)

    def _update_rate(self, current, total):
        """在标签后追加 百分比/速度/预计剩余时间（按进度回调到达速率推算）。"""
        now = time.monotonic()
        pct = ""
        if total > 0:
            pct = "" if "%" in self._stage_base else f" ({current * 100 / total:.1f}%)"
            last = self._rate_state
            if last is None or last["total"] != total:
                # 新的进度流：重置速率缓存
                self._rate_state = {"t": now, "c": current, "total": total}
                self._rate_text = ""
            else:
                dt = now - last["t"]
                delta = current - last["c"]
                # 窗口不够长时不重置锚点，继续累积到可计算为止
                if delta > 0 and dt >= 0.2:
                    rate = delta / dt
                    self._rate_text = (
                        f" | {self._fmt_rate(rate)}"
                        f" | 预计剩余 {self._fmt_eta((total - current) / rate)}")
                    self._rate_state = {"t": now, "c": current, "total": total}
                elif delta <= 0 and dt >= 2.0:
                    # 长时间无进度（如大文件处理中），重置锚点避免速率失真
                    self._rate_state = {"t": now, "c": current, "total": total}
        else:
            self._rate_state = None
            self._rate_text = ""
        self.stage_label.setText(f"{self._stage_base}{pct}{self._rate_text}")

    @staticmethod
    def _fmt_rate(rate):
        # 速率量级大（字节/秒）时按 MB/s 显示，否则按 项/秒
        if rate >= 100000:
            return f"{rate / 1048576:.1f} MB/s"
        if rate >= 100:
            return f"{rate:.0f}/s"
        if rate >= 1:
            return f"{rate:.1f}/s"
        return f"{rate:.3f}/s"

    @staticmethod
    def _fmt_eta(seconds):
        seconds = int(seconds)
        if seconds >= 3600:
            return f"{seconds // 3600}时{(seconds % 3600) // 60:02d}分"
        if seconds >= 60:
            return f"{seconds // 60}:{seconds % 60:02d}"
        return f"{seconds}秒"

    def on_run_finished(self, success, message):
        self._set_running(False)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1 if success else 0)
        self._stage_base = message
        self._rate_state = None
        self._rate_text = ""
        self.stage_label.setText(message)
        if success:
            print("流程执行完成")
        else:
            print(f"流程未完成: {message}", file=sys.stderr)

    def open_output_dir(self):
        path = os.path.abspath("data")
        os.makedirs(path, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    # ------------------------------------------------------------ 输出重定向

    def _install_stream_redirect(self):
        out_emitter = StreamEmitter(self._stdout)
        err_emitter = StreamEmitter(self._stderr)
        out_emitter.line.connect(self.log.append_line)
        out_emitter.partial.connect(self.log.append_partial)
        err_emitter.line.connect(self.log.append_line)
        err_emitter.partial.connect(self.log.append_partial)
        self._out_emitter = out_emitter
        self._err_emitter = err_emitter
        sys.stdout = out_emitter
        sys.stderr = err_emitter

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            if not self.worker.wait(5000):
                # 渲染等外部子进程可能较慢，请求取消后仍请用户稍后重试
                if self.ctx:
                    self.ctx.cancelled = True
                self.stage_label.setText("任务停止中，请稍后关闭窗口")
                event.ignore()
                return
        sys.stdout = self._stdout
        sys.stderr = self._stderr
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont(app.font().family(), 10))
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
