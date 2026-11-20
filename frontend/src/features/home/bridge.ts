import type * as Three from "three";

type ThreeModule = typeof Three;

/**
 * 홈 배경의 광안대교 3D 장면 (three.js). 현수교 모양을 직접 쌓는다: 주탑 2개, 2층 상판, 주케이블과 행어, 접속교 교각,
 * 바다, 멀리 해운대 쪽 빌딩. 색은 디자인 토큰(CSS 변수)에서만 읽고, 흰 안개로 멀리 갈수록 흐려져 글이 잘 읽히게 한다.
 * 시점은 천천히 좌우로 흐르고 커서를 조금 따라간다. 움직임 줄이기 설정이면 한 장면만 그린다.
 * 돌려주는 함수를 부르면 그리기를 멈추고 자원을 정리한다.
 */

// 길이 단위는 대략 5m = 1. 주경간 500m, 주탑 높이 약 120m
const TOWER_X = 52;
const TOWER_HEIGHT = 30;
const DECK_Y = 7.4;
const DECK_HEIGHT = 2.2;
const DECK_WIDTH = 6.4;
const CABLE_Z = DECK_WIDTH / 2 + 0.3;
const DECK_END = 190;
const ANCHOR_X = 138;
const DECK_TOP = DECK_Y + DECK_HEIGHT / 2;
/** 상판을 화면 가운데에서 얼마나 아래에 둘지 (세로 화각에 대한 비율). 0.35면 위에서 85% 높이쯤이다 */
const DECK_BELOW_CENTER = 0.35;
const DECK_BELOW_CENTER_PORTRAIT = 0.4;

function tokenColor(THREE: ThreeModule, name: string): Three.Color {
  const value = getComputedStyle(document.documentElement).getPropertyValue(`--color-${name}`).trim();
  return new THREE.Color(value);
}

/** 주케이블 높이. 주경간은 가운데가 처진 포물선, 측경간은 주탑 꼭대기에서 앵커리지로 내려간다 */
function cableY(x: number): number {
  const top = TOWER_HEIGHT - 0.5;
  const low = DECK_TOP + 1.1;
  const ax = Math.abs(x);
  if (ax <= TOWER_X) return low + (top - low) * (ax / TOWER_X) ** 2;
  const t = (ax - TOWER_X) / (ANCHOR_X - TOWER_X);
  const end = DECK_TOP + 0.5;
  return end + (top - end) * (1 - t) ** 1.7;
}

