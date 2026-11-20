import type { Ref } from "react";

/** 그림 크기 (px). 등장 계산(intro.ts)이 줄 끝 위치를 이 값으로 안다 */
export const GULL_WIDTH = 132;
export const GULL_HEIGHT = 110;
/** 부리에 문 줄의 아래 끝 (문장이 매달리는 곳). viewBox 120×100 기준 (114, 94)를 px로 바꾼 값 */
export const GULL_HOLD = { x: (114 / 120) * GULL_WIDTH, y: (94 / 100) * GULL_HEIGHT };

/**
 * 홈 제목을 물고 오는 갈매기 (꾸밈). 오른쪽을 보고 날고, 날개 두 장이 어깨를 축으로 퍼덕인다 (globals.css `.gull-wing`).
 * 부리에 문 줄 끝에 문장이 매달린다. 문장을 떨어뜨리면(`data-phase="free"`) 줄과 땀방울이 사라지고 날갯짓이 느긋해진다.
 * 위치는 등장 코드가 움직인다. 처음에는 안 보인다.
 */
export function Seagull({ ref }: { ref: Ref<HTMLDivElement> }) {
  return (
    <div
      ref={ref}
      aria-hidden
      data-phase="carry"
      className="gull pointer-events-none absolute top-0 left-0 z-10 opacity-0"
      style={{ width: GULL_WIDTH, height: GULL_HEIGHT }}
    >
      <svg viewBox="0 0 120 100" className="size-full overflow-visible" fill="none">
        {/* 문장을 매단 줄 */}
        <path className="gull-string stroke-grey-500" d="M118 43 C 117 60, 115 78, 114 94" strokeWidth="1.2" strokeLinecap="round" />
        {/* 뒤쪽 날개 */}
        <g className="gull-wing gull-wing-far">
          <path className="fill-grey-300" d="M70 44 C 62 28, 50 12, 30 3 C 40 18, 48 32, 56 49 Z" />
          <path className="fill-grey-800" d="M30 3 C 37 9, 43 16, 47 23 L 40 19 C 37 13, 34 8, 30 3 Z" />
        </g>
        {/* 꼬리, 몸, 머리 */}
        <path className="fill-grey-100 stroke-grey-300" d="M32 49 L 9 43 L 15 51 L 9 59 L 32 55 Z" strokeWidth="1" strokeLinejoin="round" />
        <path
          className="fill-white stroke-grey-300"
          d="M29 51 C 37 39, 66 35, 88 39 C 98 41, 104 45, 104 49 C 100 57, 72 63, 45 59 C 37 58, 31 55, 29 51 Z"
          strokeWidth="1"
        />
        <path className="fill-grey-100" d="M40 56 C 56 61, 82 58, 100 51 C 96 57, 72 63, 45 59 Z" />
        <circle className="fill-white stroke-grey-300" cx="98" cy="41" r="9.5" strokeWidth="1" />
        <circle className="fill-grey-900" cx="101.5" cy="39" r="1.7" />
        {/* 부리 */}
        <path className="fill-orange-500" d="M106.5 40.5 L 119 43 L 106.5 46 Z" strokeLinejoin="round" />
        {/* 앞쪽 날개 */}
        <g className="gull-wing">
          <path className="fill-grey-200 stroke-grey-300" d="M68 46 C 60 29, 46 11, 22 0 C 33 17, 42 33, 52 52 Z" strokeWidth="0.8" strokeLinejoin="round" />
          <path className="fill-grey-900" d="M22 0 C 30 7, 37 15, 42 23 L 34 18 C 31 12, 27 6, 22 0 Z" />
        </g>
        {/* 힘들어서 튀는 땀방울 */}
        <g className="gull-sweat fill-blue-500">
          <path d="M86 17 C 89 21.5, 90.6 24.6, 88.4 26.8 C 86.2 28.4, 83.6 26.8, 84 24 C 84.3 21.6, 85.2 19.4, 86 17 Z" />
          <path d="M77 9 C 79 12.2, 80 14.4, 78.5 15.9 C 77 17, 75.2 15.8, 75.5 13.8 C 75.8 12, 76.4 10.5, 77 9 Z" opacity="0.7" />
        </g>
      </svg>
    </div>
  );
}
