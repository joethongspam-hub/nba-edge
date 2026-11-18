import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = { title: 'NBA EDGE | Player Prop Odds', description: 'Compare NBA player prop lines from DraftKings and FanDuel.' };
export default function RootLayout({children}:{children:React.ReactNode}) { return <html lang="en"><body>{children}</body></html>; }
