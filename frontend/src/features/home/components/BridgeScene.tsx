"use client";

import { useEffect, useRef } from "react";
import { mountFireworks } from "../fireworks";

/**
 * 홈 배경 (꾸밈): 옅은 하늘 위에 불꽃(2D)을 깔고, 그 위에 광안대교 3D 장면을 올린다. 그래서 불꽃이 다리 뒤 하늘에서 터진다.
 * three.js와 장면 코드는 첫 화면이 뜬 뒤에 따로 불러와서 첫 화면을 막지 않는다.
 * WebGL을 못 쓰는 브라우저에서는 다리 없이 하늘과 불꽃만 보인다.
 */
export function BridgeScene() {
  const sky = useRef<HTMLDivElement>(null);
  const bridge = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const skyEl = sky.current;
    const bridgeEl = bridge.current;
    if (!skyEl || !bridgeEl) return;
    let cancelled = false;
    let unmountBridge = () => {};
    const unmountFireworks = mountFireworks(skyEl);
    Promise.all([import("three"), import("../bridge")])
      .then(([THREE, { mountBridge }]) => {
        if (!cancelled) unmountBridge = mountBridge(THREE, bridgeEl);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
      unmountFireworks();
      unmountBridge();
    };
  }, []);

  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 bg-linear-to-b from-white via-white to-blue-50">
      <div ref={sky} className="absolute inset-0" />
      <div ref={bridge} className="absolute inset-0" />
    </div>
  );
}
