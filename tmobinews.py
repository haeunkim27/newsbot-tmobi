from selenium import webdriver
from selenium.webdriver.common.by import By
import time
from datetime import datetime
from openai import OpenAI
import httpx

print("시작됨")

import os

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    http_client=httpx.Client(verify=False)
)

from selenium.webdriver.chrome.options import Options

options = Options()
options.add_argument("--headless")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(options=options)

KEYWORDS = {
    "자사 및 경쟁사 동향": [
        "티맵", "티맵모빌리티", "TMAP", "우버",
        "카카오모빌리티", "카카오T", "쏘카",
        "네이버 지도", "카카오맵", "구글맵", "구글지도",
        "네이버 내비", "카카오 내비", "현대오토에버"
    ],
    "모빌리티 동향": [
        "현대차", "테슬라", "수입차",
        "전기차", "전기차 충전",
        "대리운전", "자율주행", "인포테인먼트", "SDV",
        "모빌리티 정책", "택시 규제", "자율주행 허가"        
    ],
    "IT 업계 동향": [
        "AI", "빅테크", "엔비디아", "삼성전자",
        "구글", "애플", "쿠팡", "배민", "토스",
        "카카오", "네이버",
        "플랫폼 규제", "개인정보", "해킹",
        "데이터 정책"
    ]
}

all_news = []
seen_links = set()

def chunk_list(data, size):
    for i in range(0, len(data), size):
        yield data[i:i + size]

try:
    for category, keywords in KEYWORDS.items():
        print(f"\n===== {category} =====\n")

        for keyword in keywords:
            print(f"[검색 키워드] {keyword}")

            url = f"https://search.naver.com/search.naver?where=news&query={keyword}&sort=1&nso=so:r,p:1d,a:all"
            driver.get(url)

            time.sleep(3)

            for _ in range(2):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)

            links = driver.find_elements(By.TAG_NAME, "a")

            for link in links:
                try:
                    text = link.text.strip()
                    href = link.get_attribute("href")

                    if not text or not href:
                        continue

                    if "news" not in href:
                        continue

                    if any(x in href for x in [
                        "blog", "cafe", "help", "search",
                        "channelPromotion", "sports", "entertain",
                        "inflow", "ader"
                    ]):
                        continue

                    if len(text) < 15 or len(text) > 60:
                        continue

                    if href in seen_links:
                        continue

                    seen_links.add(href)
                    all_news.append((text, href, category))

                except Exception:
                    continue
                
finally:
    driver.quit()

print("\n===== 크롤링 완료 =====\n")
print("총 기사 개수:", len(all_news))

from datetime import datetime, timedelta

today = (datetime.utcnow() + timedelta(hours=9)).strftime("%y%m%d")

if not all_news:
    print("수집된 기사가 없습니다.")
    raise SystemExit

partial_results = []

print("\n===== GPT 1차 선별 시작 =====\n")

chunks = list(chunk_list(all_news, 60))
print("분할 개수:", len(chunks))

for idx, chunk in enumerate(chunks, start=1):
    print(f"[{idx}/{len(chunks)}] GPT 1차 선별 중...")

    news_text = "\n".join([
        f"{category} | {title} | {link}"
        for title, link, category in chunk
    ])

    prompt = f"""
다음 뉴스 리스트에서 티맵모빌리티 홍보팀 기준으로 "이슈 단위 브리핑 가치"가 있는 기사를 선별하라.

중요:
- 과도하게 제거하지 말 것
- 전체 기사 중 최소 80% 이상 유지할 것
- 기사 단위가 아니라 "이슈 단위"로 판단하되, 다양한 이슈는 최대한 살릴 것

선별 원칙:
1. 완전히 동일한 기사, 동일 링크, 재송고성 유사 기사만 제거하라.
2. 같은 이슈라도 매체 관점이나 내용 포인트가 다르면 별도 기사로 인정할 수 있다. (그러나 대부분 헤드라인 많이 겹치면 지워라)
3. 아래 기사는 우선 제외:
   - 순수 정치
   - 일반 사건사고
   - 단순 지역 행사
   - 산업/서비스/경쟁사/규제/기술과 무관한 기사
4. 애매한 경우에는 포함 여부를 보수적으로 판단하되, 브리핑 가치가 낮으면 제외하라.
5. 반드시 24시간 이내 기사만 포함하라. (eg. 네이버 상에서 00시간 전, 분전 기사만 남기고, 0일전 기사는 안됨)
   오래된 기사(하루 이상)는 모두 제거하라.
   
우선순위:
- 티맵 / 티맵모빌리티 / TMAP 직접 언급 기사
- 경쟁사(카카오모빌리티, 우버, 쏘카, 네이버지도 등) 관련 핵심 기사
- 모빌리티 시장 변화, 규제, 제휴, 신사업, 실적, 서비스 출시/중단 기사
- AI, 플랫폼 규제, 개인정보, 빅테크 변화 중 사업 영향이 큰 기사 (트렌드로 참고할 만한 건 남겨놔야 함, 해킹이나 개인정보 같은 정책 이슈는 중요)

출력 형식:
카테고리 | 기사 제목 | URL


출력 형식:
카테고리 | 기사 제목 | URL

뉴스:
{news_text}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4.1",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        result = response.choices[0].message.content.strip()
        if result:
            partial_results.append(result)

    except Exception as e:
        print(f"GPT 1차 호출 에러: {e}")

    time.sleep(1.5)

print("\n===== GPT 1차 선별 완료 =====\n")
print("1차 결과 묶음 수:", len(partial_results))

if not partial_results:
    print("GPT 1차 선별 결과가 없습니다.")
    raise SystemExit

final_input = "\n".join(partial_results)

final_prompt = f"""
다음은 1차 선별된 뉴스 목록이다.
이를 티맵모빌리티 홍보팀용 최종 미디어브리핑으로 정리하라.

