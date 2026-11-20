import { TITLE_LANDED } from "./intro";

/**
 * 홈 배경 하늘의 불꽃 (2D 캔버스, 꾸밈). 광안리 불꽃축제에서 따왔다. 색은 디자인 토큰에서만 읽는다.
 *
 * - 제목이 내려앉으면(`hero:title-landed`) 양옆에서 잇달아 터지고, 그 뒤로는 가끔 한 발씩 올라간다.
 * - 빈 곳을 누르면 그 자리에서 한 발 터진다.
 * - 글과 입력칸이 있는 가운데는 비워 둔다. 양옆에 자리가 없으면(좁은 화면) 글 위쪽 하늘에서만 터진다.
 *
 * 캔버스는 3D 장면 아래에 깔려서, 불꽃이 다리와 바다 뒤 하늘에서 올라오는 것처럼 보인다.
 * 움직임 줄이기 설정이면 아무것도 하지 않는다. 돌려주는 함수를 부르면 멈추고 정리한다.
 */

const RISE = 0.55; // 쏘아 올리는 시간 (초)
const LIFE = 1.7; // 터진 뒤 사라질 때까지 (초)
const HORIZON = 0.9; // 쏘아 올리는 높이 (화면 높이에 대한 비율). 바다 뒤에서 올라온다

type Zone = { x0: number; x1: number; y0: number; y1: number; radius: number };
type Burst = { x: number; y: number; from: number; start: number; radius: number; sparks: number; colors: [string, string]; seed: number };

function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(`--color-${name}`).trim();
}

/** 0~1 난수 (씨앗이 같으면 늘 같은 값). 불꽃 한 발의 모양을 프레임마다 똑같이 다시 그리려고 쓴다 */
const noise = (seed: number, index: number) => {
  const value = Math.sin(seed * 12.9898 + index * 78.233) * 43758.5453;
  return value - Math.floor(value);
};

