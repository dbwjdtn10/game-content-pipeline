<div align="center">

# AI Game Content Pipeline

**AI 기반 게임 콘텐츠 자동 생성 파이프라인**

게임 아이템, 몬스터, 퀘스트, 패치노트를 AI로 생성하고 자동 검증하는 End-to-End 워크플로우 엔진

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Celery](https://img.shields.io/badge/Celery-Async_Pipeline-37814A?style=for-the-badge&logo=celery&logoColor=white)](https://docs.celeryq.dev)
[![FastAPI](https://img.shields.io/badge/FastAPI-Dashboard_API-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-One--Click_Deploy-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docker.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

</div>

---

## 프로젝트 동기

게임 라이브 서비스에서 시즌/패치마다 수백 개의 아이템, 몬스터, 퀘스트를 제작해야 하지만 수작업은 느리고, 밸런스 오류와 세계관 불일치가 빈번하게 발생합니다.

> *"신규 무기 50개 추가인데 각각 설명문 써야 해..."*
> *"밸런스 패치하려면 몬스터 100마리 스탯 하나하나 조정해야 해..."*
> *"이번 시즌 퀘스트 스토리 10개 초안 필요한데 시간이 없어..."*

이 프로젝트는 AI가 콘텐츠 초안을 생성하고, 통계 기반으로 밸런스/일관성을 자동 검증하여 기획자가 **"리뷰와 창의적 수정"에만 집중**할 수 있는 워크플로우를 구축합니다.

---

## 시스템 아키텍처

```
┌──────────────────────────────────────────────────────────────────────┐
│                         CLI (Typer + Rich)                          │
│  gcpipe item | monster | quest | patch | validate | export | pipe  │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │   Pipeline            │
                    │   Orchestrator        │
                    │   (의존성 그래프 기반)   │
                    └───┬───────┬───────┬───┘
                        │       │       │
            ┌───────────▼─┐ ┌──▼──────┐ │    ┌────────────────┐
            │  Celery     │ │ Celery  │ │    │  Redis         │
            │  Worker 1   │ │ Worker 2│ │    │  (Broker +     │
            │  (아이템)    │ │ (몬스터) │ │    │   Result Store) │
            └──────┬──────┘ └────┬────┘ │    └────────────────┘
                   │             │      │
          ┌────────▼─────────────▼──────▼────────┐
          │          Generators (LLM 호출)         │
          │  ┌─────────┐ ┌─────────┐ ┌─────────┐ │
          │  │ Item    │ │ Monster │ │ Quest   │ │
          │  │ Gen     │ │ Gen     │ │ Gen     │ │
          │  └────┬────┘ └────┬────┘ └────┬────┘ │
          └───────┼───────────┼───────────┼──────┘
                  │           │           │
          ┌───────▼───────────▼───────────▼──────┐
          │    Pydantic Structured Output         │
          │    (스키마 기반 LLM 응답 파싱)          │
          └──────────────────┬────────────────────┘
                             │
          ┌──────────────────▼────────────────────┐
          │          Validators                    │
          │  일관성 · 밸런스 · 중복탐지 · 스키마    │
          │  ┌──────────────────────────────┐      │
          │  │ 검증 실패 → 자동 재생성 루프  │      │
          │  └──────────────────────────────┘      │
          └──────────────────┬────────────────────┘
                             │
          ┌──────────────────▼────────────────────┐
          │     Storage (PostgreSQL + SQLAlchemy)   │
          │     콘텐츠 버전 관리 · 리뷰 상태 추적    │
          └──────────────────┬────────────────────┘
                             │
          ┌──────────────────▼────────────────────┐
          │            Export Layer                 │
          │   JSON (게임엔진) · CSV (기획시트)       │
          │   Markdown (문서) · Jinja2 템플릿       │
          └──────────────────┬────────────────────┘
                             │
          ┌──────────────────▼────────────────────┐
          │   Streamlit Dashboard (리뷰/승인 UI)    │
          │   FastAPI (대시보드 백엔드 API)          │
          └──────────────────────────────────────┘
```

---

## 핵심 기능

### 1. AI 콘텐츠 생성기 (Generators)
LLM과 Pydantic Structured Output을 활용하여 **타입 안전한** 게임 콘텐츠를 자동 생성합니다. 아이템 설명/스탯, 몬스터 밸런싱 제안, 퀘스트 스토리, 패치노트 초안을 지원하며, 세계관 설정과 기존 시드 데이터를 참조하여 일관된 톤과 밸런스를 유지합니다.

### 2. 자동 검증 시스템 (Validators)
생성된 콘텐츠를 4중 검증 파이프라인으로 자동 검사합니다.
- **밸런스 검증** -- 기존 데이터의 평균/표준편차 기반 스탯 범위, 등급 계층, 레벨 성장 곡선 검증
- **일관성 검증** -- 세계관 톤, 네이밍 패턴, 현대어/부적절 표현 탐지 (LLM + 임베딩 유사도)
- **중복 탐지** -- 편집 거리(Levenshtein) + 임베딩 코사인 유사도 앙상블
- **스키마 검증** -- JSON Schema 준수 여부 자동 확인

검증 실패 시 에러 피드백을 프롬프트에 주입하여 **자가 개선 재생성 루프**를 실행합니다.

### 3. 비동기 파이프라인 (Celery DAG)
YAML 설정 기반으로 다단계 콘텐츠 생성 파이프라인을 오케스트레이션합니다. 독립 태스크는 병렬 실행, 의존 태스크는 순차 실행하며, 중간 결과를 Redis에 저장하여 장애 시 이어서 실행할 수 있습니다.

### 4. 콘텐츠 버전 관리 및 리뷰 워크플로우
PostgreSQL에 모든 생성 콘텐츠의 버전을 관리합니다. `draft > reviewing > approved / rejected` 상태 추적, 리뷰어 코멘트, 파이프라인 실행 이력을 기록하여 체계적인 콘텐츠 승인 프로세스를 제공합니다.

### 5. 다중 포맷 내보내기 (Export)
승인된 콘텐츠를 Jinja2 템플릿 기반으로 다양한 포맷으로 출력합니다.
- **JSON** -- 게임 엔진 직접 임포트용
- **CSV** -- 기획 스프레드시트용
- **Markdown** -- 기획 문서/패치노트용

### 6. LLM 비용 최적화
- 동일 파라미터 조합에 대한 **응답 캐싱** (Redis TTL 24h)
- 다건 생성 요청의 **배치 처리**로 API 호출 최소화
- 시드 데이터 동적 샘플링으로 **프롬프트 토큰 절약**
- Rate Limit 대응 (지수 백오프 재시도) + 일일 토큰 사용량 추적

---

## 기술 스택

| 영역 | 기술 | 선정 근거 |
|:-----|:-----|:---------|
| 언어 | **Python 3.11+** | LLM 생태계 호환성, 타입 힌트 강화 |
| LLM | **Gemini API / OpenAI API** | 구조화 출력 네이티브 지원, 비용 효율 |
| 구조화 출력 | **Pydantic** | LLM 응답의 타입 안전성 100% 보장 |
| 워크플로우 | **Celery + Redis** | 대량 콘텐츠 병렬 생성, 태스크 의존성 관리 |
| CLI | **Typer + Rich** | 기획자 친화적 인터페이스, 시각적 피드백 |
| DB | **PostgreSQL + SQLAlchemy** | JSON 컬럼 지원, 콘텐츠 버전 관리 |
| 마이그레이션 | **Alembic** | 스키마 마이그레이션 관리 |
| API | **FastAPI** | 비동기 지원, 자동 API 문서 생성 |
| 대시보드 | **Streamlit** | 빠른 프로토타이핑, 차트 내장 |
| 템플릿 | **Jinja2** | 출력 포맷 유연한 확장 |
| 유사도 검색 | **임베딩 + 코사인 유사도** | 중복 탐지, 톤 일관성 측정 |
| 로깅 | **structlog** | 구조화 로깅, LLM 호출별 비용/지연 추적 |
| 테스트 | **pytest + pytest-asyncio** | 비동기 태스크 테스트 지원 |
| 컨테이너 | **Docker + docker-compose** | 원클릭 환경 구성, 데모 재현성 |

---

## 빠른 시작 (Quick Start)

### 사전 요구사항
- Docker & Docker Compose
- LLM API Key (Gemini 또는 OpenAI)

### 1. 환경 설정

```bash
git clone https://github.com/dbwjdtn10/game-content-pipeline.git
cd game-content-pipeline

# 환경 변수 설정
cp .env.example .env
# .env 파일에 LLM API 키 입력
```

### 2. 실행

```bash
# 전체 서비스 빌드 및 실행 (PostgreSQL, Redis, Worker, API, Dashboard)
docker-compose up --build
```

### 3. CLI 사용

```bash
# CLI 도움말
gcpipe --help

# 대시보드 접속
# http://localhost:8501
```

---

## CLI 사용 예시

### 아이템 생성

```bash
gcpipe item generate \
  --type weapon \
  --rarity legendary \
  --count 10 \
  --theme "화염" \
  --level-range 50-60
```

### 몬스터 밸런싱 제안

```bash
gcpipe monster balance \
  --source game_data/seed/monsters.json \
  --target-level 55 \
  --difficulty hard \
  --output balance_report.md
```

### 퀘스트 스토리 생성

```bash
gcpipe quest generate \
  --type side \
  --region "화산 지대" \
  --npc "대장장이 가론" \
  --count 5 \
  --min-steps 3 \
  --max-steps 7
```

### 자동 검증

```bash
gcpipe validate \
  --target generated/items_20260315.json \
  --check consistency,balance,duplicate
```

### 전체 파이프라인 실행 (데모 시나리오)

```bash
# 1. 시드 데이터 확인
gcpipe content list --type item --limit 5

# 2. 신규 무기 10개 생성
gcpipe item generate --type weapon --rarity epic --count 10 --theme "화염" --level-range 50-60

# 3. 자동 검증 결과 확인
gcpipe validate --target generated/items_20260315.json

# 4. 밸런스 차트 확인
gcpipe content stats --type item --level-range 50-60

# 5. 파이프라인 일괄 실행
gcpipe pipeline run --config demo_pipeline.yaml --async

# 6. 진행 상태 모니터링
gcpipe pipeline status --id pipeline_20260315_001

# 7. 승인 후 내보내기
gcpipe content approve --batch generated/items_20260315.json
gcpipe export --status approved --format csv --output exports/
```

### CLI 출력 예시

```
┌─────────────────────────────────────────────┐
│  아이템 생성 완료                              │
├─────────────────────────────────────────────┤
│  생성: 10개 | 검증 통과: 8개 | 수정 필요: 2개  │
│                                             │
│  [PASS] 화염의 대검        Lv.52  ATK 340   │
│  [PASS] 용암 단도          Lv.55  ATK 285   │
│  [PASS] 불꽃 활           Lv.50  ATK 310   │
│  [WARN] 태양의 지팡이     Lv.58  ATK 520   │
│         -> 밸런스 초과                       │
│  [PASS] 화산석 도끼        Lv.54  ATK 355   │
│  ...                                        │
│                                             │
│  저장: generated/items_20260315.json         │
│  리포트: reports/items_20260315.md           │
└─────────────────────────────────────────────┘
```

---

## 프로젝트 구조

```
game-content-pipeline/
├── docker-compose.yml          # 전체 서비스 오케스트레이션
├── Dockerfile
├── pyproject.toml
│
├── game_data/                  # 게임 기초 데이터 (시드)
│   ├── schema/                 # 아이템/몬스터/퀘스트/스킬 JSON 스키마
│   ├── seed/                   # 시드 데이터 + 세계관 설정
│   └── templates/              # Jinja2 출력 템플릿
│
├── src/
│   ├── cli/                    # Typer CLI 앱 (item, monster, quest, patch, validate, export)
│   ├── generators/             # LLM 기반 콘텐츠 생성기 (아이템, 몬스터, 퀘스트, 스킬, 패치)
│   ├── validators/             # 검증 시스템 (밸런스, 일관성, 중복, 스키마)
│   ├── pipeline/               # Celery 비동기 파이프라인 오케스트레이터
│   ├── storage/                # PostgreSQL 모델 + 콘텐츠 버전 관리 CRUD
│   ├── export/                 # JSON/CSV/Markdown 내보내기 + Jinja2 렌더러
│   ├── api/                    # FastAPI 대시보드 백엔드
│   └── dashboard/              # Streamlit 리뷰 대시보드
│
├── prompts/                    # 프롬프트 버전 관리
│   ├── v1/                     # 시스템 프롬프트 (아이템, 몬스터, 퀘스트, 검증)
│   └── prompt_registry.yaml    # 프롬프트 버전 매핑
│
├── tests/                      # pytest 테스트 (생성기, 검증기, 파이프라인, CLI, 내보내기)
│   └── fixtures/               # 테스트용 시드 데이터
│
└── scripts/
    ├── seed_data.py            # 초기 시드 데이터 생성
    └── benchmark.py            # 생성 품질/속도/비용 벤치마크
```

---

## 주요 성과 지표

| 지표 | 수치 | 비고 |
|:-----|:-----|:-----|
| 밸런스 검증 1차 통과율 | **75~85%** | 자동 보정 적용 시 95%+ |
| 세계관 톤 일관성 | **90%+** | LLM 기반 자동 평가 |
| 이름/설명 중복 탐지 정확도 | **92%+** | 임베딩 + 편집 거리 앙상블 |
| 콘텐츠 초안 작성 시간 단축 | **70~80%** | 아이템 1개 기준 ~15분 -> ~2분 |
| 파이프라인 실행 시간 | **5~8분** | 아이템 50개 + 몬스터 15마리 + 퀘스트 8개 |
| LLM API 비용 | **~$0.15/실행** | 캐싱 + 배치 최적화 적용 기준 |

> 위 수치는 시드 데이터 기반 벤치마크 목표치이며, `scripts/benchmark.py`로 재현할 수 있습니다.

---

## 기술적 하이라이트

| 항목 | 설명 |
|:-----|:-----|
| **End-to-End AI 워크플로우** | 생성 -> 검증 -> 재생성 -> 승인 전체 루프 자동화. 검증 실패 시 에러 피드백을 프롬프트에 주입하여 자가 개선 |
| **Celery DAG 비동기 파이프라인** | 독립 태스크 병렬 + 의존 태스크 순차 실행. 중간 결과 저장으로 장애 복구 가능 |
| **Pydantic Structured Output** | LLM 출력을 100% 타입 안전하게 파싱. 파싱 실패 시 자동 재시도 |
| **통계 기반 밸런스 검증** | 기존 데이터의 레벨별/등급별 분포에서 평균 +/- 2 sigma 범위 검증 + 성장 곡선 회귀 모델 |
| **프롬프트 버전 관리** | 프롬프트를 코드와 분리하여 버전 관리. A/B 벤치마크로 품질 비교 가능 |
| **구조화 로깅 (structlog)** | LLM 호출별 토큰 수, 지연 시간, 비용, 캐시 적중률 추적 |

---

## 자가 개선 재생성 루프 (Self-Improving Regeneration)

검증 실패 시 에러 피드백을 프롬프트에 주입하여 자동으로 재생성하는 핵심 기능입니다.

```
┌───────────────┐     ┌──────────────┐     ┌───────────────┐
│   Generator   │────>│  Validators  │────>│  All Passed?  │
│  (LLM 호출)   │     │  (4중 검증)   │     │               │
└───────────────┘     └──────────────┘     └───────┬───────┘
       ^                                      │         │
       │                                     YES       NO
       │                                      │         │
       │                                      v         v
       │                               ┌──────────┐ ┌────────────────┐
       │                               │  완료 ✅  │ │ 피드백 추출     │
       │                               └──────────┘ │ (실패 사유 분석) │
       │                                            └───────┬────────┘
       │                                                    │
       └────────────────────────────────────────────────────┘
                     피드백 주입 후 재생성 (최대 N회)
```

```python
# 사용 예시
from src.pipeline.regenerator import ContentRegenerator
from src.generators import ItemGenerator
from src.validators.balance import BalanceValidator

generator = ItemGenerator()
balance_validator = BalanceValidator()

regenerator = ContentRegenerator(
    generator=generator,
    validators=[lambda items: balance_validator.check_stat_range(items[0], seed_items)],
    max_attempts=3,
)

result = regenerator.run(type="weapon", rarity="epic", count=3)
# result.succeeded: True/False
# result.attempts: 실제 시도 횟수
# result.validation_history: 라운드별 검증 결과
```

---

## 대시보드 주요 화면

### Overview — 콘텐츠 현황
- 총 콘텐츠 수, 파이프라인 실행 수, 승인 현황 메트릭
- 타입×상태별 피벗 테이블 + 바 차트

### Content Review — 리뷰/승인 워크플로우
- Content Data / Validation / Actions 3탭 구조
- 검증 결과를 severity별 아이콘(✅/⚠️/❌)으로 시각화
- Approve / Reject / **Regenerate** 버튼으로 즉시 액션

### Version History — 버전 비교
- 콘텐츠별 전체 버전 히스토리 조회
- 버전 간 diff 비교 (변경된 필드 하이라이트)

### Balance Chart — 밸런스 분석
- 스탯별 평균/표준편차 메트릭
- 아이템별 스탯 바 차트
- 레벨 vs 총 스탯 성장 곡선

### Pipeline Runs — 실행 히스토리
- 파이프라인 실행 목록 (상태, 소요 시간)
- 스텝별 성공/실패 상세 표시

---

## License

This project is licensed under the [MIT License](LICENSE).
