# AI Game Content Pipeline - AI 기반 게임 콘텐츠 자동 생성 파이프라인

## 프로젝트 개요

게임 아이템 설명 생성, 몬스터 스탯 밸런싱 제안, 퀘스트 스토리 생성, 패치노트 초안 작성 등 게임 콘텐츠 제작을 자동화하는 CLI 기반 AI 파이프라인. 생성된 콘텐츠를 자동 검증하고, 기획자가 바로 활용할 수 있는 포맷으로 출력한다.

**타겟 공고:** 넥슨 던파시너지실 AI 워크플로우 엔지니어 / 네오플 AI 엔지니어
**핵심 어필:** AI 워크플로우 자동화, 비동기 파이프라인, 게임 기획 + AI 결합, MLOps 감각

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

## 기술 스택

| 영역 | 기술 | 선정 근거 |
|------|------|----------|
| 언어 | Python 3.11+ | LLM 생태계 호환성, 타입 힌트 강화 |
| LLM | Gemini API (or OpenAI API) | 구조화 출력 네이티브 지원, 비용 효율 |
| 워크플로우 | Celery + Redis (비동기 태스크) | 대량 콘텐츠 병렬 생성, 태스크 의존성 관리 |
| 구조화 출력 | Pydantic + LLM Structured Output | LLM 응답의 타입 안정성 보장 |
| CLI | Typer (Click 기반, 자동 도움말) | 기획자 친화적 인터페이스 |
| CLI 출력 | Rich | 테이블/프로그레스바 등 시각적 피드백 |
| DB | PostgreSQL (콘텐츠 저장/버전 관리) | JSON 컬럼 지원, 버전 관리에 적합 |
| ORM | SQLAlchemy + Alembic | 마이그레이션 관리, 타입 안전 쿼리 |
| API | FastAPI (대시보드용) | 비동기 지원, 자동 API 문서 생성 |
| 대시보드 | Streamlit (생성 결과 리뷰/승인) | 빠른 프로토타이핑, 차트 내장 |
| 포맷 출력 | Jinja2 (마크다운/CSV/JSON 템플릿) | 출력 포맷 유연한 확장 |
| 유사도 검색 | 임베딩 + 코사인 유사도 | 중복 탐지, 톤 일관성 측정 |
| 컨테이너 | Docker, docker-compose | 원클릭 환경 구성, 데모 재현성 |
| 테스트 | pytest + pytest-asyncio | 비동기 태스크 테스트 지원 |
| 로깅 | structlog (구조화 로깅) | 파이프라인 실행 추적, 디버깅 용이 |

---

## 해결하는 문제

게임 기획자가 반복적으로 수행하는 콘텐츠 작업들:

```
"신규 무기 50개 추가인데 각각 설명문 써야 해..."
"밸런스 패치하려면 몬스터 100마리 스탯 하나하나 조정해야 해..."
"이번 시즌 퀘스트 스토리 10개 초안 필요한데 시간이 없어..."
"패치노트 변경사항 200줄 정리해야 하는데..."
```

→ AI가 초안을 생성하고, 일관성을 자동 검증하고, 기획자는 리뷰/수정만 하면 되는 파이프라인.

**기대 효과:**
- 콘텐츠 초안 작성 시간: 수작업 대비 **70~80% 단축** (아이템 1개 기준 ~15분 → ~2분)
- 밸런스 검증 자동화로 **수치 오류 사전 차단** (QA 반려율 감소)
- 세계관 톤 일관성 유지 → 출시 후 유저 피드백 "설정 오류" 감소
- 기획자가 **창의적 검토/수정에 집중**할 수 있는 워크플로우 전환

---

## 프로젝트 구조

