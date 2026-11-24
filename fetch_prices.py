"""관심 종목의 최근 종가를 받아 prices.json으로 저장합니다. (GitHub Actions가 매일 실행)

- 종목 목록: watchlist.json
  한국 주식은 종목코드 6자리만 쓰면 코스피·코스닥을 알아서 찾습니다. 예) 005930
  (005930.KS, 417840.KQ처럼 시장을 직접 붙여도 됩니다)
  미국 주식은 티커 그대로 씁니다. 예) AAPL
- 시세 출처: Yahoo Finance 차트 데이터 (미국 주식은 실패하면 Stooq로 한 번 더 시도)
"""
import csv
import io
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta

UA = {"User-Agent": "Mozilla/5.0 (compatible; my-calendar-prices/1.0)"}
KST = timezone(timedelta(hours=9))


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8")


def from_yahoo(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=10d&interval=1d"
    res = json.loads(get(url))["chart"]["result"][0]
    meta = res["meta"]
    tz = timezone(timedelta(seconds=meta.get("gmtoffset", 0)))
    rows = [
        (datetime.fromtimestamp(t, tz).date().isoformat(), c)
        for t, c in zip(res["timestamp"], res["indicators"]["quote"][0]["close"])
        if c is not None
    ]
    # 장중이면 마지막 줄은 아직 끝나지 않은 오늘 시세라서 뺍니다
    now = datetime.now(tz)
    period = (meta.get("currentTradingPeriod") or {}).get("regular") or {}
    if rows and period and period.get("start", 0) <= now.timestamp() < period.get("end", 0):
        if rows[-1][0] == now.date().isoformat():
            rows.pop()
    if len(rows) < 2:
        raise ValueError("종가 데이터가 부족해요")
    return {"currency": meta.get("currency", ""), "date": rows[-1][0], "close": rows[-1][1], "prev": rows[-2][1]}


def from_stooq(symbol):
    text = get(f"https://stooq.com/q/d/l/?s={symbol.lower()}.us&i=d")
    rows = [r for r in csv.DictReader(io.StringIO(text)) if r.get("Close") not in (None, "", "N/D")]
    if len(rows) < 2:
        raise ValueError("Stooq 데이터 없음")
    return {"currency": "USD", "date": rows[-1]["Date"], "close": float(rows[-1]["Close"]), "prev": float(rows[-2]["Close"])}


def main():
    with open("watchlist.json", encoding="utf-8") as f:
        watch = json.load(f)
    try:
        with open("prices.json", encoding="utf-8") as f:
            old_items = json.load(f).get("items", [])
    except (OSError, ValueError):
        old_items = []
    old = {i["symbol"]: i for i in old_items}

    items, failed = [], []
    for w in watch:
        sym = str(w["symbol"]).strip().upper()
        name = str(w.get("name") or sym)
        is_code = len(sym) == 6 and sym[:1].isdigit()          # 한국 종목코드 6자리
        market = "KR" if is_code or sym.endswith((".KS", ".KQ")) else "US"
        if is_code:
            tries = [(from_yahoo, sym + ".KS"), (from_yahoo, sym + ".KQ")]
        elif market == "US":
            tries = [(from_yahoo, sym), (from_stooq, sym)]
        else:
            tries = [(from_yahoo, sym)]
        data = None
        for source, s in tries:
            try:
                data = source(s)
                sym = s
                break
            except Exception as e:  # 다음 후보로
                print(f"[{s}] {source.__name__} 실패: {e}", file=sys.stderr)
            time.sleep(1)
        if data is None:
            failed.append(sym)
            prev = next((old[k] for k in (sym, sym + ".KS", sym + ".KQ") if k in old), None)
            if prev:  # 실패하면 예전 값을 그대로 둡니다
                items.append({**prev, "name": name, "stale": True})
            continue
        change = data["close"] - data["prev"]
        items.append({
            "symbol": sym, "name": name, "market": market, "currency": data["currency"],
            "date": data["date"], "close": round(data["close"], 4), "prev": round(data["prev"], 4),
            "change": round(change, 4), "changePct": round(change / data["prev"] * 100, 2) if data["prev"] else 0,
        })
        time.sleep(1)

    # 종가가 하나도 안 바뀌었으면 파일을 그대로 둬서 쓸데없는 저장(커밋)이 생기지 않게 합니다
    if items == old_items:
        print(f"바뀐 종가가 없어요 ({len(items)}개 확인)")
        return
    out = {"updated": datetime.now(KST).isoformat(timespec="minutes"), "items": items, "failed": failed}
    with open("prices.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"저장: {len(items)}개, 실패: {failed}")


if __name__ == "__main__":
    main()
