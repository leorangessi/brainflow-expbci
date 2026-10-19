"""
Expandable EEG 32 — 流测试软件（WiFi / 蓝牙串口）

显示：数据帧、名义/实际采样率、时间戳抖动、丢包率、重复包、通道范围。

Usage:
  python python_package/examples/tests/expandable_stream_monitor.py
  python python_package/examples/tests/expandable_stream_monitor.py --wifi --ip 192.168.4.1 --port 6677
  python python_package/examples/tests/expandable_stream_monitor.py --serial COM3
"""

from __future__ import annotations

import argparse
import collections
import csv
import logging
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Deque, List, Optional, Tuple

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PY_PKG = _REPO_ROOT / "python_package"
if str(_PY_PKG) not in sys.path:
    sys.path.insert(0, str(_PY_PKG))

from brainflow.board_shim import BoardIds, BoardShim, BrainFlowInputParams, IpProtocolTypes
from brainflow.exit_codes import BrainFlowError

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError as exc:
    raise SystemExit("Need tkinter (Windows Python 自带)") from exc

PKG_MOD = 256
UPDATE_MS = 200
FRAME_LOG_MAX = 250
RATE_HISTORY_SEC = 60.0
RAW_CACHE_MAX = 1000


def _ensure_dll() -> None:
    lib_dir = _PY_PKG / "brainflow" / "lib"
    dst = lib_dir / "BoardController.dll"
    if dst.is_file():
        return
    import shutil

    for src in (
        _REPO_ROOT / "compiled" / "Debug" / "BoardController.dll",
        _REPO_ROOT / "compiled" / "Release" / "BoardController.dll",
    ):
        if src.is_file():
            lib_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            logging.info("Copied %s -> %s", src, dst)
            return


def list_com_ports() -> List[str]:
    ports: List[str] = []
    try:
        from serial.tools import list_ports

        ports.extend(p.device for p in list_ports.comports())
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            import winreg

            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM")
            i = 0
            while True:
                ports.append(str(winreg.EnumValue(key, i)[1]))
                i += 1
        except OSError:
            pass
    uniq = sorted(set(ports), key=lambda s: (len(s), s.upper()))
    return uniq or ["COM3"]


# OpenBCI Cyton SDK / GUI BoardCytonWifiBase: ~0..~6 对应 ADS 采样率。
SR_CHOICES = (250, 500, 1000, 2000, 4000, 8000, 16000)
WIFI_SR_COMMANDS = {
    250: "~6",
    500: "~5",
    1000: "~4",
    2000: "~3",
    4000: "~2",
    8000: "~1",
    16000: "~0",
}


def wifi32_index_sequence() -> List[int]:
    """OpenBCI GUI BoardCytonWifiBase.setupPacketLossTracker: min=0 max=255."""
    return list(range(256))


def serial32_index_sequence() -> List[int]:
    """32ch serial merge: package_num 为 bank-0 的 sample_id（0,4,8,...,252）。"""
    return list(range(0, 256, 4))


class GuiPacketLossTracker:
    """Same algorithm as OpenBCI_GUI PacketLossTracker.pde.

    Walks an explicit expected sample-index list. On stream start, wait until
    the first index in that list (usually 0) so leftover buffer samples are ignored.
    """

    def __init__(self, index_sequence: List[int], wait_until_first: bool = True) -> None:
        self.seq = list(index_sequence)
        self.wait_until_first = wait_until_first
        self.reset_stream()

    def reset_stream(self) -> None:
        self.new_stream = True
        self.last_loc: Optional[int] = None
        self.n_wait = 0

    def add(self, current: int) -> Tuple[int, str]:
        if not self.seq:
            return 0, "ok"
        if self.new_stream and self.wait_until_first:
            if current == self.seq[0]:
                self.last_loc = 0
                self.new_stream = False
                return 0, "sync"
            self.n_wait += 1
            return 0, "wait"
        if self.last_loc is None:
            try:
                self.last_loc = self.seq.index(current)
            except ValueError:
                return 0, "desync"
            return 0, "first"
        loc = (self.last_loc + 1) % len(self.seq)
        lost = 0
        while self.seq[loc] != current:
            loc = (loc + 1) % len(self.seq)
            lost += 1
            if lost > len(self.seq):
                self.last_loc = None
                return 0, "desync"
        self.last_loc = loc
        if lost:
            return lost, "lost"
        return 0, "ok"


