import { ImageResponse } from 'next/og'

export const runtime = 'edge'
export const alt = 'Lowball — Singapore Salary Checker'
export const size = { width: 1200, height: 630 }
export const contentType = 'image/png'

export default function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          background: '#0f172a',
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          padding: '80px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: '32px' }}>
          <span style={{ fontSize: '48px', fontWeight: 700, color: '#f8fafc', letterSpacing: '-1px' }}>
            Lowball
          </span>
        </div>
        <div
          style={{
            fontSize: '60px',
            fontWeight: 700,
            color: '#f8fafc',
            lineHeight: 1.15,
            marginBottom: '32px',
            letterSpacing: '-2px',
          }}
        >
          Is your salary offer fair?
        </div>
        <div style={{ fontSize: '28px', color: '#94a3b8', lineHeight: 1.5 }}>
          Benchmark against 135k live Singapore job listings — free, no signup.
        </div>
        <div
          style={{
            marginTop: '48px',
            fontSize: '22px',
            color: '#38bdf8',
            fontWeight: 500,
          }}
        >
          sglowball.vercel.app
        </div>
      </div>
    ),
    { ...size }
  )
}
