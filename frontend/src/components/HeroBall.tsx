import { Component, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { ContactShadows, Environment, Float, Lightformer } from "@react-three/drei";
import { CssBall } from "./CssBall";

// ---- Panel centers: 12 pentagon (icosahedron vertices) + 20 hexagon
// (dodecahedron vertices). The spherical Voronoi of these 32 directions IS the
// truncated icosahedron — the classic 32-panel football. ----------------------
const PHI = (1 + Math.sqrt(5)) / 2;
const IP = 1 / PHI;
const v = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z).normalize();
const PANEL_CENTERS: THREE.Vector3[] = (() => {
  const penta: THREE.Vector3[] = [];
  for (const s1 of [-1, 1])
    for (const s2 of [-1, 1]) {
      penta.push(v(0, s1, s2 * PHI), v(s1, s2 * PHI, 0), v(s2 * PHI, 0, s1));
    }
  const hexa: THREE.Vector3[] = [];
  for (const x of [-1, 1]) for (const y of [-1, 1]) for (const z of [-1, 1]) hexa.push(v(x, y, z));
  for (const s1 of [-1, 1])
    for (const s2 of [-1, 1]) {
      hexa.push(v(0, s1 * IP, s2 * PHI), v(s1 * IP, s2 * PHI, 0), v(s2 * PHI, 0, s1 * IP));
    }
  return [...penta, ...hexa]; // pentagons are indices 0..11
})();

interface BallOpts {
  classic?: boolean; // true black pentagons (the user's iconic reference)
}

function buildBallMaterial({ classic = true }: BallOpts) {
  const mat = new THREE.MeshPhysicalMaterial({
    color: 0xffffff,
    metalness: 0.0,
    roughness: 0.42,
    clearcoat: 0.6,
    clearcoatRoughness: 0.28,
  });
  mat.onBeforeCompile = (sh) => {
    sh.uniforms.uCenters = { value: PANEL_CENTERS };
    sh.uniforms.uSeam = { value: 0.03 };
    sh.uniforms.uPuff = { value: 0.006 };
    sh.uniforms.uGroove = { value: 0.013 };
    sh.uniforms.uHex = { value: new THREE.Color(0xf1f3f8) }; // warm scuffed-leather white
    sh.uniforms.uPenta = { value: new THREE.Color(classic ? 0x070709 : 0x10131a) };
    sh.uniforms.uSeamCol = { value: new THREE.Color(0x05060a) };

    sh.vertexShader = sh.vertexShader
      .replace(
        "#include <common>",
        `#include <common>
        uniform vec3 uCenters[32]; uniform float uSeam; uniform float uPuff; uniform float uGroove;
        varying vec3 vDir;
        void nearest2(vec3 d, out float best, out float second){ best=-2.0; second=-2.0;
          for(int i=0;i<32;i++){ float dd=dot(d,uCenters[i]); if(dd>best){second=best;best=dd;} else if(dd>second){second=dd;} } }`
      )
      .replace(
        "#include <begin_vertex>",
        `#include <begin_vertex>
        vDir = normalize(position);
        float b, s2; nearest2(vDir, b, s2); float margin = b - s2;
        float puff = smoothstep(0.0, uSeam * 2.2, margin);
        float groove = 1.0 - smoothstep(0.0, uSeam, margin);
        transformed += normal * (puff * uPuff - groove * uGroove);`
      );

    sh.fragmentShader = sh.fragmentShader
      .replace(
        "#include <common>",
        `#include <common>
        uniform vec3 uCenters[32]; uniform float uSeam; uniform vec3 uHex; uniform vec3 uPenta; uniform vec3 uSeamCol;
        varying vec3 vDir;`
      )
      .replace(
        "#include <color_fragment>",
        `#include <color_fragment>
        float best=-2.0, second=-2.0; int bi=0;
        for(int i=0;i<32;i++){ float dd=dot(vDir,uCenters[i]); if(dd>best){second=best;best=dd;bi=i;} else if(dd>second){second=dd;} }
        float margin = best - second;
        vec3 panel = bi < 12 ? uPenta : uHex;
        float seam = 1.0 - smoothstep(uSeam * 0.35, uSeam * 1.05, margin);
        diffuseColor.rgb = mix(panel, uSeamCol, seam);`
      )
      .replace(
        "#include <roughnessmap_fragment>",
        `#include <roughnessmap_fragment>
        { float best=-2.0, second=-2.0; int bi=0;
          for(int i=0;i<32;i++){ float dd=dot(vDir,uCenters[i]); if(dd>best){second=best;best=dd;bi=i;} else if(dd>second){second=dd;} }
          float margin=best-second; float seam=1.0-smoothstep(uSeam*0.35,uSeam*1.05,margin);
          roughnessFactor = mix(bi<12 ? 0.6 : 0.4, 0.85, seam); }`
      );
  };
  return mat;
}

