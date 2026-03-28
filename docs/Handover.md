# MoneyPrinterV2 — 에이전트 핸드오버 노트

> 최종 업데이트: 2026-03-27 (Phase 0 코드 구현 완료, 런타임 검증 대기)
> 목적: 이 프로젝트의 전략/결정/구현 컨텍스트를 새 에이전트에게 전달

---

## 1. 프로젝트 한 줄 요약

MoneyPrinterV2는 필리핀 시장을 타겟으로 하는 **반자동 숏폼 영상 미디어 시스템**이다.
단순 AI 영상 자동화가 아니라, 수요 신호를 자동 수집하고 사람이 최종 승인하는 구조다.

---

## 2. 전략적 맥락

### 왜 필리핀인가
- Facebook 세계 최고 사용률
- Lazada/Shopee가 Amazon보다 적합한 제휴 시장
- Taglish(Filipino English) 니치는 경쟁이 상대적으로 낮음
- 타겟 니치: Tipid/Sulit 쇼핑, 저예산 식비, 영어 학습, 생활 도구

### 핵심 전환
```
기존: AI 영상 대량 생성 → YouTube 업로드 (레드오션)
목표: 시장 신호 수집 → 주제 점수화 → 사람 승인
      → Taglish 영상 생성 → 멀티채널 배포 → 성과 피드백
```

### LLM은 차별화 요소가 아님
- 성공/실패는 LLM 품질(5위)보다 니치 선택(70%)이 결정
- YouTube/TikTok이 순수 AI 콘텐츠 적극 억제 중 (트래픽 최대 5.44배 감소)
- "AI 보조 + 인간 레이어" 하이브리드만 정상 배포됨

---

## 3. 확정된 기술 결정

### 3-1. LLM 스택

| 용도 | 모델 | config `llm_provider` 값 | 비용 |
|------|------|--------------------------|------|
| 트렌드 신호 수집 | Gemini 2.5 Flash (Search Grounding) | `"gemini"` | $0 (500쿼리/일 무료) |
| 스크립트 생성 | GPT-4o-mini 또는 로컬 Ollama | `"openai"` / `"ollama"` | ~$0.07~0.30/월 |
| 개발/테스트 | Ollama (로컬) | `"ollama"` | $0 |

지원 provider: `ollama`, `openai`, `gemini` (모두 `src/llm_provider.py`에 구현됨)

Gemini는 `nanobanana2_api_key`(또는 `GEMINI_API_KEY` 환경변수)를 재사용.
모델명은 `config.json`의 `gemini_model` 키로 설정 (기본값: `gemini-2.5-flash`).

**Taglish 프롬프트 필수 패턴:**
```
"Write in Taglish — Filipino English code-switching.
Use Filipino sentence structure with natural English
insertions the way a 25-year-old from Manila would
talk on TikTok. NOT formal Filipino, NOT formal English."
```

**주의:** `nanobanana2_model`은 현재 `gemini-3.1-flash-image-preview`로 설정됨 — 이미지 생성 전용, 변경 불필요.

---

### 3-2. TTS — Chatterbox Turbo (구현 완료)

**`src/classes/Tts.py` 교체 완료** — KittenTTS 제거, Chatterbox Turbo 적용.

- GitHub: `resemble-ai/chatterbox` (MIT 라이선스)
- ELO 1502 vs ElevenLabs 1548
- Zero-shot 보이스 클로닝: 6~10초 레퍼런스 오디오만 필요
- `device="cpu"` 고정 (Apple Silicon MPS 불안정)
- 모델 싱글톤 캐싱 적용 — 프로세스당 1회 로드

**필수 설정 (config.json):**
```json
"tts_provider": "chatterbox",
"tts_ref_audio": ".mp/my_voice_ref.wav"
```

**아직 안 한 작업:**
- [ ] 본인 목소리 10~30초 녹음 → `.mp/my_voice_ref.wav` 저장

**플랫폼 공시 의무 (반드시 적용):**
- YouTube: 업로드 시 "AI 변경/합성 콘텐츠" 토글 활성화
- TikTok: 영상 내 AI 레이블 직접 삽입 (캡션 아님 — 미이행 시 즉시 스트라이크)

---

### 3-3. 크로스포스팅

**단기: Post Bridge ($29/월) 유지**
- 현재 코드베이스에 이미 통합됨 (`src/classes/PostBridge.py`, `src/post_bridge_integration.py`)
- 빠른 시작 우선

**중기 전환: Postiz 자체 호스팅 (약 $6/월)**
- GitHub: `gitroomhq/postiz-app` (AGPL-3.0)
- Docker Compose 배포, 실 설정 3~5시간 (1회성)
- 절감: $23/월, $276/년
- 전환 방법: `PostBridge.py` → `Postiz.py` 클라이언트 교체 (동일 패턴)

**TikTok 직접 API 불가 이유:**
- TikTok API 정책이 단일 크리에이터 내부 도구를 심사에서 명시적으로 거절
- Post Bridge / Postiz 같은 다중 유저 플랫폼을 통해야만 공개 포스팅 가능

---

### 3-4. 데이터 저장 (구현 완료)

