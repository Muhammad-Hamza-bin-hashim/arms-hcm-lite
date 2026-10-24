import { useEffect, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { EmptyState } from './ui'

/** Reads chart tokens from CSS so SVG marks follow light/dark mode (validated: #0E9384 light, #0FA394 dark). */
function useChartTokens() {
  const read = () => {
    const s = getComputedStyle(document.documentElement)
    return {
      series: s.getPropertyValue('--chart').trim() || '#0e9384',
      grid: s.getPropertyValue('--chart-grid').trim() || '#edf0f5',
      muted: s.getPropertyValue('--muted').trim() || '#5b6577',
      surface: s.getPropertyValue('--surface').trim() || '#fff',
      border: s.getPropertyValue('--border').trim() || '#e3e8ef',
      text: s.getPropertyValue('--text').trim() || '#0f1e3a',
    }
  }
  const [tokens, setTokens] = useState(read)
  useEffect(() => {
    const obs = new MutationObserver(() => setTokens(read()))
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
    return () => obs.disconnect()
  }, [])
  return tokens
}

const compact = (v: number) => (Math.abs(v) >= 1_000_000 ? `${+(v / 1_000_000).toFixed(1)}M` : Math.abs(v) >= 1000 ? `${+(v / 1000).toFixed(1)}K` : `${v}`)

type Datum = Record<string, string | number | null>

function tooltipStyle(t: ReturnType<typeof useChartTokens>) {
  return {
    contentStyle: { background: t.surface, border: `1px solid ${t.border}`, borderRadius: 8, fontSize: 12, color: t.text },
    labelStyle: { color: t.muted, marginBottom: 2 },
    itemStyle: { color: t.text },
  }
}

/** Single-series bars: 24px max thickness, 4px rounded data end, recessive grid, hover tooltip. */
export function BarSeries({ data, x, y, name, horizontal, format = (v) => compact(v), height = 240 }:
  { data: Datum[]; x: string; y: string; name: string; horizontal?: boolean; format?: (v: number) => string; height?: number }) {
  const t = useChartTokens()
  if (!data.length) return <EmptyState title="No data for these filters" />
  const axisProps = { tick: { fill: t.muted, fontSize: 11 }, axisLine: false, tickLine: false }
  const h = horizontal ? Math.max(height, data.length * 34 + 30) : height
  return (
    <div style={{ height: h }} role="img" aria-label={`${name} chart`}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout={horizontal ? 'vertical' : 'horizontal'} margin={{ top: 8, right: 16, bottom: 0, left: horizontal ? 8 : -8 }} barCategoryGap="30%">
          <CartesianGrid stroke={t.grid} vertical={Boolean(horizontal)} horizontal={!horizontal} />
          {horizontal ? (
            <>
              <XAxis type="number" {...axisProps} tickFormatter={format} allowDecimals={false} />
              <YAxis type="category" dataKey={x} {...axisProps} width={96} />
            </>
          ) : (
            <>
              <XAxis dataKey={x} {...axisProps} interval={0} />
              <YAxis {...axisProps} tickFormatter={format} allowDecimals={false} />
            </>
          )}
          <Tooltip cursor={{ fill: t.grid, opacity: 0.6 }} formatter={(v) => [format(Number(v)), name]} {...tooltipStyle(t)} />
          <Bar dataKey={y} name={name} fill={t.series} maxBarSize={24} radius={horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Single-series trend line: 2px line, 8px end dot with surface ring, crosshair tooltip. */
export function TrendLine({ data, x, y, name, format = (v) => `${v}`, domain, height = 240 }:
  { data: Datum[]; x: string; y: string; name: string; format?: (v: number) => string; domain?: [number, number]; height?: number }) {
  const t = useChartTokens()
  if (!data.length) return <EmptyState title="No working days in this range yet" />
  const axisProps = { tick: { fill: t.muted, fontSize: 11 }, axisLine: false, tickLine: false }
  const last = data.length - 1
  return (
    <div style={{ height }} role="img" aria-label={`${name} trend`}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 12, right: 16, bottom: 0, left: -8 }}>
          <CartesianGrid stroke={t.grid} vertical={false} />
          <XAxis dataKey={x} {...axisProps} minTickGap={24} />
          <YAxis {...axisProps} domain={domain} tickFormatter={format} />
          <Tooltip cursor={{ stroke: t.muted, strokeWidth: 1 }} formatter={(v) => [v === null ? '—' : format(Number(v)), name]} {...tooltipStyle(t)} />
          <Line type="monotone" dataKey={y} name={name} stroke={t.series} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"
            connectNulls isAnimationActive={false}
            dot={(p: { index?: number; cx?: number; cy?: number }) => p.index === last && p.cx != null && p.cy != null
              ? <circle key="end" cx={p.cx} cy={p.cy} r={4} fill={t.series} stroke={t.surface} strokeWidth={2} />
              : <g key={p.index} />}
            activeDot={{ r: 5, fill: t.series, stroke: t.surface, strokeWidth: 2 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Accessible table alternative for any chart. */
export function DataTable({ rows, columns }: { rows: Datum[]; columns: { key: string; label: string; format?: (v: never) => string }[] }) {
  if (!rows.length) return null
  return (
    <details className="mt-3 text-xs">
      <summary className="cursor-pointer text-muted hover:text-ink">View as table</summary>
      <table className="mt-2 w-full text-left">
        <thead><tr className="text-muted">{columns.map((c) => <th key={c.key} className="py-1 font-medium">{c.label}</th>)}</tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-line">
              {columns.map((c) => <td key={c.key} className="tabular py-1">{c.format ? c.format(r[c.key] as never) : String(r[c.key] ?? '—')}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  )
}