@dataclass
class StreamStats:
    nominal_hz: float
    index_sequence: List[int] = field(default_factory=wifi32_index_sequence)
    n_samples: int = 0
    n_lost: int = 0
    n_dup: int = 0
    n_desync: int = 0
    n_wait: int = 0
    max_gap: int = 0
    last_pkg: Optional[int] = None
    ts_first: Optional[float] = None
    ts_last: Optional[float] = None
    wall_t0: Optional[float] = None
    dts: Deque[float] = field(default_factory=lambda: collections.deque(maxlen=2000))
    eeg_min: Optional[float] = None
    eeg_max: Optional[float] = None
    eeg_finite: int = 0
    eeg_total: int = 0
    pattern: str = ""
    seq_locked: bool = False
    gui_tracker: GuiPacketLossTracker = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.gui_tracker = GuiPacketLossTracker(self.index_sequence, True)

    def reset(self) -> None:
        self.n_samples = 0
        self.n_lost = 0
        self.n_dup = 0
        self.n_desync = 0
        self.n_wait = 0
        self.max_gap = 0
        self.last_pkg = None
        self.ts_first = None
        self.ts_last = None
        self.wall_t0 = None
        self.dts.clear()
        self.eeg_min = None
        self.eeg_max = None
        self.eeg_finite = 0
        self.eeg_total = 0
        self.pattern = ""
        self.seq_locked = False
        self.gui_tracker = GuiPacketLossTracker(self.index_sequence, True)

    def lock_pattern_from_raw_ids(self, raw_ids: Tuple[int, int, int, int]) -> None:
        """Serial 32ch: 4 identical ids -> GUI 0-255; sequential ids -> 0,4,...,252."""
        if self.seq_locked or len(raw_ids) != 4:
            return
        if raw_ids[0] == raw_ids[1] == raw_ids[2] == raw_ids[3]:
            self.index_sequence = wifi32_index_sequence()
            self.pattern = "raw same-id x4 (GUI 0-255)"
        else:
            self.index_sequence = serial32_index_sequence()
            self.pattern = "raw seq +1 x4 (0,4,...,252)"
        self.gui_tracker = GuiPacketLossTracker(self.index_sequence, True)
        self.seq_locked = True

    def ingest_pkg(self, pkg: int) -> Tuple[int, str]:
        lost, event = self.gui_tracker.add(pkg)
        if event == "wait":
            self.n_wait += 1
        elif event == "desync":
            self.n_desync += 1
        elif event == "lost":
            self.n_lost += lost
            self.max_gap = max(self.max_gap, lost)
        elif event == "dup":
            self.n_dup += 1
        self.last_pkg = pkg
        return lost, event

    def ingest_ts(self, ts: float) -> Optional[float]:
        dt = None
        if self.ts_last is not None:
            dt = ts - self.ts_last
            if 0.0 < dt < 2.0:
                self.dts.append(dt)
        if self.ts_first is None:
            self.ts_first = ts
        self.ts_last = ts
        return dt

    def ingest_eeg(self, eeg: np.ndarray) -> None:
        finite = np.isfinite(eeg)
        self.eeg_finite += int(np.count_nonzero(finite))
        self.eeg_total += int(eeg.size)
        if np.any(finite):
            vals = eeg[finite]
            vmin = float(np.min(vals))
            vmax = float(np.max(vals))
            self.eeg_min = vmin if self.eeg_min is None else min(self.eeg_min, vmin)
            self.eeg_max = vmax if self.eeg_max is None else max(self.eeg_max, vmax)

    def actual_hz_from_ts(self) -> Optional[float]:
        if self.ts_first is None or self.ts_last is None:
            return None
        span = self.ts_last - self.ts_first
        if span <= 0 or self.n_samples < 2:
            return None
        return (self.n_samples - 1) / span

    def actual_hz_from_dt(self) -> Optional[float]:
        if len(self.dts) < 8:
            return None
        med = statistics.median(self.dts)
        if med <= 0:
            return None
        return 1.0 / med

    def wall_hz(self) -> Optional[float]:
        if self.wall_t0 is None or self.n_samples < 2:
            return None
        elapsed = time.time() - self.wall_t0
        if elapsed <= 0:
            return None
        return self.n_samples / elapsed

    def jitter_ms(self) -> Optional[float]:
        if len(self.dts) < 8:
            return None
        return statistics.pstdev(self.dts) * 1000.0

    def loss_pct(self) -> float:
        expected = self.n_samples + self.n_lost
        if expected <= 0:
            return 0.0
        return 100.0 * self.n_lost / expected


