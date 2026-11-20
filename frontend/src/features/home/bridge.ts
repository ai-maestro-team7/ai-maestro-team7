import type * as Three from "three";

type ThreeModule = typeof Three;

/**
 * 홈 배경의 광안대교 3D 장면 (three.js). 색은 디자인 토큰(CSS 변수)에서만 읽고, 섞어 쓸 때도 토큰끼리만 섞는다.
 *
 * 무대: 현수교(주탑 2개, 2층 상판과 트러스, 주케이블·행어, 접속교 교각), 수면에 비친 다리, 낮은 다각형 물결,
 *       오른쪽 산 너머로 뜨는 해와 바다 위 윤슬, 겹겹이 놓인 산 능선과 멀리 빌딩.
 * 움직임: 처음에 높은 곳에서 내려오는 시점, 케이블과 행어를 따라 흐르는 파란 조명, 오가는 차량 불빛, 주탑 경광등,
 *         멀리 나는 갈매기 떼, 지나가는 배. (하늘의 불꽃은 fireworks.ts가 따로 그린다)
 * 흰 안개로 멀리 갈수록 흐려져 가운데 글이 잘 읽히게 한다. 시점은 천천히 흐르고 커서를 조금 따라간다.
 * 움직임 줄이기 설정이면 한 장면만 그린다. 돌려주는 함수를 부르면 그리기를 멈추고 자원을 정리한다.
 */

// 길이 단위는 대략 5m = 1. 주경간 500m, 주탑 높이 약 120m
const TOWER_X = 52;
const TOWER_HEIGHT = 30;
const DECK_Y = 7.4;
const DECK_HEIGHT = 2.2;
const DECK_WIDTH = 6.4;
const CABLE_Z = DECK_WIDTH / 2 + 0.3;
const DECK_END = 230;
const ANCHOR_X = 138;
const DECK_TOP = DECK_Y + DECK_HEIGHT / 2;
const DECK_BOTTOM = DECK_Y - DECK_HEIGHT / 2;
/** 상판을 화면 가운데에서 얼마나 아래에 둘지 (세로 화각에 대한 비율). 0.35면 위에서 85% 높이쯤이다 */
const DECK_BELOW_CENTER = 0.35;
const DECK_BELOW_CENTER_PORTRAIT = 0.4;
const INTRO_SECONDS = 4.2;

function tokenColor(THREE: ThreeModule, name: string): Three.Color {
  const value = getComputedStyle(document.documentElement).getPropertyValue(`--color-${name}`).trim();
  return new THREE.Color(value);
}

/**
 * 토큰 두 색을 화면 색(sRGB) 기준으로 섞는다. three.js의 lerp는 빛의 양으로 섞어서 옅은 파랑이 보랏빛으로 돈다.
 * 이렇게 섞어야 blue-50처럼 디자인 토큰과 같은 결의 옅은 파랑이 나온다.
 */
