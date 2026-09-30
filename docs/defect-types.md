# 결함 유형

생성된 설계에서 반복해 나타나는 결함을 종류별로 모은다. 검사기가 자동으로 잡는
것과 아직 손으로만 발견한 것을 나눠 적는다. 아래쪽 목록이 검사기에 넣을 후보다.

## 검사기가 잡는 것

`tools/audit.py` 의 A~H. 자세한 내용은 `README.md` 의 검사기 절에 있다.

| | 결함 | 심각도 |
|---|---|---|
| A | 과제를 끝까지 못 감, 구조 보존 실패 | fatal |
| B | 표시값이 입력과 다름, 주입된 대화상자 | fatal |
| C | **죽은 컨트롤** — `data-action` 은 있는데 처리기에 분기가 없다 | fatal |
| D | 대비 | warning |
| E | 레이아웃 (겹침·넘침·줄바꿈) | warning |
| F | 원본에 없던 영어 | warning |
| G | 상태가 시각적으로 구분되지 않음 | warning |
| H | 어느 스타일시트도 정의하지 않은 클래스 | warning |

## 검사기가 아직 못 잡는 것

### 상태 전이 누락

입력 수단은 올바르게 만들었으나, **그 입력이 다음 단계의 활성 조건에 연결되지
않아** 과제가 진행 불가능해진다.

관측 (2026-09-30, `outputs/restructure_auto/20260930-145811/attempt_3.html`):

```html
<input type="text" id="acc-number" placeholder="계좌번호 입력" data-action="input-account"/>
<button disabled data-action="go-amount">다음</button>
```

```js
document.getElementById('phone').addEventListener('click', function(e){
  ...
  } else if (a === 'input-account') {
    accountState.account = el.value;    // 클릭했을 때만 실행된다
    updateButtons();                    // 그래서 여기도 안 온다
  }
```

입력 칸은 제대로 있고 `placeholder` 도 맞다. 그런데 값 변화를 **클릭 이벤트로만**
받는다. `input` 리스너가 없으므로 사람이 타이핑해도 `updateButtons()` 가 불리지
않고 `다음` 의 `disabled` 가 풀리지 않는다. 화면에서 더 나아갈 수 없다.

**C(죽은 컨트롤)와 다르다.**

| | C 죽은 컨트롤 | 상태 전이 누락 |
|---|---|---|
| 증상 | 눌러도 아무 일이 없다 | **눌릴 수 없는 상태가 풀리지 않는다** |
| 원인 | `data-action` 에 대응하는 분기가 없다 | 입력과 활성 조건이 이어지지 않았다 |
| 요소 | 버튼 자체가 죽어 있다 | 버튼은 멀쩡하고 앞 단계가 신호를 안 보낸다 |
| 검사 | 정적으로 잡힌다 (마크업 vs 처리기) | 실제로 몰아 봐야 드러난다 |

지금은 A(과제 완주)의 `navigation failed` 로 간접적으로만 드러난다. 왜 멈췄는지는
Playwright 오류 문자열(`locator resolved to <button disabled ...>`)을 읽어야 안다.

**검사기에 넣는다면** — 과제가 멈춘 지점에서 대상 요소가 `disabled` 인지 보고,
그렇다면 그 활성 조건을 바꾸는 코드가 어떤 이벤트에 걸려 있는지 확인하는 방식이
가능하다. `click` 리스너만 있고 `input`/`change` 가 없는 폼 요소는 정적으로도
의심할 수 있다.

## 관련 문서

- 실행별 편차: `variance-notes.md`
- 검사 단계(와이어프레임/스타일 이식본): `README.md`
