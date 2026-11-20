import { PageContainer } from "@/components/layout/PageContainer";
import { HomeHero } from "@/features/home/components/HomeHero";

/** 홈: 채팅창 하나만 둔 첫 화면. 맞춤 공고와 청년 정책은 "채용·정책" 메뉴에서 본다. */
export default function HomePage() {
  return (
    <PageContainer className="justify-center">
      <HomeHero />
    </PageContainer>
  );
}
