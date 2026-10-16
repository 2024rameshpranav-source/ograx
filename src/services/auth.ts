export type DemoSession = {
  email: string
  name?: string
  remember?: boolean
  at: string
}

const sessionKey = "aquasignal-demo-auth"

export const authService = {
  getSession(): DemoSession | null {
    try {
      return JSON.parse(localStorage.getItem(sessionKey) || "null")
    } catch {
      return null
    }
  },
  signIn(email: string, remember: boolean): DemoSession {
    const session = { email, remember, at: new Date().toISOString() }
    localStorage.setItem(sessionKey, JSON.stringify(session))
    return session
  },
  signUp(name: string, email: string): DemoSession {
    const session = { name, email, at: new Date().toISOString() }
    localStorage.setItem(sessionKey, JSON.stringify(session))
    return session
  },
  signOut() {
    localStorage.removeItem(sessionKey)
  },
}
