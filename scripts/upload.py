"""
game-ping.kr WebGL 게임 자동 업로드 스크립트

신규 게임: /game-registration 플로우 (Step1 → Step2 → ...)
기존 게임: /games/{slug}/edit 플로우 (편집 페이지에서 WebGL만 교체)

환경변수:
  GAME_PING_EMAIL    (필수) 로그인 이메일
  GAME_PING_PASSWORD (필수) 로그인 패스워드
  GAME_SLUG          (필수) 게임 slug (예: my-awesome-game)
  WEBGL_ZIP_PATH     (선택) 업로드 경로, 기본값 build.zip
  GAME_TITLE         (선택) 게임 제목, 없으면 slug → Title Case 변환
  GAME_VERSION       (선택) 버전, 없으면 신규=0.0.1 / 기존=현재버전 patch+1
  PUBLISHER          (선택) personal(기본) 또는 team
  TEAM_NAME          (선택) PUBLISHER=team일 때 팀 이름 (예: Team6515)
"""

import os
import sys
import zipfile
import re
import requests
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

BASE_URL = "https://www.game-ping.kr"
LOGIN_URL = f"{BASE_URL}/auth/login"
REGISTER_URL = f"{BASE_URL}/game-registration"
SCREENSHOT_DIR = Path("screenshots")


def take_screenshot(page, name: str):
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    path = SCREENSHOT_DIR / f"{name}.png"
    page.screenshot(path=str(path))
    print(f"[screenshot] {path}")


def slug_to_title(slug: str) -> str:
    """my-awesome-game → My Awesome Game"""
    return " ".join(word.capitalize() for word in re.split(r"[-_]+", slug))


def increment_patch(version: str) -> str:
    """0.1.3 → 0.1.4"""
    parts = version.strip().lstrip("v").split(".")
    if len(parts) == 3:
        try:
            parts[2] = str(int(parts[2]) + 1)
            return ".".join(parts)
        except ValueError:
            pass
    return version


def get_current_version(slug: str) -> str | None:
    """게임 페이지에서 현재 버전 읽기 (로그인 불필요)"""
    try:
        resp = requests.get(f"{BASE_URL}/games/{slug}", timeout=10)
        match = re.search(r"v(\d+\.\d+\.\d+)", resp.text)
        if match:
            return match.group(1)
    except Exception:
        pass
    return None


def game_exists(slug: str) -> bool:
    """게임이 이미 등록되어 있는지 확인"""
    try:
        resp = requests.get(f"{BASE_URL}/games/{slug}", timeout=10, allow_redirects=True)
        return resp.status_code == 200 and "/not-found" not in resp.url
    except Exception:
        return False


def resolve_zip(path_str: str) -> Path:
    """ZIP이 아니면 자동 압축"""
    src = Path(path_str).resolve()
    if not src.exists():
        raise FileNotFoundError(f"경로를 찾을 수 없습니다: {src}")

    if src.suffix.lower() == ".zip":
        print(f"[zip] ZIP 파일 확인: {src} ({src.stat().st_size // 1024} KB)")
        return src

    out_zip = src.parent / (src.stem + "_build.zip") if src.is_file() else src.parent / (src.name + ".zip")

    if src.is_dir():
        print(f"[zip] 디렉토리 압축 중: {src} → {out_zip}")
        with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in sorted(src.rglob("*")):
                if file.is_file():
                    zf.write(file, file.relative_to(src))
        print(f"[zip] 압축 완료: {out_zip.stat().st_size // 1024} KB ({sum(1 for _ in src.rglob('*') if _.is_file())} 파일)")
    else:
        print(f"[zip] 단일 파일 압축 중: {src} → {out_zip}")
        with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(src, src.name)
        print(f"[zip] 압축 완료: {out_zip.stat().st_size // 1024} KB")

    return out_zip


def login(page, email: str, password: str):
    print(f"[login] {LOGIN_URL} 접속 중...")
    page.goto(LOGIN_URL)
    page.wait_for_load_state("networkidle")
    take_screenshot(page, "01_login_page")

    page.get_by_placeholder("이메일을 입력하세요").fill(email)
    page.get_by_placeholder("패스워드를 입력하세요").fill(password)
    take_screenshot(page, "02_login_filled")

    page.get_by_role("button", name="로그인").click()

    try:
        page.wait_for_url(lambda url: "/auth/login" not in url, timeout=15000)
    except PlaywrightTimeoutError:
        take_screenshot(page, "02_login_error")
        raise RuntimeError("로그인 실패: 이메일/패스워드를 확인하세요.")

    print(f"[login] 성공! 현재 URL: {page.url}")
    take_screenshot(page, "03_after_login")


