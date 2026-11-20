import type { InputHTMLAttributes } from "react";
import { cn } from "@/lib/cn";
import { Field, fieldA11y } from "./Field";

type TextFieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, "id"> & {
  id: string;
  label: string;
  error?: string;
};

/** 한 줄 입력칸 (높이 48px, 모서리 10px). 목표 직무·희망 직무에서 쓴다. */
export function TextField({ id, label, error, className, ...rest }: TextFieldProps) {
  return (
    <Field id={id} label={label} error={error}>
      <input
        type="text"
        {...fieldA11y(id, error)}
        className={cn(
          "h-12 w-full rounded-field border bg-white px-3.75 text-body text-grey-900 placeholder:text-grey-500 focus:border-blue-500 focus:outline-none",
          error ? "border-red-500" : "border-grey-300",
          className,
        )}
        {...rest}
      />
    </Field>
  );
}