목표:
- 지나치게 많이 버리지 말 것
- 그러나 기사 전체를 모두 싣지는 말 것
- 중복 제거 + 우선순위 선별을 통해 브리핑용으로 압축할 것

선별 원칙:
1. 완전히 동일한 기사, 동일 링크, 재송고성 유사 기사만 제거하라.
2. 같은 이슈라도 매체 관점이나 내용 포인트가 다르면 별도 기사로 인정할 수 있다. (자사 한정)
3. 아래 기사는 우선 제외:
   - 순수 정치
   - 일반 사건사고
   - 단순 지역 행사
   - 산업/서비스/경쟁사/규제/기술과 무관한 기사
4. 애매한 경우에는 포함 여부를 보수적으로 판단하되, 브리핑 가치가 낮으면 제외하라.
5. 헤드라인에 고유명사(지역명, 서비스명 등)가 반복되면 중복처리해라


우선순위 규칙:
- 가장 먼저 남길 기사:
  1) 티맵 / 티맵모빌리티 / TMAP 직접 언급 기사
  2) 경쟁사(카카오모빌리티, 우버, 쏘카, 네이버지도 등) 관련 핵심 기사
  3) 모빌리티 시장 변화, 규제, 제휴, 신사업, 실적, 서비스 출시/중단 기사
  4) AI, 플랫폼 규제, 개인정보, 빅테크 변화 중 사업 영향이 큰 기사 (트렌드로 참고할 만한 건 남겨놔야 함, 해킹이나 개인정보 같은 정책 이슈는 중요)

기사 수 규칙:
- 자사 및 경쟁사 동향: 최대 8건
- 모빌리티 동향: 최대 10건 (가능하다면 7건 이상은 채울 것)
- IT 업계 동향: 최대 10건 (가능하다면 8건 이상은 채울 것)
- 전체 최대 23~25건
- 전체 기사 중 브리핑 가치가 높은 순서대로 선별하라. 
- 모든 카테고리가 0건인건 말이 안됨 적당히 보수적으로 처리하라

정렬 규칙:
- "자사 및 경쟁사 동향"에서는 티맵 / 티맵모빌리티 / TMAP 관련 기사를 최상단에 배치하라.
- 그 다음 경쟁사 기사, 그 다음 기타 관련 기사 순으로 정렬하라.
- 중요도 순으로 정렬해라
- 반드시 "기사 제목 + URL" 형태로만 출력

출력 형식:
[미디어브리핑-{today}]

■ 자사 및 경쟁사 동향

기사 제목
URL

기사 제목
URL

■ 모빌리티 동향

기사 제목
URL

기사 제목
URL

■ IT 업계 동향

기사 제목
URL

기사 제목
URL

출력 규칙 (강제):
- 각 기사는 반드시 2줄로 구성 (제목 1줄 + URL 1줄)
- 제목과 URL을 같은 줄에 쓰면 안됨
- 카테고리 아래에는 반드시 한 줄 공백
- 설명, 요약, 추가 문장 절대 금지
- 특수기호(※, -, • 등) 사용 금지
- 형식이 다르면 오답 처리

뉴스:
{final_input}
"""

import requests

print("\n===== 최종 브리핑 생성 중 =====\n")

try:
    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role": "user", "content": final_prompt}],
        temperature=0.2
    )

    final_result = response.choices[0].message.content.strip()

    print("\n===== 최종 미디어브리핑 =====\n")
    print(final_result)

    SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

    requests.post(
        SLACK_WEBHOOK_URL,
        json={"text": final_result},
        timeout=30
    )

    print("Slack 전송 완료")

except Exception as e:
    print(f"최종 GPT 호출 에러: {e}")