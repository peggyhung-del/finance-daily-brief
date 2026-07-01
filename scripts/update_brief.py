#!/usr/bin/env python3
"""
Daily Finance Brief Updater
Runs via GitHub Actions — calls Anthropic API with web search
to find 7 non-duplicate news stories and generate index.html.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta

import anthropic

# ── Config ────────────────────────────────────────────────────
TW_TZ = timezone(timedelta(hours=8))
NOW = datetime.now(TW_TZ)
DATE_DISPLAY = NOW.strftime("%Y/%m/%d")
DATE_ISO = NOW.strftime("%Y-%m-%d")
WEEKDAY = "一二三四五六日"[NOW.weekday()]

CAT_LABELS = {
    1: "① 台灣金融產業",
    2: "② 法規發展",
    3: "③ 證券產業",
    4: "④ 重量級人物發言",
    5: "⑤ 保險／證券／銀行業大老闆異動",
    6: "⑥ 川普與美國 AI 大佬動向",
    7: "⑦ 資產管理專法追蹤",
}
CAT_CSS = {1: "c1", 2: "c2", 3: "c3", 4: "c4", 5: "c5", 6: "c6", 7: "c7"}

# ── Read history for dedup ────────────────────────────────────
with open("history.json", "r", encoding="utf-8") as f:
    history = json.load(f)

history_text = "\n".join(
    f"  - [{h['date']}] {h['cat']}: {h['title']}" for h in history
)

# ── Build prompt ──────────────────────────────────────────────
PROMPT = f"""今天是 {DATE_DISPLAY}（週{WEEKDAY}）。

你是一位台灣金融產業新聞編輯，負責為金融商品經理 Peggy 每日整理七大面向的重要新聞。
請用「web_search」工具搜尋以下七大面向近 30 天瀏覽量最高的新聞，每個面向搜尋 1-2 次。

## 七大面向與搜尋關鍵字建議

1. **台灣金融產業**（搜：台灣 金控 銀行 獲利 {NOW.year}年{NOW.month}月）
2. **法規發展**（搜：金管會 央行 金融法規 新制 {NOW.year}年{NOW.month}月）
3. **證券產業**（搜：台灣 ETF 證券 資本市場 {NOW.year}年{NOW.month}月）
4. **重量級人物發言**（搜：楊金龍 彭金隆 金融 發言 {NOW.year}年{NOW.month}月）
5. **保險/證券/銀行業大老闆異動**（搜：金控 銀行 保險 董事長 總經理 人事 {NOW.year}年{NOW.month}月）
6. **川普與美國AI大佬動向**（搜：Trump AI Nvidia OpenAI 黃仁勳 {NOW.year}年{NOW.month}月）
7. **資產管理專法追蹤**（搜：亞洲資產管理中心 專法 金管會 高雄專區 家族辦公室 {NOW.year}年{NOW.month}月）

## 要求

- 每個面向選 **1 條** 近 30 天瀏覽量最高的新聞（共 7 條）
- **不可與下列已播報清單重複**（主題相同即算重複）
- 每條新聞須有：真實可點擊 URL、2-4 句摘要、PM 提醒（對金融商品設計的影響）
- 標題用 <strong> 標記關鍵數字或重點
- PM 提醒要具體到商品類型（利變型保單、ETF、結構型商品等）

## 已播報清單（不可重複）

{history_text}

## 輸出格式

搜尋完成後，請 **只** 回傳下列 JSON（不要 markdown code block，不要任何前後說明文字）：

{{
  "stories": [
    {{
      "cat_num": 1,
      "title_html": "標題 <strong>關鍵重點</strong> 後續描述",
      "source_name": "來源媒體",
      "source_url": "https://完整真實URL",
      "summary": "2-4 句摘要",
      "impact": "PM 提醒文字"
    }}
  ],
  "history_entries": [
    {{
      "date": "{DATE_ISO}",
      "cat": "金融產業",
      "title": "簡短標題（30字內）"
    }}
  ]
}}

