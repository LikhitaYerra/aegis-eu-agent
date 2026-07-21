import type { LucideIcon } from 'lucide-react'

type MetricCardProps = {
  icon: LucideIcon
  label: string
  value: string
  detail: string
}

export function MetricCard({ icon: Icon, label, value, detail }: MetricCardProps) {
  return (
    <div className="metric-card">
      <div className="metric-icon">
        <Icon size={17} aria-hidden="true" />
      </div>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </div>
  )
}