```
game-content-pipeline/
├── README.md
├── pyproject.toml
├── docker-compose.yml
├── Dockerfile
│
├── game_data/                      # 게임 기초 데이터 (시드)
│   ├── schema/
│   │   ├── item_schema.json        # 아이템 스키마 정의
│   │   ├── monster_schema.json     # 몬스터 스키마 정의
│   │   ├── quest_schema.json       # 퀘스트 스키마 정의
│   │   └── skill_schema.json       # 스킬 스키마 정의
│   │
│   ├── seed/
│   │   ├── items.json              # 기존 아이템 데이터 (참조용)
│   │   ├── monsters.json           # 기존 몬스터 데이터
│   │   ├── quests.json             # 기존 퀘스트 데이터
│   │   └── world_setting.md        # 세계관 설정 (톤 참조)
│   │
│   └── templates/
│       ├── item_description.j2     # 아이템 설명 출력 템플릿
│       ├── patch_note.j2           # 패치노트 출력 템플릿
│       ├── quest_document.j2       # 퀘스트 기획서 출력 템플릿
│       └── balance_report.j2       # 밸런스 리포트 출력 템플릿
│
├── src/
│   ├── __init__.py
│   ├── config.py
│   │
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── main.py                 # Typer CLI 앱 진입점
│   │   ├── commands/
│   │   │   ├── item.py             # 아이템 콘텐츠 생성 커맨드
│   │   │   ├── monster.py          # 몬스터 밸런싱 커맨드
│   │   │   ├── quest.py            # 퀘스트 스토리 생성 커맨드
│   │   │   ├── patch.py            # 패치노트 생성 커맨드
│   │   │   ├── validate.py         # 일관성 검증 커맨드
│   │   │   └── export.py           # 결과 내보내기 커맨드
│   │   └── ui.py                   # Rich 기반 CLI 출력 포맷
│
│   ├── generators/
│   │   ├── __init__.py
│   │   ├── base.py                 # 생성기 베이스 클래스
│   │   ├── item_generator.py       # 아이템 설명/스탯 생성
│   │   ├── monster_generator.py    # 몬스터 스탯/행동 패턴 생성
│   │   ├── quest_generator.py      # 퀘스트 스토리/조건 생성
│   │   ├── skill_generator.py      # 스킬 설명/밸런스 생성
│   │   └── patch_generator.py      # 패치노트 초안 생성
│   │
│   ├── validators/
│   │   ├── __init__.py
│   │   ├── consistency.py          # 세계관/톤 일관성 검증
│   │   ├── balance.py              # 수치 밸런스 검증
│   │   ├── duplicate.py            # 중복/유사 콘텐츠 탐지
│   │   └── schema_check.py         # 스키마 준수 검증
│   │
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── orchestrator.py         # 파이프라인 오케스트레이터
│   │   ├── tasks.py                # Celery 비동기 태스크
│   │   └── hooks.py                # 파이프라인 훅 (전/후처리)
│   │
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── models.py               # SQLAlchemy 모델
│   │   ├── repository.py           # 콘텐츠 CRUD + 버전 관리
│   │   └── migrations/             # Alembic 마이그레이션
│   │
│   ├── export/
│   │   ├── __init__.py
│   │   ├── markdown.py             # 마크다운 출력
│   │   ├── csv_export.py           # CSV 출력 (기획 스프레드시트용)
│   │   ├── json_export.py          # JSON 출력 (게임 엔진 import용)
│   │   └── renderer.py             # Jinja2 템플릿 렌더러
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI (대시보드 백엔드)
│   │   ├── schemas.py
│   │   └── routes/
│   │       ├── content.py          # 콘텐츠 조회/승인/반려
│   │       ├── pipeline.py         # 파이프라인 실행/상태 조회
│   │       └── stats.py            # 생성 통계
│   │
│   └── dashboard/
│       └── app.py                  # Streamlit 리뷰 대시보드
│
├── prompts/                           # 프롬프트 버전 관리
│   ├── v1/
│   │   ├── item_system.txt            # 아이템 생성 시스템 프롬프트
│   │   ├── monster_system.txt         # 몬스터 생성 시스템 프롬프트
│   │   ├── quest_system.txt           # 퀘스트 생성 시스템 프롬프트
│   │   └── validation_system.txt      # 검증용 시스템 프롬프트
│   └── prompt_registry.yaml          # 프롬프트 버전 매핑 (어떤 버전 활성화 중인지)
│
├── tests/
│   ├── test_generators.py
│   ├── test_validators.py
│   ├── test_pipeline.py
│   ├── test_export.py
│   ├── test_cli.py
│   └── fixtures/                      # 테스트용 시드 데이터
│       ├── sample_items.json
│       └── sample_monsters.json
│
└── scripts/
    ├── seed_data.py                # 초기 시드 데이터 생성
    └── benchmark.py                # 생성 품질/속도 벤치마크
```

