import { GULL_HOLD } from "./components/Seagull";

/**
 * 홈 제목 등장: 갈매기가 문장을 물고 왼쪽 위에서 날아와, 제목 자리 위에서 떨어뜨리고 오른쪽 위로 날아간다.
 *
 * - 나르는 동안: 문장은 부리에 문 줄 끝(맨 뒤 글자 "?")에 매달려 뒤로 처진다. 무거워서 가운데쯤 가라앉았다가
 *   버둥대며 다시 올라오고, 날갯짓에 맞춰 위아래로 출렁인다.
 * - 떨어뜨리면: 글자들이 각자 자기 높이에서 떨어져 제자리에 착지하며 눌렸다 튀어 오른다. 갈매기는 가벼워져 휙 솟아 날아간다.
 *
 * 글자의 제자리는 화면에서 직접 재고, 움직임은 Web Animations API로 준다 (끝나면 값이 남지 않아 커서 물결이 그대로 먹는다).
 * 돌려주는 함수를 부르면 멈추고 글자를 제자리에 둔다.
 */

const CARRY_MS = 3200; // 물고 오는 시간 (버겁게, 느리게)
const AWAY_MS = 1500; // 떨어뜨린 뒤 날아가는 시간
const SAMPLES = 64;
const DROP_HEIGHT = 150; // 줄 끝이 제목 위로 얼마나 높이 있을 때 놓는지 (px)
const GRAVITY = 1700; // px/s²
const LAND_MS = 420;
const BEATS = 3.4; // 나르는 동안 위아래로 출렁이는 횟수

type Point = { x: number; y: number };

const smooth = (t: number) => {
  const c = Math.min(1, Math.max(0, t));
  return c * c * (3 - 2 * c);
};

/** 줄 끝(문장이 매달린 점)의 위치와 문장이 처진 각도, 갈매기 기울기. tau는 0(출발)~1(놓는 순간) */
function carryPose(tau: number, start: Point, drop: Point) {
  const progress = 1 - (1 - tau) ** 1.5; // 갈수록 느려진다
  const sink = 38 * Math.sin(Math.PI * tau) ** 1.4; // 무거워서 가운데쯤 가라앉는다
  const bob = 11 * Math.sin(2 * Math.PI * BEATS * tau) * (0.55 + 0.45 * tau);
  const heave = -16 * smooth((tau - 0.86) / 0.14); // 놓기 직전에 한 번 끌어올린다
  const sway = 5 * Math.sin(2 * Math.PI * BEATS * tau - 1.1) * (1 - 0.5 * tau);
  return {
    hold: { x: start.x + (drop.x - start.x) * progress, y: start.y + (drop.y - start.y) * progress + sink + bob + heave },
    sag: -15 + 9 * smooth((tau - 0.72) / 0.28) + sway, // 음수 = 뒤쪽(왼쪽) 끝이 아래로
    pitch: -7 + 8 * Math.cos(2 * Math.PI * BEATS * tau) - 6 * smooth((tau - 0.86) / 0.14),
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

  const drop: Point = { x: anchor.x + 14, y: anchor.y - DROP_HEIGHT };
  const start: Point = { x: -190, y: drop.y - 26 };
  const away: Point = { x: stageBox.width + 220, y: drop.y - 150 };

  const poses = Array.from({ length: SAMPLES + 1 }, (_, k) => carryPose(k / SAMPLES, start, drop));
  const animations: Animation[] = [];
  const timers: number[] = [];
  let finished = false;

  // 갈매기: 줄 끝이 hold를 지나게 옮기고, 줄 끝을 축으로 기울인다. 놓은 뒤에는 휙 솟아 오른쪽 위로 간다
  bird.style.transformOrigin = `${GULL_HOLD.x}px ${GULL_HOLD.y}px`;
  const birdAt = (point: Point, pitch: number) =>
    `translate(${(point.x - GULL_HOLD.x).toFixed(1)}px, ${(point.y - GULL_HOLD.y).toFixed(1)}px) rotate(${pitch.toFixed(1)}deg)`;
  const total = CARRY_MS + AWAY_MS;
  const birdFrames: Keyframe[] = poses.map((pose, k) => ({
    transform: birdAt(pose.hold, pose.pitch),
    opacity: 1,
    offset: ((k / SAMPLES) * CARRY_MS) / total,
  }));
  const last = poses[SAMPLES];
  const AWAY_STEPS = 16;
  for (let k = 1; k <= AWAY_STEPS; k += 1) {
    const s = k / AWAY_STEPS;
    const go = s * s * (0.6 + 0.4 * s); // 점점 빨라진다
    const point = {
      x: last.hold.x + (away.x - last.hold.x) * go,
      y: last.hold.y + (away.y - last.hold.y) * go - 34 * Math.sin(Math.PI * Math.min(1, s * 2.2)) * (1 - s),
    };
    birdFrames.push({ transform: birdAt(point, last.pitch - 12 * smooth(s * 3)), opacity: 1, offset: (CARRY_MS + s * AWAY_MS) / total });
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
    animations.push(char.animate(frames, { duration, easing: "linear", fill: "backwards" }));
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