class ExpandableMonitorApp:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.board: Optional[BoardShim] = None
        self.board_id = int(BoardIds.EXPANDABLE_EEG_32_WIFI_BOARD)
        self.stats = StreamStats(nominal_hz=float(args.rate if args.rate in WIFI_SR_COMMANDS else 250))
        self.pause_display = False
        self.streaming = False
        self.pkg_ch = 0
        self.ts_ch = 0
        self.eeg_ch: List[int] = []
        self.other_ch: List[int] = []
        self.raw_cache: Deque[dict] = collections.deque(maxlen=RAW_CACHE_MAX)
        self.rate_hist: Deque[Tuple[float, float]] = collections.deque()
        self._n_hist: Deque[Tuple[float, int]] = collections.deque()
        self._tick_n_prev = 0
        self._tick_t_prev = time.time()

        self.root = tk.Tk()
        self.root.title("Expandable EEG 32 流测试 — WiFi / 蓝牙")
        self.root.geometry("1180x860")
        self.root.minsize(960, 700)
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(UPDATE_MS, self._on_timer)

    def _build_ui(self) -> None:
        pad = {"padx": 6, "pady": 4}
        conn = ttk.LabelFrame(self.root, text="连接")
        conn.pack(fill=tk.X, padx=8, pady=6)

        self.transport = tk.StringVar(value="wifi" if not self.args.serial else "serial")
        ttk.Radiobutton(
            conn, text="WiFi  (board 56)", variable=self.transport, value="wifi", command=self._sync_transport
        ).grid(row=0, column=0, sticky="w", **pad)
        ttk.Radiobutton(
            conn,
            text="蓝牙 / 串口 COM  (board 57)",
            variable=self.transport,
            value="serial",
            command=self._sync_transport,
        ).grid(row=0, column=1, sticky="w", **pad)

        ttk.Label(conn, text="IP").grid(row=1, column=0, sticky="e")
        self.ip_var = tk.StringVar(value=self.args.ip)
        ttk.Entry(conn, textvariable=self.ip_var, width=16).grid(row=1, column=1, sticky="w", **pad)
        ttk.Label(conn, text="Port").grid(row=1, column=2, sticky="e")
        self.port_var = tk.StringVar(value=str(self.args.port))
        ttk.Entry(conn, textvariable=self.port_var, width=8).grid(row=1, column=3, sticky="w", **pad)
        ttk.Label(conn, text="协议").grid(row=1, column=4, sticky="e")
        self.proto_var = tk.StringVar(value="TCP")
        ttk.Combobox(conn, textvariable=self.proto_var, values=("TCP", "UDP"), width=8, state="readonly").grid(
            row=1, column=5, sticky="w", **pad
        )

        ttk.Label(conn, text="COM").grid(row=2, column=0, sticky="e")
        self.com_var = tk.StringVar(value=self.args.serial or "COM3")
        self.com_box = ttk.Combobox(conn, textvariable=self.com_var, values=list_com_ports(), width=14)
        self.com_box.grid(row=2, column=1, sticky="w", **pad)
        ttk.Button(conn, text="刷新端口", command=self._refresh_com).grid(row=2, column=2, sticky="w", **pad)
        ttk.Label(conn, text="采样率 Hz").grid(row=2, column=4, sticky="e")
        sr_labels = tuple(str(hz) for hz in SR_CHOICES)
        default_sr = str(self.args.rate) if str(self.args.rate) in sr_labels else "250"
        self.sr_var = tk.StringVar(value=default_sr)
        self.sr_box = ttk.Combobox(
            conn,
            textvariable=self.sr_var,
            values=sr_labels,
            width=8,
            state="readonly",
        )
        self.sr_box.grid(row=2, column=5, sticky="w", **pad)

        btns = ttk.Frame(conn)
        btns.grid(row=3, column=0, columnspan=6, sticky="w", **pad)
        self.btn_connect = ttk.Button(btns, text="连接", command=self.connect)
        self.btn_connect.pack(side=tk.LEFT, padx=4)
        self.btn_start = ttk.Button(btns, text="开始采集", command=self.start_stream, state=tk.DISABLED)
        self.btn_start.pack(side=tk.LEFT, padx=4)
        self.btn_stop = ttk.Button(btns, text="停止采集", command=self.stop_stream, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=4)
        self.btn_disc = ttk.Button(btns, text="断开", command=self.disconnect, state=tk.DISABLED)
        self.btn_disc.pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="清零统计", command=self.clear_stats).pack(side=tk.LEFT, padx=4)
        self.pause_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(btns, text="暂停画面（统计继续）", variable=self.pause_var).pack(side=tk.LEFT, padx=8)
        ttk.Button(btns, text="导出原始包缓存", command=self.export_raw_cache).pack(side=tk.LEFT, padx=4)

        self.status_var = tk.StringVar(value="未连接")
        ttk.Label(conn, textvariable=self.status_var, foreground="#333").grid(
            row=4, column=0, columnspan=6, sticky="w", **pad
        )

        live = ttk.LabelFrame(self.root, text="实时采样率（对照名义 Hz 与已运行时间）")
        live.pack(fill=tk.X, padx=8, pady=4)
        self.live_hz_var = tk.StringVar(value="实时  — Hz")
        self.live_hz_label = ttk.Label(live, textvariable=self.live_hz_var, font=("Consolas", 18, "bold"))
        self.live_hz_label.pack(anchor="w", padx=8, pady=(4, 0))
        self.live_detail_var = tk.StringVar(value="开始采集后显示：已运行时间、应到样本、实收样本、1s/5s/全程 Hz")
        ttk.Label(live, textvariable=self.live_detail_var, font=("Consolas", 10)).pack(anchor="w", padx=8, pady=(0, 2))
        self.live_expect_var = tk.StringVar(value="")
        ttk.Label(live, textvariable=self.live_expect_var, font=("Consolas", 10)).pack(anchor="w", padx=8, pady=(0, 6))

        stats = ttk.LabelFrame(self.root, text="测试指标")
        stats.pack(fill=tk.X, padx=8, pady=4)
        self.metric_labels = {}
        rows = [
            ("board", "板卡"),
            ("fs", "采样率 名义 / 时间戳 / dt中位 / 墙钟"),
            ("live", "实时 / 近1秒 / 近5秒 / 全程"),
            ("time", "已运行 / 应到样本 / 实收 / 缺口"),
            ("count", "样本 / 丢失 / 重复 / 失步 / 等到index0"),
            ("loss", "丢包率 / 最大连续缺口"),
            ("jitter", "时间戳抖动 / 缓冲"),
            ("eeg", "EEG 有限值 / 范围 μV"),
        ]
        for i, (key, title) in enumerate(rows):
            ttk.Label(stats, text=title + ":", width=36, anchor="e").grid(row=i, column=0, sticky="e", padx=4, pady=1)
            lab = ttk.Label(stats, text="—", anchor="w", font=("Consolas", 10))
            lab.grid(row=i, column=1, sticky="w")
            self.metric_labels[key] = lab

        self.loss_style = ttk.Style()
        self.loss_style.configure("Loss.TLabel", foreground="#1a7f37")

        rate_fr = ttk.LabelFrame(self.root, text="近 60 秒接收速率 (Hz)")
        rate_fr.pack(fill=tk.X, padx=8, pady=4)
        self.rate_canvas = tk.Canvas(rate_fr, height=72, bg="#1e1e1e", highlightthickness=0)
        self.rate_canvas.pack(fill=tk.X, padx=4, pady=4)

        dump_fr = ttk.LabelFrame(self.root, text="最新合并帧 + 原始 4 子包 sample_id（other 37-40）")
        dump_fr.pack(fill=tk.X, padx=8, pady=4)
        self.dump_text = tk.Text(dump_fr, height=6, font=("Consolas", 9), wrap=tk.NONE)
        dump_scroll_x = ttk.Scrollbar(dump_fr, orient=tk.HORIZONTAL, command=self.dump_text.xview)
        self.dump_text.configure(xscrollcommand=dump_scroll_x.set, state=tk.DISABLED)
        self.dump_text.pack(fill=tk.X, padx=4, pady=(4, 0))
        dump_scroll_x.pack(fill=tk.X, padx=4, pady=(0, 4))

        raw_fr = ttk.LabelFrame(self.root, text="原始数据包缓存（最近 1000 条合并帧，含 4 个子包 id）")
        raw_fr.pack(fill=tk.BOTH, expand=False, padx=8, pady=4)
        raw_top = ttk.Frame(raw_fr)
        raw_top.pack(fill=tk.X, padx=4, pady=2)
        self.raw_count_var = tk.StringVar(value="缓存 0/1000")
        ttk.Label(raw_top, textvariable=self.raw_count_var).pack(side=tk.LEFT)
        self.raw_text = tk.Text(raw_fr, height=8, font=("Consolas", 9), wrap=tk.NONE)
        raw_y = ttk.Scrollbar(raw_fr, orient=tk.VERTICAL, command=self.raw_text.yview)
        raw_x = ttk.Scrollbar(raw_fr, orient=tk.HORIZONTAL, command=self.raw_text.xview)
        self.raw_text.configure(yscrollcommand=raw_y.set, xscrollcommand=raw_x.set, state=tk.DISABLED)
        self.raw_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 0), pady=(0, 4))
        raw_y.pack(side=tk.RIGHT, fill=tk.Y, pady=(0, 4))
        raw_x.pack(side=tk.BOTTOM, fill=tk.X, padx=4)

        log_fr = ttk.LabelFrame(self.root, text="接收数据帧日志")
        log_fr.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        cols = ("n", "pkg", "event", "lost", "ts", "dt_ms", "ch1", "ch8", "ch16", "ch32")
        self.tree = ttk.Treeview(log_fr, columns=cols, show="headings", height=14)
        headings = {
            "n": "N",
            "pkg": "Pkg#",
            "event": "事件",
            "lost": "本帧丢失",
            "ts": "时间戳",
            "dt_ms": "dt(ms)",
            "ch1": "Ch1",
            "ch8": "Ch8",
            "ch16": "Ch16",
            "ch32": "Ch32",
        }
        widths = {"n": 70, "pkg": 60, "event": 70, "lost": 80, "ts": 120, "dt_ms": 80}
        for c in cols:
            self.tree.heading(c, text=headings[c])
            self.tree.column(c, width=widths.get(c, 90), anchor="e")
        yscroll = ttk.Scrollbar(log_fr, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.tag_configure("ok", foreground="#222")
        self.tree.tag_configure("lost", foreground="#b00020")
        self.tree.tag_configure("dup", foreground="#9a6b00")
        self.tree.tag_configure("desync", foreground="#6a1b9a")
        self.tree.tag_configure("first", foreground="#1565c0")
        self.tree.tag_configure("sync", foreground="#1565c0")
        self.tree.tag_configure("wait", foreground="#888")

        self._sync_transport()
        if self.args.serial:
            self.transport.set("serial")
            self._sync_transport()

    def _selected_hz(self) -> int:
        try:
            return int(self.sr_var.get())
        except ValueError:
            return 250

    def _index_sequence(self) -> List[int]:
        if self.transport.get() == "wifi":
            return wifi32_index_sequence()
        return serial32_index_sequence()

    def _apply_sampling_rate(self) -> bool:
        if self.board is None:
            return False
        hz = self._selected_hz()
        cmd = WIFI_SR_COMMANDS.get(hz)
        if cmd is None:
            messagebox.showerror("采样率", f"不支持的采样率 {hz}")
            return False
        try:
            self.board.config_board(cmd)
            logging.info("config_board %s (%s Hz), same as OpenBCI GUI", cmd, hz)
            return True
        except BrainFlowError as e:
            messagebox.showerror("采样率", f"发送 {cmd} ({hz} Hz) 失败: {e}")
            return False

    def _sync_transport(self) -> None:
        if self.board is None:
            self.status_var.set("未连接 · 采集前选择采样率，丢包按 OpenBCI GUI PacketLossTracker 计算")

    def _refresh_com(self) -> None:
        ports = list_com_ports()
        self.com_box["values"] = ports
        if ports and self.com_var.get() not in ports:
            self.com_var.set(ports[0])

    def _set_btns(self, connected: bool, streaming: bool) -> None:
        self.btn_connect.configure(state=tk.DISABLED if connected else tk.NORMAL)
        self.btn_start.configure(state=tk.NORMAL if connected and not streaming else tk.DISABLED)
        self.btn_stop.configure(state=tk.NORMAL if streaming else tk.DISABLED)
        self.btn_disc.configure(state=tk.NORMAL if connected else tk.DISABLED)
        self.sr_box.configure(state=tk.DISABLED if streaming else "readonly")

    def connect(self) -> None:
        if self.board is not None:
            return
        _ensure_dll()
        params = BrainFlowInputParams()
        if self.transport.get() == "wifi":
            self.board_id = int(BoardIds.EXPANDABLE_EEG_32_WIFI_BOARD)
            params.ip_address = self.ip_var.get().strip()
            try:
                params.ip_port = int(self.port_var.get().strip())
            except ValueError:
                messagebox.showerror("参数", "Port 必须是整数")
                return
            params.ip_protocol = int(
                IpProtocolTypes.TCP if self.proto_var.get() == "TCP" else IpProtocolTypes.UDP
            )
            desc = f"WiFi {params.ip_address}:{params.ip_port}"
        else:
            self.board_id = int(BoardIds.EXPANDABLE_EEG_32_BOARD)
            params.serial_port = self.com_var.get().strip()
            if not params.serial_port:
                messagebox.showerror("参数", "请填写 COM 口")
                return
            desc = f"Serial {params.serial_port}"

        try:
            BoardShim.enable_board_logger()
            self.board = BoardShim(self.board_id, params)
            self.status_var.set(f"正在连接 {desc} ...")
            self.root.update_idletasks()
            self.board.prepare_session()
            if not self._apply_sampling_rate():
                self.board.release_session()
                self.board = None
                return
        except BrainFlowError as e:
            self.board = None
            self.status_var.set(f"连接失败: {e}")
            messagebox.showerror("连接失败", str(e))
            return
        except Exception as e:
            self.board = None
            self.status_var.set(f"连接失败: {e}")
            messagebox.showerror("连接失败", str(e))
            return

        self.pkg_ch = BoardShim.get_package_num_channel(self.board_id)
        self.ts_ch = BoardShim.get_timestamp_channel(self.board_id)
        self.eeg_ch = list(BoardShim.get_eeg_channels(self.board_id))
        try:
            self.other_ch = list(BoardShim.get_other_channels(self.board_id))
        except Exception:
            self.other_ch = []
        hz = self._selected_hz()
        try:
            name = BoardShim.get_device_name(self.board_id)
        except Exception:
            name = str(self.board_id)
        self.stats = StreamStats(nominal_hz=float(hz), index_sequence=self._index_sequence())
        self._set_btns(True, False)
        self.status_var.set(f"已连接 {name} (id={self.board_id})  {desc}  采样率 {hz} Hz")

    def start_stream(self) -> None:
        if self.board is None:
            return
        hz = self._selected_hz()
        if self.transport.get() == "serial" and hz > 125:
            if not messagebox.askokcancel(
                "串口带宽",
                f"32 通道串口/蓝牙默认 115200 波特，4 个 33 字节子包合成一帧。\n"
                f"{hz} Hz 需要约 {hz * 4 * 33} 字节/秒，超过串口上限（约 11.5 KB/s），"
                f"硬件上就会丢包。\nWiFi 不受 115200 波特限制，但仍受 WiFi Shield 吞吐限制。\n\n仍要继续？",
            ):
                return
        if not self._apply_sampling_rate():
            return
        try:
            # Keep ~60 s of ring buffer at the selected rate (16 kHz → 960k samples).
            self.board.start_stream(max(450000, hz * 60))
        except BrainFlowError as e:
            messagebox.showerror("start_stream", str(e))
            return
        hz = self._selected_hz()
        self.streaming = True
        self.stats = StreamStats(nominal_hz=float(hz), index_sequence=self._index_sequence())
        self.stats.wall_t0 = time.time()
        self.raw_cache.clear()
        self.rate_hist.clear()
        self._n_hist.clear()
        self._refresh_raw_text()
        self._tick_n_prev = 0
        self._tick_t_prev = time.time()
        self._set_btns(True, True)
        self.status_var.set(self.status_var.get().split("  ·")[0] + f"  · 采集中 {hz} Hz")

    def stop_stream(self) -> None:
        if self.board is None:
            return
        try:
            if self.streaming:
                self.board.stop_stream()
        except BrainFlowError as e:
            logging.warning("stop_stream: %s", e)
        self.streaming = False
        self._set_btns(True, False)
        self.status_var.set("已停止采集（会话仍保持）")

    def disconnect(self) -> None:
        self.stop_stream()
        if self.board is not None:
            try:
                if self.board.is_prepared():
                    self.board.release_session()
            except BrainFlowError:
                pass
            self.board = None
        self._set_btns(False, False)
        self.status_var.set("已断开")

    def clear_stats(self) -> None:
        self.stats = StreamStats(
            nominal_hz=float(self._selected_hz()), index_sequence=self._index_sequence()
        )
        if self.streaming:
            self.stats.wall_t0 = time.time()
        self.rate_hist.clear()
        self._n_hist.clear()
        self.raw_cache.clear()
        self._refresh_raw_text()
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._set_dump("")
        self._refresh_metrics(buffer_n=0)
        self._draw_rate()

    def _set_dump(self, text: str) -> None:
        self.dump_text.configure(state=tk.NORMAL)
        self.dump_text.delete("1.0", tk.END)
        self.dump_text.insert("1.0", text)
        self.dump_text.configure(state=tk.DISABLED)

    def _elapsed_sec(self) -> Optional[float]:
        if self.stats.wall_t0 is None:
            return None
        return max(0.0, time.time() - self.stats.wall_t0)

    def _hz_over_window(self, seconds: float) -> Optional[float]:
        """Samples received in the last `seconds` of wall time, from poll snapshots."""
        hist = self._n_hist
        if len(hist) < 2:
            return None
        now = time.time()
        cutoff = now - seconds
        n_now = self.stats.n_samples
        n_then = None
        t_then = None
        for t, n in hist:
            if t >= cutoff:
                if t_then is None:
                    t_then, n_then = t, n
                break
            t_then, n_then = t, n
        if n_then is None or t_then is None:
            return None
        dt = now - t_then
        if dt <= 0:
            return None
        return max(0.0, (n_now - n_then) / dt)

    def _instant_hz(self) -> Optional[float]:
        if not self.rate_hist:
            return None
        return self.rate_hist[-1][1]

    def _refresh_metrics(self, buffer_n: int) -> None:
        s = self.stats
        name = "—"
        if self.board is not None:
            try:
                name = BoardShim.get_device_name(self.board_id)
            except Exception:
                name = str(self.board_id)
        self.metric_labels["board"].configure(
            text=f"{name}  id={self.board_id}  目标 {s.nominal_hz:.0f} Hz  {s.pattern or ''}"
        )

        def fmt_hz(v: Optional[float]) -> str:
            return "—" if v is None else f"{v:.2f}"

        instant = self._instant_hz()
        hz_1s = self._hz_over_window(1.0)
        hz_5s = self._hz_over_window(5.0)
        hz_all = s.wall_hz()
        elapsed = self._elapsed_sec()
        expected = None if elapsed is None else s.nominal_hz * elapsed
        missing = None if expected is None else expected - s.n_samples
        fill_pct = None if not expected else 100.0 * s.n_samples / expected

        self.metric_labels["fs"].configure(
            text=(
                f"{s.nominal_hz:.1f}  /  {fmt_hz(s.actual_hz_from_ts())}  /  "
                f"{fmt_hz(s.actual_hz_from_dt())}  /  {fmt_hz(hz_all)} Hz"
            )
        )
        self.metric_labels["live"].configure(
            text=f"{fmt_hz(instant)}  /  {fmt_hz(hz_1s)}  /  {fmt_hz(hz_5s)}  /  {fmt_hz(hz_all)} Hz"
        )
        if elapsed is None:
            time_txt = "—"
        else:
            time_txt = (
                f"{elapsed:.1f} s    应到 {expected:,.0f}    实收 {s.n_samples:,}    "
                f"缺口 {missing:,.0f} ({0.0 if fill_pct is None else fill_pct:.1f}%)"
            )
        self.metric_labels["time"].configure(text=time_txt)
        self.metric_labels["count"].configure(
            text=(
                f"{s.n_samples}  /  lost={s.n_lost}  /  dup={s.n_dup}  /  "
                f"desync={s.n_desync}  /  wait0={s.n_wait}"
            )
        )
        loss = s.loss_pct()
        loss_txt = f"{loss:.3f}%   最大连续缺口 {s.max_gap} 包"
        color = "#1a7f37" if loss < 0.1 else ("#9a6b00" if loss < 1.0 else "#b00020")
        self.metric_labels["loss"].configure(text=loss_txt, foreground=color)
        jit = s.jitter_ms()
        self.metric_labels["jitter"].configure(
            text=f"{'—' if jit is None else f'{jit:.2f} ms'}    板缓冲 {buffer_n}"
        )
        finite = "—" if s.eeg_total == 0 else f"{100.0 * s.eeg_finite / s.eeg_total:.2f}%"
        rng = "—"
        if s.eeg_min is not None and s.eeg_max is not None:
            rng = f"{s.eeg_min:.1f} .. {s.eeg_max:.1f}"
        self.metric_labels["eeg"].configure(text=f"{finite}    {rng}")

        show_hz = hz_1s if hz_1s is not None else instant
        if show_hz is None:
            self.live_hz_var.set(f"实时  — Hz    目标 {s.nominal_hz:.0f} Hz")
            self.live_hz_label.configure(foreground="#333")
            self.live_detail_var.set("开始采集后显示：已运行时间、应到样本、实收样本、1s/5s/全程 Hz")
            self.live_expect_var.set("")
        else:
            ratio = show_hz / s.nominal_hz if s.nominal_hz > 0 else 0.0
            ok = ratio >= 0.8
            warn = ratio < 0.5
            fg = "#1a7f37" if ok else ("#b00020" if warn else "#9a6b00")
            self.live_hz_var.set(
                f"实时  {show_hz:,.1f} Hz    目标 {s.nominal_hz:.0f} Hz    "
                f"({100.0 * ratio:.1f}%)"
            )
            self.live_hz_label.configure(foreground=fg)
            self.live_detail_var.set(
                f"本拍 {fmt_hz(instant)} Hz   近1秒 {fmt_hz(hz_1s)} Hz   "
                f"近5秒 {fmt_hz(hz_5s)} Hz   全程 {fmt_hz(hz_all)} Hz   "
                f"时间戳推算 {fmt_hz(s.actual_hz_from_ts())} Hz"
            )
            if elapsed is None:
                self.live_expect_var.set("")
            else:
                hint = ""
                if warn and s.nominal_hz >= 1000:
                    eq_250 = s.n_samples / 250.0 if s.n_samples else 0.0
                    hint = (
                        f"    ※ 按 {s.nominal_hz:.0f} Hz 应有约 {expected:,.0f} 点；"
                        f"当前更像 {show_hz:.0f} Hz（约 250Hz×{eq_250:.1f}s）"
                    )
                self.live_expect_var.set(
                    f"已运行 {elapsed:.1f}s    应到 {expected:,.0f}    实收 {s.n_samples:,}    "
                    f"缺口 {missing:,.0f} ({0.0 if fill_pct is None else fill_pct:.1f}%)"
                    + hint
                )

    def _draw_rate(self) -> None:
        cv = self.rate_canvas
        cv.delete("all")
        w = max(cv.winfo_width(), 100)
        h = max(cv.winfo_height(), 40)
        now = time.time()
        pts = [(t, hz) for t, hz in self.rate_hist if now - t <= RATE_HISTORY_SEC]
        if not pts:
            cv.create_text(8, h / 2, anchor="w", fill="#888", text="开始采集后绘制", font=("Consolas", 9))
            return
        hz_vals = [p[1] for p in pts]
        ymax = max(max(hz_vals), self.stats.nominal_hz * 1.2, 1.0)
        ymin = 0.0
        nom_y = h - 4 - (self.stats.nominal_hz - ymin) / (ymax - ymin) * (h - 8)
        cv.create_line(0, nom_y, w, nom_y, fill="#2e7d32", dash=(4, 3))
        coords = []
        t0 = now - RATE_HISTORY_SEC
        for t, hz in pts:
            x = (t - t0) / RATE_HISTORY_SEC * w
            y = h - 4 - (hz - ymin) / (ymax - ymin) * (h - 8)
            coords.extend((x, y))
        if len(coords) >= 4:
            cv.create_line(*coords, fill="#4fc3f7", width=2)
        last = hz_vals[-1]
        hz_1s = self._hz_over_window(1.0)
        extra = "" if hz_1s is None else f"   1s {hz_1s:.1f}"
        cv.create_text(
            w - 6,
            8,
            anchor="ne",
            fill="#eee",
            text=f"本拍 {last:.1f}{extra}   目标 {self.stats.nominal_hz:.0f} Hz",
            font=("Consolas", 10),
        )

    def _raw_ids_from_col(self, col: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
        if self.transport.get() != "serial" or len(self.other_ch) < 5:
            return None
        try:
            return tuple(int(round(float(col[self.other_ch[i]]))) % PKG_MOD for i in range(1, 5))
        except Exception:
            return None

    def _append_raw_cache(
        self,
        n: int,
        pkg: int,
        event: str,
        lost: int,
        ts: float,
        dt: Optional[float],
        col: np.ndarray,
        raw_ids: Optional[Tuple[int, int, int, int]],
    ) -> None:
        eeg = [float(col[i]) for i in self.eeg_ch]
        end_b = int(round(float(col[self.other_ch[0]]))) if self.other_ch else -1
        rec = {
            "n": n,
            "pkg": pkg,
            "event": event,
            "lost": lost,
            "ts": ts,
            "dt_ms": None if dt is None else dt * 1000.0,
            "end": end_b,
            "id0": None if raw_ids is None else raw_ids[0],
            "id1": None if raw_ids is None else raw_ids[1],
            "id2": None if raw_ids is None else raw_ids[2],
            "id3": None if raw_ids is None else raw_ids[3],
            "eeg": eeg,
        }
        self.raw_cache.append(rec)
        self.raw_count_var.set(f"缓存 {len(self.raw_cache)}/{RAW_CACHE_MAX}")

    def _refresh_raw_text(self) -> None:
        lines = []
        for rec in list(self.raw_cache)[-80:]:
            ids = f"{rec['id0']},{rec['id1']},{rec['id2']},{rec['id3']}"
            dt = "" if rec["dt_ms"] is None else f"{rec['dt_ms']:.2f}"
            ch1 = rec["eeg"][0] if rec["eeg"] else 0.0
            lines.append(
                f"n={rec['n']:6d} pkg={rec['pkg']:3d} {rec['event']:5s} lost={rec['lost']:3d} "
                f"ids={ids:15s} end=0x{rec['end'] & 0xFF:02X} dt={dt:>7}ms "
                f"ch1={ch1:8.2f} ts={rec['ts']:.6f}"
            )
        body = "\n".join(lines)
        self.raw_text.configure(state=tk.NORMAL)
        self.raw_text.delete("1.0", tk.END)
        self.raw_text.insert("1.0", body)
        if not self.pause_var.get():
            self.raw_text.see(tk.END)
        self.raw_text.configure(state=tk.DISABLED)

    def export_raw_cache(self) -> None:
        if not self.raw_cache:
            messagebox.showinfo("导出", "缓存为空")
            return
        path = filedialog.asksaveasfilename(
            title="导出最近 1000 条原始包",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("All", "*.*")],
        )
        if not path:
            return
        fieldnames = [
            "n", "pkg", "event", "lost", "ts", "dt_ms", "end", "id0", "id1", "id2", "id3",
        ] + [f"ch{i}" for i in range(1, 33)]
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader()
            for rec in self.raw_cache:
                row = {k: rec.get(k) for k in fieldnames}
                for i, v in enumerate(rec.get("eeg") or []):
                    row[f"ch{i + 1}"] = v
                w.writerow(row)
        messagebox.showinfo("导出", f"已写入 {len(self.raw_cache)} 条\n{path}")

    def _format_dump(self, col: np.ndarray) -> str:
        eeg = [float(col[i]) for i in self.eeg_ch]
        pkg = int(col[self.pkg_ch]) % PKG_MOD
        ts = float(col[self.ts_ch])
        end_b = ""
        ids_s = ""
        if self.other_ch:
            end_b = f"  end=0x{int(round(float(col[self.other_ch[0]]))) & 0xFF:02X}"
        raw_ids = self._raw_ids_from_col(col)
        if raw_ids:
            ids_s = f"  raw_ids={raw_ids[0]},{raw_ids[1]},{raw_ids[2]},{raw_ids[3]}"
        lines = [f"pkg={pkg:3d}  ts={ts:.6f}{end_b}{ids_s}  n_eeg={len(eeg)}"]
        for row in range(0, 32, 8):
            chunk = eeg[row : row + 8]
            body = " ".join(f"{v:9.2f}" for v in chunk)
            lines.append(f"  ch{row + 1:02d}-{row + len(chunk):02d}: {body}")
        return "\n".join(lines)

    def _append_frame_row(
        self,
        n: int,
        pkg: int,
        event: str,
        lost: int,
        ts: float,
        dt: Optional[float],
        col: np.ndarray,
    ) -> None:
        def ch(idx_in_eeg: int) -> str:
            if idx_in_eeg >= len(self.eeg_ch):
                return ""
            return f"{col[self.eeg_ch[idx_in_eeg]]:.2f}"

        values = (
            n,
            pkg,
            event,
            lost,
            f"{ts:.6f}",
            "" if dt is None else f"{dt * 1000:.2f}",
            ch(0),
            ch(7),
            ch(15),
            ch(31),
        )
        item = self.tree.insert("", tk.END, values=values, tags=(event,))
        kids = self.tree.get_children()
        if len(kids) > FRAME_LOG_MAX:
            self.tree.delete(kids[0])
        if not self.pause_var.get():
            self.tree.see(item)

    def _on_timer(self) -> None:
        try:
            self._poll()
        except Exception:
            logging.exception("poll")
        self.root.after(UPDATE_MS, self._on_timer)

    def _poll(self) -> None:
        if self.board is None or not self.streaming:
            self._draw_rate()
            return
        try:
            buf_n = self.board.get_board_data_count()
            if buf_n <= 0:
                self._refresh_metrics(buffer_n=0)
                self._draw_rate()
                return
            data = self.board.get_board_data()
        except BrainFlowError as e:
            self.status_var.set(f"读数错误: {e}")
            return
        if data.size == 0 or data.shape[1] == 0:
            self._refresh_metrics(buffer_n=0)
            return

        last_col = None
        n_cols = data.shape[1]
        display_from = 0 if self.pause_var.get() else max(0, n_cols - 80)
        for i in range(n_cols):
            col = data[:, i]
            pkg = int(round(float(col[self.pkg_ch]))) % PKG_MOD
            ts = float(col[self.ts_ch])
            eeg = col[self.eeg_ch]
            raw_ids = self._raw_ids_from_col(col)
            if raw_ids is not None:
                self.stats.lock_pattern_from_raw_ids(raw_ids)
            if self.stats.n_samples == 0 and self.stats.wall_t0 is None:
                self.stats.wall_t0 = time.time()
            lost, event = self.stats.ingest_pkg(pkg)
            dt = self.stats.ingest_ts(ts)
            self.stats.ingest_eeg(eeg)
            self.stats.n_samples += 1
            last_col = col
            self._append_raw_cache(self.stats.n_samples, pkg, event, lost, ts, dt, col, raw_ids)
            if i >= display_from:
                self._append_frame_row(self.stats.n_samples, pkg, event, lost, ts, dt, col)

        if not self.pause_var.get():
            self._refresh_raw_text()

        now = time.time()
        dn = self.stats.n_samples - self._tick_n_prev
        dt_wall = now - self._tick_t_prev
        if dt_wall > 0 and dn >= 0:
            self.rate_hist.append((now, dn / dt_wall))
        self._n_hist.append((now, self.stats.n_samples))
        self._tick_n_prev = self.stats.n_samples
        self._tick_t_prev = now
        while self.rate_hist and now - self.rate_hist[0][0] > RATE_HISTORY_SEC:
            self.rate_hist.popleft()
        while self._n_hist and now - self._n_hist[0][0] > RATE_HISTORY_SEC:
            self._n_hist.popleft()

        live = self._hz_over_window(1.0)
        if live is None:
            live = self._instant_hz()
        if live is not None:
            elapsed = self._elapsed_sec() or 0.0
            self.status_var.set(
                f"采集中  实时 {live:,.1f} Hz  /  目标 {self.stats.nominal_hz:.0f} Hz    "
                f"已运行 {elapsed:.1f}s    实收 {self.stats.n_samples:,}"
            )

        if last_col is not None and not self.pause_var.get():
            self._set_dump(self._format_dump(last_col))
        self._refresh_metrics(buffer_n=buf_n)
        self._draw_rate()

    def on_close(self) -> None:
        try:
            self.disconnect()
        except Exception:
            pass
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Expandable 32ch WiFi/Serial stream monitor")
    p.add_argument("--ip", default="192.168.4.1")
    p.add_argument("--port", type=int, default=6677)
    p.add_argument("--serial", default="", help="COM port; implies bluetooth/serial board 57")
    p.add_argument("--wifi", action="store_true", help="start UI on WiFi (default unless --serial)")
    p.add_argument(
        "--rate",
        type=int,
        default=250,
        choices=SR_CHOICES,
        help="ADS sampling rate before stream (250..16000, Cyton ~6..~0)",
    )
    return p.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    _ensure_dll()
    app = ExpandableMonitorApp(args)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
