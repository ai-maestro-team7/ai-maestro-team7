"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Checkbox } from "@/components/ui/Checkbox";
import { saveDevModeFlag, useDevModeFlag } from "../devMode";
import { safeNextPath } from "../lib";

/**
 * 로그인 화면 아래 "개발 모드". 켜 두면 카카오·Google이든 아이디·비밀번호든 로그인한 세션에 개발 모드가 붙는다.
 * 로그인을 대신해 주지 않는다. 아이디·비밀번호 로그인은 시연 계정 화면(`/login/demo/`)으로 보낸다.
 */
export function DevModeOption() {
  const next = safeNextPath(useSearchParams().get("next"));
  const enabled = useDevModeFlag();

  return (
    <div className="flex w-full flex-col gap-2 border-t border-grey-200 pt-6 text-left">
      <Checkbox checked={enabled} onChange={saveDevModeFlag}>
        <span className="text-small font-medium text-grey-700">개발 모드로 로그인</span>
        <span className="text-small text-grey-500">
          팀 테스트용이에요. 로그인하면 메뉴에서 유저 정보를 모두 초기화할 수 있어요.
        </span>
      </Checkbox>
      {enabled && (
        <Link
          href={next === "/" ? "/login/demo/" : `/login/demo/?next=${encodeURIComponent(next)}`}
          className="ml-7.5 self-start text-small font-medium text-grey-700 underline underline-offset-4"
        >
          아이디·비밀번호로 로그인
        </Link>
      )}
    </div>
  );
}
