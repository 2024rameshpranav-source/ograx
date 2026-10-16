const trimTrailingSlash = (value: string) => value.replace(/\/+$/, "")

export const appConfig = {
  apiUrl: trimTrailingSlash(import.meta.env.VITE_API_URL || ""),
  authMode: import.meta.env.VITE_AUTH_MODE || "demo",
  reportStorage: import.meta.env.VITE_REPORT_STORAGE || "local",
  mapTileUrl:
    import.meta.env.VITE_MAP_TILE_URL ||
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
  mapAttribution:
    import.meta.env.VITE_MAP_ATTRIBUTION || "© OpenStreetMap contributors",
}

export const hasBackend = Boolean(appConfig.apiUrl)
