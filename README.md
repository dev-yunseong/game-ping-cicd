# game-ping.kr Deploy Action

game-ping.kr에 WebGL 게임을 자동으로 업로드하는 GitHub Action입니다.

## 사용법

게임 저장소의 워크플로우에서 아래처럼 사용하세요.

```yaml
# .github/workflows/deploy.yml
name: game-ping.kr 배포

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: dev-yunseong/game-ping-cicd@v1
        with:
          email: ${{ secrets.GAME_PING_EMAIL }}
          password: ${{ secrets.GAME_PING_PASSWORD }}
          game_slug: ${{ secrets.GAME_SLUG }}
          zip_path: build.zip   # WebGL ZIP 파일 경로
```

## Inputs

| 이름 | 필수 | 기본값 | 설명 |
|---|---|---|---|
| `email` | ✅ | — | game-ping.kr 로그인 이메일 |
| `password` | ✅ | — | game-ping.kr 로그인 패스워드 |
| `game_slug` | ✅ | — | 게임 URL의 slug |
| `zip_path` | — | `build.zip` | 업로드할 WebGL ZIP 경로 |

**Game Slug 확인 방법**: 게임 페이지 URL이 `game-ping.kr/g/my-game`이면 slug는 `my-game`입니다.

## Secrets 등록

게임 저장소의 **Settings → Secrets and variables → Actions**에서 등록합니다.

| Secret | 값 |
|---|---|
| `GAME_PING_EMAIL` | game-ping.kr 이메일 |
| `GAME_PING_PASSWORD` | game-ping.kr 패스워드 |
| `GAME_SLUG` | 게임 slug |

## Unity GameCI와 함께 사용하기

Unity 빌드 후 자동 배포하는 예시입니다.

```yaml
name: 빌드 & 배포

on:
  push:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: game-ci/unity-builder@v4
        env:
          UNITY_LICENSE: ${{ secrets.UNITY_LICENSE }}
          UNITY_EMAIL: ${{ secrets.UNITY_EMAIL }}
          UNITY_PASSWORD: ${{ secrets.UNITY_PASSWORD }}
        with:
          targetPlatform: WebGL

      - name: WebGL 빌드 압축
        run: zip -r build.zip build/WebGL/WebGL/

      - uses: dev-yunseong/game-ping-cicd@v1
        with:
          email: ${{ secrets.GAME_PING_EMAIL }}
          password: ${{ secrets.GAME_PING_PASSWORD }}
          game_slug: ${{ secrets.GAME_SLUG }}
          zip_path: build.zip
```

## 디버깅

실행 후 Actions 탭에서 `game-ping-screenshots-*` artifact를 다운받아 각 단계의 스크린샷을 확인할 수 있습니다.
