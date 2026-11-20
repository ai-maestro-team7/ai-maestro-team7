import type { Ref } from "react";

/** 그림 크기 (px, viewBox와 1:1). 등장 계산(intro.ts)이 아래 두 점을 이 좌표로 안다 */
export const GULL_WIDTH = 180;
export const GULL_HEIGHT = 180;
/** 부리에 문 줄의 아래 끝 (문장이 매달리는 곳). 좁은 화면에서는 이 점을 축으로 그림이 작아진다 */
export const GULL_HOLD = { x: 158, y: 170 };
/** 몸 한가운데 (놓은 뒤 공중제비의 축) */
export const GULL_BODY = { x: 84, y: 78 };

const WING = "M 8 -10 C -6 -18, -32 -18, -49 -9 C -56 -5, -56 3, -49 6 C -45 8, -41 7, -38 10 C -34 14, -28 11, -25 14 C -19 19, -6 18, 8 11 C 14 6, 14 -5, 8 -10 Z";
const WING_TIP = "M -33 -14.5 C -39 -13, -44 -11.5, -49 -9 C -56 -5, -56 3, -49 6 C -45 8, -41 7, -38 10 C -36.5 11.5, -35 12, -33.5 12 C -37 4, -37 -6, -33 -14.5 Z";
const DROP = "M 0 0 C 4 6.5, 6 10.5, 3 13.5 C 0 15.6, -3.4 13.4, -2.8 9.6 C -2.4 6.4, -1.2 3.4, 0 0 Z";

/** 어깨를 원점으로 그린 날개 (끝이 검고 뒷전이 물결 모양). 퍼덕임은 바깥 묶음이 CSS로 돌린다 */
function Wing({ at, fill }: { at: string; fill: string }) {
  return (
    <g transform={`translate(${at}) scale(0.9)`}>
      <path className={fill} d={WING} />
      <path className="fill-grey-900" d={WING_TIP} />
      <path className="stroke-grey-900" d={WING} strokeWidth="3.3" />
    </g>
  );
}

