import type { ReactNode } from "react";

type FieldProps = {
  id: string;
  label: string;
  error?: string;
  children: ReactNode;
};

/** 입력칸 위 라벨(Small M, grey-700)과 아래 오류 문구를 묶는다. */
export function Field({ id, label, error, children }: FieldProps) {
  return (
    <div className="flex w-full flex-col gap-2">
      <label htmlFor={id} className="text-small font-medium text-grey-700">
        {label}
      </label>
      {children}
      {error && (
        <p id={`${id}-error`} role="alert" className="text-small text-red-500">
          {error}
        </p>
      )}
    </div>
  );
}

/** `Field` 안의 입력 요소에 붙일 접근성 속성 */
export function fieldA11y(id: string, error?: string) {
  return {
    id,
    "aria-invalid": error ? true : undefined,
    "aria-describedby": error ? `${id}-error` : undefined,
  } as const;
}
