import { cn } from "@/lib/cn";

export type RadioOption<T extends string> = {
  value: T;
  label: string;
  /** 라벨 옆 파란 강조 글 (예: "추천") */
  badge?: string;
  description: string;
};

type RadioListProps<T extends string> = {
  name: string;
  legend: string;
  options: RadioOption<T>[];
  value: T;
  onChange: (value: T) => void;
};

/** 테두리 상자 안에 세로로 쌓인 라디오 목록. 선택한 줄은 blue-50 배경. (모의면접 진행 방식) */
export function RadioList<T extends string>({ name, legend, options, value, onChange }: RadioListProps<T>) {
  return (
    <fieldset className="flex w-full flex-col">
      <legend className="mb-2 text-small font-medium text-grey-700">{legend}</legend>
      <div className="flex w-full flex-col overflow-hidden rounded-field border border-grey-300">
        {options.map((option, index) => {
          const selected = option.value === value;
          return (
            <label
              key={option.value}
              className={cn(
                "flex cursor-pointer items-center gap-3 px-4 py-3.5",
                index < options.length - 1 && "border-b border-grey-200",
                selected && "bg-blue-50",
              )}
            >
              <input
                type="radio"
                name={name}
                value={option.value}
                checked={selected}
                onChange={() => onChange(option.value)}
                className="peer sr-only"
              />
              <span
                aria-hidden
                className={cn(
                  "size-5 shrink-0 rounded-full bg-white peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-blue-500",
                  selected ? "border-6 border-blue-500" : "border-[1.5px] border-grey-400",
                )}
              />
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="flex items-center gap-1.5">
                  <span className="text-body font-bold text-grey-900">{option.label}</span>
                  {option.badge && <span className="text-small font-bold text-blue-500">{option.badge}</span>}
                </span>
                <span className="text-small text-grey-600">{option.description}</span>
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