# ─────────────────────────────────────────────
# 신규 게임 플로우
# ─────────────────────────────────────────────

def new_game_step1(page, publisher: str, team_name: str):
    """Step 1: 웹 게임 빌드 선택 + 게시자(개인/팀) 선택"""
    print("[new/step1] 게임 파일 타입 및 게시자 선택...")
    page.goto(REGISTER_URL)
    page.wait_for_load_state("networkidle")
    take_screenshot(page, "04_step1")

    # 웹 게임 빌드 선택
    page.get_by_role("button", name="웹 게임 빌드").click()

    # 게시자 드롭다운 열기
    page.locator("button").filter(has_text="dev-yunseong").or_(
        page.locator("button").filter(has_text="Team")
    ).first.click()
    page.wait_for_timeout(500)

    popup = page.locator('[data-slot="popover-content"]')
    if publisher == "team":
        popup.get_by_role("button").filter(has_text=team_name).click()
        print(f"[new/step1] 게시자: {team_name} (팀) 선택")
    else:
        popup.get_by_role("button").filter(has_text="dev-yunseong").click()
        print("[new/step1] 게시자: dev-yunseong (개인) 선택")

    take_screenshot(page, "04_step1_done")
    page.get_by_role("button", name="다음").click()
    page.wait_for_load_state("networkidle")
    print("[new/step1] 완료 → Step 2")
    take_screenshot(page, "05_step2")


def new_game_step2(page, game_title: str, game_slug: str, version: str, zip_path: Path):
    """Step 2: 기본 정보 입력 + WebGL ZIP 업로드"""
    print("[new/step2] 기본 정보 입력 중...")

    page.locator("input#title").fill(game_title)
    page.locator("input#slug").fill(game_slug)

    parts = version.split(".")
    page.locator("input#version-major").fill(parts[0] if len(parts) > 0 else "0")
    page.locator("input#version-minor").fill(parts[1] if len(parts) > 1 else "0")
    page.locator("input#version-patch").fill(parts[2] if len(parts) > 2 else "1")

    print(f"[new/step2] 제목={game_title}, slug={game_slug}, 버전={version}")
    take_screenshot(page, "06_step2_filled")

    # WebGL ZIP — 마지막 file input (500MB)
    print(f"[new/step2] WebGL ZIP 업로드: {zip_path.name} ({zip_path.stat().st_size // 1024} KB)")
    file_inputs = page.locator("input[type='file']")
    file_inputs.nth(file_inputs.count() - 1).set_input_files(str(zip_path))

    try:
        page.wait_for_function(
            f"() => document.body.innerText.includes('{zip_path.name}')",
            timeout=300000
        )
        print("[new/step2] 업로드 완료!")
    except PlaywrightTimeoutError:
        print("[new/step2] 업로드 타임아웃 — 계속 진행합니다.")

    take_screenshot(page, "07_step2_uploaded")
    page.get_by_role("button", name="다음").click()
    page.wait_for_load_state("networkidle")
    print("[new/step2] 완료 → Step 3")


def new_game_finish(page):
    """Step 3+: 나머지 단계 완료"""
    print("[new/step3+] 나머지 단계 처리 중...")

    for i in range(10):
        take_screenshot(page, f"08_step{3+i}")

        for label in ["등록", "완료", "제출", "게시"]:
            btn = page.get_by_role("button", name=label)
            if btn.is_visible(timeout=1000):
                btn.click()
                page.wait_for_load_state("networkidle")
                print(f"[new/step3+] '{label}' 버튼 클릭 → 완료!")
                take_screenshot(page, "09_done")
                return

        next_btn = page.get_by_role("button", name="다음")
        if next_btn.is_visible(timeout=1000):
            next_btn.click()
            page.wait_for_load_state("networkidle")
        else:
            break

    take_screenshot(page, "09_final")
    print("[new/step3+] 완료")


# ─────────────────────────────────────────────
# 기존 게임 편집 플로우
# ─────────────────────────────────────────────