function Ball({
  active,
  reducedMotion,
  refreshTick,
}: {
  active: boolean;
  reducedMotion: boolean;
  refreshTick: number;
}) {
  const ballRef = useRef<THREE.Mesh>(null);
  const tiltRef = useRef<THREE.Group>(null);
  const kick = useRef(0);
  const geometry = useMemo(() => new THREE.IcosahedronGeometry(1, 48), []);
  const material = useMemo(() => buildBallMaterial({ classic: true }), []);
  const { pointer, invalidate } = useThree();

  useEffect(() => () => {
    geometry.dispose();
    material.dispose();
  }, [geometry, material]);

  // one-shot spin "kick" on refresh so the ball reacts to fresh data
  useEffect(() => {
    if (refreshTick > 0 && active) {
      kick.current = 6;
      invalidate();
    }
  }, [refreshTick, active, invalidate]);

  useFrame((_, delta) => {
    const d = Math.min(delta, 0.05);
    if (ballRef.current) {
      const base = reducedMotion ? 0 : 0.18;
      ballRef.current.rotation.y += (base + kick.current) * d;
      ballRef.current.rotation.x = 0.32 + Math.sin(performance.now() / 3200) * 0.05;
      kick.current = Math.max(0, kick.current - kick.current * 2.2 * d);
    }
    if (tiltRef.current && !reducedMotion) {
      // gentle pointer parallax
      tiltRef.current.rotation.y += (pointer.x * 0.18 - tiltRef.current.rotation.y) * 0.06;
      tiltRef.current.rotation.x += (-pointer.y * 0.12 - tiltRef.current.rotation.x) * 0.06;
    }
  });

  return (
    <group ref={tiltRef}>
      <Float speed={reducedMotion ? 0 : 1.3} rotationIntensity={0.15} floatIntensity={reducedMotion ? 0 : 0.6}>
        <mesh ref={ballRef} geometry={geometry} material={material} castShadow />
      </Float>
    </group>
  );
}

function Scene({
  active,
  reducedMotion,
  refreshTick,
  mobile,
}: {
  active: boolean;
  reducedMotion: boolean;
  refreshTick: number;
  mobile: boolean;
}) {
  return (
    <>
      <ambientLight intensity={0.18} color={0x0a0e14} />
      {/* KEY — floodlight spot, upper-left, defines rim + specular hot-spot */}
      <spotLight position={[-4, 5, 4]} angle={0.6} penumbra={0.6} decay={0} intensity={3.2} color={0xd6e8ff} castShadow />
      {/* FILL — cool, upper-right, keeps pentagons off pure black */}
      <directionalLight position={[5, 3, 2]} intensity={1.1} color={0x9fb6d8} />
      {/* RIM — cyan broadcast back-light (desktop only) */}
      {!mobile && <directionalLight position={[0, -1, -5]} intensity={2.2} color={0x38e1d6} />}

      <Float speed={0} floatIntensity={0}>
        <Ball active={active} reducedMotion={reducedMotion} refreshTick={refreshTick} />
      </Float>

      <ContactShadows
        position={[0, -1.25, 0]}
        opacity={0.55}
        scale={6}
        blur={2.6}
        far={3}
        resolution={mobile ? 256 : 512}
        color="#04111a"
      />

      {/* In-code studio reflections for the clearcoat (no HDRI fetch). */}
      <Environment resolution={128} frames={1}>
        <Lightformer intensity={2} position={[-3, 3, 3]} scale={[5, 5, 1]} color="#d6e8ff" />
        <Lightformer intensity={1.2} position={[4, 2, 2]} scale={[4, 4, 1]} color="#9fb6d8" />
        <Lightformer intensity={0.8} position={[0, -2, -4]} scale={[6, 6, 1]} color="#38e1d6" />
      </Environment>
    </>
  );
}

// --- Error boundary: any WebGL/context-loss error swaps to the CSS ball -------
class GLBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

function webglSupported(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

export default function HeroBall({ size = 300, refreshTick = 0 }: { size?: number; refreshTick?: number }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [supported] = useState(webglSupported);
  const [inView, setInView] = useState(true);
  const [docVisible, setDocVisible] = useState(true);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [mobile, setMobile] = useState(false);

  useEffect(() => {
    const rm = window.matchMedia("(prefers-reduced-motion: reduce)");
    const mb = window.matchMedia("(max-width: 768px)");
    const sync = () => {
      setReducedMotion(rm.matches);
      setMobile(mb.matches);
    };
    sync();
    rm.addEventListener("change", sync);
    mb.addEventListener("change", sync);
    const onVis = () => setDocVisible(!document.hidden);
    document.addEventListener("visibilitychange", onVis);
    return () => {
      rm.removeEventListener("change", sync);
      mb.removeEventListener("change", sync);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);

  useEffect(() => {
    if (!wrapRef.current) return;
    const io = new IntersectionObserver(([e]) => setInView(e.isIntersecting), { threshold: 0.05 });
    io.observe(wrapRef.current);
    return () => io.disconnect();
  }, []);

  const active = inView && docVisible && !reducedMotion;

  return (
    <div ref={wrapRef} className="grid place-items-center" style={{ width: size, height: size }}>
      {!supported ? (
        <CssBall size={size} />
      ) : (
        <GLBoundary fallback={<CssBall size={size} />}>
          <Canvas
            dpr={[1, mobile ? 1.5 : 1.75]}
            frameloop={active ? "always" : "demand"}
            gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
            camera={{ position: [0, 0, 4.4], fov: 30 }}
            style={{ width: size, height: size }}
          >
            <Scene active={active} reducedMotion={reducedMotion} refreshTick={refreshTick} mobile={mobile} />
          </Canvas>
        </GLBoundary>
      )}
    </div>
  );
}
