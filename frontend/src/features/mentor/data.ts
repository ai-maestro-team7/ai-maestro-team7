import type { ContinueItem, MentorExample, MentorReply } from "./types";

/** 데모 직무 (D-37: 페르소나 ① 데이터 분석). 칩·예시 문장도 이 직무로 맞춘다 (docs/architecture.md §5.3). */
const DEMO_ROLE = "데이터 분석";

/** 홈 입력칸 초기 문장 */
export const MENTOR_DEFAULT_QUESTION = `부산에서 지원할 만한 ${DEMO_ROLE} 공고를 찾아줘`;

/** 질문 한 건의 최대 글자 수. 대화를 브라우저에 보관하므로 지나치게 긴 글은 받지 않는다. */
export const QUESTION_MAX_LENGTH = 1000;

const jobReply: MentorReply = {
  answer:
    "예시 공고 중에는 (주)가상데이터의 데이터 분석 신입이 가장 잘 맞아요. SQL, Python 필수 요건이 프로필과 맞고, 우대 자격인 ADsP를 준비하면 더 좋아요.",
  recommendations: [
    {
      title: "데이터 분석 신입",
      meta: "(주)가상데이터 · 해운대구 · 정규직",
      actionLabel: "공고 보기",
      href: "/jobs", // 예시 공고는 실제 수집 데이터에 없어 목록으로 보낸다
    },
  ],
};

/** 예시 질문 Chip과 준비된 답변. 틀은 Figma 홈 · AI 멘토 답변 기준이고, 내용은 데모 페르소나에 맞춘 예시다. */
export const mentorExamples: MentorExample[] = [
  { label: `부산 ${DEMO_ROLE} 공고 찾기`, question: MENTOR_DEFAULT_QUESTION, reply: jobReply },
  {
    label: "청년 지원 정책 알아보기",
    question: "부산 청년 지원 정책을 알려줘",
    reply: {
      answer:
        "구직 중인 부산 거주 청년이라면 구직활동비 지원을 먼저 확인해 보세요. 거주지와 구직 상태 조건이 맞는지 정책 상세의 체크리스트로 확인할 수 있어요.",
      recommendations: [
        {
          title: "구직활동비 지원",
          meta: "구직 준비 비용 · 부산 거주 청년",
          actionLabel: "정책 보기",
          href: "/policies", // 예시 정책은 실제 수집 데이터에 없어 목록으로 보낸다
        },
      ],
    },
  },
  {
    // 구조 §5.3 1단계: 챗에서는 짧은 안내와 [모의면접 시작하기] 버튼만 주고, 직무를 미리 채워 면접 화면으로 보낸다.
    label: "면접 질문 연습하기",
    question: "면접 질문을 연습하고 싶어",
    reply: {
      answer:
        "면접 연습은 AI 모의면접 화면에서 할 수 있어요. 희망 직무와 자기소개서를 넣으면 질문 3개와 추가 질문으로 연습해요.",
      recommendations: [
        {
          title: "AI 모의면접",
          meta: `${DEMO_ROLE} · 혼합 면접 · 질문 3개`,
          actionLabel: "모의면접 시작하기",
          href: `/interview?job=${encodeURIComponent(DEMO_ROLE)}`,
        },
      ],
    },
  },
];

/** 예시 질문과 일치하지 않는 질문에 보여줄 시연 답변 */
export const fallbackReply: MentorReply = {
  answer: "시연 모드에서는 준비된 질문에만 답할 수 있어요. 아래 예시 질문을 눌러 보세요.",
};

export function findMentorReply(question: string): MentorReply {
  const normalized = question.trim();
  return mentorExamples.find((example) => example.question === normalized)?.reply ?? fallbackReply;
}

/** 질문에 붙일 수 있는 파일: 이력서 진단과 같은 조건 (PDF, 10MB 이하) */
export const ATTACHMENT_ACCEPT = "application/pdf,.pdf";
export const ATTACHMENT_MAX_BYTES = 10 * 1024 * 1024;

/** 고른 파일이 조건에 맞지 않으면 안내 문구를, 맞으면 null을 돌려준다. */
export function attachmentError(file: File): string | null {
  if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) return "PDF 파일만 올릴 수 있어요.";
  if (file.size > ATTACHMENT_MAX_BYTES) return "10MB 이하 PDF만 올릴 수 있어요.";
  return null;
}

/**
 * 파일을 붙여 보냈을 때의 시연 답변. 서류 종류는 사용자가 고르지 않고 내용으로 판단하므로,
 * 실제 분석 전인 지금은 진단과 첨삭 화면을 함께 안내한다.
 */
export const attachmentReply: MentorReply = {
  answer:
    "파일을 받았어요. 이력서라면 이력서·직무 진단에서 희망 직무 요건과 비교해 강점과 보완할 역량을, 자기소개서라면 AI 서류 첨삭에서 근거가 약한 문장과 고칠 방향을 알려드려요.",
  recommendations: [
    {
      title: "이력서·직무 진단",
      meta: `${DEMO_ROLE} · NCS 직무 요건 비교`,
      actionLabel: "진단하기",
      href: "/diagnosis",
    },
    {
      title: "AI 서류 첨삭",
      meta: "자기소개서 문장 다듬기",
      actionLabel: "첨삭하기",
      href: "/review",
    },
  ],
};

/** 파일만 붙이고 질문을 비워 보냈을 때 대신 쓰는 질문 */
export const ATTACHMENT_QUESTION = "첨부한 파일을 봐줘";

/** 질문 하나에 붙일 시연 답변. 파일을 붙였으면 서류 안내를, 아니면 준비된 답변을 고른다. */
export function mentorReplyTo(question: string, hasAttachment: boolean): MentorReply {
  return hasAttachment ? attachmentReply : findMentorReply(question);
}

/** 홈 "이어서 하기" (Figma 홈 오른쪽 목록). 숫자는 진단·면접·로드맵 Mock 데이터와 같은 값이다. */
export const continueItems: ContinueItem[] = [
  { title: "이력서·직무 진단", description: "서류 적합도 86점 · 보완할 역량 2개", href: "/diagnosis/result" },
  { title: "AI 모의면접", description: "최근 82점 · 질문 3개", href: "/interview/report" },
  { title: "AI 서류 첨삭", description: "자기소개서 문장 다듬기", href: "/review" },
  { title: "학습 로드맵", description: "1주차 · 분석 대시보드 만들기", href: "/roadmap" },
];
