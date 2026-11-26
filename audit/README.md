# audit/ — 봉인·검증 기록 (Audit Trail)

이 디렉터리는 "그날 우리가 주장한 수치"를 고정하고, 그 주장이 이후에 바뀌지 않았음을
암호학적으로 증명하기 위한 기록입니다. 검증은 저장소 루트에서 `python3 verify.py`.

## 파일

| 파일 | 내용 |
| :--- | :--- |
| `snapshots/YYYY-MM-DD.json` | 거래일별 스냅샷. 그날의 **원값**(종목 종가·KOSPI 지수, 가격 소스·교차검증 상태)과 **재계산 지표**, **저장 표기값**을 함께 담습니다. 해시 대상입니다. |
| `hash_chain.jsonl` | 스냅샷 해시 체인. 한 줄이 한 항목이며 `chain_sha256`으로 직전 항목과 연결됩니다. |
| `seals.jsonl` | 봉인 기록. 어떤 파일을 언제 어떤 `.ots`로 박제했는지, 캘린더 응답은 어땠는지. |
| `ots/*.ots` | OpenTimestamps 증명(DetachedTimestampFile, 바이너리). |
| `genesis-YYYY-MM-DD.json` | Phase 1~2 전 구간을 한 번에 묶은 창세 봉인. 체인 헤드 해시 하나로 모든 거래일 스냅샷을 커밋합니다. |
| `manifest.json` | 체인 헤드·규칙·스키마 요약. |

## 규칙

```
snapshot_sha256 = sha256( canonical_json(snapshot) )
  · canonical_json = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n"  (UTF-8)

chain_sha256    = sha256( prev_chain_sha256 + "\n" + seq + "\n" + date + "\n" + kind + "\n" + snapshot_sha256 )
  · 첫 항목의 prev_chain_sha256 = "0" * 64
```

- **과거를 고쳐 쓰지 않습니다.** 이미 봉인된 날짜의 스냅샷이 바뀌면(소급 정정 등) 기존 항목을
  수정하지 않고 `kind: "revision"` 항목을 **덧붙입니다**. 이전 해시는 스냅샷 본문의
  `seal.revises_sha256` 에 남습니다.
- **봉인 시각은 스냅샷 본문에 넣지 않습니다.** 본문이 같으면 해시가 같아야 재봉인이 멱등이 되기
  때문입니다. 봉인 시각은 `hash_chain.jsonl`·`seals.jsonl`에 남습니다.
- **봉인 실패는 정산을 막지 않습니다.** 네트워크·캘린더 장애 시 경고만 남기고, 다음 실행에서
  `python3 tools/audit_engine.py seal <date> --stamp`(멱등)로 재시도합니다.

## OpenTimestamps

1. `sha256` 다이제스트를 공개 캘린더 3곳(`a.pool.opentimestamps.org`, `b.pool.opentimestamps.org`,
   `ots.btc.catallaxy.com`)에 제출하고, 돌려받은 증명을 병합해 하나의 `.ots`로 저장합니다.
2. 제출 직후 증명은 **캘린더 접수(pending)** 어테스테이션입니다. 캘린더가 커밋을 비트코인 블록에
   넣으면 `python3 tools/timestamp.py upgrade audit/ots/*.ots` 로 **블록 높이 어테스테이션**으로
   승격됩니다(정산 파이프라인이 매일 자동 시도).
3. 증명은 "이 파일이 제출 시점 이후로 존재했다"는 사실을 증명합니다. 파일이 한 바이트라도 바뀌면
   다이제스트가 달라져 검증이 실패합니다.

## 직접 확인

```bash
python3 verify.py
sha256sum audit/snapshots/2026-11-25.json
python3 tools/timestamp.py show audit/ots/2026-11-25.ots
python3 tools/timestamp.py verify audit/snapshots/2026-11-25.json --ots audit/ots/2026-11-25.ots
```