function mix(THREE: ThreeModule, from: Three.Color, to: Three.Color, amount: number): Three.Color {
  const a = from.getRGB({ r: 0, g: 0, b: 0 }, THREE.SRGBColorSpace);
  const b = to.getRGB({ r: 0, g: 0, b: 0 }, THREE.SRGBColorSpace);
  return new THREE.Color().setRGB(a.r + (b.r - a.r) * amount, a.g + (b.g - a.g) * amount, a.b + (b.b - a.b) * amount, THREE.SRGBColorSpace);
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

/** 가운데가 진하고 가장자리로 사라지는 둥근 빛 그림 (해, 케이블 조명의 빛무리) */
function glowTexture(THREE: ThreeModule, color: Three.Color, stops: [number, number][]): Three.CanvasTexture {
  const size = 128;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const context = canvas.getContext("2d");
  if (context) {
    const gradient = context.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
    // three.js 색은 빛의 양으로 들어 있다. 캔버스에는 화면 색(sRGB)으로 바꿔서 칠한다
    const screen = color.getRGB({ r: 0, g: 0, b: 0 }, THREE.SRGBColorSpace);
    const rgb = `${Math.round(screen.r * 255)}, ${Math.round(screen.g * 255)}, ${Math.round(screen.b * 255)}`;
    for (const [at, alpha] of stops) gradient.addColorStop(at, `rgba(${rgb}, ${alpha})`);
    context.fillStyle = gradient;
    context.fillRect(0, 0, size, size);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

/** 0~1 난수 (같은 번호면 늘 같은 값) */
const random = (index: number, salt: number) => {
  const value = Math.sin(index * 12.9898 + salt * 78.233) * 43758.5453;
  return value - Math.floor(value);
};

const easeOutCubic = (t: number) => 1 - (1 - Math.min(1, Math.max(0, t))) ** 3;

export function mountBridge(THREE: ThreeModule, host: HTMLElement): () => void {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const white = tokenColor(THREE, "white");
  const blue50 = tokenColor(THREE, "blue-50");
  const blue500 = tokenColor(THREE, "blue-500");
  const orange500 = tokenColor(THREE, "orange-500");
  const red500 = tokenColor(THREE, "red-500");
  const grey100 = tokenColor(THREE, "grey-100");
  const grey200 = tokenColor(THREE, "grey-200");
  const grey300 = tokenColor(THREE, "grey-300");
  const grey400 = tokenColor(THREE, "grey-400");
  const grey700 = tokenColor(THREE, "grey-700");

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setClearColor(white, 0);
  const canvas = renderer.domElement;
  canvas.style.width = "100%";
  canvas.style.height = "100%";
  canvas.style.display = "block";
  host.appendChild(canvas);

  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(white, 140, 700);
  const camera = new THREE.PerspectiveCamera(30, 1, 1, 2400);
  // 거리와 보는 높이는 화면 비율에 맞춰 resize()가 정한다
  const cameraBase = new THREE.Vector3(20, 9.5, 122);
  const lookAt = new THREE.Vector3(0, 30, 0);

  // 해는 오른쪽에서 비춘다. 오른쪽 면은 밝고 왼쪽 면에는 옅은 푸른 그늘이 져서, 흰 하늘 앞에서도 덩어리가 보인다
  const shadeBlue = mix(THREE, blue50, blue500, 0.22);
  scene.add(new THREE.HemisphereLight(white, shadeBlue, 1.9));
  const sunLight = new THREE.DirectionalLight(white, 2.4);
  sunLight.position.set(160, 90, 60);
  scene.add(sunLight);

  const disposables: { dispose: () => void }[] = [];
  const keep = <T extends { dispose: () => void }>(item: T): T => {
    disposables.push(item);
    return item;
  };
  // 수면에 비친 다리는 위아래를 뒤집어 그리므로 면을 양쪽 다 칠한다
  const solid = (color: Three.Color) =>
    keep(new THREE.MeshStandardMaterial({ color, roughness: 0.9, metalness: 0, flatShading: true, side: THREE.DoubleSide }));

  // ------------------------------------------------------------------ 다리 (한 번 쌓고, 뒤집어 수면에 비춘다)
  const bridge = new THREE.Group();
  const place = (geometry: Three.BufferGeometry, material: Three.Material, x: number, y: number, z: number) => {
    const mesh = new THREE.Mesh(keep(geometry), material);
    mesh.position.set(x, y, z);
    bridge.add(mesh);
    return mesh;
  };
  const concrete = solid(white);
  const shade = solid(grey200);
  const dark = solid(grey300);

  // 주탑: 위로 갈수록 가늘어지는 기둥 2개를 가로보 3개로 잇고, 가로보 사이를 X자로 엮는다
  const braces: number[] = [];
  const beams = [TOWER_HEIGHT - 1.3, TOWER_HEIGHT * 0.66, DECK_TOP + 2.4];
  for (const x of [-TOWER_X, TOWER_X]) {
    for (const z of [-CABLE_Z, CABLE_Z]) {
      const leg = place(new THREE.CylinderGeometry(0.72, 1.05, TOWER_HEIGHT, 4, 1), concrete, x, TOWER_HEIGHT / 2, z);
      leg.rotation.y = Math.PI / 4;
      place(new THREE.BoxGeometry(2.1, 0.7, 2.1), shade, x, TOWER_HEIGHT + 0.2, z); // 케이블이 얹히는 머리
    }
    for (const y of beams) place(new THREE.BoxGeometry(1.25, 1.3, CABLE_Z * 2), shade, x, y, 0);
    place(new THREE.BoxGeometry(1.25, 1.3, CABLE_Z * 2), shade, x, DECK_BOTTOM - 0.9, 0);
    for (let i = 0; i < beams.length - 1; i += 1) {
      const top = beams[i] - 0.65;
      const bottom = beams[i + 1] + 0.65;
      braces.push(x, top, -CABLE_Z + 0.6, x, bottom, CABLE_Z - 0.6, x, top, CABLE_Z - 0.6, x, bottom, -CABLE_Z + 0.6);
    }
  }

  // 상판: 2층 트러스. 위·아래 판 사이를 지그재그 사재로 엮고 바깥 가장자리에 파란 조명 줄을 둔다
  place(new THREE.BoxGeometry(DECK_END * 2, 0.5, DECK_WIDTH), concrete, 0, DECK_TOP - 0.25, 0);
  place(new THREE.BoxGeometry(DECK_END * 2, 0.45, DECK_WIDTH), shade, 0, DECK_BOTTOM + 0.22, 0);
  place(new THREE.BoxGeometry(DECK_END * 2, DECK_HEIGHT - 0.95, DECK_WIDTH - 1.6), dark, 0, DECK_Y, 0);
  const TRUSS_STEP = 2.6;
  for (const z of [-DECK_WIDTH / 2, DECK_WIDTH / 2]) {
    for (let x = -ANCHOR_X, up = true; x < ANCHOR_X; x += TRUSS_STEP, up = !up) {
      braces.push(x, up ? DECK_BOTTOM + 0.4 : DECK_TOP - 0.5, z, x + TRUSS_STEP, up ? DECK_TOP - 0.5 : DECK_BOTTOM + 0.4, z);
      braces.push(x, DECK_BOTTOM + 0.4, z, x, DECK_TOP - 0.5, z);
    }
  }
  const lightStrip = keep(new THREE.MeshBasicMaterial({ color: blue500, side: THREE.DoubleSide }));
  for (const z of [-(DECK_WIDTH / 2 + 0.06), DECK_WIDTH / 2 + 0.06]) {
    place(new THREE.BoxGeometry(ANCHOR_X * 2, 0.16, 0.08), lightStrip, 0, DECK_TOP - 0.1, z);
  }

  // 접속교 교각
  for (let x = TOWER_X + 16; x <= DECK_END; x += 16) {
    for (const side of [-1, 1]) {
      place(new THREE.BoxGeometry(1.3, DECK_BOTTOM, DECK_WIDTH * 0.7), concrete, side * x, DECK_BOTTOM / 2, 0);
    }
  }

  // 주케이블 (양쪽), 행어, 엮음 선
  const cableMaterial = solid(grey400);
  const hangers: number[] = [];
  for (const z of [-CABLE_Z, CABLE_Z]) {
    const points: Three.Vector3[] = [];
    for (let x = -ANCHOR_X; x <= ANCHOR_X; x += 2) points.push(new THREE.Vector3(x, cableY(x), z));
    place(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points), 220, 0.2, 6, false), cableMaterial, 0, 0, 0);
    for (let x = -ANCHOR_X + 6; x <= ANCHOR_X - 6; x += 2.6) {
      if (Math.abs(Math.abs(x) - TOWER_X) < 1.6) continue;
      hangers.push(x, cableY(x), z, x, DECK_TOP, z);
    }
  }
  const lines = (points: number[], color: Three.Color, opacity: number) => {
    const geometry = keep(new THREE.BufferGeometry());
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(points, 3));
    bridge.add(new THREE.LineSegments(geometry, keep(new THREE.LineBasicMaterial({ color, transparent: true, opacity }))));
  };
  lines(braces, grey400, 0.75);
  // 행어는 꼭짓점마다 색을 따로 줘서 조명 물결이 지나갈 때 파랗게 물든다
  const hangerGeometry = keep(new THREE.BufferGeometry());
  hangerGeometry.setAttribute("position", new THREE.Float32BufferAttribute(hangers, 3));
  const hangerColors = new THREE.BufferAttribute(new Float32Array(hangers.length), 3);
  hangerGeometry.setAttribute("color", hangerColors);
  bridge.add(new THREE.LineSegments(hangerGeometry, keep(new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.95 }))));

  const mirror = bridge.clone();
  mirror.scale.y = -1;
  scene.add(bridge, mirror);

  // ------------------------------------------------------------------ 조명: 케이블 빛, 차량, 경광등 (수면에도 비친다)
  const reflected = (make: () => Three.InstancedMesh, share: (copy: Three.InstancedMesh, original: Three.InstancedMesh) => void) => {
    const original = make();
    const copy = make();
    share(copy, original);
    const flipped = new THREE.Group();
    flipped.scale.y = -1;
    flipped.add(copy);
    scene.add(original, flipped);
    return original;
  };

  // 케이블을 따라 놓은 조명 구슬. 파란 빛 물결이 왼쪽에서 오른쪽으로 흘러가고, 물결이 지나는 구슬은 커진다
  const ledSpots: { x: number; z: number; u: number }[] = [];
  for (const z of [-CABLE_Z, CABLE_Z]) {
    for (let x = -ANCHOR_X; x <= ANCHOR_X; x += 1.5) ledSpots.push({ x, z, u: (x + ANCHOR_X) / (ANCHOR_X * 2) });
  }
  const ledGeometry = keep(new THREE.SphereGeometry(0.24, 8, 6));
  const ledMaterial = keep(new THREE.MeshBasicMaterial({ color: white }));
  const matrix = new THREE.Matrix4();
  const leds = reflected(
    () => {
      const mesh = new THREE.InstancedMesh(ledGeometry, ledMaterial, ledSpots.length);
      ledSpots.forEach((_, i) => mesh.setColorAt(i, white));
      return mesh;
    },
    (copy, original) => {
      copy.instanceColor = original.instanceColor;
      copy.instanceMatrix = original.instanceMatrix;
    },
  );
  const WAVES = 2.5; // 다리 위에 동시에 보이는 물결 수
  const WAVE_SPEED = 0.2; // 물결이 1초에 지나가는 거리 (물결 간격에 대한 비율)
  /** 물결의 세기 (0~1). u는 다리 왼쪽 끝 0 ~ 오른쪽 끝 1 */
  const lightWave = (u: number, time: number) => Math.max(0, Math.sin(2 * Math.PI * (u * WAVES - time * WAVE_SPEED))) ** 6;
  // 물결 세기에 따른 색을 미리 만들어 둔다 (프레임마다 섞지 않는다)
  const SHADES = 24;
  const ledShades = Array.from({ length: SHADES + 1 }, (_, k) => mix(THREE, mix(THREE, white, blue500, 0.14), blue500, k / SHADES));
  const hangerShades = Array.from({ length: SHADES + 1 }, (_, k) => mix(THREE, grey300, blue500, k / SHADES));
  const shadeAt = (shades: Three.Color[], amount: number) => shades[Math.round(Math.min(1, Math.max(0, amount)) * SHADES)];
  const hangerCount = hangers.length / 6;
  // 물결 꼭대기를 따라다니는 빛무리
  const haloMaterials = Array.from({ length: 4 }, () =>
    keep(new THREE.SpriteMaterial({ map: null, transparent: true, depthWrite: false, opacity: 0 })),
  );
  const haloTexture = keep(glowTexture(THREE, blue500, [[0, 0.5], [0.35, 0.18], [1, 0]]));
  const halos = haloMaterials.map((material) => {
    material.map = haloTexture;
    const halo = new THREE.Sprite(material);
    halo.scale.set(20, 20, 1);
    scene.add(halo);
    return halo;
  });
  function flowLights(time: number) {
    ledSpots.forEach((spot, i) => {
      const wave = lightWave(spot.u, time);
      const twinkle = 0.1 * Math.max(0, Math.sin(time * 3 + i * 1.7));
      leds.setColorAt(i, shadeAt(ledShades, wave + twinkle));
      const size = 1 + 1.5 * wave;
      leds.setMatrixAt(i, matrix.makeScale(size, size, size).setPosition(spot.x, cableY(spot.x) + 0.32, spot.z));
    });
    if (leds.instanceColor) leds.instanceColor.needsUpdate = true;
    leds.instanceMatrix.needsUpdate = true;
    for (let i = 0; i < hangerCount; i += 1) {
      const wave = lightWave((hangers[i * 6] + ANCHOR_X) / (ANCHOR_X * 2), time);
      const color = shadeAt(hangerShades, wave);
      hangerColors.setXYZ(i * 2, color.r, color.g, color.b);
      hangerColors.setXYZ(i * 2 + 1, color.r, color.g, color.b);
    }
    hangerColors.needsUpdate = true;
    // 물결 꼭대기: u * WAVES - time * WAVE_SPEED = n + 0.25
    const first = Math.ceil(-time * WAVE_SPEED - 0.25);
    halos.forEach((halo, k) => {
      const u = (first + k + 0.25 + time * WAVE_SPEED) / WAVES;
      const x = u * ANCHOR_X * 2 - ANCHOR_X;
      halo.position.set(x, cableY(x) + 0.3, 0);
      halo.material.opacity = u > 1 ? 0 : Math.min(1, u * 8, (1 - u) * 8);
    });
  }

  // 차량 불빛: 한쪽 차로는 흰 전조등, 반대 차로는 붉은 후미등
  const cars = Array.from({ length: 84 }, (_, i) => ({
    lane: i % 2 === 0 ? 1 : -1,
    offset: ((i * 53.7) % (DECK_END * 2)) - DECK_END,
    speed: 7 + ((i * 7) % 5) * 0.9,
  }));
  const carGeometry = keep(new THREE.BoxGeometry(0.95, 0.34, 0.5));
  const carMaterial = keep(new THREE.MeshBasicMaterial({ color: white }));
  const headlight = mix(THREE, white, orange500, 0.25);
  const traffic = reflected(
    () => {
      const mesh = new THREE.InstancedMesh(carGeometry, carMaterial, cars.length);
      cars.forEach((car, i) => mesh.setColorAt(i, car.lane > 0 ? headlight : red500));
      return mesh;
    },
    (copy, original) => {
      copy.instanceMatrix = original.instanceMatrix;
    },
  );
  function driveCars(time: number) {
    cars.forEach((car, i) => {
      const travelled = car.offset + car.lane * car.speed * time;
      const x = ((((travelled + DECK_END) % (DECK_END * 2)) + DECK_END * 2) % (DECK_END * 2)) - DECK_END;
      traffic.setMatrixAt(i, matrix.makeTranslation(x, DECK_TOP + 0.2, car.lane * 1.3));
    });
    traffic.instanceMatrix.needsUpdate = true;
  }

  // 주탑 꼭대기 경광등
  const beaconMaterial = keep(new THREE.MeshBasicMaterial({ color: red500 }));
  const beaconGeometry = keep(new THREE.SphereGeometry(0.36, 10, 8));
  const beacons: Three.Mesh[] = [];
  for (const x of [-TOWER_X, TOWER_X]) {
    for (const z of [-CABLE_Z, CABLE_Z]) {
      const beacon = new THREE.Mesh(beaconGeometry, beaconMaterial);
      beacon.position.set(x, TOWER_HEIGHT + 0.95, z);
      scene.add(beacon);
      beacons.push(beacon);
    }
  }

  // ------------------------------------------------------------------ 하늘: 산 너머로 뜨는 해, 겹겹이 놓인 산 능선, 빌딩
  // 해의 자리는 화면 비율에 맞춰 resize()가 정한다 (글 오른쪽, 수평선 바로 위)
  const sunPosition = new THREE.Vector3(150, 60, -880);
  const sunRay = new THREE.Vector3();
  const sunGlow = new THREE.Sprite(
    keep(new THREE.SpriteMaterial({ map: keep(glowTexture(THREE, orange500, [[0, 0.5], [0.25, 0.24], [0.6, 0.07], [1, 0]])), transparent: true, depthWrite: false, fog: false })),
  );
  sunGlow.scale.set(420, 420, 1);
  const sunDisc = new THREE.Sprite(
    keep(new THREE.SpriteMaterial({ map: keep(glowTexture(THREE, mix(THREE, white, orange500, 0.5), [[0, 1], [0.84, 1], [0.92, 0.45], [1, 0]])), transparent: true, depthWrite: false, fog: false })),
  );
  sunDisc.scale.set(80, 80, 1);
  scene.add(sunGlow, sunDisc);

  // 산 능선 (황령산·장산 쪽): 낮은 삼각형 띠를 두 겹 둔다. 글 뒤쪽은 낮추고 양옆으로 갈수록 높아진다
  const RIDGE_CENTER = -65; // 화면 가운데가 닿는 곳 (시점이 조금 왼쪽을 본다)
  const ridgeLayer = (z: number, base: number, color: Three.Color, phase: number) => {
    const points: number[] = [];
    const heightAt = (x: number) => {
      const side = Math.min(1, Math.abs(x - RIDGE_CENTER) / 240) ** 1.6;
      const rough = 0.62 + 0.22 * Math.sin(x * 0.013 + phase) + 0.1 * Math.sin(x * 0.041 + phase * 2) + 0.06 * Math.sin(x * 0.097 + phase * 3);
      return base * rough * (0.3 + 0.7 * side);
    };
    const STEP = 22;
    for (let x = -640; x < 640; x += STEP) {
      points.push(x, 0, z, x + STEP, 0, z, x, heightAt(x), z, x + STEP, 0, z, x + STEP, heightAt(x + STEP), z, x, heightAt(x), z);
    }
    const geometry = keep(new THREE.BufferGeometry());
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(points, 3));
    scene.add(new THREE.Mesh(geometry, keep(new THREE.MeshBasicMaterial({ color, side: THREE.DoubleSide, fog: false }))));
  };
  ridgeLayer(-560, 48, mix(THREE, white, blue500, 0.08), 1.3);
  ridgeLayer(-440, 28, mix(THREE, white, blue500, 0.15), 4.1);

  // 멀리 보이는 빌딩 (해운대 쪽). 가운데 글 뒤는 비워 두고 양옆에만 둔다
  const towers = solid(grey100);
  for (let i = 0; i < 34; i += 1) {
    const left = i < 21;
    const x = left ? -250 + i * 8.6 + ((i * 13) % 5) : 96 + (i - 21) * 11.5 + ((i * 7) % 4);
    const height = (left ? 26 : 16) + ((i * 37) % 11) * (left ? 5.2 : 2.6);
    const width = 5 + ((i * 5) % 4);
    const tower = new THREE.Mesh(keep(new THREE.BoxGeometry(width, height, width)), towers);
    tower.position.set(x, height / 2, -300 - ((i * 17) % 60));
    scene.add(tower);
  }

  // ------------------------------------------------------------------ 바다: 낮은 다각형 물결 + 윤슬. 반쯤 비쳐서 다리가 비친다
  const seaGeometry = keep(new THREE.PlaneGeometry(1500, 900, 110, 64));
  seaGeometry.rotateX(-Math.PI / 2);
  const seaMaterial = keep(
    new THREE.MeshStandardMaterial({ color: mix(THREE, blue50, blue500, 0.17), roughness: 0.5, metalness: 0, flatShading: true, transparent: true, opacity: 0.86 }),
  );
  const sea = new THREE.Mesh(seaGeometry, seaMaterial);
  sea.position.set(0, 0, -170);
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

  // 윤슬: 해 아래로 이쪽까지 이어지는 물길에 몰려 있고, 나머지 바다에도 드문드문 반짝인다. 점마다 박자가 다르다
  const GLINTS = 720;
  const SUN_PATH = 460; // 이 가운데 해 물길 위에 놓는 점
  const glintPositions = new THREE.BufferAttribute(new Float32Array(GLINTS * 3), 3);
  const glintPhases = new Float32Array(GLINTS);
  const glintWarmth = new Float32Array(GLINTS); // 해 물길 위의 점은 따뜻한 빛, 나머지는 흰빛
  for (let i = 0; i < GLINTS; i += 1) {
    glintPhases[i] = (i * 2.399) % (Math.PI * 2);
    glintWarmth[i] = i < SUN_PATH ? 1 : 0;
  }
  function layGlints() {
    // 시점에서 해 쪽으로 가는 수면 위의 방향
    const dx = sunPosition.x - cameraBase.x;
    const dz = sunPosition.z - cameraBase.z;
    const length = Math.hypot(dx, dz);
    for (let i = 0; i < GLINTS; i += 1) {
      // 고르게 흩되 줄이 맞아 보이지 않게, 점 번호로 만든 난수를 쓴다
      const a = random(i, 1);
      const b = random(i, 2);
      if (i < SUN_PATH) {
        const distance = 70 + 600 * a ** 1.5;
        const spread = (b - 0.5) * (16 + 0.1 * distance);
        glintPositions.setXYZ(i, cameraBase.x + (dx / length) * distance - (dz / length) * spread, 1.5, cameraBase.z + (dz / length) * distance + (dx / length) * spread);
      } else {
        glintPositions.setXYZ(i, -300 + 600 * a, 1.5, 70 - 420 * b ** 1.3);
      }
    }
    glintPositions.needsUpdate = true;
  }
  const glintGeometry = keep(new THREE.BufferGeometry());
  glintGeometry.setAttribute("position", glintPositions);
  glintGeometry.setAttribute("phase", new THREE.BufferAttribute(glintPhases, 1));
  glintGeometry.setAttribute("warmth", new THREE.BufferAttribute(glintWarmth, 1));
  const glintMaterial = keep(
    new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      uniforms: { time: { value: 0 }, cool: { value: white }, warm: { value: mix(THREE, white, orange500, 0.14) }, scale: { value: 1 } },
      vertexShader: `
        attribute float phase;
        attribute float warmth;
        uniform float time;
        uniform float scale;
        varying float glow;
        varying float heat;
        void main() {
          glow = pow(0.5 + 0.5 * sin(time * 2.6 + phase), 4.0);
          heat = warmth;
          vec4 view = modelViewMatrix * vec4(position, 1.0);
          // 멀리 있는 점도 가운데 빛이 한두 픽셀은 되게 한다 (너무 작으면 아예 안 찍힌다)
          gl_PointSize = scale * (5.0 + 13.0 * glow) * clamp(170.0 / -view.z, 0.5, 1.5);
          gl_Position = projectionMatrix * view;
        }`,
      // 가운데 둥근 빛에 가로세로로 가는 빛줄기를 더해 별처럼 반짝이게 한다. 어두울 때도 옅게 남아 물길이 보인다
      fragmentShader: `
        uniform vec3 cool;
        uniform vec3 warm;
        varying float glow;
        varying float heat;
        void main() {
          vec2 p = abs(gl_PointCoord - 0.5) * 2.0;
          float core = 1.0 - smoothstep(0.0, 0.6, length(p));
          float rays = max(exp(-p.x * 14.0) * (1.0 - p.y), exp(-p.y * 14.0) * (1.0 - p.x));
          gl_FragColor = vec4(mix(cool, warm, heat), clamp(core * 1.2 + rays, 0.0, 1.0) * (0.22 + 0.78 * glow));
        }`,
    }),
  );
  const glints = new THREE.Points(glintGeometry, glintMaterial);
  glints.frustumCulled = false; // 점을 옮겨도 다시 재지 않는다
  glints.renderOrder = 2; // 바다를 그린 뒤에 그린다. 먼저 그리면 반투명한 바다에 덮여 안 보인다
  scene.add(glints);

  // ------------------------------------------------------------------ 지나가는 배, 멀리 나는 갈매기 떼
  const hull = solid(white);
  const sail = keep(new THREE.MeshBasicMaterial({ color: blue500, side: THREE.DoubleSide }));
  const boats = [
    { z: 34, speed: 2.2, start: -150, size: 1 },
    { z: -46, speed: -1.5, start: 120, size: 1.5 },
    { z: -110, speed: 1.1, start: -40, size: 2 },
  ].map((info) => {
    const boat = new THREE.Group();
    const body = new THREE.Mesh(keep(new THREE.BoxGeometry(5, 0.9, 1.6)), hull);
    body.position.y = 0.55;
    const cabin = new THREE.Mesh(keep(new THREE.BoxGeometry(1.8, 0.8, 1.1)), hull);
    cabin.position.set(-0.6, 1.35, 0);
    const mast = keep(new THREE.BufferGeometry());
    mast.setAttribute("position", new THREE.Float32BufferAttribute([0.9, 1, 0, 0.9, 5.4, 0, 3.3, 1.2, 0], 3));
    boat.add(body, cabin, new THREE.Mesh(mast, sail));
    boat.scale.setScalar(info.size);
    scene.add(boat);
    return { ...info, boat };
  });

  const FLOCK = 9;
  const flockGeometry = keep(new THREE.BufferGeometry());
  const flockPositions = new Float32Array(FLOCK * 4 * 3);
  flockGeometry.setAttribute("position", new THREE.BufferAttribute(flockPositions, 3));
  scene.add(new THREE.LineSegments(flockGeometry, keep(new THREE.LineBasicMaterial({ color: grey700, transparent: true, opacity: 0.55 }))));
  function flyFlock(time: number) {
    for (let i = 0; i < FLOCK; i += 1) {
      const angle = time * (0.16 + (i % 3) * 0.03) + i * 0.7;
      const side = i % 2 === 0 ? -1 : 1;
      const cx = side * (58 + (i % 4) * 9) + Math.cos(angle) * 22;
      const cy = 34 + (i % 5) * 3 + Math.sin(angle * 1.7) * 2.5;
      const cz = -40 + Math.sin(angle) * 26;
      const flap = Math.sin(time * 7 + i) * 0.9;
      const heading = -Math.sin(angle) >= 0 ? 1 : -1;
      flockPositions.set([cx, cy, cz, cx - 1.7 * heading, cy + flap, cz - 1.1, cx, cy, cz, cx - 1.7 * heading, cy + flap, cz + 1.1], i * 12);
    }
    (flockGeometry.attributes.position as Three.BufferAttribute).needsUpdate = true;
  }

  // ------------------------------------------------------------------ 시점, 그리기
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
    // 세로 화면은 화각이 넓어 점이 크게 보이므로 줄인다
    glintMaterial.uniforms.scale.value = renderer.getPixelRatio() * (height / 760) * (portrait ? 0.6 : 1);
    // 해: 글 오른쪽, 수평선 바로 위에 보이는 방향으로 멀리 둔다
    camera.position.copy(cameraBase);
    camera.lookAt(lookAt);
    camera.updateMatrixWorld();
    sunRay.set(portrait ? 0.46 : 0.58, portrait ? -0.5 : -0.43, 0.5).unproject(camera).sub(cameraBase).normalize();
    sunPosition.copy(cameraBase).addScaledVector(sunRay, 1000);
    sunGlow.position.copy(sunPosition);
    sunDisc.position.copy(sunPosition);
    // 세로 화면에서는 해가 안내 글 뒤에 오므로 둥근 해는 빼고 옅은 빛만 남긴다
    sunDisc.visible = !portrait;
    sunGlow.material.opacity = portrait ? 0.55 : 1;
    layGlints();
  }

  const target = new THREE.Vector3();
  function draw(time: number) {
    eased.x += (pointer.x - eased.x) * 0.04;
    eased.y += (pointer.y - eased.y) * 0.04;
    // 처음에는 왼쪽 높은 곳에서 내려오며 다리가 펼쳐진다
    const arrive = 1 - easeOutCubic(time / INTRO_SECONDS);
    camera.position.set(
      cameraBase.x + Math.sin(time * 0.07) * 7 + eased.x * 5 - 64 * arrive,
      cameraBase.y - eased.y * 0.6 + 44 * arrive,
      cameraBase.z + Math.cos(time * 0.05) * 3 + 86 * arrive,
    );
    camera.lookAt(target.set(lookAt.x, lookAt.y - 13 * arrive, lookAt.z));
    waves(time);
    flowLights(time);
    driveCars(time);
    flyFlock(time);
    glintMaterial.uniforms.time.value = time;
    const blink = 0.55 + 0.45 * Math.sin(time * 3.2);
    for (const beacon of beacons) beacon.scale.setScalar(0.7 + 0.6 * blink);
    for (const info of boats) {
      const x = ((((info.start + info.speed * time + 260) % 520) + 520) % 520) - 260;
      info.boat.position.set(x, 0.2 + 0.25 * Math.sin(time * 1.3 + info.z), info.z);
      info.boat.rotation.y = info.speed > 0 ? 0 : Math.PI;
      info.boat.rotation.z = 0.04 * Math.sin(time * 1.1 + info.z);
    }
    renderer.render(scene, camera);
  }

  let frame = 0;
  let running = false;
  let clock = 0; // 장면 시간 (초). 실제 시간을 따라가고, 탭이 쉬는 동안은 흐르지 않는다
  let last = 0;
  function loop(now: number) {
    if (!running) return;
    // 프레임이 느린 기기에서도 도입이 늘어지지 않게 실제 흐른 시간만큼 간다 (한 번에 0.25초까지)
    const delta = Math.min(0.25, (now - last) / 1000);
    last = now;
    clock += delta;
    draw(clock);
    frame = requestAnimationFrame(loop);
  }
  function setRunning(next: boolean) {
    if (reduceMotion || next === running) return;
    running = next;
    cancelAnimationFrame(frame);
    if (running) {
      last = performance.now();
      frame = requestAnimationFrame(loop);
    }
  }
  /** 멈춘 한 장면: 도입이 끝난 뒤의 모습 (움직임 줄이기, 크기 바뀔 때) */
  const drawStill = () => draw(Math.max(clock, INTRO_SECONDS + 8));

  const resizeObserver = new ResizeObserver(() => {
    resize();
    if (!running) drawStill();
  });
  resizeObserver.observe(host);
  const onVisibility = () => setRunning(!document.hidden);
  document.addEventListener("visibilitychange", onVisibility);
  window.addEventListener("pointermove", onPointerMove, { passive: true });

  resize();
  if (reduceMotion) drawStill();
  else draw(0);
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