---

## 핵심 기능 명세

### 1. CLI 인터페이스 (`src/cli/`)

**Typer 기반 CLI 커맨드:**

```bash
# 아이템 설명 생성
gcpipe item generate \
  --type weapon \
  --rarity legendary \
  --count 10 \
  --theme "화염" \
  --level-range 50-60

# 몬스터 밸런싱 제안
gcpipe monster balance \
  --source game_data/seed/monsters.json \
  --target-level 55 \
  --difficulty hard \
  --output balance_report.md

# 퀘스트 스토리 생성
gcpipe quest generate \
  --type side \
  --region "화산 지대" \
  --npc "대장장이 가론" \
  --count 5 \
  --min-steps 3 \
  --max-steps 7

# 패치노트 생성
gcpipe patch generate \
  --changes changelog_v2.5.json \
  --tone professional \
  --format markdown

# 일관성 검증
gcpipe validate \
  --target generated/items_20260315.json \
  --check consistency,balance,duplicate

# 내보내기
gcpipe export \
  --source generated/items_20260315.json \
  --format csv \
  --template game_data/templates/item_description.j2

# 파이프라인 한 번에 실행
gcpipe pipeline run \
  --config pipeline_config.yaml \
  --async
```

**Rich 기반 CLI 출력 (차별화 포인트):**
```
┌─────────────────────────────────────────────┐
│  🗡️  아이템 생성 완료                        │
├─────────────────────────────────────────────┤
│  생성: 10개 | 검증 통과: 8개 | 수정 필요: 2개  │
│                                             │
│  ✅ 화염의 대검        Lv.52  ATK 340       │
│  ✅ 용암 단도          Lv.55  ATK 285       │
│  ✅ 불꽃 활           Lv.50  ATK 310       │
│  ⚠️  태양의 지팡이     Lv.58  ATK 520  ← 밸런스 초과  │
│  ✅ 화산석 도끼        Lv.54  ATK 355       │
│  ...                                        │
│  ⚠️  염화 창          Lv.51  ATK 290  ← 기존 아이템과 유사  │
│                                             │
│  📁 저장: generated/items_20260315.json      │
│  📊 리포트: reports/items_20260315.md        │
└─────────────────────────────────────────────┘
```

### 2. 콘텐츠 생성기 (`src/generators/`)

**아이템 생성기:**

```python
# Pydantic 구조화 출력
class GeneratedItem(BaseModel):
    name: str                       # 아이템 이름
    description: str                # 설명문 (2~3문장)
    rarity: Literal["common", "uncommon", "rare", "epic", "legendary"]
    type: Literal["weapon", "armor", "accessory", "consumable"]
    level_requirement: int          # 요구 레벨
    stats: ItemStats                # 스탯 (공격력, 방어력 등)
    special_effect: str | None      # 특수 효과 설명
    lore: str                       # 세계관 연결 배경 스토리 (1문장)
    obtained_from: str              # 획득처
```

**프롬프트 전략:**
```
[시스템]
당신은 판타지 RPG 게임의 아이템 기획자입니다.
아래 세계관 설정과 기존 아이템 예시를 참고하여 새 아이템을 생성하세요.

[세계관]
{world_setting}

[기존 아이템 예시 (톤/밸런스 참조)]
{seed_items_sample}

[생성 조건]
- 타입: {type}
- 등급: {rarity}
- 테마: {theme}
- 레벨 범위: {level_range}
- 같은 레벨/등급 기존 아이템 스탯 범위: ATK {min_atk}~{max_atk}

[규칙]
1. 설명문은 세계관 톤에 맞게 작성 (중세 판타지, 진지한 톤)
2. 스탯은 기존 아이템과 동일 레벨/등급 범위 내에서 설정
3. 이름이 기존 아이템과 겹치거나 너무 유사하면 안 됨
4. 반드시 JSON 스키마에 맞춰 출력
```

