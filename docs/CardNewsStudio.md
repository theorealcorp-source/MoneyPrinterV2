# Card News Studio

최종 업데이트: 2026-03-28

## 적용한 내용

- 카드뉴스 생성 파이프라인 추가
  - 주제 생성
  - 슬라이드 초안 생성
  - 규칙 + LLM 리뷰
  - PNG 렌더링
  - 승인 후 Post Bridge 발행
- 카드뉴스 대시보드 추가
  - 프로필 관리
  - draft 생성/승인/발행
  - 대형 프리뷰와 전체 덱 뷰어
- 카드뉴스 디자인 개편
  - `cover`, `insight`, `list`, `stat`, `quote`, `cta` 슬라이드 타입 도입
  - 덱 단위 테마 팔레트 적용
  - 표지/리스트/CTA 레이아웃 분리
  - 한국어 대응 폰트 fallback 및 텍스트 fitting 개선
- 이미지 백엔드 추상화
  - `image_generation.provider = none | gemini | comfyui`
  - 카드뉴스와 YouTube가 같은 이미지 백엔드를 사용하도록 정리
  - ComfyUI는 기본 checkpoint 워크플로 또는 API workflow JSON 둘 다 지원

## 관련 파일

- `src/content_planner.py`
- `src/cardnews_renderer.py`
- `src/classes/CardNews.py`
- `src/image_generator.py`
- `src/dashboard.py`
- `templates/dashboard.html`
- `src/config.py`

## 설정 키

```json
{
  "image_generation": {
    "provider": "none",
    "comfyui": {
      "base_url": "http://127.0.0.1:8188",
      "workflow_path": "",
      "checkpoint": "",
      "negative_prompt": "low quality, blurry, distorted, watermark, logo, text",
      "steps": 8,
      "cfg": 4.0,
      "sampler_name": "euler",
      "scheduler": "normal",
      "timeout_seconds": 180
    }
  }
}
```

## 로컬 이미지 생성 운영 방식

### 1. 가장 간단한 경로

- ComfyUI 서버 실행
- `image_generation.provider = "comfyui"`
- `image_generation.comfyui.checkpoint`에 체크포인트 파일명 입력
- `workflow_path`는 비워두기

이 경우 MPV2가 내장된 간단한 text-to-image 워크플로를 사용한다.

### 2. 고품질 커스텀 경로

- ComfyUI에서 원하는 FLUX 워크플로 구성
- API 형식 JSON으로 export
- `image_generation.comfyui.workflow_path`에 절대경로 입력

지원 placeholder:

- `{{prompt}}`
- `{{negative_prompt}}`
- `{{width}}`
- `{{height}}`
- `{{steps}}`
- `{{cfg}}`
- `{{seed}}`
- `{{sampler_name}}`
- `{{scheduler}}`
- `{{checkpoint}}`
- `{{filename_prefix}}`

## 현재 확인된 상태

- 대시보드에서 이미지 provider 설정 가능
- 현재 로컬 환경에서 ComfyUI 설치 폴더는 확인됨:
  - `/Users/theo/iCloud Drive (Archive)/Documents/ComfyUI`
- 다만 작업 시점 기준:
  - `http://127.0.0.1:8188` 서버 미실행
  - `models/checkpoints` 및 `models/diffusion_models`에 실제 모델 파일 없음

## 실패 시 동작

- `provider = comfyui`인데 이미지가 하나도 생성되지 않으면 카드뉴스 생성은 명시적 에러로 중단
- `provider = gemini`인데 이미지 생성 실패 시 시각 fallback만으로 렌더링 가능
- `provider = none`이면 배경 생성 없이 카드뉴스 레이아웃만 렌더링

## 다음 권장 작업

1. ComfyUI 서버 실행
2. 사용할 체크포인트 또는 FLUX 워크플로 배치
3. 대시보드 Settings에서 image provider를 `comfyui`로 변경
4. 카드뉴스 한 건 생성해서 실제 배경 품질 확인
