"""
game-ping.kr WebGL 게임 자동 업로드 스크립트
- 이메일/패스워드로 로그인
- 내 게임 목록에서 대상 게임 찾기
- 디렉토리/파일이 ZIP이 아니면 자동 압축 후 업로드
"""

import os
import sys
import time
import zipfile
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

BASE_URL = "https://www.game-ping.kr"
LOGIN_URL = f"{BASE_URL}/auth/login"
SCREENSHOT_DIR = Path("screenshots")

def take_screenshot(page, name: str):
    """디버깅용 스크린샷 저장"""
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    path = SCREENSHOT_DIR / f"{name}.png"
    page.screenshot(path=str(path))
    print(f"[screenshot] {path}")


def resolve_zip(path_str: str) -> Path:
    """
    입력 경로가 ZIP이 아니면 자동으로 압축해서 ZIP 경로를 반환.
    - 디렉토리 → 내부 파일 전체를 ZIP으로 압축
    - .zip 외 단일 파일 → 해당 파일을 ZIP으로 감싸기
    - .zip 파일 → 그대로 반환
    """
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

    # 이메일 입력 (label, placeholder, type 등 다양한 방식으로 탐색)
    email_field = (
        page.get_by_label("이메일", exact=False)
        or page.get_by_placeholder("이메일", exact=False)
        or page.locator("input[type='email']")
    )
    email_field.fill(email)

    # 패스워드 입력
    password_field = (
        page.get_by_label("패스워드", exact=False)
        or page.get_by_placeholder("패스워드", exact=False)
        or page.locator("input[type='password']")
    )
    password_field.fill(password)

    take_screenshot(page, "02_login_filled")

    # 로그인 버튼 클릭
    login_btn = page.get_by_role("button", name="로그인")
    login_btn.click()

    # 로그인 완료 대기 (URL 변경 또는 특정 요소 등장)
    try:
        page.wait_for_url(lambda url: "/auth/login" not in url, timeout=15000)
    except PlaywrightTimeoutError:
        take_screenshot(page, "02_login_error")
        raise RuntimeError("로그인 실패: 이메일/패스워드를 확인하세요.")

    print(f"[login] 성공! 현재 URL: {page.url}")
    take_screenshot(page, "03_after_login")


def find_game_management_url(page) -> str:
    """로그인 후 내 게임 관리 페이지 URL을 찾아 반환"""
    # 유저 메뉴/프로필 아이콘 클릭 시도
    for selector in [
        "[data-testid='user-menu']",
        "[aria-label='사용자 메뉴']",
        "[aria-label='프로필']",
        "button:has-text('내 게임')",
        "a:has-text('내 게임')",
        "a:has-text('게임 관리')",
        "a:has-text('스튜디오')",
        "a:has-text('대시보드')",
        "a[href*='/my']",
        "a[href*='/games']",
    ]:
        try:
            el = page.locator(selector).first
            if el.is_visible(timeout=2000):
                href = el.get_attribute("href")
                if href:
                    print(f"[discover] 게임 관리 링크 발견: {href}")
                    return href
                el.click()
                page.wait_for_load_state("networkidle")
                current = page.url
                if "/auth/login" not in current:
                    print(f"[discover] 이동된 URL: {current}")
                    return current
        except Exception:
            continue

    # 프로필 아이콘(이미지 버튼) 클릭 후 메뉴 탐색
    try:
        profile_btn = page.locator("button img, button[class*='avatar'], button[class*='profile']").first
        if profile_btn.is_visible(timeout=3000):
            profile_btn.click()
            page.wait_for_timeout(1000)
            take_screenshot(page, "04_profile_menu")
            for link_text in ["내 게임", "게임 관리", "스튜디오", "대시보드", "마이페이지"]:
                link = page.get_by_text(link_text, exact=False).first
                if link.is_visible(timeout=1000):
                    link.click()
                    page.wait_for_load_state("networkidle")
                    print(f"[discover] '{link_text}' 클릭 후 URL: {page.url}")
                    return page.url
    except Exception:
        pass

    raise RuntimeError("게임 관리 페이지를 찾을 수 없습니다. 스크린샷을 확인하세요.")


