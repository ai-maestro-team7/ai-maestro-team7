import Link from "next/link";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";

export type ButtonVariant = "primary" | "secondary" | "line" | "text" | "textMuted";
export type ButtonSize = "L" | "M";

const base =
  "inline-flex shrink-0 items-center justify-center whitespace-nowrap transition-colors disabled:cursor-not-allowed disabled:opacity-40";

const variants: Record<ButtonVariant, string> = {
  primary: "bg-blue-500 text-white hover:brightness-95",
  secondary: "bg-grey-100 text-grey-800 hover:bg-grey-200",
  line: "border border-grey-300 bg-white text-grey-800 hover:bg-grey-50",
  // 배경 없는 텍스트 버튼 ("카메라 없이 계속", "면접 종료" 등)
  text: "text-grey-800 hover:text-grey-900",
  // 보조 텍스트 버튼 ("설정으로 돌아가기", "면접 종료")
  textMuted: "text-grey-700 hover:text-grey-900",
};

const sizes: Record<ButtonSize, string> = {
  L: "h-12 px-5 rounded-field text-btn font-bold",
  M: "h-9.5 px-3.5 rounded-control text-btn-s font-medium",
};

const textSizes: Record<ButtonSize, string> = {
  L: "h-12 text-body font-medium",
  M: "h-9.5 text-btn-s font-medium",
};

type CommonProps = {
  variant?: ButtonVariant;
  size?: ButtonSize;
  fullWidth?: boolean;
  className?: string;
  children: ReactNode;
};

type LinkButtonProps = CommonProps & { href: string };
type NativeButtonProps = CommonProps &
  Omit<ButtonHTMLAttributes<HTMLButtonElement>, "className" | "children"> & { href?: undefined };

/**
 * Figma Button(27:1350). Type(Primary/Secondary/Line) × Size(L 48px / M 38px).
 * `href`가 있으면 링크로, 없으면 `<button>`으로 렌더링한다.
 */
export function Button(props: LinkButtonProps | NativeButtonProps) {
  const { variant = "primary", size = "L", fullWidth, className, children } = props;
  const classes = cn(
    base,
    variant === "text" || variant === "textMuted" ? textSizes[size] : sizes[size],
    variants[variant],
    fullWidth && "w-full",
    className,
  );

  if (props.href !== undefined) {
    return (
      <Link href={props.href} className={classes}>
        {children}
      </Link>
    );
  }

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { variant: _v, size: _s, fullWidth: _f, className: _c, children: _ch, type = "button", ...rest } = props;
  return (
    <button type={type} className={classes} {...rest}>
      {children}
    </button>
  );
}