**몬스터 밸런싱 생성기:**
```python
class BalanceSuggestion(BaseModel):
    monster_id: str
    monster_name: str
    current_stats: MonsterStats
    suggested_stats: MonsterStats
    changes: list[StatChange]       # 변경 사항 목록
    reasoning: str                  # 변경 근거 설명
    expected_difficulty: str        # 예상 난이도 변화
    affected_quests: list[str]      # 영향받는 퀘스트
```

**퀘스트 스토리 생성기:**
```python
class GeneratedQuest(BaseModel):
    title: str
    type: Literal["main", "side", "daily", "event"]
    description: str                # 퀘스트 설명 (유저에게 보이는)
    background: str                 # 기획 의도 (내부용)
    npc: str                        # 관련 NPC
    region: str                     # 발생 지역
    level_range: tuple[int, int]
    steps: list[QuestStep]          # 단계별 목표
    rewards: list[QuestReward]      # 보상 목록
    prerequisites: list[str]        # 선행 조건
    estimated_time_minutes: int     # 예상 소요 시간
```

### 3. 검증 시스템 (`src/validators/`)

**일관성 검증:**
```
세계관 톤 체크:
- 생성된 텍스트가 세계관 설정(중세 판타지)에 맞는지 LLM으로 평가
- 현대어/은어/부적절한 표현 탐지
- 기존 콘텐츠와의 톤 유사도 측정 (임베딩 코사인 유사도)

네이밍 일관성:
- 기존 아이템/몬스터 네이밍 패턴 분석
- 새 이름이 패턴에서 벗어나는지 체크
- 기존 이름과의 유사도 검사 (편집 거리 + 의미 유사도)
```

**밸런스 검증:**
```python
class BalanceValidator:
    """
    검증 규칙:
    1. 같은 레벨/등급 아이템의 스탯 범위 (평균 ± 2σ) 내인지
    2. 상위 등급이 하위 등급보다 확실히 강한지
    3. 레벨 대비 스탯 성장 곡선이 기존 패턴을 따르는지
    4. 특수 효과의 수치가 과도하지 않은지
    """
    
    def validate(self, item: GeneratedItem, existing_items: list[Item]) -> ValidationResult:
        results = []
        results.append(self.check_stat_range(item, existing_items))
        results.append(self.check_rarity_hierarchy(item, existing_items))
        results.append(self.check_level_curve(item, existing_items))
        results.append(self.check_special_effect(item))
        return ValidationResult(checks=results)
```

**중복 탐지:**
```
1. 이름 유사도: 편집 거리 (Levenshtein) < 3 → 경고
2. 설명 유사도: 임베딩 코사인 유사도 > 0.85 → 경고
3. 스탯 동일: 같은 레벨에서 스탯이 완전히 같은 아이템 존재 → 에러
4. 효과 중복: 동일한 특수 효과를 가진 아이템 존재 → 경고
```

### 4. 파이프라인 오케스트레이터 (`src/pipeline/`)

**파이프라인 설정 (YAML):**
```yaml
# pipeline_config.yaml
pipeline:
  name: "시즌2 콘텐츠 일괄 생성"
  
  steps:
    - name: generate_weapons
      generator: item
      params:
        type: weapon
        rarity: [rare, epic, legendary]
        count: 30
        theme: "얼음"
        level_range: [60, 70]
      
    - name: generate_monsters
      generator: monster
      params:
        region: "얼음 동굴"
        count: 15
        level_range: [60, 70]
        difficulty: [normal, hard, boss]
    
    - name: generate_quests
      generator: quest
      params:
        type: [side, daily]
        region: "얼음 동굴"
        count: 8
      depends_on: [generate_weapons, generate_monsters]  # 앞 결과 참조
    
    - name: validate_all
      validator: [consistency, balance, duplicate]
      target: [generate_weapons, generate_monsters, generate_quests]
    
    - name: export
      format: [json, csv, markdown]
      template_dir: game_data/templates/

  options:
    async: true             # Celery 비동기 실행
    retry_on_fail: 2        # 검증 실패 시 재생성 횟수
    auto_fix: true          # 밸런스 초과 시 자동 보정
```

