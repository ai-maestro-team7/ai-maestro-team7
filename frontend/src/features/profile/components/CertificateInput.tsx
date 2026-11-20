"use client";

import { X } from "lucide-react";
import { type KeyboardEvent, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Field, fieldA11y } from "@/components/ui/Field";
import { cn } from "@/lib/cn";
import { CERTIFICATE_MAX_LENGTH, MAX_CERTIFICATES } from "../options";

/**
 * 가진 자격증 (선택). 이름을 적고 추가하면 아래 목록에 쌓인다. 백엔드는 10개까지, 이름마다 50자까지 받는다.
 * 공고의 자격 요건·우대 조건과 글자로 맞춰 보므로 자격증 이름을 그대로 적게 안내한다.
 */
export function CertificateInput({
  id,
  value,
  onChange,
}: {
  id: string;
  value: string[];
  onChange: (next: string[]) => void;
}) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string>();
  const full = value.length >= MAX_CERTIFICATES;

  function add() {
    const name = draft.trim();
    if (!name) return;
    if (value.some((item) => item.toLowerCase() === name.toLowerCase())) {
      setError("이미 넣은 자격증이에요.");
      return;
    }
    if (full) {
      setError(`자격증은 ${MAX_CERTIFICATES}개까지 넣을 수 있어요.`);
      return;
    }
    onChange([...value, name]);
    setDraft("");
    setError(undefined);
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    // 한글 조합 중 Enter는 글자를 확정하는 입력이라 건너뛴다
    if (event.key !== "Enter" || event.nativeEvent.isComposing) return;
    event.preventDefault(); // 폼 전체가 저장되지 않게
    add();
  }

  return (
    <div className="flex w-full flex-col gap-2.5">
      <Field id={id} label={`가진 자격증 (선택, ${MAX_CERTIFICATES}개까지)`} error={error}>
        <div className="flex w-full gap-2">
          <input
            type="text"
            {...fieldA11y(id, error)}
            value={draft}
            maxLength={CERTIFICATE_MAX_LENGTH}
            placeholder="예: 정보처리기사"
            disabled={full}
            onChange={(event) => {
              setDraft(event.target.value);
              if (error) setError(undefined);
            }}
            onKeyDown={onKeyDown}
            className={cn(
              "h-12 w-full rounded-field border bg-white px-3.75 text-body text-grey-900 placeholder:text-grey-500 focus:border-blue-500 focus:outline-none disabled:bg-grey-50",
              error ? "border-red-500" : "border-grey-300",
            )}
          />
          <Button type="button" variant="line" onClick={add} disabled={!draft.trim() || full} className="shrink-0">
            추가
          </Button>
        </div>
      </Field>
      {value.length > 0 && (
        <ul aria-label="넣은 자격증" className="flex flex-wrap gap-2">
          {value.map((name) => (
            <li
              key={name}
              className="inline-flex h-8.5 items-center gap-1 rounded-control border border-grey-300 bg-white pr-1.5 pl-3 text-small font-medium text-grey-800"
            >
              {name}
              <button
                type="button"
                onClick={() => onChange(value.filter((item) => item !== name))}
                aria-label={`${name} 빼기`}
                className="flex size-6 items-center justify-center rounded-full text-grey-500 hover:bg-grey-100 hover:text-grey-800"
              >
                <X aria-hidden className="size-3.5" strokeWidth={2.25} />
              </button>
            </li>
          ))}
        </ul>
      )}
      <p className="text-small text-grey-600">공고의 자격 요건·우대 조건과 맞춰 봐요. 자격증 이름을 그대로 적어 주세요.</p>
    </div>
  );
}
