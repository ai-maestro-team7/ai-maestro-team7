"use client";

import type { ReactNode } from "react";
import { fetchPublicPostings } from "@/features/jobs/data";
import { cn } from "@/lib/cn";
import { useApi } from "@/lib/useApi";

/**
 * 홈 첫 화면 양옆에 떠 있는 카드 4장 (꾸밈). 서비스가 실제로 보여 주는 화면 조각(공고, 정책, 대화, 진행 중 공고 수)을
 * 살짝 기울여 입체감을 준다. 화면 읽기 프로그램에는 숨기고(aria-hidden), 누를 수 없다. 넓은 화면(xl)에서만 보인다.
 * 공고·정책 카드는 예시다. 실제 회사 이름은 쓰지 않는다 (B-D01). 진행 중 공고 수만 공개 목록 API에서 읽는다.
 */
export function HeroCards() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 hidden select-none [perspective:1200px] xl:block">
      <Floating className="-left-10 top-4 w-56" delay="0s" tilt="[transform:rotateX(8deg)_rotateY(16deg)_rotateZ(-3deg)]">
        <PostingCard />
      </Floating>
      <Floating className="-right-10 top-14 w-56" delay="-3s" tilt="[transform:rotateX(8deg)_rotateY(-16deg)_rotateZ(3deg)]">
        <PolicyCard />
      </Floating>
      <Floating className="-left-20 bottom-0 w-64" delay="-5s" tilt="[transform:rotateX(6deg)_rotateY(14deg)_rotateZ(2deg)]">
        <ChatBubbles />
      </Floating>
      <Floating className="-right-16 bottom-6 w-52" delay="-1.5s" tilt="[transform:rotateX(6deg)_rotateY(-14deg)_rotateZ(-2deg)]">
        <CountCard />
      </Floating>
    </div>
  );
}

/** 바깥 상자는 위아래로 천천히 뜨고, 안쪽 상자는 기울어져 있다 (둘 다 transform이라 나눠 둔다) */
function Floating({ className, delay, tilt, children }: { className: string; delay: string; tilt: string; children: ReactNode }) {
  return (
    <div className={cn("absolute animate-float motion-reduce:animate-none", className)} style={{ animationDelay: delay }}>
      <div className={tilt}>{children}</div>
    </div>
  );
}

function Card({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("rounded-card border border-grey-200 bg-white p-4 shadow-xl shadow-grey-900/8", className)}>
      {children}
    </div>
  );
}

function PostingCard() {
  return (
    <Card>
      <div className="flex items-center justify-between">
        <span className="text-small font-medium text-grey-500">채용 공고</span>
        <span className="rounded-full bg-blue-50 px-2 py-0.5 text-small font-bold text-blue-500">잘 맞아요</span>
      </div>
      <p className="mt-2 text-h3 font-bold text-grey-900">데이터 분석 신입</p>
      <p className="mt-0.5 text-small text-grey-600">부산 해운대구 · 정규직</p>
      <div className="mt-3 flex items-center justify-between border-t border-grey-100 pt-3 text-small">
        <span className="text-grey-500">마감</span>
        <span className="font-bold text-grey-900">D-14</span>
      </div>
    </Card>
  );
}

function PolicyCard() {
  return (
    <Card>
      <div className="flex items-center justify-between">
        <span className="text-small font-medium text-grey-500">청년 지원 정책</span>
        <span className="flex items-center gap-1 text-small font-medium text-green-500">
          <span className="size-1.5 rounded-full bg-green-500" />
          신청 가능
        </span>
      </div>
      <p className="mt-2 text-h3 font-bold text-grey-900">청년 월세 지원</p>
      <p className="mt-0.5 text-small text-grey-600">월 최대 20만 원</p>
      <div className="mt-3 flex flex-col gap-1.5 border-t border-grey-100 pt-3">
        <div className="flex justify-between text-small">
          <span className="text-grey-500">자격 조건</span>
          <span className="font-bold text-grey-900">3개 중 3개 충족</span>
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-grey-100">
          <div className="h-full w-full rounded-full bg-blue-500" />
        </div>
      </div>
    </Card>
  );
}

function ChatBubbles() {
  return (
    <div className="flex flex-col gap-2">
      <p className="self-end rounded-2xl rounded-br-md bg-blue-500 px-3.5 py-2.5 text-small font-medium text-white shadow-lg shadow-blue-500/25">
        이력서로 맞는 공고 찾아줘
      </p>
      <p className="self-start rounded-2xl rounded-bl-md border border-grey-200 bg-white px-3.5 py-2.5 text-small text-grey-800 shadow-xl shadow-grey-900/8">
        맞는 공고 12개와 받을 수 있는 정책 3개를 찾았어요
      </p>
    </div>
  );
}

function CountCard() {
  // 로그인 없이 부르는 공개 목록에서 건수만 읽는다. 못 읽으면 숫자 없이 둔다
  const [state] = useApi("hero-total", () => fetchPublicPostings({ sector: "ALL", region: "ALL", career: "ALL", employment: "ALL", limit: 1 }));
  const total = state.status === "success" ? state.data.total : null;
  return (
    <Card>
      <span className="text-small font-medium text-grey-500">지금 진행 중인 공고</span>
      <p className="mt-1 text-num font-bold text-grey-900">{total === null ? "·" : `${total.toLocaleString("ko-KR")}건`}</p>
      <p className="mt-0.5 text-small text-grey-600">공기업·사기업 공식 채용 공고</p>
    </Card>
  );
}
