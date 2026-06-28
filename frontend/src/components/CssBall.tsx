// Dependency-free fallback football, occupying the IDENTICAL hero slot as the
// 3D ball so layout never shifts. Used as the Suspense fallback, the no-WebGL
// fallback, and the error-boundary fallback. The slow spin freezes under
// prefers-reduced-motion (handled globally in index.css).
export function CssBall({ size = 240 }: { size?: number }) {
  return (
    <div
      className="relative grid place-items-center"
      style={{ width: size, height: size }}
      role="img"
      aria-label="Football"
    >
      {/* plinth glow */}
      <div
        className="absolute rounded-full"
        style={{
          width: size * 0.72,
          height: size * 0.16,
          bottom: size * 0.02,
          background: "radial-gradient(closest-side, rgba(56,225,214,0.28), transparent 70%)",
          filter: "blur(6px)",
        }}
      />
      <div
        className="relative rounded-full"
        style={{
          width: size * 0.82,
          height: size * 0.82,
          background:
            "radial-gradient(circle at 36% 30%, #ffffff 0%, #eef1f6 30%, #d4d8e0 68%, #aab0bd 100%)",
          boxShadow:
            "0 0 0 1px rgba(56,225,214,0.25), 0 0 38px -6px rgba(56,225,214,0.35), inset -10px -14px 30px rgba(0,0,0,0.35)",
          animation: "spin 14s linear infinite",
        }}
      >
        <svg viewBox="0 0 100 100" className="absolute inset-0 h-full w-full" aria-hidden>
          <defs>
            <clipPath id="ballclip">
              <circle cx="50" cy="50" r="50" />
            </clipPath>
          </defs>
          <g clipPath="url(#ballclip)" fill="#0b0d12">
            {/* central pentagon */}
            <polygon points="50,30 61,38 57,51 43,51 39,38" />
            {/* ring of partial pentagons */}
            <polygon points="50,4 60,12 54,24 46,24 40,12" />
            <polygon points="86,34 92,48 82,56 73,47 78,35" />
            <polygon points="72,82 60,88 52,78 60,68 71,71" />
            <polygon points="28,82 40,88 48,78 40,68 29,71" />
            <polygon points="14,34 8,48 18,56 27,47 22,35" />
          </g>
          {/* seams */}
          <g stroke="rgba(20,22,30,0.55)" strokeWidth="1.1" fill="none" clipPath="url(#ballclip)">
            <path d="M50,30 L50,12 M61,38 L80,34 M57,51 L66,70 M43,51 L34,70 M39,38 L20,34" />
          </g>
        </svg>
      </div>
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}