def find_game_and_edit(page, game_slug: str):
    """게임 목록에서 target game을 찾아 편집 페이지로 이동"""
    print(f"[game] '{game_slug}' 게임 편집 페이지 탐색 중...")

    # 직접 게임 편집 URL 패턴 시도
    candidate_urls = [
        f"{BASE_URL}/games/{game_slug}/edit",
        f"{BASE_URL}/games/{game_slug}/update",
        f"{BASE_URL}/my/games/{game_slug}",
        f"{BASE_URL}/studio/{game_slug}",
    ]
    for url in candidate_urls:
        page.goto(url)
        page.wait_for_load_state("networkidle")
        if page.url == url and "404" not in page.title():
            print(f"[game] 편집 페이지 접근 성공: {url}")
            take_screenshot(page, "05_game_edit_page")
            return

    # 게임 목록에서 검색
    management_url = find_game_management_url(page)
    page.goto(management_url)
    page.wait_for_load_state("networkidle")
    take_screenshot(page, "05_game_list")

    # 게임 이름이나 slug로 편집 버튼 찾기
    edit_link = page.locator(
        f"a[href*='{game_slug}'], a[href*='/edit']"
    ).first
    try:
        edit_link.click(timeout=5000)
        page.wait_for_load_state("networkidle")
        print(f"[game] 편집 페이지 이동: {page.url}")
        take_screenshot(page, "05_game_edit_page")
    except Exception:
        take_screenshot(page, "05_game_not_found")
        raise RuntimeError(
            f"게임 '{game_slug}'의 편집 페이지를 찾을 수 없습니다. "
            "GAME_SLUG 환경변수를 확인하세요."
        )


def upload_webgl_zip(page, zip_path: str):
    """WebGL ZIP 파일 업로드"""
    zip_path = Path(zip_path).resolve()
    if not zip_path.exists():
        raise FileNotFoundError(f"ZIP 파일을 찾을 수 없습니다: {zip_path}")

    print(f"[upload] ZIP 파일 업로드 시작: {zip_path} ({zip_path.stat().st_size // 1024} KB)")
    take_screenshot(page, "06_before_upload")

    # 파일 입력 요소 탐색
    file_input_selectors = [
        "input[type='file'][accept*='zip']",
        "input[type='file'][accept*='.zip']",
        "input[type='file']",
    ]
    file_input = None
    for sel in file_input_selectors:
        try:
            el = page.locator(sel).first
            if el.count() > 0:
                file_input = el
                break
        except Exception:
            continue

    if file_input is None:
        take_screenshot(page, "06_no_file_input")
        raise RuntimeError("파일 업로드 input을 찾을 수 없습니다. 스크린샷을 확인하세요.")

    # 드롭존이 있는 경우 클릭 후 파일 선택
    try:
        dropzone = page.locator("[class*='drop'], [class*='upload'], [data-testid*='upload']").first
        if dropzone.is_visible(timeout=2000):
            dropzone.click()
    except Exception:
        pass

    file_input.set_input_files(str(zip_path))
    print("[upload] 파일 선택 완료, 업로드 진행 중...")
    take_screenshot(page, "07_file_selected")

    # 업로드 진행 대기 (프로그레스 바 또는 버튼 상태 변화)
    try:
        page.wait_for_selector(
            "[class*='progress'], [class*='uploading']",
            timeout=5000
        )
        page.wait_for_selector(
            "[class*='progress'], [class*='uploading']",
            state="hidden",
            timeout=300000  # 최대 5분
        )
        print("[upload] 업로드 완료!")
    except PlaywrightTimeoutError:
        # 프로그레스 UI가 없을 수도 있음 — 저장 버튼 탐색으로 이동
        pass

    take_screenshot(page, "08_after_upload")


def save_changes(page):
    """업로드 후 저장/제출 버튼 클릭"""
    save_selectors = [
        "button:has-text('저장')",
        "button:has-text('업데이트')",
        "button:has-text('배포')",
        "button[type='submit']",
    ]
    for sel in save_selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=3000):
                btn.click()
                print(f"[save] 저장 버튼 클릭: {sel}")
                page.wait_for_load_state("networkidle")
                take_screenshot(page, "09_saved")
                return
        except Exception:
            continue

    print("[save] 저장 버튼을 찾지 못했습니다. 스크린샷을 확인하세요.")
    take_screenshot(page, "09_no_save_button")


def main():
    email = os.environ.get("GAME_PING_EMAIL")
    password = os.environ.get("GAME_PING_PASSWORD")
    game_slug = os.environ.get("GAME_SLUG")
    zip_path = os.environ.get("WEBGL_ZIP_PATH", "build.zip")

    missing = [k for k, v in {
        "GAME_PING_EMAIL": email,
        "GAME_PING_PASSWORD": password,
        "GAME_SLUG": game_slug,
    }.items() if not v]

    if missing:
        print(f"[error] 필수 환경변수가 없습니다: {', '.join(missing)}")
        sys.exit(1)

    print(f"[start] game-ping.kr CI/CD 업로드 시작")
    print(f"  게임 slug : {game_slug}")
    print(f"  입력 경로  : {zip_path}")

    zip_path = resolve_zip(zip_path)
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
            find_game_and_edit(page, game_slug)
            upload_webgl_zip(page, zip_path)
            save_changes(page)
            print("[done] 배포 완료!")
        except Exception as e:
            take_screenshot(page, "error")
            print(f"[error] {e}")
            sys.exit(1)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
