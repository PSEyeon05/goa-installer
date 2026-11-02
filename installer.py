"""GOA 서버 설치기 (Windows / macOS 공용)

하는 일
1. 서버가 관리하는 manifest.json 을 받아온다.
2. NeoForge 가 없으면 설치한다 (공식 런처에 들어 있는 Java 를 사용).
3. 공식 런처에 'GOA 서버' 프로필을 추가/갱신한다.
4. 모드, 쉐이더팩, 설정 파일을 전용 폴더에 받는다 (바뀐 파일만).
5. 서버 목록에 서버 주소를 등록한다 (servers.dat 가 없을 때만).
"""
import hashlib
import json
import os
import platform
import queue
import re
import shutil
import ssl
import struct
import subprocess
import tempfile
import threading
import time
import tkinter as tk
import urllib.request
from pathlib import Path
from tkinter import ttk, messagebox

try:
    import certifi  # macOS 에서 SSL 인증서 문제를 피하기 위해 사용
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except Exception:
    SSL_CONTEXT = ssl.create_default_context()

# ===================== 여기만 고치면 됨 =====================
MANIFEST_URL = "https://raw.githubusercontent.com/PSEyeon05/goa-installer/main/manifest.json"
PROFILE_ID = "goa-server"
PROFILE_NAME = "GOA 서버"
SERVER_NAME = "GOA"
SERVER_ADDRESS = "25.8.255.178"
INSTANCE_DIRNAME = "goa-server"  # .minecraft 안에 만들어질 전용 게임 폴더 이름
ICON_DATA = "data:image/png;base64,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"  # 공식 런처 프로필 아이콘
# ===========================================================

IS_WINDOWS = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"


def minecraft_dir() -> Path:
    if IS_WINDOWS:
        return Path(os.environ["APPDATA"]) / ".minecraft"
    if IS_MAC:
        return Path.home() / "Library" / "Application Support" / "minecraft"
    return Path.home() / ".minecraft"


def http_get(url: str) -> urllib.request.addinfourl:
    req = urllib.request.Request(url, headers={"User-Agent": "GOA-Installer"})
    return urllib.request.urlopen(req, timeout=60, context=SSL_CONTEXT)


def fetch_json(url: str) -> dict:
    with http_get(url) as r:
        return json.loads(r.read().decode("utf-8"))


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    with http_get(url) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    tmp.replace(dest)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def java_major(java: str) -> int:
    try:
        out = subprocess.run([java, "-version"], capture_output=True, text=True,
                             timeout=20, **_no_window()).stderr
        m = re.search(r'version "(\d+)', out)
        return int(m.group(1)) if m else 0
    except Exception:
        return 0


def _no_window() -> dict:
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WINDOWS else {}


def find_java(mc: Path) -> str:
    """공식 런처가 내려받아 둔 Java 를 찾는다. 없으면 PATH 의 java 를 쓴다."""
    exe = "java.exe" if IS_WINDOWS else "java"
    roots = [mc / "runtime"]
    if IS_WINDOWS and os.environ.get("LOCALAPPDATA"):
        roots.append(Path(os.environ["LOCALAPPDATA"]) / "Packages" /
                     "Microsoft.4297127D64EC6_8wekyb3d8bbwe" / "LocalCache" / "Local" / "runtime")
    found = []
    for root in roots:
        if root.exists():
            found += [p for p in root.rglob(exe) if p.parent.name == "bin" and p.is_file()]
    found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for p in found:
        if java_major(str(p)) >= 21:
            return str(p)
    sys_java = shutil.which("java")
    if sys_java and java_major(sys_java) >= 21:
        return sys_java
    raise RuntimeError("Java 21 이상을 찾지 못했어요. 공식 마인크래프트 런처에서 1.21.11 을 한 번 실행한 뒤 다시 시도해주세요.")


def write_servers_dat(path: Path, name: str, ip: str) -> None:
    """압축 없는 NBT 로 servers.dat 를 새로 만든다."""
    def s(v: str) -> bytes:
        b = v.encode("utf-8")
        return struct.pack(">H", len(b)) + b

    def tag(t: int, n: str) -> bytes:
        return bytes([t]) + s(n)

    data = tag(10, "")                                   # 루트 compound
    data += tag(9, "servers") + bytes([10]) + struct.pack(">i", 1)  # compound 1개짜리 리스트
    data += tag(8, "ip") + s(ip) + tag(8, "name") + s(name) + b"\x00"
    data += b"\x00"
    path.write_bytes(data)


def update_profile(mc: Path, inst: Path, version_id: str, jvm_args: str | None) -> None:
    p = mc / "launcher_profiles.json"
    shutil.copy2(p, p.with_name("launcher_profiles.json.goa-backup"))
    data = json.loads(p.read_text(encoding="utf-8"))
    profiles = data.setdefault("profiles", {})
    prof = profiles.get(PROFILE_ID, {})
    now = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    prof.setdefault("created", now)
    prof.update({
        "name": PROFILE_NAME,
        "type": "custom",
        "icon": ICON_DATA,
        "lastVersionId": version_id,
        "gameDir": str(inst),
        "lastUsed": now,
    })
    if jvm_args:
        prof["javaArgs"] = jvm_args
    profiles[PROFILE_ID] = prof
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def safe_join(base: Path, rel: str) -> Path:
    dest = (base / rel).resolve()
    if base.resolve() not in dest.parents:
        raise RuntimeError(f"허용되지 않는 경로: {rel}")
    return dest


