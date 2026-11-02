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
        "icon": "Furnace",
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