**Celery 비동기 처리:**
```
파이프라인 실행 플로우:

1. CLI에서 pipeline run 실행
2. 설정 파싱 → 의존성 그래프 생성
3. 독립 태스크 병렬 실행 (Celery worker)
   - generate_weapons → worker 1
   - generate_monsters → worker 2
4. 의존성 있는 태스크 순차 실행
   - generate_quests (weapons, monsters 결과 참조)
5. 전체 검증 실행
6. 검증 실패 항목 → 재생성 (retry_on_fail 횟수만큼)
7. 최종 결과 저장 + 내보내기
8. 리포트 생성
```

**파이프라인 상태 모니터링:**
```bash
# 실행 상태 확인
gcpipe pipeline status --id pipeline_20260315_001

┌─────────────────────────────────────────────────┐
│  📦 파이프라인: 시즌2 콘텐츠 일괄 생성            │
│  ID: pipeline_20260315_001                       │
│  상태: 진행 중 (3/5 완료)                         │
├─────────────────────────────────────────────────┤
│  ✅ generate_weapons    30/30  (2분 12초)        │
│  ✅ generate_monsters   15/15  (1분 45초)        │
│  🔄 generate_quests     5/8   (진행 중...)       │
│  ⏳ validate_all        대기 중                   │
│  ⏳ export              대기 중                   │
├─────────────────────────────────────────────────┤
│  예상 남은 시간: ~3분                             │
└─────────────────────────────────────────────────┘
```

### 5. 콘텐츠 버전 관리 (`src/storage/`)

```python
class ContentVersion(Base):
    __tablename__ = "content_versions"
    
    id: int
    content_type: str           # item / monster / quest / skill
    content_id: str             # 고유 식별자
    version: int                # 버전 번호
    status: str                 # draft / reviewing / approved / rejected
    data: dict                  # 생성된 콘텐츠 JSON
    validation_result: dict     # 검증 결과
    created_at: datetime
    reviewed_by: str | None     # 리뷰어
    review_comment: str | None  # 리뷰 코멘트
    pipeline_id: str | None     # 어떤 파이프라인에서 생성되었는지
```

**버전 관리 CLI:**
```bash
# 콘텐츠 히스토리 조회
gcpipe content history --type item --id fire_greatsword_01

# 특정 버전 비교
gcpipe content diff --type item --id fire_greatsword_01 --v1 2 --v2 3

# 승인/반려
gcpipe content approve --type item --id fire_greatsword_01 --version 3
gcpipe content reject --type item --id fire_greatsword_01 --version 3 --comment "스탯 너무 높음"

# 승인된 콘텐츠만 내보내기
gcpipe export --status approved --since 2026-03-01
```

### 6. LLM 비용 최적화 & 호출 관리

**비용 최적화 전략:**
```
1. 응답 캐싱
   - 동일 파라미터(타입+등급+테마+레벨) 조합의 생성 요청 캐싱 (Redis TTL: 24h)
   - 검증용 프롬프트 결과 캐싱 (동일 콘텐츠 재검증 방지)

2. 배치 처리
   - 아이템 10개 생성 요청 → 1회 API 호출로 묶어 처리 (토큰 효율)
   - Few-shot 예시를 시드 데이터에서 동적 선택 (불필요한 예시 제거)

3. 프롬프트 토큰 절약
   - 시스템 프롬프트: 핵심 규칙만 포함 (세계관 전문은 별도 참조)
   - 시드 데이터 샘플링: 전체가 아닌 동일 레벨/등급 3~5개만 전달

4. Rate Limit 대응
   - Celery 태스크에 rate_limit 설정 (예: 10/m)
   - API 429 응답 시 지수 백오프 재시도 (최대 3회)
   - 일일 토큰 사용량 추적 + 임계치 알림
```

