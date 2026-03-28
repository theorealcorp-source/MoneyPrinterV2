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
- 현재 로컬 환경에 ComfyUI 설치 완료:
  - 앱 루트: `/Users/theo/iCloud Drive (Archive)/Documents/ComfyUI/app`
  - 서버 URL: `http://127.0.0.1:8188`
  - 실행 스크립트: `scripts/start_comfyui_local.sh`
  - 기본 체크포인트: `sd_xl_base_1.0_0.9vae.safetensors`
- 추가 체크포인트 설치 완료:
  - `flux1-schnell-fp8.safetensors`
- `image_generation.provider = "comfyui"`로 로컬 `config.json` 설정 완료
- MPV2의 `generate_image_asset(..., provider="comfyui")` 경로로 실제 PNG 생성 검증 완료
- 샘플 결과:
  - `/Users/theo/ai_playgroud/MoneyPrinterV2/.mp/comfyui_smoke/5e1b5f88-ffb7-4c23-bed0-602f74b59c17.png`
- 로컬 SDXL 기본 워크플로 기준 20 step 생성 시간:
  - 약 90초
- FLUX preset 추가:
  - `FLUX Fast`: `flux1-schnell-fp8.safetensors`, `steps=4`, `cfg=1.0`, `scheduler=simple`
- 실사용 기본 조합 추가:
  - `SDXL CardNews`: `sd_xl_base_1.0_0.9vae.safetensors`, `steps=10`, `cfg=4.5`
  - `cardnews.background_strategy = deck_pair`
  - 즉 슬라이드마다 1장씩이 아니라 덱당 2장만 생성해서 재사용
- 대시보드 UI 개편:
  - 좌측 상태/프리셋 레일
  - 중앙 compose workspace
  - latest draft spotlight
  - grouped settings accordion

## FLUX 메모

- `FLUX.1-schnell-fp8`는 설치는 간단하지만, 이 로컬 M1 Max 환경에서는 첫 추론이 체감상 매우 가볍지는 않다.
- 즉, 카드뉴스 배경용으로는 품질/스타일 실험용으로 좋고, 대량 배치는 여전히 SDXL preset이 더 실용적일 수 있다.
- 운영 방식은 다음처럼 가져가는 것이 좋다:
  - 빠른 배치 생성: `SDXL CardNews` + `deck_pair`
  - 키 비주얼 한두 장 테스트: `FLUX Fast` + `shared_single`

## 실패 시 동작

- `provider = comfyui`인데 이미지가 하나도 생성되지 않으면 카드뉴스 생성은 명시적 에러로 중단
- `provider = gemini`인데 이미지 생성 실패 시 시각 fallback만으로 렌더링 가능
- `provider = none`이면 배경 생성 없이 카드뉴스 레이아웃만 렌더링

## 다음 권장 작업

1. 필요할 때 `bash scripts/start_comfyui_local.sh`로 서버 실행
2. 대시보드 Settings에서 step/cfg를 속도 우선으로 조정
3. FLUX 품질이 필요하면 ComfyUI API workflow JSON을 export해서 `workflow_path`에 연결
4. 카드뉴스 한 건 생성해서 슬라이드별 배경 일관성 확인