/**
 * 홈 제목을 물고 오는 갈매기 (꾸밈). 이 서비스에서 새로 그린 마스코트다: 굵은 선, 동그란 머리와 통통한 몸, 끝이 검은 짧은 날개,
 * 주황 부리와 물갈퀴 발, 파란 목도리, 머리 위 삐친 깃. 부산시 캐릭터 "부기"는 시의 승인을 받아 쓰는 캐릭터라 따라 그리지 않는다
 * (빨간 안경·신발 같은 고유 요소도 쓰지 않는다).
 *
 * 나르는 동안(`data-phase="carry"`)에는 눈을 질끈 감고 땀을 흘리며 날개와 발을 바쁘게 젓는다.
 * 문장을 놓으면(`data-phase="free"`) 줄과 땀이 사라지고, 눈웃음을 지으며 부리를 벌린다. 날갯짓도 느긋해진다.
 * 움직임은 globals.css(`.gull-*`), 위치는 등장 코드가 준다. 처음에는 안 보인다.
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
      <svg
        viewBox={`0 0 ${GULL_WIDTH} ${GULL_HEIGHT}`}
        className="size-full overflow-visible max-sm:scale-[0.72]"
        style={{ transformOrigin: `${GULL_HOLD.x}px ${GULL_HOLD.y}px` }}
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {/* 문장을 매단 줄 */}
        <path className="gull-string stroke-grey-600" d="M 152 67 C 153 100, 156 140, 158 170" strokeWidth="1.8" />

        {/* 뒤쪽 날개 */}
        <g className="gull-wing gull-wing-far">
          <Wing at="81 69" fill="fill-grey-100" />
        </g>

        {/* 물갈퀴 발: 허공을 젓는다 */}
        <path
          className="gull-leg gull-leg-far fill-orange-500 stroke-grey-900"
          d="M 83.5 109 L 89.5 110 L 88.5 122 L 84.5 132 L 78.5 129.5 L 74 132.5 L 71 125 L 82.5 121 Z"
          strokeWidth="2.4"
        />
        <path
          className="gull-leg fill-orange-500 stroke-grey-900"
          d="M 65.5 110 L 71.5 111 L 70.5 123 L 66.5 133 L 60.5 130.5 L 56 133.5 L 53 126 L 64.5 122 Z"
          strokeWidth="2.4"
        />

        {/* 꼬리와 몸 */}
        <path
          className="fill-white stroke-grey-900"
          d="M 38 78 L 15 70 C 12 74, 13 79, 17 82 C 11 85, 11 91, 15 94 C 10 98, 11 103, 16 105 L 40 99 Z"
          strokeWidth="3"
        />
        <ellipse className="fill-white" cx="76" cy="84" rx="46" ry="33" transform="rotate(-8 76 84)" />
        <path className="fill-grey-100" d="M 38 96 C 50 112, 86 118, 114 102 C 92 108, 60 108, 38 96 Z" />
        <ellipse className="stroke-grey-900" cx="76" cy="84" rx="46" ry="33" transform="rotate(-8 76 84)" strokeWidth="3" />

        {/* 목도리 자락: 목 뒤 매듭에서 뒤로 나부낀다 */}
        <g className="gull-scarf fill-blue-500 stroke-grey-900" strokeWidth="2.6">
          <path d="M 90 52 C 80 52, 70 54, 60 60 L 66 62 L 62 68 C 72 62, 82 60, 91 59 Z" />
          <path d="M 91 47 C 80 40, 68 34, 54 34 L 59 41 L 52 46 C 66 46, 78 50, 88 56 Z" />
        </g>

        {/* 머리, 머리 위 삐친 깃 */}
        <path className="stroke-grey-900" d="M 110 31.5 C 108 24, 102 21, 97 23.5 M 116 30.2 C 116 22, 110 17, 104 17.5" strokeWidth="3" />
        <circle className="fill-white stroke-grey-900" cx="118" cy="57" r="27" strokeWidth="3" />

        {/* 목도리: 머리 아래를 감싼 띠와 매듭 */}
        <path
          className="fill-blue-500 stroke-grey-900"
          d="M 124.9 89.3 A 33 33 0 0 1 86.1 48.5 L 96.7 51.3 A 22 22 0 0 0 122.6 78.5 Z"
          strokeWidth="2.6"
        />
        <path className="stroke-white" d="M 120.4 84.4 A 27.5 27.5 0 0 1 90.8 53.2" strokeWidth="2" opacity="0.5" />
        <circle className="fill-blue-500 stroke-grey-900" cx="90" cy="50.5" r="5.6" strokeWidth="2.6" />

        {/* 얼굴: 볼, 눈(힘줄 때 > <, 놓은 뒤 눈웃음), 부리 */}
        <ellipse className="fill-red-500" cx="115" cy="65" rx="6" ry="3.6" opacity="0.28" />
        <g className="gull-eyes-strain stroke-grey-900" strokeWidth="3">
          <path d="M 112 45.5 L 121.5 51 L 112 56.5" />
          <path d="M 138.5 41.5 L 132 45.5 L 138.5 49.5" />
          <path d="M 109.5 41 L 119.5 38.2" strokeWidth="2.4" />
        </g>
        <g className="gull-eyes-happy stroke-grey-900" strokeWidth="3">
          <path d="M 111.5 53.5 C 113.5 47, 120 47, 122 53.5" />
          <path d="M 130.5 49 C 132 43.5, 137 43.5, 138.5 49" />
        </g>
        <path className="gull-mouth fill-red-500" d="M 133 66.6 L 153 67.2 L 150.5 74 Z" />
        <path
          className="gull-beak-lower fill-orange-500 stroke-grey-900"
          d="M 132 66 L 152 68 C 149 73.5, 140 75, 133 72.5 Z"
          strokeWidth="2.4"
        />
        <path
          className="fill-orange-500 stroke-grey-900"
          d="M 132.5 56 C 143 53, 156 57, 164 65.5 C 155 68, 143 68, 132.5 66.5 Z"
          strokeWidth="2.4"
        />

        {/* 앞쪽 날개 */}
        <g className="gull-wing">
          <Wing at="73 76" fill="fill-white" />
        </g>

        {/* 힘들어서 튀는 땀방울 */}
        <g className="gull-sweat fill-blue-500">
          <path d={DROP} transform="translate(141 6)" />
          <path d={DROP} transform="translate(155 22) scale(0.75)" />
          <path d={DROP} transform="translate(93 4) scale(0.85)" />
        </g>
      </svg>
    </div>
  );
}
