"use client";

import { useEffect, useRef } from "react";

export default function FogLayer() {
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap) return;

    const handleMouseMove = (e: MouseEvent) => {
      const x = (e.clientX / window.innerWidth - 0.5) * 20;
      const y = (e.clientY / window.innerHeight - 0.5) * 20;
      wrap.style.transform = `translate(${x}px, ${y}px)`;
    };

    window.addEventListener("mousemove", handleMouseMove);
    return () => window.removeEventListener("mousemove", handleMouseMove);
  }, []);

  return (
    <div className="fogWrap" ref={wrapRef} aria-hidden="true">
      <div className="fog fog1" />
      <div className="fog fog2" />
      <div className="fog fog3" />
    </div>
  );
}
