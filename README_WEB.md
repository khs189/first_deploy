# Web Setup Guide

## 1. Local run (Windows)
1. `run_web.bat` 실행
2. 브라우저에서 `http://localhost:8000` 접속
3. `config.ini`의 `[auth] users` 계정으로 로그인
4. `input.xlsx` 업로드 후 `시작/중지/다운로드` 사용

## 2. Key features implemented
- 로그인 인증 후에만 대시보드 접근
- `.xlsx` 업로드
- 시작/중지 버튼으로 작업 제어
- 진행률(%) + 처리건수 실시간 갱신
- 중지 시점까지의 부분 결과 다운로드
- 완료 시 상태 문구/알림:
  - `주소 정제가 완료되었습니다. 다운로드하세요.`

## 3. Deploy with Docker
1. 이미지 빌드:
   - `docker build -t auto-address-web .`
2. 컨테이너 실행:
   - `docker run -p 8000:8000 --name auto-address auto-address-web`
3. 접속:
   - `http://localhost:8000`

## 4. Internet link for external users
배포 서버(예: 클라우드 VM, Docker 호스팅)에 컨테이너를 올린 뒤,
도메인 또는 공인 IP로 접속 링크를 공유하면 됩니다.

예: `http://<server-public-ip>:8000`