def edit_game(page, game_slug: str, version: str, zip_path: Path):
    """기존 게임 편집 페이지에서 WebGL 파일만 교체"""
    edit_url = f"{BASE_URL}/games/{game_slug}/edit"
    print(f"[edit] 편집 페이지 이동: {edit_url}")
    page.goto(edit_url)
    page.wait_for_load_state("networkidle")

    if "/not-authorized" in page.url or "/not-found" in page.url:
        take_screenshot(page, "error_edit_page")
        raise RuntimeError(
            f"편집 페이지 접근 불가: {page.url}\n"
            "게임 소유자인지 확인하거나, GAME_SLUG를 확인하세요."
        )

    print(f"[edit] 편집 페이지 접근 성공: {page.url}")
    take_screenshot(page, "04_edit_page")

    # 버전 업데이트
    major_input = page.locator("input#version-major")
    if major_input.is_visible(timeout=3000):
        parts = version.split(".")
        page.locator("input#version-major").fill(parts[0] if len(parts) > 0 else "0")
        page.locator("input#version-minor").fill(parts[1] if len(parts) > 1 else "0")
        page.locator("input#version-patch").fill(parts[2] if len(parts) > 2 else "1")
        print(f"[edit] 버전 업데이트: {version}")

    # WebGL ZIP 교체
    print(f"[edit] WebGL ZIP 업로드: {zip_path.name} ({zip_path.stat().st_size // 1024} KB)")
    file_inputs = page.locator("input[type='file']")
    count = file_inputs.count()
    if count == 0:
        take_screenshot(page, "error_no_file_input")
        raise RuntimeError("파일 업로드 input을 찾을 수 없습니다.")

    file_inputs.nth(count - 1).set_input_files(str(zip_path))

    try:
        page.wait_for_function(
            f"() => document.body.innerText.includes('{zip_path.name}')",
            timeout=300000
        )
        print("[edit] 업로드 완료!")
    except PlaywrightTimeoutError:
        print("[edit] 업로드 타임아웃 — 저장 진행합니다.")

    take_screenshot(page, "05_edit_uploaded")

    # 저장
    for label in ["저장", "업데이트", "수정 완료", "다음"]:
        btn = page.get_by_role("button", name=label)
        if btn.is_visible(timeout=2000):
            btn.click()
            page.wait_for_load_state("networkidle")
            print(f"[edit] '{label}' 버튼 클릭 → 저장 완료!")
            take_screenshot(page, "06_saved")
            return

    take_screenshot(page, "error_no_save_button")
    raise RuntimeError("저장 버튼을 찾을 수 없습니다. 스크린샷을 확인하세요.")


# ─────────────────────────────────────────────
# main
# ─────────────────────────────────────────────

def main():
    email = os.environ.get("GAME_PING_EMAIL")
    password = os.environ.get("GAME_PING_PASSWORD")
    game_slug = os.environ.get("GAME_SLUG")
    zip_path_str = os.environ.get("WEBGL_ZIP_PATH", "build.zip")
    publisher = os.environ.get("PUBLISHER", "personal").lower()
    team_name = os.environ.get("TEAM_NAME", "")

    missing = [k for k, v in {
        "GAME_PING_EMAIL": email,
        "GAME_PING_PASSWORD": password,
        "GAME_SLUG": game_slug,
    }.items() if not v]
    if missing:
        print(f"[error] 필수 환경변수가 없습니다: {', '.join(missing)}")
        sys.exit(1)

    if publisher == "team" and not team_name:
        print("[error] PUBLISHER=team 일 때 TEAM_NAME이 필요합니다.")
        sys.exit(1)

    # 게임 존재 여부 확인
    is_existing = game_exists(game_slug)
    print(f"[check] 게임 '{game_slug}' 존재 여부: {'기존 게임 (편집 모드)' if is_existing else '신규 게임 (등록 모드)'}")

    # game_title 자동 변환
    game_title = os.environ.get("GAME_TITLE", "") or slug_to_title(game_slug)

    # version 자동 결정
    game_version = os.environ.get("GAME_VERSION", "")
    if not game_version:
        if is_existing:
            current = get_current_version(game_slug)
            game_version = increment_patch(current) if current else "0.0.1"
            print(f"[version] 현재 버전 감지: {current} → {game_version}")
        else:
            game_version = "0.0.1"
            print(f"[version] 신규 게임 기본 버전: {game_version}")

    print(f"[start] game-ping.kr CI/CD 시작")
    print(f"  slug      : {game_slug}")
    print(f"  title     : {game_title}")
    print(f"  version   : {game_version}")
    print(f"  publisher : {publisher}{f' ({team_name})' if publisher == 'team' else ''}")
    print(f"  입력 경로 : {zip_path_str}")

    zip_path = resolve_zip(zip_path_str)
    print(f"  ZIP 경로  : {zip_path}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="ko-KR",
        )
        page = context.new_page()

        try:
            login(page, email, password)

            if is_existing:
                edit_game(page, game_slug, game_version, zip_path)
            else:
                new_game_step1(page, publisher, team_name)
                new_game_step2(page, game_title, game_slug, game_version, zip_path)
                new_game_finish(page)

            print("[done] 배포 완료!")
        except Exception as e:
            take_screenshot(page, "error")
            print(f"[error] {e}")
            sys.exit(1)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
