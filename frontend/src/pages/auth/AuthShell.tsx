import type { ReactNode } from 'react'
import { Logo } from '../../components/Logo'

export function AuthShell({ title, subtitle, children }: { title: string; subtitle?: ReactNode; children: ReactNode }) {
  return (
    <div className="flex min-h-full">
      <div className="relative hidden w-[44%] flex-col justify-between overflow-hidden bg-navy-2 p-10 text-white lg:flex dark:bg-navy">
        <Logo inverted />
        <div className="relative z-10 max-w-md">
          <h2 className="text-3xl font-semibold leading-tight">People operations, attendance, leave and payroll in one place.</h2>
          <p className="mt-4 text-white/70">AR&amp;MS HCM Lite gives Admin, HR and every employee their own workspace, with an assistant that answers from live records.</p>
        </div>
        <p className="text-xs text-white/40">AR&amp;MS Management Company · HCM Lite</p>
        <div className="absolute -right-24 -bottom-24 size-96 rounded-full bg-[#14B8A6]/20" aria-hidden />
        <div className="absolute -right-10 top-24 size-40 rounded-full bg-[#14B8A6]/10" aria-hidden />
      </div>
      <div className="flex flex-1 items-center justify-center px-4 py-10">
        <div className="w-full max-w-sm">
          <div className="mb-8 lg:hidden"><Logo /></div>
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          {subtitle && <p className="mt-1.5 text-sm text-muted">{subtitle}</p>}
          <div className="mt-6">{children}</div>
        </div>
      </div>
    </div>
  )
}
