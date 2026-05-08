import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

export function FocusPage() {
  return (
    <div className="min-h-screen bg-[#090909] px-4 py-12 text-[#e8dcc8] sm:px-6 lg:px-8">
      <div className="mx-auto max-w-5xl">
        <Card className="rounded-[1.5rem] border border-[#4a7c59]/20 bg-[#111111]/95">
          <CardHeader className="px-6 pt-6">
            <CardTitle className="text-lg text-[#e8dcc8]">Focus</CardTitle>
          </CardHeader>
          <CardContent className="p-6">
            <p className="text-sm text-[#d4c5a9]">Coming Soon!</p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
