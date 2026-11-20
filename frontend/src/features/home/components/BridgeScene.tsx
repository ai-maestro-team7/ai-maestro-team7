"use client";

import { useEffect, useRef } from "react";

/**
 * 홈 배경의 광안대교 3D 장면 자리 (꾸밈). three.js와 장면 코드는 첫 화면이 뜬 뒤에 따로 불러와서 첫 화면을 막지 않는다.
 * WebGL을 못 쓰는 브라우저에서는 아무것도 그리지 않고 뒤의 옅은 하늘색만 보인다.
 */
export function BridgeScene() {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    let cancelled = false;
    let unmount = () => {};
    Promise.all([import("three"), import("../bridge")])
      .then(([THREE, { mountBridge }]) => {
        if (!cancelled) unmount = mountBridge(THREE, element);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
      unmount();
    };
  }, []);

  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 bg-linear-to-b from-white via-white to-blue-50">
      <div ref={host} className="absolute inset-0" />
    </div>
  );
}