export function mountFireworks(host: HTMLElement): () => void {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return () => {};
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d");
  if (!context) return () => {};
  canvas.style.width = "100%";
  canvas.style.height = "100%";
  canvas.style.display = "block";
  host.appendChild(canvas);

  const palette: [string, string][] = [
    [token("blue-500"), token("orange-500")],
    [token("orange-500"), token("red-500")],
    [token("blue-500"), token("green-500")],
    [token("red-500"), token("orange-500")],
    [token("blue-500"), token("blue-500")],
  ];
  const stage = host.closest("main");
  let width = 0;
  let height = 0;
  let ratio = 1;
  function resize() {
    width = host.clientWidth;
    height = host.clientHeight;
    ratio = Math.min(window.devicePixelRatio, 2);
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
  }

  /** 글·입력칸·버튼이 차지한 자리 (host 기준). 여기서는 터뜨리지 않는다 */
  function content(): DOMRect | null {
    const items = stage?.querySelectorAll("section h1, section p, section form, section button, section a") ?? [];
    const origin = host.getBoundingClientRect();
    let left = Infinity;
    let top = Infinity;
    let right = -Infinity;
    let bottom = -Infinity;
    for (const item of items) {
      const box = item.getBoundingClientRect();
      if (!box.width || !box.height) continue;
      left = Math.min(left, box.left - origin.left);
      top = Math.min(top, box.top - origin.top);
      right = Math.max(right, box.right - origin.left);
      bottom = Math.max(bottom, box.bottom - origin.top);
    }
    return Number.isFinite(left) ? new DOMRect(left, top, right - left, bottom - top) : null;
  }

  /** 불꽃이 터져도 되는 하늘: 글 양옆. 좁은 화면이면 글 위쪽 */
  function zones(): Zone[] {
    const keep = content();
    if (!keep) return [];
    const gutter = Math.min(keep.left, width - keep.right);
    if (gutter >= 190) {
      const radius = Math.min(125, Math.max(70, gutter * 0.3));
      const y0 = height * 0.12;
      const y1 = height * 0.5;
      return [
        { x0: radius * 0.8, x1: keep.left - radius * 0.75, y0, y1, radius },
        { x0: keep.right + radius * 0.75, x1: width - radius * 0.8, y0, y1, radius },
      ];
    }
    if (keep.top >= 130) {
      // 불티가 처져도 글에 닿지 않게 작게, 위쪽에 붙여서 터뜨린다
      const radius = Math.min(54, keep.top * 0.3);
      const y0 = radius + 6;
      const y1 = Math.max(y0, keep.top - radius * 1.5 - 12);
      return [
        { x0: radius, x1: width * 0.42, y0, y1, radius },
        { x0: width * 0.58, x1: width - radius, y0, y1, radius },
      ];
    }
    return [];
  }

  let bursts: Burst[] = [];
  let count = 0;
  let frame = 0;
  const now = () => performance.now() / 1000;

  function add(x: number, y: number, radius: number, delay = 0) {
    count += 1;
    bursts.push({
      x,
      y,
      from: Math.max(y + 120, height * HORIZON),
      start: now() + delay,
      radius,
      sparks: radius > 90 ? 54 : 40,
      colors: palette[count % palette.length],
      seed: count * 7.31,
    });
    if (!frame) frame = requestAnimationFrame(draw);
  }

  /** 정해진 하늘 한쪽(side: 0 왼쪽, 1 오른쪽)에 한 발 */
  function launch(side: number, delay = 0) {
    const all = zones();
    if (all.length === 0) return;
    const zone = all[side % all.length];
    const pick = (salt: number) => noise(count + 1, salt);
    const radius = zone.radius * (0.78 + 0.34 * pick(1));
    add(zone.x0 + (zone.x1 - zone.x0) * pick(2), zone.y0 + (zone.y1 - zone.y0) * pick(3), radius, delay);
  }

  function drawBurst(burst: Burst, time: number) {
    if (!context) return;
    const since = time - burst.start;
    if (since < 0) return;
    const [main, second] = burst.colors;
    context.lineCap = "round";
    if (since < RISE) {
      // 쏘아 올리기: 점점 느려지며 올라가고, 뒤로 가는 꼬리가 남는다
      const progress = 1 - (1 - since / RISE) ** 3;
      const y = burst.from + (burst.y - burst.from) * progress;
      const tail = 56 * (1 - progress) + 6;
      const sway = Math.sin(since * 22 + burst.seed) * 1.6;
      const gradient = context.createLinearGradient(0, y, 0, y + tail);
      gradient.addColorStop(0, main);
      gradient.addColorStop(1, "transparent");
      context.globalAlpha = 0.75;
      context.strokeStyle = gradient;
      context.lineWidth = 2.2;
      context.beginPath();
      context.moveTo(burst.x + sway, y);
      context.lineTo(burst.x, y + tail);
      context.stroke();
      return;
    }
    const age = since - RISE;
    const life = age / LIFE;
    if (life >= 1) return;
    // 터지는 순간의 둥근 번쩍임
    if (age < 0.24) {
      context.globalAlpha = 0.45 * (1 - age / 0.24);
      context.strokeStyle = main;
      context.lineWidth = 2;
      context.beginPath();
      context.arc(burst.x, burst.y, burst.radius * 0.3 * (age / 0.24), 0, Math.PI * 2);
      context.stroke();
    }
    // 불티: 바깥 고리와 안쪽 고리. 빠르게 퍼졌다가 느려지며 아래로 처진다
    const at = (index: number, when: number) => {
      const inner = index % 3 === 2;
      const angle = (index / burst.sparks) * Math.PI * 2 + (noise(burst.seed, index) - 0.5) * 0.22;
      const reach = burst.radius * (inner ? 0.56 : 0.9 + 0.2 * noise(burst.seed, index + 99)) * (1 - Math.exp(-3.4 * when));
      return { x: burst.x + Math.cos(angle) * reach, y: burst.y + Math.sin(angle) * reach + 16 * when * when };
    };
    const fade = (1 - life) ** 1.5;
    for (let index = 0; index < burst.sparks; index += 1) {
      const head = at(index, age);
      const tail = at(index, Math.max(0, age - 0.13));
      // 끝나갈 무렵에는 불티마다 따로 깜박인다
      const twinkle = life > 0.5 ? 0.45 + 0.55 * Math.abs(Math.sin(age * 19 + index * 2.4)) : 1;
      context.globalAlpha = fade * twinkle;
      context.strokeStyle = index % 3 === 2 ? second : main;
      context.lineWidth = 0.9 + 1.8 * (1 - life);
      context.beginPath();
      context.moveTo(tail.x, tail.y);
      context.lineTo(head.x, head.y);
      context.stroke();
    }
  }

  function draw() {
    frame = 0;
    if (!context) return;
    const time = now();
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, width, height);
    bursts = bursts.filter((burst) => time - burst.start < RISE + LIFE);
    for (const burst of bursts) drawBurst(burst, time);
    context.globalAlpha = 1;
    if (bursts.length > 0 && !document.hidden) frame = requestAnimationFrame(draw);
  }

  // 제목이 내려앉으면 양옆에서 잇달아 터진다. 그 뒤로는 가끔 한 발씩
  let timer = 0;
  let welcomed = false;
  function later() {
    timer = window.setTimeout(
      () => {
        if (!document.hidden) launch(count);
        later();
      },
      7000 + noise(count, 5) * 5000,
    );
  }
  function welcome() {
    if (welcomed) return;
    welcomed = true;
    [0, 0.16, 0.5, 0.72, 1.15, 1.4].forEach((delay, index) => launch(index, delay));
    window.clearTimeout(timer);
    later();
  }
  // 등장이 없거나 멈췄을 때를 위한 예비 (등장은 5초쯤 걸린다)
  timer = window.setTimeout(welcome, 6500);

  /** 빈 곳을 누르면 그 자리에서 한 발. 글과 입력칸, 버튼 위에서는 터뜨리지 않는다 */
  function onClick(event: MouseEvent) {
    const target = event.target instanceof Element ? event.target : null;
    if (!target || !stage?.contains(target)) return;
    if (target.closest("a, button, input, textarea, select, label, [role='button']")) return;
    const origin = host.getBoundingClientRect();
    const x = event.clientX - origin.left;
    const y = event.clientY - origin.top;
    const keep = content();
    if (keep && x > keep.left - 12 && x < keep.right + 12 && y > keep.top - 12 && y < keep.bottom + 12) return;
    add(x, y, Math.min(110, Math.max(60, width * 0.07)));
  }
  const onVisibility = () => {
    if (!document.hidden && bursts.length > 0 && !frame) frame = requestAnimationFrame(draw);
  };

  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(host);
  resize();
  window.addEventListener(TITLE_LANDED, welcome);
  window.addEventListener("click", onClick);
  document.addEventListener("visibilitychange", onVisibility);

  return () => {
    cancelAnimationFrame(frame);
    window.clearTimeout(timer);
    resizeObserver.disconnect();
    window.removeEventListener(TITLE_LANDED, welcome);
    window.removeEventListener("click", onClick);
    document.removeEventListener("visibilitychange", onVisibility);
    canvas.remove();
  };
}
