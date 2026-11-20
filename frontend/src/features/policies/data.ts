import type { Policy } from "./types";

const BUSAN_YOUTH_PLATFORM = { label: "부산청년플랫폼", url: "https://young.busan.go.kr" } as const;

const SCHEDULE_NOTE = "모집 일정과 지급 금액은 사업별 공식 공고에서 확인할 수 있어요.";

/**
 * 시연용 정책 유형 예시. 금액·일정은 확인되지 않은 값이라 넣지 않는다 (제품 원칙 1).
 * 첫 정책은 Figma 화면 값 그대로이고, 나머지 상세 내용은 같은 틀에 채운 예시다.
 */
export const policies: Policy[] = [
  {
    id: "job-seeking-allowance",
    name: "구직활동비 지원",
    benefit: "구직 준비 비용",
    target: "부산 거주 청년",
    conditions: "거주지, 구직 상태",
    status: "CHECK_NEEDED",
    summary: "구직 준비 비용 · 부산 거주 청년 대상 · 정책 유형 예시",
    checklist: [
      { title: "거주지", description: "주민등록상 부산 거주 요건과 기준일을 확인하세요." },
      { title: "구직 상태", description: "미취업, 졸업·재학, 다른 사업 참여 제한 조건을 확인하세요." },
      { title: "소득 기준과 제출 서류", description: "소득 기준과 주민등록, 졸업·취업 상태 증빙 서류를 확인하세요." },
    ],
    reason:
      "부산 취업을 준비 중인 프로필과 관련 있는 정책이에요. 연령, 소득 같은 추가 요건은 공식 공고에서 확인해 주세요.",
    officialSource: BUSAN_YOUTH_PLATFORM,
    note: SCHEDULE_NOTE,
  },
  {
    id: "interview-suit-rental",
    name: "면접 정장 대여",
    benefit: "면접 준비 지원",
    target: "부산 구직 청년",
    conditions: "면접 일정, 예약",
    status: "CHECK_NEEDED",
    summary: "면접 준비 지원 · 부산 구직 청년 대상 · 정책 유형 예시",
    checklist: [
      { title: "면접 일정", description: "대여 기간 안에 면접 일정이 있는지 확인하세요." },
      { title: "예약 방법", description: "대여 장소와 예약 가능한 날짜를 확인하세요." },
      { title: "제출 서류", description: "면접 확인 자료와 신분 확인 서류를 확인하세요." },
    ],
    reason: "면접을 준비 중인 프로필과 관련 있는 정책이에요. 이용 횟수 같은 추가 요건은 공식 공고에서 확인해 주세요.",
    officialSource: BUSAN_YOUTH_PLATFORM,
    note: SCHEDULE_NOTE,
  },
  {
    id: "youth-job-training",
    name: "청년 직무 교육",
    benefit: "실무 교육 지원",
    target: "지역 취업 희망 청년",
    conditions: "교육 일정, 신청 요건",
    status: "CHECK_NEEDED",
    summary: "실무 교육 지원 · 지역 취업 희망 청년 대상 · 정책 유형 예시",
    checklist: [
      { title: "교육 일정", description: "교육 기간과 출석 조건을 확인하세요." },
      { title: "신청 요건", description: "연령, 거주지, 다른 교육 참여 제한 조건을 확인하세요." },
      { title: "교육 분야", description: "목표 직무와 관련 있는 과정인지 확인하세요." },
    ],
    reason: "보완할 역량과 관련 있는 교육 유형이에요. 과정별 요건은 공식 공고에서 확인해 주세요.",
    officialSource: BUSAN_YOUTH_PLATFORM,
    note: SCHEDULE_NOTE,
  },
];

export function getPolicy(id: string): Policy | undefined {
  return policies.find((policy) => policy.id === id);
}

/** 정책 목록 "신청 전에 확인하세요" 상자에서 바로 보여줄 정책 */
export const featuredPolicy = { policy: policies[0], linkLabel: "구직활동비 요건 보기" } as const;
