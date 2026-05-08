export function StatBar({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between rounded-md bg-[#0f0f0f]/80 px-3 py-2">
      <div className="text-xs text-[#d4c5a9]/80">{label}</div>
      <div className="text-sm font-semibold text-[#e8dcc8]">{value}</div>
    </div>
  )
}