**프롬프트 버전 관리:**
```yaml
# prompts/prompt_registry.yaml
prompts:
  item_generator:
    active_version: v1
    description: "아이템 생성용 시스템 프롬프트"
    versions:
      v1:
        file: v1/item_system.txt
        created_at: "2026-03-15"
        note: "초기 버전"

  # 프롬프트 변경 시 새 버전 추가 → 이전 버전과 품질 비교 가능
  # benchmark.py로 v1 vs v2 생성 품질 A/B 비교
```

**LLM 호출 로깅:**
```python
# 모든 LLM 호출을 구조화 로깅 → 비용/품질 분석 기반 데이터
{
    "event": "llm_call",
    "generator": "item",
    "model": "gemini-2.0-flash",
    "input_tokens": 1250,
    "output_tokens": 480,
    "latency_ms": 2340,
    "cache_hit": False,
    "prompt_version": "v1",
    "validation_passed": True
}
```

### 7. 에러 처리 & 복구 전략

```
LLM 응답 파싱 실패:
  → Pydantic ValidationError 캐치 → 자동 재시도 (최대 2회, 프롬프트에 에러 피드백 포함)
  → 3회 실패 시 해당 항목 skip + 로그 기록 → 나머지 항목 계속 진행

검증 실패 자동 복구:
  → 밸런스 초과: 스탯을 허용 범위 내 최대값으로 자동 보정 (auto_fix 옵션)
  → 톤 불일치: 재생성 시 실패 사유를 프롬프트에 포함하여 품질 개선
  → 이름 중복: 자동 재생성 (새 이름 생성)

파이프라인 레벨 복구:
  → 개별 태스크 실패 시 해당 태스크만 재실행 (전체 파이프라인 재시작 불필요)
  → 중간 결과 Redis에 저장 → 파이프라인 중단 후 이어서 실행 가능
  → Dead Letter Queue: 반복 실패 태스크 별도 큐로 이동 → 수동 확인
```

### 8. 리뷰 대시보드 (`src/dashboard/`)

**Streamlit 페이지 구성:**

- **Overview:** 파이프라인 실행 현황, 생성/검증/승인 통계
- **Content Review:** 생성된 콘텐츠 카드 뷰, 승인/반려/수정 요청
- **Balance Chart:** 아이템/몬스터 스탯 분포 차트 (기존 vs 신규)
- **Validation Report:** 검증 결과 상세 (어떤 항목이 왜 실패했는지)
- **Pipeline History:** 과거 파이프라인 실행 기록 + 성공률 추이

---

## 구현 순서 (CLI 바이브코딩 가이드)

### Phase 1: 기반 & 스키마 (1~2일)
```
1. 프로젝트 초기화 (구조 생성, 의존성 설치, pyproject.toml)
2. 게임 데이터 스키마 정의 (Pydantic 모델)
3. 시드 데이터 작성 (아이템 20개, 몬스터 15개, 퀘스트 5개)
4. 세계관 설정 문서 작성 (톤, 용어집, 네이밍 규칙)
5. Jinja2 출력 템플릿 작성
6. 프롬프트 v1 작성 + prompt_registry.yaml
7. structlog 기반 로깅 설정
```

### Phase 2: 생성기 구현 (2~3일)
```
6. 생성기 베이스 클래스 설계
7. 아이템 생성기 구현 + 프롬프트 설계
8. 몬스터 밸런싱 생성기 구현
9. 퀘스트 스토리 생성기 구현
10. 패치노트 생성기 구현
11. Pydantic structured output 연동
12. CLI 커맨드 연결 (Typer)
```

### Phase 3: 검증 시스템 (2일)
```
13. 밸런스 검증기 구현 (스탯 범위, 등급 계층, 성장 곡선)
14. 일관성 검증기 구현 (세계관 톤, 네이밍 패턴)
15. 중복 탐지 구현 (이름 유사도, 설명 유사도)
16. 스키마 준수 검증
17. 검증 실패 시 자동 재생성 로직 (에러 피드백 프롬프트 주입)
18. LLM 응답 파싱 실패 재시도 로직
```

