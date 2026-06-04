// Inline SVG icons. Each component renders a 16x16 svg unless `size` is set.
import { CSSProperties } from "react";

interface P { size?: number; style?: CSSProperties; className?: string }
const Svg = ({ size = 16, style, className, children }: P & { children: React.ReactNode }) => (
  <svg width={size} height={size} viewBox="0 0 16 16" style={style} className={className} fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
    {children}
  </svg>
);
export const IPlay = (p: P) => <Svg {...p}><path d="M4 2.5v11l9-5.5z" fill="currentColor" stroke="none"/></Svg>;
export const IPause = (p: P) => <Svg {...p}><rect x="3.5" y="2.5" width="3" height="11" fill="currentColor" stroke="none"/><rect x="9.5" y="2.5" width="3" height="11" fill="currentColor" stroke="none"/></Svg>;
export const IRegen = (p: P) => <Svg {...p}><path d="M13.5 4a5.5 5.5 0 1 0 1.4 5"/><path d="M14 1v3.5h-3.5"/></Svg>;
export const INote = (p: P) => <Svg {...p}><path d="M3 2.5h7l3 3v8h-10z"/><path d="M10 2.5v3h3"/><path d="M5 9h6M5 11.5h6"/></Svg>;
export const IBrace = (p: P) => <Svg {...p}><path d="M6.5 2.5C4.5 2.5 4.5 5 4.5 6S3 8 3 8s1.5 0 1.5 1S4.5 13.5 6.5 13.5"/><path d="M9.5 2.5C11.5 2.5 11.5 5 11.5 6S13 8 13 8s-1.5 0-1.5 1 0 4.5-2 4.5"/></Svg>;
export const IPlus = (p: P) => <Svg {...p}><path d="M8 3.5v9M3.5 8h9"/></Svg>;
export const IChevron = (p: P) => <Svg {...p}><path d="M4 6l4 4 4-4"/></Svg>;
export const IX = (p: P) => <Svg {...p}><path d="M4 4l8 8M12 4l-8 8"/></Svg>;
export const IDL = (p: P) => <Svg {...p}><path d="M8 2v9M4.5 7.5L8 11l3.5-3.5"/><path d="M3 13.5h10"/></Svg>;
export const IFolder = (p: P) => <Svg {...p}><path d="M2.5 4.5v8h11v-7H7.5L6 4.5z"/></Svg>;
export const IList = (p: P) => <Svg {...p}><path d="M5.5 4h8M5.5 8h8M5.5 12h8"/><path d="M2.5 4h.01M2.5 8h.01M2.5 12h.01"/></Svg>;
export const ITerminal = (p: P) => <Svg {...p}><rect x="1.5" y="2.5" width="13" height="11" rx="1.5"/><path d="M4 6l2.5 2L4 10M8.5 10.5H12"/></Svg>;
