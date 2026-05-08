type AvatarLike = {
  name?: string | null
  level?: number
  is_alive?: boolean
  health?: number
  max_health?: number
  energy?: number
  max_energy?: number
  avatar_url?: string | null
  avatar_type?: { image_url?: string | null } | null
}

export function CharacterWidget({ character }: { character?: AvatarLike | null }) {
  if (!character) {
    return (
      <div className="rounded-[1.25rem] border border-[#2a2a2a] bg-[#141414]/95 p-4 text-center">
        <p className="text-sm text-[#d4c5a9]">No character created yet.</p>
      </div>
    )
  }

  const rawImage = character.avatar_url ?? character.avatar_type?.image_url ?? null
  let imageUrl: string | null = null
  if (rawImage) {
    // If it's an absolute URL or starts with '/', use as-is. Otherwise resolve relative to base.
    if (/^https?:\/\//.test(rawImage) || rawImage.startsWith("/")) {
      imageUrl = rawImage
    } else {
      const base = import.meta.env.BASE_URL ?? "/"
      imageUrl = `${base.replace(/\/$/, "")}/${rawImage.replace(/^\//, "")}`
    }
  }

  const initials = character.name ? character.name.charAt(0).toUpperCase() : "?"

  return (
    <div className="rounded-[1.25rem] border border-[#2a2a2a] bg-[#0f0f0f]/90 p-4">
      <div className="flex items-center gap-3">
        <div className="relative h-12 w-12 shrink-0">
          {imageUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={imageUrl}
              alt={character.name ?? "avatar"}
              className="h-12 w-12 rounded-full object-cover"
            />
          ) : (
            <div className="h-12 w-12 rounded-full bg-gradient-to-br from-[#4a7c59]/30 to-[#6aab7e]/20 flex items-center justify-center text-[#e8dcc8]">{initials}</div>
          )}
        </div>
        <div>
          <p className="text-sm font-semibold text-[#e8dcc8]">{character.name}</p>
          <p className="text-xs text-[#d4c5a9]/80">Level {character.level ?? 1} • {character.is_alive ? "Alive" : "Deceased"}</p>
        </div>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-2 text-sm">
        <div className="rounded-md bg-[#111111]/80 p-2 text-center">
          <div className="text-xs text-[#d4c5a9]">HP</div>
          <div className="text-sm font-semibold text-[#e8dcc8]">{character.health ?? 0}/{character.max_health ?? 0}</div>
        </div>
        <div className="rounded-md bg-[#111111]/80 p-2 text-center">
          <div className="text-xs text-[#d4c5a9]">Energy</div>
          <div className="text-sm font-semibold text-[#e8dcc8]">{character.energy ?? 0}/{character.max_energy ?? 0}</div>
        </div>
      </div>
    </div>
  )
}