export function mountBridge(THREE: ThreeModule, host: HTMLElement): () => void {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const white = tokenColor(THREE, "white");
  const blue50 = tokenColor(THREE, "blue-50");
  const blue500 = tokenColor(THREE, "blue-500");
  const grey100 = tokenColor(THREE, "grey-100");
  const grey200 = tokenColor(THREE, "grey-200");
  const grey300 = tokenColor(THREE, "grey-300");
  const grey400 = tokenColor(THREE, "grey-400");

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
  renderer.setClearColor(white, 0);
  const canvas = renderer.domElement;
  canvas.style.width = "100%";
  canvas.style.height = "100%";
  canvas.style.display = "block";
  host.appendChild(canvas);

  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(white, 110, 430);
  const camera = new THREE.PerspectiveCamera(30, 1, 1, 1200);
  // 거리와 보는 높이는 화면 비율에 맞춰 resize()가 정한다
  const cameraBase = new THREE.Vector3(20, 9.5, 122);
  const lookAt = new THREE.Vector3(0, 30, 0);

  scene.add(new THREE.HemisphereLight(white, blue50, 2.3));
  const sun = new THREE.DirectionalLight(white, 2.1);
  sun.position.set(-70, 90, 80);
  scene.add(sun);

  const disposables: { dispose: () => void }[] = [];
  const solid = (color: Three.Color) => {
    const material = new THREE.MeshStandardMaterial({ color, roughness: 0.9, metalness: 0, flatShading: true });
    disposables.push(material);
    return material;
  };
  const add = (geometry: Three.BufferGeometry, material: Three.Material, x: number, y: number, z: number) => {
    disposables.push(geometry);
    const mesh = new THREE.Mesh(geometry, material);
    mesh.position.set(x, y, z);
    scene.add(mesh);
    return mesh;
  };

  const concrete = solid(white);
  const shade = solid(grey200);
  const dark = solid(grey300);

  // 주탑: 위로 갈수록 가늘어지는 기둥 2개를 가로보 3개로 잇는다
  for (const x of [-TOWER_X, TOWER_X]) {
    for (const z of [-CABLE_Z, CABLE_Z]) {
      const leg = add(new THREE.CylinderGeometry(0.72, 1.05, TOWER_HEIGHT, 4, 1), concrete, x, TOWER_HEIGHT / 2, z);
      leg.rotation.y = Math.PI / 4;
    }
    for (const [y, height] of [
      [TOWER_HEIGHT - 1.3, 1.5],
      [TOWER_HEIGHT * 0.62, 1.2],
      [DECK_Y - DECK_HEIGHT / 2 - 0.9, 1.3],
    ] as const) {
      add(new THREE.BoxGeometry(1.25, height, CABLE_Z * 2), shade, x, y, 0);
    }
  }

  // 상판: 2층 트러스. 두 층 사이를 어둡게 넣고 바깥 가장자리에 파란 조명 줄을 둔다
  add(new THREE.BoxGeometry(DECK_END * 2, DECK_HEIGHT, DECK_WIDTH), concrete, 0, DECK_Y, 0);
  add(new THREE.BoxGeometry(DECK_END * 2, DECK_HEIGHT * 0.34, DECK_WIDTH + 0.08), dark, 0, DECK_Y, 0);
  const lightStrip = new THREE.MeshBasicMaterial({ color: blue500 });
  disposables.push(lightStrip);
  for (const z of [-(DECK_WIDTH / 2 + 0.06), DECK_WIDTH / 2 + 0.06]) {
    add(new THREE.BoxGeometry(ANCHOR_X * 2, 0.14, 0.08), lightStrip, 0, DECK_TOP - 0.12, z);
  }

  // 접속교 교각
  for (let x = TOWER_X + 16; x <= DECK_END; x += 16) {
    for (const side of [-1, 1]) {
      add(new THREE.BoxGeometry(1.3, DECK_Y - DECK_HEIGHT / 2, DECK_WIDTH * 0.7), shade, side * x, (DECK_Y - DECK_HEIGHT / 2) / 2, 0);
    }
  }

  // 주케이블 (양쪽) 과 행어
  const cableMaterial = solid(grey400);
  const hangerPoints: number[] = [];
  for (const z of [-CABLE_Z, CABLE_Z]) {
    const points: Three.Vector3[] = [];
    for (let x = -ANCHOR_X; x <= ANCHOR_X; x += 2) points.push(new THREE.Vector3(x, cableY(x), z));
    const curve = new THREE.CatmullRomCurve3(points);
    add(new THREE.TubeGeometry(curve, 220, 0.2, 6, false), cableMaterial, 0, 0, 0);
    for (let x = -ANCHOR_X + 6; x <= ANCHOR_X - 6; x += 2.6) {
      if (Math.abs(Math.abs(x) - TOWER_X) < 1.6) continue;
      hangerPoints.push(x, cableY(x), z, x, DECK_TOP, z);
    }
  }
  const hangerGeometry = new THREE.BufferGeometry();
  hangerGeometry.setAttribute("position", new THREE.Float32BufferAttribute(hangerPoints, 3));
  const hangerMaterial = new THREE.LineBasicMaterial({ color: grey300, transparent: true, opacity: 0.9 });
  disposables.push(hangerGeometry, hangerMaterial);
  scene.add(new THREE.LineSegments(hangerGeometry, hangerMaterial));

  // 멀리 보이는 빌딩 (해운대 쪽). 안개에 묻혀 윤곽만 남는다
  const towers = solid(grey100);
  // 가운데 글 뒤는 비워 두고 양옆에만 둔다
  const skyline = [
    [-190, 30, 9], [-176, 46, 8], [-163, 34, 9], [-150, 58, 8], [-138, 40, 9], [-126, 66, 8], [-114, 44, 9],
    [-102, 28, 10], [-90, 36, 8], [96, 22, 11], [110, 32, 9], [124, 24, 10], [140, 38, 9], [156, 26, 10], [174, 34, 9],
  ] as const;
  for (const [x, height, width] of skyline) add(new THREE.BoxGeometry(width, height, width), towers, x, height / 2, -240);

  // 바다: 낮은 다각형 물결. 꼭짓점 높이만 바꾸고 면은 평평하게 칠한다 (flatShading)
  const seaGeometry = new THREE.PlaneGeometry(1000, 620, 96, 56);
  seaGeometry.rotateX(-Math.PI / 2);
  const seaMaterial = new THREE.MeshStandardMaterial({ color: blue50, roughness: 0.6, metalness: 0, flatShading: true });
  disposables.push(seaGeometry, seaMaterial);
  const sea = new THREE.Mesh(seaGeometry, seaMaterial);
  sea.position.set(0, 0, -60);
  scene.add(sea);
  const seaPositions = seaGeometry.attributes.position as Three.BufferAttribute;
  const seaBase = Float32Array.from(seaPositions.array as Float32Array);
  function waves(time: number) {
    for (let i = 0; i < seaPositions.count; i += 1) {
      const x = seaBase[i * 3];
      const z = seaBase[i * 3 + 2];
      seaPositions.setY(i, 0.5 * Math.sin(x * 0.11 + time * 0.7) + 0.42 * Math.sin(z * 0.17 + time * 0.9) + 0.3 * Math.sin((x + z) * 0.23 + time * 1.3));
    }
    seaPositions.needsUpdate = true;
  }

  const pointer = { x: 0, y: 0 };
  const eased = { x: 0, y: 0 };
  function onPointerMove(event: PointerEvent) {
    if (event.pointerType === "touch") return;
    pointer.x = (event.clientX / window.innerWidth) * 2 - 1;
    pointer.y = (event.clientY / window.innerHeight) * 2 - 1;
  }

  function resize() {
    const width = host.clientWidth;
    const height = host.clientHeight;
    if (!width || !height) return;
    renderer.setSize(width, height, false);
    const aspect = width / height;
    const portrait = aspect < 1;
    camera.aspect = aspect;
    camera.fov = portrait ? 50 : 30;
    camera.updateProjectionMatrix();
    // 주탑 두 개가 양옆에 걸리도록 물러선다. 세로 화면에서는 안개에 묻히지 않을 만큼만 물러서고 가운데 경간만 보인다
    const halfFov = (camera.fov * Math.PI) / 360;
    cameraBase.z = Math.min(190, Math.max(118, (TOWER_X * 1.25) / (Math.tan(halfFov) * aspect)));
    // 상판이 늘 화면 아래쪽(글 아래)에 오도록, 물러선 거리만큼 더 위를 본다
    lookAt.y = DECK_Y + cameraBase.z * Math.tan(halfFov * 2 * (portrait ? DECK_BELOW_CENTER_PORTRAIT : DECK_BELOW_CENTER));
  }

  let frame = 0;
  let running = false;
  const start = performance.now();
  function draw(time: number) {
    eased.x += (pointer.x - eased.x) * 0.04;
    eased.y += (pointer.y - eased.y) * 0.04;
    camera.position.set(
      cameraBase.x + Math.sin(time * 0.07) * 7 + eased.x * 5,
      cameraBase.y - eased.y * 0.6,
      cameraBase.z + Math.cos(time * 0.05) * 3,
    );
    camera.lookAt(lookAt);
    waves(time);
    renderer.render(scene, camera);
  }
  function loop() {
    if (!running) return;
    draw((performance.now() - start) / 1000);
    frame = requestAnimationFrame(loop);
  }
  function setRunning(next: boolean) {
    if (reduceMotion || next === running) return;
    running = next;
    cancelAnimationFrame(frame);
    if (running) frame = requestAnimationFrame(loop);
  }

  const resizeObserver = new ResizeObserver(() => {
    resize();
    if (!running) draw(0);
  });
  resizeObserver.observe(host);
  const onVisibility = () => setRunning(!document.hidden);
  document.addEventListener("visibilitychange", onVisibility);
  window.addEventListener("pointermove", onPointerMove, { passive: true });

  resize();
  draw(0);
  setRunning(!document.hidden);

  return () => {
    running = false;
    cancelAnimationFrame(frame);
    resizeObserver.disconnect();
    document.removeEventListener("visibilitychange", onVisibility);
    window.removeEventListener("pointermove", onPointerMove);
    for (const item of disposables) item.dispose();
    renderer.dispose();
    canvas.remove();
  };
}
