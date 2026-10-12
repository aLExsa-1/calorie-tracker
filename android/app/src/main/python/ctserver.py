"""Android 端引导模块：在手机本地启动 calorie-tracker 的 Python 后端。

由 MainActivity 通过 Chaquopy 调用：
    Python.getModule("ctserver").callAttr("start", filesDir, 8787, extraDirs)

设计要点：
  - 数据目录固定为应用私有目录（files/data），随应用卸载一起删除；
  - 服务的监听地址强制为 127.0.0.1，只在设备本机可达，不对外暴露；
  - 前端静态文件位置在打包后可能有多种布局，这里按候选路径逐个探测；
  - 后端代码保持原样不动，只覆盖 server.WEB_DIR，避免改写被测过的逻辑。
"""
from __future__ import annotations

import os
import sys
import threading
import traceback
from pathlib import Path
from typing import Any

STATE: dict[str, Any] = {
    "httpd": None,
    "thread": None,
    "url": None,
    "data_dir": None,
    "web_dir": None,
    "error": None,
}

_BACKEND_DIR = Path(__file__).resolve().parent
_ROOT = _BACKEND_DIR.parent

# Chaquopy 传进来的 Java 对象（如 java.util.ArrayList）只是代理，
# 在 Python 侧不可迭代，必须显式转换。
_UNAVAILABLE = ("The Android runtime does not support this method.",)


