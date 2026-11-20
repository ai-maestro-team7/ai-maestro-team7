import { HomeHero } from "@/features/home/components/HomeHero";

/**
 * 홈: 채팅창 하나만 둔 첫 화면. 맞춤 공고와 청년 정책은 "채용·정책" 메뉴에서 본다.
 * 배경(광안대교)이 화면 폭 전체에 깔리도록 본문 폭 상자(PageContainer) 대신 넓은 main을 쓴다.
 * 갈매기가 위쪽으로 조금 넘어가도 보이게 가로만 자른다 (overflow-x-clip).
 */
export default function HomePage() {
  return (
    <main
      id="main"
      className="relative isolate flex w-full flex-1 flex-col justify-center overflow-x-clip px-5 pt-40 pb-48 xl:px-0"
    >
      <HomeHero />
    </main>
  );
}