**`src/database.py` 신규 생성** — `init_db()`는 `main.py` 시작 시 자동 호출.
DB 파일 위치: `.mp/mpv2.db`

4개 테이블:
- `topic_candidate` — id, cluster_id, keyword, working_title, niche_grade, score, risk_level, status
- `approval_decision` — id, topic_id, decision, reason, decided_at
- `published_asset` — id, topic_id, platform, published_at, external_video_id
- `performance_outcome` — id, topic_id, platform, views, ctr, avg_view_duration, comments, affiliate_clicks

---

### 3-5. 주제 점수화 가중치 (MVP 초기값)

| 항목 | 가중치 | 측정 방식 |
|------|--------|-----------|
| 수요 강도 | +0.25 | YouTube 검색 상위 결과 조회수 중앙값 |
| 상업성 | +0.20 | 니치 등급 기반 기본값 |
| 반복 가능성 | +0.15 | evergreen 태그 + LLM 분류 |
| 최근성 | +0.10 | 최근 30일 영상 비중 |
| 포맷 적합성 | +0.10 | Shorts/Reels 포맷 적합 여부 |
| 경쟁 포화도 | **-0.10** | 상위 10개 채널 구독자 중앙값 |
| 정확도 리스크 | **-0.10** | 금지 카테고리, 사실 확인 필요도 |

> ⚠️ 경쟁 포화도는 반드시 음수 가중치 — 높을수록 나쁨

4주 데이터 후 재조정.

---

## 4. 현재 코드베이스 상태 (2026-03-27 기준)

### 주요 파일
```
src/
├── main.py                    # 인터랙티브 메뉴 루프, 시작 시 init_db() 호출
├── cron.py                    # 헤드리스 스케줄러 (python cron.py <platform> <account_id>)
├── llm_provider.py            # generate_text() — ollama / openai / gemini 3종 지원
├── database.py                # SQLite 스키마 및 get_connection() / init_db()
├── production_request.py      # 외부 topic 주입 인터페이스 (ProductionRequest dataclass)
├── config.py                  # 35+ getter 함수, 매번 config.json 재읽기, 캐싱 없음
├── cache.py                   # .mp/ 폴더 JSON 영속성
├── status.py                  # 터미널 출력 (info/warning/error/success)
├── utils.py                   # rem_temp_files(), Selenium teardown
├── post_bridge_integration.py # 크로스포스팅 오케스트레이션
└── classes/
    ├── YouTube.py             # Data API v3 업로드 (OAuth), Selenium 업로드 제거됨
    ├── Twitter.py             # Selenium 자동화
    ├── AFM.py                 # Amazon 스크래핑 + LLM 피치
    ├── Outreach.py            # Google Maps + 이메일
    ├── Tts.py                 # Chatterbox Turbo (교체 완료)
    └── PostBridge.py          # Post Bridge REST 클라이언트
```

### config.example.json 현재 상태
```json
{
  "llm_provider": "ollama",
  "openai_api_key": "",
  "openai_model": "gpt-4o-mini",
  "gemini_model": "gemini-2.5-flash",
  "nanobanana2_api_key": "",
  "nanobanana2_model": "gemini-3.1-flash-image-preview",
  "tts_provider": "chatterbox",
  "tts_ref_audio": ".mp/my_voice_ref.wav",
  "youtube_client_secrets": "client_secrets.json",
  "youtube_oauth_token": ".mp/youtube_token.json",
  "post_bridge": { "enabled": false }
}
```

### YouTube 업로드 방식 (변경됨)
- **이전:** Selenium Firefox 자동화 (불안정)
- **현재:** YouTube Data API v3 OAuth 2.0 resumable upload
- OAuth 토큰 첫 실행 시 브라우저 인증 플로우 → `.mp/youtube_token.json`에 저장, 이후 자동 갱신
- 필요한 파일: `client_secrets.json` (Google Cloud Console에서 다운로드)

### sys.path 주의
앱은 반드시 프로젝트 루트에서 실행: `python src/main.py`
`src/`가 sys.path에 추가되므로 import는 `from config import *` 형태 사용.

---

## 5. Phase 로드맵 및 Go/No-Go 기준

### Phase 0 — 기반 안정화 ✅ 코드 완료, 설정 대기 중

| 항목 | 상태 |
|------|------|
| YouTube.py Selenium → Data API v3 교체 | ✅ 완료 |
| llm_provider.py Gemini provider 추가 | ✅ 완료 |
| Tts.py KittenTTS → Chatterbox Turbo 교체 | ✅ 완료 |
| SQLite 스키마 (database.py, 4개 테이블) | ✅ 완료 |
| production_request.py 인터페이스 | ✅ 완료 (기존 존재) |
| pip install -r requirements.txt | ⬜ 미실행 |
| 본인 목소리 녹음 → `.mp/my_voice_ref.wav` | ⬜ 미완료 |
| Google OAuth client_secrets.json 설정 | ⬜ 미완료 |
| YouTube API 업로드 1회 성공 검증 | ⬜ 미완료 |

