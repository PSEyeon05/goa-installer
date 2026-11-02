"""manifest.json 생성기 (서버 관리자용)

사용법:
    python make_manifest.py <배포폴더> <기본URL> <neoforge_version>

예:
    python make_manifest.py ./pack https://example.com/goa/files 21.11.0

<배포폴더> 안의 구조가 그대로 친구들의 전용 게임 폴더에 복사돼요.
    pack/mods/voicechat.jar
    pack/mods/journeymap.jar
    pack/shaderpacks/MyShader.zip
    pack/config/...
이 폴더를 <기본URL> 아래에 그대로 올려두고, 생성된 manifest.json 도 올리면 됩니다.
config/ 아래 파일은 자동으로 "overwrite": false 가 붙어서,
친구들 PC 에 이미 있으면 덮어쓰지 않아요.
"""
import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import quote


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    root = Path(sys.argv[1])
    base = sys.argv[2].rstrip("/")
    nf = sys.argv[3]
    files = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.name.startswith("."):
            rel = p.relative_to(root).as_posix()
            entry = {"path": rel, "url": f"{base}/{quote(rel)}", "sha256": sha256_of(p)}
            if rel.startswith("config/"):  # 설정 파일은 처음 한 번만 넣고 덮어쓰지 않음
                entry["overwrite"] = False
            files.append(entry)
    manifest = {"neoforge_version": nf, "files": files}
    Path("manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"manifest.json 생성 완료 (파일 {len(files)}개)")


if __name__ == "__main__":
    main()
