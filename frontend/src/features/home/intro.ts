import { GULL_BODY, GULL_HOLD } from "./components/Seagull";

/**
 * 홈 제목 등장: 갈매기가 문장을 물고 왼쪽 위에서 날아와, 제목 자리 위에서 떨어뜨리고 오른쪽 위로 날아간다.
 *
 * - 나르는 동안: 문장은 부리에 문 줄 끝(맨 뒤 글자 "?")에 매달려 뒤로 처진다. 무거워서 두 번 휘청하며 뚝 떨어졌다가
 *   버둥대며 겨우 올라오고, 날갯짓에 맞춰 위아래로 출렁인다. 휘청할 때는 코가 아래로 쏠리고 문장이 앞으로 쏠린다.
 * - 떨어뜨리면: 글자들이 각자 자기 높이에서 떨어져 제자리에 착지하며 눌렸다 튀어 오른다. 갈매기는 가벼워져
 *   튀어 오르며 공중제비를 한 바퀴 돌고, 오른쪽 위로 휙 날아간다. 글자가 다 내려앉으면 `hero:title-landed`를 알린다
 *   (배경의 불꽃이 이때 터진다).
 *
 * 글자의 제자리는 화면에서 직접 재고, 움직임은 Web Animations API로 준다 (끝나면 값이 남지 않아 커서 물결이 그대로 먹는다).
 * 돌려주는 함수를 부르면 멈추고 글자를 제자리에 둔다.
 */

const CARRY_MS = 3400; // 물고 오는 시간 (버겁게, 느리게)
const AWAY_MS = 1700; // 떨어뜨린 뒤 한 바퀴 돌고 날아가는 시간
const SAMPLES = 96;
const DROP_HEIGHT = 130; // 줄 끝이 제목 위로 얼마나 높이 있을 때 놓는지 (px)
const GRAVITY = 1700; // px/s²
const LAND_MS = 420;
const BEATS = 5.5; // 나르는 동안 위아래로 출렁이는 횟수
const STUMBLES = [0.3, 0.6]; // 휘청하며 뚝 떨어지는 때 (tau)
const STUMBLE_SPAN = 0.2;
/** 글자가 다 내려앉았을 때 window에 알리는 이벤트 이름 */
export const TITLE_LANDED = "hero:title-landed";

type Point = { x: number; y: number };

const smooth = (t: number) => {
  const c = Math.min(1, Math.max(0, t));
  return c * c * (3 - 2 * c);
};

/** 휘청: 순식간에 떨어졌다가(앞 25%) 버둥대며 천천히 올라온다. 0~1 */
function stumble(tau: number): number {
  let total = 0;
  for (const at of STUMBLES) {
    const u = (tau - at) / STUMBLE_SPAN;
    if (u <= 0 || u >= 1) continue;
    total += u < 0.25 ? (u / 0.25) ** 2 : ((1 - u) / 0.75) ** 1.6;
  }
  return total;
}

/** 줄 끝(문장이 매달린 점)의 위치와 문장이 처진 각도, 갈매기 기울기. tau는 0(출발)~1(놓는 순간) */
function carryPose(tau: number, start: Point, drop: Point) {
  const fall = stumble(tau);
  const falling = stumble(tau + 0.012) - fall; // 양수면 떨어지는 중, 음수면 올라오는 중
  const progress = 1 - (1 - tau) ** 1.4 - 0.022 * fall; // 갈수록 느려지고, 휘청할 때는 뒤로 밀린다
  const sink = 26 * Math.sin(Math.PI * tau) ** 1.4; // 무거워서 가운데쯤 가라앉는다
  const bob = 10 * Math.sin(2 * Math.PI * BEATS * tau) * (0.6 + 0.4 * tau);
  const heave = -20 * smooth((tau - 0.86) / 0.14); // 놓기 직전에 한 번 끌어올린다
  const sway = 6 * Math.sin(2 * Math.PI * BEATS * 0.5 * tau - 1.1) * (1 - 0.4 * tau);
  return {
    hold: { x: start.x + (drop.x - start.x) * progress, y: start.y + (drop.y - start.y) * progress + sink + bob + heave + 54 * fall },
    sag: -15 + 9 * smooth((tau - 0.72) / 0.28) + sway + 12 * fall, // 음수 = 뒤쪽(왼쪽) 끝이 아래로. 휘청하면 문장이 앞으로 쏠린다
    // 코가 떨어질 때는 아래로, 올라올 때는 위로 들린다
    pitch: -4 + 6 * Math.cos(2 * Math.PI * BEATS * tau) + (falling > 0 ? 22 : -10) * Math.min(1, fall * 1.6) - 6 * smooth((tau - 0.86) / 0.14),
  };
}