**Go/No-Go:** YouTube API 업로드 1회 성공 + LLM 2개 이상 동작 확인

### Phase 1 — 리서치 자동화 MVP (다음 단계)
- Gemini grounding + YouTube + RSS 신호 수집기
- 주제 점수화 + 일일 shortlist 생성 (`topic_candidate` 테이블 활용)
- CLI 승인 큐 구현 (approve/reject/defer → `approval_decision` 테이블)
- YouTube 성과 → 점수 보정 첫 feedback loop

**Go/No-Go:** shortlist 10개 중 3개 이상 승인하는 날 5일 누적

### Phase 2 — 제작 시스템
- 니치별 Taglish 프롬프트 템플릿
- Pexels stock footage + AI 이미지 혼합
- 배경음악 / 자막 품질 템플릿
- AI 공시 라벨 자동 삽입

**Go/No-Go:** 승인 → 제작 → 업로드 end-to-end 5회 완료

### Phase 3 — 배포 최적화
- 채널별 메타데이터 분기
- Post Bridge → Postiz 자체 호스팅 전환
- 멀티채널 성과 수집 자동화

**Go/No-Go:** 1,000뷰 이상 영상 3개 + CTR 자동 수집 확인

### Phase 4 — 수익화 연결 (중기)
- Lazada Affiliate 링크 삽입 (구매 의도 주제만)
- TikTok Shop 연동

---

## 6. 월 비용 구조

| 항목 | MVP | Postiz 전환 후 |
|------|-----|----------------|
| VPS | $15 | $15+$6 |
| LLM | ~$1 | ~$1 |
| Gemini Grounding | $0 | $0 |
| TTS (Chatterbox) | $0 | $0 |
| Post Bridge / Postiz | $29 | $6 |
| **합계** | **~$45** | **~$28** |

---

## 7. YouTube API 쿼터 주의사항

```
일일 무료 쿼터: 10,000 units

videos.insert (업로드): 1,600 units/회
search.list (검색):      100 units/회

4개 업로드/일 = 6,400 units
30 search/일  = 3,000 units
─────────────────────────────
합계: 9,400/day → 한계 근접

대응: 신호 수집에 Gemini grounding 우선 사용
     YouTube search.list 최소화
     쿼터 초과 시 Google Cloud Console에서 무료 증량 신청 (2~4주 소요)
```

---

## 8. 니치 등급 (자동화 범위 기준)

### A등급 (반자동화 가능)
- Tipid/Sulit 쇼핑 (under-₱299 finds 등)
- 저예산 식비/장보기
- 영어 학습 (BPO English 등)
- 생활 생산성/학교/일 도구

### B등급 (사람 승인 필수)
- OFW 돈 관리
- 정부 제도 설명

### C등급 (자동화 금지)
- 법률/비자/출입국
- 정치/외교
- 건강/의료

---

## 9. 즉시 해야 할 작업 (Phase 0 마무리)

```
[ ] 1. pip install -r requirements.txt 실행
[ ] 2. 본인 목소리 10~30초 녹음 → .mp/my_voice_ref.wav 저장
[ ] 3. Google Cloud Console에서 YouTube Data API OAuth 클라이언트 시크릿 다운로드
       → client_secrets.json으로 저장, config.json의 youtube_client_secrets 경로 설정
[ ] 4. config.json 업데이트 (tts_provider, tts_ref_audio, gemini_model, youtube_client_secrets)
[ ] 5. python src/main.py 실행 → YouTube 업로드 1회 성공 검증 (Go/No-Go)
```

Phase 0 Go/No-Go 통과 후 → Phase 1 (리서치 자동화 MVP) 진입.

---

## 10. 관련 문서

| 문서 | 경로 | 내용 |
|------|------|------|
| 마스터플랜 | `docs/MasterPlan.md` | 전략/워크플로/로드맵 전체 |
| 구현 체크리스트 | `docs/ImplementationChecklist.md` | Phase별 세부 구현 항목 |
| 리서치 아키텍처 | `docs/ResearchAutomationArchitecture.md` | 신호 수집/점수화 설계 |
| CLAUDE.md | `CLAUDE.md` | 코드베이스 구조 가이드 |

---

## 11. 에이전트에게 전달하는 판단 기준

- **Phase 순서를 건너뛰지 않는다.** Go/No-Go 조건 미충족 시 다음 Phase 진입 금지
- **LLM 비용은 판단 기준이 아니다.** 월 $1~5 수준이므로 품질로만 결정
- **Taglish 프롬프트 없이는 어떤 모델도 격식체로 출력한다.** 항상 포함할 것
- **경쟁 포화도 가중치는 반드시 음수(-0.10)다.** 실수하기 쉬운 부분
- **TikTok 직접 API 구현 시도하지 않는다.** 단일 크리에이터 도구로 심사 통과 불가
- **AI 공시 라벨은 필수다.** YouTube 토글 + TikTok 온영상 레이블 — 미적용 시 스트라이크
- **YouTube.py는 이제 Selenium 업로드를 사용하지 않는다.** `_ensure_browser()`는 YouTube.py에 남아있지만 upload_video/get_channel_id에서는 호출되지 않음