def run_install(log, progress) -> None:
    mc = minecraft_dir()
    if not (mc / "launcher_profiles.json").exists():
        raise RuntimeError("공식 마인크래프트 런처를 먼저 한 번 실행해서 로그인해주세요.")

    log("서버 정보를 확인하는 중...")
    manifest = fetch_json(MANIFEST_URL)
    nf = manifest["neoforge_version"]
    version_id = f"neoforge-{nf}"
    inst = mc / INSTANCE_DIRNAME
    inst.mkdir(parents=True, exist_ok=True)

    # 1) NeoForge 설치
    if (mc / "versions" / version_id).exists():
        log(f"NeoForge {nf} 는 이미 설치되어 있어요.")
    else:
        log(f"NeoForge {nf} 를 설치하는 중... (몇 분 걸릴 수 있어요)")
        url = (f"https://maven.neoforged.net/releases/net/neoforged/neoforge/"
               f"{nf}/neoforge-{nf}-installer.jar")
        jar = Path(tempfile.gettempdir()) / f"neoforge-{nf}-installer.jar"
        download(url, jar)
        java = find_java(mc)
        res = subprocess.run([java, "-jar", str(jar), "--install-client", str(mc)],
                             capture_output=True, text=True, **_no_window())
        if res.returncode != 0 or not (mc / "versions" / version_id).exists():
            raise RuntimeError("NeoForge 설치에 실패했어요.\n" + (res.stdout + res.stderr)[-800:])

    # 2) 프로필
    log("공식 런처에 프로필을 추가하는 중...")
    update_profile(mc, inst, version_id, manifest.get("jvm_args"))

    # 3) 파일 동기화
    state_path = inst / ".goa-state.json"
    old = set(json.loads(state_path.read_text(encoding="utf-8"))) if state_path.exists() else set()
    files = manifest.get("files", [])
    new_paths = set()
    for i, f in enumerate(files, 1):
        rel = f["path"]
        dest = safe_join(inst, rel)
        new_paths.add(rel)
        keep_if_exists = f.get("overwrite", True) is False
        if dest.exists() and (keep_if_exists or sha256_of(dest) == f["sha256"]):
            log(f"[{i}/{len(files)}] 최신: {rel}")
        else:
            log(f"[{i}/{len(files)}] 받는 중: {rel}")
            download(f["url"], dest)
            if sha256_of(dest) != f["sha256"]:
                dest.unlink(missing_ok=True)
                raise RuntimeError(f"파일이 손상됐어요 (해시 불일치): {rel}")
        progress(i / max(len(files), 1) * 100)

    for rel in old - new_paths:  # manifest 에서 빠진 파일(옛 모드 등) 정리
        try:
            safe_join(inst, rel).unlink(missing_ok=True)
            log(f"삭제: {rel}")
        except Exception:
            pass
    state_path.write_text(json.dumps(sorted(new_paths), ensure_ascii=False), encoding="utf-8")

    # 4) 서버 목록
    servers = inst / "servers.dat"
    if not servers.exists():
        write_servers_dat(servers, SERVER_NAME, SERVER_ADDRESS)
        log("서버 목록에 서버를 추가했어요.")

    progress(100)
    log("\n완료! 마인크래프트 런처를 열고 'GOA 서버' 프로필로 접속하세요.")


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title(f"{PROFILE_NAME} 설치기")
        root.geometry("520x380")
        self.q: "queue.Queue[tuple[str, object]]" = queue.Queue()

        ttk.Label(root, text=f"{PROFILE_NAME} 설치기", font=("", 16, "bold")).pack(pady=(14, 4))
        ttk.Label(root, text="모드와 설정을 설치하고 업데이트해요.").pack()
        self.btn = ttk.Button(root, text="설치 / 업데이트", command=self.start)
        self.btn.pack(pady=10)
        self.bar = ttk.Progressbar(root, length=460, maximum=100)
        self.bar.pack()
        self.text = tk.Text(root, height=12, width=62, state="disabled")
        self.text.pack(padx=10, pady=10, fill="both", expand=True)
        root.after(100, self.poll)

    def start(self):
        self.btn.state(["disabled"])
        self.bar["value"] = 0

        def work():
            try:
                run_install(lambda m: self.q.put(("log", m)),
                            lambda v: self.q.put(("bar", v)))
                self.q.put(("done", None))
            except Exception as e:
                self.q.put(("error", str(e)))

        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "log":
                    self.text.config(state="normal")
                    self.text.insert("end", str(val) + "\n")
                    self.text.see("end")
                    self.text.config(state="disabled")
                elif kind == "bar":
                    self.bar["value"] = val
                elif kind == "done":
                    self.btn.state(["!disabled"])
                    messagebox.showinfo("완료", "설치가 끝났어요!")
                elif kind == "error":
                    self.btn.state(["!disabled"])
                    messagebox.showerror("오류", str(val))
        except queue.Empty:
            pass
        self.root.after(100, self.poll)


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
