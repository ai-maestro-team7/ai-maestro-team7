export type NavItem = {
  label: string;
  href: string;
  /** 이 경로들로 시작하면 현재 탭으로 본다 */
  match: string[];
};

/** GNB 탭 6개 (Figma GNB 27:1616 변형 순서) */
export const NAV_ITEMS: NavItem[] = [
  { label: "홈", href: "/", match: ["/"] },
  { label: "채용·정책", href: "/jobs", match: ["/jobs", "/policies"] },
  { label: "AI 모의면접", href: "/interview", match: ["/interview"] },
  { label: "이력서·직무 진단", href: "/diagnosis", match: ["/diagnosis"] },
  { label: "AI 서류 첨삭", href: "/review", match: ["/review"] },
  { label: "학습 로드맵", href: "/roadmap", match: ["/roadmap"] },
];

/** "채용·정책" 아래 하위 탭 (채용 공고 목록 · 청년 지원 정책 목록) */
export const OPPORTUNITY_TABS = [
  { key: "jobs", label: "채용 공고", href: "/jobs" },
  { key: "policies", label: "청년 지원 정책", href: "/policies" },
] as const satisfies ReadonlyArray<{ key: string; label: string; href: string }>;

/** 현재 경로에 해당하는 탭의 href. `trailingSlash` 설정 때문에 끝의 `/`는 떼고 비교한다. */
export function activeNavHref(pathname: string): string | undefined {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  const found = NAV_ITEMS.find((item) =>
    item.match.some((prefix) => (prefix === "/" ? path === "/" : path === prefix || path.startsWith(`${prefix}/`))),
  );
  return found?.href;
}
