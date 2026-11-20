import type { TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/cn";
import { Field, fieldA11y } from "./Field";

type TextAreaProps = Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "id" | "value"> & {
  id: string;
  label: string;
  value: string;
  error?: string;
  /** 글자 수 뒤에 붙일 말 (예: "· 예시") */
  counterSuffix?: string;
};

/** 글자 수가 오른쪽 아래에 보이는 여러 줄 입력칸 (자기소개서, 내 답변, 이력서 직접 입력). */
export function TextArea({ id, label, value, error, counterSuffix, rows = 2, className, ...rest }: TextAreaProps) {
  const count = value.length;
  return (
    <Field id={id} label={label} error={error}>
      <div
        className={cn(
          "flex w-full flex-col gap-2 rounded-field border bg-white px-3.75 pt-3.25 pb-3.5 focus-within:border-blue-500",
          error ? "border-red-500" : "border-grey-300",
          className,
        )}
      >
        <textarea
          {...fieldA11y(id, error)}
          value={value}
          rows={rows}
          className="w-full resize-none bg-transparent text-body text-grey-900 placeholder:text-grey-500 focus:outline-none"
          {...rest}
        />
        <p className="text-right text-small text-grey-500" aria-live="polite">
          {count}자{counterSuffix ? ` ${counterSuffix}` : ""}
        </p>
      </div>
    </Field>
  );
}
