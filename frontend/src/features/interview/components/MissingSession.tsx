import { Button } from "@/components/ui/Button";

/** 주소에 면접 세션이 없을 때 (새로고침으로 값이 빠졌거나 주소를 직접 연 경우) */
export function MissingSession() {
  return (
    <div
      role="alert"
      className="flex w-full flex-col items-center gap-3 border-t border-b border-t-grey-800 border-b-grey-200 py-12 text-center"
    >
      <p className="text-body font-bold text-grey-900">진행 중인 면접을 찾지 못했어요</p>
      <p className="text-small text-grey-600">설정부터 다시 시작해 주세요.</p>
      <Button href="/interview" size="M">
        면접 설정으로
      </Button>
    </div>
  );
}