stories 和 history_entries 各 7 筆，cat_num 對應 1-7。"""


# ── Call Anthropic API ────────────────────────────────────────
def call_api():
    client = anthropic.Anthropic()  # uses ANTHROPIC_API_KEY env var
    print(f"[{DATE_DISPLAY}] Calling Anthropic API with web search...")

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=16000,
        tools=[{
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 20,
        }],
        messages=[{"role": "user", "content": PROMPT}],
    )

    print(f"  Stop reason: {response.stop_reason}")
    print(f"  Usage: input={response.usage.input_tokens} output={response.usage.output_tokens}")
    return response


def extract_json(response):
    """Extract JSON data from the API response text blocks."""
    texts = []
    for block in response.content:
        if hasattr(block, "text") and block.text.strip():
            texts.append(block.text.strip())

    # Try each text block (last first — most likely to have final JSON)
    for text in reversed(texts):
        cleaned = text
        # Strip markdown code fences
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
        cleaned = re.sub(r"\n?\s*```\s*$", "", cleaned)
        cleaned = cleaned.strip()
        if cleaned.startswith("{"):
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                continue

    raise ValueError(
        "Could not extract JSON from response.\n"
        + "Text blocks:\n"
        + "\n---\n".join(texts[:3])
    )


# ── HTML template ─────────────────────────────────────────────
HTML_TEMPLATE = """<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>台灣金融產業日報 · Financial Product Manager Daily Brief</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: #f6f7f9; color: #15171a; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang TC", "Microsoft JhengHei", sans-serif; line-height: 1.6; }}
  .wrap {{ max-width: 980px; margin: 0 auto; padding: 28px 20px 60px; }}
  header.top {{ border-bottom: 2px solid #15171a; padding-bottom: 12px; margin-bottom: 18px; }}
  .brand {{ font-size: 13px; letter-spacing: 0.18em; color: #b5520e; font-weight: 700; text-transform: uppercase; }}
  h1 {{ font-size: 26px; margin: 4px 0 6px; letter-spacing: -0.01em; }}
  .meta {{ font-size: 13px; color: #5b6470; }}
  .meta strong {{ color: #15171a; }}
  .lead {{ background: #fff; border: 1px solid #e3e6ec; border-left: 4px solid #1f4ed8; padding: 14px 18px; border-radius: 8px; margin: 16px 0 24px; font-size: 14px; color: #2b3340; }}
  .grid {{ display: grid; grid-template-columns: 1fr; gap: 16px; }}
  .card {{ background: #fff; border: 1px solid #e3e6ec; border-radius: 12px; padding: 22px 22px 18px; box-shadow: 0 1px 2px rgba(20,30,50,0.03); }}
  .cat {{ display: inline-flex; align-items: center; gap: 8px; font-size: 12px; font-weight: 600; letter-spacing: 0.04em; color: #fff; padding: 4px 10px; border-radius: 999px; margin-bottom: 12px; }}
  .c1 {{ background: #1f4ed8; }} .c2 {{ background: #0a8754; }} .c3 {{ background: #b5520e; }} .c4 {{ background: #6d28d9; }} .c5 {{ background: #b91c1c; }} .c6 {{ background: #0f766e; }} .c7 {{ background: #be185d; }}
  h2.title {{ font-size: 18px; margin: 2px 0 6px; line-height: 1.4; }}
  .source {{ font-size: 12.5px; color: #5b6470; margin-bottom: 12px; word-break: break-all; }}
  .source a {{ color: #1f4ed8; text-decoration: none; }}
  .source a:hover {{ text-decoration: underline; }}
  .summary {{ font-size: 14.5px; color: #1f2329; margin: 6px 0 14px; }}
  .impact {{ background: #f0f4ff; border: 1px dashed #c6d0ee; border-radius: 8px; padding: 12px 14px; font-size: 13.5px; color: #1f2329; }}
  .impact-title {{ font-weight: 600; color: #1f4ed8; font-size: 12.5px; letter-spacing: 0.02em; margin-bottom: 4px; display: block; }}
  footer {{ margin-top: 28px; font-size: 12px; color: #7a8290; text-align: center; }}
  @media (min-width: 720px) {{ h1 {{ font-size: 28px; }} }}
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <div class="brand">Financial Product Manager Daily Brief</div>
    <h1>台灣金融產業日報</h1>
    <div class="meta">資料日期：<strong>{date_display} (週{weekday})</strong> · 涵蓋區間：近 30 天瀏覽量最高（不重複） · 每日 08:30 自動更新</div>
  </header>
  <div class="lead">為 <strong>Peggy</strong>（金融商品經理）整理 — 六大面向各取近 30 天瀏覽量最高且<strong>未曾播報過</strong>的一條新聞，含摘要、原始連結，與 PM 提醒。</div>
  <div class="grid">
{cards}
  </div>
  <footer>本頁由 GitHub Actions 自動整理 · 每日 08:30 重新抓取近 30 天瀏覽量最高新聞（不重複已播報） · 內容僅供商品設計參考，非投資建議</footer>
</div>
</body>
</html>"""

CARD_TEMPLATE = """
    <article class="card">
      <span class="cat {css}">{label}</span>
      <h2 class="title">{title}</h2>
      <div class="source">來源：<a href="{url}" target="_blank" rel="noopener">{source}</a></div>
      <p class="summary">{summary}</p>
      <div class="impact"><span class="impact-title">🔔 PM 提醒：對金融商品設計的影響</span>{impact}</div>
    </article>"""


def build_html(stories):
    cards = []
    for s in sorted(stories, key=lambda x: x["cat_num"]):
        n = s["cat_num"]
        cards.append(CARD_TEMPLATE.format(
            css=CAT_CSS[n],
            label=CAT_LABELS[n],
            title=s["title_html"],
            url=s["source_url"],
            source=s["source_name"],
            summary=s["summary"],
            impact=s["impact"],
        ))
    return HTML_TEMPLATE.format(
        date_display=DATE_DISPLAY,
        weekday=WEEKDAY,
        cards="\n".join(cards),
    )


# ── Main ──────────────────────────────────────────────────────
def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY environment variable not set.")
        sys.exit(1)

    # Call API (retry once on JSON parse failure)
    for attempt in range(2):
        try:
            response = call_api()
            data = extract_json(response)
            break
        except (ValueError, json.JSONDecodeError) as e:
            if attempt == 0:
                print(f"  Retry due to: {e}")
            else:
                print(f"FATAL: {e}")
                sys.exit(1)

    stories = data["stories"]
    new_entries = data["history_entries"]

    if len(stories) != 7:
        print(f"WARNING: Expected 6 stories, got {len(stories)}")

    # Write index.html
    html = build_html(stories)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Wrote index.html ({len(html):,} bytes)")

    # Update history.json
    history.extend(new_entries)
    with open("history.json", "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    print(f"  Wrote history.json ({len(history)} entries)")

    print(f"\nDone! Updated for {DATE_DISPLAY} (週{WEEKDAY})")
    for s in sorted(stories, key=lambda x: x["cat_num"]):
        n = s["cat_num"]
        print(f"  {CAT_LABELS[n]}: {s['source_name']}")


if __name__ == "__main__":
    main()