const LAND_FRAMES: Keyframe[] = [
  { transform: "scale(1.14, 0.84)" },
  { transform: "translateY(-3px) scale(0.94, 1.08)", offset: 0.45 },
  { transform: "scale(1.03, 0.97)", offset: 0.75 },
  { transform: "none" },
];

export function playSeagullIntro(bird: HTMLElement, title: HTMLElement): () => void {
  const stage = bird.offsetParent as HTMLElement | null;
  const chars = [...title.querySelectorAll<HTMLElement>(".wave-char")];
  if (!stage || chars.length === 0) {
    title.dataset.intro = "done";
    return () => {};
  }

  const stageBox = stage.getBoundingClientRect();
  const centers = chars.map((char) => {
    const box = char.getBoundingClientRect();
    return { x: box.left + box.width / 2 - stageBox.left, y: box.top + box.height / 2 - stageBox.top, height: box.height };
  });
  const anchor = centers[centers.length - 1]; // 맨 뒤 글자 "?"가 줄 끝에 매달린다
  const hang = anchor.height * 0.3; // 줄 끝에서 글자 가운데까지 (글자 윗부분이 줄 끝에 닿게)

  // 좁은 화면에서는 갈매기 그림이 줄 끝을 축으로 작아진다 (Seagull의 scale). 거리도 그만큼 줄인다
  const scale = Number.parseFloat(getComputedStyle(bird.firstElementChild ?? bird).scale) || 1;
  const drop: Point = { x: anchor.x + 14 * scale, y: anchor.y - DROP_HEIGHT * scale };
  const start: Point = { x: -200 * scale, y: drop.y - 26 * scale };

  const poses = Array.from({ length: SAMPLES + 1 }, (_, k) => carryPose(k / SAMPLES, start, drop));
  const animations: Animation[] = [];
  const timers: number[] = [];
  let finished = false;

  // 갈매기: 줄 끝이 hold를 지나게 옮기고, 줄 끝을 축으로 기울인다
  bird.style.transformOrigin = `${GULL_HOLD.x}px ${GULL_HOLD.y}px`;
  const birdAt = (point: Point, pitch: number) =>
    `translate(${(point.x - GULL_HOLD.x).toFixed(1)}px, ${(point.y - GULL_HOLD.y).toFixed(1)}px) rotate(${pitch.toFixed(1)}deg)`;
  // 줄 끝에서 몸 한가운데까지. 놓은 뒤에는 몸 한가운데가 길을 따라가고, 몸을 축으로 돈다
  const arm = { x: (GULL_BODY.x - GULL_HOLD.x) * scale, y: (GULL_BODY.y - GULL_HOLD.y) * scale };
  const bodyOffset = (pitch: number): Point => {
    const angle = (pitch * Math.PI) / 180;
    return { x: arm.x * Math.cos(angle) - arm.y * Math.sin(angle), y: arm.x * Math.sin(angle) + arm.y * Math.cos(angle) };
  };
  const total = CARRY_MS + AWAY_MS;
  const birdFrames: Keyframe[] = poses.map((pose, k) => ({
    transform: birdAt(pose.hold, pose.pitch),
    opacity: 1,
    offset: ((k / SAMPLES) * CARRY_MS) / total,
  }));
  const last = poses[SAMPLES];
  const AWAY_STEPS = 48;
  const LOOP = 0.44; // 앞부분: 가벼워져 튀어 오르며 공중제비를 한 바퀴 돈다
  const lastOffset = bodyOffset(last.pitch);
  const released: Point = { x: last.hold.x + lastOffset.x, y: last.hold.y + lastOffset.y }; // 놓는 순간 몸 한가운데
  const away: Point = { x: stageBox.width + 240 * scale, y: released.y - 190 * scale };
  for (let k = 1; k <= AWAY_STEPS; k += 1) {
    const s = k / AWAY_STEPS;
    const hop = Math.sin(Math.PI * Math.min(1, s / LOOP)); // 튀어 올랐다 내려오는 높이
    const go = s < LOOP ? 0.05 * (s / LOOP) : 0.05 + 0.95 * ((s - LOOP) / (1 - LOOP)) ** 2.2; // 돌고 난 뒤 휙 빨라진다
    const pitch = last.pitch - 360 * smooth(s / LOOP) - 16 * smooth((s - LOOP) / 0.2); // 뒤로 한 바퀴, 그다음 코를 들고 간다
    const offset = bodyOffset(pitch);
    const point = {
      x: released.x + (away.x - released.x) * go - offset.x,
      y: released.y + (away.y - released.y) * go - 62 * scale * hop - offset.y,
    };
    birdFrames.push({ transform: birdAt(point, pitch), opacity: 1, offset: (CARRY_MS + s * AWAY_MS) / total });
  }
  const flight = bird.animate(birdFrames, { duration: total, easing: "linear" });
  animations.push(flight);
  // 놓는 순간을 비행 시간에 맞춘다 (탭이 쉬거나 느려져도 줄·땀방울·날갯짓이 비행과 어긋나지 않게)
  let watching = 0;
  const watch = () => {
    const now = Number(flight.currentTime ?? 0);
    bird.dataset.phase = now >= CARRY_MS ? "free" : "carry";
    if (flight.playState !== "finished" && flight.playState !== "idle") watching = requestAnimationFrame(watch);
  };
  watching = requestAnimationFrame(watch);

  // 글자: 줄 끝에 매달려 따라오다가, 놓는 순간부터 각자 떨어진다
  let longest = 0;
  chars.forEach((char, index) => {
    const home = centers[index];
    const reach = home.x - anchor.x; // 줄 끝에서 이 글자까지 (왼쪽이라 음수)
    const at = (pose: (typeof poses)[number]) => {
      const angle = (pose.sag * Math.PI) / 180;
      const x = pose.hold.x + reach * Math.cos(angle);
      const y = pose.hold.y + hang + reach * Math.sin(angle);
      return { dx: x - home.x, dy: y - home.y, sag: pose.sag };
    };
    const end = at(last);
    const fallMs = Math.min(560, Math.max(260, Math.sqrt((2 * Math.max(20, -end.dy)) / GRAVITY) * 1000));
    const pause = ((index * 37) % 5) * 16; // 놓인 뒤 잠깐 멈칫하는 시간을 글자마다 조금씩 다르게
    const duration = CARRY_MS + pause + fallMs;
    const frames: Keyframe[] = poses.map((pose, k) => {
      const p = at(pose);
      return {
        transform: `translate(${p.dx.toFixed(1)}px, ${p.dy.toFixed(1)}px) rotate(${p.sag.toFixed(1)}deg)`,
        offset: ((k / SAMPLES) * CARRY_MS) / duration,
      };
    });
    const hanging = `translate(${end.dx.toFixed(1)}px, ${end.dy.toFixed(1)}px) rotate(${end.sag.toFixed(1)}deg)`;
    // 떨어지는 구간만 점점 빨라지게 한다
    frames.push({ transform: hanging, offset: (CARRY_MS + pause) / duration, easing: "cubic-bezier(0.5, 0, 0.9, 0.5)" });
    frames.push({ transform: "translate(0px, 0px) rotate(0deg)" });
    const fall = char.animate(frames, { duration, easing: "linear", fill: "backwards" });
    animations.push(fall);
    if (index === chars.length - 1) {
      // 멈추면(cancel) 약속이 깨지므로 그때는 알리지 않는다
      fall.finished.then(() => window.dispatchEvent(new CustomEvent(TITLE_LANDED))).catch(() => {});
    }
    const hop = char.querySelector<HTMLElement>(".wave-hop");
    if (hop) {
      // fill을 주지 않는다. 착지 전에는 눌린 모양이 보이면 안 된다
      animations.push(hop.animate(LAND_FRAMES, { duration: LAND_MS, delay: duration, easing: "cubic-bezier(0.3, 1.5, 0.5, 1)" }));
    }
    longest = Math.max(longest, duration + LAND_MS);
  });

  title.dataset.intro = "playing";
  timers.push(
    window.setTimeout(
      () => {
        finished = true;
        title.dataset.intro = "done";
      },
      Math.max(longest, total) + 80,
    ),
  );

  return () => {
    cancelAnimationFrame(watching);
    for (const timer of timers) window.clearTimeout(timer);
    for (const animation of animations) animation.cancel();
    if (!finished) title.dataset.intro = "done";
  };
}