def _as_dirs(value: Any) -> list[str]:
    """把 Java 集合 / 字符串 / 可迭代对象统一转换成 Python 的字符串列表。

    真机上 Chaquopy 把 java.util.ArrayList 作为代理对象传入，Python 侧直接
    for 迭代会抛 "TypeError: 'ArrayList' object is not iterable"，因此这里
    对标准容器逐个取元素，取不到再尝试 Java 集合的 toArray()。
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, (list, tuple, set, frozenset)):
        return [str(x) for x in value]

    # Java 集合代理：优先 toArray()，其次 iterator() 逐个取
    to_array = getattr(value, "toArray", None) or getattr(value, "to_array", None)
    if to_array is not None:
        try:
            array = to_array()
        except Exception:  # noqa: BLE001
            array = None
        if array is not None and array is not _UNAVAILABLE:
            if isinstance(array, str):
                return [array] if array else []
            try:
                return [str(x) for x in array]
            except TypeError:
                pass

    iterator = getattr(value, "iterator", None)
    if iterator is not None:
        try:
            it = iterator()
            out: list[str] = []
            while True:
                try:
                    has_next = it.hasNext()
                except Exception:  # noqa: BLE001
                    break
                if not has_next:
                    break
                out.append(str(it.next()))
            return out
        except Exception:  # noqa: BLE001
            pass

    # 最后再试普通迭代（原生 Python 序列会走到这里）
    try:
        return [str(x) for x in value]
    except TypeError:
        return []


def _candidates(extra_dirs: list[str]) -> list[Path]:
    """按可能性从高到低列出前端目录的候选位置。"""
    out: list[Path] = []
    # 1) Chaquopy 解压出来的资源目录（前端随 app.imy 打包，通常在这里）。
    for item in extra_dirs:
        base = Path(item)
        out += [base / "frontend", base]
    # 2) 与 ctserver.py 同级的 frontend/（源码布局下的常规位置）。
    out += [
        _ROOT / "frontend",
        _BACKEND_DIR / "frontend",
    ]
    return out


def find_web_dir(extra_dirs: list[str] | None = None) -> Path:
    """定位包含 index.html 的前端目录。

    查找顺序：候选路径 → 从各候选根做有限深度的搜索。打包布局随 Chaquopy
    版本可能不同，因此不依赖单一固定路径。
    """
    extra_dirs = _as_dirs(extra_dirs)
    tried: list[str] = []

    # 1) 直接命中候选路径
    for cand in _candidates(extra_dirs):
        tried.append(str(cand))
        try:
            if (cand / "index.html").is_file() and (cand / "app.js").is_file():
                return cand
        except OSError:
            continue

    # 2) 在各候选根下有限深度搜索 frontend 目录
    #    除了 Java 传入的解压路径，也把 sys.path 里的目录纳入搜索范围：
    #    Chaquopy 会把 app 内容的解压目录加进 sys.path，这样即使 Java 侧
    #    什么都没传（或传的对象无法解析），Python 侧依然能自己找到前端。
    roots: list[Path] = [Path(p) for p in extra_dirs] + [_ROOT, _BACKEND_DIR]
    for entry in list(getattr(sys, "path", [])):
        try:
            cand = Path(entry)
        except (TypeError, ValueError):
            continue
        if cand.is_dir() and cand not in roots:
            roots.append(cand)

    for root in roots:
        try:
            if not root.is_dir():
                continue
        except OSError:
            continue
        for depth in range(1, 4):
            pattern = "/".join(["*"] * depth) + "/frontend/index.html"
            try:
                for hit in root.glob(pattern):
                    cand = hit.parent
                    tried.append(f"{cand}（搜索 depth={depth}）")
                    if (cand / "app.js").is_file():
                        return cand
            except OSError:
                continue

    # 3) 兜底：列出目录内容，便于从日志判断实际布局
    listing: list[str] = []
    for item in extra_dirs + [str(_ROOT)]:
        base = Path(item)
        listing.append(f"{base}:")
        try:
            for child in sorted(base.iterdir())[:30]:
                listing.append(f"    {'[D]' if child.is_dir() else '   '} {child.name}")
        except OSError as exc:
            listing.append(f"    <无法读取：{exc}>")
    raise RuntimeError(
        "找不到前端静态文件（需要 index.html 与 app.js）。\n已尝试：\n  "
        + "\n  ".join(tried) + "\n目录内容：\n" + "\n".join(listing))


def start(data_dir: str, port: int = 8787, extra_dirs: list[str] | None = None) -> str:
    """启动本地后端（幂等）。返回一行状态文本。"""
    if STATE["httpd"] is not None:
        return f"已在运行：{STATE['url']}"

    # 真机上传入的是 Java 集合代理，先归一化成 Python 列表。
    extra_dirs = _as_dirs(extra_dirs)

    data = Path(data_dir)
    data.mkdir(parents=True, exist_ok=True)

    # 只允许本机回环地址，避免局域网内其他设备访问到含明文 API Key 的接口。
    os.environ.setdefault("PYTHONUNBUFFERED", "1")

    from backend import server as srv
    from backend.config import Config
    from backend.engine import Engine
    from backend.store import Store

    web_dir = find_web_dir(extra_dirs)
    srv.WEB_DIR = web_dir  # 覆盖静态文件目录（原值为项目根下的 frontend/）

    engine = Engine(Store(data / "ct.db"), Config(data / "config.json"))
    httpd = srv.make_server(engine, "127.0.0.1", int(port))

    thread = threading.Thread(target=httpd.serve_forever, name="ct-http", daemon=True)
    thread.start()

    STATE.update({
        "httpd": httpd, "thread": thread, "data_dir": str(data), "web_dir": str(web_dir),
        "url": f"http://127.0.0.1:{port}", "error": None,
    })
    print(f"[ctserver] 后端已启动 {STATE['url']}  数据目录={data}  前端目录={web_dir}", flush=True)
    return f"url={STATE['url']} data={data} web={web_dir} version={srv.VERSION}"


def url() -> str:
    """返回后端地址；未启动时为空字符串。"""
    return STATE["url"] or ""


def status() -> str:
    """返回当前状态，便于在界面上展示或排查问题。"""
    if STATE["httpd"] is None:
        return "未启动"
    return f"运行中 {STATE['url']}（数据目录 {STATE['data_dir']}）"


def stop() -> None:
    """停止本地服务（应用退出时调用）。"""
    httpd = STATE.get("httpd")
    if httpd is None:
        return
    try:
        httpd.shutdown()
        httpd.server_close()
    finally:
        STATE.update({"httpd": None, "thread": None})
        print("[ctserver] 后端已停止", flush=True)


def diagnose(data_dir: str, extra_dirs: list[str] | None = None) -> str:
    """收集环境信息，供启动失败时显示。"""
    dirs = _as_dirs(extra_dirs)
    lines = [f"data_dir={data_dir}", f"backend_dir={_BACKEND_DIR}", f"root={_ROOT}"]
    try:
        lines.append(f"python={sys.version.split()[0]}")
        lines.append(f"sys.path={sys.path}")
    except Exception:  # noqa: BLE001
        lines.append(traceback.format_exc())
    lines.append(f"extra_dirs={dirs!r}")
    for cand in _candidates(dirs):
        try:
            exists = (cand / "index.html").is_file()
        except OSError:
            exists = False
        lines.append(f"  {'OK ' if exists else '   '} {cand}")
    return "\n".join(lines)
