/** Shared vector mark: three luminous eyes remain legible at sidebar size. */
export default function RavenMark() {
  return (
    <svg className="raven-logo" viewBox="0 0 120 120" aria-hidden="true" focusable="false">
      <path
        d="M18 105 27 76 29 55 20 59 33 42 27 42 46 29 40 23 58 28 56 19 70 30 88 32 105 42 115 56 96 49 82 50 72 60 68 77 73 104 57 96 52 108 43 96 32 108 31 98Z"
        fill="#22272c" stroke="#b99b6b" strokeWidth="2.5" strokeLinejoin="round"
      />
      <path d="m77 38 23 6 9 8-27-7-11 10M30 73l15-9-9 18m7 4 14-16-8 23M35 45l21-9"
        fill="none" stroke="#6f777c" strokeWidth="2" strokeLinecap="round" />
      <path d="m29 97 6-10m23 7 3-14" stroke="#b99b6b" strokeWidth="1.5" />
      {[{ x: 44, y: 51 }, { x: 57, y: 44 }, { x: 71, y: 41 }].map(({ x, y }) => (
        <g key={x}>
          <circle cx={x} cy={y} r="7" fill="#ba397f" opacity=".25" />
          <circle cx={x} cy={y} r="4.3" fill="#ec69c3" />
          <circle cx={x - 1} cy={y - 1} r="1.7" fill="#ffe4f9" />
        </g>
      ))}
    </svg>
  );
}