### Phase 4: 파이프라인 & 저장소 (2~3일)
```
18. Celery + Redis 셋업
19. 파이프라인 오케스트레이터 구현 (의존성 그래프)
20. YAML 설정 파서
21. PostgreSQL + SQLAlchemy 모델
22. 콘텐츠 버전 관리 CRUD
23. Alembic 마이그레이션
24. 파이프라인 상태 모니터링 CLI
```

### Phase 5: 내보내기 & 대시보드 (2일)
```
25. 내보내기 모듈 (JSON, CSV, 마크다운)
26. Jinja2 템플릿 렌더링
27. Streamlit 리뷰 대시보드
28. 밸런스 차트 (기존 vs 신규 스탯 분포)
```

### Phase 6: 마무리 (1~2일)
```
29. Docker + docker-compose 구성 (PostgreSQL, Redis, Worker, API, Dashboard)
30. pytest 테스트 작성 (생성기 mock, 검증기 단위, 파이프라인 통합)
31. scripts/benchmark.py 구현 (품질/속도/비용 측정)
32. 데모 파이프라인 설정 작성 + 실행 결과 스크린샷 (GIF 권장)
33. README 작성 (성과 수치, 아키텍처 다이어그램, 실행 방법)
34. GitHub 배포
```

**예상 총 소요: 10~14일**

---

## 데모 시나리오

```bash
# 1. 시드 데이터 확인
gcpipe content list --type item --limit 5

# 2. 신규 무기 10개 생성
gcpipe item generate --type weapon --rarity epic --count 10 --theme "화염" --level-range 50-60

# 3. 자동 검증 결과 확인
gcpipe validate --target generated/items_20260315.json

# 4. 밸런스 차트 확인
gcpipe content stats --type item --level-range 50-60

# 5. 전체 파이프라인 실행
gcpipe pipeline run --config demo_pipeline.yaml --async

# 6. 진행 상태 모니터링
gcpipe pipeline status --id pipeline_20260315_001

# 7. 승인 후 내보내기
gcpipe content approve --batch generated/items_20260315.json
gcpipe export --status approved --format csv --output exports/
```

---

## README에 포함할 내용 (포트폴리오 어필용)

```markdown
## 프로젝트 동기
게임 라이브 서비스에서 시즌/패치마다 수백 개의 아이템·몬스터·퀘스트를 제작해야 하지만,
수작업은 느리고 밸런스 오류·세계관 불일치가 빈번합니다.
이 프로젝트는 AI가 콘텐츠 초안을 생성하고, 통계 기반으로 밸런스/일관성을 자동 검증하여
기획자가 "리뷰와 창의적 수정"에만 집중할 수 있는 워크플로우를 구축합니다.

## 주요 성과
- 아이템 생성 → 검증 → 승인까지 End-to-End 파이프라인 자동화
- 밸런스 검증 1차 통과율: 75~85% (자동 보정 적용 시 95%+)
- 세계관 톤 일관성 평가: 90%+ (LLM 기반 자동 평가)
- 이름/설명 중복 탐지 정확도: 92%+ (임베딩 + 편집 거리 앙상블)
- 파이프라인 실행 시간: 50개 아이템 + 15마리 몬스터 + 8개 퀘스트 ≈ 5~8분
- LLM API 비용: 1회 파이프라인 실행 기준 ~$0.15 (캐싱/배치 최적화 적용)

## 기술적 하이라이트
- Celery DAG 기반 비동기 파이프라인 (독립 태스크 병렬, 의존 태스크 순차)
- Pydantic Structured Output으로 LLM 응답 100% 타입 안전 파싱
- 검증 실패 → 에러 피드백 포함 재생성 루프 (자가 개선)
- 프롬프트 버전 관리 + A/B 벤치마크 (품질 추적 가능)
- 구조화 로깅으로 LLM 호출별 토큰/지연/비용 추적

## 실행 방법
docker-compose up --build
# CLI: gcpipe --help
# Dashboard: http://localhost:8501

## 데모
gcpipe pipeline run --config demo_pipeline.yaml
```

