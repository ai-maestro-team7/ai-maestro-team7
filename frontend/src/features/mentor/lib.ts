/** 대화 화면 주소. 대화 ID가 없으면 새 대화다. 정적 내보내기라 경로 대신 `?c=`로 고른다. */
export function mentorChatHref(conversationId?: string): string {
  return conversationId ? `/mentor/?c=${encodeURIComponent(conversationId)}` : "/mentor/";
}
