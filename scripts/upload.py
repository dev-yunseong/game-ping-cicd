"""
game-ping.kr WebGL 게임 자동 업로드 스크립트
- 이메일/패스워드로 로그인
- 게임 등록 플로우 (Step 1 → Step 2 → 완료)
- 개인/팀 게시자 선택 지원
- 디렉토리/파일이 ZIP이 아니면 자동 압축 후 업로드
"""

import os
import sys
import zipfile
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


def step1_select_file_type(page, publisher: str):
    """Step 1: 웹 게임 빌드 선택 + 게시자(개인/팀) 선택"""
    print("[step1] 게임 파일 타입 선택...")
    page.goto(REGISTER_URL)
    page.wait_for_load_state("networkidle")
    take_screenshot(page, "04_step1")

    # 웹 게임 빌드 선택
    page.get_by_role("button", name="웹 게임 빌드").click()
    print("[step1] 웹 게임 빌드 선택 완료")

    # 게시자 선택 (개인/팀)
    # 현재 게시자 버튼 클릭하여 드롭다운 열기
    publisher_btn = page.locator("button").filter(has_text="dev-yunseong").or_(
        page.locator("button").filter(has_text="Team")
    ).first
    publisher_btn.click()
    page.wait_for_timeout(500)

    if publisher.lower() in ("team", "팀"):
        # 팀 선택
        popup = page.locator('[data-slot="popover-content"]')
        popup.get_by_role("button").filter(has_text="Team6515").click()
        print("[step1] 게시자: Team6515 선택")
    else:
        # 개인 선택 (dev-yunseong)
        popup = page.locator('[data-slot="popover-content"]')
        popup.get_by_role("button").filter(has_text="dev-yunseong").click()
        print("[step1] 게시자: dev-yunseong (개인) 선택")

    take_screenshot(page, "04_step1_selected")

    # 다음 단계로
    page.get_by_role("button", name="다음").click()
    page.wait_for_load_state("networkidle")
    print("[step1] 완료 → Step 2로 이동")
    take_screenshot(page, "05_step2")


def step2_fill_info(page, game_title: str, game_slug: str, version: str, zip_path: Path):
    """Step 2: 기본 정보 입력 + WebGL ZIP 업로드"""
    print("[step2] 기본 정보 입력 중...")

    # 게임 제목
    title_input = page.locator("input#title")
    title_input.fill(game_title)
    print(f"[step2] 제목: {game_title}")

    # 슬러그
    slug_input = page.locator("input#slug")
    slug_input.fill(game_slug)
    print(f"[step2] 슬러그: {game_slug}")

    # 버전 (major.minor.patch)
    parts = version.split(".")
    major = parts[0] if len(parts) > 0 else "0"
    minor = parts[1] if len(parts) > 1 else "0"
    patch = parts[2] if len(parts) > 2 else "1"
    page.locator("input#version-major").fill(major)
    page.locator("input#version-minor").fill(minor)
    page.locator("input#version-patch").fill(patch)
    print(f"[step2] 버전: {major}.{minor}.{patch}")

    take_screenshot(page, "06_step2_filled")

    # WebGL ZIP 업로드 — Step2의 마지막 file input (500MB짜리)
    print(f"[step2] WebGL ZIP 업로드 중: {zip_path} ({zip_path.stat().st_size // 1024} KB)")
    file_inputs = page.locator("input[type='file']")
    count = file_inputs.count()
    # 마지막 file input이 WebGL ZIP용
    webgl_input = file_inputs.nth(count - 1)
    webgl_input.set_input_files(str(zip_path))
    print("[step2] 파일 선택 완료, 업로드 대기 중...")

    # 업로드 완료 대기 (파일명이 나타날 때까지)
    try:
        page.wait_for_function(
            f"() => document.body.innerText.includes('{zip_path.name}')",
            timeout=300000
        )
        print("[step2] 업로드 완료!")
    except PlaywrightTimeoutError:
        print("[step2] 업로드 타임아웃 — 계속 진행합니다.")

    take_screenshot(page, "07_step2_uploaded")

    # 다음 단계로
    page.get_by_role("button", name="다음").click()
    page.wait_for_load_state("networkidle")
    print("[step2] 완료 → Step 3으로 이동")
    take_screenshot(page, "08_step3")


def step3_finish(page):
    """Step 3 이후: 소개글 등 나머지 단계를 건너뛰고 등록 완료"""
    print("[step3+] 나머지 단계 처리 중...")
    take_screenshot(page, "08_step3")

    # 남은 단계를 '다음' 또는 '등록' 버튼으로 완료
    for i in range(5):
        finish_btn = page.locator("button").filter(has_text="등록").or_(
            page.locator("button").filter(has_text="완료")
        ).or_(
            page.locator("button").filter(has_text="제출")
        ).first

        if finish_btn.is_visible(timeout=2000):
            finish_btn.click()
            page.wait_for_load_state("networkidle")
            print(f"[step3+] 완료 버튼 클릭!")
            take_screenshot(page, "09_done")
            return

        next_btn = page.get_by_role("button", name="다음")
        if next_btn.is_visible(timeout=2000):
            next_btn.click()
            page.wait_for_load_state("networkidle")
            take_screenshot(page, f"08_step{3+i+1}")
        else:
            break

    print("[step3+] 모든 단계 완료")
    take_screenshot(page, "09_final")


def main():
    email = os.environ.get("GAME_PING_EMAIL")
    password = os.environ.get("GAME_PING_PASSWORD")
    game_slug = os.environ.get("GAME_SLUG")
    game_title = os.environ.get("GAME_TITLE", game_slug)
    version = os.environ.get("GAME_VERSION", "0.0.1")
    zip_path_str = os.environ.get("WEBGL_ZIP_PATH", "build.zip")
    publisher = os.environ.get("PUBLISHER", "personal")  # "personal" 또는 "team"

    missing = [k for k, v in {
        "GAME_PING_EMAIL": email,
        "GAME_PING_PASSWORD": password,
        "GAME_SLUG": game_slug,
    }.items() if not v]

    if missing:
        print(f"[error] 필수 환경변수가 없습니다: {', '.join(missing)}")
        sys.exit(1)

    print(f"[start] game-ping.kr CI/CD 업로드 시작")
    print(f"  게임 slug  : {game_slug}")
    print(f"  게임 제목  : {game_title}")
    print(f"  버전       : {version}")
    print(f"  게시자     : {publisher}")
    print(f"  입력 경로  : {zip_path_str}")

    zip_path = resolve_zip(zip_path_str)
    print(f"  업로드 ZIP : {zip_path}")

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
            step1_select_file_type(page, publisher)
            step2_fill_info(page, game_title, game_slug, version, zip_path)
            step3_finish(page)
            print("[done] 배포 완료!")
        except Exception as e:
            take_screenshot(page, "error")
            print(f"[error] {e}")
            sys.exit(1)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