> **참고:** 위 수치는 시드 데이터 기반 벤치마크 목표치이며, `scripts/benchmark.py`로 재현 가능.

---

## 차별화 포인트 (면접 대비)

| # | 포인트 | 설명 | 어필 키워드 |
|---|--------|------|------------|
| 1 | **End-to-End AI 워크플로우** | 단순 "생성"이 아닌 생성→검증→재생성→승인 전체 루프 자동화. 실패 시 에러 피드백을 프롬프트에 주입하여 자가 개선 | AI 워크플로우 설계 |
| 2 | **비동기 파이프라인 (Celery DAG)** | 독립 태스크 병렬 + 의존 태스크 순차 실행. 중간 결과 저장으로 장애 복구 가능 | 비동기/분산 처리 |
| 3 | **구조화 출력 (Pydantic)** | LLM 출력을 타입 안전하게 파싱 → JSON으로 게임 엔진에 바로 import 가능. 파싱 실패 시 자동 재시도 | LLM 엔지니어링 |
| 4 | **통계 기반 밸런스 검증** | 기존 데이터의 평균·표준편차·성장 곡선으로 자동 밸런스 체크. 이상치 자동 보정 옵션 | 데이터 분석/ML 감각 |
| 5 | **LLM 비용 최적화** | 응답 캐싱, 배치 처리, 프롬프트 토큰 절약, Rate Limit 대응 → 프로덕션 수준 비용 관리 | MLOps/비용 감각 |
| 6 | **프롬프트 버전 관리** | 프롬프트를 코드와 분리하여 버전 관리 → A/B 벤치마크로 품질 비교 가능 | 프롬프트 엔지니어링 |
| 7 | **기획자 친화적 CLI + 대시보드** | Rich 기반 시각적 CLI + Streamlit 리뷰 UI → 실제 기획자가 쓸 수 있는 도구 형태 | 프로덕트 감각 |
| 8 | **게임 도메인 피처 설계** | SBS게임아카데미 기획 과정 + 게임 개발 경험 → 기획자 Pain Point를 정확히 반영한 피처 설계 | 도메인 전문성 |
| 9 | **3개 프로젝트 시너지** | GameAI Analytics(데이터 분석) → NPC Dialogue(RAG/NLP) → Content Pipeline(워크플로우) = ML·NLP·MLOps 전체 커버 | 포트폴리오 스토리 |

**예상 면접 질문 대비:**
```
Q: "왜 Celery를 선택했나? 다른 대안은?"
A: 의존성 그래프 기반 태스크 오케스트레이션이 필요했고, Python 생태계에서 가장 성숙한 솔루션.
   소규모라면 asyncio로 충분하지만, 워커 스케일링과 태스크 모니터링(Flower)이 필요한
   프로덕션 시나리오를 보여주기 위해 선택.

Q: "LLM이 엉뚱한 응답을 주면?"
A: Pydantic ValidationError 캐치 → 실패 사유를 프롬프트에 포함하여 재시도 (최대 2회).
   3회 실패 시 skip + 로그 기록. 전체 파이프라인은 계속 진행.

Q: "밸런스 검증의 통계적 근거는?"
A: 기존 아이템 데이터의 레벨별/등급별 스탯 분포를 산출하고, 새 아이템이
   평균 ± 2σ 범위 내인지 검증. 성장 곡선은 레벨-스탯 회귀 모델로 예측값과 비교.

Q: "실제 게임 회사에서 이걸 쓴다면 어떻게 개선?"
A: 1) 사내 게임 데이터 연동 (DB 직접 연결)
   2) 기획자 피드백을 파인튜닝/RAG에 반영하는 RLHF 루프
   3) 다국어 콘텐츠 동시 생성 (번역 파이프라인 연결)
   4) Slack/Jira 연동으로 승인 워크플로우 자동화
```
