import type { City } from "../data/geography"
import { appConfig } from "../config"
import { apiClient } from "./api"

export type CoordinateSource = "gps" | "manual" | "area_centre"

export type DemoReport = {
  id: string
  city: City
  area: string
  latitude: number
  longitude: number
  landmark: string
  severity: string
  description: string
  access: string
  evidenceReference?: string
  coordinateSource?: CoordinateSource
  accuracyM?: number
  photoUrl?: string
  createdAt: string
  updatedAt: string
  status: "UNVERIFIED REPORT" | "CORROBORATED" | "ADMIN-VERIFIED"
}

const reportKey = "aquasignal-demo-reports"

export const reportService = {
  list(): DemoReport[] {
    try {
      return JSON.parse(localStorage.getItem(reportKey) || "[]")
    } catch {
      return []
    }
  },

  /**
   * Save a report to local browser storage only
   */
  saveLocal(report: DemoReport): DemoReport[] {
    const reports = [report, ...this.list().filter((item) => item.id !== report.id)]
    localStorage.setItem(reportKey, JSON.stringify(reports))
    return reports
  },

  /**
   * Synchronous local save helper preserved for existing demo flows
   */
  save(report: DemoReport): DemoReport[] {
    return this.saveLocal(report)
  },

  /**
   * Directly submit to the backend API without silent fallback.
   * Throws an error on network or HTTP failure so UI can display proper error.
   */
  async submitToBackend(report: Omit<DemoReport, "createdAt" | "updatedAt">): Promise<DemoReport> {
    const saved = await apiClient.createReport(report)
    // Cache the successfully returned backend report locally for offline resilience
    const local = [saved, ...this.list().filter((item) => item.id !== saved.id)]
    localStorage.setItem(reportKey, JSON.stringify(local))
    return saved
  },

  replace(reports: DemoReport[]) {
    localStorage.setItem(reportKey, JSON.stringify(reports))
  },

  /**
   * Fetches latest reports from the backend SQLite database and syncs to local storage
   */
  async syncFromBackend(city?: string): Promise<DemoReport[]> {
    try {
      const result = await apiClient.getReports({ city })
      if (result && Array.isArray(result.reports)) {
        this.replace(result.reports)
        return result.reports
      }
    } catch (err) {
      console.warn("Could not sync reports from backend, using local storage:", err)
    }
    return this.list()
  },
}
